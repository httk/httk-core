"""
Tests for the exact-math helpers in httk.core.vectors.exactmath.

Exact rational properties are asserted exactly; the transcendental approximations are checked
for agreement with the corresponding math.* function within a tolerance. The Decimal-mode tests
additionally assert exact type-preservation, exact short-circuits, correct rounding vs correct
truncation, determinism, and context-independence.
"""

import decimal
import fractions
import math

import pytest

from httk.core.vectors import exactmath

F = fractions.Fraction
D = decimal.Decimal


def test_integer_sqrt() -> None:
    assert exactmath.integer_sqrt(0) == 0
    assert exactmath.integer_sqrt(16) == 4
    assert exactmath.integer_sqrt(17) == 4
    assert exactmath.integer_sqrt(10**12) == 10**6


def test_sqrt_exact_for_perfect_squares() -> None:
    assert exactmath.sqrt(F(4)) == F(2)
    assert exactmath.sqrt(F(1, 4)) == F(1, 2)
    assert exactmath.sqrt(F(9, 16)) == F(3, 4)


def test_sqrt_two_agrees_with_math() -> None:
    assert abs(float(exactmath.sqrt(F(2))) - math.sqrt(2)) < 1e-8


def test_pi_default_reference_value() -> None:
    assert exactmath.pi() == F(
        1812775448643948950904740389629316518445900010127,
        577024346734625462205756697620397878260206571339,
    )
    assert abs(float(exactmath.pi()) - math.pi) < 1e-15


def test_any_to_fraction_string_min_accuracy() -> None:
    assert exactmath.any_to_fraction("0.33") == F(33, 100)
    assert exactmath.any_to_fraction("0.3333") == F(1, 3)
    assert exactmath.any_to_fraction("2/3") == F(2, 3)


def test_any_to_fraction_infinite_accuracy() -> None:
    assert exactmath.any_to_fraction("0.3333", min_accuracy=None) == F(3333, 10000)


def test_string_to_val_and_delta_uncertainty() -> None:
    val, delta = exactmath.string_to_val_and_delta("0.33342(10)")
    assert val == F(33342, 100000)
    assert delta == F(10, 100000)


def test_best_rational_in_interval() -> None:
    # 1/3 is the simplest rational in a tight interval around 0.3333.
    assert exactmath.best_rational_in_interval(F(33325, 100000), F(33345, 100000)) == F(1, 3)


def test_continued_fraction_roundtrip() -> None:
    cf = list(exactmath.get_continued_fraction(415, 93))
    assert cf == [4, 2, 6, 7]
    assert exactmath.fraction_from_continued_fraction(cf) == F(415, 93)


@pytest.mark.parametrize(
    "fn, mathfn, arg",
    [
        (exactmath.cos, math.cos, F(1, 2)),
        (exactmath.sin, math.sin, F(1, 2)),
        (exactmath.exp, math.exp, F(3, 4)),
        (exactmath.atan, math.atan, F(1, 3)),
        (exactmath.acos, math.acos, F(1, 3)),
        (exactmath.tan, math.tan, F(1, 4)),
        (exactmath.log, math.log, F(1, 2)),
    ],
)
def test_transcendentals_agree_with_math(fn, mathfn, arg) -> None:  # type: ignore[no-untyped-def]
    assert abs(float(fn(arg)) - mathfn(float(arg))) < 1e-6


# The legacy log algorithm is only practical for arguments reasonably close to 1 (its docstring
# notes it "fails for moderately large arguments"), so these stay small/fast.
_LOG_PREC = F(1, 10**8)


@pytest.mark.parametrize(
    "x, base",
    [(F(8), 2), (F(4), 2), (F(5), 10), (F(9), 3), (F(1, 4), 2)],
)
def test_log_with_integer_base(x: fractions.Fraction, base: int) -> None:
    # Regression: an integer base (or the integer argument reached by recursion) used to make
    # ``1/x`` a float and crash on ``x.numerator``. Now uses exact Fraction arithmetic.
    value = float(exactmath.log(x, base=base, prec=_LOG_PREC))
    assert abs(value - math.log(float(x), base)) < 1e-6


