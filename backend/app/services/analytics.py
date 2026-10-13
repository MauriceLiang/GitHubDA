import csv
import io
import json
from datetime import timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.analytics.metrics import numeric_summary, spearman_summary
from backend.app.core.clock import iso_z, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.models import Dataset, DatasetRepository, Repository, SamplingRun
from backend.app.services.repositories import FEATURED_ID, LIBRARY_ID, RESEARCH_ID, analysis_status, latest_analysis, latest_snapshot


def _dataset(session: Session, dataset_id: str, expected_type: str = "research") -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None or dataset.type != expected_type:
        raise AppError(422, "VALIDATION_ERROR", "dataset_id 不存在或类型不符合要求", {"fields": [{"field": "dataset_id", "message": f"必须为 {expected_type} 类型数据集"}]})
    return dataset


def dataset_rows(session: Session, dataset_id: str, language: str | None = None) -> list[dict[str, Any]]:
    memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id).order_by(DatasetRepository.repository_id)).all()
    rows: list[dict[str, Any]] = []
    for membership in memberships:
        repo = session.get(Repository, membership.repository_id)
        if repo is None or (language and repo.language != language):
            continue
        snapshot = latest_snapshot(session, repo.repository_id)
        analysis = latest_analysis(session, repo.repository_id)
        metrics = json.loads(analysis.metrics_json) if analysis else {}
        rows.append({
            "repository": repo,
            "snapshot": snapshot,
            "analysis": analysis,
            "metrics": metrics,
            "stars": snapshot.stars if snapshot else None,
            "forks": snapshot.forks if snapshot else None,
            "pushed_at": snapshot.pushed_at if snapshot else repo.pushed_at,
            "collected_at": snapshot.collected_at if snapshot else None,
            "analyzable": snapshot is not None and (snapshot.stars is not None or snapshot.forks is not None),
        })
    return rows


def _recently_pushed(row: dict[str, Any]) -> bool | None:
    pushed_at = row["pushed_at"]
    collected_at = row["collected_at"]
    if pushed_at is None or collected_at is None:
        return None
    return collected_at - timedelta(days=90) <= pushed_at <= collected_at


def _source_metadata(rows: list[dict[str, Any]], dataset_id: str | None, total: int, note: str | None = None) -> dict[str, Any]:
    dates = [row["collected_at"] for row in rows if row["collected_at"]]
    analyzed = sum(row["analyzable"] for row in rows)
    coverage = "not_collected" if analyzed == 0 else ("complete" if analyzed == total else "partial")
    notes = [note] if note else []
    if analyzed < total:
        notes.append(f"{total - analyzed} 个成员尚无可用基础快照")
    return {
        "source": "GitHub REST API",
        "collected_at": iso_z(max(dates)) if dates else None,
        "window_start": None,
        "window_end": None,
        "sample_size": analyzed,
        "dataset_id": dataset_id,
        "coverage": coverage,
        "notes": notes,
    }


def get_datasets(session: Session) -> list[dict[str, Any]]:
    datasets = session.scalars(select(Dataset).order_by(Dataset.type, Dataset.dataset_id)).all()
    result = []
    for dataset in datasets:
        count = len(session.scalars(select(DatasetRepository.repository_id).where(DatasetRepository.dataset_id == dataset.dataset_id)).all())
        result.append({"dataset_id": dataset.dataset_id, "name": dataset.name, "type": dataset.type, "sample_size": count, "frozen_at": iso_z(dataset.frozen_at), "rules_version": dataset.rules_version})
    return result


def overview(session: Session, scope: str, dataset_id: str | None, language: str | None) -> dict[str, Any]:
    if scope == "research":
        if not dataset_id:
            raise AppError(422, "VALIDATION_ERROR", "scope=research 时必须提供 dataset_id", {"fields": [{"field": "dataset_id", "message": "此字段必填"}]})
        _dataset(session, dataset_id)
    else:
        if dataset_id:
            raise AppError(422, "VALIDATION_ERROR", "scope=library 时不能提供 dataset_id", {"fields": [{"field": "dataset_id", "message": "library 范围不接收此字段"}]})
        dataset_id = LIBRARY_ID
    all_rows = dataset_rows(session, dataset_id, language)
    total = len(all_rows)
    analyzable = [row for row in all_rows if row["analyzable"]]
    stars = [row["stars"] for row in analyzable if row["stars"] is not None]
    recent = sum(_recently_pushed(row) is True for row in analyzable)
    languages = pd.Series([row["repository"].language for row in all_rows if row["repository"].language]).value_counts(sort=True)
    star_values = [row["stars"] for row in analyzable if row["stars"] is not None]
    buckets = {
        "0-999": sum(0 <= value <= 999 for value in star_values),
        "1000-9999": sum(1000 <= value <= 9999 for value in star_values),
        "10000+": sum(value >= 10000 for value in star_values),
    }
    distribution = [{"bucket": key, "count": count} for key, count in buckets.items()]
    return {
        "scope": scope,
        "dataset_id": dataset_id if scope == "research" else None,
        "kpis": {
            "repositories_total": total,
            "repositories_analyzed": len(analyzable),
            "stars_median": float(pd.Series(stars).median()) if stars else None,
            "recently_pushed_90d_count": recent if analyzable else None,
        },
        "language_distribution": [{"language": str(key), "count": int(value)} for key, value in languages.items()],
        "stars_distribution": distribution,
        "source_metadata": _source_metadata(all_rows, dataset_id if scope == "research" else None, total),
    }


