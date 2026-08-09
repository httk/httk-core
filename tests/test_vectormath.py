"""
Tests for the functional math wrappers in httk.core.vectors.vectormath.

These focus on the fallback-bug fixes relative to the legacy implementation:

* ``floor`` now falls back to :func:`math.floor` (legacy dispatched to ``math.copysign``);
* ``factorial`` now falls back to :func:`math.factorial` (legacy dispatched to ``math.copysign``);
* ``log`` no longer passes ``base=None`` positionally to :func:`math.log``;
* ``acosh``/``asinh``/``atanh`` now dispatch to the inverse hyperbolic functions
  (legacy dispatched to the non-inverse ``cosh``/``sinh``/``tanh``);
* ``sign`` follows the numpy convention (``sign(0) == 0``) and dispatches to
  ``x.sign()`` like the other wrappers (legacy hardcoded ``copysign(1, x)``);
* ``atan2`` uses the standard ``atan2(y, x)`` argument order (legacy forwarded
  its arguments to :func:`math.atan2` in the wrong order relative to its docstring);
* ``ldexp`` takes the exponent as a real second parameter (legacy could not
  receive it at all);
* ``frexp`` raises a clear TypeError for exact rational types; ``modf`` works
  element-wise on FracVectors via the new :meth:`FracVector.modf`.
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


def test_inverse_hyperbolic_fallbacks() -> None:
    # These used to dispatch to the NON-inverse hyperbolic functions (cosh/sinh/tanh).
    assert abs(vectormath.acosh(2.0) - math.acosh(2.0)) < 1e-12
    assert abs(vectormath.asinh(2.0) - math.asinh(2.0)) < 1e-12
    assert abs(vectormath.atanh(0.5) - math.atanh(0.5)) < 1e-12
    # Sanity: they are NOT equal to the non-inverse versions they used to call.
    assert abs(vectormath.acosh(2.0) - math.cosh(2.0)) > 1.0


def test_noninverse_hyperbolic_fallbacks() -> None:
    assert abs(vectormath.cosh(1.0) - math.cosh(1.0)) < 1e-12
    assert abs(vectormath.sinh(1.0) - math.sinh(1.0)) < 1e-12
    assert abs(vectormath.tanh(1.0) - math.tanh(1.0)) < 1e-12


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
    assert vectormath.sign(0) == 0
    assert vectormath.sign(0.0) == 0
    assert vectormath.sign(FracVector("-1/3")) == -1
    assert vectormath.sign(FracVector(0)) == 0
    assert vectormath.copysign(2.0, 0) == 2.0


def test_floor_dispatches_to_fracvector_method() -> None:
    assert vectormath.floor(FracVector("7/2")) == 3


def test_cos_dispatches_elementwise_on_fracvector() -> None:
    v = FracVector([0, 0, 0])
    result = vectormath.cos(v)
    assert isinstance(result, FracVector)
    assert result == FracVector([1, 1, 1])


def test_sqrt_dispatches_on_fracvector() -> None:
    result = vectormath.sqrt(FracVector([4, 9]))
    assert isinstance(result, FracVector)
    assert result.simplify() == FracVector([2, 3])


def test_pow_wrapper() -> None:
    assert vectormath.pow(FracVector("2"), 3) == 8


# ------------------------------------------------- convention and signature fixes


def test_atan2_standard_argument_order() -> None:
    assert vectormath.atan2(1.0, 1.0) == pytest.approx(math.atan2(1.0, 1.0))
    # Quadrant checks: atan2(y, x)
    assert vectormath.atan2(1.0, 0.0) == pytest.approx(math.pi / 2)
    assert vectormath.atan2(-1.0, 0.0) == pytest.approx(-math.pi / 2)
    assert vectormath.atan2(0.0, -1.0) == pytest.approx(math.pi)


def test_ldexp_takes_exponent() -> None:
    assert vectormath.ldexp(0.75, 4) == 12.0
    assert vectormath.ldexp(1.0, -1) == 0.5


def test_frexp_rejects_exact_types_with_clear_error() -> None:
    assert vectormath.frexp(12.0) == math.frexp(12.0)
    with pytest.raises(TypeError, match="to_floats"):
        vectormath.frexp(FracVector("1/3"))


def test_modf_elementwise_on_fracvector() -> None:
    frac, integer = vectormath.modf(FracVector(["5/2", "-5/2", 3]))
    assert frac == FracVector(["1/2", "-1/2", 0])
    assert integer == FracVector([2, -2, 3])
    assert vectormath.modf(-2.5) == math.modf(-2.5)
