#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2015 Rickard Armiento
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Functional wrappers over the :mod:`math` module that also work on FracVector-like objects.

Each function first tries to dispatch to a method on the argument (so a FracVector computes
an exact-rational element-wise result), and otherwise falls back to the corresponding
:mod:`math` function on a plain scalar.
"""

import math
from typing import Any


def ceil(x: Any, **args: Any) -> Any:
    """
    Return the ceiling of x, the smallest integer value greater than or equal to x.

    (For vectors applied to each element.)
    """
    try:
        return x.ceil(**args)
    except AttributeError:
        return math.ceil(x, **args)


def copysign(x: Any, y: Any, **args: Any) -> Any:
    """
    Return x with the sign of y. If an element of y is zero, abs of the corresponding element
    in x is returned.

    (For vectors applied to each element.)
    """
    try:
        return x.copysign(y, **args)
    except AttributeError:
        if y == 0:
            return abs(x)
        return math.copysign(x, y, **args)


def sign(x: Any, **args: Any) -> Any:
    """
    Return the sign of x, equivalent to copysign(1, x).

    (For vectors applied to each element.)
    """
    return copysign(1, x)


def fabs(x: Any, **args: Any) -> Any:
    """
    Return the absolute value of x.

    (For vectors applied to each element.)
    """
    return abs(x)


def factorial(x: Any, **args: Any) -> Any:
    """
    Return x factorial. Raises ValueError if (any element of) x is negative.

    (For vectors applied to each element.)
    """
    try:
        return x.factorial(**args)
    except AttributeError:
        return math.factorial(x, **args)


def floor(x: Any, **args: Any) -> Any:
    """
    Return the floor of x, the largest integer value less than or equal to x.

    (For vectors applied to each element.)
    """
    try:
        return x.floor(**args)
    except AttributeError:
        return math.floor(x, **args)


def fmod(x: Any, y: Any, **args: Any) -> Any:
    """
    Equivalent to x % y.
    """
    return x % y


def frexp(x: Any, **args: Any) -> Any:
    """
    Return the mantissa and exponent of x as the pair (m, e). m is a float and e is an integer
    such that x == m * 2**e exactly. If x is zero, returns (0.0, 0), otherwise 0.5 <= abs(m) < 1.

    (For vectors applied to each element and returns tuples nested in lists.)
    """
    try:
        return x.frexp(**args)
    except AttributeError:
        return math.frexp(x, **args)


def fsum(iterable: Any, **args: Any) -> Any:
    """
    Equivalent to sum(iterable).
    """
    return sum(iterable)


def isinf(x: Any, **args: Any) -> Any:
    """
    Check if the float x is positive or negative infinity.

    (For vectors applied to each element and returns True/False as nested lists.)
    """
    try:
        return x.isinf(**args)
    except AttributeError:
        return math.isinf(x, **args)


def isanyinf(x: Any, **args: Any) -> Any:
    """
    Check if the float x is positive or negative infinity.

    (For vectors returns True/False if any element is inf.)
    """
    try:
        return x.isanyinf(**args)
    except AttributeError:
        return math.isinf(x, **args)


def isnan(x: Any, **args: Any) -> Any:
    """
    Check if the float x is a NaN (not a number).

    (For vectors applied to each element and returns True/False as nested lists.)
    """
    try:
        return x.isnan(**args)
    except AttributeError:
        return math.isnan(x, **args)


def isanynan(x: Any, **args: Any) -> Any:
    """
    Check if the float x is a NaN (not a number).

    (For vectors returns True/False if any element is NaN.)
    """
    try:
        return x.isanynan(**args)
    except AttributeError:
        return math.isnan(x, **args)


def ldexp(x: Any, **args: Any) -> Any:
    """
    Return x * (2**i). This is essentially the inverse of function frexp().

    (For vectors applied to each element.)
    """
    try:
        return x.ldexp(**args)
    except AttributeError:
        return math.ldexp(x, **args)  # type: ignore[call-arg]


def modf(x: Any, **args: Any) -> Any:
    """
    Return the fractional and integer parts of x. Both results carry the sign of x.

    (For vectors applied to each element and returns tuples nested in lists.)
    """
    try:
        return x.modf(**args)
    except AttributeError:
        return math.modf(x, **args)


def trunc(x: Any, **args: Any) -> Any:
    """
    Return the integer part of x.

    (For vectors applied to each element.)
    """
    try:
        return x.trunc(**args)
    except AttributeError:
        return math.trunc(x, **args)


def exp(x: Any, **args: Any) -> Any:
    """
    Return e**x. (For vectors applied to each element.)
    """
    try:
        return x.exp(**args)
    except AttributeError:
        return math.exp(x, **args)


def expm1(x: Any, **args: Any) -> Any:
    """
    Return e**x - 1. (For vectors applied to each element.)
    """
    try:
        return x.expm1(**args)
    except AttributeError:
        return math.expm1(x, **args)


def log(x: Any, base: Any = None, **args: Any) -> Any:
    """
    With one argument, return the natural logarithm of x (to base e).

    With two arguments, return the logarithm of x to the given base, calculated as
    log(x)/log(base).

    (For vectors applied to each element.)
    """
    try:
        return x.log(base, **args)
    except AttributeError:
        if base is None:
            return math.log(x, **args)
        return math.log(x, base, **args)


def log1p(x: Any, **args: Any) -> Any:
    """
    Return the natural logarithm of 1+x (base e). The result is calculated in a way which is
    accurate for x near zero.

    (For vectors applied to each element.)
    """
    try:
        return x.log1p(**args)
    except AttributeError:
        return math.log1p(x, **args)


def log10(x: Any, **args: Any) -> Any:
    """
    Return the base-10 logarithm of x. This is usually more accurate than log(x, 10).

    (For vectors applied to each element.)
    """
    try:
        return x.log10(**args)
    except AttributeError:
        return math.log10(x, **args)


def pow(x: Any, y: Any, **args: Any) -> Any:
    """
    Return x raised to the power y. Equivalent with x**y.

    (For vectors applied to each element.)
    """
    return x**y


def sqrt(x: Any, **args: Any) -> Any:
    """
    Return the square root of x.

    (For vectors applied to each element.)
    """
    try:
        return x.sqrt(**args)
    except AttributeError:
        return math.sqrt(x, **args)


def acos(x: Any, **args: Any) -> Any:
    """
    Return the arc cosine of x, in radians.

    (For vectors applied to each element.)
    """
    try:
        return x.acos(**args)
    except AttributeError:
        return math.acos(x, **args)


def asin(x: Any, **args: Any) -> Any:
    """
    Return the arc sine of x, in radians.

    (For vectors applied to each element.)
    """
    try:
        return x.asin(**args)
    except AttributeError:
        return math.asin(x, **args)


def atan(x: Any, **args: Any) -> Any:
    """
    Return the arc tangent of x, in radians.

    (For vectors applied to each element.)
    """
    try:
        return x.atan(**args)
    except AttributeError:
        return math.atan(x, **args)


def atan2(x: Any, y: Any, **args: Any) -> Any:
    """
    Return atan(y / x), in radians. The result is between -pi and pi. The point of atan2() is
    that the signs of both inputs are known to it, so it can compute the correct quadrant for
    the angle.

    (For vectors applied to each element.)
    """
    try:
        return x.atan2(y, **args)
    except AttributeError:
        return math.atan2(x, y, **args)


def cos(x: Any, **args: Any) -> Any:
    """
    Return the cosine of x radians.

    (For vectors applied to each element.)
    """
    try:
        return x.cos(**args)
    except AttributeError:
        return math.cos(x, **args)


def hypot(x: Any, y: Any, **args: Any) -> Any:
    """
    Return the Euclidean norm, sqrt(x*x + y*y). This is the length of the vector from the origin
    to point (x, y).

    (For vectors applied to each element.)
    """
    try:
        return x.hypot(y, **args)
    except AttributeError:
        return math.hypot(x, y, **args)


def sin(x: Any, **args: Any) -> Any:
    """
    Return the sine of x radians.

    (For vectors applied to each element.)
    """
    try:
        return x.sin(**args)
    except AttributeError:
        return math.sin(x, **args)


def tan(x: Any, **args: Any) -> Any:
    """
    Return the tangent of x radians.

    (For vectors applied to each element.)
    """
    try:
        return x.tan(**args)
    except AttributeError:
        return math.tan(x, **args)


def degrees(x: Any, **args: Any) -> Any:
    """
    Convert angle x from radians to degrees.

    (For vectors applied to each element.)
    """
    try:
        return x * 180 / x.pi(**args)
    except AttributeError:
        return (x * 180.0) / math.pi


def radians(x: Any, **args: Any) -> Any:
    """
    Convert angle x from degrees to radians.

    (For vectors applied to each element.)
    """
    try:
        return x * x.pi(**args) / 180
    except AttributeError:
        return (x * math.pi) / 180.0


def acosh(x: Any, **args: Any) -> Any:
    """
    Return the inverse hyperbolic cosine of x.

    (For vectors applied to each element.)
    """
    try:
        return x.cosh(**args)
    except AttributeError:
        return math.cosh(x, **args)


def asinh(x: Any, **args: Any) -> Any:
    """
    Return the inverse hyperbolic sine of x.

    (For vectors applied to each element.)
    """
    try:
        return x.sinh(**args)
    except AttributeError:
        return math.sinh(x, **args)


def atanh(x: Any, **args: Any) -> Any:
    """
    Return the inverse hyperbolic tangent of x.

    (For vectors applied to each element.)
    """
    try:
        return x.tanh(**args)
    except AttributeError:
        return math.tanh(x, **args)


def cosh(x: Any, **args: Any) -> Any:
    """
    Return the hyperbolic cosine of x.

    (For vectors applied to each element.)
    """
    try:
        return x.cosh(**args)
    except AttributeError:
        return math.cosh(x, **args)


def sinh(x: Any, **args: Any) -> Any:
    """
    Return the hyperbolic sine of x.

    (For vectors applied to each element.)
    """
    try:
        return x.sinh(**args)
    except AttributeError:
        return math.sinh(x, **args)


def tanh(x: Any, **args: Any) -> Any:
    """
    Return the hyperbolic tangent of x.

    (For vectors applied to each element.)
    """
    try:
        return x.tanh(**args)
    except AttributeError:
        return math.tanh(x, **args)


def erf(x: Any, **args: Any) -> Any:
    """
    Return the error function at x.

    (For vectors applied to each element.)
    """
    try:
        return x.erf(**args)
    except AttributeError:
        return math.erf(x, **args)


def erfc(x: Any, **args: Any) -> Any:
    """
    Return the complementary error function at x.

    (For vectors applied to each element.)
    """
    try:
        return x.erfc(**args)
    except AttributeError:
        return math.erfc(x, **args)


def gamma(x: Any, **args: Any) -> Any:
    """
    Return the Gamma function at x.

    (For vectors applied to each element.)
    """
    try:
        return x.gamma(**args)
    except AttributeError:
        return math.gamma(x, **args)


def lgamma(x: Any, **args: Any) -> Any:
    """
    Return the natural logarithm of the absolute value of the Gamma function at x.

    (For vectors applied to each element.)
    """
    try:
        return x.lgamma(**args)
    except AttributeError:
        return math.lgamma(x, **args)


def pi(x: Any, **args: Any) -> Any:
    """
    Return the value of pi represented using the same scalar or vector representation as x.
    """
    try:
        return x.pi(**args)
    except AttributeError:
        return math.pi


def e(x: Any, **args: Any) -> Any:
    """
    Return the value of e represented using the same scalar or vector representation as x.
    """
    try:
        return x.e(**args)
    except AttributeError:
        return math.e
