import os

os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.dependencies import get_github_client, get_session
from backend.app.main import app
from backend.app.persistence.db import Base
from backend.app.services.repositories import ensure_default_datasets


class FakeGitHub:
    def __init__(self, repository=None):
        self.repository = repository or {
            "id": 123,
            "full_name": "example/project",
            "html_url": "https://github.com/example/project",
            "description": "test fixture repository",
            "language": "Python",
            "topics": ["fixture"],
            "license": {"spdx_id": "MIT"},
            "created_at": "2020-01-01T00:00:00Z",
            "pushed_at": "2026-10-01T12:00:00Z",
            "updated_at": "2026-10-02T12:00:00Z",
            "archived": False,
            "fork": False,
            "private": False,
            "size": 100,
            "stargazers_count": 20,
            "forks_count": 3,
            "open_issues_count": 4,
        }

    def get_repository(self, _full_name, etag=None):
        return self.repository, 200, '"fixture-etag"'

    def get_repository_by_id(self, _repository_id, etag=None):
        return self.repository, 200, '"fixture-etag"'

    def search_repositories(self, *_args):
        return {"items": [self.repository], "total_count": 1, "incomplete_results": False}

    def close(self):
        pass


@pytest.fixture
def backend_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        ensure_default_datasets(session)
    fake_github = FakeGitHub()

    def get_test_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def get_test_github():
        yield fake_github

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_github_client] = get_test_github
    client = TestClient(app)
    yield client, factory, fake_github
    client.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
