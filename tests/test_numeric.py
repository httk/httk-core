"""
Tests for the numeric presentation helpers: ``to_numeric`` (numpy-backed), ``to_numeric_scalar``
(numpy-free), and ``numpy_available``.
"""

import fractions
from typing import Any, cast

import pytest

import httk.core.vectors as vectors_pkg
from httk.core import FracVector, SurdVector
from httk.core.vectors import to_numeric, to_numeric_scalar
from httk.core.vectors.fracvector import FracScalar

F = fractions.Fraction

try:
    import numpy

    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    HAS_NUMPY = False

requires_numpy = pytest.mark.skipif(not HAS_NUMPY, reason="numpy is not installed")


# ------------------------------------------------------------------ to_numeric (numpy-backed)


@requires_numpy
def test_to_numeric_is_plain_float64_ndarray() -> None:
    fv = FracVector([["1/3", "2/3"], [1, 2]])
    result = to_numeric(fv)
    assert type(result) is numpy.ndarray  # exactly the base class, not a view subclass
    assert result.dtype == numpy.float64
    assert result.tolist() == fv.to_floats()


@requires_numpy
def test_to_numeric_matches_floats_for_surd() -> None:
    # Hexagonal-style basis carrying sqrt(3).
    a = F(3)
    B = SurdVector.from_radicand_map(
        {
            1: [[a, 0, 0], [-a / 2, 0, 0], [0, 0, F(5)]],
            3: [[0, 0, 0], [0, a / 2, 0], [0, 0, 0]],
        }
    )
    result = to_numeric(B)
    assert type(result) is numpy.ndarray
    assert result.dtype == numpy.float64
    assert result.tolist() == B.to_floats()


@requires_numpy
def test_to_numeric_accepts_varied_matrix_inputs() -> None:
    expected = [[1.0, 2.0], [3.0, 4.0]]
    assert cast(numpy.ndarray, to_numeric(FracVector([[1, 2], [3, 4]]))).tolist() == expected
    assert cast(numpy.ndarray, to_numeric(SurdVector([[1, 2], [3, 4]]))).tolist() == expected
    assert cast(numpy.ndarray, to_numeric([[1, 2], [3, 4]])).tolist() == expected
    assert cast(numpy.ndarray, to_numeric(numpy.array([[1.0, 2.0], [3.0, 4.0]]))).tolist() == expected


@requires_numpy
def test_to_numeric_scalar_inputs_return_plain_float() -> None:
    assert to_numeric(5) == 5.0
    assert type(to_numeric(5)) is float  # a scalar is a plain float, never a 0-d array
    assert to_numeric(F(1, 4)) == 0.25
    assert to_numeric(FracScalar(F(3, 8))) == 0.375
    surd = SurdVector.sqrt_of(2)
    assert abs(to_numeric(surd) - 2.0**0.5) < 1e-12
    assert type(to_numeric(surd)) is float


@requires_numpy
def test_to_numeric_rejects_unrepresentable() -> None:
    with pytest.raises(TypeError):
        to_numeric(cast(Any, object()))


# ------------------------------------------------------------------ to_numeric_scalar (numpy-free)


def test_to_numeric_scalar_direct() -> None:
    assert to_numeric_scalar(3) == 3.0
    assert to_numeric_scalar(F(1, 2)) == 0.5
    assert to_numeric_scalar("1/4") == 0.25
    assert to_numeric_scalar(FracScalar(2)) == 2.0
    assert abs(to_numeric_scalar(SurdVector.sqrt_of(3)) - 3.0**0.5) < 1e-12


def test_to_numeric_scalar_rejects_matrix() -> None:
    with pytest.raises(TypeError):
        to_numeric_scalar(FracVector([[1, 2], [3, 4]]))
    with pytest.raises(TypeError):
        to_numeric_scalar(SurdVector([[1, 2], [3, 4]]))


# ------------------------------------------------------------------ numpy requirement / availability


def test_to_numeric_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the availability flag the helper reads to False, regardless of the real environment.
    monkeypatch.setattr(vectors_pkg, "_numpy_available", False)
    from httk.core.vectors import numpy_available

    assert numpy_available() is False
    with pytest.raises(ImportError, match=r"httk-core\[numpy\]"):
        to_numeric([[1, 2], [3, 4]])
    # Even a scalar input raises: the contract is numpy-backed, uniformly.
    with pytest.raises(ImportError, match=r"httk-core\[numpy\]"):
        to_numeric(5)


def test_to_numeric_scalar_never_requires_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vectors_pkg, "_numpy_available", False)
    # to_numeric_scalar has no numpy dependency, so it works even when numpy is reported unavailable.
    assert to_numeric_scalar(F(1, 3)) == 1.0 / 3.0
    assert to_numeric_scalar(SurdVector.sqrt_of(2)) == pytest.approx(2.0**0.5)
