"""
tests/unit/test_workbook_inspector.py — Tests for app.services.workbook_inspector.
"""

from pathlib import Path
import pytest

from app.services.workbook_inspector import (
    CorruptWorkbookError,
    FileSizeExceededError,
    InvalidFileFormatError,
    PathTraversalError,
    WorksheetNotFoundError,
    generate_safe_upload_path,
    get_worksheet_preview,
    inspect_workbook,
    validate_xlsx_file,
)


# ── Secure Upload Path & Traversal Tests ──────────────────────────────────────


class TestSafeUploadPath:
    """Verify UUID filename generation, extension checking, and path safety."""

    def test_valid_filename_generates_uuid_path(self, tmp_path: Path) -> None:
        dest, unique_name = generate_safe_upload_path(tmp_path, "Supplier Invoice.xlsx")
        assert unique_name.endswith(".xlsx")
        assert len(unique_name) == 32 + 5  # 32 hex chars + .xlsx
        assert dest == tmp_path / unique_name
        assert dest.parent == tmp_path

    def test_directory_traversal_payload_is_neutralised(self, tmp_path: Path) -> None:
        """Attempting to supply ../../../etc/passwd.xlsx should not escape upload_dir."""
        dest, unique_name = generate_safe_upload_path(
            tmp_path, "../../../evil.xlsx"
        )
        assert dest.parent == tmp_path.resolve()
        assert not str(dest).endswith("evil.xlsx")

    def test_unsupported_extensions_raise_error(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidFileFormatError, match="Unsupported file extension"):
            generate_safe_upload_path(tmp_path, "report.csv")

        with pytest.raises(InvalidFileFormatError):
            generate_safe_upload_path(tmp_path, "script.py")

        with pytest.raises(InvalidFileFormatError):
            generate_safe_upload_path(tmp_path, "document.pdf")


# ── File Validation Tests ────────────────────────────────────────────────────


class TestFileValidation:
    """Verify pre-inspection validation rules."""

    def test_nonexistent_file_raises_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.xlsx"
        with pytest.raises(FileNotFoundError):
            validate_xlsx_file(missing)

    def test_fake_magic_bytes_raises_invalid_format(
        self, fake_magic_bytes_xlsx: Path
    ) -> None:
        with pytest.raises(InvalidFileFormatError, match="Invalid file signature"):
            validate_xlsx_file(fake_magic_bytes_xlsx)

    def test_file_exceeding_max_size_raises(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        # Pass an artificially tiny max_size_mb (e.g. 0 MB / 0.00001 MB)
        with pytest.raises(FileSizeExceededError, match="exceeds maximum allowed size"):
            validate_xlsx_file(clean_single_sheet_xlsx, max_size_mb=0)


# ── Inspection Tests ──────────────────────────────────────────────────────────


class TestWorkbookInspection:
    """Verify metadata extraction, sheet state, and formula detection."""

    def test_inspect_clean_workbook(self, clean_single_sheet_xlsx: Path) -> None:
        result = inspect_workbook(clean_single_sheet_xlsx)
        assert len(result.worksheets) == 1
        ws = result.worksheets[0]
        assert ws.name == "Invoice"
        assert ws.is_hidden is False
        assert ws.row_count >= 11
        assert ws.column_count >= 6
        assert ws.has_formulas is False
        assert result.has_formula_cells is False
        assert len(result.warnings) == 0

    def test_inspect_multi_sheet_hidden_detection(
        self, multi_sheet_with_hidden_xlsx: Path
    ) -> None:
        result = inspect_workbook(multi_sheet_with_hidden_xlsx)
        assert len(result.worksheets) == 3

        sheet_map = {ws.name: ws for ws in result.worksheets}

        # Overview: visible
        assert sheet_map["Overview"].is_hidden is False
        # Lookup_Rates: hidden
        assert sheet_map["Lookup_Rates"].is_hidden is True
        # Audit_Internal: veryHidden
        assert sheet_map["Audit_Internal"].is_hidden is True

    def test_formula_detection_and_warning(
        self, workbook_with_formulas_xlsx: Path
    ) -> None:
        result = inspect_workbook(workbook_with_formulas_xlsx)
        assert result.has_formula_cells is True
        assert len(result.formula_cells) == 1

        formula_cell = result.formula_cells[0]
        assert formula_cell.coordinate == "A3"
        assert "=SUM(A1:A2)" in formula_cell.formula
        # Since this workbook was generated programmatically without Excel evaluation:
        assert formula_cell.is_cached_value_available is False
        assert formula_cell.cached_value is None

        # Warnings should clearly state that cached calculated values are unavailable
        assert len(result.warnings) == 1
        assert "no cached calculated values" in result.warnings[0]


# ── Corrupt Workbook Handling ────────────────────────────────────────────────


class TestCorruptWorkbookHandling:
    """Verify that corrupt or unparseable files raise CorruptWorkbookError gracefully."""

    def test_corrupted_zip_raises_corrupt_error(self, corrupt_xlsx: Path) -> None:
        with pytest.raises(CorruptWorkbookError, match="Failed to parse Excel workbook"):
            inspect_workbook(corrupt_xlsx)


# ── Preview Grid Tests ───────────────────────────────────────────────────────


class TestWorksheetPreview:
    """Verify cell matrix preview extraction."""

    def test_get_valid_preview(self, clean_single_sheet_xlsx: Path) -> None:
        grid = get_worksheet_preview(clean_single_sheet_xlsx, "Invoice", max_rows=5, max_cols=6)
        assert len(grid) == 5
        # Row 1, Col 1 should be 'INVOICE'
        assert grid[0][0] == "INVOICE"
        # Row 2, Col 2 (B2) should be 'Acme Supplies Ltd'
        assert grid[1][1] == "Acme Supplies Ltd"

    def test_nonexistent_sheet_raises_not_found(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        with pytest.raises(WorksheetNotFoundError, match="Worksheet 'NonExistent' not found"):
            get_worksheet_preview(clean_single_sheet_xlsx, "NonExistent")
