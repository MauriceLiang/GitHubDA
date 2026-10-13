from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env"), extra="ignore")

    internal_api_key: str | None = None
    github_token: str | None = None
    database_url: str = "sqlite:///./data/app.db"
    raw_data_dir: str = "./data/raw"
    worker_poll_seconds: float = Field(default=3, gt=0)
    base_refresh_hours: int = Field(default=24, gt=0)
    worker_heartbeat_seconds: int = Field(default=10, gt=0)
    worker_lease_seconds: int = Field(default=120, gt=0)
    github_timeout_seconds: float = Field(default=15, gt=0)
    github_max_pages: int = Field(default=10, ge=1, le=100)
    worker_stale_seconds: int = Field(default=45, gt=0)

    @property
    def raw_data_path(self) -> Path:
        path = Path(self.raw_data_dir).expanduser()
        return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def resolve_database_url(url: str) -> str:
    if not url.startswith("sqlite:///") or url == "sqlite:///:memory:":
        return url
    raw_path = url.removeprefix("sqlite:///")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
