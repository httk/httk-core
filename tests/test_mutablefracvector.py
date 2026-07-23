"""
Tests for MutableFracVector: from/to FracVector, slice assignment, and the set_* mutators.

The exact expected results are seeded from the legacy implementation, including its two
preserved quirks: set_simplify makes the denominator a float, and set_inv uses the (already
reassigned) denominator when scaling the adjugate.
"""

import fractions

import pytest

from httk.core.vectors import FracVector, MutableFracVector

F = fractions.Fraction


def test_from_and_to_fracvector() -> None:
    a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    m = MutableFracVector.from_FracVector(a)
    assert isinstance(m, MutableFracVector)
    assert m.noms == [[2, 3, 5], [3, 5, 4], [4, 6, 7]]
    assert m.denom == 1
    back = m.to_FracVector()
    assert isinstance(back, FracVector) and not isinstance(back, MutableFracVector)
    assert back == a


def test_slice_assignment_multi_axis() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([[1, 2, 3], [4, 5, 6]]))
    m[1, 1:] = [40, 50]
    assert m.noms == [[1, 2, 3], [4, 40, 50]]
    assert m.denom == 1


def test_slice_assignment_puts_on_common_denominator() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([["1/2", "1/2"]]))
    m[0, 1] = F(1, 3)
    assert m.to_FracVector().simplify() == FracVector.create([["1/2", "1/3"]])


def test_set_negative() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([[1, 2], [3, 4]]))
    m.set_negative()
    assert m.noms == [[-1, -2], [-3, -4]]


def test_set_transpose() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([[1, 2, 3], [4, 5, 6]]))
    m.set_T()
    assert m.noms == [[1, 4], [2, 5], [3, 6]]


def test_set_inv_legacy_reference() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]]))
    m.set_inv()
    assert m.noms == [[-33, -27, 39], [15, 18, -21], [6, 0, -3]]
    assert m.denom == 3


def test_set_simplify_makes_denominator_float_preserved_quirk() -> None:
    m = MutableFracVector([[2, 4, 6], [8, 10, 12]], 4)
    m.set_simplify()
    assert m.noms == [[1, 2, 3], [4, 5, 6]]
    # Preserved legacy bug: true division makes the denominator a float.
    assert m.denom == 2.0
    assert isinstance(m.denom, float)


def test_set_normalize() -> None:
    m = MutableFracVector([[1, 2], [3, 4]], 2)
    m.set_normalize()
    assert m.noms == [[1, 0], [1, 0]]
    assert m.denom == 2


def test_set_normalize_half() -> None:
    m = MutableFracVector([[1, 3], [5, 7]], 4)
    m.set_normalize_half()
    assert m.noms == [[2, -2], [2, -2]]
    assert m.denom == 8


def test_mutablefracvector_is_unhashable() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([[1, 2], [3, 4]]))
    with pytest.raises(Exception):
        hash(m)


def test_inherited_methods_return_copies() -> None:
    m = MutableFracVector.from_FracVector(FracVector.create([[1, 2], [3, 4]]))
    transposed = m.T()
    # T() returns a new object; the original is unchanged.
    assert m.noms == [[1, 2], [3, 4]]
    assert transposed.noms == [[1, 3], [2, 4]]
