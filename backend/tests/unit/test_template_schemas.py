"""
tests/unit/test_template_schemas.py — Unit tests for template Pydantic schemas.
"""

import pytest
from pydantic import ValidationError

from app.schemas.template import (
    FieldMappingCreate,
    TemplateCreate,
    TemplateUpdate,
)


class TestFieldMappingValidation:
    """Verify validation rules on FieldMappingCreate."""

    def test_valid_cell_mapping_is_canonicalized(self) -> None:
        mapping = FieldMappingCreate(
            field_name="Invoice_Number",
            mapping_type="cell",
            cell_ref="$b$3",
            is_required=True,
            data_type="text",
        )
        assert mapping.field_name == "invoice_number"
        assert mapping.cell_ref == "B3"  # normalized to uppercase A1 notation

    def test_invalid_cell_ref_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="Invalid cell_ref"):
            FieldMappingCreate(
                field_name="total",
                mapping_type="cell",
                cell_ref="B0",  # Row 0 does not exist
            )

    def test_valid_column_mapping_is_canonicalized(self) -> None:
        mapping = FieldMappingCreate(
            field_name="Invoice_Number",
            mapping_type="column",
            column_ref="$b",
            is_required=True,
            data_type="text",
        )
        assert mapping.field_name == "invoice_number"
        assert mapping.column_ref == "B"

    def test_unsupported_mapping_type_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            FieldMappingCreate(
                field_name="items",
                mapping_type="invalid_type",  # type: ignore[arg-type]
                cell_ref=None,
            )

    def test_missing_column_ref_for_column_mapping_raises_error(self) -> None:
        with pytest.raises(ValidationError, match="column_ref is required"):
            FieldMappingCreate(
                field_name="total",
                mapping_type="column",
                column_ref="",
            )

    def test_missing_cell_ref_for_cell_mapping_raises_error(self) -> None:
        with pytest.raises(ValidationError, match="cell_ref is required"):
            FieldMappingCreate(
                field_name="total",
                mapping_type="cell",
                cell_ref="",
            )


class TestTemplateCreateValidation:
    """Verify validation rules on TemplateCreate."""

    def test_valid_template_with_multiple_mappings(self) -> None:
        template = TemplateCreate(
            name=" Acme Supplier Template ",
            description="Invoice layout for Acme",
            file_type="xlsx",
            worksheet="Sheet1",
            header_row=1,
            data_start_row=2,
            field_mappings=[
                FieldMappingCreate(
                    field_name="company_name", mapping_type="cell", cell_ref="B2"
                ),
                FieldMappingCreate(
                    field_name="total_amount", mapping_type="cell", cell_ref="D6", data_type="decimal"
                ),
            ],
        )
        assert template.name == "Acme Supplier Template"  # stripped whitespace
        assert len(template.field_mappings) == 2

    def test_duplicate_field_names_in_template_raises_error(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate field_name 'invoice_number'"):
            TemplateCreate(
                name="Duplicate Test",
                field_mappings=[
                    FieldMappingCreate(
                        field_name="invoice_number", mapping_type="cell", cell_ref="B2"
                    ),
                    FieldMappingCreate(
                        field_name="invoice_number", mapping_type="cell", cell_ref="C2"
                    ),
                ],
            )


class TestTemplateUpdateValidation:
    """Verify validation rules on TemplateUpdate."""

    def test_duplicate_field_names_in_update_raises_error(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate field_name"):
            TemplateUpdate(
                field_mappings=[
                    FieldMappingCreate(
                        field_name="total", mapping_type="cell", cell_ref="D6"
                    ),
                    FieldMappingCreate(
                        field_name="total", mapping_type="cell", cell_ref="E6"
                    ),
                ]
            )