def test_log10_matches_math_log10() -> None:
    for x in [F(2), F(1, 3), F(3), F(7, 11)]:
        assert abs(float(exactmath.log10(x, prec=_LOG_PREC)) - math.log10(float(x))) < 1e-6


def test_log10_of_ten_is_exactly_one() -> None:
    # 10**1 is exact via the base == x shortcut; higher powers of ten are within the algorithm's
    # documented "moderately large argument" slow/inaccurate regime and are not exercised.
    assert exactmath.log10(F(10), prec=_LOG_PREC) == 1


def test_log_domain_errors() -> None:
    with pytest.raises(ValueError):
        exactmath.log(F(-1))
    with pytest.raises(ValueError):
        exactmath.log(F(0))
    with pytest.raises(ValueError):
        exactmath.log(F(5), base=1)


def test_asin_agrees_and_exact_endpoints() -> None:
    assert abs(float(exactmath.asin(F(1, 3))) - math.asin(1 / 3)) < 1e-6
    assert exactmath.asin(F(0)) == F(0)
    assert exactmath.asin(F(1)) == exactmath.pi() / 2


def test_cos_degrees() -> None:
    # cos(60 degrees) == 1/2 exactly (after simplification of the rational approximation).
    result = exactmath.cos(F(60), degrees=True).limit_denominator(1000)
    assert result == F(1, 2)


def test_returns_are_fractions() -> None:
    assert isinstance(exactmath.cos(F(1, 3)), fractions.Fraction)
    assert isinstance(exactmath.sqrt(F(2)), fractions.Fraction)


# ------------------------------------------------------------- atan2 fixes


def test_atan2_matches_math_atan2_in_all_quadrants_and_axes() -> None:
    # Legacy bugs: atan2(+-1, 0) returned 0 instead of +-pi/2, and atan2(0, -1)
    # returned -pi instead of +pi (math.atan2 convention).
    for y, x in [(1, 1), (1, 0), (-1, 0), (0, -1), (0, 1), (1, -1), (-1, -1), (0, 0), (-1, 1)]:
        got = float(exactmath.atan2(fractions.Fraction(y), fractions.Fraction(x)))
        assert abs(got - math.atan2(y, x)) < 1e-9, (y, x)


def test_atan2_degrees_flag_is_honored() -> None:
    # Legacy bug: the degrees parameter was accepted but ignored.
    # Axis cases cancel the pi approximation exactly; diagonals are approximations.
    assert exactmath.atan2(fractions.Fraction(1), fractions.Fraction(0), degrees=True) == 90
    assert exactmath.atan2(fractions.Fraction(-1), fractions.Fraction(0), degrees=True) == -90
    assert exactmath.atan2(fractions.Fraction(0), fractions.Fraction(-1), degrees=True) == 180
    assert abs(float(exactmath.atan2(fractions.Fraction(1), fractions.Fraction(1), degrees=True)) - 45) < 1e-8


# ============================================================= Decimal mode


