"""
tests/integration/test_api_imports_persistence.py — Integration tests for import confirmation & history.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.invoice import ImportBatch, InvoiceRecord, ValidationErrorRecord


@pytest.fixture
def clean_template_payload() -> dict[str, Any]:
    return {
        "name": "Supplier Invoice Standard",
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
async def test_confirm_import_success_persists_batch_and_invoice(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    clean_template_payload: dict[str, Any],
    db_session: Session,
) -> None:
    """Confirming a valid import creates an ImportBatch and InvoiceRecord in DB."""
    # 1. Upload file
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    # 2. Create template
    template_res = await client.post("/api/v1/templates", json=clean_template_payload)
    template_id = template_res.json()["id"]

    # 3. Confirm import
    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={
            "file_id": file_id,
            "template_id": template_id,
            "acknowledge_warnings": True,
        },
    )
    assert confirm_res.status_code == 201

    data = confirm_res.json()
    batch_id = data["id"]
    assert batch_id > 0
    assert data["status"] == "imported"
    assert data["record_count"] == 1
    assert len(data["invoice_records"]) == 1

    inv = data["invoice_records"][0]
    assert inv["company_name"] == "Acme Supplies Ltd"
    assert inv["invoice_number"] == "INV-2026-001"
    assert inv["invoice_date"] == "2026-09-22"
    assert float(inv["total_amount"]) == 1450.50

    # 4. Verify in Database
    db_session.expire_all()
    db_batch = db_session.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    assert db_batch is not None
    assert db_batch.status == "imported"
    assert len(db_batch.invoice_records) == 1

    db_inv = db_batch.invoice_records[0]
    assert db_inv.company_name == "Acme Supplies Ltd"
    assert db_inv.total_amount == Decimal("1450.50")
    assert "Acme Supplies Ltd" in db_inv.raw_data

@pytest.mark.asyncio
async def test_confirm_import_handles_different_field_naming_formats(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    clean_template_payload: dict[str, Any],
    db_session: Session,
) -> None:
    """Verify that fields like 'Company Name' or 'invoice number' map correctly to DB columns."""
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    # Modify template to use weird field names
    weird_template = dict(clean_template_payload)
    weird_template["name"] = "Weird Template"
    for field in weird_template["field_mappings"]:
        if field["field_name"] == "company_name":
            field["field_name"] = "Company"
        elif field["field_name"] == "invoice_number":
            field["field_name"] = "invoice number"
        elif field["field_name"] == "invoice_date":
            field["field_name"] = "Invoice-Date"
        elif field["field_name"] == "total_amount":
            field["field_name"] = "total amount"

    template_res = await client.post("/api/v1/templates", json=weird_template)
    template_id = template_res.json()["id"]

    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id, "acknowledge_warnings": True},
    )
    assert confirm_res.status_code == 201
    
    data = confirm_res.json()
    inv = data["invoice_records"][0]
    assert inv["company_name"] == "Acme Supplies Ltd"
    assert inv["invoice_number"] == "INV-2026-001"
    assert inv["invoice_date"] == "2026-09-22"
    assert float(inv["total_amount"]) == 1450.50

@pytest.mark.asyncio
async def test_confirm_import_rejected_on_validation_errors_commits_nothing(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    clean_template_payload: dict[str, Any],
    db_session: Session,
) -> None:
    """If extracted data fails validation, confirm endpoint returns 422 and commits zero rows."""
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    # Modify template to require an empty cell (Z1)
    broken_template = dict(clean_template_payload)
    broken_template["name"] = "Broken Template"
    broken_template["field_mappings"].append(
        {
            "field_name": "po_number",
            "mapping_type": "cell",
            "cell_ref": "Z1",
            "is_required": True,
            "data_type": "text",
        }
    )
    template_res = await client.post("/api/v1/templates", json=broken_template)
    template_id = template_res.json()["id"]

    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id},
    )
    assert confirm_res.status_code == 422
    assert "Cannot confirm import" in confirm_res.json()["detail"]

    # Verify zero batches and zero invoices committed
    db_session.expire_all()
    assert db_session.query(ImportBatch).count() == 0
    assert db_session.query(InvoiceRecord).count() == 0


@pytest.mark.asyncio
async def test_live_duplicate_invoice_detection_after_persistence(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    clean_template_payload: dict[str, Any],
) -> None:
    """Once an invoice is confirmed, subsequent extractions of the same invoice trigger DUPLICATE_INVOICE."""
    # 1. Upload and confirm first invoice
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    template_res = await client.post("/api/v1/templates", json=clean_template_payload)
    template_id = template_res.json()["id"]

    await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id, "acknowledge_warnings": True},
    )

    # 2. Run extraction preview on a second upload with same data
    upload_res2 = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice_copy.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id2 = upload_res2.json()["file_id"]

    extract_res = await client.post(
        "/api/v1/imports/extract",
        json={"file_id": file_id2, "template_id": template_id},
    )
    assert extract_res.status_code == 200

    val_report = extract_res.json()["validation_report"]
    issue_rules = [i["rule_id"] for i in val_report["issues"]]
    assert "DUPLICATE_INVOICE" in issue_rules


@pytest.mark.asyncio
async def test_history_listing_and_detail(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    clean_template_payload: dict[str, Any],
) -> None:
    """Verify GET /api/v1/imports and GET /api/v1/imports/{batch_id}."""
    # Setup and confirm one batch
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    template_res = await client.post("/api/v1/templates", json=clean_template_payload)
    template_id = template_res.json()["id"]

    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id, "acknowledge_warnings": True},
    )
    batch_id = confirm_res.json()["id"]

    # 1. Test List Endpoint
    list_res = await client.get("/api/v1/imports?skip=0&limit=10")
    assert list_res.status_code == 200
    batches = list_res.json()
    assert len(batches) == 1
    assert batches[0]["id"] == batch_id
    assert batches[0]["status"] == "imported"
    assert batches[0]["record_count"] == 1

    # 2. Test Detail Endpoint
    detail_res = await client.get(f"/api/v1/imports/{batch_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == batch_id
    assert len(detail["invoice_records"]) == 1
    assert detail["invoice_records"][0]["company_name"] == "Acme Supplies Ltd"

    # 3. Test Detail 404
    missing_res = await client.get("/api/v1/imports/99999")
    assert missing_res.status_code == 404
