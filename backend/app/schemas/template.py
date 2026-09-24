"""
app/schemas/template.py — Pydantic request and response schemas for templates.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import CANONICAL_INVOICE_FIELDS
from app.utils.cell_reference import (
    InvalidCellReference,
    parse_cell_reference,
    parse_column_reference,
)


# ── Field Mapping Schemas ─────────────────────────────────────────────────────


class FieldMappingBase(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=100, description="Standard field identifier")
    target_field: str | None = Field(None, max_length=100, description="Canonical or custom backend field to map to")
    mapping_type: Literal["cell", "column"] = Field("cell", description="Mapping strategy ('cell' or 'column')")
    cell_ref: str | None = Field(None, description="Cell reference e.g. 'B2'")
    column_ref: str | None = Field(None, description="Column letter e.g. 'B'")
    is_required: bool = Field(False, description="Whether this field must be present and non-empty")
    data_type: Literal["text", "date", "decimal", "integer"] = Field("text", description="Expected data type")

    @field_validator("field_name")
    @classmethod
    def clean_field_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean:
            raise ValueError("Field name cannot be empty or whitespace.")
        return clean

    @field_validator("target_field")
    @classmethod
    def clean_target_field(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().lower()
        if not clean:
            return None
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", clean):
            raise ValueError(
                f"Invalid target_field '{clean}'. Target field must contain only "
                "alphanumeric characters and underscores, and cannot start with a number."
            )
        return clean

    @field_validator("mapping_type")
    @classmethod
    def validate_mapping_type(cls, v: str) -> str:
        if v not in ("cell", "column"):
            raise ValueError("Only mapping_type 'cell' or 'column' is supported.")
        return v

    @model_validator(mode="after")
    def validate_reference_by_mapping_type(self) -> FieldMappingBase:
        if self.mapping_type == "cell":
            if not self.cell_ref or not self.cell_ref.strip():
                raise ValueError("cell_ref is required when mapping_type is 'cell'.")
            try:
                parsed = parse_cell_reference(self.cell_ref)
                # Canonicalize to standard A1 format (e.g. '$b$2' -> 'B2')
                self.cell_ref = parsed.to_a1()
            except InvalidCellReference as exc:
                raise ValueError(f"Invalid cell_ref '{self.cell_ref}': {exc}") from exc
        elif self.mapping_type == "column":
            if not self.column_ref or not self.column_ref.strip():
                raise ValueError("column_ref is required when mapping_type is 'column'.")
            try:
                self.column_ref = parse_column_reference(self.column_ref)
            except InvalidCellReference as exc:
                raise ValueError(f"Invalid column_ref '{self.column_ref}': {exc}") from exc
        return self


class FieldMappingCreate(FieldMappingBase):
    """Schema for creating a field mapping inside a template."""


class FieldMappingRead(FieldMappingBase):
    id: int
    template_id: int

    model_config = ConfigDict(from_attributes=True)


# ── Template Schemas ──────────────────────────────────────────────────────────



class TemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Unique template name")
    description: str | None = Field(None, max_length=500)
    file_type: Literal["xlsx"] = Field("xlsx", description="File format")
    worksheet: str | None = Field(None, max_length=100, description="Target worksheet name (null = first sheet)")
    header_row: int | None = Field(None, ge=1, description="Header row number (1-based)")
    data_start_row: int | None = Field(None, ge=1, description="Data start row (1-based)")
    date_format: str | None = Field(None, max_length=50, description="Optional custom date parsing format")

    @field_validator("name")
    @classmethod
    def clean_template_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Template name cannot be empty or whitespace.")
        return clean


class TemplateCreate(TemplateBase):
    field_mappings: list[FieldMappingCreate] = Field(
        default_factory=list, description="Initial field mappings"
    )

    @model_validator(mode="after")
    def check_duplicate_field_names(self) -> TemplateCreate:
        names_seen: set[str] = set()
        canonical_targets_seen: set[str] = set()
        for mapping in self.field_mappings:
            if mapping.field_name in names_seen:
                raise ValueError(
                    f"Duplicate field_name '{mapping.field_name}' in template mappings. "
                    "Each field name must be unique within a template."
                )
            names_seen.add(mapping.field_name)

            if mapping.target_field and mapping.target_field in CANONICAL_INVOICE_FIELDS:
                if mapping.target_field in canonical_targets_seen:
                    raise ValueError(
                        f"Duplicate mapping to canonical field '{mapping.target_field}'. "
                        "Each canonical target field can only be mapped once per template."
                    )
                canonical_targets_seen.add(mapping.target_field)
        return self


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    worksheet: str | None = Field(None, max_length=100)
    header_row: int | None = Field(None, ge=1)
    data_start_row: int | None = Field(None, ge=1)
    date_format: str | None = Field(None, max_length=50)
    field_mappings: list[FieldMappingCreate] | None = Field(
        None, description="If provided, completely replaces existing field mappings"
    )

    @field_validator("name")
    @classmethod
    def clean_update_name(cls, v: str | None) -> str | None:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Template name cannot be empty.")
            return clean
        return v

    @model_validator(mode="after")
    def check_duplicate_update_field_names(self) -> TemplateUpdate:
        if self.field_mappings is not None:
            names_seen: set[str] = set()
            canonical_targets_seen: set[str] = set()
            for mapping in self.field_mappings:
                if mapping.field_name in names_seen:
                    raise ValueError(
                        f"Duplicate field_name '{mapping.field_name}' in template mappings."
                    )
                names_seen.add(mapping.field_name)

                if mapping.target_field and mapping.target_field in CANONICAL_INVOICE_FIELDS:
                    if mapping.target_field in canonical_targets_seen:
                        raise ValueError(
                            f"Duplicate mapping to canonical field '{mapping.target_field}'. "
                            "Each canonical target field can only be mapped once per template."
                        )
                    canonical_targets_seen.add(mapping.target_field)
        return self


class TemplateRead(TemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime
    field_mappings: list[FieldMappingRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TemplateListItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    file_type: str
    worksheet: str | None = None
    mapping_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
