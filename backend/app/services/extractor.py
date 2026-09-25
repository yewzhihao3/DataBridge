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
    target_field: str | None = None
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


_LINE_ITEM_FOOTER_LABELS: frozenset[str] = frozenset([
    "subtotal",
    "sub-total",
    "sub total",
    "total",
    "grand total",
    "total amount",
    "total due",
    "amount due",
    "balance due",
    "net amount",
    "total payable",
    "tax",
    "tax total",
    "sales tax",
    "vat",
    "gst",
    "sst",
    "discount",
    "shipping",
    "handling",
    "freight",
    "terms",
    "terms and conditions",
    "terms & conditions",
    "payment terms",
    "payment instructions",
    "bank details",
    "notes",
    "remarks",
    "thank you",
    "thank you for your business",
])


@dataclass
class ExtractionResult:
    """
    Summary outcome of extracting a workbook using a template.
    """

    target_worksheet: str
    fields: list[ExtractedField] = field(default_factory=list)
    rows: list[RowExtractionResult] = field(default_factory=list)
    line_items: list[RowExtractionResult] = field(default_factory=list)
    is_multi_record: bool = False
    has_line_items: bool = False
    errors: list[ExtractionError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        if self.errors:
            return True
        if self.is_multi_record:
            return any(r.has_errors for r in self.rows)
        if self.has_line_items:
            return any(li.has_errors for li in self.line_items)
        return len(self.errors) > 0

    @property
    def error_count(self) -> int:
        count = len(self.errors)
        if self.is_multi_record:
            count += sum(len(r.errors) for r in self.rows)
        if self.has_line_items:
            count += sum(len(li.errors) for li in self.line_items)
        return count

    @property
    def warning_count(self) -> int:
        count = len(self.warnings)
        if self.is_multi_record:
            count += sum(len(r.warnings) for r in self.rows)
        if self.has_line_items:
            count += sum(len(li.warnings) for li in self.line_items)
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
    template_type = getattr(template, "template_type", None)

    # Check if this is a dataset (multi-record) template
    is_dataset_template = (
        template_type == "dataset"
        or (
            mappings
            and all(
                getattr(m, "mapping_type", "cell") == "column"
                and getattr(m, "mapping_group", "header") == "header"
                for m in mappings
            )
        )
    )


    if is_dataset_template:
        return _extract_column_rows_from_workbook(
            wb_formula=wb_formula,
            wb_values=wb_values,
            template=template,
            target_sheet_name=target_sheet_name,
            ws_formula=ws_formula,
            ws_values=ws_values,
            mappings=mappings,
        )

    # Invoice Template Mode (Extract Header Cells + Optional Repeating Line Items)
    header_mappings = [m for m in mappings if getattr(m, "mapping_group", "header") == "header"]
    line_item_mappings = [m for m in mappings if getattr(m, "mapping_group", "header") == "line_item"]

    workbook_epoch = getattr(wb_formula, "epoch", None)
    template_date_format = getattr(template, "date_format", None)

    for mapping in header_mappings:

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
                target_field=getattr(mapping, "target_field", None),
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

    # 2. Extract Line Items if configured
    extracted_line_items: list[RowExtractionResult] = []
    has_line_items = False

    if line_item_mappings:
        has_line_items = True
        line_items_res = _extract_line_item_rows_from_workbook(
            wb_formula=wb_formula,
            wb_values=wb_values,
            template=template,
            target_sheet_name=target_sheet_name,
            ws_formula=ws_formula,
            ws_values=ws_values,
            line_item_mappings=line_item_mappings,
        )
        extracted_line_items = line_items_res.line_items
        errors.extend(line_items_res.errors)
        warnings.extend(line_items_res.warnings)

    return ExtractionResult(
        target_worksheet=target_sheet_name,
        fields=extracted_fields,
        line_items=extracted_line_items,
        is_multi_record=False,
        has_line_items=has_line_items,
        errors=errors,
        warnings=warnings,
    )


def _extract_line_item_rows_from_workbook(
    wb_formula: openpyxl.Workbook,
    wb_values: openpyxl.Workbook,
    template: Any,
    target_sheet_name: str,
    ws_formula: Any,
    ws_values: Any,
    line_item_mappings: list[Any],
) -> ExtractionResult:
    workbook_epoch = getattr(wb_formula, "epoch", None)
    template_date_format = getattr(template, "date_format", None)
    header_row = getattr(template, "header_row", None) or 1
    data_start_row = getattr(template, "data_start_row", None) or (header_row + 1)

    top_level_errors: list[ExtractionError] = []
    top_level_warnings: list[str] = []

    valid_mappings: list[tuple[Any, str]] = []
    for mapping in line_item_mappings:
        field_name = mapping.field_name
        col_ref = getattr(mapping, "column_ref", None)
        if not col_ref or not col_ref.strip():
            top_level_errors.append(
                ExtractionError(
                    field_name=field_name,
                    message=f"Missing column reference for line-item field '{field_name}'.",
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
            has_line_items=True,
            line_items=[],
            errors=top_level_errors,
            warnings=top_level_warnings,
        )

    max_r = ws_formula.max_row or data_start_row
    max_scan_row = min(max_r, data_start_row + 500)

    extracted_items: list[RowExtractionResult] = []
    consecutive_empty = 0

    for row_num in range(data_start_row, max_scan_row + 1):
        # 1. Quick probe for emptiness across all line item columns
        row_raw_values: dict[str, Any] = {}
        row_is_all_empty = True

        for mapping, col_letter in valid_mappings:
            cell_coord = f"{col_letter}{row_num}"
            cell_val = ws_values[cell_coord].value
            cell_f = ws_formula[cell_coord]
            is_formula = (
                cell_f.data_type == "f"
                or (isinstance(cell_f.value, str) and str(cell_f.value).startswith("="))
            )
            raw = cell_f.value if is_formula else cell_val
            row_raw_values[mapping.field_name] = raw
            if (cell_val is not None and str(cell_val).strip() != "") or is_formula:
                row_is_all_empty = False

        if row_is_all_empty:
            if extracted_items:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
            continue
        else:
            consecutive_empty = 0

        # 2. Contextual footer / summary row detection.
        #
        # Strategy: scan EVERY mapped column for footer keywords (not just
        # the description column).  A footer keyword found in ANY cell is
        # treated as a *candidate* signal.  To avoid false positives on
        # legitimate product names (e.g. "Total Care Cleaning Kit"), we
        # require *structural evidence*: key numeric columns (quantity and
        # unit_price) must be blank or absent for the row to be classified
        # as a summary/footer row.
        #
        # Text cleaning: strip parenthetical suffixes so that values like
        # "Tax (8%)" match the base label "tax".

        footer_keyword_found = False
        qty_val = None
        price_val = None

        for mapping, _ in valid_mappings:
            target = getattr(mapping, "target_field", None) or mapping.field_name

            # Collect qty / unit_price values regardless of footer detection
            if target in {"quantity", "qty"}:
                qty_val = row_raw_values.get(mapping.field_name)
            elif target in {"unit_price", "price", "rate"}:
                price_val = row_raw_values.get(mapping.field_name)

            # Check this column's value for a footer keyword
            if not footer_keyword_found:
                cell_val = row_raw_values.get(mapping.field_name)
                if cell_val is not None and isinstance(cell_val, str):
                    cleaned = cell_val.strip().lower()
                    # Strip trailing colon  e.g.  "Total:"
                    if cleaned.endswith(":"):
                        cleaned = cleaned[:-1].strip()
                    # Strip parenthetical suffix  e.g.  "Tax (8%)" → "tax"
                    paren_idx = cleaned.find("(")
                    if paren_idx > 0:
                        cleaned = cleaned[:paren_idx].strip()

                    if cleaned in _LINE_ITEM_FOOTER_LABELS:
                        footer_keyword_found = True

        if footer_keyword_found:
            qty_empty = qty_val is None or str(qty_val).strip() == ""
            price_empty = price_val is None or str(price_val).strip() == ""

            if qty_empty or price_empty:
                # Confirmed footer/summary row → stop line-item extraction
                break

        # 3. Extract this row
        row_fields: list[ExtractedField] = []
        row_errors: list[ExtractionError] = []
        row_warnings: list[str] = []

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
                or (isinstance(val_formula, str) and str(val_formula).startswith("="))
            )
            formula_expr = str(val_formula) if is_formula else None
            raw_val = val_formula if is_formula else val_cached

            is_empty_cell = (
                (val_cached is None or (isinstance(val_cached, str) and not val_cached.strip()))
                and not is_formula
            )

            field_status: Literal["success", "empty_optional", "error"] = "success"
            norm_val: Any = None
            error_msg: str | None = None
            warning_msg: str | None = None

            if is_formula and val_cached is None:
                warning_msg = f"Formula '{formula_expr}' in cell '{cell_coord}' has no cached calculated value in Excel."
                row_warnings.append(warning_msg)
                if is_required:
                    field_status = "error"
                    error_msg = f"Required line-item field '{field_name}' in cell '{cell_coord}' contains an uncalculated formula '{formula_expr}'."
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
                    error_msg = f"Required line-item field '{field_name}' in cell '{cell_coord}' (Row {row_num}) is empty."
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
                    error_msg = f"Failed to normalize value '{value_to_normalize}' as {data_type} for line-item field '{field_name}' in cell '{cell_coord}': {exc}"
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
                    target_field=getattr(mapping, "target_field", None),
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

        extracted_items.append(
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
        has_line_items=True,
        line_items=extracted_items,
        errors=top_level_errors,
        warnings=top_level_warnings,
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
                    target_field=getattr(mapping, "target_field", None),
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

