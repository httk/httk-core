"""
Exactness tests for SurdVector and SurdScalar: the squarefree-radical field.

Field identities, canonicalization, exact sign/ordering, and the crystallographic Cartesian use
cases are all asserted by EXACT equality (surd equality is coefficient equality); the few float
cross-checks are only there to pin down which side of a comparison is which.
"""

import decimal
import fractions
import math

import pytest

from httk.core.vectors import FracVector, SurdScalar, SurdVector
from httk.core.vectors._squarefree import square_part

F = fractions.Fraction


# --------------------------------------------------------------- square_part helper


def test_square_part_basic() -> None:
    assert square_part(1) == (1, 1)
    assert square_part(8) == (2, 2)
    assert square_part(12) == (2, 3)
    assert square_part(36) == (6, 1)
    assert square_part(72) == (6, 2)  # 72 = 36*2
    assert square_part(1000003) == (1, 1000003)  # a large prime stays squarefree


def test_square_part_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        square_part(0)


# --------------------------------------------------------------- canonicalization


def test_sqrt_of_extracts_square_part() -> None:
    assert SurdVector.sqrt_of(8) == SurdVector.from_radicand_map({2: 2})  # 2*sqrt(2)
    assert SurdVector.sqrt_of(12) == SurdVector.from_radicand_map({3: 2})  # 2*sqrt(3)


def test_sqrt_of_perfect_square_is_rational() -> None:
    r = SurdVector.sqrt_of(F(4, 9))
    assert r == SurdVector.create(F(2, 3))
    assert r.is_rational
    assert r.radicands == (1,)


def test_sqrt_of_normalizes_rational_radicand() -> None:
    # sqrt(1/2) = sqrt(2)/2, radicand normalized to a squarefree integer.
    assert SurdVector.sqrt_of(F(1, 2)) == SurdVector.sqrt_of(2) * SurdVector.create(F(1, 2))
    assert SurdVector.sqrt_of(F(1, 2)).radicands == (2,)


def test_product_of_radicals_combines() -> None:
    s2 = SurdVector.sqrt_of(2)
    s3 = SurdVector.sqrt_of(3)
    assert s2 * s3 == SurdVector.sqrt_of(6)  # sqrt(2)*sqrt(3) = sqrt(6)
    assert SurdVector.sqrt_of(12) * SurdVector.sqrt_of(3) == SurdVector.create(6)  # sqrt(12)*sqrt(3) = 6
    assert s2 * s2 == SurdVector.create(2)  # sqrt(2)^2 = 2 (rational again)


def test_zero_handling() -> None:
    z = SurdVector.sqrt_of(0)
    assert z.is_zero()
    assert z == SurdVector.create(0)
    s2 = SurdVector.sqrt_of(2)
    assert (s2 - s2).is_zero()
    assert s2 * SurdVector.create(0) == SurdVector.create(0)


def test_negative_sqrt_raises() -> None:
    with pytest.raises(ValueError):
        SurdVector.sqrt_of(-1)


def test_canonical_equality_ignores_denominator_form() -> None:
    # Coefficients on different (unsimplified) denominators still compare equal.
    a = SurdVector.from_radicand_map({2: FracVector([[2]], 4)})  # (2/4)*sqrt(2) = sqrt(2)/2
    b = SurdVector.from_radicand_map({2: FracVector([[1]], 2)})
    assert a == b
    assert hash(a) == hash(b)


# --------------------------------------------------------------- field laws


_SURDS = [
    SurdVector.create(F(2, 3)),
    SurdVector.sqrt_of(2),
    SurdVector.sqrt_of(3),
    SurdVector.one() + SurdVector.sqrt_of(2),
    SurdVector.sqrt_of(2) - SurdVector.sqrt_of(6) * SurdVector.create(F(1, 2)),
    SurdVector.sqrt_of(F(3, 2)),
]


def test_commutativity_and_associativity() -> None:
    for a in _SURDS:
        for b in _SURDS:
            assert a + b == b + a
            assert a * b == b * a
            for c in _SURDS:
                assert (a + b) + c == a + (b + c)
                assert (a * b) * c == a * (b * c)


