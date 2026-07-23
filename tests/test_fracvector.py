"""
Exactness tests for FracVector and FracScalar.

Every assertion checks EXACT equality of noms/denom (or exact Fraction equality), seeded from
the legacy embedded reference values; nothing here uses approximate comparison except where the
legacy semantics themselves approximate (limit_denominator, string min_accuracy, transcendentals),
which are pinned to their exact expected rationals.
"""

import decimal
import fractions

import pytest

from httk.core.vectors import FracScalar, FracVector

F = fractions.Fraction


# ------------------------------------------------------------------ creation


def test_create_from_ints_with_denominator() -> None:
    v = FracVector.create([[804, 0, 0], [0, 372, 0], [0, 0, 738]], 100)
    # simplify shares the gcd(=2) out of the denominator
    assert v.noms == ((402, 0, 0), (0, 186, 0), (0, 0, 369))
    assert v.denom == 50


def test_create_from_decimal_strings_matches_int_form() -> None:
    strings = FracVector.create([["8.04", "0.0", "0.0"], ["0.0", "3.72", "0.0"], ["0.0", "0.0", "7.38"]])
    ints = FracVector.create([[804, 0, 0], [0, 372, 0], [0, 0, 738]], 100)
    assert strings.noms == ints.noms
    assert strings.denom == ints.denom


def test_create_from_python_float_is_binary_rational() -> None:
    # A Python float literal is a binary rational; 8.04 is NOT 804/100.
    v = FracVector.create([8.04])
    assert v.to_fractions() == [fractions.Fraction(8.04)]
    assert v != FracVector.create(["8.04"])


def test_create_from_decimal() -> None:
    v = FracVector.create([decimal.Decimal("0.25"), decimal.Decimal("1.5"), decimal.Decimal("2.125")])
    assert v.noms == (2, 12, 17)
    assert v.denom == 8


def test_create_from_fraction() -> None:
    v = FracVector.create(
        [[F(185, 23), 0, 0], [0, F(67, 18), 0], [0, 0, F(59, 8)]]
    )
    assert v.noms == ((13320, 0, 0), (0, 6164, 0), (0, 0, 12213))
    assert v.denom == 1656


def test_create_string_min_accuracy_default() -> None:
    # 0.33 assumed to be 0.3300 = 33/100; 0.3333 assumed to mean 1/3.
    assert FracVector.create("0.33").to_fraction() == F(33, 100)
    assert FracVector.create("0.3333").to_fraction() == F(1, 3)


def test_create_string_infinite_accuracy() -> None:
    assert FracVector.create("0.33", min_accuracy=None).to_fraction() == F(33, 100)
    assert FracVector.create("0.3333", min_accuracy=None).to_fraction() == F(3333, 10000)


def test_create_uncertainty_string() -> None:
    assert FracVector.create(["0.33342(10)"]).noms == (1,)
    assert FracVector.create(["0.33342(10)"]).denom == 3
    assert FracVector.create(["0.33352(10)"]).noms == (388,)
    assert FracVector.create(["0.33352(10)"]).denom == 1163
    both = FracVector.create(["0.33342(10)", "0.33352(10)"])
    assert both.noms == (1163, 1164)
    assert both.denom == 3489


def test_create_fraction_string() -> None:
    assert FracVector.create("2/3").to_fraction() == F(2, 3)


# ------------------------------------------------------------------ simplify / resolution


def test_third_times_three_simplifies_to_one() -> None:
    v = (FracVector.create("1/3") * 3).simplify()
    assert v == 1
    assert v.noms == 1
    assert v.denom == 1


def test_simplify_shares_common_denominator() -> None:
    v = FracVector(((2, 4), (6, 8)), 4).simplify()
    assert v.noms == ((1, 2), (3, 4))
    assert v.denom == 2


def test_set_denominator() -> None:
    v = FracVector.create([["1/3", "2/7"]]).set_denominator(1000)
    assert v.denom == 1000
    assert v.noms == ((333, 286),)


