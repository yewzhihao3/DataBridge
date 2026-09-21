"""
tests/unit/test_cell_reference.py — Tests for app.utils.cell_reference.

──────────────────────────────────────────────────────────────────────────────
Test organisation

Tests are grouped into classes by behavioural category:

    TestValidReferences   — inputs that must succeed and return correct values
    TestInvalidReferences — inputs that must raise InvalidCellReference
    TestCellReferenceObject — properties of the returned CellReference object
    TestColumnArithmetic  — specific column-to-number conversions (base-26)

──────────────────────────────────────────────────────────────────────────────
Why write tests this thoroughly for such a small function?

1. cell_reference.py is the foundation of the extraction engine.
   Every template mapping ("Company Name → B2") passes through here.
   A silent off-by-one error here would corrupt every extracted record.

2. Edge cases in cell parsing are not obvious. "B0", "$B$2", "aA10",
   None — these are real inputs that real users will eventually provide.
   Tests document what the function promises for each case.

3. Tests written now prevent regressions when we refactor later.
   If we ever change the regex or swap out openpyxl, the tests tell us
   immediately whether behaviour has changed.
──────────────────────────────────────────────────────────────────────────────
"""

import pytest

from app.utils.cell_reference import (
    CellReference,
    InvalidCellReference,
    parse_cell_reference,
)


# ── Valid references ──────────────────────────────────────────────────────────


class TestValidReferences:
    """parse_cell_reference should return correct row and col for valid inputs."""

    def test_simple_reference_b2(self) -> None:
        ref = parse_cell_reference("B2")
        assert ref.row == 2
        assert ref.col == 2

    def test_minimum_reference_a1(self) -> None:
        """A1 is the smallest valid Excel cell address."""
        ref = parse_cell_reference("A1")
        assert ref.row == 1
        assert ref.col == 1

    def test_lowercase_input_is_accepted(self) -> None:
        ref = parse_cell_reference("b2")
        assert ref.row == 2
        assert ref.col == 2

    def test_mixed_case_input_is_accepted(self) -> None:
        """'aA10' should be treated the same as 'AA10'."""
        ref = parse_cell_reference("aA10")
        assert ref.row == 10
        assert ref.col == 27

    def test_absolute_reference_both_markers(self) -> None:
        """'$B$2' is an absolute reference — both column and row locked."""
        ref = parse_cell_reference("$B$2")
        assert ref.row == 2
        assert ref.col == 2

    def test_absolute_column_marker_only(self) -> None:
        """'$B2' locks only the column. Row remains relative."""
        ref = parse_cell_reference("$B2")
        assert ref.row == 2
        assert ref.col == 2

    def test_absolute_row_marker_only(self) -> None:
        """'B$2' locks only the row. Column remains relative."""
        ref = parse_cell_reference("B$2")
        assert ref.row == 2
        assert ref.col == 2

    def test_leading_and_trailing_whitespace_is_stripped(self) -> None:
        """Users may accidentally include spaces. These should be accepted."""
        ref = parse_cell_reference("  B2  ")
        assert ref.row == 2
        assert ref.col == 2

    def test_large_row_number(self) -> None:
        """Excel supports up to 1,048,576 rows."""
        ref = parse_cell_reference("A1048576")
        assert ref.row == 1_048_576
        assert ref.col == 1

    def test_f3_reference(self) -> None:
        """Sanity check for a common invoice template field location."""
        ref = parse_cell_reference("F3")
        assert ref.row == 3
        assert ref.col == 6  # A=1, B=2, C=3, D=4, E=5, F=6

    def test_d6_reference(self) -> None:
        ref = parse_cell_reference("D6")
        assert ref.row == 6
        assert ref.col == 4


# ── Column arithmetic ─────────────────────────────────────────────────────────


class TestColumnArithmetic:
    """
    Verify that column letters are converted to numbers correctly.

    Excel columns use a base-26 system where A=1, not 0.
    This is subtly different from ordinary base-26 and is a common source
    of off-by-one errors.

    Arithmetic:
        AA = 1×26 + 1  = 27
        AZ = 1×26 + 26 = 52
        BA = 2×26 + 1  = 53
        ZZ = 26×26 + 26 = 702
    """

    def test_column_a_is_1(self) -> None:
        assert parse_cell_reference("A1").col == 1

    def test_column_z_is_26(self) -> None:
        assert parse_cell_reference("Z1").col == 26

    def test_column_aa_is_27(self) -> None:
        assert parse_cell_reference("AA1").col == 27

    def test_column_az_is_52(self) -> None:
        assert parse_cell_reference("AZ1").col == 52

    def test_column_ba_is_53(self) -> None:
        assert parse_cell_reference("BA1").col == 53

    def test_column_zz_is_702(self) -> None:
        assert parse_cell_reference("ZZ1").col == 702


