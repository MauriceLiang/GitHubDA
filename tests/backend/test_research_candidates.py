import json

import pytest

from backend.app.core.exceptions import AppError
from scripts import collect_research_candidates


class FakeSearchClient:
    def __init__(self):
        self.calls = []
        self.ids_by_query = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def search_repositories(self, query, _language, _stars_min, sort, order, page, per_page):
        self.calls.append((query, sort, order, page, per_page))
        repository_id = self.ids_by_query.setdefault(query, len(self.ids_by_query) + 1)
        language = query.split("language:", 1)[1].split()[0]
        stars_query = query.split("stars:", 1)[1]
        stars = 10 if stars_query == "0..999" else 1_000 if stars_query == "1000..9999" else 10_000
        return {
            "items": [{
                "id": repository_id,
                "full_name": f"owner/project-{repository_id}",
                "html_url": f"https://github.com/owner/project-{repository_id}",
                "language": language,
                "stargazers_count": stars,
                "forks_count": 0,
                "fork": False,
                "archived": False,
                "private": False,
            }],
            "total_count": 1,
            "incomplete_results": len(self.calls) == 1,
        }


def test_candidate_collection_combines_sort_orders_and_deduplicates(tmp_path, monkeypatch):
    fake = FakeSearchClient()
    monkeypatch.setattr(collect_research_candidates, "GitHubClient", lambda: fake)
    output = tmp_path / "candidates.json"

    metadata = collect_research_candidates.collect(output)
    manifest = json.loads(output.read_text(encoding="utf-8"))

    assert len(fake.calls) == 45
    assert {call[1:3] for call in fake.calls} == {("updated", "desc"), ("stars", "desc"), ("stars", "asc")}
    assert all(call[3:] == (1, 20) for call in fake.calls)
    assert metadata["candidate_count"] == len(manifest["candidates"]) == 15
    assert sum(len(tiers) for tiers in metadata["candidate_shortfalls"].values()) == 15
    assert metadata["incomplete_results"] is True
    assert manifest["metadata"]["review_status"] == "pending_human_review"
    assert all(candidate["reviewed_eligible"] is False for candidate in manifest["candidates"])


def test_candidate_collection_rejects_bucket_sizes_below_documented_minimum(tmp_path):
    with pytest.raises(ValueError, match="between 20 and 100"):
        collect_research_candidates.collect(tmp_path / "candidates.json", per_bucket=19)


def test_search_waits_for_quota_reset_and_retries_rate_limit(monkeypatch):
    sleeps = []
    snapshots = iter([
        {"remaining": 1, "reset_at": "2026-10-22T07:38:00Z"},
        {"remaining": 10, "reset_at": "2026-10-22T07:39:00Z"},
    ])

    class RateLimitedSearchClient:
        calls = 0

        @staticmethod
        def rate_limit_snapshot():
            return next(snapshots)

        def search_repositories(self, *_args):
            self.calls += 1
            if self.calls == 1:
                raise AppError(429, "GITHUB_RATE_LIMITED", "limited", {"retry_after_seconds": 2})
            return {"items": [], "total_count": 0, "incomplete_results": False}

    monkeypatch.setattr(collect_research_candidates, "_GitHubClient", RateLimitedSearchClient)
    monkeypatch.setattr(collect_research_candidates.time, "time", lambda: 1792654670.0)
    monkeypatch.setattr(collect_research_candidates.time, "sleep", sleeps.append)

    client = RateLimitedSearchClient()
    result = collect_research_candidates._search_with_quota(client, "query", "stars", "desc", 20)

    assert result["items"] == []
    assert client.calls == 2
    assert sleeps == [11.0, 3]
