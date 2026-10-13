import json

from sqlalchemy import func, select

from backend.app.persistence.models import Dataset, DatasetRepository, SamplingRun
from backend.app.services.repositories import RESEARCH_ID
from scripts import build_research_sample


def test_sample_import_is_seeded_frozen_and_separate_from_library(backend_client, tmp_path, monkeypatch):
    client, factory, _github = backend_client
    monkeypatch.setattr(build_research_sample, "SessionLocal", factory)
    manifest = {
        "metadata": {
            "source": "GitHub REST API",
            "sampled_at": "2026-10-13T00:00:00Z",
            "queries": {"Python": "language:Python"},
            "candidate_count": 4,
            "incomplete_results": False,
            "random_seed": 13,
            "rules_version": "selection-v1",
            "quotas": {"Python": {"0-999": 1, "1000-9999": 1}},
        },
        "candidates": [
            {"repository": {"id": 501, "full_name": "research/low", "html_url": "https://github.com/research/low", "language": "Python", "stargazers_count": 50, "forks_count": 5, "fork": False, "archived": False, "private": False}, "reviewed_eligible": True, "inclusion_reason": "reviewed public software"},
            {"repository": {"id": 502, "full_name": "research/mid", "html_url": "https://github.com/research/mid", "language": "Python", "stargazers_count": 1500, "forks_count": 15, "fork": False, "archived": False, "private": False}, "reviewed_eligible": True, "inclusion_reason": "reviewed public software"},
            {"repository": {"id": 503, "full_name": "research/fork", "language": "Python", "stargazers_count": 100, "forks_count": 1, "fork": True, "archived": False, "private": False}, "reviewed_eligible": True, "inclusion_reason": "excluded fork"},
            {"repository": {"id": 504, "full_name": "research/low-alt", "html_url": "https://github.com/research/low-alt", "language": "Python", "stargazers_count": 700, "forks_count": 2, "fork": False, "archived": False, "private": False}, "reviewed_eligible": True, "inclusion_reason": "reviewed public software"},
        ],
    }
    manifest_path = tmp_path / "candidates.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = build_research_sample.build(manifest_path, RESEARCH_ID)
    assert result["accepted_count"] == 2
    assert result["rejection_counts"]["private_fork_or_archived"] == 1

    with factory() as session:
        dataset = session.get(Dataset, RESEARCH_ID)
        before = session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == RESEARCH_ID))
        run = session.scalar(select(SamplingRun).where(SamplingRun.dataset_id == RESEARCH_ID))
    assert dataset.frozen_at is not None
    assert before == 2 and run is not None
    decisions = json.loads(run.candidate_decisions_json)
    assert sum(item["outcome"] == "included" for item in decisions) == 2
    assert sum(item["reason"] == "quota_not_selected" for item in decisions) == 1
    assert decisions[2]["reason"] == "private_fork_or_archived"
    assert decisions[0]["selection_tier"] == "Python:0-999"

    response = client.post("/api/v1/library/repositories", json={"full_name": "example/project", "auto_analyze": False}, headers={"X-Internal-Api-Key": "test-internal-key"})
    assert response.status_code == 201
    with factory() as session:
        after = session.scalar(select(func.count()).select_from(DatasetRepository).where(DatasetRepository.dataset_id == RESEARCH_ID))
    assert after == before