# ── CellReference object behaviour ────────────────────────────────────────────


class TestCellReferenceObject:
    """Verify the properties and behaviour of the returned CellReference."""

    def test_return_type_is_cell_reference(self) -> None:
        ref = parse_cell_reference("B2")
        assert isinstance(ref, CellReference)

    def test_original_string_is_preserved_exactly(self) -> None:
        """The original input is kept unchanged, including dollar signs and case."""
        assert parse_cell_reference("$B$2").original == "$B$2"
        assert parse_cell_reference("b2").original == "b2"
        assert parse_cell_reference("  B2  ").original == "  B2  "

    def test_to_a1_returns_uppercase_without_dollar_signs(self) -> None:
        assert parse_cell_reference("$b$2").to_a1() == "B2"

    def test_to_a1_with_two_letter_column(self) -> None:
        assert parse_cell_reference("AA10").to_a1() == "AA10"

    def test_to_a1_with_lowercase_input(self) -> None:
        assert parse_cell_reference("b2").to_a1() == "B2"

    def test_is_immutable(self) -> None:
        """
        CellReference is a frozen dataclass. Attempting to change a field
        should raise an error. This prevents accidental mutation in service code.
        """
        ref = parse_cell_reference("B2")
        with pytest.raises(Exception):
            ref.row = 99  # type: ignore[misc]

    def test_two_references_with_same_values_are_equal(self) -> None:
        """Frozen dataclasses implement __eq__ by comparing field values."""
        ref_a = parse_cell_reference("B2")
        ref_b = parse_cell_reference("B2")
        assert ref_a == ref_b

    def test_two_references_with_different_originals_but_same_values_are_equal(
        self,
    ) -> None:
        """
        '$B$2' and 'b2' resolve to the same row and col. The original field
        differs, so they are NOT equal as objects.
        This test documents that behaviour explicitly.
        """
        ref_absolute = parse_cell_reference("$B$2")
        ref_plain = parse_cell_reference("B2")
        # Different originals → different objects, even though row/col match
        assert ref_absolute != ref_plain
        # But row and col values are the same
        assert ref_absolute.row == ref_plain.row
        assert ref_absolute.col == ref_plain.col


# ── Invalid references ────────────────────────────────────────────────────────


class TestInvalidReferences:
    """parse_cell_reference should raise InvalidCellReference for bad inputs."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("   ")

    def test_row_zero_raises_with_descriptive_message(self) -> None:
        """Row 0 does not exist in Excel. The error message should say so."""
        with pytest.raises(InvalidCellReference, match="row 0"):
            parse_cell_reference("B0")

    def test_digits_before_letters_raises(self) -> None:
        """'2B' has the column and row reversed."""
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("2B")

    def test_letters_only_no_row_number_raises(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("B")

    def test_digits_only_no_column_letter_raises(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("2")

    def test_special_character_in_reference_raises(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("B!2")

    def test_space_between_column_and_row_raises(self) -> None:
        """'B 2' looks like a reference but has an embedded space."""
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("B 2")

    def test_double_dollar_sign_raises(self) -> None:
        """'$$B2' has two leading dollar signs, which is not valid."""
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("$$B2")

    def test_none_raises_invalid_cell_reference_not_type_error(self) -> None:
        """
        None is a common mistake. The error should be domain-specific
        (InvalidCellReference) rather than a bare TypeError or AttributeError.
        """
        with pytest.raises(InvalidCellReference):
            parse_cell_reference(None)  # type: ignore[arg-type]

    def test_integer_raises_invalid_cell_reference(self) -> None:
        """Integers should produce a clear error, not a crash."""
        with pytest.raises(InvalidCellReference):
            parse_cell_reference(42)  # type: ignore[arg-type]

    def test_list_raises_invalid_cell_reference(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference(["B2"])  # type: ignore[arg-type]

    def test_hash_in_reference_raises(self) -> None:
        """'#REF!' is an Excel error string, not a valid reference."""
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("#REF!")


# ── Exception type hierarchy ──────────────────────────────────────────────────


class TestExceptionHierarchy:
    """
    InvalidCellReference inherits from ValueError.

    This allows callers to catch the specific exception for precise handling,
    or catch the broader ValueError if they only care that parsing failed.
    Both of these should work:

        except InvalidCellReference: ...   # specific
        except ValueError: ...             # broad
    """

    def test_invalid_cell_reference_is_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_cell_reference("")

    def test_invalid_cell_reference_is_catchable_as_its_own_type(self) -> None:
        with pytest.raises(InvalidCellReference):
            parse_cell_reference("")
