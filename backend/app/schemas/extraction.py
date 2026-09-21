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


class ExtractionPreviewResponse(BaseModel):
    file_id: int
    template_id: int
    template_name: str
    target_worksheet: str
    fields: list[ExtractedFieldSchema]
    has_errors: bool
    error_count: int
    warning_count: int
    errors: list[ExtractionErrorSchema]
    warnings: list[str]
    validation_report: ValidationReportSchema

    model_config = ConfigDict(from_attributes=True)
