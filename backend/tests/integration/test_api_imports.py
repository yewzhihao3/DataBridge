"""
tests/integration/test_api_imports.py — Integration tests for data extraction preview API.
"""

from pathlib import Path
from typing import Any
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.source_file import SourceFile
from app.models.template import Template


@pytest.fixture
def sample_template_payload() -> dict[str, Any]:
    return {
        "name": "Invoice Test Template",
        "file_type": "xlsx",
        "worksheet": "Invoice",
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
                "cell_ref": "B3",
                "is_required": True,
                "data_type": "text",
            },
            {
                "field_name": "invoice_date",
                "mapping_type": "cell",
                "cell_ref": "F3",
                "is_required": True,
                "data_type": "date",
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
async def test_extract_preview_success_with_validation_report(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    sample_template_payload: dict[str, Any],
    db_session: Session,
) -> None:
    """POST /api/v1/imports/extract returns complete extraction preview with validation report."""
    # 1. Upload file
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    # 2. Create template
    template_res = await client.post("/api/v1/templates", json=sample_template_payload)
    template_id = template_res.json()["id"]

    # Snapshot database counts before validation
    source_files_count_before = db_session.query(SourceFile).count()
    templates_count_before = db_session.query(Template).count()

    # 3. Request extraction preview
    extract_res = await client.post(
        "/api/v1/imports/extract",
        json={"file_id": file_id, "template_id": template_id},
    )
    assert extract_res.status_code == 200

    data = extract_res.json()
    assert data["file_id"] == file_id
    assert data["template_id"] == template_id
    assert data["template_name"] == "Invoice Test Template"
    assert data["target_worksheet"] == "Invoice"
    assert data["has_errors"] is False
    assert len(data["fields"]) == 4

    # Validation Report assertions
    val_report = data["validation_report"]
    assert val_report["is_valid_for_import"] is True
    assert val_report["error_count"] == 0
    assert val_report["normalized_data"]["company_name"] == "Acme Supplies Ltd"
    assert val_report["normalized_data"]["invoice_number"] == "INV-2026-001"

    # Verify Database was NOT mutated by validation
    db_session.expire_all()
    assert db_session.query(SourceFile).count() == source_files_count_before
    assert db_session.query(Template).count() == templates_count_before


@pytest.mark.asyncio
async def test_extract_missing_file_id_returns_404(
    client: AsyncClient, sample_template_payload: dict[str, Any]
) -> None:
    template_res = await client.post("/api/v1/templates", json=sample_template_payload)
    template_id = template_res.json()["id"]

    res = await client.post(
        "/api/v1/imports/extract",
        json={"file_id": 99999, "template_id": template_id},
    )
    assert res.status_code == 404
    assert "Source file with ID 99999 was not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_extract_missing_template_id_returns_404(
    client: AsyncClient, clean_single_sheet_xlsx: Path
) -> None:
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    res = await client.post(
        "/api/v1/imports/extract",
        json={"file_id": file_id, "template_id": 99999},
    )
    assert res.status_code == 404
    assert "Template with ID 99999 was not found" in res.json()["detail"]
