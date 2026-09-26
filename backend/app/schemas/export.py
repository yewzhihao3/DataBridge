"""
app/schemas/export.py — Schemas for Export Center endpoints.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ExportSummaryResponse(BaseModel):
    dataset: Literal["invoices", "line-items"]
    total_records: int = Field(..., ge=0, description="Total number of matching records to export")
    column_count: int = Field(..., ge=0, description="Total number of columns including custom fields")
    columns: list[str] = Field(default_factory=list, description="List of human-readable column headers")
