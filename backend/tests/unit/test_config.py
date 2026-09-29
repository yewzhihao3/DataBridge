import pytest
from app.config import Settings


def test_development_public_origin_extends_only_development_allowlist():
    settings = Settings(app_env="development", frontend_url="http://localhost:5173", cors_origins=["http://127.0.0.1:5173"], dev_public_origins="https://demo.ngrok-free.dev")
    assert settings.trusted_origins == ["http://127.0.0.1:5173", "http://localhost:5173", "https://demo.ngrok-free.dev"]
    production = Settings(app_env="production", frontend_url="https://app.example.test", cors_origins=["https://app.example.test"], dev_public_origins="https://demo.ngrok-free.dev")
    assert "https://demo.ngrok-free.dev" not in production.trusted_origins


def test_development_public_origin_requires_a_plain_exact_origin():
    settings = Settings(app_env="development", dev_public_origins="https://demo.ngrok-free.dev/path")
    with pytest.raises(ValueError, match="exact origins"):
        _ = settings.trusted_origins
