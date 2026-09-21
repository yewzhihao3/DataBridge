"""
tests/integration/test_health.py — Integration tests for app health check.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_200_and_metadata(client: AsyncClient) -> None:
    """Verify that the /health endpoint is operational and returns expected keys."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "DataBridge API"
    assert "version" in data
    assert "environment" in data
