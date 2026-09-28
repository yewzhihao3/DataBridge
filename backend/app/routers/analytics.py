"""Dashboard analytics over standardized database records only."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analytics import AnalyticsFilterOptions, AnalyticsFilters, DashboardResponse
from app.services.analytics_service import dashboard, filter_options

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/filter-options", response_model=AnalyticsFilterOptions)
def get_filter_options(db: Session = Depends(get_db)):
    return filter_options(db)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    currency: str | None = Query(None, max_length=10, description="One currency. Omitted/blank selects unspecified currency, with monetary results withheld."),
    date_from: date | None = None,
    date_to: date | None = None,
    company: str | None = Query(None, max_length=255),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Date From must be on or before Date To.")
    filters = AnalyticsFilters(
        currency=currency.strip().upper() or None if currency is not None else None,
        date_from=date_from, date_to=date_to, company=company.strip() or None if company is not None else None,
    )
    return dashboard(db, filters)
