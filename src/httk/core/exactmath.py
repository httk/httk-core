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
Exact math on rationals and decimals: type-preserving transcendentals.

This module provides the transcendental and helper functions used by
:class:`~httk.core.vectors.fracvector.FracVector`. Every value is computed with 100% exact
integer/rational arithmetic, so results are platform-independent and deterministic by
construction — no floating point is used anywhere in the computation.

Two output domains are supported, selected by a single documented rule. All scalar functions also
accept ``ScalarLike`` and ``VectorLike`` inputs. Vectors are mapped elementwise and retain their
shape: Fraction mode returns a ``FracVector``, while Decimal mode returns nested Decimal tuples.
The entire vector is promoted when any leaf is Decimal or ``digits=`` is passed.

    The result is a :class:`decimal.Decimal` iff any numeric input is a Decimal OR ``digits=``
    is passed; Fraction/int/str inputs otherwise get today's exact Fraction behavior with
    ``prec``/``limit`` semantics.

The exact-symbolic domain is selected by ``exact=True`` on ``sqrt`` and degree-mode trigonometric
functions. It returns exact squarefree-radical values (or exact inverse angles), with no
approximation. Exact trigonometry is available only for the complete surd-cosine angle set:
multiples of 15 and 36 degrees; unsupported values raise ``ValueError``. Exact inverse
trigonometry accepts surd values and returns exact degree Fractions.

When a genuinely irrational ``SurdScalar`` is used by ordinary Fraction-mode functions, it is
reduced to the deterministic Fraction hub at the active Decimal context precision plus three guard
digits. Exact symbolic operations preserve the surd and never use that lossy approximation.

In the **Fraction** domain each function returns a rational (:class:`fractions.Fraction`)
approximation to a target precision ``prec`` (the error bound), with ``limit`` controlling the
result denominator — exactly as before. In the **Decimal** domain the same rational algorithms
drive Ziv's adaptive strategy to produce a *correctly rounded* Decimal to ``digits`` significant
digits (default: the active :func:`decimal.getcontext` precision, matching stdlib Decimal's own
model) under ``rounding`` (``"half_even"`` = correctly rounded, ``"down"`` = correct truncation
toward zero). A Decimal input is converted to a Fraction exactly (:class:`fractions.Fraction`
accepts a Decimal), so the rational core is identical in both domains; this gives deterministic
``cos``/``sin``/``atan2``/... for Decimals, which the stdlib :mod:`decimal` module does not offer.

Note: a possible future performance follow-up is to soft-import the third-party
``cfractions`` accelerator in place of the standard-library :mod:`fractions`; the
legacy code did so, but on Python 3.12 the standard library is used unconditionally.
"""

import decimal
import fractions
import math
from collections.abc import Callable, Iterator
from functools import lru_cache, reduce
from typing import Any

default_accuracy = fractions.Fraction(1, 10000000000)

from .vectors.scalar_like import (  # noqa: E402  # required during vector import cycle
    ScalarLike,
)
from .vectors.vector_like import (  # noqa: E402  # required during vector import cycle
    VectorLike,
)

_EXACT_ANGLE_MESSAGE = (
    "exact degree-mode trigonometry is available only for the exact surd-cosine angle set "
    "(multiples of 15° and 36°; the complete square-root extension of Niven's theorem)"
)


# Euler's algorithm, code from https://code.google.com/p/mpmath/issues/detail?id=55
def get_continued_fraction(p: int, q: int) -> Iterator[int]:
    """
    Yield the terms of the continued fraction expansion of ``p/q``.
    """
    while q:
        n = p // q
        yield n
        q, p = p - q * n, q


# https://en.wikipedia.org/wiki/Continued_fraction#Best_rational_within_an_interval
def best_rational_in_interval(low: Any, high: Any) -> fractions.Fraction:
    """
    Return the rational number with the smallest denominator lying in ``[low, high]``.
    """
    low = fractions.Fraction(low)
    lowcf = get_continued_fraction(low.numerator, low.denominator)
    high = fractions.Fraction(high)
    highcf = get_continued_fraction(high.numerator, high.denominator)
    cf = []
    while True:
        try:
            nextlow = next(lowcf)
        except StopIteration:
            nextlow = None
        try:
            nexthigh = next(highcf)
        except StopIteration:
            nexthigh = None
        if nextlow is None or nexthigh is None or nextlow != nexthigh:
            break
        cf += [nextlow]
    if nexthigh is not None and nextlow is not None:
        cf += [min(nexthigh, nextlow) + 1]
    return fraction_from_continued_fraction(cf)


# http://stackoverflow.com/questions/14493901/continued-fraction-to-fraction-malfunction
def fraction_from_continued_fraction(cf: list[int]) -> fractions.Fraction:
    """
    Reconstruct a :class:`fractions.Fraction` from a list of continued-fraction terms.
    """
    return cf[0] + reduce(lambda d, n: 1 / (d + n), cf[:0:-1], fractions.Fraction(0))


def string_to_val_and_delta(
    arg: str, min_accuracy: fractions.Fraction | None = fractions.Fraction(1, 10000)
) -> tuple[fractions.Fraction, fractions.Fraction]:
    """
    Parse a numeric string into a central value and an uncertainty (delta).

    Recognizes plain decimals, fractions (``"2/3"``), scientific notation, and explicit
    standard-deviation notation (``"0.33342(10)"``). When no explicit uncertainty is
    present and ``min_accuracy`` is not None, an uncertainty is inferred from the number
    of written digits (capped at ``min_accuracy``).
    """
    arg = arg.upper()

    if arg.find("/") >= 0:
        return fractions.Fraction(arg), fractions.Fraction(0)

    sd_start = arg.find("(")
    if sd_start >= 0:
        infered_delta = False
        sd_end = arg.find(")")
        val = arg[:sd_start]
        m, _e, _exp = val.partition("E")
        sd = arg[sd_start + 1 : sd_end]
    elif min_accuracy is not None:
        infered_delta = True
        val = arg
        m, _e, _exp = val.partition("E")
        if arg.find(".") >= 0:
            m = m + "0"
        else:
            m = m + ".0"
        sd = "5"
    else:
        return fractions.Fraction(arg), fractions.Fraction(0)
    numdigits = reduce(lambda y, x: y + 1 if x.isdigit() else y, m, 0)
    replacelist = list("0" * (numdigits - len(sd)) + sd)
    delta = fractions.Fraction("".join(replacelist.pop(0) if c.isdigit() else c for c in m))
    if infered_delta and min_accuracy is not None and delta > min_accuracy:
        delta = min_accuracy
    value = fractions.Fraction(val)
    return value, delta


def any_to_fraction(
    arg: Any, min_accuracy: fractions.Fraction | None = fractions.Fraction(1, 10000)
) -> fractions.Fraction:
    """
    Convert an arbitrary numeric-like object into a :class:`fractions.Fraction`.

    Args:
        arg: a number, string, Decimal, Fraction, or anything the Fraction constructor
            accepts. Strings are parsed for uncertainty via :func:`string_to_val_and_delta`.
        min_accuracy: the minimum assumed accuracy for string input. With the default
            ``1/10000``, ``0.33`` is taken to mean ``0.3300`` (= 33/100), whereas
            ``0.3333`` is taken to mean ``1/3``. Set to None to convert strings exactly.
    """
    if isinstance(arg, str):
        val, delta = string_to_val_and_delta(arg, min_accuracy=min_accuracy)
        if delta == 0:
            return fractions.Fraction(val)
        else:
            return best_rational_in_interval(val - delta, val + delta)
    else:
        try:
            return fractions.Fraction(arg)
        except Exception:
            print("any_to_fraction tried to convert this argument and failed:", arg)
            raise


def integer_sqrt(n: int) -> int:
    """
    Return the integer square root of ``n`` (the floor of its exact square root).
    """
    x = n
    y = (x + 1) // 2
    while y < x:
        x = y
        y = (x + n // x) // 2
    return x


# --------------------------------------------------------------------------------------------
# Exact-rational algorithm cores.
#
# These private ``_frac_*`` functions are the historical exact-rational algorithms, kept
# numerically UNTOUCHED. Each takes a :class:`fractions.Fraction` and returns a Fraction
# approximation within ``prec`` of the true value (with ``limit`` controlling the result
# denominator). They back both the Fraction-domain public API (called directly) and the
# Decimal-domain public API (driven by the Ziv loop in :func:`_to_decimal`).
# --------------------------------------------------------------------------------------------


def _frac_sqrt(
    x: fractions.Fraction,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the square root of ``x`` to precision ``prec``.
    """
    # Check if there is an exact solution, in that case, make sure to return it
    sqrtnom = integer_sqrt(x.numerator)
    sqrtdenom = integer_sqrt(x.denominator)
    s = fractions.Fraction(sqrtnom, sqrtdenom)
    if s * s == x:
        return s

    # This actually accelerates convergence for 'large' numbers
    if x > 2:
        s = fractions.Fraction(integer_sqrt(x))  # type: ignore[arg-type]

    denom = int(100 / prec)
    sn = (s.numerator * denom) // s.denominator
    xn = (x.numerator * denom) // x.denominator

    while True:
        lastsn = sn
        sn = (sn * sn + xn * denom) // (2 * sn)
        if abs(sn - lastsn) < prec * denom:
            break

    s = fractions.Fraction(sn, denom)

    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


