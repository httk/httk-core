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
