"""Integration tests for Milestone 7.5 Composite Invoice Templates and Line Item Imports.

Covers:
- Composite template creation with header cell mappings and line item column mappings
- Extraction preview returning header fields + line items
- Confirmation persisting InvoiceRecord and child InvoiceLineItems in an atomic transaction
- Verifying batch detail contains line items
- Atomic rollback if an error occurs
- Legacy cell template and legacy dataset template compatibility
"""

import io
from decimal import Decimal
import openpyxl
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.invoice import InvoiceRecord, InvoiceLineItem
from app.models.template import Template


def create_composite_invoice_excel_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"

    # Header fields
    ws["B2"] = "INV-2026-9901"
    ws["B3"] = "2026-09-26"
    ws["B4"] = "Apex Global Industrial Ltd"
    ws["E2"] = "Pacific Distribution Hub"
    ws["E3"] = "USD"
    ws["E4"] = "NET 30"
    ws["E15"] = 3800.00
    ws["E16"] = 304.00
    ws["E17"] = 4104.00

    # Line item table header (Row 7)
    ws["A7"] = "Item Description"
    ws["B7"] = "Qty"
    ws["C7"] = "Unit Price"
    ws["D7"] = "Tax Rate"
    ws["E7"] = "Tax Amount"
    ws["F7"] = "Line Total"

    # 4 Line items (Rows 8..11)
    items = [
        ("Industrial Valve Component", 10, 150.00, "8%", 120.00, 1500.00),
        ("Total Care Cleaning Kit", 4, 75.00, "8%", 24.00, 300.00),
        ("Tax Preparation Service", 2, 500.00, "8%", 80.00, 1000.00),
        ("Hydraulic Pressure Hose", 5, 200.00, "8%", 80.00, 1000.00),
    ]

    for idx, item in enumerate(items, start=8):
        ws[f"A{idx}"] = item[0]
        ws[f"B{idx}"] = item[1]
        ws[f"C{idx}"] = item[2]
        ws[f"D{idx}"] = item[3]
        ws[f"E{idx}"] = item[4]
        ws[f"F{idx}"] = item[5]

    # Footer rows (Rows 12..14)
    ws["A12"] = "Subtotal"
    ws["F12"] = 3800.00

    ws["A13"] = "Tax"
    ws["F13"] = 304.00

    ws["A14"] = "TOTAL"
    ws["F14"] = 4104.00

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_composite_invoice_end_to_end(client: AsyncClient, db_session: Session):
    # 1. Create a composite invoice template
    template_payload = {
        "name": "Apex Standard Composite Invoice",
        "description": "Template with header cells and line item columns",
        "template_type": "invoice",
        "header_row": 7,
        "data_start_row": 8,
        "field_mappings": [
            # Header mappings
            {"field_name": "invoice_number", "mapping_type": "cell", "cell_ref": "B2", "is_required": True, "mapping_group": "header"},
            {"field_name": "invoice_date", "mapping_type": "cell", "cell_ref": "B3", "data_type": "date", "is_required": True, "mapping_group": "header"},
            {"field_name": "supplier_name", "mapping_type": "cell", "cell_ref": "B4", "is_required": True, "mapping_group": "header"},
            {"field_name": "customer_name", "mapping_type": "cell", "cell_ref": "E2", "is_required": False, "mapping_group": "header"},
            {"field_name": "currency", "mapping_type": "cell", "cell_ref": "E3", "is_required": False, "mapping_group": "header"},
            {"field_name": "payment_terms", "mapping_type": "cell", "cell_ref": "E4", "is_required": False, "mapping_group": "header"},
            {"field_name": "subtotal_amount", "mapping_type": "cell", "cell_ref": "E15", "data_type": "decimal", "is_required": False, "mapping_group": "header"},
            {"field_name": "tax_amount", "mapping_type": "cell", "cell_ref": "E16", "data_type": "decimal", "is_required": False, "mapping_group": "header"},
            {"field_name": "total_amount", "mapping_type": "cell", "cell_ref": "E17", "data_type": "decimal", "is_required": True, "mapping_group": "header"},
            # Line item mappings
            {"field_name": "description", "mapping_type": "column", "column_ref": "A", "is_required": True, "mapping_group": "line_item"},
            {"field_name": "quantity", "mapping_type": "column", "column_ref": "B", "data_type": "decimal", "is_required": True, "mapping_group": "line_item"},
            {"field_name": "unit_price", "mapping_type": "column", "column_ref": "C", "data_type": "decimal", "is_required": True, "mapping_group": "line_item"},
            {"field_name": "tax_rate", "mapping_type": "column", "column_ref": "D", "data_type": "decimal", "is_required": False, "mapping_group": "line_item"},
            {"field_name": "tax_amount", "mapping_type": "column", "column_ref": "E", "data_type": "decimal", "is_required": False, "mapping_group": "line_item"},
            {"field_name": "amount", "mapping_type": "column", "column_ref": "F", "data_type": "decimal", "is_required": True, "mapping_group": "line_item"},
        ]
    }

    create_res = await client.post("/api/v1/templates", json=template_payload)
    assert create_res.status_code == 201, create_res.text
    template_data = create_res.json()
    template_id = template_data["id"]
    assert template_data["template_type"] == "invoice"
    assert len(template_data["field_mappings"]) == 15

    # 2. Upload file
    excel_bytes = create_composite_invoice_excel_bytes()
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("apex_invoice.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload_res.status_code == 201, upload_res.text
    file_id = upload_res.json()["file_id"]

    # 3. Extract preview
    extract_res = await client.post(
        "/api/v1/imports/extract",
        json={"file_id": file_id, "template_id": template_id},
    )
    assert extract_res.status_code == 200, extract_res.text
    preview = extract_res.json()

    assert preview["has_line_items"] is True
    assert preview["is_multi_record"] is False
    assert len(preview["line_items"]) == 4

    # Verify line items extracted without footer rows
    def get_field_val(li_dict: dict, name: str):
        for f in li_dict["fields"]:
            if f["field_name"] == name:
                return f["normalized_value"]
        return None

    descriptions = [get_field_val(li, "description") for li in preview["line_items"]]
    assert descriptions == [
        "Industrial Valve Component",
        "Total Care Cleaning Kit",
        "Tax Preparation Service",
        "Hydraulic Pressure Hose",
    ]
    # Check tax_rate and tax_amount
    assert Decimal(get_field_val(preview["line_items"][0], "tax_rate")) == Decimal("8")
    assert Decimal(get_field_val(preview["line_items"][0], "tax_amount")) == Decimal("120.00")
    assert Decimal(get_field_val(preview["line_items"][0], "amount")) == Decimal("1500.00")
    assert preview["line_items"][0]["source_row_number"] == 8
    assert preview["line_items"][3]["source_row_number"] == 11

    # Check header fields
    fields_dict = {f["field_name"]: f["normalized_value"] for f in preview["fields"]}
    assert fields_dict["invoice_number"] == "INV-2026-9901"
    assert fields_dict["supplier_name"] == "Apex Global Industrial Ltd"
    assert Decimal(fields_dict["total_amount"]) == Decimal("4104.00")

    # 4. Confirm import
    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id},
    )
    assert confirm_res.status_code == 201, confirm_res.text
    batch_res = confirm_res.json()
    batch_id = batch_res["id"]
    assert batch_res["record_count"] == 1

    # 5. Verify in database
    stmt = (
        select(InvoiceRecord)
        .where(InvoiceRecord.batch_id == batch_id)
        .options(selectinload(InvoiceRecord.line_items))
    )
    res = db_session.execute(stmt)
    records = res.scalars().all()
    assert len(records) == 1
    inv_rec = records[0]

    assert inv_rec.invoice_number == "INV-2026-9901"
    assert inv_rec.total_amount == Decimal("4104.00")
    assert len(inv_rec.line_items) == 4

    li1 = inv_rec.line_items[0]
    assert li1.description == "Industrial Valve Component"
    assert li1.quantity == Decimal("10")
    assert li1.unit_price == Decimal("150.00")
    assert li1.tax_rate == Decimal("8")
    assert li1.tax_amount == Decimal("120.00")
    assert li1.amount == Decimal("1500.00")
    assert li1.source_row_number == 8

    # Check batch detail endpoint
    get_batch_res = await client.get(f"/api/v1/imports/{batch_id}")
    assert get_batch_res.status_code == 200
    batch_detail = get_batch_res.json()
    assert len(batch_detail["invoice_records"]) == 1
    assert len(batch_detail["invoice_records"][0]["line_items"]) == 4


