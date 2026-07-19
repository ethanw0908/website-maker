from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LocalSite Agent"
    app_env: str = "development"
    admin_api_key: str | None = None
    app_secret_key: str = "change-me-with-openssl-rand-hex-32"
    database_url: str = "sqlite:///./localsite.db"
    redis_url: str = "redis://localhost:6379/0"

    google_places_api_key: str | None = None
    github_token: str | None = None
    vercel_token: str | None = None

    max_businesses_per_day: int = Field(default=20, ge=1, le=500)
    qualification_threshold: int = Field(default=35, ge=-100, le=100)
    max_codex_revisions: int = Field(default=2, ge=0, le=5)
    allow_repository_creation: bool = False
    allow_vercel_deployment: bool = False
    control_centre_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    workspace_root: Path = Path("workspaces")
    codex_home: Path = Path.home() / ".codex"

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.control_centre_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    return settings