def research_statistics(session: Session, dataset_id: str, language: str | None, group_by: str) -> dict[str, Any]:
    _dataset(session, dataset_id)
    rows = dataset_rows(session, dataset_id, language)
    usable = [row for row in rows if row["analyzable"]]
    stars = [row["stars"] for row in usable if row["stars"] is not None]
    forks = [row["forks"] for row in usable if row["forks"] is not None]
    frame = pd.DataFrame([{
        "language": row["repository"].language or "Unknown",
        "stars": row["stars"],
        "forks": row["forks"],
        "age_days": row["metrics"].get("age_days"),
        "recent": _recently_pushed(row),
    } for row in usable])
    if not frame.empty:
        if group_by == "star_tier":
            frame["group"] = pd.cut(frame["stars"], bins=[-1, 999, 9999, float("inf")], labels=["0-999", "1000-9999", "10000+"]).astype("string")
        elif group_by == "age_tier":
            frame["group"] = pd.cut(frame["age_days"], bins=[-1, 365, 1825, float("inf")], labels=["0-1y", "1-5y", "5y+"]).astype("string")
        else:
            frame["group"] = frame["language"]
        grouped = frame.groupby("group", dropna=True, observed=True)
        groups = []
        for key, group in grouped:
            recent = group["recent"].dropna()
            groups.append({
                "group": str(key),
                "n": int(len(group)),
                "stars_median": float(group["stars"].median()) if group["stars"].notna().any() else None,
                "forks_median": float(group["forks"].median()) if group["forks"].notna().any() else None,
                "recently_pushed_90d_pct": round(float(recent.mean() * 100), 1) if len(recent) else None,
            })
    else:
        groups = []
    correlation = spearman_summary(
        [row["stars"] for row in usable],
        [row["forks"] for row in usable],
    )
    correlation.update(x="stars", y="forks")
    return {
        "dataset_id": dataset_id,
        "group_by": group_by,
        "valid_sample_size": len(usable),
        "summary": {"stars": numeric_summary(stars), "forks": numeric_summary(forks)},
        "groups": groups,
        "correlations": [correlation],
        "source_metadata": _source_metadata(rows, dataset_id, len(rows), "Spearman 相关仅描述关联，不代表因果"),
    }


def data_quality(session: Session, dataset_id: str) -> dict[str, Any]:
    dataset = _dataset(session, dataset_id)
    memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id)).all()
    rows = dataset_rows(session, dataset_id)
    total = len(memberships)
    analyzable = sum(row["analyzable"] and row["analysis"] is not None for row in rows)
    fields = {
        "language": lambda row: row["repository"].language,
        "stars": lambda row: row["stars"],
        "forks": lambda row: row["forks"],
        "pushed_at": lambda row: row["pushed_at"],
        "created_at": lambda row: row["repository"].created_at,
    }
    missing = []
    for name, get_value in fields.items():
        count = sum(get_value(row) is None for row in rows)
        missing.append({"field": name, "count": count, "rate": round(count / total, 5) if total else None})
    now = utc_now()
    stale = sum(row["collected_at"] is not None and now - row["collected_at"] > timedelta(hours=24) for row in rows)
    exclusion_counts: dict[str, int] = {}
    latest_run = session.scalar(select(SamplingRun).where(SamplingRun.dataset_id == dataset_id).order_by(SamplingRun.finished_at.desc()).limit(1))
    if latest_run:
        try:
            exclusions = json.loads(latest_run.rejection_counts_json)
            exclusion_counts.update({str(key): int(value) for key, value in exclusions.items() if int(value) > 0})
        except (TypeError, ValueError):
            exclusion_counts["sampling_metadata_invalid"] = 1
    for item in memberships:
        if item.exclusion_status:
            exclusion_counts[item.exclusion_status] = exclusion_counts.get(item.exclusion_status, 0) + 1
    notes = ["缺失率分母为当前数据集成员总数。", "研究样本只有导入带来源和筛选记录的清单后才具有研究证据。"]
    if dataset.source_metadata_json:
        try:
            source_metadata = json.loads(dataset.source_metadata_json)
            if source_metadata.get("incomplete_results"):
                notes.append("GitHub Search 候选结果不完整，样本仅代表已观察候选集合。")
        except ValueError:
            notes.append("采样来源元数据无法解析。")
    return {
        "dataset_id": dataset_id,
        "records_total": total,
        "records_analyzable": analyzable,
        "missing_fields": missing,
        "excluded_by_reason": [{"reason": key, "count": value} for key, value in sorted(exclusion_counts.items())],
        "stale_count": stale,
        "sampling_rules_version": dataset.rules_version,
        "coverage_notes": notes,
    }


