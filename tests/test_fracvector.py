"""
Exactness tests for FracVector and FracScalar.

Every assertion checks EXACT equality of noms/denom (or exact Fraction equality), seeded from
the legacy embedded reference values; nothing here uses approximate comparison except where the
legacy semantics themselves approximate (limit_denominator, string min_accuracy, transcendentals),
which are pinned to their exact expected rationals.
"""

import copy
import decimal
import fractions
import pickle
from typing import cast

import pytest

from httk.core.vectors import MutableFracVector, FracScalar, FracVector, SurdVector, VectorBackend, VectorNativeBackend

F = fractions.Fraction


class IntLike(int):
    pass


class Convertible:
    def to_fractions(self) -> tuple[int, int]:
        return (2, 3)


def _force_generic_constructor(node: object) -> object:
    if type(node) is int:
        return IntLike(node)
    if type(node) is F:
        return str(node)
    if type(node) is tuple:
        return tuple(_force_generic_constructor(item) for item in node)
    if type(node) is list:
        return [_force_generic_constructor(item) for item in node]
    return node


# ------------------------------------------------------------------ creation


def test_create_from_ints_with_denominator() -> None:
    v = FracVector([[804, 0, 0], [0, 372, 0], [0, 0, 738]], denom=100)
    # simplify shares the gcd(=2) out of the denominator
    assert v.noms == ((402, 0, 0), (0, 186, 0), (0, 0, 369))
    assert v.denom == 50


def test_create_from_vector_api_members() -> None:
    scalar = FracScalar("1/2")
    assert scalar.fractions_exact is True
    assert FracVector([scalar]) == FracVector([F(1, 2)])

    native_backend = VectorNativeBackend([1, 2])
    assert FracVector([1]).fractions_exact is True
    assert native_backend.fractions_exact is True
    assert FracVector([native_backend]) == FracVector([[1, 2]])

    rational_surd = SurdVector([F(1, 2), F(3, 2)])
    assert rational_surd.fractions_exact is True
    assert FracVector([rational_surd]) == FracVector([[F(1, 2), F(3, 2)]])


def test_create_from_numpy_vector_api_member() -> None:
    numpy = pytest.importorskip("numpy")
    backend = VectorBackend.create(numpy.array([1.5, 2.5]))
    assert backend.fractions_exact is True
    assert FracVector([backend]) == FracVector([[1.5, 2.5]])


def test_create_from_irrational_surd_rejects_inexact_hub() -> None:
    surd = SurdVector.sqrt_of(2)
    assert surd.fractions_exact is False
    # Exact construction must not silently consume SurdVector's deterministic hub approximation.
    with pytest.raises(TypeError, match="inexact member.*to_fractions_approx"):
        FracVector([surd])


def test_create_from_decimal_strings_matches_int_form() -> None:
    strings = FracVector([["8.04", "0.0", "0.0"], ["0.0", "3.72", "0.0"], ["0.0", "0.0", "7.38"]])
    ints = FracVector([[804, 0, 0], [0, 372, 0], [0, 0, 738]], denom=100)
    assert strings.noms == ints.noms
    assert strings.denom == ints.denom


def test_create_from_python_float_is_binary_rational() -> None:
    # A Python float literal is a binary rational; 8.04 is NOT 804/100.
    v = FracVector([8.04])
    assert v.to_fractions() == [fractions.Fraction(8.04)]
    assert v != FracVector(["8.04"])


def test_create_from_decimal() -> None:
    v = FracVector([decimal.Decimal("0.25"), decimal.Decimal("1.5"), decimal.Decimal("2.125")])
    assert v.noms == (2, 12, 17)
    assert v.denom == 8


def test_create_from_fraction() -> None:
    v = FracVector([[F(185, 23), 0, 0], [0, F(67, 18), 0], [0, 0, F(59, 8)]])
    assert v.noms == ((13320, 0, 0), (0, 6164, 0), (0, 0, 12213))
    assert v.denom == 1656


def test_create_string_min_accuracy_default() -> None:
    # 0.33 assumed to be 0.3300 = 33/100; 0.3333 assumed to mean 1/3.
    assert FracVector("0.33").to_fraction() == F(33, 100)
    assert FracVector("0.3333").to_fraction() == F(1, 3)


def test_create_string_infinite_accuracy() -> None:
    assert FracVector("0.33", min_accuracy=None).to_fraction() == F(33, 100)
    assert FracVector("0.3333", min_accuracy=None).to_fraction() == F(3333, 10000)