def test_limit_denominator_recovers_small_rational() -> None:
    binary = F(6004799503160661, 18014398509481984)  # float64 of 1/3
    v = FracVector.create([[binary]]).limit_denominator(1000)
    assert v == FracVector.create([["1/3"]])


def test_floor_and_ceil() -> None:
    assert FracVector.create("-7/3").floor() == -3
    assert FracVector.create("-7/3").ceil() == -2
    assert FracVector.create("7/3").floor() == 2
    assert FracVector.create("7/3").ceil() == 3


def test_sign() -> None:
    assert FracVector.create("-3/4").sign() == -1
    assert FracVector.create("0").sign() == 0
    assert FracVector.create("5").sign() == 1


# ------------------------------------------------------------------ operators


def test_multiplication_is_matrix_multiply() -> None:
    a = FracVector.create([[1, 2], [3, 4]])
    identity = FracVector.create([[1, 0], [0, 1]])
    assert (a * identity) == a


def test_addition_across_denominators() -> None:
    v = (FracVector.create([["1/2", "1/3"]]) + FracVector.create([["1/6", "1/6"]])).simplify()
    assert v.noms == ((4, 3),)  # [2/3, 1/2] on the shared denominator 6
    assert v.denom == 6


def test_subtraction() -> None:
    v = FracVector.create([[5, 6, 7]]) - FracVector.create([[1, 2, 3]])
    assert v == FracVector.create([[4, 4, 4]])


def test_truediv_scalar() -> None:
    v = (FracVector.create([[1, 2], [3, 4]]) / FracVector.create("2")).simplify()
    assert v == FracVector.create([["1/2", "1"], ["3/2", "2"]])


def test_pow_minus_one_is_inverse() -> None:
    a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    assert (a**-1).simplify() == a.inv().simplify()


def test_pow_positive() -> None:
    a = FracVector.create([[1, 1], [0, 1]])
    assert a**3 == FracVector.create([[1, 3], [0, 1]])


# ------------------------------------------------------------------ linear algebra


def test_transpose() -> None:
    a = FracVector.create([[1, 2, 3], [4, 5, 6]])
    assert a.T() == FracVector.create([[1, 4], [2, 5], [3, 6]])


def test_det_3x3() -> None:
    assert FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]]).det() == -3


def test_det_4x4() -> None:
    a = FracVector.create([[1, 2, 3, 4], [2, 1, 4, 3], [3, 4, 1, 2], [4, 3, 2, 7]])
    assert a.det() == 120


def test_inv_3x3_exact() -> None:
    a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    inv = a.inv().simplify()
    assert inv.noms == ((-11, -9, 13), (5, 6, -7), (2, 0, -1))
    assert inv.denom == 3
    assert (a * inv).simplify() == FracVector.eye((3, 3))


def test_dot() -> None:
    assert FracVector.create([1, 2, 3]).dot(FracVector.create([4, 5, 6])) == 32


def test_cross() -> None:
    v = FracVector.create([1, 2, 3]).cross(FracVector.create([4, 5, 6]))
    assert v == FracVector.create([-3, 6, -3])


def test_lengthsqr() -> None:
    assert FracVector.create([3, 4, 12]).lengthsqr() == 169


def test_metric_product() -> None:
    metric = FracVector.create([[2, 0, 0], [0, 3, 0], [0, 0, 4]])
    v = FracVector.create([1, 1, 1])
    assert metric.metric_product(v, v) == 9


def test_reciprocal_issue_60_reference() -> None:
    cell = FracVector.create([["8.04", "0.0", "0.0"], ["0.0", "3.72", "0.0"], ["0.0", "0.0", "7.38"]])
    recip = cell.reciprocal()
    assert recip.noms == ((3431700, 0, 0), (0, 7416900, 0), (0, 0, 3738600))
    assert recip.denom == 27590868


# ------------------------------------------------------------------ normalize


