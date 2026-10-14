import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from frontend.api.models import (
    APIEnvelope,
    DataQualityData,
    DatasetListData,
    OverviewData,
    RefreshTaskData,
    Task,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_datasets_accept_featured_and_research_filter_stays_specific():
    result = TypeAdapter(APIEnvelope[DatasetListData]).validate_python(load_fixture("default_datasets.json"))

    assert {item.type for item in result.data.items} == {"library", "research", "featured"}
    assert [item.dataset_id for item in result.data.items if item.type == "research"] == ["research-2026-v1"]


def test_empty_overview_and_quality_preserve_nulls():
    overview = TypeAdapter(APIEnvelope[OverviewData]).validate_python(load_fixture("empty_overview.json")).data
    quality = TypeAdapter(APIEnvelope[DataQualityData]).validate_python(load_fixture("empty_data_quality.json")).data

    assert overview.source_metadata.collected_at is None
    assert overview.kpis.stars_median is None
    assert overview.source_metadata.sample_size == 0
    assert all(field.rate is None for field in quality.missing_fields)
    assert quality.sampling_rules_version is None


def test_queued_attempt_zero_and_cached_refresh_terminal_status_are_accepted():
    task = TypeAdapter(APIEnvelope[Task]).validate_python(load_fixture("queued_attempt_zero.json")).data
    refresh = TypeAdapter(APIEnvelope[RefreshTaskData]).validate_python(
        load_fixture("refresh_reused_succeeded.json")
    ).data

    assert task.attempt == 0
    assert task.progress_kind == "unknown"
    assert task.modules == []
    assert task.eta_seconds is None
    assert refresh.reused is True
    assert refresh.status == "succeeded"


def test_contract_still_rejects_missing_fields_and_unknown_values():
    datasets = load_fixture("default_datasets.json")
    del datasets["data"]["items"][0]["name"]
    with pytest.raises(ValidationError):
        TypeAdapter(APIEnvelope[DatasetListData]).validate_python(datasets)

    datasets = load_fixture("default_datasets.json")
    datasets["data"]["items"][0]["type"] = "experimental"
    with pytest.raises(ValidationError):
        TypeAdapter(APIEnvelope[DatasetListData]).validate_python(datasets)

    task = load_fixture("queued_attempt_zero.json")
    task["data"]["attempt"] = -1
    with pytest.raises(ValidationError):
        TypeAdapter(APIEnvelope[Task]).validate_python(task)

    refresh = load_fixture("refresh_reused_succeeded.json")
    refresh["data"]["status"] = "cached"
    with pytest.raises(ValidationError):
        TypeAdapter(APIEnvelope[RefreshTaskData]).validate_python(refresh)


def test_v2_task_progress_fields_are_validated_and_preserved():
    task = TypeAdapter(APIEnvelope[Task]).validate_python(load_fixture("task_progress.json")).data

    assert task.progress_kind == "stages"
    assert task.current_module == "pulls"
    assert task.progress_percent == 38
    assert task.eta_seconds is None
    assert [(module.name, module.status) for module in task.modules] == [
        ("profile", "complete"),
        ("commits", "complete"),
        ("issues", "complete"),
        ("pulls", "running"),
        ("releases", "pending"),
    ]

    invalid = load_fixture("task_progress.json")
    invalid["data"]["modules"][0]["pages_fetched"] = -1
    with pytest.raises(ValidationError):
        TypeAdapter(APIEnvelope[Task]).validate_python(invalid)
