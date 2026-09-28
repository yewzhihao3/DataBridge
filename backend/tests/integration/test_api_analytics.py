"""M10 regression tests: persisted values, currency isolation and SQL scope."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from app.models.invoice import ImportBatch, InvoiceLineItem, InvoiceRecord
from app.models.source_file import SourceFile
from app.models.template import Template
from app.services.analytics_service import money_sum
from tests.integration.test_m75_northstar_persistence_audit import northstar_template_and_file


@pytest.fixture
def add_invoice(db_session):
    source = SourceFile(original_name="analytics.xlsx", stored_filename="analytics.xlsx", file_size=1, checksum="a" * 64)
    template = Template(name="Analytics dataset", template_type="dataset")
    db_session.add_all([source, template])
    db_session.flush()
    sequence = 0

    def add(total="100", currency="MYR", day="2026-09-20", company="Acme", amounts=(), description="Chair", deleted=False):
        nonlocal sequence
        sequence += 1
        batch = ImportBatch(source_file_id=source.id, template_id=template.id, is_deleted=deleted)
        record = InvoiceRecord(
            company_name=company, invoice_number=f"INV-{sequence}",
            invoice_date=date.fromisoformat(day) if day else None,
            total_amount=Decimal(total) if total is not None else None,
            currency=currency, source_worksheet="Data", raw_data="{}",
        )
        batch.invoice_records.append(record)
        for i, amount in enumerate(amounts, 1):
            record.line_items.append(InvoiceLineItem(
                source_row_number=i, description=description,
                quantity=Decimal("5"), unit_price=Decimal("7"),
                amount=Decimal(amount) if amount is not None else None,
            ))
        db_session.add(batch)
        db_session.commit()
        return record
    return add


async def get(client, **params):
    response = await client.get("/api/v1/analytics/dashboard", params={"currency": "MYR", **params})
    assert response.status_code == 200, response.text
    return response.json()


async def test_empty_database(client):
    data = await get(client)
    assert data["summary"] == {
        "invoice_count": 0, "invoices_with_total": 0, "invoices_without_total": 0,
        "invoices_without_date": 0, "total_invoice_value": None,
        "average_invoice_value": None, "line_item_count": 0, "line_items_with_amount": 0,
    }
    assert data["invoice_value_over_time"] == data["company_values"] == data["line_item_values"] == []
    options = (await client.get("/api/v1/analytics/filter-options")).json()
    assert options == {"currencies": [], "has_unspecified_currency": False, "companies": [], "date_from": None, "date_to": None}


async def test_invoice_totals_never_multiplied_by_children(client, add_invoice):
    add_invoice("100", amounts=["1"] * 4)
    add_invoice("200", amounts=["2"] * 3)
    data = await get(client)
    summary = data["summary"]
    assert summary["invoice_count"] == 2
    assert summary["line_item_count"] == 7
    assert summary["total_invoice_value"] == "300.00"
    assert summary["average_invoice_value"] == "150.00"
    assert data["company_values"][0]["invoice_value"] == "300.00"
    assert data["invoice_value_over_time"][0]["invoice_value"] == "300.00"
    assert data["line_item_values"][0]["amount"] == "10.00"


async def test_mixed_currencies_are_separate(client, add_invoice):
    add_invoice("100", amounts=["10"])
    add_invoice("200", amounts=["20"])
    add_invoice("500", currency="USD", amounts=["50"])
    myr = await get(client)
    usd = await get(client, currency="USD")
    assert myr["summary"]["total_invoice_value"] == "300.00"
    assert usd["summary"]["total_invoice_value"] == "500.00"
    assert usd["summary"]["invoice_count"] == 1
    assert usd["line_item_values"][0]["amount"] == "50.00"
    unspecified = (await client.get("/api/v1/analytics/dashboard")).json()
    assert unspecified["summary"]["invoice_count"] == 0
    assert unspecified["summary"]["total_invoice_value"] is None


async def test_unknown_currencies_have_counts_but_no_combined_money(client, add_invoice):
    add_invoice("100", currency=None, amounts=["5"])
    add_invoice("200", currency=" ", amounts=["7"])
    add_invoice("500", currency="MYR")
    data = (await client.get("/api/v1/analytics/dashboard")).json()
    assert data["filters"]["currency"] is None
    assert data["monetary_values_available"] is False
    assert data["summary"]["invoice_count"] == 2
    assert data["summary"]["line_item_count"] == 2
    assert data["summary"]["invoices_with_total"] == 2
    assert data["summary"]["total_invoice_value"] is None
    assert data["summary"]["average_invoice_value"] is None
    assert data["company_values"] == data["line_item_values"] == []
    assert data["invoice_value_over_time"][0]["invoice_value"] is None


async def test_null_totals_count_without_affecting_average(client, add_invoice):
    add_invoice("100")
    add_invoice("200")
    add_invoice(None)
    data = await get(client)
    assert data["summary"]["invoice_count"] == 3
    assert data["summary"]["invoices_with_total"] == 2
    assert data["summary"]["invoices_without_total"] == 1
    assert data["summary"]["average_invoice_value"] == "150.00"
    assert data["company_values"][0]["invoice_count"] == 3
    assert data["company_values"][0]["invoices_with_total"] == 2
    assert data["invoice_value_over_time"][0]["invoice_count"] == 3


async def test_all_unknown_values_remain_null(client, add_invoice):
    add_invoice(None, amounts=[None, None])
    data = await get(client)
    assert data["summary"]["total_invoice_value"] is None
    assert data["summary"]["average_invoice_value"] is None
    assert data["summary"]["line_item_count"] == 2
    assert data["summary"]["line_items_with_amount"] == 0
    assert data["company_values"] == data["line_item_values"] == []
    assert data["invoice_value_over_time"][0]["invoice_value"] is None


async def test_zero_and_negative_are_known_values(client, add_invoice):
    add_invoice("0", amounts=["0"])
    add_invoice("-20", amounts=["-5"])
    data = await get(client)
    assert data["summary"]["total_invoice_value"] == "-20.00"
    assert data["summary"]["average_invoice_value"] == "-10.00"
    assert data["summary"]["invoices_with_total"] == 2
    assert data["line_item_values"][0]["amount"] == "-5.00"


async def test_zero_only_is_not_missing(client, add_invoice):
    add_invoice("0", amounts=["0"])
    data = await get(client)
    assert data["summary"]["total_invoice_value"] == "0.00"
    assert data["summary"]["average_invoice_value"] == "0.00"
    assert data["line_item_values"][0]["amount"] == "0.00"


async def test_decimal_sum_and_half_up_average(client, add_invoice):
    add_invoice("0.10")
    add_invoice("0.20")
    add_invoice("779.40")
    data = await get(client)
    assert data["summary"]["total_invoice_value"] == "779.70"
    assert data["summary"]["average_invoice_value"] == "259.90"
    add_invoice("0.01", company="Rounding")
    add_invoice("0.00", company="Rounding")
    assert (await get(client, company="Rounding"))["summary"]["average_invoice_value"] == "0.01"


async def test_sqlite_values_match_canonical_two_decimal_scale(client, add_invoice):
    add_invoice("7211.592", amounts=["779.404"])
    data = await get(client)
    assert data["summary"]["total_invoice_value"] == "7211.59"
    assert data["line_item_values"][0]["amount"] == "779.40"


async def test_inclusive_dates_and_null_dates(client, add_invoice):
    for day in ["2026-08-31", "2026-09-01", "2026-09-30", "2026-10-01", None]:
        add_invoice("100", day=day, amounts=["10"])
    data = await get(client, date_from="2026-09-01", date_to="2026-09-30")
    assert data["summary"]["invoice_count"] == 2
    assert data["summary"]["total_invoice_value"] == "200.00"
    assert data["summary"]["line_item_count"] == 2
    assert data["line_item_values"][0]["amount"] == "20.00"
    assert data["company_values"][0]["invoice_count"] == 2
    assert data["invoice_value_over_time"][0]["period"] == "2026-09"
    all_data = await get(client)
    assert all_data["summary"]["invoice_count"] == 5
    assert all_data["summary"]["invoices_without_date"] == 1
    assert sum(p["invoice_count"] for p in all_data["invoice_value_over_time"]) == 4


@pytest.mark.parametrize("params", [{"date_from": "2026-09-20"}, {"date_to": "2026-09-20"}])
async def test_one_sided_date_boundaries(client, add_invoice, params):
    add_invoice(day="2026-09-19")
    add_invoice(day="2026-09-20")
    add_invoice(day="2026-09-21")
    assert (await get(client, **params))["summary"]["invoice_count"] == 2


async def test_company_substring_and_all_parent_filters(client, add_invoice):
    add_invoice("10", company="Northstar Office", amounts=["1"])
    add_invoice("20", company="NORTHSTAR Branch", amounts=["2"])
    add_invoice("900", company="Other", amounts=["90"])
    add_invoice("800", company="Northstar USD", currency="USD", amounts=["80"])
    data = await get(client, company="northstar")
    assert data["summary"]["invoice_count"] == 2
    assert data["summary"]["total_invoice_value"] == "30.00"
    assert data["line_item_values"][0]["amount"] == "3.00"
    assert len(data["company_values"]) == 2


async def test_deleted_data_excluded_everywhere(client, add_invoice):
    add_invoice("100", amounts=["10"])
    add_invoice("9999", currency="EUR", company="Deleted Only", day="1990-01-01", amounts=["999"], deleted=True)
    add_invoice("9999", day="2099-01-01", amounts=["999"], deleted=True)
    data = await get(client)
    assert data["summary"]["invoice_count"] == data["summary"]["line_item_count"] == 1
    assert data["summary"]["total_invoice_value"] == "100.00"
    assert data["company_values"][0]["invoice_value"] == "100.00"
    assert data["line_item_values"][0]["amount"] == "10.00"
    assert len(data["invoice_value_over_time"]) == 1
    options = (await client.get("/api/v1/analytics/filter-options")).json()
    assert options["currencies"] == ["MYR"]
    assert options["companies"] == ["Acme"]
    assert options["date_from"] == options["date_to"] == "2026-09-20"


async def test_currency_whitespace_case_normalization_and_options(client, add_invoice):
    add_invoice("100", currency=" myr ")
    add_invoice("200", currency="MYR")
    add_invoice("5", currency=None)
    assert (await get(client, currency=" myr "))["summary"]["total_invoice_value"] == "300.00"
    options = (await client.get("/api/v1/analytics/filter-options")).json()
    assert options["currencies"] == ["MYR"]
    assert options["has_unspecified_currency"] is True


async def test_monthly_grouping_across_years_and_unknown_month_values(client, add_invoice):
    add_invoice("20", day="2025-12-31")
    add_invoice("30", day="2026-01-01")
    add_invoice(None, day="2026-01-15")
    add_invoice(None, day="2026-03-01")
    data = await get(client)
    assert data["grouping"] == "month"
    assert data["invoice_value_over_time"] == [
        {"period": "2025-12", "invoice_count": 1, "invoices_with_total": 1, "invoice_value": "20.00"},
        {"period": "2026-01", "invoice_count": 2, "invoices_with_total": 1, "invoice_value": "30.00"},
        {"period": "2026-03", "invoice_count": 1, "invoices_with_total": 0, "invoice_value": None},
    ]


async def test_all_dates_missing_keeps_kpis_but_no_trend(client, add_invoice):
    add_invoice("50", day=None)
    data = await get(client)
    assert data["summary"]["total_invoice_value"] == "50.00"
    assert data["summary"]["invoices_without_date"] == 1
    assert data["invoice_value_over_time"] == []


async def test_rankings_descending_limit_and_ties(client, add_invoice):
    for i in range(12):
        add_invoice(str(i), company=f"Company {i:02d}", amounts=[str(i)], description=f"Description {i:02d}")
    add_invoice("11", company="Company AA", amounts=["11"], description="Description AA")
    data = await get(client)
    assert len(data["company_values"]) == len(data["line_item_values"]) == 10
    assert [r["company_name"] for r in data["company_values"][:3]] == ["Company 11", "Company AA", "Company 10"]
    assert [r["description"] for r in data["line_item_values"][:3]] == ["Description 11", "Description AA", "Description 10"]


async def test_line_description_normalization_null_amount_not_derived(client, add_invoice):
    add_invoice("100", amounts=["10", None], description=" Chair ")
    add_invoice("200", amounts=["20"], description="Chair")
    add_invoice("300", amounts=[None], description="No amount")
    data = await get(client)
    assert data["line_item_values"] == [{"description": "Chair", "line_item_count": 3, "line_items_with_amount": 2, "amount": "30.00"}]
    assert data["summary"]["line_item_count"] == 4


async def test_missing_description_and_legacy_company_preserved(client, add_invoice):
    add_invoice("10", company="Unknown Company", amounts=["2"], description=None)
    add_invoice("20", company="Unknown Company", amounts=["3"], description=" ")
    data = await get(client)
    assert data["company_values"][0]["company_name"] == "Unknown Company"
    assert data["line_item_values"][0]["description"] is None
    assert data["line_item_values"][0]["amount"] == "5.00"


@pytest.mark.parametrize("params", [
    {"date_from": "2026-10-01", "date_to": "2026-09-01"},
    {"date_from": "bad-date"}, {"date_to": "2026-02-30"},
])
async def test_invalid_dates_rejected(client, params):
    response = await client.get("/api/v1/analytics/dashboard", params=params)
    assert response.status_code == 422


async def test_no_matches(client, add_invoice):
    add_invoice()
    data = await get(client, company="Absent")
    assert data["summary"]["invoice_count"] == 0
    assert data["summary"]["total_invoice_value"] is None
    assert data["company_values"] == []


async def test_fresh_northstar_import_dashboard(client, northstar_template_and_file):
    file_id, template_id = northstar_template_and_file
    response = await client.post("/api/v1/imports/confirm", json={"file_id": file_id, "template_id": template_id, "acknowledge_warnings": True})
    assert response.status_code == 201
    data = await get(client, company="NORTHSTAR", date_from="2026-09-20", date_to="2026-09-20")
    assert data["summary"]["invoice_count"] == 1
    assert data["summary"]["line_item_count"] == 4
    assert data["summary"]["total_invoice_value"] == data["summary"]["average_invoice_value"] == "7211.59"
    assert data["company_values"][0]["company_name"] == "NORTHSTAR OFFICE SOLUTIONS SDN. BHD."
    assert data["company_values"][0]["invoice_value"] == "7211.59"
    assert [r["amount"] for r in data["line_item_values"]] == ["4134.00", "1494.00", "779.40", "270.00"]


def test_money_expression_compiles_for_postgresql():
    expression = str(money_sum(InvoiceRecord.total_amount).compile(dialect=postgresql.dialect()))
    assert "sum(CAST(round(" in expression
    assert "BIGINT" in expression
