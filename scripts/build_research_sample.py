"""Build a frozen research dataset from a manifest of GitHub REST API candidates."""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from backend.app.core.clock import parse_github_datetime, utc_now
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import SessionLocal
from backend.app.persistence.models import Dataset, DatasetRepository, SamplingRun
from backend.app.services.repositories import repository_from_github


STAR_TIERS = {"0-999": (0, 999), "1000-9999": (1000, 9999), "10000+": (10000, None)}


def build(manifest_path: Path, dataset_id: str) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = manifest.get("metadata") or {}
    candidates = manifest.get("candidates")
    required = ("source", "sampled_at", "queries", "candidate_count", "incomplete_results", "random_seed", "rules_version", "quotas")
    missing = [key for key in required if key not in metadata]
    if missing or metadata.get("source") != "GitHub REST API" or not isinstance(candidates, list):
        raise ValueError(f"Manifest must include GitHub source metadata and candidates; missing: {missing}")
    if metadata["candidate_count"] != len(candidates):
        raise ValueError("metadata.candidate_count must match the candidates array")
    if not isinstance(metadata["incomplete_results"], bool) or not isinstance(metadata["random_seed"], int):
        raise ValueError("incomplete_results and random_seed must have correct types")
    if not isinstance(metadata["quotas"], dict) or not metadata["quotas"]:
        raise ValueError("metadata.quotas must define language and star tier quotas")
    sampled_at = parse_github_datetime(metadata["sampled_at"])
    if sampled_at is None:
        raise ValueError("metadata.sampled_at must be an ISO-8601 timestamp")

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    rejection_counts: Counter[str] = Counter()
    seen_ids = set()
    candidate_decisions: list[dict] = []
    for candidate_index, entry in enumerate(candidates):
        repo = entry.get("repository") if isinstance(entry, dict) else None
        decision = {"candidate_index": candidate_index, "outcome": "excluded"}
        if isinstance(repo, dict):
            for source_key, decision_key in (
                ("id", "repository_id"),
                ("full_name", "full_name"),
                ("language", "language"),
                ("stargazers_count", "stars"),
            ):
                value = repo.get(source_key)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    decision[decision_key] = value
        if not isinstance(repo, dict):
            rejection_counts["invalid_repository_payload"] += 1
            decision["reason"] = "invalid_repository_payload"
            candidate_decisions.append(decision)
            continue
        repo_id = repo.get("id")
        if not isinstance(repo_id, int) or isinstance(repo_id, bool) or repo_id <= 0 or repo_id in seen_ids:
            rejection_counts["invalid_or_duplicate_id"] += 1
            decision["reason"] = "invalid_or_duplicate_id"
            candidate_decisions.append(decision)
            continue
        seen_ids.add(repo_id)
        if repo.get("private") is not False or repo.get("fork") is not False or repo.get("archived") is not False:
            rejection_counts["private_fork_or_archived"] += 1
            decision["reason"] = "private_fork_or_archived"
            candidate_decisions.append(decision)
            continue
        if entry.get("reviewed_eligible") is not True or not entry.get("inclusion_reason"):
            rejection_counts["not_reviewed_eligible"] += 1
            decision["reason"] = "not_reviewed_eligible"
            candidate_decisions.append(decision)
            continue
        language = repo.get("language")
        stars = repo.get("stargazers_count")
        if language not in metadata["quotas"] or not isinstance(stars, int) or isinstance(stars, bool) or stars < 0:
            rejection_counts["outside_language_or_missing_stars"] += 1
            decision["reason"] = "outside_language_or_missing_stars"
            candidate_decisions.append(decision)
            continue
        tier = next((name for name, (lower, upper) in STAR_TIERS.items() if stars >= lower and (upper is None or stars <= upper)), None)
        if tier not in metadata["quotas"][language]:
            rejection_counts["outside_quota_tiers"] += 1
            decision["reason"] = "outside_quota_tiers"
            candidate_decisions.append(decision)
            continue
        decision.update({"outcome": "eligible", "reason": "reviewed_candidate_matches_quota", "inclusion_reason": entry["inclusion_reason"], "selection_tier": f"{language}:{tier}"})
        candidate_decisions.append(decision)
        buckets[(language, tier)].append({**entry, "repository": repo, "_candidate_index": candidate_index})

    rng = random.Random(metadata["random_seed"])
    selected: list[tuple[dict, str, str]] = []
    for language, tier_quotas in sorted(metadata["quotas"].items()):
        if not isinstance(tier_quotas, dict):
            raise ValueError(f"Quota for {language} must be an object")
        for tier, quota in sorted(tier_quotas.items()):
            if tier not in STAR_TIERS or not isinstance(quota, int) or isinstance(quota, bool) or quota < 0:
                raise ValueError(f"Invalid quota {language}/{tier}")
            options = sorted(buckets[(language, tier)], key=lambda item: item["repository"]["id"])
            chosen = rng.sample(options, min(quota, len(options)))
            for entry in chosen:
                candidate_decisions[entry["_candidate_index"]].update({"outcome": "included", "reason": "selected_by_seeded_stratified_quota"})
                selected.append((entry, tier, language))
            if len(chosen) < quota:
                rejection_counts[f"quota_unfilled:{language}:{tier}"] += quota - len(chosen)

    for decision in candidate_decisions:
        if decision["outcome"] == "eligible":
            decision.update({"outcome": "excluded", "reason": "quota_not_selected"})

    if not selected:
        raise ValueError("No reviewed, public candidates matched the requested quotas; dataset was not frozen")
    if metadata["incomplete_results"]:
        metadata["sampling_note"] = "GitHub Search reported incomplete_results=true; this is a stratified quota sample, not a probability sample of all GitHub repositories."

    session = SessionLocal()
    try:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            dataset = Dataset(dataset_id=dataset_id, name=metadata.get("name", dataset_id), type="research", rules_version=metadata["rules_version"], description="由真实 GitHub Search 候选 manifest 按分层配额和固定种子构建")
            session.add(dataset)
            session.flush()
        elif dataset.type != "research":
            raise ValueError("Target dataset_id is already used by a non-research dataset")
        if session.scalar(select(DatasetRepository.repository_id).where(DatasetRepository.dataset_id == dataset_id).limit(1)):
            raise ValueError("Target dataset already has members; create a new dataset_id to preserve frozen versions")
        if dataset.frozen_at is not None:
            raise ValueError("Target dataset is already frozen")
        dataset.name = metadata.get("name", dataset.name)
        dataset.rules_version = metadata["rules_version"]
        frozen_at = utc_now()
        dataset.frozen_at = frozen_at
        dataset.source_metadata_json = json.dumps({key: value for key, value in metadata.items() if key != "quotas"} | {"candidate_count": len(candidates), "accepted_count": len(selected), "quotas": metadata["quotas"]}, ensure_ascii=False)
        for entry, tier, language in selected:
            repo = repository_from_github(session, entry["repository"])
            session.flush()
            session.add(DatasetRepository(
                dataset_id=dataset_id,
                repository_id=repo.repository_id,
                added_at=frozen_at,
                selection_tier=f"{language}:{tier}",
                inclusion_reason=entry["inclusion_reason"],
                selection_source=entry.get("selection_source") or json.dumps(metadata["queries"], ensure_ascii=False),
            ))
        session.add(SamplingRun(
            run_id=str(uuid4()),
            dataset_id=dataset_id,
            rules_json=json.dumps({"rules_version": metadata["rules_version"], "quotas": metadata["quotas"]}, ensure_ascii=False),
            query_json=json.dumps(metadata["queries"], ensure_ascii=False),
            random_seed=metadata["random_seed"],
            candidate_count=len(candidates),
            accepted_count=len(selected),
            rejection_counts_json=json.dumps(rejection_counts, ensure_ascii=False),
            candidate_decisions_json=json.dumps(candidate_decisions, ensure_ascii=False),
            started_at=utc_now(),
            finished_at=utc_now(),
        ))
        session.commit()
        return {"dataset_id": dataset_id, "candidate_count": len(candidates), "accepted_count": len(selected), "rejection_counts": dict(rejection_counts), "frozen_at": frozen_at.isoformat() + "Z"}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest exported from official GitHub REST Search and reviewed by a person")
    parser.add_argument("--dataset-id", default="research-2026-v1")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.manifest, args.dataset_id), ensure_ascii=False, indent=2))
    except (OSError, ValueError, AppError) as exc:
        print(f"sample import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
