"""
tests/integration/test_api_data_explorer.py — Integration tests for Milestone 8 Data Explorer endpoints.

Covers:
- Default paginated invoice list
- Search company
- Search invoice number
- Company filter
- Currency filter
- Date-from filter
- Date-to filter
- Has line items filter
- Sorting ascending / descending (allowlisted columns)
- Pagination (page, page_size, total_pages)
- Invoice detail retrieval with line items and custom fields
- Invoice record PATCH update
- Soft-deleted batches excluded from invoice lists, counts, and details
- Default paginated line items list
- Line item description search
- Line item parent company / invoice search
- Line item filters (company, currency, date_from, date_to)
- Line item sorting
- Line item custom fields
- Soft-deleted parent batches excluded from line items list and count
- Dynamic filter options (companies, currencies)
- Security and validation (invalid sort field, invalid sort order, invalid pagination)
"""

from datetime import date, datetime
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.invoice import ImportBatch, InvoiceLineItem, InvoiceRecord
from app.models.source_file import SourceFile
from app.models.template import Template


@pytest.fixture
def seed_explorer_data(db_session: Session) -> dict:
    """
    Seeds test database with:
    1. Active Batch 1 (Northstar invoice with 4 line items and custom fields)
    2. Active Batch 2 (Asteron Medical multi-record / header invoices)
    3. Soft-deleted Batch 3 (Should be completely hidden from Data Explorer)
    """
    # 1. Source files
    sf1 = SourceFile(
        stored_filename="northstar.xlsx",
        original_name="Northstar_Invoice_Sept2026.xlsx",
        file_size=10240,
        checksum="abc111",
    )
    sf2 = SourceFile(
        stored_filename="asteron.xlsx",
        original_name="Asteron_Medical_Sept2026.xlsx",
        file_size=8192,
        checksum="abc222",
    )
    sf3 = SourceFile(
        stored_filename="deleted_batch.xlsx",
        original_name="Deleted_Batch.xlsx",
        file_size=4096,
        checksum="abc333",
    )
    db_session.add_all([sf1, sf2, sf3])
    db_session.flush()

    # 2. Templates
    t1 = Template(
        name="Northstar Invoice Template",
        template_type="invoice",
        file_type="xlsx",
        worksheet="Invoice",
    )
    t2 = Template(
        name="Asteron Multi-Record Template",
        template_type="dataset",
        file_type="xlsx",
        worksheet="Sheet1",
    )
    db_session.add_all([t1, t2])
    db_session.flush()

    # 3. Batches
    batch1 = ImportBatch(
        source_file_id=sf1.id,
        template_id=t1.id,
        status="imported",
        record_count=1,
        warning_count=0,
        is_deleted=False,
        imported_at=datetime(2026, 9, 21, 10, 0, 0),
    )
    batch2 = ImportBatch(
        source_file_id=sf2.id,
        template_id=t2.id,
        status="imported",
        record_count=2,
        warning_count=1,
        is_deleted=False,
        imported_at=datetime(2026, 9, 22, 11, 30, 0),
    )
    batch_deleted = ImportBatch(
        source_file_id=sf3.id,
        template_id=t1.id,
        status="imported",
        record_count=1,
        warning_count=0,
        is_deleted=True,  # Soft deleted!
        imported_at=datetime(2026, 9, 20, 8, 0, 0),
    )
    db_session.add_all([batch1, batch2, batch_deleted])
    db_session.flush()

    # 4. Invoices
    # Invoice 1: Northstar (Active)
    inv1 = InvoiceRecord(
        batch_id=batch1.id,
        company_name="NORTHSTAR OFFICE SOLUTIONS SDN. BHD.",
        invoice_number="NOS-2026-0947",
        invoice_date=date(2026, 9, 20),
        total_amount=Decimal("7211.59"),
        currency="MYR",
        source_worksheet="Invoice",
        raw_data='{"company": "NORTHSTAR OFFICE SOLUTIONS SDN. BHD.", "invoice_num": "NOS-2026-0947"}',
        custom_fields={"due_date": "2026-10-20", "sub_total": "6677.40", "tax_amount": "534.19"},
        created_at=datetime(2026, 9, 21, 10, 0, 0),
    )
    # Invoice 2: Asteron 1 (Active)
    inv2 = InvoiceRecord(
        batch_id=batch2.id,
        company_name="Asteron Medical Supplies",
        invoice_number="INV-1001",
        invoice_date=date(2026, 9, 1),
        total_amount=Decimal("1250.00"),
        currency="USD",
        source_worksheet="Sheet1",
        source_row_number=2,
        raw_data='{"company": "Asteron Medical Supplies"}',
        custom_fields={"payment_terms": "Net 30"},
        created_at=datetime(2026, 9, 22, 11, 30, 0),
    )
    # Invoice 3: Asteron 2 (Active, no line items)
    inv3 = InvoiceRecord(
        batch_id=batch2.id,
        company_name="Asteron Medical Supplies",
        invoice_number="INV-1002",
        invoice_date=date(2026, 9, 15),
        total_amount=Decimal("4500.00"),
        currency="USD",
        source_worksheet="Sheet1",
        source_row_number=3,
        raw_data='{"company": "Asteron Medical Supplies"}',
        custom_fields={"payment_terms": "Net 15"},
        created_at=datetime(2026, 9, 22, 11, 31, 0),
    )
    # Invoice 4: Soft-Deleted Invoice
    inv_del = InvoiceRecord(
        batch_id=batch_deleted.id,
        company_name="Ghost Technologies Inc",
        invoice_number="GHOST-9999",
        invoice_date=date(2026, 9, 10),
        total_amount=Decimal("9999.99"),
        currency="USD",
        source_worksheet="Invoice",
        raw_data='{"company": "Ghost Technologies"}',
        created_at=datetime(2026, 9, 20, 8, 0, 0),
    )
    db_session.add_all([inv1, inv2, inv3, inv_del])
    db_session.flush()

    # 5. Line items
    # 4 Northstar line items
    li1 = InvoiceLineItem(
        invoice_id=inv1.id,
        source_row_number=11,
        description="Ergonomic Office Chair — Model E7",
        quantity=Decimal("6.0000"),
        unit_price=Decimal("689.00"),
        tax_rate=Decimal("0.0800"),
        amount=Decimal("4134.00"),
        custom_fields={"sku_code": "SKU-CHAIR-E7"},
        created_at=datetime(2026, 9, 21, 10, 0, 0),
    )
    li2 = InvoiceLineItem(
        invoice_id=inv1.id,
        source_row_number=12,
        description="Adjustable Monitor Arm — Dual Display",
        quantity=Decimal("6.0000"),
        unit_price=Decimal("249.00"),
        tax_rate=Decimal("0.0800"),
        amount=Decimal("1494.00"),
        custom_fields={"sku_code": "SKU-ARM-DUAL"},
        created_at=datetime(2026, 9, 21, 10, 0, 0),
    )
    li3 = InvoiceLineItem(
        invoice_id=inv1.id,
        source_row_number=13,
        description="Wireless Keyboard & Mouse Set",
        quantity=Decimal("6.0000"),
        unit_price=Decimal("129.90"),
        tax_rate=Decimal("0.0800"),
        amount=Decimal("779.40"),
        custom_fields={"sku_code": "SKU-KBD-SET"},
        created_at=datetime(2026, 9, 21, 10, 0, 0),
    )
    li4 = InvoiceLineItem(
        invoice_id=inv1.id,
        source_row_number=14,
        description="Cable Management Tray",
        quantity=Decimal("6.0000"),
        unit_price=Decimal("45.00"),
        tax_rate=Decimal("0.0800"),
        amount=Decimal("270.00"),
        custom_fields={"sku_code": "SKU-TRAY-01"},
        created_at=datetime(2026, 9, 21, 10, 0, 0),
    )
    # 1 Asteron line item
    li5 = InvoiceLineItem(
        invoice_id=inv2.id,
        source_row_number=1,
        description="Surgical Gloves Latex Box",
        quantity=Decimal("25.0000"),
        unit_price=Decimal("50.00"),
        amount=Decimal("1250.00"),
        created_at=datetime(2026, 9, 22, 11, 30, 0),
    )
    # Line item in deleted batch
    li_del = InvoiceLineItem(
        invoice_id=inv_del.id,
        source_row_number=1,
        description="Ghost Item Not Visible",
        quantity=Decimal("1.0000"),
        unit_price=Decimal("9999.99"),
        amount=Decimal("9999.99"),
        created_at=datetime(2026, 9, 20, 8, 0, 0),
    )
    db_session.add_all([li1, li2, li3, li4, li5, li_del])
    db_session.commit()

    return {
        "batch1": batch1,
        "batch2": batch2,
        "batch_deleted": batch_deleted,
        "inv1": inv1,
        "inv2": inv2,
        "inv3": inv3,
        "inv_del": inv_del,
    }


