from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend.app.core.config import get_settings


def test_0001_database_upgrades_to_task_progress_without_losing_tasks(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES ('0001_initial')")
        connection.exec_driver_sql(
            """CREATE TABLE collection_tasks (
                task_id VARCHAR(36) PRIMARY KEY,
                repository_id INTEGER NOT NULL,
                type VARCHAR(50) NOT NULL,
                depth VARCHAR(10) NOT NULL,
                status VARCHAR(20) NOT NULL,
                phase VARCHAR(20),
                progress_percent FLOAT,
                message TEXT,
                attempt INTEGER NOT NULL,
                retry_of VARCHAR(36),
                idempotency_key VARCHAR(200),
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                heartbeat_at DATETIME,
                finished_at DATETIME,
                error_code VARCHAR(100),
                error_message TEXT,
                lease_owner VARCHAR(100),
                lease_until DATETIME
            )"""
        )
        connection.execute(
            text("INSERT INTO collection_tasks (task_id, repository_id, type, depth, status, progress_percent, attempt, created_at) VALUES (:id, 123, 'collect_repository', 'deep', 'succeeded', 75, 1, '2026-10-13 10:00:00')"),
            {"id": "legacy-task"},
        )
    engine.dispose()

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    upgraded = create_engine(database_url)
    with upgraded.connect() as connection:
        row = connection.execute(
            text("SELECT task_id, status, progress_percent, progress_kind, progress_updated_at, current_module FROM collection_tasks")
        ).one()
        assert row == ("legacy-task", "succeeded", 75.0, "unknown", None, None)
        assert inspect(connection).has_table("task_module_progress")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0002_task_progress"
    upgraded.dispose()
