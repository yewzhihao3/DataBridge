"""
tests/integration/test_api_templates.py — Integration tests for template CRUD.
"""

from typing import Any
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.template import Template, TemplateFieldMapping


@pytest.fixture
def sample_template_payload() -> dict[str, Any]:
    return {
        "name": "Supplier A Invoice",
        "description": "Standard invoice layout for Supplier A",
        "file_type": "xlsx",
        "worksheet": "Overview",
        "header_row": 10,
        "data_start_row": 11,
        "date_format": "%Y-%m-%d",
        "field_mappings": [
            {
                "field_name": "company_name",
                "mapping_type": "cell",
                "cell_ref": "B2",
                "is_required": True,
                "data_type": "text",
            },
            {
                "field_name": "invoice_number",
                "mapping_type": "cell",
                "cell_ref": "$b$3",
                "is_required": True,
                "data_type": "text",
            },
            {
                "field_name": "total_amount",
                "mapping_type": "cell",
                "cell_ref": "D6",
                "is_required": False,
                "data_type": "decimal",
            },
        ],
    }


@pytest.mark.asyncio
async def test_create_template_success(
    client: AsyncClient, sample_template_payload: dict[str, Any]
) -> None:
    """Creating a template returns 201 Created and persists nested field mappings."""
    response = await client.post("/api/v1/templates", json=sample_template_payload)
    assert response.status_code == 201

    data = response.json()
    assert data["id"] > 0
    assert data["name"] == "Supplier A Invoice"
    assert len(data["field_mappings"]) == 3

    # Cell references should be normalized to A1
    mappings = {m["field_name"]: m for m in data["field_mappings"]}
    assert mappings["invoice_number"]["cell_ref"] == "B3"  # $b$3 normalized to B3


@pytest.mark.asyncio
async def test_create_duplicate_template_name_returns_409(
    client: AsyncClient, sample_template_payload: dict[str, Any]
) -> None:
    """Duplicate template name returns 409 Conflict."""
    res1 = await client.post("/api/v1/templates", json=sample_template_payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/templates", json=sample_template_payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_list_templates(
    client: AsyncClient, sample_template_payload: dict[str, Any]
) -> None:
    """List endpoint returns summaries with mapping_count."""
    await client.post("/api/v1/templates", json=sample_template_payload)

    second_payload = dict(sample_template_payload)
    second_payload["name"] = "Supplier B Invoice"
    second_payload["field_mappings"] = []
    await client.post("/api/v1/templates", json=second_payload)

    response = await client.get("/api/v1/templates")
    assert response.status_code == 200

    items = response.json()
    assert len(items) == 2
    template_map = {t["name"]: t for t in items}
    assert template_map["Supplier A Invoice"]["mapping_count"] == 3
    assert template_map["Supplier B Invoice"]["mapping_count"] == 0


@pytest.mark.asyncio
async def test_get_template_by_id(
    client: AsyncClient, sample_template_payload: dict[str, Any]
) -> None:
    """Fetch template by ID includes all child mappings."""
    created = await client.post("/api/v1/templates", json=sample_template_payload)
    template_id = created.json()["id"]

    response = await client.get(f"/api/v1/templates/{template_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == template_id
    assert len(data["field_mappings"]) == 3


@pytest.mark.asyncio
async def test_get_nonexistent_template_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/templates/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_template_and_replace_mappings(
    client: AsyncClient, sample_template_payload: dict[str, Any]
) -> None:
    """Updating a template modifies scalar fields and replaces mappings."""
    created = await client.post("/api/v1/templates", json=sample_template_payload)
    template_id = created.json()["id"]
    original_updated_at = created.json()["updated_at"]

    update_payload = {
        "description": "Updated description",
        "field_mappings": [
            {
                "field_name": "company_name",
                "mapping_type": "cell",
                "cell_ref": "A1",
                "is_required": True,
                "data_type": "text",
            }
        ],
    }

    response = await client.put(f"/api/v1/templates/{template_id}", json=update_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["description"] == "Updated description"
    assert len(data["field_mappings"]) == 1
    assert data["field_mappings"][0]["cell_ref"] == "A1"
    assert data["updated_at"] >= original_updated_at


@pytest.mark.asyncio
async def test_delete_template_and_verify_cascade_deletion(
    client: AsyncClient, sample_template_payload: dict[str, Any], db_session: Session
) -> None:
    """Deleting a template returns 204 and cascades to delete all child mappings in DB."""
    created = await client.post("/api/v1/templates", json=sample_template_payload)
    template_id = created.json()["id"]

    # Verify rows exist in database
    db_template = db_session.query(Template).filter(Template.id == template_id).first()
    assert db_template is not None
    mappings_count = (
        db_session.query(TemplateFieldMapping)
        .filter(TemplateFieldMapping.template_id == template_id)
        .count()
    )
    assert mappings_count == 3

    # Send DELETE request
    del_res = await client.delete(f"/api/v1/templates/{template_id}")
    assert del_res.status_code == 204

    # Verify template is deleted from DB
    db_session.expire_all()
    assert db_session.query(Template).filter(Template.id == template_id).first() is None

    # CRITICAL: Verify ON DELETE CASCADE wiped the child mappings
    remaining_mappings = (
        db_session.query(TemplateFieldMapping)
        .filter(TemplateFieldMapping.template_id == template_id)
        .count()
    )
    assert remaining_mappings == 0