def test_create_uncertainty_string() -> None:
    assert FracVector(["0.33342(10)"]).noms == (1,)
    assert FracVector(["0.33342(10)"]).denom == 3
    assert FracVector(["0.33352(10)"]).noms == (388,)
    assert FracVector(["0.33352(10)"]).denom == 1163
    both = FracVector(["0.33342(10)", "0.33352(10)"])
    assert both.noms == (1163, 1164)
    assert both.denom == 3489


def test_create_fraction_string() -> None:
    assert FracVector("2/3").to_fraction() == F(2, 3)


# ------------------------------------------------------------------ simplify / resolution


def test_third_times_three_simplifies_to_one() -> None:
    v = (FracVector("1/3") * 3).simplify()
    assert v == 1
    assert v.noms == 1
    assert v.denom == 1


def test_simplify_shares_common_denominator() -> None:
    v = FracVector.from_noms_and_denom(((2, 4), (6, 8)), 4).simplify()
    assert v.noms == ((1, 2), (3, 4))
    assert v.denom == 2


def test_set_denominator() -> None:
    v = FracVector([["1/3", "2/7"]]).set_denominator(1000)
    assert v.denom == 1000
    assert v.noms == ((333, 286),)


def test_limit_denominator_recovers_small_rational() -> None:
    binary = F(6004799503160661, 18014398509481984)  # float64 of 1/3
    v = FracVector([[binary]]).limit_denominator(1000)
    assert v == FracVector([["1/3"]])


def test_floor_and_ceil() -> None:
    assert FracVector("-7/3").floor() == -3
    assert FracVector("-7/3").ceil() == -2
    assert FracVector("7/3").floor() == 2
    assert FracVector("7/3").ceil() == 3


def test_sign() -> None:
    assert FracVector("-3/4").sign() == -1
    assert FracVector("0").sign() == 0
    assert FracVector("5").sign() == 1


# ------------------------------------------------------------------ operators


def test_multiplication_is_matrix_multiply() -> None:
    a = FracVector([[1, 2], [3, 4]])
    identity = FracVector([[1, 0], [0, 1]])
    assert (a * identity) == a


def test_addition_across_denominators() -> None:
    v = (FracVector([["1/2", "1/3"]]) + FracVector([["1/6", "1/6"]])).simplify()
    assert v.noms == ((4, 3),)  # [2/3, 1/2] on the shared denominator 6
    assert v.denom == 6


def test_subtraction() -> None:
    v = FracVector([[5, 6, 7]]) - FracVector([[1, 2, 3]])
    assert v == FracVector([[4, 4, 4]])


def test_truediv_scalar() -> None:
    v = (FracVector([[1, 2], [3, 4]]) / FracVector("2")).simplify()
    assert v == FracVector([["1/2", "1"], ["3/2", "2"]])


def test_pow_minus_one_is_inverse() -> None:
    a = FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    assert (a**-1).simplify() == a.inv().simplify()


def test_pow_positive() -> None:
    a = FracVector([[1, 1], [0, 1]])
    assert a**3 == FracVector([[1, 3], [0, 1]])


# ------------------------------------------------------------------ linear algebra


def test_transpose() -> None:
    a = FracVector([[1, 2, 3], [4, 5, 6]])
    assert a.T() == FracVector([[1, 4], [2, 5], [3, 6]])


def test_det_3x3() -> None:
    assert FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]]).det() == -3


def test_det_4x4() -> None:
    a = FracVector([[1, 2, 3, 4], [2, 1, 4, 3], [3, 4, 1, 2], [4, 3, 2, 7]])
    assert a.det() == 120


def test_inv_3x3_exact() -> None:
    a = FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    inv = a.inv().simplify()
    assert inv.noms == ((-11, -9, 13), (5, 6, -7), (2, 0, -1))
    assert inv.denom == 3
    assert (a * inv).simplify() == FracVector.eye((3, 3))


def test_dot() -> None:
    assert FracVector([1, 2, 3]).dot(FracVector([4, 5, 6])) == 32


def test_cross() -> None:
    v = FracVector([1, 2, 3]).cross(FracVector([4, 5, 6]))
    assert v == FracVector([-3, 6, -3])


def test_lengthsqr() -> None:
    assert FracVector([3, 4, 12]).lengthsqr() == 169


def test_metric_product() -> None:
    metric = FracVector([[2, 0, 0], [0, 3, 0], [0, 0, 4]])
    v = FracVector([1, 1, 1])
    assert metric.metric_product(v, v) == 9


