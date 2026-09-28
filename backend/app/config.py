"""
app/config.py — Application configuration management.

Uses pydantic-settings to load and validate configuration from environment
variables and optional .env files.
"""

from pathlib import Path
from typing import Literal
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

    # Uploads
    upload_dir: Path = Path("uploads")
    max_file_size_mb: int = Field(10, ge=1, le=50)
    storage_backend: Literal["local"] = "local"

    # Database
    database_url: str = "sqlite:///./databridge.db"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",  # Default Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