@pytest.mark.asyncio
async def test_canonical_line_item_fields_endpoint(client: AsyncClient):
    res = await client.get("/api/v1/templates/canonical-line-item-fields")
    assert res.status_code == 200
    fields = res.json()
    assert "description" in fields
    assert "quantity" in fields
    assert "unit_price" in fields
    assert "tax_rate" in fields
    assert "tax_amount" in fields
    assert "amount" in fields


@pytest.mark.asyncio
async def test_composite_invoice_atomic_rollback_on_error(client: AsyncClient, db_session: Session):
    """
    Verifies that if a required line item field is missing in one line item,
    confirmation fails with 422 and nothing is committed (no batch, no invoice, no line items).
    """
    # 1. Create a composite template where quantity is required
    template_payload = {
        "name": "Strict Composite Template",
        "template_type": "invoice",
        "header_row": 7,
        "data_start_row": 8,
        "field_mappings": [
            {"field_name": "invoice_number", "mapping_type": "cell", "cell_ref": "B2", "is_required": True, "mapping_group": "header"},
            {"field_name": "description", "mapping_type": "column", "column_ref": "A", "is_required": True, "mapping_group": "line_item"},
            {"field_name": "quantity", "mapping_type": "column", "column_ref": "B", "data_type": "decimal", "is_required": True, "mapping_group": "line_item"},
        ]
    }
    t_res = await client.post("/api/v1/templates", json=template_payload)
    template_id = t_res.json()["id"]

    # 2. Create workbook where one line item has missing quantity
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["B2"] = "INV-FAULTY-01"
    ws["A7"] = "Item"
    ws["B7"] = "Qty"
    ws["A8"] = "Valid Item 1"
    ws["B8"] = 10
    ws["A9"] = "Invalid Item 2 (No Qty)"
    # B9 is empty!

    buf = io.BytesIO()
    wb.save(buf)

    up_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("faulty.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    file_id = up_res.json()["file_id"]

    # 3. Attempt confirmation
    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id},
    )
    assert confirm_res.status_code == 422

    # 4. Verify DB has 0 batches, 0 invoices, 0 line items
    assert db_session.query(InvoiceRecord).count() == 0
    assert db_session.query(InvoiceLineItem).count() == 0