def compare_repositories(session: Session, repository_ids: list[int], depth: str) -> dict[str, Any]:
    repositories = []
    collected_at = []
    languages = set()
    for repository_id in repository_ids:
        repo = session.get(Repository, repository_id)
        if repo is None:
            raise AppError(422, "VALIDATION_ERROR", "所有仓库必须已存在于本地", {"fields": [{"field": "repository_ids", "message": f"仓库 {repository_id} 不存在"}]})
        snapshot = latest_snapshot(session, repository_id)
        base = latest_analysis(session, repository_id, "basic")
        requested_analysis = latest_analysis(session, repository_id, depth)
        analysis = requested_analysis or base
        if snapshot is None or base is None:
            raise AppError(409, "CONFLICTING_OPERATION", "仓库缺少基础分析数据", {"repository_id": repository_id})
        metrics = json.loads(analysis.metrics_json) if analysis else {}
        repositories.append({
            "repository_id": repository_id,
            "full_name": repo.full_name,
            "metrics": {"stars": snapshot.stars, "forks": snapshot.forks, "days_since_push": metrics.get("days_since_push"), "commits_90d": metrics.get("commits_90d")},
            "coverage": analysis.coverage if requested_analysis else ("partial" if depth == "deep" else base.coverage),
        })
        collected_at.append(snapshot.collected_at)
        languages.add(repo.language)
    warnings = []
    if len(set(languages)) > 1:
        warnings.append("仓库主要语言不同，项目用途可能不同，不能直接判断谁更优秀")
    if collected_at and (max(collected_at) - min(collected_at)) > timedelta(hours=24):
        warnings.append("仓库采样时间相差超过 24 小时")
    return {
        "repositories": repositories,
        "comparison_basis": {"depth": depth, "metric_window": "latest_successful_snapshot", "same_project_type": False, "warnings": warnings + ["项目类型未经过分类验证；不能直接判断谁更优秀"]},
    }


def export_repositories(session: Session, scope: str, dataset_id: str | None, language: str | None) -> tuple[str, str]:
    if scope == "research":
        if not dataset_id:
            raise AppError(422, "VALIDATION_ERROR", "scope=research 时必须提供 dataset_id", {"fields": [{"field": "dataset_id", "message": "此字段必填"}]})
        _dataset(session, dataset_id)
    else:
        if dataset_id:
            raise AppError(422, "VALIDATION_ERROR", "scope=library 时不能提供 dataset_id", {"fields": [{"field": "dataset_id", "message": "library 范围不接收此字段"}]})
        dataset_id = LIBRARY_ID
    rows = dataset_rows(session, dataset_id, language)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = ["repository_id", "full_name", "description", "language", "stars", "forks", "created_at", "pushed_at", "collected_at", "analysis_status", "dataset_id"]
    writer.writerow(columns)
    for row in rows:
        repo, snapshot = row["repository"], row["snapshot"]
        values = [
            repo.repository_id,
            repo.full_name,
            repo.description,
            repo.language,
            snapshot.stars if snapshot else None,
            snapshot.forks if snapshot else None,
            iso_z(repo.created_at),
            iso_z(snapshot.pushed_at if snapshot else repo.pushed_at),
            iso_z(snapshot.collected_at if snapshot else None),
            analysis_status(session, repo.repository_id),
            dataset_id,
        ]
        writer.writerow([_csv_safe(value) for value in values])
    filename = f"repositories_{utc_now().date().isoformat()}.csv"
    return output.getvalue(), filename


def _csv_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
