"""
app/config.py — Application configuration management.

Uses pydantic-settings to load and validate configuration from environment
variables and optional .env files.
"""

from pathlib import Path
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

    # Uploads
    upload_dir: Path = Path("uploads")
    max_file_size_mb: int = 10

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