def test_normalize_into_unit_range() -> None:
    v = FracVector.create([["7/3", "-1/6", "5/2"]]).normalize().simplify()
    assert v == FracVector.create([["1/3", "5/6", "1/2"]])


def test_normalize_half_into_symmetric_range() -> None:
    v = FracVector.create([["7/3", "-1/6", "5/2"]]).normalize_half().simplify()
    assert v == FracVector.create([["1/3", "-1/6", "-1/2"]])


# ------------------------------------------------------------------ conversions / round-trips


def test_to_floats() -> None:
    assert FracVector.create([[1, 2], [3, 4]], 7).to_floats() == [[1 / 7, 2 / 7], [3 / 7, 4 / 7]]


def test_to_ints_rounds() -> None:
    assert FracVector.create([["7/3", "8/3"]]).to_ints() == [[2, 3]]


def test_to_strings() -> None:
    assert FracVector.create([["1/3", "2/3"]]).to_strings(6) == [["0.333333", "0.666667"]]


def test_to_fractions_roundtrip() -> None:
    a = FracVector.create([["1/3", "2/5"], ["3/7", "4/9"]])
    assert FracVector.create(a.to_fractions()) == a


def test_to_tuple_exact() -> None:
    a = FracVector.create([[1, 2, 3], [4, 5, 6]], 7)
    assert a.to_tuple() == (7, ((1, 2, 3), (4, 5, 6)))


# ------------------------------------------------------------------ equality / ordering / hash / indexing


def test_equality_across_denominators() -> None:
    assert FracVector.create([["2/4"]]) == FracVector.create([["1/2"]])
    assert FracVector(((1,),), 2) == FracVector(((2,),), 4)


def test_ordering_scalars() -> None:
    assert FracVector.create("1/3") < FracVector.create("1/2")
    assert FracVector.create("5/2") > FracVector.create("2")
    assert FracVector.create("1/3") <= FracVector.create("1/3")


def test_hash_matches_for_equal_representation() -> None:
    assert hash(FracVector(((1, 2), (3, 4)), 2)) == hash(FracVector(((1, 2), (3, 4)), 2))


def test_indexing_single_axis() -> None:
    a = FracVector.create([[1, 2, 3], [4, 5, 6]])
    assert a[0] == FracVector.create([1, 2, 3])
    assert a[1, 2] == FracVector.create(6)


