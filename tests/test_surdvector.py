"""
Exactness tests for SurdVector and SurdScalar: the squarefree-radical field.

Field identities, canonicalization, exact sign/ordering, and the crystallographic Cartesian use
cases are all asserted by EXACT equality (surd equality is coefficient equality); the few float
cross-checks are only there to pin down which side of a comparison is which.
"""

import copy
import decimal
import fractions
import math
import pickle
from typing import cast

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
    assert r == SurdVector(F(2, 3))
    assert r.is_rational
    assert r.radicands == (1,)


def test_sqrt_of_normalizes_rational_radicand() -> None:
    # sqrt(1/2) = sqrt(2)/2, radicand normalized to a squarefree integer.
    assert SurdVector.sqrt_of(F(1, 2)) == SurdVector.sqrt_of(2) * SurdVector(F(1, 2))
    assert SurdVector.sqrt_of(F(1, 2)).radicands == (2,)


def test_constructor_consumes_generator_once() -> None:
    assert SurdVector(x for x in (1, 2, 3)) == SurdVector([1, 2, 3])


def test_constructor_iterable_is_consumed_once() -> None:
    class CountingIterable:
        values = iter((1, 2, 3))
        consumed = 0

        def __iter__(self):
            return self

        def __next__(self):
            value = next(self.values, None)
            if value is None:
                raise StopIteration
            self.consumed += 1
            return value

    values = CountingIterable()
    assert SurdVector(values) == SurdVector([1, 2, 3])
    assert values.consumed == 3


def test_surdscalar_conversion_hook_runs_once() -> None:
    class CountingValue:
        conversions = 0

        def to_fractions(self):
            self.conversions += 1
            return F(3, 2)

    value = CountingValue()
    assert SurdScalar(value) == SurdScalar(F(3, 2))
    assert value.conversions == 1


def test_surdscalar_rejects_vector_shape() -> None:
    with pytest.raises(ValueError, match="SurdScalar"):
        SurdScalar([[1, 2]])


def test_surdvector_detaches_mutable_input() -> None:
    from httk.core.vectors import MutableFracVector

    source = MutableFracVector([1, 2])
    result = SurdVector(source)
    source[0] = 99

    assert isinstance(result.coefficient(1), FracVector)
    assert result.coefficient(1) == FracVector([1, 2])


@pytest.mark.parametrize("cls", [SurdVector, SurdScalar])
def test_bare_surd_construction_requires_value(cls) -> None:
    with pytest.raises(TypeError):
        cls()


def test_surdvector_and_surdscalar_copy_round_trip() -> None:
    for value in (SurdVector([1, 2]), SurdScalar("1/2")):
        assert pickle.loads(pickle.dumps(value)) == value
        assert copy.copy(value) == value
        assert copy.deepcopy(value) == value


def test_repr_uses_raw_constructor() -> None:
    value = SurdVector.from_components({1: FracVector.from_noms_and_denom((1, 2), 3)}, (2,))
    assert repr(value) == ("SurdVector.from_components({1: FracVector.from_noms_and_denom((1, 2), 3)}, (2,))")


def test_product_of_radicals_combines() -> None:
    s2 = SurdVector.sqrt_of(2)
    s3 = SurdVector.sqrt_of(3)
    assert s2 * s3 == SurdVector.sqrt_of(6)  # sqrt(2)*sqrt(3) = sqrt(6)
    assert SurdVector.sqrt_of(12) * SurdVector.sqrt_of(3) == SurdVector(6)  # sqrt(12)*sqrt(3) = 6
    assert s2 * s2 == SurdVector(2)  # sqrt(2)^2 = 2 (rational again)


def test_zero_handling() -> None:
    z = SurdVector.sqrt_of(0)
    assert z.is_zero()
    assert z == SurdVector(0)
    s2 = SurdVector.sqrt_of(2)
    assert (s2 - s2).is_zero()
    assert s2 * SurdVector(0) == SurdVector(0)


def test_negative_sqrt_raises() -> None:
    with pytest.raises(ValueError):
        SurdVector.sqrt_of(-1)


def test_canonical_equality_ignores_denominator_form() -> None:
    # Coefficients on different (unsimplified) denominators still compare equal.
    a = SurdVector.from_radicand_map({2: FracVector.from_noms_and_denom(((2,),), 4)})  # (2/4)*sqrt(2) = sqrt(2)/2
    b = SurdVector.from_radicand_map({2: FracVector.from_noms_and_denom(((1,),), 2)})
    assert a == b
    assert hash(a) == hash(b)


# --------------------------------------------------------------- field laws