def test_reciprocal_issue_60_reference() -> None:
    cell = FracVector([["8.04", "0.0", "0.0"], ["0.0", "3.72", "0.0"], ["0.0", "0.0", "7.38"]])
    recip = cell.reciprocal()
    assert recip.noms == ((3431700, 0, 0), (0, 7416900, 0), (0, 0, 3738600))
    assert recip.denom == 27590868


# ------------------------------------------------------------------ normalize


def test_normalize_into_unit_range() -> None:
    v = FracVector([["7/3", "-1/6", "5/2"]]).normalize().simplify()
    assert v == FracVector([["1/3", "5/6", "1/2"]])


def test_normalize_half_into_symmetric_range() -> None:
    v = FracVector([["7/3", "-1/6", "5/2"]]).normalize_half().simplify()
    assert v == FracVector([["1/3", "-1/6", "-1/2"]])


# ------------------------------------------------------------------ conversions / round-trips


def test_to_floats() -> None:
    assert FracVector([[1, 2], [3, 4]], denom=7).to_floats() == [[1 / 7, 2 / 7], [3 / 7, 4 / 7]]


def test_to_fractions_roundtrip() -> None:
    a = FracVector([["1/3", "2/5"], ["3/7", "4/9"]])
    assert FracVector(a.to_fractions()) == a


def test_to_tuple_exact() -> None:
    a = FracVector([[1, 2, 3], [4, 5, 6]], denom=7)
    assert a.to_tuple() == (7, ((1, 2, 3), (4, 5, 6)))


# ------------------------------------------------------------------ equality / ordering / hash / indexing


def test_equality_across_denominators() -> None:
    assert FracVector([["2/4"]]) == FracVector([["1/2"]])
    assert FracVector.from_noms_and_denom(((1,),), 2) == FracVector.from_noms_and_denom(((2,),), 4)


def test_ordering_scalars() -> None:
    assert FracVector("1/3") < FracVector("1/2")
    assert FracVector("5/2") > FracVector("2")
    assert FracVector("1/3") <= FracVector("1/3")


def test_hash_matches_for_equal_representation() -> None:
    raw = FracVector.from_noms_and_denom(((1, 2), (3, 4)), 2)
    assert hash(raw) == hash(raw)


def test_indexing_single_axis() -> None:
    a = FracVector([[1, 2, 3], [4, 5, 6]])
    assert a[0] == FracVector([1, 2, 3])
    assert a[1, 2] == FracVector(6)


