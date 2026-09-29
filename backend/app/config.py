"""
app/config.py — Application configuration management.

Uses pydantic-settings to load and validate configuration from environment
variables and optional .env files.
"""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with default fallbacks.
    """

    app_name: str = "DataBridge API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    cookie_secure: bool = False
    session_hours: int = Field(24, ge=1, le=168)
    frontend_url: str = "http://localhost:5173"
    # Comma-separated HTTPS origins that are trusted only while developing
    # through a temporary public tunnel. Never use this in production.
    dev_public_origins: str = ""

    # Uploads
    upload_dir: Path = Path("uploads")
    max_file_size_mb: int = Field(10, ge=1, le=50)
    max_batch_file_count: int = Field(25, ge=2, le=50)
    batch_analysis_concurrency: int = Field(4, ge=1, le=8)
    storage_backend: Literal["local"] = "local"

    # Database
    database_url: str = "sqlite:///./databridge.db"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",  # Default Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @property
    def trusted_origins(self) -> list[str]:
        """Exact origins accepted by CORS and the state-changing request guard."""
        origins = [*self.cors_origins, self.frontend_url]
        if self.app_env == "development":
            for value in self.dev_public_origins.split(","):
                origin = value.strip().rstrip("/")
                if not origin:
                    continue
                parsed = urlsplit(origin)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                    raise ValueError("DEV_PUBLIC_ORIGINS entries must be exact origins, for example https://example.ngrok-free.dev")
                origins.append(origin)
        return list(dict.fromkeys(origins))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
