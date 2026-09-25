"""
app/schemas/extraction.py — Schemas for extraction requests and validation reports.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    file_id: int = Field(..., gt=0, description="ID of uploaded SourceFile")
    template_id: int = Field(..., gt=0, description="ID of Template configuration")


class ExtractionErrorSchema(BaseModel):
    field_name: str | None = None
    message: str
    worksheet: str | None = None
    cell_ref: str | None = None
    error_type: str

    model_config = ConfigDict(from_attributes=True)


class ExtractedFieldSchema(BaseModel):
    field_name: str
    target_field: str | None = None
    mapping_type: str
    source_worksheet: str
    source_cell_ref: str | None
    raw_value: Any
    data_type: str
    is_required: bool
    is_empty_cell: bool
    is_formula: bool
    formula_expression: str | None
    normalized_value: Any
    status: Literal["success", "empty_optional", "error"]
    error_message: str | None = None
    warning_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ValidationIssueSchema(BaseModel):
    rule_id: str
    field_name: str | None = None
    severity: Literal["error", "warning", "info"]
    message: str
    cell_ref: str | None = None
    worksheet: str | None = None
    actual_value: Any = None

    model_config = ConfigDict(from_attributes=True)


class ValidationReportSchema(BaseModel):
    is_valid_for_import: bool
    issues: list[ValidationIssueSchema] = Field(default_factory=list)
    error_count: int
    warning_count: int
    info_count: int
    normalized_data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class RowExtractionPreviewSchema(BaseModel):
    source_row_number: int
    fields: list[ExtractedFieldSchema] = Field(default_factory=list)
    has_errors: bool
    error_count: int
    warning_count: int
    errors: list[ExtractionErrorSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class LineItemExtractionPreviewSchema(BaseModel):
    source_row_number: int
    fields: list[ExtractedFieldSchema] = Field(default_factory=list)
    has_errors: bool = False
    error_count: int = 0
    warning_count: int = 0
    errors: list[ExtractionErrorSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ExtractionPreviewResponse(BaseModel):
    file_id: int
    template_id: int
    template_name: str
    template_type: str = "invoice"
    target_worksheet: str
    is_multi_record: bool = False
    has_line_items: bool = False
    record_count: int = 1
    line_item_count: int = 0
    fields: list[ExtractedFieldSchema] = Field(default_factory=list)
    records: list[RowExtractionPreviewSchema] = Field(default_factory=list)
    line_items: list[LineItemExtractionPreviewSchema] = Field(default_factory=list)
    has_errors: bool
    error_count: int
    warning_count: int
    errors: list[ExtractionErrorSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_report: ValidationReportSchema

    model_config = ConfigDict(from_attributes=True)

