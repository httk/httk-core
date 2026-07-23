"""
Tests for the exact-rational math helpers in httk.core.vectors.fracmath.

Exact rational properties are asserted exactly; the transcendental approximations are checked
for agreement with the corresponding math.* function within a tolerance.
"""

import fractions
import math

import pytest

from httk.core.vectors import fracmath

F = fractions.Fraction


def test_integer_sqrt() -> None:
    assert fracmath.integer_sqrt(0) == 0
    assert fracmath.integer_sqrt(16) == 4
    assert fracmath.integer_sqrt(17) == 4
    assert fracmath.integer_sqrt(10**12) == 10**6


def test_frac_sqrt_exact_for_perfect_squares() -> None:
    assert fracmath.frac_sqrt(F(4)) == F(2)
    assert fracmath.frac_sqrt(F(1, 4)) == F(1, 2)
    assert fracmath.frac_sqrt(F(9, 16)) == F(3, 4)


def test_frac_sqrt_two_agrees_with_math() -> None:
    assert abs(float(fracmath.frac_sqrt(F(2))) - math.sqrt(2)) < 1e-8


def test_frac_pi_default_reference_value() -> None:
    assert fracmath.frac_pi() == F(
        1812775448643948950904740389629316518445900010127,
        577024346734625462205756697620397878260206571339,
    )
    assert abs(float(fracmath.frac_pi()) - math.pi) < 1e-15


def test_any_to_fraction_string_min_accuracy() -> None:
    assert fracmath.any_to_fraction("0.33") == F(33, 100)
    assert fracmath.any_to_fraction("0.3333") == F(1, 3)
    assert fracmath.any_to_fraction("2/3") == F(2, 3)


def test_any_to_fraction_infinite_accuracy() -> None:
    assert fracmath.any_to_fraction("0.3333", min_accuracy=None) == F(3333, 10000)


def test_string_to_val_and_delta_uncertainty() -> None:
    val, delta = fracmath.string_to_val_and_delta("0.33342(10)")
    assert val == F(33342, 100000)
    assert delta == F(10, 100000)


def test_best_rational_in_interval() -> None:
    # 1/3 is the simplest rational in a tight interval around 0.3333.
    assert fracmath.best_rational_in_interval(F(33325, 100000), F(33345, 100000)) == F(1, 3)


def test_continued_fraction_roundtrip() -> None:
    cf = list(fracmath.get_continued_fraction(415, 93))
    assert cf == [4, 2, 6, 7]
    assert fracmath.fraction_from_continued_fraction(cf) == F(415, 93)


@pytest.mark.parametrize(
    "fn, mathfn, arg",
    [
        (fracmath.frac_cos, math.cos, F(1, 2)),
        (fracmath.frac_sin, math.sin, F(1, 2)),
        (fracmath.frac_exp, math.exp, F(3, 4)),
        (fracmath.frac_atan, math.atan, F(1, 3)),
        (fracmath.frac_acos, math.acos, F(1, 3)),
        (fracmath.frac_tan, math.tan, F(1, 4)),
        (fracmath.frac_log, math.log, F(1, 2)),
    ],
)
def test_transcendentals_agree_with_math(fn, mathfn, arg) -> None:  # type: ignore[no-untyped-def]
    assert abs(float(fn(arg)) - mathfn(float(arg))) < 1e-6


def test_frac_asin_agrees_and_exact_endpoints() -> None:
    assert abs(float(fracmath.frac_asin(F(1, 3))) - math.asin(1 / 3)) < 1e-6
    assert fracmath.frac_asin(F(0)) == F(0)
    assert fracmath.frac_asin(F(1)) == fracmath.frac_pi() / 2


def test_frac_cos_degrees() -> None:
    # cos(60 degrees) == 1/2 exactly (after simplification of the rational approximation).
    result = fracmath.frac_cos(F(60), degrees=True).limit_denominator(1000)
    assert result == F(1, 2)


def test_returns_are_fractions() -> None:
    assert isinstance(fracmath.frac_cos(F(1, 3)), fractions.Fraction)
    assert isinstance(fracmath.frac_sqrt(F(2)), fractions.Fraction)