def test_distributivity() -> None:
    for a in _SURDS:
        for b in _SURDS:
            for c in _SURDS:
                assert a * (b + c) == a * b + a * c


def test_field_inverse_multiplies_back_to_one() -> None:
    one = SurdVector.one()
    for a in _SURDS:
        assert a._as_scalar()._inverse() * a == one
    # The showcase three-radicand denominator.
    d = SurdVector.one() + SurdVector.sqrt_of(2) + SurdVector.sqrt_of(3)
    inv = SurdVector.one() / d
    assert inv * d == one


def test_division_operator() -> None:
    s2 = SurdVector.sqrt_of(2)
    assert SurdVector.one() / (SurdVector.one() + s2) == s2 - SurdVector.one()  # 1/(1+sqrt2) = sqrt2-1


# --------------------------------------------------------------- exact comparison


def test_sqrt2_plus_sqrt3_less_than_sqrt10() -> None:
    lhs = SurdVector.sqrt_of(2) + SurdVector.sqrt_of(3)  # ~3.146
    rhs = SurdVector.sqrt_of(10)  # ~3.162
    assert lhs < rhs
    assert rhs > lhs
    assert not (lhs > rhs)
    # sanity: the float ordering agrees
    assert float(lhs.to_float()) < float(rhs.to_float())


def test_tight_pell_convergent_comparison_exercises_refinement() -> None:
    # 665857/470832 is a convergent of sqrt(2); it exceeds sqrt(2) by ~1e-12, decided exactly.
    convergent = SurdVector.create(F(665857, 470832))
    s2 = SurdVector.sqrt_of(2)
    assert convergent > s2
    assert not (convergent < s2)
    assert convergent != s2


def test_ordering_consistent_with_float_on_a_sample() -> None:
    samples = [
        SurdVector.sqrt_of(2),
        SurdVector.sqrt_of(3),
        SurdVector.create(F(3, 2)),
        SurdVector.sqrt_of(2) + SurdVector.create(F(1, 10)),
        SurdVector.sqrt_of(F(7, 3)),
        SurdVector.one(),
    ]
    for a in samples:
        for b in samples:
            exact_lt = a._as_scalar() < b._as_scalar()
            fa, fb = float(a._as_scalar().to_float()), float(b._as_scalar().to_float())
            if abs(fa - fb) > 1e-9:
                assert exact_lt == (fa < fb)


def test_sign() -> None:
    assert (SurdVector.sqrt_of(2) - SurdVector.create(F(3, 2)))._as_scalar().sign() == -1
    assert (SurdVector.sqrt_of(2) - SurdVector.create(F(7, 5)))._as_scalar().sign() == 1
    assert SurdVector.create(0)._as_scalar().sign() == 0


# --------------------------------------------------------------- crystallographic


def _hexagonal_basis(a: fractions.Fraction, c: fractions.Fraction) -> SurdVector:
    """The standard hexagonal Cartesian basis B = [[a,0,0],[-a/2, a*sqrt3/2, 0],[0,0,c]]."""
    z = SurdVector.create(0)
    sqrt3 = SurdVector.sqrt_of(3)
    row0 = [SurdVector.create(a), z, z]
    row1 = [SurdVector.create(-a / 2), sqrt3 * SurdVector.create(a / 2), z]
    row2 = [z, z, SurdVector.create(c)]
    return SurdVector._from_scalar_grid([row0, row1, row2], (3, 3))


def _identity3() -> SurdVector:
    o = SurdVector.create(1)
    z = SurdVector.create(0)
    return SurdVector._from_scalar_grid([[o, z, z], [z, o, z], [z, z, o]], (3, 3))


def test_hexagonal_det_and_inverse_exact() -> None:
    a, c = F(3), F(5)
    B = _hexagonal_basis(a, c)
    # det = a * (a*sqrt3/2) * c = (a^2 c / 2) sqrt(3) = (45/2) sqrt(3)
    assert B.det() == SurdVector.from_radicand_map({3: F(45, 2)})
    Binv = B.inv()
    assert B * Binv == _identity3()
    assert Binv * B == _identity3()


