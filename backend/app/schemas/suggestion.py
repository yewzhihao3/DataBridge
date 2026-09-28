"""Review-only, bounded workbook analysis responses."""
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.template import FieldMappingCreate

Confidence = Literal["high", "medium", "low"]


class AnalyzeRequest(BaseModel):
    file_id: int = Field(gt=0)
    worksheet: str | None = Field(default=None, max_length=100)


class SheetProfile(BaseModel):
    name: str
    is_hidden: bool
    used_range: str
    scanned_rows: int
    scanned_columns: int
    truncated: bool
    non_empty_count: int
    likely_header_rows: list[int]
    blank_rows: list[int]
    numeric_columns: list[str]
    date_cells: list[str]
    currency_cells: list[str]
    formula_cells: list[str]
    merged_ranges: list[str]


class MappingSuggestion(FieldMappingCreate):
    confidence: Confidence
    reason: str


class TableSuggestion(BaseModel):
    header_row: int
    data_start_row: int
    data_end_row: int
    confidence: Confidence
    columns: list[MappingSuggestion]


class SheetAnalysis(BaseModel):
    worksheet: str
    suggested_template_type: Literal["invoice", "dataset"] | None
    confidence: Confidence
    reasons: list[str]
    mappings: list[MappingSuggestion]
    table: TableSuggestion | None = None


class TemplateMatch(BaseModel):
    template_id: int
    name: str
    confidence: Confidence
    reasons: list[str]


class AnalyzeResponse(BaseModel):
    file_id: int
    suggested_worksheet: str
    selected_worksheet: str
    review_required: Literal[True] = True
    profiles: list[SheetProfile]
    analysis: SheetAnalysis
    template_matches: list[TemplateMatch]
    warnings: list[str]