_SURDS = [
    SurdVector(F(2, 3)),
    SurdVector.sqrt_of(2),
    SurdVector.sqrt_of(3),
    SurdVector.one() + SurdVector.sqrt_of(2),
    SurdVector.sqrt_of(2) - SurdVector.sqrt_of(6) * SurdVector(F(1, 2)),
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
    assert float(cast(SurdScalar, lhs).to_float()) < float(cast(SurdScalar, rhs).to_float())


def test_tight_pell_convergent_comparison_exercises_refinement() -> None:
    # 665857/470832 is a convergent of sqrt(2); it exceeds sqrt(2) by ~1e-12, decided exactly.
    convergent = SurdVector(F(665857, 470832))
    s2 = SurdVector.sqrt_of(2)
    assert convergent > s2
    assert not (convergent < s2)
    assert convergent != s2


def test_ordering_consistent_with_float_on_a_sample() -> None:
    samples = [
        SurdVector.sqrt_of(2),
        SurdVector.sqrt_of(3),
        SurdVector(F(3, 2)),
        SurdVector.sqrt_of(2) + SurdVector(F(1, 10)),
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
    assert (SurdVector.sqrt_of(2) - SurdVector(F(3, 2)))._as_scalar().sign() == -1
    assert (SurdVector.sqrt_of(2) - SurdVector(F(7, 5)))._as_scalar().sign() == 1
    assert SurdVector(0)._as_scalar().sign() == 0


# --------------------------------------------------------------- crystallographic


def _hexagonal_basis(a: fractions.Fraction, c: fractions.Fraction) -> SurdVector:
    """The standard hexagonal Cartesian basis B = [[a,0,0],[-a/2, a*sqrt3/2, 0],[0,0,c]]."""
    z = SurdVector(0)
    sqrt3 = SurdVector.sqrt_of(3)
    row0 = [SurdVector(a), z, z]
    row1 = [SurdVector(-a / 2), sqrt3 * SurdVector(a / 2), z]
    row2 = [z, z, SurdVector(c)]
    return SurdVector._from_scalar_grid([row0, row1, row2], (3, 3))


def _identity3() -> SurdVector:
    o = SurdVector(1)
    z = SurdVector(0)
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
        [
            SurdVector(F(1, 3)),
            SurdVector(F(1, 3)),
            SurdVector(F(1, 4)),
        ],
        (3,),
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
    # The second basis row itself is a Cartesian vector: [-a/2, a*sqrt3/2, 0], length a.
    row1 = SurdVector._from_scalar_grid(
        [
            SurdVector(-a / 2),
            SurdVector.sqrt_of(3) * SurdVector(a / 2),
            SurdVector(0),
        ],
        (3,),
    )
    assert row1.lengthsqr() == SurdVector(a * a)
    assert row1.length() == SurdVector(a)  # exact rational length here


def test_length_raises_on_irrational_lengthsqr() -> None:
    # A vector whose squared length is irrational (3 + 2 sqrt(2)) has a nested-radical length.
    v = SurdVector._from_scalar_grid(
        [
            SurdVector.one() + SurdVector.sqrt_of(2),
            SurdVector(0),
            SurdVector(0),
        ],
        (3,),
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
    val = SurdVector(F(1, 8))._as_scalar()
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


# --------------------------------------------------------------- Niven degree trigonometry


# cos 15 = (sqrt6 + sqrt2)/4, cos 75 = (sqrt6 - sqrt2)/4 (the 15-degree family);
# cos 36 = (1 + sqrt5)/4, cos 72 = (sqrt5 - 1)/4 (the 36-degree family).
_C15 = (SurdVector.sqrt_of(6) + SurdVector.sqrt_of(2)) / 4
_C75 = (SurdVector.sqrt_of(6) - SurdVector.sqrt_of(2)) / 4
_C36 = (SurdVector.one() + SurdVector.sqrt_of(5)) / 4
_C72 = (SurdVector.sqrt_of(5) - SurdVector.one()) / 4

# The full special-angle table over [0, 180]: exact cos/sin as SurdScalars. A sin entry of None
# marks the 36-family asymmetry: cos(36k) is an exact surd but sin(36k) = cos(90 - 36k) is not.
_NIVEN_TABLE = {
    0: (SurdVector.one(), SurdVector(0)),
    15: (_C15, _C75),
    30: (SurdVector.sqrt_of(3) / 2, SurdVector(F(1, 2))),
    36: (_C36, None),
    45: (SurdVector.sqrt_of(2) / 2, SurdVector.sqrt_of(2) / 2),
    60: (SurdVector(F(1, 2)), SurdVector.sqrt_of(3) / 2),
    72: (_C72, None),
    75: (_C75, _C15),
    90: (SurdVector(0), SurdVector.one()),
    105: (-_C75, _C15),
    108: (-_C72, None),
    120: (SurdVector(F(-1, 2)), SurdVector.sqrt_of(3) / 2),
    135: (-SurdVector.sqrt_of(2) / 2, SurdVector.sqrt_of(2) / 2),
    144: (-_C36, None),
    150: (-SurdVector.sqrt_of(3) / 2, SurdVector(F(1, 2))),
    165: (-_C15, _C75),
    180: (SurdVector(-1), SurdVector(0)),
}


def test_niven_cos_sin_forward_full_table() -> None:
    for angle, (cos_exp, sin_exp) in _NIVEN_TABLE.items():
        assert SurdScalar.cos_degrees(angle) == cos_exp, angle
        if sin_exp is None:
            assert SurdScalar.sin_degrees(angle) is None, angle
        else:
            assert SurdScalar.sin_degrees(angle) == sin_exp, angle


def test_niven_symmetry_and_reduction_cases() -> None:
    # Reduction mod 360 and sign symmetry: cos is even and 360-periodic, sin is odd.
    assert SurdScalar.cos_degrees(210) == -SurdVector.sqrt_of(3) / 2
    assert SurdScalar.cos_degrees(300) == SurdVector(F(1, 2))
    assert SurdScalar.cos_degrees(-60) == SurdScalar.cos_degrees(60)
    assert SurdScalar.cos_degrees(390) == SurdScalar.cos_degrees(30)
    assert SurdScalar.sin_degrees(210) == SurdVector(F(-1, 2))
    sin_60 = SurdScalar.sin_degrees(60)
    assert sin_60 is not None
    assert SurdScalar.sin_degrees(-60) == -sin_60
    # Accepts int, Fraction and numeric strings.
    assert SurdScalar.cos_degrees(F(60)) == SurdScalar.cos_degrees("60")


def test_niven_reverse_round_trip() -> None:
    for angle, (cos_exp, _sin_exp) in _NIVEN_TABLE.items():
        assert cos_exp._as_scalar().acos_degrees() == F(angle), angle
        # forward-then-reverse is the identity over [0, 180]
        assert SurdScalar.cos_degrees(angle)._as_scalar().acos_degrees() == F(angle)  # type: ignore[union-attr]


def test_niven_none_for_non_special_angles() -> None:
    # 20 degrees and 1/3 degree are multiples of neither 15 nor 36 -> None (a proof).
    assert SurdScalar.cos_degrees(20) is None
    assert SurdScalar.sin_degrees(20) is None
    assert SurdScalar.cos_degrees(F(1, 3)) is None
    # 54 = 90 - 36 is in neither family, so sin of the 36-family is not a surd:
    assert SurdScalar.cos_degrees(54) is None
    assert SurdScalar.sin_degrees(36) is None
    # A cosine value not in the table reverses to None.
    assert SurdVector(F(1, 3))._as_scalar().acos_degrees() is None


def test_niven_acos_domain_error() -> None:
    with pytest.raises(ValueError, match="domain"):
        SurdVector(2)._as_scalar().acos_degrees()
    with pytest.raises(ValueError, match="domain"):
        (SurdVector.sqrt_of(2) + SurdVector.one())._as_scalar().acos_degrees()


def test_niven_pythagorean_identity_exact() -> None:
    # Every multiple of 15 has both cos and sin exact in the field.
    for angle in range(0, 360, 15):
        c = SurdScalar.cos_degrees(angle)
        s = SurdScalar.sin_degrees(angle)
        assert c is not None and s is not None
        assert c * c + s * s == SurdVector.one(), angle


def test_niven_36_family_golden_identities() -> None:
    # cos 36 - cos 72 == 1/2 and cos 36 * cos 72 == 1/4 (golden-ratio identities), exactly:
    assert _C36 - _C72 == SurdVector(F(1, 2))
    assert _C36 * _C72 == SurdVector(F(1, 4))
    # Reverse lookup covers the 15- and 36-families:
    assert _C36._as_scalar().acos_degrees() == F(36)
    assert _C15._as_scalar().acos_degrees() == F(15)
    assert (-_C72)._as_scalar().acos_degrees() == F(108)
    assert _C75._as_scalar().acos_degrees() == F(75)


def test_surdscalar_supports_float() -> None:
    # float(x) on an exact scalar renders like to_float() (the deterministic approximation).
    assert float(SurdVector.sqrt_of(4)) == 2.0
    assert float(SurdVector.sqrt_of(2)) == SurdVector.sqrt_of(2).to_float()
    assert float(SurdVector(F(-3, 2))._as_scalar()) == -1.5
