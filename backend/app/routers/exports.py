"""
app/routers/exports.py — Endpoints for Export Center (CSV and XLSX database exports).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.tenancy import get_tenant_db as get_db
from app.schemas.export import ExportSummaryResponse
from app.security import audit
from app.services.export_builder import (
    build_invoices_export_query,
    build_line_items_export_query,
    discover_custom_keys,
    friendly_label,
    generate_invoices_csv,
    generate_invoices_xlsx,
    generate_line_items_csv,
    generate_line_items_xlsx,
)

router = APIRouter(prefix="/api/v1/exports", tags=["Exports"])


# ── Export Summary Endpoint ───────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=ExportSummaryResponse,
    summary="Get export metadata (matching record count, discovered columns)",
)
def get_export_summary(
    dataset: Literal["invoices", "line-items"] = Query(..., description="Dataset type to export"),
    search: str | None = Query(None, description="Search term"),
    company: str | None = Query(None, description="Company filter"),
    currency: str | None = Query(None, description="Currency filter"),
    date_from: date | None = Query(None, description="Date from"),
    date_to: date | None = Query(None, description="Date to"),
    has_line_items: bool | None = Query(None, description="Line item presence filter (invoices only)"),
    db: Session = Depends(get_db),
) -> ExportSummaryResponse:
    """
    Returns total matching record count and discovered column headers for the selected dataset and filters.
    """
    if dataset == "invoices":
        query = build_invoices_export_query(
            db=db,
            search=search,
            company=company,
            currency=currency,
            date_from=date_from,
            date_to=date_to,
            has_line_items=has_line_items,
        )
        total = query.count()

        # To discover custom fields without loading all records, sample first 100 or load custom_fields
        custom_fields_query = query.with_entities(query.column_descriptions[0]["expr"].custom_fields).all()
        custom_keys = discover_custom_keys([row[0] for row in custom_fields_query if row])

        columns = [
            "Company Name",
            "Invoice Number",
            "Invoice Date",
            "Currency",
            "Total Amount",
        ]
        for ck in custom_keys:
            columns.append(friendly_label(ck))
        columns.extend(["Source File", "Template Name", "Worksheet", "Imported At"])

        return ExportSummaryResponse(
            dataset="invoices",
            total_records=total,
            column_count=len(columns),
            columns=columns,
        )

    else:
        query = build_line_items_export_query(
            db=db,
            search=search,
            company=company,
            currency=currency,
            date_from=date_from,
            date_to=date_to,
        )
        total = query.count()

        custom_fields_query = query.with_entities(query.column_descriptions[0]["expr"].custom_fields).all()
        custom_keys = discover_custom_keys([row[0] for row in custom_fields_query if row])

        columns = [
            "Company Name",
            "Invoice Number",
            "Invoice Date",
            "Currency",
            "Description",
            "Quantity",
            "Unit Price",
            "Tax Rate",
            "Tax Amount",
            "Amount",
        ]
        for ck in custom_keys:
            columns.append(friendly_label(ck))
        columns.extend(["Source File", "Source Row"])

        return ExportSummaryResponse(
            dataset="line-items",
            total_records=total,
            column_count=len(columns),
            columns=columns,
        )


# ── Invoices Exports ──────────────────────────────────────────────────────────


@router.get(
    "/invoices.csv",
    summary="Export invoice records as CSV",
)
def export_invoices_csv(
    search: str | None = Query(None, description="Search term"),
    company: str | None = Query(None, description="Company filter"),
    currency: str | None = Query(None, description="Currency filter"),
    date_from: date | None = Query(None, description="Date from"),
    date_to: date | None = Query(None, description="Date to"),
    has_line_items: bool | None = Query(None, description="Line item presence filter"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Exports all matching invoice records to a standardized UTF-8 BOM CSV file.
    """
    query = build_invoices_export_query(
        db=db,
        search=search,
        company=company,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        has_line_items=has_line_items,
    )
    records = query.all()

    csv_text = generate_invoices_csv(records)
    # Prefix with UTF-8 BOM for Microsoft Excel compatibility
    csv_bytes = "\ufeff".encode("utf-8") + csv_text.encode("utf-8")

    today_str = date.today().isoformat()
    filename = f"databridge_invoices_{today_str}.csv"

    audit(db, db.info["organization_id"], db.info["user_id"], "EXPORT_INVOICES" if "invoices" in filename else "EXPORT_LINE_ITEMS")
    db.commit()
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/invoices.xlsx",
    summary="Export invoice records as Excel (.xlsx)",
)
def export_invoices_xlsx(
    search: str | None = Query(None, description="Search term"),
    company: str | None = Query(None, description="Company filter"),
    currency: str | None = Query(None, description="Currency filter"),
    date_from: date | None = Query(None, description="Date from"),
    date_to: date | None = Query(None, description="Date to"),
    has_line_items: bool | None = Query(None, description="Line item presence filter"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Exports all matching invoice records to a styled Excel .xlsx spreadsheet.
    """
    query = build_invoices_export_query(
        db=db,
        search=search,
        company=company,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        has_line_items=has_line_items,
    )
    records = query.all()

    xlsx_bytes = generate_invoices_xlsx(records)

    today_str = date.today().isoformat()
    filename = f"databridge_invoices_{today_str}.xlsx"

    audit(db, db.info["organization_id"], db.info["user_id"], "EXPORT_INVOICES" if "invoices" in filename else "EXPORT_LINE_ITEMS")
    db.commit()
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ── Line Items Exports ────────────────────────────────────────────────────────


@router.get(
    "/line-items.csv",
    summary="Export flattened line items as CSV",
)
def export_line_items_csv(
    search: str | None = Query(None, description="Search term"),
    company: str | None = Query(None, description="Company filter"),
    currency: str | None = Query(None, description="Currency filter"),
    date_from: date | None = Query(None, description="Date from"),
    date_to: date | None = Query(None, description="Date to"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Exports all matching line items to a standardized UTF-8 BOM CSV file.
    """
    query = build_line_items_export_query(
        db=db,
        search=search,
        company=company,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )
    items = query.all()

    csv_text = generate_line_items_csv(items)
    csv_bytes = "\ufeff".encode("utf-8") + csv_text.encode("utf-8")

    today_str = date.today().isoformat()
    filename = f"databridge_line_items_{today_str}.csv"

    audit(db, db.info["organization_id"], db.info["user_id"], "EXPORT_INVOICES" if "invoices" in filename else "EXPORT_LINE_ITEMS")
    db.commit()
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/line-items.xlsx",
    summary="Export flattened line items as Excel (.xlsx)",
)
def export_line_items_xlsx(
    search: str | None = Query(None, description="Search term"),
    company: str | None = Query(None, description="Company filter"),
    currency: str | None = Query(None, description="Currency filter"),
    date_from: date | None = Query(None, description="Date from"),
    date_to: date | None = Query(None, description="Date to"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Exports all matching line items to a styled Excel .xlsx spreadsheet.
    """
    query = build_line_items_export_query(
        db=db,
        search=search,
        company=company,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )
    items = query.all()

    xlsx_bytes = generate_line_items_xlsx(items)

    today_str = date.today().isoformat()
    filename = f"databridge_line_items_{today_str}.xlsx"

    audit(db, db.info["organization_id"], db.info["user_id"], "EXPORT_INVOICES" if "invoices" in filename else "EXPORT_LINE_ITEMS")
    db.commit()
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
