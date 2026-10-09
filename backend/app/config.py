"""
app/config.py — Application configuration management.

Uses pydantic-settings to load and validate configuration from environment
variables and optional .env files.
"""

from pathlib import Path
from typing import Literal
import logging
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
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    cookie_secure: bool = False
    session_hours: int = Field(24, ge=1, le=168)
    frontend_url: str = "http://localhost:5173"
    # Comma-separated HTTPS origins that are trusted only while developing
    # through a temporary public tunnel. Never use this in production.
    dev_public_origins: str = ""

    # Uploads
    upload_dir: Path = Path("uploads")
    max_file_size_mb: int = Field(10, ge=1, le=50)
    max_document_image_size_mb: int = Field(10, ge=1, le=50)
    max_document_pdf_size_mb: int = Field(20, ge=1, le=50)
    max_document_pages: int = Field(25, ge=1, le=100)
    max_batch_file_count: int = Field(25, ge=2, le=50)
    batch_analysis_concurrency: int = Field(4, ge=1, le=8)
    storage_backend: Literal["local"] = "local"

    # AI Receipt Intelligence (Milestone 15)
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    ai_receipt_mode: Literal["auto", "vision_only", "local_ocr"] = "local_ocr"
    ai_vision_timeout_seconds: int = Field(30, ge=5, le=120)
    ai_vision_max_retries: int = Field(1, ge=0, le=5)

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

    def validate_production_security(self) -> None:
        """Fail closed when a staging/production environment is misconfigured."""
        if self.app_env != "production":
            return
        if self.dev_public_origins.strip() or not self.cookie_secure:
            raise ValueError("Production requires secure cookies and no DEV_PUBLIC_ORIGINS")
        origins = self.trusted_origins
        if not self.frontend_url.startswith("https://") or not origins:
            raise ValueError("Production requires explicit HTTPS frontend origins")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or "*" in origin:
                raise ValueError("Production CORS origins must be explicit HTTPS origins")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
logging.basicConfig(level=getattr(logging, settings.log_level), format="%(asctime)s %(levelname)s %(name)s %(message)s")
