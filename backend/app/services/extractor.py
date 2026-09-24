"""
app/services/extractor.py — Core Excel extraction engine with full provenance tracking.

──────────────────────────────────────────────────────────────────────────────
Design Principles:
1. Framework Independence: Operates entirely on file paths / openpyxl workbooks
   and template definitions. Zero dependencies on FastAPI or SQLAlchemy sessions.
2. Provenance Tracking: Every extracted field preserves original cell address,
   sheet name, raw content, formula string, and conversion status.
3. Deterministic Error Handling: Captures structured extraction errors and
   warnings rather than silently returning corrupted defaults.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import openpyxl

from app.services.normalizer import (
    NormalizationError,
    normalize_date,
    normalize_decimal,
    normalize_integer,
    normalize_text,
)
from app.services.workbook_inspector import (
    CorruptWorkbookError,
    validate_xlsx_file,
)
from app.utils.cell_reference import InvalidCellReference, parse_cell_reference


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtractionError:
    """
    Structured extraction error for reporting to APIs, UIs, and validation layers.
    """

    field_name: str | None
    message: str
    worksheet: str | None
    cell_ref: str | None
    error_type: str  # missing_worksheet, unsupported_mapping_type, missing_cell_ref, required_empty, uncalculated_formula, normalization_error


@dataclass(frozen=True)
class ExtractedField:
    """
    Complete provenance record for a single mapped field.
    """

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


@dataclass
class RowExtractionResult:
    """
    Provenance and field extractions for a single Excel row in a multi-record extraction.
    """

    row_number: int  # 1-based Excel row index
    fields: list[ExtractedField] = field(default_factory=list)
    errors: list[ExtractionError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_blank_row: bool = False

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


@dataclass
class ExtractionResult:
    """
    Summary outcome of extracting a workbook using a template.
    """

    target_worksheet: str
    fields: list[ExtractedField] = field(default_factory=list)
    rows: list[RowExtractionResult] = field(default_factory=list)
    is_multi_record: bool = False
    errors: list[ExtractionError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        if self.errors:
            return True
        if self.is_multi_record:
            return any(r.has_errors for r in self.rows)
        return len(self.errors) > 0

    @property
    def error_count(self) -> int:
        count = len(self.errors)
        if self.is_multi_record:
            count += sum(len(r.errors) for r in self.rows)
        return count

    @property
    def warning_count(self) -> int:
        count = len(self.warnings)
        if self.is_multi_record:
            count += sum(len(r.warnings) for r in self.rows)
        return count


# ── Extraction Engine ─────────────────────────────────────────────────────────


def extract_from_file(
    file_path: Path | str,
    template: Any,
    max_size_mb: int = 10,
) -> ExtractionResult:
    """
    Extracts and normalizes field values from an Excel file based on a template.

    Args:
        file_path: Path to the .xlsx file.
        template: Template instance (ORM model or duck-typed object) with attributes:
                  - worksheet (str | None)
                  - date_format (str | None)
                  - field_mappings (iterable of mappings)
        max_size_mb: Maximum allowed file size in megabytes.

    Returns:
        ExtractionResult containing fields with full provenance, errors, and warnings.
    """
    validate_xlsx_file(file_path, max_size_mb=max_size_mb)
    path = Path(file_path).resolve()

    try:
        wb_formula = openpyxl.load_workbook(path, data_only=False, read_only=False)
        wb_values = openpyxl.load_workbook(path, data_only=True, read_only=False)
    except Exception as exc:
        raise CorruptWorkbookError(
            f"Failed to open workbook for extraction: {exc}"
        ) from exc

    try:
        return extract_from_workbook(
            wb_formula=wb_formula,
            wb_values=wb_values,
            template=template,
        )
    finally:
        wb_formula.close()
        wb_values.close()


def extract_from_workbook(
    wb_formula: openpyxl.Workbook,
    wb_values: openpyxl.Workbook,
    template: Any,
) -> ExtractionResult:
    """
    Extracts fields from open openpyxl workbook instances.
    """
    extracted_fields: list[ExtractedField] = []
    errors: list[ExtractionError] = []
    warnings: list[str] = []

    # 1. Resolve target worksheet
    target_sheet_name = (
        template.worksheet if getattr(template, "worksheet", None) else wb_formula.sheetnames[0]
    )

    if target_sheet_name not in wb_formula.sheetnames:
        err = ExtractionError(
            field_name=None,
            message=(
                f"Target worksheet '{target_sheet_name}' was not found in workbook. "
                f"Available sheets: {wb_formula.sheetnames}"
            ),
            worksheet=target_sheet_name,
            cell_ref=None,
            error_type="missing_worksheet",
        )
        return ExtractionResult(
            target_worksheet=target_sheet_name,
            fields=[],
            errors=[err],
            warnings=[f"Worksheet '{target_sheet_name}' does not exist."],
        )

    ws_formula = wb_formula[target_sheet_name]
    ws_values = wb_values[target_sheet_name]

    # Check if this template is a column-mapping template
    mappings = getattr(template, "field_mappings", []) or []
    is_column_template = any(getattr(m, "mapping_type", "cell") == "column" for m in mappings)

    if is_column_template:
        return _extract_column_rows_from_workbook(
            wb_formula=wb_formula,
            wb_values=wb_values,
            template=template,
            target_sheet_name=target_sheet_name,
            ws_formula=ws_formula,
            ws_values=ws_values,
            mappings=mappings,
        )

    workbook_epoch = getattr(wb_formula, "epoch", None)
    template_date_format = getattr(template, "date_format", None)

    for mapping in mappings:
        field_name = mapping.field_name
        mapping_type = getattr(mapping, "mapping_type", "cell")
        raw_cell_ref = getattr(mapping, "cell_ref", None)
        is_required = bool(getattr(mapping, "is_required", False))
        data_type = getattr(mapping, "data_type", "text")

        # Guard: Validate mapping type
        if mapping_type != "cell":
            err_msg = (
                f"Unsupported mapping_type '{mapping_type}' for field '{field_name}'. "
                "Only 'cell' mappings are supported."
            )
            errors.append(
                ExtractionError(
                    field_name=field_name,
                    message=err_msg,
                    worksheet=target_sheet_name,
                    cell_ref=raw_cell_ref,
                    error_type="unsupported_mapping_type",
                )
            )
            extracted_fields.append(
                ExtractedField(
                    field_name=field_name,
                    mapping_type=mapping_type,
                    source_worksheet=target_sheet_name,
                    source_cell_ref=raw_cell_ref,
                    raw_value=None,
                    data_type=data_type,
                    is_required=is_required,
                    is_empty_cell=True,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=None,
                    status="error",
                    error_message=err_msg,
                )
            )
            continue

        # Guard: Validate cell reference presence
        if not raw_cell_ref or not raw_cell_ref.strip():
            err_msg = f"Missing cell reference for field '{field_name}'."
            errors.append(
                ExtractionError(
                    field_name=field_name,
                    message=err_msg,
                    worksheet=target_sheet_name,
                    cell_ref=None,
                    error_type="missing_cell_ref",
                )
            )
            extracted_fields.append(
                ExtractedField(
                    field_name=field_name,
                    mapping_type=mapping_type,
                    source_worksheet=target_sheet_name,
                    source_cell_ref=None,
                    raw_value=None,
                    data_type=data_type,
                    is_required=is_required,
                    is_empty_cell=True,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=None,
                    status="error",
                    error_message=err_msg,
                )
            )
            continue

        # Parse cell reference
        try:
            parsed_ref = parse_cell_reference(raw_cell_ref)
            cell_coord = parsed_ref.to_a1()
        except InvalidCellReference as exc:
            err_msg = f"Invalid cell reference '{raw_cell_ref}' for field '{field_name}': {exc}"
            errors.append(
                ExtractionError(
                    field_name=field_name,
                    message=err_msg,
                    worksheet=target_sheet_name,
                    cell_ref=raw_cell_ref,
                    error_type="invalid_cell_ref",
                )
            )
            extracted_fields.append(
                ExtractedField(
                    field_name=field_name,
                    mapping_type=mapping_type,
                    source_worksheet=target_sheet_name,
                    source_cell_ref=raw_cell_ref,
                    raw_value=None,
                    data_type=data_type,
                    is_required=is_required,
                    is_empty_cell=True,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=None,
                    status="error",
                    error_message=err_msg,
                )
            )
            continue

        # Read cell content from both workbooks
        cell_formula = ws_formula[cell_coord]
        cell_values = ws_values[cell_coord]

        val_formula = cell_formula.value
        val_cached = cell_values.value

        is_formula = (
            cell_formula.data_type == "f"
            or (isinstance(val_formula, str) and val_formula.startswith("="))
        )

        formula_expr = str(val_formula) if is_formula else None
        raw_val = val_formula if is_formula else val_cached

        # Determine emptiness
        is_empty_cell = (
            (val_cached is None or (isinstance(val_cached, str) and not val_cached.strip()))
            and not is_formula
        )

        # ── Status and Normalization Evaluation ───────────────────────────────
        field_status: Literal["success", "empty_optional", "error"] = "success"
        norm_val: Any = None
        error_msg: str | None = None
        warning_msg: str | None = None

        if is_formula and val_cached is None:
            # Formula present but uncalculated
            warning_msg = (
                f"Formula '{formula_expr}' in cell '{cell_coord}' has no cached calculated value in Excel."
            )
            warnings.append(warning_msg)

            if is_required:
                field_status = "error"
                error_msg = (
                    f"Required field '{field_name}' in cell '{cell_coord}' contains an uncalculated "
                    f"formula '{formula_expr}' with no cached value."
                )
                errors.append(
                    ExtractionError(
                        field_name=field_name,
                        message=error_msg,
                        worksheet=target_sheet_name,
                        cell_ref=cell_coord,
                        error_type="uncalculated_formula",
                    )
                )
            else:
                field_status = "empty_optional"

        elif is_empty_cell:
            # Non-formula empty cell
            if is_required:
                field_status = "error"
                error_msg = f"Required field '{field_name}' in cell '{cell_coord}' is empty."
                errors.append(
                    ExtractionError(
                        field_name=field_name,
                        message=error_msg,
                        worksheet=target_sheet_name,
                        cell_ref=cell_coord,
                        error_type="required_empty",
                    )
                )
            else:
                field_status = "empty_optional"

        else:
            # Has a value to normalize (either normal value or cached formula value)
            value_to_normalize = val_cached if is_formula else raw_val
            try:
                if data_type == "decimal":
                    norm_val = normalize_decimal(value_to_normalize)
                elif data_type == "date":
                    norm_val = normalize_date(
                        value_to_normalize,
                        date_format=template_date_format,
                        workbook_epoch=workbook_epoch,
                    )
                elif data_type == "integer":
                    norm_val = normalize_integer(value_to_normalize)
                else:  # text
                    norm_val = normalize_text(value_to_normalize)

                field_status = "success"

            except NormalizationError as exc:
                field_status = "error"
                error_msg = (
                    f"Failed to normalize value '{value_to_normalize}' as {data_type} "
                    f"for field '{field_name}' in cell '{cell_coord}': {exc}"
                )
                errors.append(
                    ExtractionError(
                        field_name=field_name,
                        message=error_msg,
                        worksheet=target_sheet_name,
                        cell_ref=cell_coord,
                        error_type="normalization_error",
                    )
                )

        extracted_fields.append(
            ExtractedField(
                field_name=field_name,
                mapping_type=mapping_type,
                source_worksheet=target_sheet_name,
                source_cell_ref=cell_coord,
                raw_value=raw_val,
                data_type=data_type,
                is_required=is_required,
                is_empty_cell=is_empty_cell,
                is_formula=is_formula,
                formula_expression=formula_expr,
                normalized_value=norm_val,
                status=field_status,
                error_message=error_msg,
                warning_message=warning_msg,
            )
        )

    return ExtractionResult(
        target_worksheet=target_sheet_name,
        fields=extracted_fields,
        errors=errors,
        warnings=warnings,
    )


def _extract_column_rows_from_workbook(
    wb_formula: openpyxl.Workbook,
    wb_values: openpyxl.Workbook,
    template: Any,
    target_sheet_name: str,
    ws_formula: Any,
    ws_values: Any,
    mappings: list[Any],
) -> ExtractionResult:
    workbook_epoch = getattr(wb_formula, "epoch", None)
    template_date_format = getattr(template, "date_format", None)
    header_row = getattr(template, "header_row", None) or 1
    data_start_row = getattr(template, "data_start_row", None) or (header_row + 1)

    column_mappings = [
        m for m in mappings if getattr(m, "mapping_type", "cell") == "column"
    ]

    top_level_errors: list[ExtractionError] = []
    top_level_warnings: list[str] = []

    if not column_mappings:
        top_level_errors.append(
            ExtractionError(
                field_name=None,
                message="No column mappings found in template for multi-row extraction.",
                worksheet=target_sheet_name,
                cell_ref=None,
                error_type="missing_column_mappings",
            )
        )
        return ExtractionResult(
            target_worksheet=target_sheet_name,
            is_multi_record=True,
            rows=[],
            errors=top_level_errors,
            warnings=top_level_warnings,
        )

    valid_mappings: list[tuple[Any, str]] = []
    for mapping in column_mappings:
        field_name = mapping.field_name
        col_ref = getattr(mapping, "column_ref", None)
        if not col_ref or not col_ref.strip():
            top_level_errors.append(
                ExtractionError(
                    field_name=field_name,
                    message=f"Missing column reference for field '{field_name}'.",
                    worksheet=target_sheet_name,
                    cell_ref=None,
                    error_type="missing_column_ref",
                )
            )
        else:
            valid_mappings.append((mapping, col_ref.strip().upper()))

    if top_level_errors:
        return ExtractionResult(
            target_worksheet=target_sheet_name,
            is_multi_record=True,
            rows=[],
            errors=top_level_errors,
            warnings=top_level_warnings,
        )

    max_r = ws_formula.max_row or data_start_row
    max_scan_row = min(max_r, data_start_row + 2000)

    extracted_rows: list[RowExtractionResult] = []
    consecutive_empty = 0

    for row_num in range(data_start_row, max_scan_row + 1):
        row_fields: list[ExtractedField] = []
        row_errors: list[ExtractionError] = []
        row_warnings: list[str] = []
        is_all_empty = True

        for mapping, col_letter in valid_mappings:
            cell_coord = f"{col_letter}{row_num}"
            field_name = mapping.field_name
            is_required = bool(getattr(mapping, "is_required", False))
            data_type = getattr(mapping, "data_type", "text")

            cell_formula = ws_formula[cell_coord]
            cell_values = ws_values[cell_coord]

            val_formula = cell_formula.value
            val_cached = cell_values.value

            is_formula = (
                cell_formula.data_type == "f"
                or (isinstance(val_formula, str) and val_formula.startswith("="))
            )
            formula_expr = str(val_formula) if is_formula else None
            raw_val = val_formula if is_formula else val_cached

            is_empty_cell = (
                (val_cached is None or (isinstance(val_cached, str) and not val_cached.strip()))
                and not is_formula
            )

            if not is_empty_cell:
                is_all_empty = False

            field_status: Literal["success", "empty_optional", "error"] = "success"
            norm_val: Any = None
            error_msg: str | None = None
            warning_msg: str | None = None

            if is_formula and val_cached is None:
                warning_msg = f"Formula '{formula_expr}' in cell '{cell_coord}' has no cached calculated value in Excel."
                row_warnings.append(warning_msg)
                if is_required:
                    field_status = "error"
                    error_msg = f"Required field '{field_name}' in cell '{cell_coord}' contains an uncalculated formula '{formula_expr}'."
                    row_errors.append(
                        ExtractionError(
                            field_name=field_name,
                            message=error_msg,
                            worksheet=target_sheet_name,
                            cell_ref=cell_coord,
                            error_type="uncalculated_formula",
                        )
                    )
                else:
                    field_status = "empty_optional"
            elif is_empty_cell:
                if is_required:
                    field_status = "error"
                    error_msg = f"Required field '{field_name}' in cell '{cell_coord}' (Row {row_num}) is empty."
                    row_errors.append(
                        ExtractionError(
                            field_name=field_name,
                            message=error_msg,
                            worksheet=target_sheet_name,
                            cell_ref=cell_coord,
                            error_type="required_empty",
                        )
                    )
                else:
                    field_status = "empty_optional"
            else:
                value_to_normalize = val_cached if is_formula else raw_val
                try:
                    if data_type == "decimal":
                        norm_val = normalize_decimal(value_to_normalize)
                    elif data_type == "date":
                        norm_val = normalize_date(
                            value_to_normalize,
                            date_format=template_date_format,
                            workbook_epoch=workbook_epoch,
                        )
                    elif data_type == "integer":
                        norm_val = normalize_integer(value_to_normalize)
                    else:
                        norm_val = normalize_text(value_to_normalize)
                    field_status = "success"
                except NormalizationError as exc:
                    field_status = "error"
                    error_msg = f"Failed to normalize value '{value_to_normalize}' as {data_type} for field '{field_name}' in cell '{cell_coord}': {exc}"
                    row_errors.append(
                        ExtractionError(
                            field_name=field_name,
                            message=error_msg,
                            worksheet=target_sheet_name,
                            cell_ref=cell_coord,
                            error_type="normalization_error",
                        )
                    )

            row_fields.append(
                ExtractedField(
                    field_name=field_name,
                    mapping_type="column",
                    source_worksheet=target_sheet_name,
                    source_cell_ref=cell_coord,
                    raw_value=raw_val,
                    data_type=data_type,
                    is_required=is_required,
                    is_empty_cell=is_empty_cell,
                    is_formula=is_formula,
                    formula_expression=formula_expr,
                    normalized_value=norm_val,
                    status=field_status,
                    error_message=error_msg,
                    warning_message=warning_msg,
                )
            )

        if is_all_empty:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            continue
        else:
            consecutive_empty = 0
            extracted_rows.append(
                RowExtractionResult(
                    row_number=row_num,
                    fields=row_fields,
                    errors=row_errors,
                    warnings=row_warnings,
                    is_blank_row=False,
                )
            )

    return ExtractionResult(
        target_worksheet=target_sheet_name,
        is_multi_record=True,
        rows=extracted_rows,
        errors=top_level_errors,
        warnings=top_level_warnings,
    )

