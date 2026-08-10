"""How precisely a number was written down.

None of this behaviour was ever covered before — the equivalent private helper in
*httk-io* had no test at all — so the cases its docstring claimed are pinned here, along
with the ones it got subtly wrong.
"""

import fractions

import pytest

from httk.core import combined_precision, decimal_precision

F = fractions.Fraction


# --- decimal_precision ---


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("0.123", F(1, 1000)),
        ("0.1", F(1, 10)),
        (".25", F(1, 100)),
        ("5.", F(1)),
        ("10", None),
        ("0", None),
        ("-3", None),
        ("0.000001", F(1, 1000000)),
    ],
    ids=[
        "three-decimals",
        "one-decimal",
        "leading-point",
        "trailing-point",
        "integer",
        "zero",
        "negative-integer",
        "six",
    ],
)
def test_precision_follows_the_digits_written(literal: str, expected: F | None) -> None:
    assert decimal_precision(literal) == expected


def test_the_sign_is_not_part_of_the_claim() -> None:
    assert decimal_precision("-0.5") == decimal_precision("+0.5") == decimal_precision("0.5") == F(1, 10)


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("1.2e-3", F(1, 10000)),
        ("1.2E-3", F(1, 10000)),
        ("1e3", F(1000)),
        ("2E2", F(100)),
        ("1e0", F(1)),
        ("0.5e1", F(1)),
    ],
)
def test_an_exponent_scales_the_precision(literal: str, expected: F) -> None:
    """The mantissa's digits set the precision; the exponent then moves it."""
    assert decimal_precision(literal) == expected


def test_precision_is_absolute_not_relative() -> None:
    """Magnitude is irrelevant — four decimals is four decimals."""
    assert decimal_precision("0.0001") == decimal_precision("9999.9999") == F(1, 10000)


def test_an_exact_rational_makes_no_precision_claim() -> None:
    """``1/3`` states a value rather than a measurement.

    Reporting a precision for it would let a single such coordinate drag a whole
    structure's precision down to the width of its last written digit, which is what the
    old ``0.0`` sentinel did.
    """
    assert decimal_precision("1/3") is None
    assert decimal_precision("-2/3") is None


@pytest.mark.parametrize("literal", ["", "   ", "?", ".", "abc", "1.2.3", "--1", "0x10", "1,5", "e5"])
def test_a_non_decimal_states_no_precision(literal: str) -> None:
    """Including CIF's ``?`` and ``.`` placeholders. A guess here would be worse than None."""
    assert decimal_precision(literal) is None


def test_missing_values_state_no_precision() -> None:
    assert decimal_precision(None) is None


def test_whitespace_is_ignored() -> None:
    assert decimal_precision("  0.25  ") == F(1, 100)


def test_the_result_is_exact_not_a_float() -> None:
    """``1e-4`` is representable exactly, and everything downstream stays exact."""
    precision = decimal_precision("0.0001")
    assert isinstance(precision, F)
    assert precision == F(1, 10000)
    assert float(precision) == 1e-4


# --- combined_precision ---


def test_the_coarsest_value_wins() -> None:
    """A structure is only as precisely stated as its least precisely stated number."""
    assert combined_precision(["0.123456", "0.5", "0.12"]) == F(1, 10)
    assert combined_precision(["0.123456", "0.123457"]) == F(1, 1000000)


def test_values_with_no_claim_are_skipped_not_treated_as_precise() -> None:
    """``1/3`` alongside four-decimal values must not change the answer."""
    assert combined_precision(["0.1234", "1/3", "?", None]) == F(1, 10000)


def test_integer_literals_make_no_precision_claim() -> None:
    assert combined_precision(["0", "10", "-3"]) is None
    assert combined_precision(["0", "0.5"]) == F(1, 10)


def test_no_claim_at_all_gives_none() -> None:
    assert combined_precision(["1/3", "?", None]) is None
    assert combined_precision([]) is None


def test_an_already_computed_precision_passes_through() -> None:
    """So a standard uncertainty read from a file can widen a digit-derived precision."""
    assert combined_precision([F(1, 10000), F(3, 10000)]) == F(3, 10000)
    assert combined_precision([F(1, 10000), 2]) == 2


def test_a_float_uncertainty_converts_through_its_decimal_spelling() -> None:
    """``0.005`` must land on 1/200, not on a binary approximation of it."""
    assert combined_precision([0.005]) == F(1, 200)
    assert combined_precision([F(1, 10000), 0.005]) == F(1, 200)


def test_a_digit_precision_wins_when_it_is_coarser_than_the_uncertainty() -> None:
    """The conservative reading: whichever claim is weaker is the one that holds."""
    assert combined_precision([decimal_precision("5.64"), 0.0003]) == F(1, 100)
    assert combined_precision([decimal_precision("5.6402"), 0.0003]) == F(3, 10000)


def test_nonsense_entries_are_ignored() -> None:
    assert combined_precision([True, False, "abc", 0, -1.0, "0.25"]) == F(1, 100)


def test_mixed_literals_and_precisions() -> None:
    assert combined_precision(["0.1234", F(1, 100), "0.123456"]) == F(1, 100)