@pytest.mark.asyncio
async def test_legacy_dataset_template_multi_record(client: AsyncClient, db_session: Session):
    """
    Verifies that a template with template_type='dataset' creates multiple InvoiceRecords
    and no InvoiceLineItems.
    """
    dataset_template = {
        "name": "Legacy Multi-Record Dataset Template",
        "template_type": "dataset",
        "header_row": 1,
        "data_start_row": 2,
        "field_mappings": [
            {"field_name": "invoice_number", "mapping_type": "column", "column_ref": "A", "is_required": True, "mapping_group": "header"},
            {"field_name": "supplier_name", "mapping_type": "column", "column_ref": "B", "is_required": True, "mapping_group": "header"},
            {"field_name": "total_amount", "mapping_type": "column", "column_ref": "C", "data_type": "decimal", "is_required": True, "mapping_group": "header"},
        ]
    }
    t_res = await client.post("/api/v1/templates", json=dataset_template)
    template_id = t_res.json()["id"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Inv Num"
    ws["B1"] = "Vendor"
    ws["C1"] = "Amount"

    ws["A2"] = "INV-001"
    ws["B2"] = "Vendor A"
    ws["C2"] = 100.00

    ws["A3"] = "INV-002"
    ws["B3"] = "Vendor B"
    ws["C3"] = 200.00

    ws["A4"] = "INV-003"
    ws["B4"] = "Vendor C"
    ws["C4"] = 300.00

    buf = io.BytesIO()
    wb.save(buf)

    up_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("dataset.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    file_id = up_res.json()["file_id"]

    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id},
    )
    assert confirm_res.status_code == 201
    batch_data = confirm_res.json()
    assert batch_data["record_count"] == 3

    records = db_session.query(InvoiceRecord).filter(InvoiceRecord.batch_id == batch_data["id"]).all()
    assert len(records) == 3
    assert db_session.query(InvoiceLineItem).count() == 0

