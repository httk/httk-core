"""
Tests for the functional math wrappers in httk.core.vectors.vectormath.

These focus on the three fallback-bug fixes relative to the legacy implementation:

* ``floor`` now falls back to :func:`math.floor` (legacy dispatched to ``math.copysign``);
* ``factorial`` now falls back to :func:`math.factorial` (legacy dispatched to ``math.copysign``);
* ``log`` no longer passes ``base=None`` positionally to :func:`math.log`.
"""

import math

import pytest

from httk.core.vectors import FracVector, vectormath

# --------------------------------------------------------------- fixed fallbacks


def test_floor_falls_back_to_math_floor() -> None:
    assert vectormath.floor(2.7) == 2
    assert vectormath.floor(-1.5) == -2
    assert vectormath.floor(3.0) == 3


def test_factorial_falls_back_to_math_factorial() -> None:
    assert vectormath.factorial(0) == 1
    assert vectormath.factorial(5) == 120


def test_log_natural_without_base() -> None:
    assert abs(vectormath.log(math.e) - 1.0) < 1e-12
    assert abs(vectormath.log(1.0)) < 1e-12


def test_log_with_base() -> None:
    assert abs(vectormath.log(100.0, 10) - 2.0) < 1e-12


# --------------------------------------------------------------- other scalar fallbacks


def test_ceil_and_trunc_scalar() -> None:
    assert vectormath.ceil(2.1) == 3
    assert vectormath.trunc(2.9) == 2


def test_scalar_trig_fallbacks() -> None:
    assert abs(vectormath.cos(0.0) - 1.0) < 1e-12
    assert abs(vectormath.sin(0.0)) < 1e-12
    assert abs(vectormath.sqrt(4.0) - 2.0) < 1e-12
    assert abs(vectormath.exp(0.0) - 1.0) < 1e-12


def test_sign_and_copysign() -> None:
    assert vectormath.sign(3.0) == 1
    assert vectormath.sign(-3.0) == -1
    assert vectormath.copysign(2.0, 0) == 2.0


# --------------------------------------------------------------- vector dispatch


def test_floor_dispatches_to_fracvector_method() -> None:
    assert vectormath.floor(FracVector.create("7/2")) == 3


def test_cos_dispatches_elementwise_on_fracvector() -> None:
    v = FracVector.create([0, 0, 0])
    result = vectormath.cos(v)
    assert isinstance(result, FracVector)
    assert result == FracVector.create([1, 1, 1])


def test_sqrt_dispatches_on_fracvector() -> None:
    result = vectormath.sqrt(FracVector.create([4, 9]))
    assert isinstance(result, FracVector)
    assert result.simplify() == FracVector.create([2, 3])


def test_pow_wrapper() -> None:
    assert vectormath.pow(FracVector.create("2"), 3) == 8