# ── Invoices Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_invoices_default_pagination(client: AsyncClient, seed_explorer_data: dict):
    """Verifies default list excludes soft-deleted records and returns pagination metadata."""
    res = await client.get("/api/v1/data/invoices")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3  # inv1, inv2, inv3 (inv_del excluded)
    assert data["page"] == 1
    assert data["page_size"] == 25
    assert len(data["items"]) == 3

    # Check first item contains business columns and line_item_count
    item_by_num = {item["invoice_number"]: item for item in data["items"]}
    assert "NOS-2026-0947" in item_by_num
    nos = item_by_num["NOS-2026-0947"]
    assert nos["company_name"] == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert nos["currency"] == "MYR"
    assert float(nos["total_amount"]) == 7211.59
    assert nos["line_item_count"] == 4
    assert nos["source_filename"] == "Northstar_Invoice_Sept2026.xlsx"


@pytest.mark.asyncio
async def test_search_invoices_by_company(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?search=Northstar")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["invoice_number"] == "NOS-2026-0947"


@pytest.mark.asyncio
async def test_search_invoices_by_invoice_number(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?search=INV-1001")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["invoice_number"] == "INV-1001"


@pytest.mark.asyncio
async def test_filter_invoices_by_company(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?company=Asteron")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert "Asteron" in item["company_name"]


@pytest.mark.asyncio
async def test_filter_invoices_by_currency(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?currency=MYR")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["currency"] == "MYR"


@pytest.mark.asyncio
async def test_filter_invoices_by_date_range(client: AsyncClient, seed_explorer_data: dict):
    # From 2026-09-10 to 2026-09-20
    res = await client.get("/api/v1/data/invoices?date_from=2026-09-10&date_to=2026-09-20")
    assert res.status_code == 200
    data = res.json()
    # Should include INV-1002 (Sept 15) and NOS-2026-0947 (Sept 20)
    assert data["total"] == 2
    numbers = {item["invoice_number"] for item in data["items"]}
    assert numbers == {"INV-1002", "NOS-2026-0947"}


@pytest.mark.asyncio
async def test_filter_invoices_by_has_line_items(client: AsyncClient, seed_explorer_data: dict):
    # has_line_items=true
    res = await client.get("/api/v1/data/invoices?has_line_items=true")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2  # NOS-2026-0947 (4 items) and INV-1001 (1 item)

    # has_line_items=false
    res_false = await client.get("/api/v1/data/invoices?has_line_items=false")
    assert res_false.status_code == 200
    data_false = res_false.json()
    assert data_false["total"] == 1  # INV-1002 (0 items)
    assert data_false["items"][0]["invoice_number"] == "INV-1002"


@pytest.mark.asyncio
async def test_sort_invoices_ascending_descending(client: AsyncClient, seed_explorer_data: dict):
    # Sort by total_amount asc
    res_asc = await client.get("/api/v1/data/invoices?sort_by=total_amount&sort_order=asc")
    assert res_asc.status_code == 200
    items_asc = res_asc.json()["items"]
    assert float(items_asc[0]["total_amount"]) == 1250.00
    assert float(items_asc[-1]["total_amount"]) == 7211.59

    # Sort by total_amount desc
    res_desc = await client.get("/api/v1/data/invoices?sort_by=total_amount&sort_order=desc")
    assert res_desc.status_code == 200
    items_desc = res_desc.json()["items"]
    assert float(items_desc[0]["total_amount"]) == 7211.59
    assert float(items_desc[-1]["total_amount"]) == 1250.00


@pytest.mark.asyncio
async def test_sort_invoices_by_line_item_count(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?sort_by=line_item_count&sort_order=desc")
    assert res.status_code == 200
    items = res.json()["items"]
    assert items[0]["line_item_count"] == 4
    assert items[-1]["line_item_count"] == 0


@pytest.mark.asyncio
async def test_invoices_pagination_page_size(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?page=1&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 2

    # Page 2
    res_p2 = await client.get("/api/v1/data/invoices?page=2&page_size=2")
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["items"]) == 1


# ── Invoice Detail Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_invoice_detail_success(client: AsyncClient, seed_explorer_data: dict):
    inv1_id = seed_explorer_data["inv1"].id
    res = await client.get(f"/api/v1/data/invoices/{inv1_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == inv1_id
    assert data["company_name"] == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert data["invoice_number"] == "NOS-2026-0947"
    assert data["custom_fields"]["due_date"] == "2026-10-20"
    assert data["custom_fields"]["sub_total"] == "6677.40"
    assert len(data["line_items"]) == 4
    assert data["batch"]["template_name"] == "Northstar Invoice Template"
    assert data["batch"]["source_filename"] == "Northstar_Invoice_Sept2026.xlsx"


@pytest.mark.asyncio
async def test_get_invoice_detail_soft_deleted_returns_404(client: AsyncClient, seed_explorer_data: dict):
    inv_del_id = seed_explorer_data["inv_del"].id
    res = await client.get(f"/api/v1/data/invoices/{inv_del_id}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_patch_invoice_canonical_fields(client: AsyncClient, seed_explorer_data: dict):
    inv2_id = seed_explorer_data["inv2"].id
    update_payload = {
        "company_name": "Asteron Medical Supplies Corp",
        "total_amount": "1299.50",
    }
    res = await client.patch(f"/api/v1/data/invoices/{inv2_id}", json=update_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["company_name"] == "Asteron Medical Supplies Corp"
    assert float(data["total_amount"]) == 1299.50
    # Custom fields preserved
    assert data["custom_fields"]["payment_terms"] == "Net 30"


# ── Line Items Tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_line_items_default(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/line-items")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5  # 4 Northstar + 1 Asteron (ghost deleted excluded)
    assert len(data["items"]) == 5

    # Check parent invoice metadata on line items
    chair_item = next(item for item in data["items"] if "Chair" in item["description"])
    assert chair_item["company_name"] == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert chair_item["invoice_number"] == "NOS-2026-0947"
    assert chair_item["currency"] == "MYR"
    assert float(chair_item["unit_price"]) == 689.00
    assert float(chair_item["amount"]) == 4134.00
    assert chair_item["custom_fields"]["sku_code"] == "SKU-CHAIR-E7"


@pytest.mark.asyncio
async def test_search_line_items_by_description(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/line-items?search=Monitor")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert "Monitor Arm" in data["items"][0]["description"]


@pytest.mark.asyncio
async def test_search_line_items_by_parent_invoice_number(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/line-items?search=NOS-2026-0947")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4


@pytest.mark.asyncio
async def test_filter_line_items_by_company(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/line-items?company=Asteron")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["description"] == "Surgical Gloves Latex Box"


@pytest.mark.asyncio
async def test_sort_line_items(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/line-items?sort_by=amount&sort_order=desc")
    assert res.status_code == 200
    items = res.json()["items"]
    assert float(items[0]["amount"]) == 4134.00
    assert float(items[-1]["amount"]) == 270.00


# ── Filter Options Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_filter_options(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/filter-options")
    assert res.status_code == 200
    data = res.json()
    assert "NORTHSTAR OFFICE SOLUTIONS SDN. BHD." in data["companies"]
    assert "Asteron Medical Supplies" in data["companies"]
    assert "Ghost Technologies Inc" not in data["companies"]  # Deleted batch excluded

    assert "MYR" in data["currencies"]
    assert "USD" in data["currencies"]


# ── Security & Validation Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_sort_by_defaults_safely(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?sort_by=nonexistent_column;DROP+TABLE")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3  # Safely fell back to default sort


@pytest.mark.asyncio
async def test_invalid_pagination_params(client: AsyncClient, seed_explorer_data: dict):
    res = await client.get("/api/v1/data/invoices?page=0")
    assert res.status_code == 422

    res_large = await client.get("/api/v1/data/invoices?page_size=500")
    assert res_large.status_code == 422


@pytest.mark.asyncio
async def test_northstar_m8_full_specification_audit(client: AsyncClient, seed_explorer_data: dict):
    """
    Direct verification of Milestone 8 Specification 31:
    - Invoices tab shows Northstar company, NOS-2026-0947, 2026-09-20, MYR, 7211.59, 4 items
    - Search 'Northstar' finds invoice
    - Search 'NOS-2026-0947' finds invoice
    - Line Items tab displays:
      1. Ergonomic Office Chair — Model E7 (Qty 6, Price 689.00, Tax 8%, Amount 4134.00)
      2. Adjustable Monitor Arm — Dual Display (Qty 6, Price 249.00, Tax 8%, Amount 1494.00)
      3. Wireless Keyboard & Mouse Set (Qty 6, Price 129.90, Tax 8%, Amount 779.40)
      4. Cable Management Tray (Qty 6, Price 45.00, Tax 8%, Amount 270.00)
    - Invoice detail displays due_date, sub_total, tax_amount in custom_fields
    """
    # 1. Invoice list verification
    inv_res = await client.get("/api/v1/data/invoices")
    assert inv_res.status_code == 200
    inv_data = inv_res.json()
    northstar_inv = next(i for i in inv_data["items"] if i["invoice_number"] == "NOS-2026-0947")
    assert northstar_inv["company_name"] == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert northstar_inv["invoice_date"] == "2026-09-20"
    assert northstar_inv["currency"] == "MYR"
    assert float(northstar_inv["total_amount"]) == 7211.59
    assert northstar_inv["line_item_count"] == 4

    # 2. Search verification
    s_comp = await client.get("/api/v1/data/invoices?search=Northstar")
    assert s_comp.status_code == 200
    assert s_comp.json()["items"][0]["invoice_number"] == "NOS-2026-0947"

    s_num = await client.get("/api/v1/data/invoices?search=NOS-2026-0947")
    assert s_num.status_code == 200
    assert s_num.json()["items"][0]["invoice_number"] == "NOS-2026-0947"

    # 3. Line items tab verification
    li_res = await client.get("/api/v1/data/line-items?search=NOS-2026-0947&sort_by=source_row_number&sort_order=asc")
    assert li_res.status_code == 200
    li_items = li_res.json()["items"]
    assert len(li_items) == 4

    expected_items = [
        ("Ergonomic Office Chair — Model E7", Decimal("6.0000"), Decimal("689.00"), Decimal("0.0800"), Decimal("4134.00")),
        ("Adjustable Monitor Arm — Dual Display", Decimal("6.0000"), Decimal("249.00"), Decimal("0.0800"), Decimal("1494.00")),
        ("Wireless Keyboard & Mouse Set", Decimal("6.0000"), Decimal("129.90"), Decimal("0.0800"), Decimal("779.40")),
        ("Cable Management Tray", Decimal("6.0000"), Decimal("45.00"), Decimal("0.0800"), Decimal("270.00")),
    ]

    for item, (exp_desc, exp_qty, exp_price, exp_tax, exp_amt) in zip(li_items, expected_items):
        assert item["description"] == exp_desc
        assert Decimal(str(item["quantity"])) == exp_qty
        assert Decimal(str(item["unit_price"])) == exp_price
        assert Decimal(str(item["tax_rate"])) == exp_tax
        assert Decimal(str(item["amount"])) == exp_amt

    # 4. Detail modal verification
    detail_res = await client.get(f"/api/v1/data/invoices/{northstar_inv['id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["custom_fields"]["due_date"] == "2026-10-20"
    assert detail["custom_fields"]["sub_total"] == "6677.40"
    assert detail["custom_fields"]["tax_amount"] == "534.19"
