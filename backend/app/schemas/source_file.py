"""
app/schemas/source_file.py — Pydantic schemas for file inspection and responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class FormulaCellDetailSchema(BaseModel):
    sheet_name: str
    coordinate: str
    formula: str
    cached_value: Any = None
    is_cached_value_available: bool

    model_config = ConfigDict(from_attributes=True)


class WorksheetInfoSchema(BaseModel):
    name: str
    is_hidden: bool
    row_count: int
    column_count: int
    has_formulas: bool
    formula_count: int

    model_config = ConfigDict(from_attributes=True)


class WorkbookInspectionSchema(BaseModel):
    worksheets: list[WorksheetInfoSchema]
    active_sheet_name: str
    has_formula_cells: bool
    formula_cells: list[FormulaCellDetailSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FileUploadResponse(BaseModel):
    file_id: int
    original_name: str
    file_size: int
    checksum: str
    uploaded_at: datetime
    inspection: WorkbookInspectionSchema

    model_config = ConfigDict(from_attributes=True)


class WorksheetPreviewResponse(BaseModel):
    file_id: int
    sheet_name: str
    rows: list[list[Any]]
    total_rows_returned: int
    total_cols_returned: int