def test_indexing_multi_axis_tuple_slice() -> None:
    a = FracVector.create([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert a[1:, 1:] == FracVector.create([[5, 6], [8, 9]])
    assert a[:, 0] == FracVector.create([1, 4, 7])


def test_iteration_yields_rows() -> None:
    a = FracVector.create([[1, 2], [3, 4]])
    rows = list(a)
    assert rows == [FracVector.create([1, 2]), FracVector.create([3, 4])]


def test_max_min_argmax() -> None:
    a = FracVector.create([2, 7, 5])
    assert a.max() == 7
    assert a.min() == 2
    assert a.argmax() == 1
    assert a.argmin() == 0


# ------------------------------------------------------------------ FracScalar


def test_fracscalar_creation_and_conversions() -> None:
    s = FracScalar.create("3/4")
    assert isinstance(s, FracScalar)
    assert s.nom == 3
    assert s.denom == 4
    assert float(s) == 0.75
    assert s.to_fraction() == F(3, 4)


def test_fracscalar_create_ignores_min_accuracy() -> None:
    # Unlike FracVector.create, FracScalar.create converts strings exactly (legacy behavior).
    assert FracScalar.create("0.33").to_fraction() == F(33, 100)


# ------------------------------------------------------------------ stacking / chaining


def test_chain_and_stack_vecs() -> None:
    a = FracVector.create([1, 2, 3])
    b = FracVector.create([4, 5, 6])
    assert FracVector.chain_vecs([a, b]) == FracVector.create([1, 2, 3, 4, 5, 6])
    assert FracVector.stack_vecs([a, b]) == FracVector.create([[1, 2, 3], [4, 5, 6]])


def test_get_append_extend() -> None:
    b = FracVector.create([1, 2, 3])
    assert b.get_append(4) == FracVector.create([1, 2, 3, 4])
    assert b.get_extend(FracVector.create([4, 5, 6])) == FracVector.create([1, 2, 3, 4, 5, 6])


def test_get_stackedinsert_rename() -> None:
    # The legacy misspellings ged_prestacked/ged_stackedinsert are renamed to get_*.
    assert hasattr(FracVector, "get_prestacked")
    assert hasattr(FracVector, "get_stackedinsert")
    assert not hasattr(FracVector, "ged_prestacked")
    assert not hasattr(FracVector, "ged_stackedinsert")


def test_immutable_setitem_raises() -> None:
    with pytest.raises(Exception):
        FracVector.create([1, 2, 3])[0] = 5


# ------------------------------------------------------------------ from_tuple / to_tuple round-trip


@pytest.mark.parametrize(
    "v",
    [
        FracVector.create([[1, 2, 3], [4, 5, 6]], 7),
        FracVector.create([1, 2, 3]),
        FracScalar.create("3/4"),
        FracVector.create([[["1/3", "2/5"]], [["3/7", "4/9"]]]),
    ],
)
def test_from_tuple_inverts_to_tuple(v: FracVector) -> None:
    # Corrected: legacy from_tuple used t[1:], double-wrapping noms, so it never round-tripped.
    assert FracVector.from_tuple(v.to_tuple()) == v
    rebuilt = FracVector.from_tuple(v.to_tuple())
    assert rebuilt.noms == v.noms
    assert rebuilt.denom == v.denom


# ------------------------------------------------------------------ stacked helpers (corrected)


def test_get_stacked_adds_leading_axis() -> None:
    # Corrected: legacy wrapped `other` in an extra list, giving a ragged result.
    assert FracVector.create([1, 2, 3]).get_stacked([4, 5, 6]) == FracVector.create([[1, 2, 3], [4, 5, 6]])
    assert FracVector.create([1, 2, 3]).get_prestacked([4, 5, 6]) == FracVector.create([[4, 5, 6], [1, 2, 3]])


def test_get_stacked_matrices() -> None:
    a = FracVector.create([[1, 2], [3, 4]])
    b = FracVector.create([[5, 6], [7, 8]])
    stacked = a.get_stacked(b)
    assert stacked.dim == (2, 2, 2)
    assert stacked[0] == a and stacked[1] == b


# ------------------------------------------------------------------ use() live to_FracVector path


class _HasToFracVector:
    def to_FracVector(self) -> FracVector:
        return FracVector.create([[1, 2], [3, 4]])


def test_use_returns_plain_fracvector_unchanged() -> None:
    v = FracVector.create([1, 2, 3])
    assert FracVector.use(v) is v


def test_use_converts_via_to_fracvector() -> None:
    # Live fast path: an object exposing to_FracVector() is converted through it.
    result = FracVector.use(_HasToFracVector())
    assert isinstance(result, FracVector)
    assert result == FracVector.create([[1, 2], [3, 4]])


def test_use_converts_mutable_to_immutable() -> None:
    from httk.core.vectors import MutableFracVector

    m = MutableFracVector.from_FracVector(FracVector.create([[1, 2], [3, 4]]))
    result = FracVector.use(m)
    assert type(result) is FracVector
    assert result == m


def test_use_falls_back_to_create_for_plain_sequence() -> None:
    assert FracVector.use([[1, 2], [3, 4]]) == FracVector.create([[1, 2], [3, 4]])


# ------------------------------------------------------------------ __pow__ (corrected negatives / scalar 0)


def test_pow_negative_matrix_beyond_minus_one() -> None:
    a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    inv = a.inv()
    # Corrected: legacy multiplied by self (not the inverse), collapsing A**-2 to the identity.
    assert (a**-2).simplify() == inv.mul(inv).simplify()
    assert (a**-3).simplify() == inv.mul(inv).mul(inv).simplify()
    assert (a ** -2).simplify() != FracVector.eye((3, 3))


def test_pow_zero_scalar_and_fracscalar() -> None:
    assert FracVector.create("2/3") ** 0 == 1
    # Corrected: FracScalar ** 0 used to crash (single-arg constructor needs two arguments).
    s = FracScalar.create("2/3") ** 0
    assert s == 1


def test_pow_zero_matrix_is_identity() -> None:
    assert FracVector.create([[1, 2], [3, 4]]) ** 0 == FracVector.eye((2, 2))


# ------------------------------------------------------------------ mutable/immutable equality (corrected)


def test_equality_across_list_and_tuple_noms() -> None:
    from httk.core.vectors import MutableFracVector

    fv = FracVector.create([[1, 2], [3, 4]])
    mv = MutableFracVector.from_FracVector(fv)
    # Corrected: nested list vs nested tuple never compared equal before.
    assert mv == fv
    assert fv == mv
    assert mv == FracVector([[2, 4], [6, 8]], 2)  # equal value, different denom
    assert mv != FracVector.create([[1, 2], [3, 5]])


# ------------------------------------------------------------------ chain / division-by-zero


def test_create_chain_flattens_outer_dimension() -> None:
    assert FracVector.create([[1, 2, 3], [4, 5, 6]], chain=True) == FracVector.create([1, 2, 3, 4, 5, 6])


def test_division_by_zero_raises_on_use() -> None:
    quotient = FracVector.create("1/2") / FracVector.create("0")
    with pytest.raises(ZeroDivisionError):
        quotient.to_fraction()


# ------------------------------------------------------------------ argmax / nargmax semantics


def test_nargmax_nargmin_collect_all_ties() -> None:
    a = FracVector.create([[1, 7, 3], [7, 2, 7]])
    assert sorted(a.nargmax()) == sorted([(0, 1), (1, 0), (1, 2)])
    assert a.nargmin() == [(0, 0)]
    # argmax returns a single (first) index of the maximum.
    assert a.argmax() in a.nargmax()


# ------------------------------------------------------------------ property-style laws


_MATS = [
    FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]]),
    FracVector.create([[1, 0, 2], [0, 3, 0], [4, 0, 1]]),
    FracVector.create([["1/2", "1/3", 0], [0, "2/5", 1], [1, 0, "3/7"]]),
]


