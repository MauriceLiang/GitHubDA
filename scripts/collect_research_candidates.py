"""Collect stratified public repository candidates from GitHub Search."""

import argparse
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.exceptions import AppError
from backend.app.integrations.github.client import GitHubClient

_GitHubClient = GitHubClient

LANGUAGES = ("Python", "TypeScript", "Java", "Go", "Rust")
STAR_TIERS = {"0-999": "0..999", "1000-9999": "1000..9999", "10000+": ">=10000"}
SEARCH_ORDERS = (("updated", "desc"), ("stars", "desc"), ("stars", "asc"))
SEED = 20261022


def collect(output: Path, per_bucket: int = 20) -> dict:
    if not 20 <= per_bucket <= 100:
        raise ValueError("per_bucket must be between 20 and 100")
    candidates: dict[int, dict] = {}
    queries = []
    incomplete_results = False
    with GitHubClient() as github:
        for language in LANGUAGES:
            for tier, stars in STAR_TIERS.items():
                query = f"is:public fork:false archived:false language:{language} stars:{stars}"
                for sort, order in SEARCH_ORDERS:
                    response = _search_with_quota(github, query, sort, order, per_bucket)
                    incomplete_results |= response["incomplete_results"]
                    queries.append({"query": query, "sort": sort, "order": order, "page": 1, "per_page": per_bucket, "total_count": response["total_count"], "incomplete_results": response["incomplete_results"], "language": language, "star_tier": tier})
                    selection_source = f"{query}; sort={sort}:{order}"
                    for repository in response["items"]:
                        repository_id = repository.get("id")
                        if type(repository_id) is not int or repository_id <= 0:
                            continue
                        candidates.setdefault(repository_id, {
                            "repository": repository,
                            "reviewed_eligible": False,
                            "inclusion_reason": "",
                            "selection_source": selection_source,
                        })

    bucket_counts = {language: {tier: 0 for tier in STAR_TIERS} for language in LANGUAGES}
    for candidate in candidates.values():
        repository = candidate["repository"]
        language = repository.get("language")
        stars = repository.get("stargazers_count")
        if language in bucket_counts and type(stars) is int and stars >= 0:
            tier = next((name for name, (lower, upper) in _tier_ranges().items() if stars >= lower and (upper is None or stars <= upper)), None)
            if tier:
                bucket_counts[language][tier] += 1
    shortfalls = {
        language: {tier: per_bucket - count for tier, count in tiers.items() if count < per_bucket}
        for language, tiers in bucket_counts.items()
    }
    shortfalls = {language: tiers for language, tiers in shortfalls.items() if tiers}

    manifest = {
        "metadata": {
            "source": "GitHub REST API",
            "sampled_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "queries": queries,
            "candidate_count": len(candidates),
            "incomplete_results": incomplete_results,
            "random_seed": SEED,
            "rules_version": "stratified-v1",
            "quotas": {language: {tier: 2 for tier in STAR_TIERS} for language in LANGUAGES},
            "candidate_bucket_counts": bucket_counts,
            "candidate_shortfalls": shortfalls,
            "review_status": "pending_human_review",
        },
        "candidates": list(candidates.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return manifest["metadata"]


def _search_with_quota(github, query: str, sort: str, order: str, per_page: int) -> dict:
    for attempt in range(3):
        if isinstance(github, _GitHubClient):
            snapshot = _GitHubClient.rate_limit_snapshot()
            remaining = snapshot.get("remaining")
            reset_at = snapshot.get("reset_at")
            if remaining is not None and remaining <= 1 and reset_at:
                reset = datetime.fromisoformat(reset_at.replace("Z", "+00:00")).timestamp()
                time.sleep(max(0.0, reset - time.time()) + 1.0)
        try:
            return github.search_repositories(query, None, None, sort, order, 1, per_page)
        except AppError as exc:
            if exc.code != "GITHUB_RATE_LIMITED" or attempt == 2:
                raise
            retry_after = exc.details.get("retry_after_seconds")
            time.sleep(max(1, retry_after if isinstance(retry_after, int) else 60) + 1)
    raise RuntimeError("GitHub Search retry limit exceeded")


def _tier_ranges() -> dict[str, tuple[int, int | None]]:
    return {"0-999": (0, 999), "1000-9999": (1000, 9999), "10000+": (10000, None)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/manifests/research-candidates.json"))
    parser.add_argument("--per-bucket", type=int, default=20, help="results per language/star query and sort order (20–100)")
    args = parser.parse_args()
    print(json.dumps(collect(args.output, args.per_bucket), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
