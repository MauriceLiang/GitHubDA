import pytest

from frontend.api import factory
from frontend.api.client import APIClient
from frontend.api.errors import APIError
from frontend.api.mock_client import MockAPIClient
from frontend.state.keys import STATE_KEYS


def test_mock_clients_and_scenario_changes_are_isolated_per_session(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    first_session: dict[str, object] = {}
    monkeypatch.setattr(factory.st, "session_state", first_session)
    first_client, first_is_mock = factory.get_api_client()
    assert first_is_mock is True
    assert isinstance(first_client, MockAPIClient)
    added = first_client.add_repository("psf/requests").data

    second_session: dict[str, object] = {STATE_KEYS["mock_scenario"]: "normal"}
    monkeypatch.setattr(factory.st, "session_state", second_session)
    second_client, second_is_mock = factory.get_api_client()
    assert second_is_mock is True
    assert isinstance(second_client, MockAPIClient)
    assert second_client is not first_client
    first_ids = {item.repository_id for item in first_client.list_library().data.items}
    second_ids = {item.repository_id for item in second_client.list_library().data.items}
    assert added.repository_id in first_ids
    assert added.repository_id not in second_ids

    second_session[STATE_KEYS["mock_scenario"]] = "github_limited"
    same_second_client, _ = factory.get_api_client()
    assert same_second_client is second_client
    with pytest.raises(APIError) as raised:
        second_client.search_repositories("python")
    assert raised.value.code == "GITHUB_RATE_LIMITED"
    assert first_client.search_repositories("python").data.items

    first_client.close()
    second_client.close()


def test_real_mode_does_not_construct_mock_client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    real_client = APIClient(base_url="http://backend.test", internal_api_key="test-key")
    monkeypatch.setattr(factory, "_get_real_api_client", lambda: real_client)

    selected, mock_mode = factory.get_api_client()

    assert selected is real_client
    assert not isinstance(selected, MockAPIClient)
    assert mock_mode is False
    real_client.close()
