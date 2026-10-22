"""Build a sanitized featured data bundle from already collected local data."""

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.core.clock import iso_z
from backend.app.persistence.models import ActivityWindow, AnalysisResult, Dataset, DatasetRepository, Repository, RepositoryActivityEvent, RepositoryInsightRun, RepositorySnapshot
from backend.app.pipeline.collection_archive import iter_module_records
from backend.app.pipeline.raw_archive import read_archive
from backend.app.services.dataset_import import BUNDLE_ROOT, FEATURED_ID, MODULES


def build_featured_bundle(session: Session, version: str, output: Path = BUNDLE_ROOT, *, force: bool = False) -> dict:
    if not version or len(version) > 64 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in version):
        raise ValueError("version must contain 1–64 letters, digits, dot, underscore or hyphen")
    dataset = session.get(Dataset, FEATURED_ID)
    if dataset is None or dataset.type != "featured":
        raise ValueError("featured-default dataset is missing")
    memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == FEATURED_ID).order_by(DatasetRepository.repository_id)).all()
    if len(memberships) != 15:
        raise ValueError(f"featured-default requires 15 reviewed members; found {len(memberships)}")
    if any(not member.inclusion_reason or not member.inclusion_reason.strip() for member in memberships):
        raise ValueError("every featured member needs a human-reviewed inclusion_reason")
    repository_ids = [member.repository_id for member in memberships]
    repositories = [session.get(Repository, repository_id) for repository_id in repository_ids]
    if any(repo is None for repo in repositories):
        raise ValueError("featured-default contains a missing repository record")
    repo_by_id = {repo.repository_id: repo for repo in repositories if repo is not None}
    snapshots = {}
    analyses = []
    insights = []
    coverage_rows = []
    events: dict[str, list[dict]] = {module: [] for module in MODULES}
    details: dict[str, list[dict]] = {module: [] for module in MODULES}
    event_task_ids: dict[int, set[str]] = {}
    warnings = []
    data_as_of = None

    for repository_id in repository_ids:
        snapshot = session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id == repository_id, RepositorySnapshot.valid.is_(True)).order_by(desc(RepositorySnapshot.collected_at), desc(RepositorySnapshot.id)).limit(1))
        if snapshot:
            snapshots[repository_id] = snapshot
            data_as_of = max(data_as_of, snapshot.collected_at) if data_as_of else snapshot.collected_at
        else:
            warnings.append(f"repository {repository_id} has no snapshot")
        for kind in ("basic", "deep"):
            analysis = session.scalar(select(AnalysisResult).where(AnalysisResult.repository_id == repository_id, AnalysisResult.analysis_kind == kind).order_by(desc(AnalysisResult.source_collected_at), desc(AnalysisResult.result_id)).limit(1))
            if analysis:
                analyses.append(_analysis_record(analysis))
        window = session.scalar(select(ActivityWindow).where(ActivityWindow.repository_id == repository_id).order_by(desc(ActivityWindow.collected_at)).limit(1))
        if window:
            coverage = _coverage_record(window)
            coverage_rows.append(coverage)
            for module in MODULES:
                module_coverage = coverage["modules"].get(module)
                if module_coverage != "complete":
                    warnings.append(f"repository {repository_id} {module} coverage is {module_coverage or 'unknown'}")
        else:
            warnings.append(f"repository {repository_id} has no activity coverage")
        run = session.scalar(select(RepositoryInsightRun).where(RepositoryInsightRun.repository_id == repository_id).order_by(desc(RepositoryInsightRun.analyzed_at)).limit(1))
        if run:
            insights.append(_insight_record(run))
            _collect_details(repository_id, run.source_archive_paths_json, details, warnings)
            try:
                task_ids = json.loads(run.source_task_ids_json)
            except (TypeError, ValueError):
                task_ids = []
            event_task_ids[repository_id] = {value for value in task_ids if isinstance(value, str)} if isinstance(task_ids, list) else set()
        else:
            warnings.append(f"repository {repository_id} has no event insight")
            event_task_ids[repository_id] = set()
        event_query = select(RepositoryActivityEvent).where(RepositoryActivityEvent.repository_id == repository_id)
        if event_task_ids[repository_id]:
            event_query = event_query.where(RepositoryActivityEvent.source_task_id.in_(event_task_ids[repository_id]))
        else:
            event_query = event_query.where(RepositoryActivityEvent.source_task_id == "")
        for event in session.scalars(event_query.order_by(RepositoryActivityEvent.event_at, RepositoryActivityEvent.source_item_id)).all():
            module = {"commit": "commits", "issue": "issues", "pull_request": "pulls", "release": "releases"}.get(event.event_type)
            if module:
                events[module].append(_event_record(event))

    if data_as_of is None:
        raise ValueError("featured members have no repository snapshots")
    repository_records = [_repository_record(repo) for repo in repo_by_id.values()]
    snapshot_records = [_snapshot_record(snapshot) for snapshot in snapshots.values()]
    member_records = [{"repository_id": member.repository_id, "added_at": iso_z(member.added_at), "selection_tier": member.selection_tier, "inclusion_reason": _redact_emails(member.inclusion_reason)} for member in memberships]

    target = output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (target / "dataset.json").exists() and not force:
        raise FileExistsError(f"{target} already contains a dataset bundle; pass --force to replace it")
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        _write_jsonl(stage / "repositories.jsonl.gz", repository_records)
        _write_jsonl(stage / "snapshots.jsonl.gz", snapshot_records)
        _write_jsonl(stage / "memberships.jsonl.gz", member_records)
        _write_jsonl(stage / "analysis.jsonl.gz", analyses)
        _write_jsonl(stage / "insights.jsonl.gz", insights)
        _write_jsonl(stage / "coverage.jsonl.gz", coverage_rows)
        for module in MODULES:
            _write_jsonl(stage / f"events/{module}.jsonl.gz", events[module])
            _write_jsonl(stage / f"details/{module}.jsonl.gz", details[module])
        (stage / "README.md").write_text(_bundle_readme(version, data_as_of, len(warnings)), encoding="utf-8")
        (stage / "DATA_NOTICE.md").write_text(_data_notice(data_as_of), encoding="utf-8")
        (stage / "schemas").mkdir()
        _write_schemas(stage / "schemas")
        coverage_summary = {
            module: sum(row.get("modules", {}).get(module) == "complete" for row in coverage_rows)
            for module in MODULES
        }
        metadata = {
            "schema_version": 1,
            "dataset_id": FEATURED_ID,
            "version": version,
            "generated_at": iso_z(datetime.now(UTC)),
            "data_as_of": iso_z(data_as_of),
            "source": "GitHub REST API, collected and stored locally by RepoVantage",
            "total_repositories": len(repository_records),
            "candidate_list": "data/manifests/featured-v1-candidates.json",
            "rules_version": dataset.rules_version,
            "quality": "complete" if not warnings and all(count == len(repository_ids) for count in coverage_summary.values()) else "partial",
            "coverage_summary": coverage_summary,
            "warnings": warnings,
            "limitations": ["数据仅覆盖各记录明确标注的观测窗口，不代表 GitHub 全部历史。", "精选集合是人工选择案例，不是 GitHub 全体的随机样本。"],
        }
        (stage / "dataset.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _write_checksums(stage)
        _atomic_replace_directory(stage, target, force)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    from backend.app.services.dataset_import import verify_dataset_bundle

    return verify_dataset_bundle(target)


def _repository_record(repo: Repository) -> dict:
    return {
        "repository_id": repo.repository_id,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "description": _redact_emails(repo.description),
        "language": repo.language,
        "topics": [_redact_emails(topic) for topic in json.loads(repo.topics_json or "[]") if isinstance(topic, str)],
        "license_spdx": repo.license_spdx,
        "created_at": iso_z(repo.created_at),
        "pushed_at": iso_z(repo.pushed_at),
        "github_updated_at": iso_z(repo.github_updated_at),
        "archived": repo.archived,
        "is_fork": repo.is_fork,
        "size_kb": repo.size_kb,
        "first_seen_at": iso_z(repo.first_seen_at),
        "last_seen_at": iso_z(repo.last_seen_at),
    }


def _snapshot_record(row: RepositorySnapshot) -> dict:
    return {
        "repository_id": row.repository_id,
        "collected_at": iso_z(row.collected_at),
        "stars": row.stars,
        "forks": row.forks,
        "open_issues_and_pr_count": row.open_issues_and_pr_count,
        "pushed_at": iso_z(row.pushed_at),
        "github_updated_at": iso_z(row.github_updated_at),
        "response_etag": row.response_etag,
        "source_http_status": row.source_http_status,
    }


def _analysis_record(row: AnalysisResult) -> dict:
    return {
        "repository_id": row.repository_id,
        "analysis_kind": row.analysis_kind,
        "metric_version": row.metric_version,
        "window_start": iso_z(row.window_start),
        "window_end": iso_z(row.window_end),
        "source_collected_at": iso_z(row.source_collected_at),
        "calculated_at": iso_z(row.calculated_at),
        "coverage": row.coverage,
        "metrics": json.loads(row.metrics_json),
        "limitations": json.loads(row.limitations_json or "[]"),
        "valid_sample_size": row.valid_sample_size,
    }


def _coverage_record(row: ActivityWindow) -> dict:
    details = json.loads(row.details_json or "{}")
    source_coverage = details.get("coverage_by_module", {})
    modules = {
        "commits": source_coverage.get("commits_count"),
        "issues": source_coverage.get("issues_closed_count"),
        "pulls": source_coverage.get("pulls_merged_count"),
        "releases": source_coverage.get("releases_count"),
    } if isinstance(source_coverage, dict) else {}
    return {
        "repository_id": row.repository_id,
        "window_start": iso_z(row.window_start),
        "window_end": iso_z(row.window_end),
        "collected_at": iso_z(row.collected_at),
        "commits_count": row.commits_count,
        "issues_opened_count": row.issues_opened_count,
        "issues_closed_count": row.issues_closed_count,
        "pulls_opened_count": row.pulls_opened_count,
        "pulls_merged_count": row.pulls_merged_count,
        "releases_count": row.releases_count,
        "coverage": row.coverage,
        "modules": modules,
    }


def _event_record(row: RepositoryActivityEvent) -> dict:
    return {
        "repository_id": row.repository_id,
        "event_type": row.event_type,
        "source_item_id": row.source_item_id,
        "event_at": iso_z(row.event_at),
        "created_at": iso_z(row.created_at),
        "closed_at": iso_z(row.closed_at),
        "merged_at": iso_z(row.merged_at),
        "published_at": iso_z(row.published_at),
        "updated_at": iso_z(row.updated_at),
        "author_key": row.author_key,
        "is_draft": row.is_draft,
        "is_prerelease": row.is_prerelease,
        "first_seen_at": iso_z(row.first_seen_at),
        "last_seen_at": iso_z(row.last_seen_at),
    }


def _insight_record(row: RepositoryInsightRun) -> dict:
    result = json.loads(row.result_json)
    result.pop("source_task_ids", None)
    result.pop("source_archive_paths", None)
    result.pop("origin", None)
    result.pop("run_id", None)
    return {
        "repository_id": row.repository_id,
        "metric_version": row.metric_version,
        "window_start": iso_z(row.window_start),
        "window_end": iso_z(row.window_end),
        "analyzed_at": iso_z(row.analyzed_at),
        "module_coverage": json.loads(row.module_coverage_json),
        "status": row.status,
        "limitations": json.loads(row.limitations_json),
        "sources": json.loads(row.module_coverage_json),
        "result": result,
    }


def _collect_details(repository_id: int, archive_paths_json: str, details: dict[str, list[dict]], warnings: list[str]) -> None:
    try:
        archive_paths = json.loads(archive_paths_json)
    except (TypeError, ValueError):
        warnings.append(f"repository {repository_id} insight archive reference is invalid")
        return
    if not isinstance(archive_paths, list):
        return
    for path in archive_paths:
        if not isinstance(path, str):
            continue
        try:
            archive = read_archive(path)
            for module in MODULES:
                for row in iter_module_records(archive.get(module)):
                    item = _sanitize_detail(module, row)
                    if item is not None:
                        details[module].append({"repository_id": repository_id, "item": item})
        except (OSError, ValueError, TypeError, KeyError):
            warnings.append(f"repository {repository_id} detail archive unavailable")


def _sanitize_detail(module: str, row: dict) -> dict | None:
    if module == "commits":
        sha = row.get("sha")
        commit = row.get("commit") if isinstance(row.get("commit"), dict) else {}
        message = commit.get("message") if isinstance(commit.get("message"), str) else ""
        title = _redact_emails(message.splitlines()[0][:500] if message else "（无提交说明）")
        author = row.get("author") if isinstance(row.get("author"), dict) else {}
        return {"sha": sha, "commit": {"message": title}, "author": {key: author[key] for key in ("login", "type") if isinstance(author.get(key), str)}} if isinstance(sha, str) else None
    if module in {"issues", "pulls"}:
        if module == "issues" and "pull_request" in row:
            return None
        item = {key: row.get(key) for key in ("id", "number", "title", "created_at", "closed_at", "merged_at", "updated_at", "comments", "draft") if row.get(key) is None or isinstance(row.get(key), (str, int, bool))}
        if type(item.get("id")) is not int or type(item.get("number")) is not int:
            return None
        if isinstance(item.get("title"), str):
            item["title"] = _redact_emails(item["title"][:1000])
        return item
    identifier = row.get("id")
    if type(identifier) is not int:
        return None
    body = row.get("body") if isinstance(row.get("body"), str) else ""
    return {"id": identifier, "name": _redact_emails(row.get("name")) if isinstance(row.get("name"), str) else None, "body": _redact_emails(body[:20_000])}


def _redact_emails(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[email removed]", value, flags=re.IGNORECASE)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            for record in records:
                compressed.write((json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def _write_checksums(root: Path) -> None:
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}" for path in sorted(root.rglob("*")) if path.is_file()]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")


def _atomic_replace_directory(stage: Path, target: Path, force: bool) -> None:
    backup = None
    if target.exists():
        contents = {path.name for path in target.iterdir()} if target.is_dir() else set()
        is_placeholder = contents == {"README.md", "DATA_NOTICE.md"} and "not available yet" in (target / "README.md").read_text(encoding="utf-8")
        if not force and is_placeholder:
            backup = target.with_name(f".{target.name}.placeholder-{os.getpid()}")
            target.rename(backup)
        elif not force:
            if contents:
                raise FileExistsError(f"{target} already exists; pass --force to replace it")
            target.rmdir()
        else:
            backup = target.with_name(f".{target.name}.backup-{os.getpid()}")
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
    try:
        stage.rename(target)
    except Exception:
        if backup and backup.exists() and not target.exists():
            backup.rename(target)
        raise
    if backup:
        shutil.rmtree(backup)


def _bundle_readme(version: str, data_as_of, warning_count: int) -> str:
    state = "partial" if warning_count else "collected"
    return f"# RepoVantage Featured Dataset {version}\n\nStatus: `{state}`. Data as of {iso_z(data_as_of)}.\n\nThis bundle contains only the explicit windows and module coverage recorded in `dataset.json` and `coverage.jsonl.gz`. It is a curated showcase, not a random sample of GitHub.\n"


def _data_notice(data_as_of) -> str:
    return f"# Data notice\n\nRepository metadata and public activity records were collected from GitHub REST API. Snapshot cutoff: {iso_z(data_as_of)}. Use this third-party data under the applicable GitHub and repository terms. This project does not claim that one license applies to every source record. Issue and Pull Request bodies, comments, commit email addresses, raw logs, credentials, and source-machine paths are excluded.\n"


def _write_schemas(root: Path) -> None:
    schemas = {
        "repository.schema.json": {"type": "object", "required": ["repository_id", "full_name", "html_url"], "properties": {"repository_id": {"type": "integer", "minimum": 1}, "full_name": {"type": "string"}, "html_url": {"type": "string"}}},
        "event.schema.json": {"type": "object", "required": ["repository_id", "event_type", "source_item_id"], "properties": {"repository_id": {"type": "integer"}, "event_type": {"enum": ["commit", "issue", "pull_request", "release"]}, "source_item_id": {"type": "string"}}},
        "coverage.schema.json": {"type": "object", "required": ["repository_id", "window_start", "window_end", "coverage", "modules"], "properties": {"repository_id": {"type": "integer"}, "coverage": {"enum": ["complete", "partial"]}, "modules": {"type": "object"}}},
    }
    for name, schema in schemas.items():
        (root / name).write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
