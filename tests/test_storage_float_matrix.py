"""Tests for the float-tensor value normaliser."""

import math
from array import array

import pytest

from httk.core.storage import float_matrix


def test_float_matrix_returns_canonical_tuples() -> None:
    value = float_matrix([array("d", [1, -0.0]), (2, 3.5)], 2, rows=2)
    assert value == ((1.0, 0.0), (2.0, 3.5))
    assert all(type(row) is tuple and all(type(x) is float for x in row) for row in value)
    assert math.copysign(1.0, value[0][1]) == 1.0
    assert float_matrix([], 3) == ()


def test_float_matrix_accepts_numpy_arrays() -> None:
    numpy = pytest.importorskip("numpy")
    value = float_matrix(numpy.eye(3), 3, rows=3)
    assert value == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert all(type(x) is float for row in value for x in row)


@pytest.mark.parametrize(
    ("value", "rows", "message"),
    [
        ([[1.0, 2.0]], 2, "expected 2 rows"),
        ([[1.0, 2.0], [3.0]], None, "row 1 has 1 elements"),
        ([[1.0, math.nan]], None, "non-finite"),
        ([[math.inf, 1.0]], None, "non-finite"),
    ],
)
def test_float_matrix_rejects_bad_values(value: list[list[float]], rows: int | None, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        float_matrix(value, 2, rows=rows)