def _independent_correctly_rounded_sqrt(x: fractions.Fraction, sig: int) -> decimal.Decimal:
    """
    Correctly-rounded (half-even) sqrt of a positive rational to ``sig`` significant digits,
    computed independently of exactmath using only :func:`math.isqrt` (exact integer square root)
    and exact integer/Fraction arithmetic — the cross-check for exactmath's Decimal-mode sqrt.
    """
    num, den = x.numerator, x.denominator
    # floor(sqrt(x) * 10^p) for a very high guard p, exactly, via isqrt of an integer.
    p = sig + 40
    floor_scaled = math.isqrt((num * 10 ** (2 * p)) // den)  # floor(sqrt(x) * 10^p)
    # e = floor(log10(sqrt(x))): the integer floor_scaled has e + p + 1 digits.
    e = len(str(floor_scaled)) - 1 - p
    # Round floor_scaled/10^p to sig significant digits, i.e. to the 10^(e-sig+1) place.
    drop = p - (sig - 1 - e)  # decimal places to remove from floor_scaled
    assert drop > 0
    q, r = divmod(floor_scaled, 10**drop)
    half = 10**drop
    twice = 2 * r
    if twice < half:
        m = q
    elif twice > half:
        m = q + 1
    else:  # exact half boundary — impossible for an irrational sqrt, handled defensively
        m = q if q % 2 == 0 else q + 1
    exponent = e - sig + 1
    return decimal.Decimal((0, tuple(int(c) for c in str(m)), exponent))


def test_type_preservation_matrix() -> None:
    # Fraction / int / str inputs (no digits=) -> Fraction; Decimal input or digits= -> Decimal.
    assert isinstance(exactmath.sqrt(F(2)), fractions.Fraction)
    assert isinstance(exactmath.sqrt(4), fractions.Fraction)
    assert isinstance(exactmath.sqrt(D(2)), decimal.Decimal)
    assert isinstance(exactmath.sqrt(F(2), digits=10), decimal.Decimal)
    # Mixed-argument promotion: any Decimal argument promotes the whole result to Decimal.
    assert isinstance(exactmath.atan2(D(1), F(1)), decimal.Decimal)
    assert isinstance(exactmath.atan2(F(1), D(1)), decimal.Decimal)
    assert isinstance(exactmath.atan2(F(1), F(1)), fractions.Fraction)
    # A Decimal base also promotes log.
    assert isinstance(exactmath.log(F(8), base=D(2)), decimal.Decimal)


def test_digits_forces_decimal_from_fraction_input() -> None:
    result = exactmath.sqrt(F(2), digits=10)
    assert isinstance(result, decimal.Decimal)
    assert result == decimal.Decimal("1.414213562")


def test_exact_short_circuits_are_exact_decimals() -> None:
    # Perfect square of a rational: sqrt(2.25) == 1.5 exactly (finite decimal expansion).
    assert exactmath.sqrt(D("2.25")) == D("1.5")
    assert exactmath.sqrt(F(9, 4), digits=30) == D("1.5")
    # cos of a special angle in degrees: cos(60 deg) == 0.5 exactly.
    assert exactmath.cos(D("60"), degrees=True) == D("0.5")
    assert exactmath.sin(D("30"), degrees=True) == D("0.5")
    # exp(0) == 1, log(1) == 0, atan2 axis in degrees are exact rationals.
    assert exactmath.exp(D(0)) == D(1)
    assert exactmath.log(D(1)) == D(0)
    assert exactmath.atan2(D(1), D(0), degrees=True) == D("90")


def test_sqrt_decimal_is_correctly_rounded() -> None:
    # sqrt(2) to 30 significant digits, cross-checked against an independent isqrt computation.
    got = exactmath.sqrt(D(2), digits=30)
    assert isinstance(got, decimal.Decimal)
    reference = _independent_correctly_rounded_sqrt(F(2), 30)
    assert got == reference
    # The exact digit string (30 significant digits, half-even).
    assert got == decimal.Decimal("1.41421356237309504880168872421")


def test_correct_rounding_versus_correct_truncation_near_a_boundary() -> None:
    # Construct an EXACT near-boundary case. At 2 significant digits the rounding boundary between
    # 1.2 and 1.3 sits exactly at 1.25 (half-even would send 1.25 -> 1.2). Take a value a hair
    # ABOVE the boundary: b = 1.25 + 1e-6, and feed sqrt(b**2) so the exact result is exactly b.
    b = F(125, 100) + F(1, 10**6)  # 1.250001, an exact rational just above the 2-sig-fig boundary
    x = b * b  # exact; sqrt(x) == b exactly via the perfect-square short-circuit
    # half-even rounds the value (just above 1.25) UP to 1.3; truncation toward zero gives 1.2.
    assert exactmath.sqrt(x, digits=2, rounding="half_even") == decimal.Decimal("1.3")
    assert exactmath.sqrt(x, digits=2, rounding="down") == decimal.Decimal("1.2")

    # And a hair BELOW the boundary: both modes give 1.2 (half-even rounds down, truncation too).
    b2 = F(125, 100) - F(1, 10**6)  # 1.249999
    x2 = b2 * b2
    assert exactmath.sqrt(x2, digits=2, rounding="half_even") == decimal.Decimal("1.2")
    assert exactmath.sqrt(x2, digits=2, rounding="down") == decimal.Decimal("1.2")


def test_exact_value_on_rounding_boundary_uses_exact_arithmetic() -> None:
    # sqrt(2.25) == 1.5 sits exactly on the 1-significant-digit boundary between 1 and 2.
    # Half-even resolves it exactly (1.5 -> 2, ties to even); down truncates exactly (1.5 -> 1).
    assert exactmath.sqrt(D("2.25"), digits=1, rounding="half_even") == decimal.Decimal("2")
    assert exactmath.sqrt(D("2.25"), digits=1, rounding="down") == decimal.Decimal("1")


def test_pi_digits_50_matches_known_reference() -> None:
    # The first 50 significant digits of pi, as an authoritative literal (independent of the
    # module's own high-precision pi rational — not self-certified through the tested code path).
    reference = decimal.Decimal("3.1415926535897932384626433832795028841971693993751")
    assert exactmath.pi(digits=50) == reference


def test_determinism_repeated_calls_identical() -> None:
    a = exactmath.sqrt(D(2), digits=40)
    b = exactmath.sqrt(D(2), digits=40)
    assert a == b
    c = exactmath.cos(D("60"), degrees=True)
    d = exactmath.cos(D("60"), degrees=True)
    assert c == d


def test_explicit_digits_is_independent_of_decimal_context() -> None:
    saved = decimal.getcontext().prec
    try:
        decimal.getcontext().prec = 5
        low_ctx = exactmath.sqrt(D(2), digits=30)
        decimal.getcontext().prec = 60
        high_ctx = exactmath.sqrt(D(2), digits=30)
    finally:
        decimal.getcontext().prec = saved
    assert low_ctx == high_ctx
    assert low_ctx == decimal.Decimal("1.41421356237309504880168872421")


def test_context_default_applies_without_explicit_digits() -> None:
    saved = decimal.getcontext().prec
    try:
        decimal.getcontext().prec = 10
        ten = exactmath.sqrt(D(2))
        decimal.getcontext().prec = 20
        twenty = exactmath.sqrt(D(2))
    finally:
        decimal.getcontext().prec = saved
    # Without digits=, the active context precision drives the significant-digit count.
    assert ten == decimal.Decimal("1.414213562")
    assert twenty == decimal.Decimal("1.4142135623730950488")
    assert ten != twenty


def test_invalid_rounding_and_digits_raise_eagerly() -> None:
    with pytest.raises(ValueError):
        exactmath.sqrt(D(2), rounding="sideways")
    with pytest.raises(ValueError):
        exactmath.sqrt(D(2), digits=0)
    with pytest.raises(ValueError):
        exactmath.sqrt(D(2), digits=-3)
    with pytest.raises(ValueError):
        exactmath.sqrt(F(2), digits=2, rounding="nope")


# ----------------------------------------------- termination guarantee completion


def test_rational_logarithms_are_decided_exactly() -> None:
    # log_base(x) = p/q iff x**q == base**p; q is bounded by base's largest prime
    # exponent, making rationality a finite exact decision. The exact tie log_4(8)
    # = 3/2 at one significant digit resolves by exact arithmetic in both modes.
    assert exactmath.log(decimal.Decimal(8), decimal.Decimal(4), digits=1) == decimal.Decimal("2")
    assert exactmath.log(decimal.Decimal(8), decimal.Decimal(4), digits=1, rounding="down") == decimal.Decimal("1")
    assert exactmath.log(decimal.Decimal(8), decimal.Decimal(4), digits=3) == decimal.Decimal("1.50")
    assert exactmath.log(decimal.Decimal(1024), decimal.Decimal(2), digits=2) == decimal.Decimal("10")
    assert exactmath.log(decimal.Decimal(8), decimal.Decimal("0.5"), digits=3) == decimal.Decimal("-3.00")
    # Irrational logarithms still take the adaptive path.
    assert str(exactmath.log(decimal.Decimal(3), decimal.Decimal(2), digits=20)) == "1.5849625007211561815"


def test_niven_special_values_are_exact_in_truncation_mode() -> None:
    # Truncating an approximation of an exact value must not lose the last digit:
    # these all previously returned 29.99-style results under rounding="down".
    assert exactmath.asin(decimal.Decimal("0.5"), degrees=True, digits=4, rounding="down") == decimal.Decimal("30")
    assert exactmath.asin(decimal.Decimal("-0.5"), degrees=True, digits=4, rounding="down") == decimal.Decimal("-30")
    assert exactmath.acos(decimal.Decimal("0.5"), degrees=True, digits=4, rounding="down") == decimal.Decimal("60")
    assert exactmath.acos(decimal.Decimal("-0.5"), degrees=True, digits=4, rounding="down") == decimal.Decimal("120")
    assert exactmath.atan(decimal.Decimal(1), degrees=True, digits=4, rounding="down") == decimal.Decimal("45")
    assert exactmath.atan(decimal.Decimal(-1), degrees=True, digits=4, rounding="down") == decimal.Decimal("-45")
    assert exactmath.tan(decimal.Decimal(45), degrees=True, digits=4, rounding="down") == decimal.Decimal("1")
    assert exactmath.tan(decimal.Decimal(135), degrees=True, digits=4, rounding="down") == decimal.Decimal("-1")
    assert exactmath.atan2(
        decimal.Decimal(1), decimal.Decimal(-1), degrees=True, digits=5, rounding="down"
    ) == decimal.Decimal("135")
    assert exactmath.atan2(
        decimal.Decimal(-1), decimal.Decimal(1), degrees=True, digits=5, rounding="down"
    ) == decimal.Decimal("-45")


# --------------------------------------------------------------- bounded-time mode


def test_max_refinements_bounds_time_and_stays_deterministic() -> None:
    # Adversarial construction: sqrt((1.25 + 1e-40)**2) at two significant digits sits
    # 1e-40 above the half-even boundary 1.25. Correct rounding needs ~10 refinements;
    # bounded mode stops early and deterministically rounds the approximant instead.
    boundary = fractions.Fraction(125, 100) + fractions.Fraction(1, 10**40)
    x = boundary * boundary
    assert exactmath.sqrt(x, digits=2) == decimal.Decimal("1.3")  # unbounded: correct
    bounded = exactmath.sqrt(x, digits=2, max_refinements=0)
    # Within one ulp of the correct result, and perfectly repeatable:
    assert bounded in (decimal.Decimal("1.2"), decimal.Decimal("1.3"))
    assert bounded == exactmath.sqrt(x, digits=2, max_refinements=0)
    # On non-adversarial values the bounded mode agrees with the correct result:
    assert exactmath.sqrt(decimal.Decimal(2), digits=10, max_refinements=0) == exactmath.sqrt(
        decimal.Decimal(2), digits=10
    )
    assert exactmath.pi(digits=20, max_refinements=1) == exactmath.pi(digits=20)


def test_max_refinements_validation() -> None:
    with pytest.raises(ValueError, match="max_refinements"):
        exactmath.sqrt(decimal.Decimal(2), digits=5, max_refinements=-1)
    with pytest.raises(ValueError, match="max_refinements"):
        exactmath.sqrt(decimal.Decimal(2), digits=5, max_refinements=1.5)  # type: ignore[arg-type]