@pytest.mark.parametrize("a", _MATS)
def test_inverse_law(a: FracVector) -> None:
    assert (a * a.inv()).simplify() == FracVector.eye((3, 3))
    assert (a.inv() * a).simplify() == FracVector.eye((3, 3))


def test_matmul_associativity() -> None:
    a, b, c = _MATS
    assert ((a * b) * c).simplify() == (a * (b * c)).simplify()


@pytest.mark.parametrize("a", _MATS)
def test_transpose_involution(a: FracVector) -> None:
    assert a.T().T() == a


@pytest.mark.parametrize("a", _MATS)
def test_simplify_idempotent_and_value_preserving(a: FracVector) -> None:
    s = a.simplify()
    assert s == a
    assert s.simplify() == s
    assert s.simplify().denom == s.denom


def test_create_fast_matches_create() -> None:
    import random

    rng = random.Random(20240721)
    for _ in range(60):
        depth = rng.choice([2, 3])
        if depth == 2:
            data = [[rng.randint(-40, 40) for _ in range(3)] for _ in range(3)]
        else:
            data = [[[rng.randint(-9, 9) for _ in range(2)] for _ in range(2)] for _ in range(2)]
        cd = rng.randint(1, 24)

        def as_fraction(node: object) -> object:
            if isinstance(node, list):
                return [as_fraction(x) for x in node]
            return F(node, cd)  # type: ignore[arg-type]

        fast = FracVector.create_fast(data, common_denom=cd)
        slow = FracVector.create(as_fraction(data))
        assert fast.simplify() == slow.simplify()
        assert fast.simplify().denom == slow.simplify().denom