def test_hexagonal_metric_is_rational_and_distances_agree() -> None:
    a, c = F(4), F(7)
    B = _hexagonal_basis(a, c)
    G = B * B.T()  # Gram/metric matrix
    assert G.is_rational  # metric of a metric-rational basis is rational
    # Two rational fractional sites; Cartesian difference = frac_diff * B (row-vector convention).
    frac_diff = SurdVector._from_scalar_grid(
        [SurdVector.create(F(1, 3)), SurdVector.create(F(1, 3)), SurdVector.create(F(1, 4))], (3,)
    )
    cart = frac_diff * B
    dist_sqr_cart = cart.lengthsqr()
    # Squared distance via the metric: d^2 = f * G * f^T (all rational).
    fG = frac_diff * G
    dist_sqr_metric = fG.dot(frac_diff)
    assert dist_sqr_cart == dist_sqr_metric
    assert dist_sqr_cart.is_rational  # canonicalizes to the same rational


def test_length_of_surd_cartesian_difference_is_exact() -> None:
    a = F(2)
    B = _hexagonal_basis(a, F(5))
    # The second basis row itself is a Cartesian vector: [-a/2, a*sqrt3/2, 0], length a.
    row1 = SurdVector._from_scalar_grid(
        [SurdVector.create(-a / 2), SurdVector.sqrt_of(3) * SurdVector.create(a / 2), SurdVector.create(0)], (3,)
    )
    assert row1.lengthsqr() == SurdVector.create(a * a)
    assert row1.length() == SurdVector.create(a)  # exact rational length here


def test_length_raises_on_irrational_lengthsqr() -> None:
    # A vector whose squared length is irrational (3 + 2 sqrt(2)) has a nested-radical length.
    v = SurdVector._from_scalar_grid(
        [SurdVector.one() + SurdVector.sqrt_of(2), SurdVector.create(0), SurdVector.create(0)], (3,)
    )
    assert not v.lengthsqr().is_rational
    with pytest.raises(ValueError, match="nested radical"):
        v.length()


# --------------------------------------------------------------- decimal rendering


def test_decimal_rendering_deterministic_and_matches_float() -> None:
    s2 = SurdVector.sqrt_of(2)._as_scalar()
    a = s2.to_decimal(digits=30)
    b = s2.to_decimal(digits=30)
    assert a == b  # deterministic across calls
    assert a == decimal.Decimal("1.41421356237309504880168872421")
    assert abs(float(a) - math.sqrt(2)) < 1e-25


def test_decimal_rational_surd_is_exact_finite_expansion() -> None:
    # A rational surd renders its finite decimal expansion exactly (honored, not quantized).
    val = SurdVector.create(F(1, 8))._as_scalar()
    assert val.to_decimal(digits=30) == decimal.Decimal("0.125")


def test_decimal_max_refinements_passthrough() -> None:
    # On a non-adversarial irrational surd, bounded mode agrees with the unbounded correct result
    # and is deterministic; the parameter is forwarded to the exactmath Ziv loop.
    s2 = SurdVector.sqrt_of(2)._as_scalar()
    bounded = s2.to_decimal(digits=10, max_refinements=0)
    assert bounded == s2.to_decimal(digits=10)
    assert bounded == s2.to_decimal(digits=10, max_refinements=0)  # deterministic
    with pytest.raises(ValueError, match="max_refinements"):
        s2.to_decimal(digits=5, max_refinements=-1)


def test_to_fractions_approx_is_within_prec() -> None:
    s2 = SurdVector.sqrt_of(2)._as_scalar()
    prec = F(1, 10**20)
    approx = s2._scalar_approx(prec)
    assert abs(approx * approx - 2) < F(1, 10**15)  # very close to sqrt(2)
    assert abs(float(approx) - math.sqrt(2)) < 1e-19
