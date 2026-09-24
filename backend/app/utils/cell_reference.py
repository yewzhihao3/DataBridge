"""
app/utils/cell_reference.py — Excel cell reference parsing.

This module provides one public function (parse_cell_reference) and one
public data class (CellReference). It has no knowledge of FastAPI, SQLAlchemy,
or any business domain. It depends only on the standard library and openpyxl's
utility functions.

──────────────────────────────────────────────────────────────────────────────
Background: Excel cell reference formats

Excel refers to cells using a column letter followed by a row number:

    A1   — column A (1st column), row 1
    B2   — column B (2nd column), row 2
    AA10 — column AA (27th column), row 10

Absolute references use dollar signs to "lock" the row, column, or both:

    $B2   — absolute column B, relative row 2
    B$2   — relative column B, absolute row 2
    $B$2  — both locked

The dollar signs are meaningful inside Excel formulas (they prevent the
reference from shifting when a formula is copied). For DataBridge's purposes,
we only need the cell location itself, so we strip the dollar signs.

Column letters use a base-26 system:

    A  = 1
    Z  = 26
    AA = 27   (think: 1×26 + 1)
    AZ = 52   (think: 1×26 + 26)
    XFD = 16,384  (Excel's maximum column)

Rather than reimplementing this conversion, we delegate to openpyxl's
column_index_from_string(), which is well-tested and handles edge cases.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter


# ── Custom exception ──────────────────────────────────────────────────────────


class InvalidCellReference(ValueError):
    """
    Raised when an Excel cell reference string is malformed or out of range.

    Inherits from ValueError so callers can either:
        - Catch this specific exception for precise handling.
        - Catch the broader ValueError if they don't care about the cause.

    Example:
        try:
            ref = parse_cell_reference(user_input)
        except InvalidCellReference as e:
            return {"error": str(e)}
    """


# ── Regex pattern ─────────────────────────────────────────────────────────────

# This pattern matches valid Excel cell reference strings.
#
# Breakdown of each part:
#
#   ^           — start of string (no leading garbage allowed)
#   \$?         — optional dollar sign (absolute column marker)
#   ([A-Za-z]{1,3}) — capture group 1: one to three column letters
#                     (Excel columns go from A to XFD, so max 3 letters)
#   \$?         — optional dollar sign (absolute row marker)
#   (\d+)       — capture group 2: one or more digits for the row number
#   $           — end of string (no trailing garbage allowed)
#
# We allow lowercase letters here and normalise to uppercase after matching.
_CELL_REF_PATTERN: re.Pattern[str] = re.compile(
    r"^\$?([A-Za-z]{1,3})\$?(\d+)$"
)


# ── Data class ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CellReference:
    """
    A validated, parsed Excel cell reference.

    Attributes:
        row:      1-based row number.    A1 → row=1,  B2 → row=2.
        col:      1-based column number. A1 → col=1,  B1 → col=2, AA1 → col=27.
        original: The exact string that was parsed. Preserved for traceability
                  so error messages can quote the user's original input.

    frozen=True makes this dataclass immutable. Once created, its values
    cannot be changed. This prevents accidental modification as the object
    is passed between functions.

    Example:
        ref = parse_cell_reference("$B$2")
        ref.row      # 2
        ref.col      # 2
        ref.original # "$B$2"
        ref.to_a1()  # "B2"
    """

    row: int
    col: int
    original: str

    def to_a1(self) -> str:
        """
        Return the canonical, uppercase A1-notation string for this reference.

        The result always uses uppercase letters and no dollar signs,
        regardless of how the original string was written.

        Examples:
            parse_cell_reference("$b$2").to_a1()  == "B2"
            parse_cell_reference("AA10").to_a1()  == "AA10"
        """
        return f"{get_column_letter(self.col)}{self.row}"


# ── Public API ────────────────────────────────────────────────────────────────


def parse_cell_reference(ref: Any) -> CellReference:
    """
    Parse an Excel cell reference string into a CellReference.

    Accepts standard, absolute, and mixed references in any case:

        "B2"    → CellReference(row=2, col=2,  original="B2")
        "$B$2"  → CellReference(row=2, col=2,  original="$B$2")
        "$B2"   → CellReference(row=2, col=2,  original="$B2")
        "B$2"   → CellReference(row=2, col=2,  original="B$2")
        "AA10"  → CellReference(row=10, col=27, original="AA10")
        "b2"    → CellReference(row=2, col=2,  original="b2")   (normalised)
        "  B2 " → CellReference(row=2, col=2,  original="  B2 ") (trimmed)

    Args:
        ref: The cell reference to parse. Must be a non-empty string.
             The type annotation is Any so we can raise a descriptive
             InvalidCellReference instead of a bare TypeError for non-string
             inputs at runtime.

    Returns:
        A CellReference with row ≥ 1 and col ≥ 1.

    Raises:
        InvalidCellReference: If ref is not a string, is empty or whitespace,
            is malformed (e.g. "2B", "B", "2"), or refers to row 0.
    """
    # ── Guard: type and emptiness ─────────────────────────────────────────────
    #
    # We check isinstance before anything else. This means non-string inputs
    # (None, integers, lists) raise InvalidCellReference with a useful message
    # instead of an AttributeError or TypeError from a later .strip() call.
    #
    # Why `Any` as the parameter type?
    # The function's public contract says "pass a string". Using `str` as the
    # annotation would be accurate for type-checked code. However, at runtime,
    # Python does not enforce type hints. A caller might pass None or an integer.
    # Typing the parameter as `Any` lets us write the explicit isinstance check
    # and produce a clear, domain-specific error instead of a cryptic crash.
    if not isinstance(ref, str):
        raise InvalidCellReference(
            f"Cell reference must be a string, got {type(ref).__name__!r}. "
            f"Received: {ref!r}"
        )

    if not ref or not ref.strip():
        raise InvalidCellReference(
            "Cell reference must not be empty or whitespace."
        )

    cleaned = ref.strip()

    # ── Pattern match ─────────────────────────────────────────────────────────
    match = _CELL_REF_PATTERN.match(cleaned)
    if not match:
        raise InvalidCellReference(
            f"'{ref}' is not a valid Excel cell reference. "
            "Expected a format like 'B2', '$B$2', 'B$2', or 'AA10'. "
            "Column letters must come before the row number."
        )

    col_str: str = match.group(1).upper()   # normalise to uppercase
    row_str: str = match.group(2)
    row: int = int(row_str)

    # ── Row 0 guard ───────────────────────────────────────────────────────────
    #
    # The regex accepts any sequence of digits, including "0". Excel rows
    # start at 1, so "B0" is syntactically plausible but semantically invalid.
    if row == 0:
        raise InvalidCellReference(
            f"'{ref}' refers to row 0, which does not exist in Excel. "
            "Excel rows start at 1. Did you mean row 1?"
        )

    # ── Column letter to integer ──────────────────────────────────────────────
    #
    # openpyxl's column_index_from_string() validates that the column letters
    # are within the Excel maximum of XFD (column 16,384). It raises a plain
    # ValueError for invalid inputs. We catch that and re-raise as
    # InvalidCellReference so callers only need to handle one exception type.
    try:
        col: int = column_index_from_string(col_str)
    except ValueError as exc:
        raise InvalidCellReference(
            f"'{col_str}' is not a valid Excel column identifier. "
            f"Excel columns range from A to XFD (column 16,384)."
        ) from exc

    return CellReference(row=row, col=col, original=ref)


# ── Column Reference parsing ──────────────────────────────────────────────────

_COLUMN_REF_PATTERN: re.Pattern[str] = re.compile(r"^\$?([A-Za-z]{1,3})$")


def parse_column_reference(ref: Any) -> str:
    """
    Parse and validate an Excel column reference string (e.g. 'A', 'B', 'AA', '$B').

    Args:
        ref: The column reference to parse. Must be a non-empty string.

    Returns:
        The canonical uppercase column letter string (e.g. 'A', 'B', 'AA').

    Raises:
        InvalidCellReference: If ref is not a string, is empty or whitespace,
            or is not a valid Excel column identifier (A to XFD).
    """
    if not isinstance(ref, str):
        raise InvalidCellReference(
            f"Column reference must be a string, got {type(ref).__name__!r}. "
            f"Received: {ref!r}"
        )

    if not ref or not ref.strip():
        raise InvalidCellReference(
            "Column reference must not be empty or whitespace."
        )

    cleaned = ref.strip()

    match = _COLUMN_REF_PATTERN.match(cleaned)
    if not match:
        raise InvalidCellReference(
            f"'{ref}' is not a valid Excel column reference. "
            "Expected a column letter format like 'A', 'B', '$B', or 'AA'."
        )

    col_str: str = match.group(1).upper()
    try:
        column_index_from_string(col_str)
    except ValueError as exc:
        raise InvalidCellReference(
            f"'{col_str}' is not a valid Excel column identifier. "
            "Excel columns range from A to XFD (column 16,384)."
        ) from exc

    return col_str

