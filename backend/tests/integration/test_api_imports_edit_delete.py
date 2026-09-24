"""
tests/integration/test_api_imports_edit_delete.py — Integration tests for:
1. GET /api/v1/templates/canonical-fields
2. DELETE /api/v1/imports/{batch_id} (soft delete)
3. PATCH /api/v1/imports/{batch_id}/records/{record_id} (record editing)
4. Custom fields preservation & target_field mapping
"""

from decimal import Decimal
from pathlib import Path
from typing import Any
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.invoice import ImportBatch, InvoiceRecord


@pytest.fixture
def target_mapping_template_payload() -> dict[str, Any]:
    return {
        "name": "Custom Mapping Template",
        "file_type": "xlsx",
        "worksheet": "Invoice",
        "field_mappings": [
            {
                "field_name": "Supplier Entity",
                "target_field": "company_name",
                "mapping_type": "cell",
                "cell_ref": "B2",
                "is_required": True,
                "data_type": "text",
            },
            {
                "field_name": "Bill Code",
                "target_field": "invoice_number",
                "mapping_type": "cell",
                "cell_ref": "B3",
                "is_required": True,
                "data_type": "text",
            },
            {
                "field_name": "Issue Timestamp",
                "target_field": "invoice_date",
                "mapping_type": "cell",
                "cell_ref": "F3",
                "is_required": True,
                "data_type": "date",
            },
            {
                "field_name": "Grand Total",
                "target_field": "total_amount",
                "mapping_type": "cell",
                "cell_ref": "D6",
                "is_required": False,
                "data_type": "decimal",
            },
            {
                "field_name": "department_code",
                "target_field": None,  # Custom field!
                "mapping_type": "cell",
                "cell_ref": "A1",
                "is_required": False,
                "data_type": "text",
            },
        ],
    }


@pytest.mark.asyncio
async def test_get_canonical_fields(client: AsyncClient) -> None:
    res = await client.get("/api/v1/templates/canonical-fields")
    assert res.status_code == 200
    fields = res.json()
    assert "company_name" in fields
    assert "invoice_number" in fields
    assert "invoice_date" in fields
    assert "total_amount" in fields
    assert "currency" in fields


@pytest.mark.asyncio
async def test_soft_delete_and_patch_invoice_record(
    client: AsyncClient,
    clean_single_sheet_xlsx: Path,
    target_mapping_template_payload: dict[str, Any],
    db_session: Session,
) -> None:
    # 1. Create template with explicit target_field mappings
    tpl_res = await client.post("/api/v1/templates", json=target_mapping_template_payload)
    assert tpl_res.status_code == 201
    tpl_id = tpl_res.json()["id"]

    # 2. Upload file
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    # 3. Confirm import
    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": tpl_id, "acknowledge_warnings": True},
    )
    assert confirm_res.status_code == 201
    batch_data = confirm_res.json()
    batch_id = batch_data["id"]
    assert len(batch_data["invoice_records"]) >= 1
    record = batch_data["invoice_records"][0]
    record_id = record["id"]

    # Check that canonical mapping worked via target_field
    assert record["company_name"] == "Acme Supplies Ltd"
    assert record["invoice_number"] == "INV-2026-001"
    assert float(record["total_amount"]) == 1450.50

    # 4. PATCH the invoice record's canonical fields
    patch_payload = {
        "company_name": "Alpha Corp International",
        "total_amount": 1999.99,
        "currency": "USD",
    }
    patch_res = await client.patch(
        f"/api/v1/imports/{batch_id}/records/{record_id}",
        json=patch_payload,
    )
    assert patch_res.status_code == 200
    patched_record = patch_res.json()
    assert patched_record["company_name"] == "Alpha Corp International"
    assert float(patched_record["total_amount"]) == 1999.99
    assert patched_record["currency"] == "USD"
    # Unchanged canonical field should be preserved
    assert patched_record["invoice_number"] == "INV-2026-001"

    # 5. Verify batch list includes the batch
    list_res = await client.get("/api/v1/imports")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(b["id"] == batch_id for b in items)

    # 6. Soft-delete the batch
    del_res = await client.delete(f"/api/v1/imports/{batch_id}")
    assert del_res.status_code == 204

    # 7. Check database state directly: is_deleted == True
    db_batch = db_session.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    assert db_batch is not None
    assert db_batch.is_deleted is True

    # 8. GET /api/v1/imports should NOT list the soft-deleted batch
    list_res_after = await client.get("/api/v1/imports")
    assert list_res_after.status_code == 200
    items_after = list_res_after.json()
    assert not any(b["id"] == batch_id for b in items_after)

    # 9. GET /api/v1/imports/{batch_id} should return 404
    detail_res_after = await client.get(f"/api/v1/imports/{batch_id}")
    assert detail_res_after.status_code == 404

    # 10. Attempting to PATCH records of a soft-deleted batch should return 404
    patch_deleted_res = await client.patch(
        f"/api/v1/imports/{batch_id}/records/{record_id}",
        json={"company_name": "Should Fail"},
    )
    assert patch_deleted_res.status_code == 404