# pi, exp, cos, sin adapted from python documentation examples:
# https://docs.python.org/2/library/decimal.html
def _frac_cos(
    x: fractions.Fraction,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    degrees: bool = False,
) -> fractions.Fraction:
    """
    Return a rational approximation of the cosine of ``x`` to precision ``prec``.

    Args:
        x: the angle (in radians unless ``degrees`` is True).
        prec: the target precision, given as a Fraction.
        limit: if True, limit the denominator of the result to at most ``1/prec``.
        degrees: if True, interpret ``x`` in degrees.
    """
    if degrees:
        x *= _frac_pi(prec=prec, limit=True) / 180
    if abs(x) > 4:
        twopi = 2 * _frac_pi(prec=prec, limit=True)
        fac = (x / twopi).__trunc__()
        x -= fac * twopi

    denom = int(100 / prec)
    x2 = x**2
    x2n = (x2.numerator * denom) // x2.denominator
    i, sn, fact, numn, sign = 0, denom, 1, denom, 1
    while True:
        i += 2
        fact *= i * (i - 1)
        numn = (numn * x2n) // denom
        sign *= -1
        deltan = numn * sign
        deltad = fact
        sn = (sn * deltad + deltan) // deltad

        if abs(deltan) < prec * denom * deltad:
            break

    s = fractions.Fraction(sn, denom)

    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_sin(
    x: fractions.Fraction,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    degrees: bool = False,
) -> fractions.Fraction:
    """
    Return a rational approximation of the sine of ``x`` to precision ``prec``.

    Args:
        x: the angle (in radians unless ``degrees`` is True).
        prec: the target precision, given as a Fraction.
        limit: if True, limit the denominator of the result to at most ``1/prec``.
        degrees: if True, interpret ``x`` in degrees.
    """
    if degrees:
        x *= _frac_pi(prec=prec) / 180
    if abs(x) > 4:
        twopi = 2 * _frac_pi(prec=prec)
        fac = (x / twopi).__trunc__()
        x -= fac * twopi

    denom = int(100 / prec)
    denom2 = denom**2
    xn = (x.numerator * denom) // x.denominator
    xn2 = xn**2
    i, deltan, deltad, sn, fact, numn, sign = 1, denom, 1, xn, 1, xn, 1
    while abs(deltan) > prec * deltad * denom:
        i += 2
        fact *= i * (i - 1)
        numn = (numn * xn2) // denom2
        sign *= -1
        deltan = numn * sign
        deltad = fact
        sn = (sn * deltad + deltan) // deltad

    s = fractions.Fraction(sn, denom)

    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_exp(
    x: fractions.Fraction,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of ``e`` raised to the power of ``x`` to precision ``prec``.
    """
    denom = int(100 / prec)
    xn = (x.numerator * denom) // x.denominator

    deltan, deltad = denom, 1
    i, sn, fact, numn = 0, denom, 1, denom
    while abs(deltan) > prec * deltad * denom:
        i += 1
        fact *= i
        numn = (numn * xn) // denom
        deltan = numn
        deltad = fact
        sn = (sn * deltad + deltan) // deltad

    s = fractions.Fraction(sn, denom)

    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_pi(prec: fractions.Fraction = default_accuracy, limit: bool = True) -> fractions.Fraction:
    """
    Return a rational approximation of pi to precision ``prec``.
    """
    if prec >= fractions.Fraction(1, 10000000000000):
        return fractions.Fraction(
            1812775448643948950904740389629316518445900010127,
            577024346734625462205756697620397878260206571339,
        )

    denom = int(100 / prec)
    deltan, deltad, tn, sn, n, na, d, da = denom, 1, 3 * denom, 3 * denom, 1, 0, 0, 24

    while abs(deltan) > prec * deltad * denom:
        n, na = n + na, na + 8
        d, da = d + da, da + 32
        deltan = tn * n
        deltad = d
        tn = (tn * n) // d
        sn = (sn * deltad + deltan) // deltad

    s = fractions.Fraction(sn, denom)

    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


# The below functions have been adapted from Brian Beck and Christopher Hesse's dmath v0.9.1.
# All modifications done are copyright (c) Rickard Armiento and licensed under GNU Affero
# General Public License as part of the rest of httk. The original source is copyright (c) 2006
# Brian Beck <exogen@gmail.com>, Christopher Hesse <christopher.hesse@gmail.com> and was
# released under the MIT license.


def _frac_log(
    x: fractions.Fraction,
    base: fractions.Fraction | int | None = None,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the logarithm of ``x`` to the given ``base``.

    If the base is not specified, return the natural logarithm (base e) of ``x``.

    Note: this fails for moderately large arguments (a known legacy limitation).
    """
    # Coerce to exact Fraction up front. The legacy code left ``x`` (and ``base``, e.g. the
    # integer 10 passed by log10) as whatever type it arrived as, so the reciprocal ``1/x``
    # below produced a float for an int argument and then crashed on ``x.numerator``.
    x = fractions.Fraction(x)

    if x < 0:
        raise ValueError("log: logarithm of negative number.")
    elif base == 1:
        raise ValueError("log: logarithm of base 1 not valid.")
    elif x == base:
        return fractions.Fraction(1)
    elif x == 0:
        raise ValueError("log: logarithm of zero.")

    if base is None:
        log_base: fractions.Fraction | int = 1
    else:
        log_base = _frac_log(fractions.Fraction(base), prec=prec, limit=limit)

    if x > 1:
        inv = True
        x = 1 / x
    else:
        inv = False

    # Tests give that we need more accuracy margin for this one
    prec = prec / 1000
    denom = int(100 / prec)
    xn = (x.numerator * denom) // x.denominator

    def frac_inner_exp(xn: int) -> int:
        deltan, deltad = denom, 1
        i, sn, fact, numn = 0, denom, 1, denom
        while abs(deltan) > prec * deltad * denom:
            i += 1
            fact *= i
            numn = (numn * xn) // denom
            deltan = numn
            deltad = fact
            sn = (sn * deltad + deltan) // deltad
        return sn

    sn = denom
    while True:
        en = frac_inner_exp(sn)
        deltan = (en - xn) * denom
        deltad = en
        sn = (sn * deltad - deltan) // deltad
        if abs(deltan) < abs(prec * deltad * denom):
            break

    if inv:
        s = fractions.Fraction(-sn, denom)
    else:
        s = fractions.Fraction(sn, denom)
    s /= log_base

    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_tan(
    x: fractions.Fraction,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the tangent of ``x`` to precision ``prec``.
    """
    s = _frac_sin(x, prec=prec, limit=False) / _frac_cos(x, prec=prec, limit=False)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_asin(
    x: fractions.Fraction,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction | int:
    """
    Return a rational approximation of the arc sine (in radians, or degrees if ``degrees``
    is True) of ``x`` to precision ``prec``.
    """
    iteracc = int(1 / (prec * 100))
    if abs(x) > 1:
        raise ValueError("Domain error: asin accepts -1 <= x <= 1")

    if degrees:
        if x == -1:
            return fractions.Fraction(180, -2)
        elif x == 0:
            return 0
        elif x == 1:
            return fractions.Fraction(180, 2)
    else:
        if x == -1:
            return _frac_pi(prec=prec, limit=limit) / -2
        elif x == 0:
            return fractions.Fraction(0)
        elif x == 1:
            return _frac_pi(prec=prec, limit=limit) / 2

    one_half = fractions.Fraction(1, 2)
    i, lasts, s, gamma, fact, num = (
        fractions.Fraction(0),
        fractions.Fraction(0),
        x,
        fractions.Fraction(1),
        fractions.Fraction(1),
        x,
    )
    while abs(s - lasts) > prec:
        lasts = s
        i += 1
        fact *= i
        num *= x * x
        gamma *= i - one_half
        coeff = gamma / ((2 * i + 1) * fact)
        s += coeff * num
        # The sizes of these numbers need to be kept under control during iteration
        num = num.limit_denominator(iteracc)
        s = s.limit_denominator(iteracc)
    if degrees:
        s = s * 180 / _frac_pi(prec=prec, limit=limit)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_acos(
    x: fractions.Fraction,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the arc cosine (in radians, or degrees if
    ``degrees`` is True) of ``x`` to precision ``prec``.
    """
    if abs(x) > 1:
        raise ValueError("Domain error: acos accepts -1 <= x <= 1")
    PI = _frac_pi(prec=prec, limit=False)

    if x == 1:
        return fractions.Fraction(0)
    else:
        if x == -1:
            return PI
        elif x == 0:
            return PI / 2

    s = PI / 2 - _frac_atan2(x, _frac_sqrt(1 - x**2, prec=prec, limit=limit), prec=prec, limit=limit)

    if degrees:
        s = s * 180 / PI
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_atan(
    x: fractions.Fraction,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the arc tangent (in radians, or degrees if
    ``degrees`` is True) of ``x`` to precision ``prec``.
    """
    c: fractions.Fraction | None = None
    if x == 0:
        return fractions.Fraction(0)
    elif abs(x) > 1:
        PI = _frac_pi(prec=prec, limit=False)
        if x < 0:
            c = -PI / 2
        else:
            c = PI / 2
        x = 1 / x

    denom = int(100 / prec)

    x_squared = x**2
    y = x_squared / (1 + x_squared)
    yn = (y.numerator * denom) // y.denominator
    s = y / x
    sn = (s.numerator * denom) // s.denominator

    i = 0
    coeffn = 1
    coeffd = 1
    numn = sn
    deltan = denom

    while abs(deltan) > prec * denom:
        i += 2
        coeffn = coeffn * i
        coeffd = coeffd * (i + 1)
        numn = (numn * yn) // denom
        deltan = (coeffn * numn) // coeffd
        sn = sn + deltan

    s = fractions.Fraction(sn, denom)

    if c:
        s = c - s
    if degrees:
        s = s * 180 / _frac_pi(prec=prec, limit=limit)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_atan2(
    y: fractions.Fraction,
    x: fractions.Fraction,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the arc tangent of ``y/x`` (in radians, or
    degrees if ``degrees`` is True) to precision ``prec``.

    Unlike ``atan(y/x)``, the signs of both ``x`` and ``y`` are considered, following
    the quadrant conventions of :func:`math.atan2` (so ``atan2(0, -1)`` is pi and
    ``atan2(1, 0)`` is pi/2).
    """
    if x != 0:
        a = y and _frac_atan(y / x, prec=prec, limit=limit) or fractions.Fraction(0)
        if x < 0:
            if y >= 0:
                a += _frac_pi(prec=prec, limit=limit)
            else:
                a -= _frac_pi(prec=prec, limit=limit)
    elif y > 0:
        a = _frac_pi(prec=prec, limit=limit) / 2
    elif y < 0:
        a = -_frac_pi(prec=prec, limit=limit) / 2
    else:
        a = fractions.Fraction(0)
    if degrees:
        a = a * 180 / _frac_pi(prec=prec, limit=limit)
        if limit:
            a = a.limit_denominator(int(1 / prec))
    return a


# --------------------------------------------------------------------------------------------
# Decimal domain: correctly-rounded rendering via Ziv's adaptive strategy.
# --------------------------------------------------------------------------------------------

# Vocabulary matching the decimal module's constants, extensible later.
_VALID_ROUNDINGS = ("half_even", "down")

# Ziv loop shape: start comfortably tighter than the requested significant digits, then tighten
# the rational error bound aggressively each refinement, with a defensive cap that raises rather
# than spinning. Irrational values are never exactly on a quantization boundary, so a handful of
# refinements always suffices; exact rational results short-circuit before the loop entirely.
_ZIV_GUARD_DIGITS = 3
_ZIV_TIGHTEN = fractions.Fraction(1, 10**4)
_ZIV_CAP = 64


def _validate_decimal_params(digits: int | None, rounding: str, max_refinements: int | None = None) -> None:
    """Validate Decimal-mode ``digits``, ``rounding``, and ``max_refinements`` eagerly."""
    if digits is not None and (not isinstance(digits, int) or isinstance(digits, bool) or digits <= 0):
        raise ValueError(f"invalid digits {digits!r}; expected a positive integer or None")
    if rounding not in _VALID_ROUNDINGS:
        raise ValueError(f"unknown rounding {rounding!r}; expected one of {list(_VALID_ROUNDINGS)}")
    if max_refinements is not None and (
        not isinstance(max_refinements, int) or isinstance(max_refinements, bool) or max_refinements < 0
    ):
        raise ValueError(f"invalid max_refinements {max_refinements!r}; expected a non-negative integer or None")


def _ge_pow10(num: int, den: int, p: int) -> bool:
    """Exact test ``num/den >= 10**p`` for positive ``num``, ``den`` and any integer ``p``."""
    if p >= 0:
        return num >= den * 10**p
    return num * 10 ** (-p) >= den


def _floor_log10(num: int, den: int) -> int:
    """
    Return ``floor(log10(num/den))`` for positive integers ``num``, ``den``, exactly.

    The decimal exponent is derived from integer digit counts (never a float ``log10``): the
    guess ``len(str(num)) - len(str(den))`` is off by at most one, and is corrected by exact
    integer comparisons against powers of ten so that magnitude boundaries (e.g. 0.09999.. vs
    0.1) are resolved without rounding error.
    """
    e = len(str(num)) - len(str(den))
    while _ge_pow10(num, den, e + 1):
        e += 1
    while not _ge_pow10(num, den, e):
        e -= 1
    return e


def _quantize_fraction(r: fractions.Fraction, sig: int, rounding: str) -> decimal.Decimal:
    """
    Round the exact rational ``r`` to ``sig`` significant digits, returning a :class:`decimal.Decimal`.

    All arithmetic is exact integer arithmetic: the decimal exponent of ``|r|`` is found via
    :func:`_floor_log10`, then the value is scaled by the appropriate power of ten (as integers)
    and rounded to an integer under the requested mode (``"half_even"`` correctly rounds, ``"down"``
    truncates toward zero). Because this operates on the exact ``r``, a value that sits exactly on a
    rounding boundary is resolved exactly (half-even applies exactly; down truncates exactly).
    """
    if r == 0:
        return decimal.Decimal(0)
    sign = 0 if r > 0 else 1
    a = -r if r < 0 else r
    num, den = a.numerator, a.denominator
    e = _floor_log10(num, den)
    k = sig - 1 - e
    if k >= 0:
        scaled_num, scaled_den = num * 10**k, den
    else:
        scaled_num, scaled_den = num, den * 10 ** (-k)
    q, rem = divmod(scaled_num, scaled_den)
    if rounding == "down":
        m = q
    else:  # half_even
        twice = 2 * rem
        if twice < scaled_den:
            m = q
        elif twice > scaled_den:
            m = q + 1
        else:
            m = q if q % 2 == 0 else q + 1
    if m == 10**sig:
        # Rounding carried into a new leading digit (e.g. 9.99 -> 10 at 2 sig figs); renormalize
        # so the digit tuple keeps exactly ``sig`` digits.
        m //= 10
        k -= 1
    if m == 0:
        return decimal.Decimal(0)
    digits = tuple(int(c) for c in str(m))
    return decimal.Decimal((sign, digits, -k))


def _finite_decimal_expansion(value: fractions.Fraction) -> decimal.Decimal | None:
    """
    Return the exact :class:`decimal.Decimal` for ``value`` if it has a finite decimal expansion.

    A reduced denominator of the form ``2**a * 5**b`` has a finite decimal expansion; the exact
    Decimal is built from its digit tuple with no rounding and independent of the active decimal
    context. Returns None when no finite expansion exists. This is the shared home of the
    finite-expansion logic reused by :mod:`httk.core.vectors.leaf_codecs`'s decimal codec.
    """
    stripped = value.denominator
    twos = 0
    fives = 0
    while stripped % 2 == 0:
        stripped //= 2
        twos += 1
    while stripped % 5 == 0:
        stripped //= 5
        fives += 1
    if stripped != 1:
        return None
    scale = max(twos, fives)
    scaled = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    sign = 0 if scaled >= 0 else 1
    digit_tuple = tuple(int(c) for c in str(abs(scaled)))
    return decimal.Decimal((sign, digit_tuple, -scale))


def _significant_digits(d: decimal.Decimal) -> int:
    """Number of significant digits in the finite Decimal ``d`` (0 for zero)."""
    if d.is_zero():
        return 0
    return len(d.as_tuple().digits)


def _to_decimal(
    compute: Callable[[fractions.Fraction], tuple[fractions.Fraction, bool]],
    digits: int | None,
    rounding: str,
    max_refinements: int | None = None,
) -> decimal.Decimal:
    """
    Render ``compute`` to a correctly-rounded Decimal using Ziv's adaptive strategy.

    ``compute(prec) -> (value, exact)`` returns a rational ``value`` within ``prec`` of the true
    result together with a flag stating whether ``value`` is the *exact* result (the algorithms'
    exact rational short-circuits). The result is rounded to ``sig`` significant digits (``digits``,
    or the active context precision when None) under ``rounding``:

    - When ``exact`` is reported, the exact value is rendered directly — as its exact finite
      expansion when that fits within ``sig`` digits, otherwise quantized to ``sig`` digits (so an
      exact value on a rounding boundary is resolved by exact arithmetic, no iteration).
    - Otherwise the interval ``[value - prec, value + prec]`` is quantized; if both endpoints
      agree the shared candidate is correctly rounded, else ``prec`` is tightened and ``compute``
      re-run.

    Termination is guaranteed, not merely bounded: after the exact rational short-circuits
    (perfect squares; the Niven special angles for degree-mode trigonometry and their
    inverses; ``exp(0)``/``log(1)``; and the finite exact rational-logarithm decision), every
    remaining value is provably irrational — by the Lindemann-Weierstrass theorem for
    ``exp``/``log`` and radian trigonometry, by Niven's theorem for degree-mode trigonometry,
    and by elementary algebra for square roots — and an irrational value is never exactly on a
    (rational) rounding boundary, so the interval always eventually disambiguates. The
    iteration bound below is therefore unreachable and guards only against implementation
    bugs.

    Bounded-time mode: with ``max_refinements=k`` (a non-negative integer), at most ``k``
    refinements are performed; if the interval is still ambiguous the *approximation itself*
    is rounded deterministically and returned. The whole pipeline is exact integer
    arithmetic, so this is a well-defined, platform-independent function of the inputs: the
    result is correctly rounded unless the true value lies within
    ``10**-(sig + 3 + 4*k)`` of a rounding boundary, in which case the returned value is the
    deterministic rounding of the deterministic approximant — one of the two neighbouring
    representables, i.e. off by at most one unit in the last place.
    """
    sig = decimal.getcontext().prec if digits is None else digits
    prec = fractions.Fraction(1, 10 ** (sig + _ZIV_GUARD_DIGITS))
    rounds = _ZIV_CAP if max_refinements is None else max_refinements + 1
    for attempt in range(rounds):
        value, exact = compute(prec)
        if exact:
            finite = _finite_decimal_expansion(value)
            if finite is not None and _significant_digits(finite) <= sig:
                return finite
            return _quantize_fraction(value, sig, rounding)
        low = _quantize_fraction(value - prec, sig, rounding)
        high = _quantize_fraction(value + prec, sig, rounding)
        if low == high:
            return low
        if max_refinements is not None and attempt == rounds - 1:
            # Bounded-time exit: deterministically round the (deterministic) approximation.
            return _quantize_fraction(value, sig, rounding)
        prec *= _ZIV_TIGHTEN
    raise RuntimeError(
        "exactmath: the Ziv refinement bound was reached, which the termination guarantee "
        "proves unreachable - please report this as a bug "
        f"(digits={sig}, rounding={rounding!r})"
    )


# --------------------------------------------------------------------------------------------
# Decimal-domain compute cores: ``(value, exact)`` for the Ziv loop. Each detects its exact
# rational short-circuits (returning ``exact=True``) and otherwise defers to the ``_frac_*``
# algorithm for a ``prec``-accurate approximation (``exact=False``).
# --------------------------------------------------------------------------------------------

# The special angles (in degrees, reduced to [0, 360)) at which cos/sin are exact rationals.
_COS_EXACT_DEG = {
    0: fractions.Fraction(1),
    60: fractions.Fraction(1, 2),
    90: fractions.Fraction(0),
    120: fractions.Fraction(-1, 2),
    180: fractions.Fraction(-1),
    240: fractions.Fraction(-1, 2),
    270: fractions.Fraction(0),
    300: fractions.Fraction(1, 2),
}
_TAN_EXACT_DEG = {
    0: fractions.Fraction(0),
    45: fractions.Fraction(1),
    135: fractions.Fraction(-1),
    180: fractions.Fraction(0),
    225: fractions.Fraction(1),
    315: fractions.Fraction(-1),
}
_SIN_EXACT_DEG = {
    0: fractions.Fraction(0),
    30: fractions.Fraction(1, 2),
    90: fractions.Fraction(1),
    150: fractions.Fraction(1, 2),
    180: fractions.Fraction(0),
    210: fractions.Fraction(-1, 2),
    270: fractions.Fraction(-1),
    330: fractions.Fraction(-1, 2),
}


def _exact_trig_degrees(x: fractions.Fraction, table: dict[int, fractions.Fraction]) -> fractions.Fraction | None:
    """Return the exact rational trig value for an integer number of degrees, reduced mod 360."""
    r = x - 360 * (x // 360)
    if r.denominator == 1 and int(r) in table:
        return table[int(r)]
    return None


def _sqrt_core(x: fractions.Fraction, prec: fractions.Fraction) -> tuple[fractions.Fraction, bool]:
    s = fractions.Fraction(integer_sqrt(x.numerator), integer_sqrt(x.denominator))
    if s * s == x:
        return s, True
    return _frac_sqrt(x, prec=prec, limit=False), False


def _cos_core(x: fractions.Fraction, prec: fractions.Fraction, degrees: bool) -> tuple[fractions.Fraction, bool]:
    exact = _exact_trig_degrees(x, _COS_EXACT_DEG) if degrees else (fractions.Fraction(1) if x == 0 else None)
    if exact is not None:
        return exact, True
    return _frac_cos(x, prec=prec, limit=False, degrees=degrees), False


def _sin_core(x: fractions.Fraction, prec: fractions.Fraction, degrees: bool) -> tuple[fractions.Fraction, bool]:
    exact = _exact_trig_degrees(x, _SIN_EXACT_DEG) if degrees else (fractions.Fraction(0) if x == 0 else None)
    if exact is not None:
        return exact, True
    return _frac_sin(x, prec=prec, limit=False, degrees=degrees), False


def _tan_core(x: fractions.Fraction, prec: fractions.Fraction, degrees: bool) -> tuple[fractions.Fraction, bool]:
    if degrees:
        exact = _exact_trig_degrees(x, _TAN_EXACT_DEG)
        if exact is not None:
            return exact, True
    cos_val, cos_exact = _cos_core(x, prec, degrees)
    sin_val, sin_exact = _sin_core(x, prec, degrees)
    if cos_exact and sin_exact and cos_val != 0:
        return sin_val / cos_val, True
    # Approximation as the ratio of the (degrees-aware) sin and cos approximations.
    approx = _frac_sin(x, prec=prec, limit=False, degrees=degrees) / _frac_cos(
        x, prec=prec, limit=False, degrees=degrees
    )
    return approx, False


def _exp_core(x: fractions.Fraction, prec: fractions.Fraction) -> tuple[fractions.Fraction, bool]:
    if x == 0:
        return fractions.Fraction(1), True
    return _frac_exp(x, prec=prec, limit=False), False


def _rational_log(x: fractions.Fraction, base: fractions.Fraction) -> fractions.Fraction | None:
    """
    Return ``log(x, base)`` as an exact Fraction when it is rational, else None.

    ``log_base(x) = p/q`` (in lowest terms) requires ``x**q == base**p``, and taking prime
    valuations of that identity with ``gcd(p, q) == 1`` forces ``q`` to divide every prime
    exponent of ``base`` — so ``q`` is bounded by the largest prime exponent of ``base``,
    itself at most the bit length of base's numerator/denominator. For each such ``q`` a
    rigorous window for ``p`` follows from a coarse exact-log bound, and each candidate is
    verified with exact integer arithmetic. This makes "is the logarithm rational?" a finite,
    deterministic decision — the key to the module's termination guarantee.
    """
    if x <= 0 or base <= 0 or base == 1:
        return None
    if x == 1:
        return fractions.Fraction(0)
    q_max = max(base.numerator.bit_length(), base.denominator.bit_length())
    for q in range(1, q_max + 1):
        bound = fractions.Fraction(1, 8 * q)
        approx = _frac_log(x, base=base, prec=bound, limit=False)
        low = math.floor(q * (approx - bound))
        high = math.ceil(q * (approx + bound))
        for p_cand in range(low, high + 1):
            if x**q == base**p_cand:
                return fractions.Fraction(p_cand, q)
    return None


def _log_core(
    x: fractions.Fraction,
    base: fractions.Fraction | int | None,
    prec: fractions.Fraction,
) -> tuple[fractions.Fraction, bool]:
    if x == 1:
        return fractions.Fraction(0), True
    if base is not None:
        base_frac = fractions.Fraction(base)
        rational = _rational_log(x, base_frac)
        if rational is not None:
            return rational, True
    return _frac_log(x, base=base, prec=prec, limit=False), False


def _asin_core(x: fractions.Fraction, prec: fractions.Fraction, degrees: bool) -> tuple[fractions.Fraction, bool]:
    if x == 0:
        return fractions.Fraction(0), True
    if degrees:
        if x == 1:
            return fractions.Fraction(90), True
        if x == -1:
            return fractions.Fraction(-90), True
        if x == fractions.Fraction(1, 2):
            return fractions.Fraction(30), True
        if x == fractions.Fraction(-1, 2):
            return fractions.Fraction(-30), True
    return fractions.Fraction(_frac_asin(x, prec=prec, limit=False, degrees=degrees)), False


def _acos_core(x: fractions.Fraction, prec: fractions.Fraction, degrees: bool) -> tuple[fractions.Fraction, bool]:
    if x == 1:
        return fractions.Fraction(0), True
    if degrees:
        if x == -1:
            return fractions.Fraction(180), True
        if x == 0:
            return fractions.Fraction(90), True
        if x == fractions.Fraction(1, 2):
            return fractions.Fraction(60), True
        if x == fractions.Fraction(-1, 2):
            return fractions.Fraction(120), True
    return _frac_acos(x, prec=prec, limit=False, degrees=degrees), False


def _atan_core(x: fractions.Fraction, prec: fractions.Fraction, degrees: bool) -> tuple[fractions.Fraction, bool]:
    if x == 0:
        return fractions.Fraction(0), True
    if degrees:
        if x == 1:
            return fractions.Fraction(45), True
        if x == -1:
            return fractions.Fraction(-45), True
    return _frac_atan(x, prec=prec, limit=False, degrees=degrees), False


def _atan2_core(
    y: fractions.Fraction,
    x: fractions.Fraction,
    prec: fractions.Fraction,
    degrees: bool,
) -> tuple[fractions.Fraction, bool]:
    if x > 0 and y == 0:
        return fractions.Fraction(0), True
    if degrees:
        if x == 0 and y > 0:
            return fractions.Fraction(90), True
        if x == 0 and y < 0:
            return fractions.Fraction(-90), True
        if x < 0 and y == 0:
            return fractions.Fraction(180), True
        if y == x and x > 0:
            return fractions.Fraction(45), True
        if y == -x and x < 0:
            return fractions.Fraction(135), True
        if y == x and x < 0:
            return fractions.Fraction(-135), True
        if y == -x and x > 0:
            return fractions.Fraction(-45), True
    return _frac_atan2(y, x, prec=prec, limit=False, degrees=degrees), False


# --------------------------------------------------------------------------------------------
# Public, type-preserving API. The result is Decimal iff any numeric input is a Decimal OR
# ``digits=`` is passed; otherwise the exact Fraction contract (``prec``/``limit``) is preserved.
# --------------------------------------------------------------------------------------------


def _coerce(x: Any) -> tuple[fractions.Fraction, bool]:
    """Coerce one scalar input to the rational hub and report Decimal promotion."""
    x = _unwrap_scalar_backend(x)
    if isinstance(x, decimal.Decimal):
        return fractions.Fraction(x), True
    if isinstance(x, (int, float, str, fractions.Fraction)):
        # Fraction(float) intentionally embeds the float's exact binary value. Strings use the
        # public scalar contract (unlike FracVector.create, no inferred uncertainty).
        return fractions.Fraction(x), False

    from .vectors.fracvector import FracVector
    from .vectors.surdvector import SurdVector

    if isinstance(x, FracVector):
        if x.dim != ():
            raise TypeError(f"expected a scalar, got vector shape {x.dim}")
        return x.to_fraction(), False
    if isinstance(x, SurdVector):
        if x.dim != ():
            raise TypeError(f"expected a scalar, got vector shape {x.dim}")
        if x.is_rational:
            return x._rational_fraction(), False
        # Match VectorSurd's deterministic Fraction hub: active context precision plus guard
        # digits. The exact surd remains available to exact=True operations.
        prec = fractions.Fraction(1, 10 ** (decimal.getcontext().prec + 3))
        return fractions.Fraction(x.to_fractions_approx(prec=prec)), False
    shape = getattr(x, "shape", None)
    if shape is not None and tuple(shape) == ():
        return fractions.Fraction(float(x)), False
    if hasattr(x, "dim") and hasattr(x, "fractions"):
        if x.dim != ():
            raise TypeError(f"expected a scalar, got vector shape {x.dim}")
        value = x.fractions
        if isinstance(value, tuple):
            raise TypeError(f"expected a scalar, got vector shape {x.dim}")
        return _coerce(value)
    raise TypeError(f"unsupported exact-math scalar {x!r}")


def _unwrap_scalar_backend(value: Any) -> Any:
    """Unwrap a dim-() backend/view before scalar coercion, preserving exact surds."""
    if getattr(value, "dim", None) == () and hasattr(value, "unwrap"):
        raw = value.unwrap()
        if raw is not value:
            return raw
    return value


def _is_vector_input(x: Any) -> bool:
    """Return whether ``x`` is a non-scalar VectorLike value without importing numpy."""
    dim = getattr(x, "dim", None)
    if dim is not None:
        return dim != ()
    if isinstance(x, (list, tuple)):
        return True
    shape = getattr(x, "shape", None)
    return shape is not None and tuple(shape) != ()


def _as_lists(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_as_lists(item) for item in value]
    return value


def _vector_data(value: Any) -> tuple[Any, tuple[int, ...]]:
    """Return vector leaves and shape, retaining exact surd leaves where available."""
    from .vectors.fracvector import FracVector
    from .vectors.surdvector import SurdVector

    if isinstance(value, FracVector):
        data = _as_lists(value.to_fractions())
        return data, value.dim
    if isinstance(value, SurdVector):
        dim = value.dim

        def build(index: tuple[int, ...], depth: int) -> Any:
            if depth == len(dim):
                return value._element(index)
            return [build(index + (i,), depth + 1) for i in range(dim[depth])]

        return build((), 0), dim
    if isinstance(value, (list, tuple)):
        data = _as_lists(value)
    elif hasattr(value, "unwrap"):
        raw = value.unwrap()
        if raw is not value:
            return _vector_data(raw)
        data = _as_lists(value.fractions)
    elif hasattr(value, "tolist"):
        data = _as_lists(value.tolist())
    elif hasattr(value, "fractions"):
        data = _as_lists(value.fractions)
    else:
        raise TypeError(f"unsupported vector input {value!r}")

    def shape(node: Any) -> tuple[int, ...]:
        if not isinstance(node, list):
            return ()
        if not node:
            return (0,)
        return (len(node),) + shape(node[0])

    return data, shape(data)


def _contains_decimal(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return any(_contains_decimal(item) for item in value)
    return isinstance(value, decimal.Decimal)


def _map_nested(value: Any, function: Callable[[Any], Any]) -> Any:
    if isinstance(value, list):
        return [_map_nested(item, function) for item in value]
    return function(value)


def _map_binary_nested(left: Any, right: Any, function: Callable[[Any, Any], Any]) -> Any:
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            raise ValueError("vector shapes do not match for elementwise operation")
        return [_map_binary_nested(a, b, function) for a, b in zip(left, right)]
    if isinstance(left, list):
        return [_map_binary_nested(a, right, function) for a in left]
    if isinstance(right, list):
        return [_map_binary_nested(left, b, function) for b in right]
    return function(left, right)


def _tuple_nested(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple_nested(item) for item in value)
    return value


def _map_vector(value: Any, function: Callable[[Any], Any], *, decimal_mode: bool, exact: bool) -> Any:
    """Apply a scalar operation to a vector and construct the documented output domain."""
    data, dim = _vector_data(value)
    mapped = _map_nested(data, function)
    if exact:
        from .vectors.surdvector import SurdVector

        return SurdVector._from_scalar_grid(_map_nested(mapped, _as_surd_scalar), dim)
    if decimal_mode:
        return _tuple_nested(mapped)
    from .vectors.fracvector import FracVector

    return FracVector.create(mapped)


def _map_binary_vector(
    left: Any,
    right: Any,
    function: Callable[[Any, Any], Any],
    *,
    decimal_mode: bool,
    exact: bool,
) -> Any:
    left_data, left_dim = _vector_data(left) if _is_vector_input(left) else (left, ())
    right_data, right_dim = _vector_data(right) if _is_vector_input(right) else (right, ())
    if left_dim != () and right_dim != () and left_dim != right_dim:
        raise ValueError(f"vector shapes do not match: {left_dim} vs {right_dim}")
    dim = left_dim if left_dim != () else right_dim
    mapped = _map_binary_nested(left_data, right_data, function)
    if exact:
        from .vectors.surdvector import SurdVector

        return SurdVector._from_scalar_grid(_map_nested(mapped, _as_surd_scalar), dim)
    if decimal_mode:
        return _tuple_nested(mapped)
    from .vectors.fracvector import FracVector

    return FracVector.create(mapped)


def _effective_digits(digits: int | None, decimal_mode: bool, exact: bool) -> int | None:
    if exact or not decimal_mode:
        return digits
    return decimal.getcontext().prec if digits is None else digits


def _as_surd_scalar(value: Any):
    from .vectors.surdvector import SurdVector

    value = _unwrap_scalar_backend(value)
    if isinstance(value, SurdVector):
        if value.dim != ():
            raise TypeError(f"expected a scalar, got vector shape {value.dim}")
        return value._as_scalar()
    return SurdVector.create(_coerce(value)[0])._as_scalar()


def _reject_genuine_surd(value: Any) -> None:
    from .vectors.surdvector import SurdVector

    value = _unwrap_scalar_backend(value)
    if isinstance(value, SurdVector) and not value.is_rational:
        raise ValueError("exact square roots and exact angle inputs require a rational value")


def _exact_cos(x: Any):
    from .vectors.surdvector import SurdScalar

    _reject_genuine_surd(x)
    result = SurdScalar.cos_degrees(_coerce(x)[0])
    if result is None:
        raise ValueError(_EXACT_ANGLE_MESSAGE)
    return result


def _exact_sin(x: Any):
    from .vectors.surdvector import SurdScalar

    _reject_genuine_surd(x)
    result = SurdScalar.sin_degrees(_coerce(x)[0])
    if result is None:
        raise ValueError(_EXACT_ANGLE_MESSAGE)
    return result


def _exact_tan(x: Any):
    cosine = _exact_cos(x)
    if cosine.is_zero():
        raise ValueError("exact tangent is undefined where the cosine is zero")
    return _exact_sin(x) / cosine


def _exact_acos(x: Any) -> fractions.Fraction:
    result = _as_surd_scalar(x).acos_degrees()
    if result is None:
        raise ValueError(_EXACT_ANGLE_MESSAGE)
    return result


def _exact_asin(x: Any) -> fractions.Fraction:
    result = _as_surd_scalar(x).acos_degrees()
    if result is None:
        raise ValueError(_EXACT_ANGLE_MESSAGE)
    return fractions.Fraction(90) - result


@lru_cache(maxsize=1)
def _exact_tangent_table() -> tuple[tuple[Any, fractions.Fraction], ...]:
    from .vectors.surdvector import SurdScalar

    values: list[tuple[Any, fractions.Fraction]] = []
    for angle in range(-90, 91):
        cosine = SurdScalar.cos_degrees(angle)
        sine = SurdScalar.sin_degrees(angle)
        if cosine is not None and sine is not None and not cosine.is_zero():
            values.append((sine / cosine, fractions.Fraction(angle)))
    return tuple(values)


def _exact_atan(x: Any) -> fractions.Fraction:
    value = _as_surd_scalar(x)
    for tangent, angle in _exact_tangent_table():
        if value == tangent:
            return angle
    raise ValueError(_EXACT_ANGLE_MESSAGE)


def _exact_atan2(y: Any, x: Any) -> fractions.Fraction:
    y_value = _as_surd_scalar(y)
    x_value = _as_surd_scalar(x)
    if x_value.is_zero():
        if y_value.is_zero():
            return fractions.Fraction(0)
        return fractions.Fraction(90 if y_value > 0 else -90)
    principal = _exact_atan(y_value / x_value)
    if x_value > 0:
        return principal
    return principal + (fractions.Fraction(180) if y_value >= 0 else fractions.Fraction(-180))


def _is_decimal(*args: Any) -> bool:
    return any(isinstance(a, decimal.Decimal) for a in args)


def sqrt(
    x: ScalarLike | VectorLike,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> Any:
    """
    Return the square root of ``x``.

    Fraction domain (Fraction/int/str input, no ``digits=``): a rational approximation within
    ``prec`` (exact for perfect squares), ``limit`` controlling the denominator. Decimal domain
    (Decimal input or ``digits=`` given): the correctly-rounded Decimal to ``digits`` significant
    digits under ``rounding``.

    With ``exact=True`` the output-domain rule is overridden: the result is the **exact**
    :class:`~httk.core.vectors.surdvector.SurdScalar` square root of ``x`` — an element of the
    squarefree-radical field, with no approximation at all (``sqrt(2, exact=True)`` squares back to
    exactly ``2``, ``sqrt(9/4, exact=True)`` is the rational ``3/2``). ``x`` must be a nonnegative
    rational; ``prec``/``limit``/``digits``/``rounding`` are ignored in this mode.
    """
    if exact:
        _reject_genuine_surd(x)
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: sqrt(
                item,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        # Lazy import to avoid an import cycle (surdvector imports from exactmath).
        from httk.core.vectors.surdvector import SurdVector

        _reject_genuine_surd(x)
        return SurdVector.sqrt_of(xf)
    if digits is None and not decimal_input:
        return _frac_sqrt(xf, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _sqrt_core(xf, p), digits, rounding, max_refinements)


def cos(
    x: ScalarLike | VectorLike,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    degrees: bool = False,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> Any:
    """
    Return the cosine of ``x`` (radians unless ``degrees`` is True). See the module docstring for
    the type-preservation rule; Decimal mode renders the special-angle exact values exactly (e.g.
    ``cos(Decimal("60"), degrees=True) == Decimal("0.5")``).
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if exact:
        _reject_genuine_surd(x)
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: cos(
                item,
                prec=prec,
                limit=limit,
                degrees=degrees,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        return _exact_cos(x)
    if digits is None and not decimal_input:
        return _frac_cos(xf, prec=prec, limit=limit, degrees=degrees)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _cos_core(xf, p, degrees), digits, rounding, max_refinements)


def sin(
    x: ScalarLike | VectorLike,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    degrees: bool = False,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> Any:
    """
    Return the sine of ``x`` (radians unless ``degrees`` is True). See the module docstring for the
    type-preservation rule.
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if exact:
        _reject_genuine_surd(x)
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: sin(
                item,
                prec=prec,
                limit=limit,
                degrees=degrees,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        return _exact_sin(x)
    if digits is None and not decimal_input:
        return _frac_sin(xf, prec=prec, limit=limit, degrees=degrees)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _sin_core(xf, p, degrees), digits, rounding, max_refinements)


def tan(
    x: ScalarLike | VectorLike,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> Any:
    """
    Return the tangent of ``x``. See the module docstring for the type-preservation rule.
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if exact:
        _reject_genuine_surd(x)
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: tan(
                item,
                degrees=degrees,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        return _exact_tan(x)
    if digits is None and not decimal_input:
        return _frac_tan(xf, degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _tan_core(xf, p, degrees), digits, rounding, max_refinements)


def exp(
    x: ScalarLike | VectorLike,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
) -> Any:
    """
    Return ``e`` raised to the power ``x``. See the module docstring for the type-preservation rule.
    """
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, False)
        if decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: exp(
                item,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
            ),
            decimal_mode=decimal_mode,
            exact=False,
        )
    xf, decimal_input = _coerce(x)
    if digits is None and not decimal_input:
        return _frac_exp(xf, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _exp_core(xf, p), digits, rounding, max_refinements)


def log(
    x: ScalarLike | VectorLike,
    base: ScalarLike | None = None,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the logarithm of ``x`` to ``base`` (natural log when ``base`` is None). See the module
    docstring for the type-preservation rule; a Decimal ``base`` also promotes the result.
    """
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data) or _contains_decimal(base)
        vector_digits = _effective_digits(digits, decimal_mode, False)
        if decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: log(
                item,
                base=base,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
            ),
            decimal_mode=decimal_mode,
            exact=False,
        )
    xf, decimal_input = _coerce(x)
    basef, base_decimal = (None, False) if base is None else _coerce(base)
    if digits is None and not (decimal_input or base_decimal):
        return _frac_log(xf, base=None if base is None else basef, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _log_core(xf, basef, p), digits, rounding, max_refinements)


def log10(
    x: ScalarLike | VectorLike,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the base-10 logarithm of ``x``. See the module docstring for the type-preservation rule.
    ``max_refinements`` is honored and is forwarded to the logarithm implementation.
    """
    return log(
        x,
        base=10,
        prec=prec,
        limit=limit,
        digits=digits,
        rounding=rounding,
        max_refinements=max_refinements,
    )


def asin(
    x: ScalarLike | VectorLike,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> fractions.Fraction | int | decimal.Decimal:
    """
    Return the arc sine of ``x`` (radians, or degrees if ``degrees``). See the module docstring for
    the type-preservation rule.
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: asin(
                item,
                degrees=degrees,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        return _exact_asin(x)
    if digits is None and not decimal_input:
        return _frac_asin(xf, degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _asin_core(xf, p, degrees), digits, rounding, max_refinements)


def acos(
    x: ScalarLike | VectorLike,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the arc cosine of ``x`` (radians, or degrees if ``degrees``). See the module docstring
    for the type-preservation rule.
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: acos(
                item,
                degrees=degrees,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        return _exact_acos(x)
    if digits is None and not decimal_input:
        return _frac_acos(xf, degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _acos_core(xf, p, degrees), digits, rounding, max_refinements)


def atan(
    x: ScalarLike | VectorLike,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the arc tangent of ``x`` (radians, or degrees if ``degrees``). See the module docstring
    for the type-preservation rule.
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if _is_vector_input(x):
        data, _ = _vector_data(x)
        decimal_mode = digits is not None or _contains_decimal(data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_vector(
            x,
            lambda item: atan(
                item,
                degrees=degrees,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    xf, decimal_input = _coerce(x)
    if exact:
        return _exact_atan(x)
    if digits is None and not decimal_input:
        return _frac_atan(xf, degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _atan_core(xf, p, degrees), digits, rounding, max_refinements)


def atan2(
    y: ScalarLike | VectorLike,
    x: ScalarLike | VectorLike,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
    exact: bool = False,
) -> Any:
    """
    Return the arc tangent of ``y/x`` with :func:`math.atan2` quadrant conventions (radians, or
    degrees if ``degrees``). See the module docstring for the type-preservation rule; a Decimal in
    either argument promotes the result (``atan2(Decimal, Fraction)`` returns a Decimal). Vector
    inputs are mapped elementwise; a scalar argument is broadcast across the vector.
    """
    if exact and not degrees:
        raise ValueError("exact trigonometry requires degrees=True")
    if _is_vector_input(y) or _is_vector_input(x):
        y_data = _vector_data(y)[0] if _is_vector_input(y) else y
        x_data = _vector_data(x)[0] if _is_vector_input(x) else x
        decimal_mode = digits is not None or _contains_decimal(y_data) or _contains_decimal(x_data)
        vector_digits = _effective_digits(digits, decimal_mode, exact)
        if not exact and decimal_mode:
            _validate_decimal_params(digits, rounding, max_refinements)
        return _map_binary_vector(
            y,
            x,
            lambda left, right: atan2(
                left,
                right,
                degrees=degrees,
                prec=prec,
                limit=limit,
                digits=vector_digits,
                rounding=rounding,
                max_refinements=max_refinements,
                exact=exact,
            ),
            decimal_mode=decimal_mode,
            exact=exact,
        )
    yf, y_decimal = _coerce(y)
    xf, x_decimal = _coerce(x)
    if exact:
        return _exact_atan2(y, x)
    if digits is None and not (y_decimal or x_decimal):
        return _frac_atan2(yf, xf, degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(lambda p: _atan2_core(yf, xf, p, degrees), digits, rounding, max_refinements)


def pi(
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
    max_refinements: int | None = None,
) -> fractions.Fraction | decimal.Decimal:
    """
    Return pi.

    With no ``digits=`` the Fraction contract holds (a rational within ``prec``, ``limit``
    controlling the denominator); ``pi(digits=n)`` returns the correctly-rounded Decimal to ``n``
    significant digits under ``rounding``.
    """
    if digits is None:
        return _frac_pi(prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding, max_refinements)
    return _to_decimal(
        lambda p: (_frac_pi(prec=p, limit=False), False),
        digits,
        rounding,
        max_refinements,
    )