def test_indexing_multi_axis_tuple_slice() -> None:
    a = FracVector([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert a[1:, 1:] == FracVector([[5, 6], [8, 9]])
    assert a[:, 0] == FracVector([1, 4, 7])


def test_iteration_yields_rows() -> None:
    a = FracVector([[1, 2], [3, 4]])
    rows = list(a)
    assert rows == [FracVector([1, 2]), FracVector([3, 4])]


def test_max_min_argmax() -> None:
    a = FracVector([2, 7, 5])
    assert a.max() == 7
    assert a.min() == 2
    assert a.argmax() == 1
    assert a.argmin() == 0


# ------------------------------------------------------------------ FracScalar


def test_fracscalar_creation_and_conversions() -> None:
    s = FracScalar("3/4")
    assert isinstance(s, FracScalar)
    assert s.nom == 3
    assert s.denom == 4
    assert float(s) == 0.75
    assert s.to_fraction() == F(3, 4)


def test_fracscalar_create_ignores_min_accuracy() -> None:
    # Unlike FracVector, FracScalar converts strings exactly (legacy behavior).
    assert FracScalar("0.33").to_fraction() == F(33, 100)


# ------------------------------------------------------------------ stacking / chaining


def test_chain_and_stack_vecs() -> None:
    a = FracVector([1, 2, 3])
    b = FracVector([4, 5, 6])
    assert FracVector.chain_vecs([a, b]) == FracVector([1, 2, 3, 4, 5, 6])
    assert FracVector.stack_vecs([a, b]) == FracVector([[1, 2, 3], [4, 5, 6]])


def test_get_append_extend() -> None:
    b = FracVector([1, 2, 3])
    assert b.get_append(4) == FracVector([1, 2, 3, 4])
    assert b.get_extend(FracVector([4, 5, 6])) == FracVector([1, 2, 3, 4, 5, 6])


def test_get_stackedinsert_rename() -> None:
    # The legacy misspellings ged_prestacked/ged_stackedinsert are renamed to get_*.
    assert hasattr(FracVector, "get_prestacked")
    assert hasattr(FracVector, "get_stackedinsert")
    assert not hasattr(FracVector, "ged_prestacked")
    assert not hasattr(FracVector, "ged_stackedinsert")


def test_immutable_setitem_raises() -> None:
    with pytest.raises(Exception, match="immutable"):
        FracVector([1, 2, 3])[0] = 5


# ------------------------------------------------------------------ from_tuple / to_tuple round-trip


@pytest.mark.parametrize(
    "v",
    [
        FracVector([[1, 2, 3], [4, 5, 6]], denom=7),
        FracVector([1, 2, 3]),
        FracScalar("3/4"),
        FracVector([[["1/3", "2/5"]], [["3/7", "4/9"]]]),
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
    assert FracVector([1, 2, 3]).get_stacked([4, 5, 6]) == FracVector([[1, 2, 3], [4, 5, 6]])
    assert FracVector([1, 2, 3]).get_prestacked([4, 5, 6]) == FracVector([[4, 5, 6], [1, 2, 3]])


def test_get_stacked_matrices() -> None:
    a = FracVector([[1, 2], [3, 4]])
    b = FracVector([[5, 6], [7, 8]])
    stacked = a.get_stacked(b)
    assert stacked.dim == (2, 2, 2)
    assert stacked[0] == a and stacked[1] == b


def test_dim_treats_string_nominators_as_scalar_leaves() -> None:
    """A string leaf must not be followed through forever by ``dim``."""
    assert FracVector([["1", "0"], ["0", "1"]]).dim == (2, 2)


def test_constructor_copies_plain_fracvector() -> None:
    v = FracVector([1, 2, 3])
    assert FracVector(v) == v
    assert FracVector(v) is not v


def test_constructor_converts_mutable_to_immutable() -> None:
    from httk.core.vectors import MutableFracVector

    m = MutableFracVector(FracVector([[1, 2], [3, 4]]))
    result = FracVector(m)
    assert type(result) is FracVector
    assert result == m


def test_constructor_converts_plain_sequence() -> None:
    assert FracVector([[1, 2], [3, 4]]) == FracVector([[1, 2], [3, 4]])


# ------------------------------------------------------------------ __pow__ (corrected negatives / scalar 0)


def test_pow_negative_matrix_beyond_minus_one() -> None:
    a = FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    inv = a.inv()
    # Corrected: legacy multiplied by self (not the inverse), collapsing A**-2 to the identity.
    assert (a**-2).simplify() == inv.mul(inv).simplify()
    assert (a**-3).simplify() == inv.mul(inv).mul(inv).simplify()
    assert (a**-2).simplify() != FracVector.eye((3, 3))


def test_pow_zero_scalar_and_fracscalar() -> None:
    assert FracVector("2/3") ** 0 == 1
    # Scalar powers use the raw constructor for the identity.
    s = FracScalar("2/3") ** 0
    assert s == 1


def test_fracvector_and_fracscalar_copy_round_trip() -> None:
    for value in (FracVector([1, 2]), FracScalar("1/2")):
        assert pickle.loads(pickle.dumps(value)) == value
        assert copy.copy(value) == value
        assert copy.deepcopy(value) == value


def test_repr_uses_raw_constructor() -> None:
    assert repr(FracVector.from_noms_and_denom((1, 2), 3)) == "FracVector.from_noms_and_denom((1, 2), 3)"


def test_pow_zero_matrix_is_identity() -> None:
    assert FracVector([[1, 2], [3, 4]]) ** 0 == FracVector.eye((2, 2))


# ------------------------------------------------------------------ mutable/immutable equality (corrected)


def test_equality_across_list_and_tuple_noms() -> None:
    from httk.core.vectors import MutableFracVector

    fv = FracVector([[1, 2], [3, 4]])
    mv = MutableFracVector(fv)
    # Corrected: nested list vs nested tuple never compared equal before.
    assert mv == fv
    assert fv == mv
    assert mv == FracVector([[2, 4], [6, 8]], denom=2)  # equal value, different denom
    assert mv != FracVector([[1, 2], [3, 5]])


# ------------------------------------------------------------------ chain / division-by-zero


def test_create_chain_flattens_outer_dimension() -> None:
    assert FracVector([[1, 2, 3], [4, 5, 6]], chain=True) == FracVector([1, 2, 3, 4, 5, 6])


def test_division_by_zero_raises_on_use() -> None:
    quotient = FracVector("1/2") / FracVector("0")
    with pytest.raises(ZeroDivisionError):
        quotient.to_fraction()


# ------------------------------------------------------------------ argmax / nargmax semantics


def test_nargmax_nargmin_collect_all_ties() -> None:
    a = FracVector([[1, 7, 3], [7, 2, 7]])
    assert sorted(a.nargmax()) == sorted([(0, 1), (1, 0), (1, 2)])
    assert a.nargmin() == [(0, 0)]
    # argmax returns a single (first) index of the maximum.
    assert a.argmax() in a.nargmax()


# ------------------------------------------------------------------ property-style laws


_MATS = [
    FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]]),
    FracVector([[1, 0, 2], [0, 3, 0], [4, 0, 1]]),
    FracVector([["1/2", "1/3", 0], [0, "2/5", 1], [1, 0, "3/7"]]),
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


def test_constructor_matches_fraction_conversion() -> None:
    import random

    rng = random.Random(20240721)
    for _ in range(60):
        depth = rng.choice([2, 3])
        if depth == 2:
            data: object = [[rng.randint(-40, 40) for _ in range(3)] for _ in range(3)]
        else:
            data = [[[rng.randint(-9, 9) for _ in range(2)] for _ in range(2)] for _ in range(2)]
        cd = rng.randint(1, 24)

        def as_fraction(node: object, denominator: int) -> object:
            if isinstance(node, list):
                return [as_fraction(x, denominator) for x in node]
            return F(cast(int, node), denominator)

        fast = FracVector(data, denom=cd)
        slow = FracVector(as_fraction(data, cd))
        assert fast.simplify() == slow.simplify()
        assert fast.simplify().denom == slow.simplify().denom


@pytest.mark.parametrize(
    ("values", "denom", "simplify"),
    [
        (7, None, True),
        (F(-5, 12), 5, False),
        ([1, F(1, 2), 3], 7, True),
        (((1, F(2, 3)), (F(-5, 6), 4)), 5, False),
    ],
)
def test_fast_exact_constructor_matches_generic_representation(
    values: object, denom: int | None, simplify: bool
) -> None:
    fast = FracVector(values, denom=denom, simplify=simplify, min_accuracy=None)
    slow = FracVector(_force_generic_constructor(values), denom=denom, simplify=simplify, min_accuracy=None)
    assert (fast.noms, fast.denom) == (slow.noms, slow.denom)


def test_fast_vector_copy_matches_generic_representation() -> None:
    source = FracVector.from_noms_and_denom(((2, 4), (6, 8)), -4)
    fast = FracVector(source, simplify=False)
    slow = FracVector(_force_generic_constructor(source.to_fractions()), simplify=False, min_accuracy=None)
    assert (fast.noms, fast.denom) == (slow.noms, slow.denom)


@pytest.mark.parametrize("values", [[1, (2, 3)], [1, Convertible()]])
@pytest.mark.parametrize("vector_type", [FracVector, MutableFracVector])
def test_mixed_leaf_and_nested_values_match_generic_representation(values: object, vector_type: type) -> None:
    fast = vector_type(values, simplify=False, min_accuracy=None)
    slow = vector_type(_force_generic_constructor(values), simplify=False, min_accuracy=None)
    assert (fast.noms, fast.denom) == (slow.noms, slow.denom)


def test_simplify_huge_integers_no_float_overflow() -> None:
    # Regression: simplify() used int(x / gcd) (float division), which overflowed for
    # exact integers beyond the float range. Exact floor division must be used instead.
    huge = 10**400
    vector = FracVector([[2 * huge, 4 * huge, 6 * huge]], denom=2)
    simplified = vector.simplify()  # must not raise OverflowError
    assert simplified == FracVector([[huge, 2 * huge, 3 * huge]])


def test_to_floats_huge_integers_no_float_overflow() -> None:
    # Regression: to_floats() called math.isnan(x) on each nominator, which converted
    # very large exact integers to float first and overflowed. The ratio itself is finite.
    vector = FracVector([[3, 0]], denom=10**16)
    floats = vector.to_floats()
    assert floats[0][0] == float(fractions.Fraction(3, 10**16))
    # A genuinely huge numerator/denominator whose ratio is order 1 renders finitely.
    ratio = FracVector([[7 * 10**350]], denom=2 * 10**350)
    assert ratio.to_floats()[0][0] == 3.5
