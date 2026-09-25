"""
tests/unit/test_line_item_footer_detection.py — Regression tests for M7.5 line-item
footer/summary row detection.

Covers the 7 regression scenarios (A–G) identified during manual QA:

A) Footer label ("Subtotal") in Tax column → terminates extraction
B) "Tax (8%)" in Tax column → must not become a line item
C) "TOTAL" in Tax column → must not become a line item
D) "Total Care Cleaning Kit" (with qty/price) → valid line item, no false termination
E) "Tax Preparation Service" (with qty/price) → valid line item, no false termination
F) Quantity = "abc" → extraction error, NOT SUCCESS
G) tax_rate = "hello" → extraction error, NOT SUCCESS
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from app.services.extractor import extract_from_file


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_line_item_mappings() -> list[SimpleNamespace]:
    """Standard 5-column line item mappings (desc, qty, price, tax_rate, amount)."""
    return [
        SimpleNamespace(field_name="desc", target_field="description", mapping_group="line_item", mapping_type="column", column_ref="A", is_required=True, data_type="text"),
        SimpleNamespace(field_name="qty", target_field="quantity", mapping_group="line_item", mapping_type="column", column_ref="B", is_required=True, data_type="decimal"),
        SimpleNamespace(field_name="price", target_field="unit_price", mapping_group="line_item", mapping_type="column", column_ref="C", is_required=True, data_type="decimal"),
        SimpleNamespace(field_name="tax_rate", target_field="tax_rate", mapping_group="line_item", mapping_type="column", column_ref="D", is_required=False, data_type="decimal"),
        SimpleNamespace(field_name="amount", target_field="amount", mapping_group="line_item", mapping_type="column", column_ref="E", is_required=True, data_type="decimal"),
    ]


def _make_template(extra_header_mappings=None, extra_line_mappings=None):
    """Build a template namespace with header + line-item mappings."""
    header_mappings = [
        SimpleNamespace(field_name="supplier", target_field="company_name", mapping_group="header", mapping_type="cell", cell_ref="A1", is_required=True, data_type="text"),
        SimpleNamespace(field_name="inv_no", target_field="invoice_number", mapping_group="header", mapping_type="cell", cell_ref="F5", is_required=True, data_type="text"),
    ]
    if extra_header_mappings:
        header_mappings.extend(extra_header_mappings)

    line_mappings = _make_line_item_mappings()
    if extra_line_mappings:
        line_mappings.extend(extra_line_mappings)

    return SimpleNamespace(
        name="Footer Detection Test",
        template_type="invoice",
        worksheet="Invoice",
        header_row=10,
        data_start_row=11,
        date_format=None,
        field_mappings=header_mappings + line_mappings,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def footer_in_tax_column_file(tmp_path: Path) -> Path:
    """
    Scenarios A/B/C: Footer labels appear in the TAX RATE column (D), not
    in the description column (A).  Columns A-C of footer rows are blank.

    Row 11-14: 4 valid line items
    Row 15: blank
    Row 16: D="Subtotal", E=6677.40       ← footer (A)
    Row 17: D="Tax (8%)", E=534.19        ← footer (B)
    Row 18: D="TOTAL",    E=7211.59       ← footer (C)
    """
    fp = tmp_path / "footer_tax_col.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"

    ws["A1"] = "NORTHSTAR OFFICE SOLUTIONS"
    ws["F5"] = "NOS-2026-0947"

    # Table headers
    ws["A10"] = "Description"
    ws["B10"] = "Qty"
    ws["C10"] = "Unit Price"
    ws["D10"] = "Tax Rate"
    ws["E10"] = "Amount"

    # 4 valid line items
    for i, (desc, qty, price, tax, amt) in enumerate([
        ("Ergonomic Office Chair", 6, 689.00, "8%", 4134.00),
        ("Standing Desk Pro", 3, 1200.00, "8%", 3600.00),
        ("Monitor Arm", 10, 89.90, "8%", 899.00),
        ("Cable Management Tray", 6, 45.00, "8%", 270.00),
    ], start=11):
        ws[f"A{i}"] = desc
        ws[f"B{i}"] = qty
        ws[f"C{i}"] = price
        ws[f"D{i}"] = tax
        ws[f"E{i}"] = amt

    # Row 15: blank

    # Footer rows — labels in column D (the tax_rate column)
    ws["D16"] = "Subtotal"
    ws["E16"] = 6677.40

    ws["D17"] = "Tax (8%)"
    ws["E17"] = 534.19

    ws["D18"] = "TOTAL"
    ws["E18"] = 7211.59

    wb.save(fp)
    wb.close()
    return fp


@pytest.fixture
def product_names_with_keywords_file(tmp_path: Path) -> Path:
    """
    Scenarios D/E: Product names contain words like "Total" and "Tax" but are
    legitimate data rows with valid qty/price.  Must NOT terminate extraction.
    """
    fp = tmp_path / "keyword_products.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"

    ws["A1"] = "SUPPLIER CO"
    ws["F5"] = "INV-001"

    ws["A10"] = "Description"
    ws["B10"] = "Qty"
    ws["C10"] = "Unit Price"
    ws["D10"] = "Tax Rate"
    ws["E10"] = "Amount"

    # Row 11: Normal item
    ws["A11"] = "Ergonomic Office Chair"
    ws["B11"] = 6
    ws["C11"] = 689.00
    ws["D11"] = "8%"
    ws["E11"] = 4134.00

    # Row 12: "Total Care Cleaning Kit" — Scenario D
    ws["A12"] = "Total Care Cleaning Kit"
    ws["B12"] = 4
    ws["C12"] = 25.00
    ws["D12"] = "8%"
    ws["E12"] = 108.00

    # Row 13: "Tax Preparation Service" — Scenario E
    ws["A13"] = "Tax Preparation Service"
    ws["B13"] = 2
    ws["C13"] = 500.00
    ws["D13"] = "6%"
    ws["E13"] = 1060.00

    # Row 14: Normal item
    ws["A14"] = "Cable Management Tray"
    ws["B14"] = 6
    ws["C14"] = 45.00
    ws["D14"] = "8%"
    ws["E14"] = 270.00

    # Row 15: blank

    # Footer
    ws["A16"] = "Subtotal"
    ws["E16"] = 5572.00

    wb.save(fp)
    wb.close()
    return fp


@pytest.fixture
def invalid_numeric_fields_file(tmp_path: Path) -> Path:
    """
    Scenarios F/G: Valid product names but invalid non-numeric content in
    numeric fields.  These rows are NOT footer rows, they are data entry
    errors that must produce extraction errors.
    """
    fp = tmp_path / "invalid_numerics.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"

    ws["A1"] = "SUPPLIER CO"
    ws["F5"] = "INV-002"

    ws["A10"] = "Description"
    ws["B10"] = "Qty"
    ws["C10"] = "Unit Price"
    ws["D10"] = "Tax Rate"
    ws["E10"] = "Amount"

    # Row 11: Normal valid item
    ws["A11"] = "Ergonomic Office Chair"
    ws["B11"] = 6
    ws["C11"] = 689.00
    ws["D11"] = "8%"
    ws["E11"] = 4134.00

    # Row 12: Scenario F — Quantity = "abc" (invalid)
    ws["A12"] = "Office Chair"
    ws["B12"] = "abc"
    ws["C12"] = 689.00
    ws["D12"] = "8%"
    ws["E12"] = 4134.00

    # Row 13: Scenario G — tax_rate = "hello" (invalid)
    ws["A13"] = "Office Chair"
    ws["B13"] = 6
    ws["C13"] = 689.00
    ws["D13"] = "hello"
    ws["E13"] = 4134.00

    # Row 14: blank → terminates

    wb.save(fp)
    wb.close()
    return fp


# ── Scenario A: Footer "Subtotal" in Tax column terminates extraction ────────


class TestScenarioA_FooterInTaxColumn:
    """Footer label "Subtotal" in column D (tax_rate) with blank qty/price → terminate."""

    def test_extraction_yields_exactly_4_items(self, footer_in_tax_column_file: Path):
        template = _make_template()
        res = extract_from_file(footer_in_tax_column_file, template)

        assert res.has_line_items is True
        assert len(res.line_items) == 4, (
            f"Expected 4 line items but got {len(res.line_items)}. "
            f"Footer rows in column D were not properly detected."
        )

    def test_no_line_item_has_subtotal_value(self, footer_in_tax_column_file: Path):
        template = _make_template()
        res = extract_from_file(footer_in_tax_column_file, template)

        for item in res.line_items:
            fields = {f.field_name: f for f in item.fields}
            tax_field = fields.get("tax_rate")
            if tax_field and tax_field.normalized_value is not None:
                assert str(tax_field.normalized_value).lower() != "subtotal", (
                    f"Row {item.row_number}: tax_rate should never be 'Subtotal'"
                )


# ── Scenario B: "Tax (8%)" in Tax column must not become a line item ─────────


class TestScenarioB_TaxParenthetical:
    """Footer label "Tax (8%)" in column D must NOT become a line item."""

    def test_tax_8pct_row_excluded(self, footer_in_tax_column_file: Path):
        template = _make_template()
        res = extract_from_file(footer_in_tax_column_file, template)

        row_numbers = [item.row_number for item in res.line_items]
        assert 17 not in row_numbers, (
            "Row 17 ('Tax (8%)' in tax column) should NOT be extracted as a line item"
        )


# ── Scenario C: "TOTAL" in Tax column must not become a line item ────────────


class TestScenarioC_TotalInTaxColumn:
    """Footer label "TOTAL" in column D must NOT become a line item."""

    def test_total_row_excluded(self, footer_in_tax_column_file: Path):
        template = _make_template()
        res = extract_from_file(footer_in_tax_column_file, template)

        row_numbers = [item.row_number for item in res.line_items]
        assert 18 not in row_numbers, (
            "Row 18 ('TOTAL' in tax column) should NOT be extracted as a line item"
        )


# ── Scenario D: "Total Care Cleaning Kit" must NOT terminate ─────────────────


class TestScenarioD_ProductNameWithTotal:
    """'Total Care Cleaning Kit' has valid qty/price — must be kept as a line item."""

    def test_total_care_cleaning_kit_preserved(self, product_names_with_keywords_file: Path):
        template = _make_template()
        res = extract_from_file(product_names_with_keywords_file, template)

        # Row 12 should be present
        row12 = [item for item in res.line_items if item.row_number == 12]
        assert len(row12) == 1, (
            "Row 12 ('Total Care Cleaning Kit') should be extracted as a valid line item"
        )

        fields = {f.field_name: f.normalized_value for f in row12[0].fields}
        assert fields["desc"] == "Total Care Cleaning Kit"
        assert fields["qty"] == Decimal("4")
        assert fields["price"] == Decimal("25.00")


# ── Scenario E: "Tax Preparation Service" must NOT terminate ─────────────────


class TestScenarioE_ProductNameWithTax:
    """'Tax Preparation Service' has valid qty/price — must be kept as a line item."""

    def test_tax_preparation_service_preserved(self, product_names_with_keywords_file: Path):
        template = _make_template()
        res = extract_from_file(product_names_with_keywords_file, template)

        # Row 13 should be present
        row13 = [item for item in res.line_items if item.row_number == 13]
        assert len(row13) == 1, (
            "Row 13 ('Tax Preparation Service') should be extracted as a valid line item"
        )

        fields = {f.field_name: f.normalized_value for f in row13[0].fields}
        assert fields["desc"] == "Tax Preparation Service"
        assert fields["qty"] == Decimal("2")
        assert fields["price"] == Decimal("500.00")

    def test_all_4_items_extracted(self, product_names_with_keywords_file: Path):
        template = _make_template()
        res = extract_from_file(product_names_with_keywords_file, template)
        assert len(res.line_items) == 4, (
            f"Expected 4 line items but got {len(res.line_items)}. "
            f"Product names with footer keywords should not cause early termination."
        )


# ── Scenario F: Invalid quantity "abc" → extraction error ────────────────────


class TestScenarioF_InvalidQuantity:
    """Quantity = 'abc' on a valid product → normalization error, NOT success."""

    def test_abc_quantity_produces_error(self, invalid_numeric_fields_file: Path):
        template = _make_template()
        res = extract_from_file(invalid_numeric_fields_file, template)

        # Row 12 should still be extracted (it's not a footer row)
        row12 = [item for item in res.line_items if item.row_number == 12]
        assert len(row12) == 1, "Row 12 should be extracted even with invalid data"

        fields = {f.field_name: f for f in row12[0].fields}
        qty_field = fields["qty"]
        assert qty_field.status == "error", (
            f"Expected qty status='error' for value 'abc', got '{qty_field.status}'"
        )
        assert qty_field.error_message is not None

    def test_abc_quantity_row_has_errors(self, invalid_numeric_fields_file: Path):
        template = _make_template()
        res = extract_from_file(invalid_numeric_fields_file, template)

        row12 = [item for item in res.line_items if item.row_number == 12]
        assert row12[0].has_errors is True


# ── Scenario G: Invalid tax_rate "hello" → extraction error ──────────────────


class TestScenarioG_InvalidTaxRate:
    """tax_rate = 'hello' on a valid product → normalization error, NOT success."""

    def test_hello_tax_rate_produces_error(self, invalid_numeric_fields_file: Path):
        template = _make_template()
        res = extract_from_file(invalid_numeric_fields_file, template)

        # Row 13 should still be extracted (it's not a footer row)
        row13 = [item for item in res.line_items if item.row_number == 13]
        assert len(row13) == 1, "Row 13 should be extracted even with invalid tax_rate"

        fields = {f.field_name: f for f in row13[0].fields}
        tax_field = fields["tax_rate"]
        assert tax_field.status == "error", (
            f"Expected tax_rate status='error' for value 'hello', got '{tax_field.status}'"
        )
        assert tax_field.error_message is not None

    def test_hello_tax_rate_row_has_errors(self, invalid_numeric_fields_file: Path):
        template = _make_template()
        res = extract_from_file(invalid_numeric_fields_file, template)

        row13 = [item for item in res.line_items if item.row_number == 13]
        assert row13[0].has_errors is True


# ── Combined integration: full Northstar-style invoice ───────────────────────


class TestNorthstarStyleInvoice:
    """
    End-to-end test replicating the exact Northstar invoice layout from the
    bug report: footer labels in column D (tax_rate), blank columns A-C.
    """

    @pytest.fixture
    def northstar_file(self, tmp_path: Path) -> Path:
        fp = tmp_path / "northstar_invoice.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Invoice"

        ws["A1"] = "NORTHSTAR OFFICE SOLUTIONS"
        ws["A6"] = "Customer Corp"
        ws["F5"] = "NOS-2026-0947"
        ws["F6"] = "2026-09-20"
        ws["F8"] = "MYR"

        ws["A10"] = "Description"
        ws["B10"] = "Qty"
        ws["C10"] = "Unit Price"
        ws["D10"] = "Tax Rate"
        ws["E10"] = "Amount"

        # Row 11-14: 4 products (including "Total" and "Tax" in names)
        ws["A11"] = "Ergonomic Office Chair"
        ws["B11"] = 6
        ws["C11"] = 689
        ws["D11"] = "8%"
        ws["E11"] = 4134

        ws["A12"] = "Total Care Cleaning Kit"
        ws["B12"] = 6
        ws["C12"] = 249
        ws["D12"] = "8%"
        ws["E12"] = 1494

        ws["A13"] = "Tax Preparation Service"
        ws["B13"] = 6
        ws["C13"] = 129.90
        ws["D13"] = "8%"
        ws["E13"] = 779.40

        ws["A14"] = "Cable Management Tray"
        ws["B14"] = 6
        ws["C14"] = 45
        ws["D14"] = "8%"
        ws["E14"] = 270

        # Row 15: blank

        # Footer rows — labels in D column, A-C blank
        ws["D16"] = "Subtotal"
        ws["E16"] = 6677.40

        ws["D17"] = "Tax (8%)"
        ws["E17"] = 534.192

        ws["D18"] = "TOTAL"
        ws["E18"] = 7211.592

        wb.save(fp)
        wb.close()
        return fp

    def test_exactly_4_line_items(self, northstar_file: Path):
        template = _make_template()
        res = extract_from_file(northstar_file, template)

        assert len(res.line_items) == 4, (
            f"Northstar invoice: expected 4 line items, got {len(res.line_items)}. "
            f"Row numbers: {[li.row_number for li in res.line_items]}"
        )

    def test_no_footer_row_numbers(self, northstar_file: Path):
        template = _make_template()
        res = extract_from_file(northstar_file, template)

        row_numbers = {item.row_number for item in res.line_items}
        assert 16 not in row_numbers, "Subtotal row (16) leaked into line items"
        assert 17 not in row_numbers, "Tax (8%) row (17) leaked into line items"
        assert 18 not in row_numbers, "TOTAL row (18) leaked into line items"

    def test_product_names_with_keywords_preserved(self, northstar_file: Path):
        template = _make_template()
        res = extract_from_file(northstar_file, template)

        descs = []
        for item in res.line_items:
            fields = {f.field_name: f.normalized_value for f in item.fields}
            descs.append(fields.get("desc"))

        assert "Total Care Cleaning Kit" in descs, (
            "'Total Care Cleaning Kit' should be extracted as a valid line item"
        )
        assert "Tax Preparation Service" in descs, (
            "'Tax Preparation Service' should be extracted as a valid line item"
        )

    def test_no_errors_on_valid_items(self, northstar_file: Path):
        template = _make_template()
        res = extract_from_file(northstar_file, template)

        for item in res.line_items:
            assert not item.has_errors, (
                f"Row {item.row_number} should have no errors, but has: "
                f"{[e.message for e in item.errors]}"
            )
