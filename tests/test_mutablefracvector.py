"""
Tests for MutableFracVector class conversion, slice assignment, and set_* mutators.

The exact expected results are seeded from the legacy implementation. Two legacy bugs have now
been corrected (previously these tests pinned the buggy behavior): set_simplify keeps the
denominator an int (integer division), and set_inv scales the adjugate by the original
denominator so it agrees numerically with FracVector.inv().
"""

import fractions

import pytest

from httk.core.vectors import FracVector, MutableFracVector

F = fractions.Fraction


def test_from_and_to_fracvector() -> None:
    a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    m = MutableFracVector.create(a)
    assert isinstance(m, MutableFracVector)
    assert m.noms == [[2, 3, 5], [3, 5, 4], [4, 6, 7]]
    assert m.denom == 1
    back = FracVector.create(m)
    assert isinstance(back, FracVector) and not isinstance(back, MutableFracVector)
    assert back == a


def test_slice_assignment_multi_axis() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2, 3], [4, 5, 6]]))
    m[1, 1:] = [40, 50]
    assert m.noms == [[1, 2, 3], [4, 40, 50]]
    assert m.denom == 1


def test_slice_assignment_puts_on_common_denominator() -> None:
    m = MutableFracVector.create(FracVector.create([["1/2", "1/2"]]))
    m[0, 1] = F(1, 3)
    assert FracVector.create(m).simplify() == FracVector.create([["1/2", "1/3"]])


def test_slice_assignment_fancy_index_rows() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2, 3], [4, 5, 6], [7, 8, 9]]))
    # Fancy (list-of-indices) selection in the first axis, single column in the second.
    m[(0, 2), 1] = [20, 80]
    assert m.noms == [[1, 20, 3], [4, 5, 6], [7, 80, 9]]


def test_slice_assignment_fancy_index_with_slice() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2, 3], [4, 5, 6], [7, 8, 9]]))
    m[(0, 2), 1:] = [[20, 30], [80, 90]]
    assert m.noms == [[1, 20, 30], [4, 5, 6], [7, 80, 90]]


def test_slice_assignment_full_column() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2], [3, 4], [5, 6]]))
    m[:, 0] = [10, 30, 50]
    assert m.noms == [[10, 2], [30, 4], [50, 6]]


def test_set_negative() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2], [3, 4]]))
    m.set_negative()
    assert m.noms == [[-1, -2], [-3, -4]]


def test_set_transpose() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2, 3], [4, 5, 6]]))
    m.set_T()
    assert m.noms == [[1, 4], [2, 5], [3, 6]]


def test_set_inv_matches_fracvector_inv() -> None:
    a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    m = MutableFracVector.create(a)
    m.set_inv()
    # Corrected behavior: numerically equal to FracVector.inv() (was 3x off in the legacy bug).
    assert m.noms == [[-11, -9, 13], [5, 6, -7], [2, 0, -1]]
    assert m.denom == 3
    assert FracVector.create(m) == a.inv()


@pytest.mark.parametrize(
    "data",
    [
        [[2, 3, 5], [3, 5, 4], [4, 6, 7]],
        [[1, 2, 0], [0, 1, 3], [4, 0, 1]],
        [[2, 0, 0], [0, 3, 0], [0, 0, 5]],
        [[-2, 3, 1], [4, -1, 5], [1, 2, -3]],
    ],
)
def test_set_inv_agrees_with_fracvector_inv_various(data: list[list[int]]) -> None:
    a = FracVector.create(data)
    m = MutableFracVector.create(a)
    m.set_inv()
    assert FracVector.create(m).simplify() == a.inv().simplify()


def test_set_simplify_keeps_integer_denominator() -> None:
    m = MutableFracVector([[2, 4, 6], [8, 10, 12]], 4)
    m.set_simplify()
    assert m.noms == [[1, 2, 3], [4, 5, 6]]
    # Corrected behavior: integer division keeps the denominator an int, matching .simplify().
    assert m.denom == 2
    assert isinstance(m.denom, int)
    assert FracVector.create(m) == FracVector([[2, 4, 6], [8, 10, 12]], 4).simplify()


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
    m = MutableFracVector.create(FracVector.create([[1, 2], [3, 4]]))
    with pytest.raises(Exception):
        hash(m)


def test_inherited_methods_return_copies() -> None:
    m = MutableFracVector.create(FracVector.create([[1, 2], [3, 4]]))
    transposed = m.T()
    # T() returns a new object; the original is unchanged.
    assert m.noms == [[1, 2], [3, 4]]
    assert transposed.noms == [[1, 3], [2, 4]]
