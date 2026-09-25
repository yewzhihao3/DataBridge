"""
tests/integration/test_m75_northstar_persistence_audit.py — Milestone 7.5 Persistence and Canonical-Field Audit Tests.

Covers regression criteria A through F specified in M7.5 audit requirements:
A. Composite line-item persistence (description, quantity, unit_price, tax_rate, amount)
B. Multiple line items (all 4 Northstar line items persisted with full numeric fidelity)
C. Invoice total (7211.592 persisted to InvoiceRecord.total_amount)
D. Company merged-cell top-left mapping (A1 -> company_name)
E. Custom line-item field (non-canonical line-item field persisted to InvoiceLineItem.custom_fields)
F. Invoice tax semantics (tax_amount remains tax_amount in custom_fields, not converted to tax_rate)
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


def build_northstar_workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"

    # Header cells (A1:F1 merged company name)
    ws["A1"] = "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    ws["F5"] = "NOS-2026-0947"
    ws["F6"] = "2026-09-20"
    ws["F7"] = "2026-10-20"
    ws["F8"] = "MYR"

    # Line items table header (Row 10)
    ws["A10"] = "Description"
    ws["B10"] = "Qty"
    ws["C10"] = "Unit Price"
    ws["D10"] = "Tax Rate"
    ws["E10"] = "Amount"

    # 4 Northstar line items (Rows 11..14)
    items = [
        ("Ergonomic Office Chair — Model E7", 6, 689.00, "8%", 4134.00, "SKU-CHAIR-E7"),
        ("Adjustable Monitor Arm — Dual Display", 6, 249.00, "8%", 1494.00, "SKU-ARM-DUAL"),
        ("Wireless Keyboard & Mouse Set", 6, 129.90, "8%", 779.40, "SKU-KBD-SET"),
        ("Cable Management Tray", 6, 45.00, "8%", 270.00, "SKU-TRAY-01"),
    ]

    for idx, (desc, qty, price, rate, amt, sku) in enumerate(items, start=11):
        ws[f"A{idx}"] = desc
        ws[f"B{idx}"] = qty
        ws[f"C{idx}"] = price
        ws[f"D{idx}"] = rate
        ws[f"E{idx}"] = amt
        ws[f"F{idx}"] = sku

    # Footer rows
    ws["D16"] = "Subtotal"
    ws["E16"] = 6677.40

    ws["D17"] = "Tax (8%)"
    ws["E17"] = 534.192

    ws["D18"] = "TOTAL"
    ws["E18"] = 7211.592

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
async def northstar_template_and_file(client: AsyncClient):
    file_bytes = build_northstar_workbook_bytes()
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("northstar_demo_invoice.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    template_payload = {
        "name": "Northstar Audit Template",
        "description": "Template for M7.5 Northstar invoice audit",
        "template_type": "invoice",
        "file_type": "xlsx",
        "worksheet": "Invoice",
        "header_row": 10,
        "data_start_row": 11,
        "field_mappings": [
            {"field_name": "Supplier", "target_field": "company_name", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "A1", "is_required": True, "data_type": "text"},
            {"field_name": "Invoice No", "target_field": "invoice_number", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "F5", "is_required": True, "data_type": "text"},
            {"field_name": "Invoice Date", "target_field": "invoice_date", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "F6", "is_required": True, "data_type": "date"},
            {"field_name": "Due Date", "target_field": "due_date", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "F7", "is_required": False, "data_type": "date"},
            {"field_name": "Currency", "target_field": "currency", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "F8", "is_required": False, "data_type": "text"},
            {"field_name": "Subtotal", "target_field": "sub_total", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "E16", "is_required": False, "data_type": "decimal"},
            {"field_name": "Tax Amount", "target_field": "tax_amount", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "E17", "is_required": False, "data_type": "decimal"},
            {"field_name": "Total Amount", "target_field": "total_amount", "mapping_group": "header", "mapping_type": "cell", "cell_ref": "E18", "is_required": True, "data_type": "decimal"},

            {"field_name": "Description", "target_field": "description", "mapping_group": "line_item", "mapping_type": "column", "column_ref": "A", "is_required": True, "data_type": "text"},
            {"field_name": "Qty", "target_field": "quantity", "mapping_group": "line_item", "mapping_type": "column", "column_ref": "B", "is_required": True, "data_type": "decimal"},
            {"field_name": "Unit Price", "target_field": "unit_price", "mapping_group": "line_item", "mapping_type": "column", "column_ref": "C", "is_required": True, "data_type": "decimal"},
            {"field_name": "Tax Rate", "target_field": "tax_rate", "mapping_group": "line_item", "mapping_type": "column", "column_ref": "D", "is_required": False, "data_type": "decimal"},
            {"field_name": "Amount", "target_field": "amount", "mapping_group": "line_item", "mapping_type": "column", "column_ref": "E", "is_required": True, "data_type": "decimal"},
            {"field_name": "SKU Code", "target_field": "sku_code", "mapping_group": "line_item", "mapping_type": "column", "column_ref": "F", "is_required": False, "data_type": "text"},
        ],
    }

    tmpl_res = await client.post("/api/v1/templates", json=template_payload)
    assert tmpl_res.status_code == 201
    template_id = tmpl_res.json()["id"]

    return file_id, template_id


@pytest.mark.asyncio
async def test_northstar_m75_persistence_audit(client: AsyncClient, db_session: Session, northstar_template_and_file):
    file_id, template_id = northstar_template_and_file

    # 1. Preview
    extract_res = await client.post("/api/v1/imports/extract", json={"file_id": file_id, "template_id": template_id})
    assert extract_res.status_code == 200
    preview = extract_res.json()
    assert preview["has_line_items"] is True
    assert len(preview["line_items"]) == 4

    # 2. Confirm import
    confirm_res = await client.post(
        "/api/v1/imports/confirm",
        json={"file_id": file_id, "template_id": template_id, "acknowledge_warnings": True},
    )
    assert confirm_res.status_code == 201
    confirm_data = confirm_res.json()
    batch_id = confirm_data["id"]

    # 3. Retrieve DB record
    stmt = select(InvoiceRecord).where(InvoiceRecord.batch_id == batch_id).options(selectinload(InvoiceRecord.line_items))
    inv_rec = db_session.execute(stmt).scalars().one()

    # D. Company merged-cell top-left mapping A1 -> company_name
    assert inv_rec.company_name == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert inv_rec.invoice_number == "NOS-2026-0947"
    assert inv_rec.invoice_date.isoformat() == "2026-09-20"
    assert inv_rec.currency == "MYR"

    # C. Invoice total E18 -> total_amount
    assert Decimal(str(inv_rec.total_amount)) == Decimal("7211.59")

    # F. Invoice tax semantics: tax_amount remains tax_amount in custom_fields, not tax_rate
    assert inv_rec.custom_fields is not None
    assert "tax_amount" in inv_rec.custom_fields
    assert "tax_rate" not in inv_rec.custom_fields
    assert inv_rec.custom_fields["tax_amount"] == "534.192"
    assert inv_rec.custom_fields["sub_total"] == "6677.4"

    # A & B. Line items canonical persistence & 4 line items
    assert len(inv_rec.line_items) == 4

    li1 = inv_rec.line_items[0]
    assert li1.description == "Ergonomic Office Chair — Model E7"
    assert li1.quantity == Decimal("6.0000")
    assert li1.unit_price == Decimal("689.00")
    assert li1.tax_rate == Decimal("0.0800")
    assert li1.amount == Decimal("4134.00")
    # E. Custom line-item field sku_code in custom_fields
    assert li1.custom_fields is not None and li1.custom_fields.get("sku_code") == "SKU-CHAIR-E7"

    li2 = inv_rec.line_items[1]
    assert li2.description == "Adjustable Monitor Arm — Dual Display"
    assert li2.quantity == Decimal("6.0000")
    assert li2.unit_price == Decimal("249.00")
    assert li2.tax_rate == Decimal("0.0800")
    assert li2.amount == Decimal("1494.00")

    li3 = inv_rec.line_items[2]
    assert li3.description == "Wireless Keyboard & Mouse Set"
    assert li3.quantity == Decimal("6.0000")
    assert li3.unit_price == Decimal("129.90")
    assert li3.tax_rate == Decimal("0.0800")
    assert li3.amount == Decimal("779.40")

    li4 = inv_rec.line_items[3]
    assert li4.description == "Cable Management Tray"
    assert li4.quantity == Decimal("6.0000")
    assert li4.unit_price == Decimal("45.00")
    assert li4.tax_rate == Decimal("0.0800")
    assert li4.amount == Decimal("270.00")

    # 4. Import Details API retrieval check
    get_detail_res = await client.get(f"/api/v1/imports/{batch_id}")
    assert get_detail_res.status_code == 200
    detail_data = get_detail_res.json()
    rec_read = detail_data["invoice_records"][0]

    assert rec_read["company_name"] == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert rec_read["invoice_number"] == "NOS-2026-0947"
    assert Decimal(str(rec_read["total_amount"])) == Decimal("7211.59")
    assert len(rec_read["line_items"]) == 4

    item1_read = rec_read["line_items"][0]
    assert item1_read["description"] == "Ergonomic Office Chair — Model E7"
    assert Decimal(str(item1_read["quantity"])) == Decimal("6")
    assert Decimal(str(item1_read["unit_price"])) == Decimal("689")
    assert Decimal(str(item1_read["tax_rate"])) == Decimal("0.08")
    assert Decimal(str(item1_read["amount"])) == Decimal("4134")
