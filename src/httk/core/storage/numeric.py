"""Normalisers for float-valued storage fields."""

import math
from collections.abc import Iterable
from typing import SupportsFloat

__all__ = ["float_matrix"]


def float_matrix(
    value: Iterable[Iterable[SupportsFloat]], cols: int, rows: int | None = None
) -> tuple[tuple[float, ...], ...]:
    """Return a matrix in the canonical float-tensor form ``tuple[tuple[float, ...], ...]``.

    This is the value form of a field declared as
    ``Annotated[tuple[tuple[float, ...], ...], Shape(rows, cols)]``; call it from
    the record's ``__post_init__``. Nested sequences and arrays (numpy arrays
    included, without importing numpy) are accepted; every element goes through
    ``float()``, and ``-0.0`` becomes ``0.0`` because signed zero is not content.

    :param value: The matrix rows.
    :param cols: The required row width.
    :param rows: The required row count, or ``None`` to accept any number of rows.
    :return: The matrix as a tuple of tuples of plain floats.
    :raises ValueError: If an element is not finite, a row is not ``cols`` wide, or the
        row count differs from ``rows``.
    :raises TypeError: If ``value`` is not a nested iterable of real numbers.
    """
    matrix = tuple(tuple(float(element) + 0.0 for element in row) for row in value)
    if rows is not None and len(matrix) != rows:
        raise ValueError(f"expected {rows} rows of {cols} floats, got {len(matrix)} rows")
    for index, row in enumerate(matrix):
        if len(row) != cols:
            raise ValueError(f"row {index} has {len(row)} elements, expected {cols}")
        if not all(math.isfinite(element) for element in row):
            raise ValueError(f"row {index} holds a non-finite value: {row!r}")
    return matrix
