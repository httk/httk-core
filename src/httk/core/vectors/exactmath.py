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

Two output domains are supported, selected by a single documented rule:

    The result is a :class:`decimal.Decimal` iff any numeric input is a Decimal OR ``digits=``
    is passed; Fraction/int/str inputs otherwise get today's exact Fraction behavior with
    ``prec``/``limit`` semantics.

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
from functools import reduce
from typing import Any

default_accuracy = fractions.Fraction(1, 10000000000)


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

    if arg.find('/') >= 0:
        return fractions.Fraction(arg), fractions.Fraction(0)

    sd_start = arg.find('(')
    if sd_start >= 0:
        infered_delta = False
        sd_end = arg.find(')')
        val = arg[:sd_start]
        m, _e, _exp = val.partition('E')
        sd = arg[sd_start + 1 : sd_end]
    elif min_accuracy is not None:
        infered_delta = True
        val = arg
        m, _e, _exp = val.partition('E')
        if arg.find('.') >= 0:
            m = m + "0"
        else:
            m = m + ".0"
        sd = "5"
    else:
        return fractions.Fraction(arg), fractions.Fraction(0)
    numdigits = reduce(lambda y, x: y + 1 if x.isdigit() else y, m, 0)
    replacelist = list('0' * (numdigits - len(sd)) + sd)
    delta = fractions.Fraction(''.join(replacelist.pop(0) if c.isdigit() else c for c in m))
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
    x: fractions.Fraction, prec: fractions.Fraction = default_accuracy, limit: bool = True
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
    x: fractions.Fraction, prec: fractions.Fraction = default_accuracy, limit: bool = True, degrees: bool = False
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
    x: fractions.Fraction, prec: fractions.Fraction = default_accuracy, limit: bool = True, degrees: bool = False
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
    x: fractions.Fraction, prec: fractions.Fraction = default_accuracy, limit: bool = True
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
    x: fractions.Fraction, degrees: bool = False, prec: fractions.Fraction = default_accuracy, limit: bool = True
) -> fractions.Fraction:
    """
    Return a rational approximation of the tangent of ``x`` to precision ``prec``.
    """
    s = _frac_sin(x, prec=prec, limit=False) / _frac_cos(x, prec=prec, limit=False)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def _frac_asin(
    x: fractions.Fraction, degrees: bool = False, prec: fractions.Fraction = default_accuracy, limit: bool = True
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
    x: fractions.Fraction, degrees: bool = False, prec: fractions.Fraction = default_accuracy, limit: bool = True
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
    x: fractions.Fraction, degrees: bool = False, prec: fractions.Fraction = default_accuracy, limit: bool = True
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


def _validate_decimal_params(digits: int | None, rounding: str) -> None:
    """Validate Decimal-mode ``digits`` and ``rounding`` eagerly, raising :class:`ValueError`."""
    if digits is not None and (not isinstance(digits, int) or isinstance(digits, bool) or digits <= 0):
        raise ValueError(f"invalid digits {digits!r}; expected a positive integer or None")
    if rounding not in _VALID_ROUNDINGS:
        raise ValueError(f"unknown rounding {rounding!r}; expected one of {list(_VALID_ROUNDINGS)}")


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
    """
    sig = decimal.getcontext().prec if digits is None else digits
    prec = fractions.Fraction(1, 10 ** (sig + _ZIV_GUARD_DIGITS))
    for _ in range(_ZIV_CAP):
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
    x: fractions.Fraction, base: fractions.Fraction | int | None, prec: fractions.Fraction
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
    y: fractions.Fraction, x: fractions.Fraction, prec: fractions.Fraction, degrees: bool
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


def _is_decimal(*args: Any) -> bool:
    return any(isinstance(a, decimal.Decimal) for a in args)


def sqrt(
    x: Any,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the square root of ``x``.

    Fraction domain (Fraction/int/str input, no ``digits=``): a rational approximation within
    ``prec`` (exact for perfect squares), ``limit`` controlling the denominator. Decimal domain
    (Decimal input or ``digits=`` given): the correctly-rounded Decimal to ``digits`` significant
    digits under ``rounding``.
    """
    if digits is None and not _is_decimal(x):
        return _frac_sqrt(fractions.Fraction(x), prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _sqrt_core(xf, p), digits, rounding)


def cos(
    x: Any,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    degrees: bool = False,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the cosine of ``x`` (radians unless ``degrees`` is True). See the module docstring for
    the type-preservation rule; Decimal mode renders the special-angle exact values exactly (e.g.
    ``cos(Decimal("60"), degrees=True) == Decimal("0.5")``).
    """
    if digits is None and not _is_decimal(x):
        return _frac_cos(fractions.Fraction(x), prec=prec, limit=limit, degrees=degrees)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _cos_core(xf, p, degrees), digits, rounding)


def sin(
    x: Any,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    degrees: bool = False,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the sine of ``x`` (radians unless ``degrees`` is True). See the module docstring for the
    type-preservation rule.
    """
    if digits is None and not _is_decimal(x):
        return _frac_sin(fractions.Fraction(x), prec=prec, limit=limit, degrees=degrees)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _sin_core(xf, p, degrees), digits, rounding)


def tan(
    x: Any,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the tangent of ``x``. See the module docstring for the type-preservation rule.
    """
    if digits is None and not _is_decimal(x):
        return _frac_tan(fractions.Fraction(x), degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _tan_core(xf, p, degrees), digits, rounding)


def exp(
    x: Any,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return ``e`` raised to the power ``x``. See the module docstring for the type-preservation rule.
    """
    if digits is None and not _is_decimal(x):
        return _frac_exp(fractions.Fraction(x), prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _exp_core(xf, p), digits, rounding)


def log(
    x: Any,
    base: Any = None,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the logarithm of ``x`` to ``base`` (natural log when ``base`` is None). See the module
    docstring for the type-preservation rule; a Decimal ``base`` also promotes the result.
    """
    if digits is None and not _is_decimal(x, base):
        return _frac_log(fractions.Fraction(x), base=base, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    basef: fractions.Fraction | int | None = None if base is None else fractions.Fraction(base)
    return _to_decimal(lambda p: _log_core(xf, basef, p), digits, rounding)


def log10(
    x: Any,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the base-10 logarithm of ``x``. See the module docstring for the type-preservation rule.
    """
    return log(x, base=10, prec=prec, limit=limit, digits=digits, rounding=rounding)


def asin(
    x: Any,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | int | decimal.Decimal:
    """
    Return the arc sine of ``x`` (radians, or degrees if ``degrees``). See the module docstring for
    the type-preservation rule.
    """
    if digits is None and not _is_decimal(x):
        return _frac_asin(fractions.Fraction(x), degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _asin_core(xf, p, degrees), digits, rounding)


def acos(
    x: Any,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the arc cosine of ``x`` (radians, or degrees if ``degrees``). See the module docstring
    for the type-preservation rule.
    """
    if digits is None and not _is_decimal(x):
        return _frac_acos(fractions.Fraction(x), degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _acos_core(xf, p, degrees), digits, rounding)


def atan(
    x: Any,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the arc tangent of ``x`` (radians, or degrees if ``degrees``). See the module docstring
    for the type-preservation rule.
    """
    if digits is None and not _is_decimal(x):
        return _frac_atan(fractions.Fraction(x), degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _atan_core(xf, p, degrees), digits, rounding)


def atan2(
    y: Any,
    x: Any,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return the arc tangent of ``y/x`` with :func:`math.atan2` quadrant conventions (radians, or
    degrees if ``degrees``). See the module docstring for the type-preservation rule; a Decimal in
    either argument promotes the result (``atan2(Decimal, Fraction)`` returns a Decimal).
    """
    if digits is None and not _is_decimal(y, x):
        return _frac_atan2(fractions.Fraction(y), fractions.Fraction(x), degrees=degrees, prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    yf = fractions.Fraction(y)
    xf = fractions.Fraction(x)
    return _to_decimal(lambda p: _atan2_core(yf, xf, p, degrees), digits, rounding)


def pi(
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
    digits: int | None = None,
    rounding: str = "half_even",
) -> fractions.Fraction | decimal.Decimal:
    """
    Return pi.

    With no ``digits=`` the Fraction contract holds (a rational within ``prec``, ``limit``
    controlling the denominator); ``pi(digits=n)`` returns the correctly-rounded Decimal to ``n``
    significant digits under ``rounding``.
    """
    if digits is None:
        return _frac_pi(prec=prec, limit=limit)
    _validate_decimal_params(digits, rounding)
    return _to_decimal(lambda p: (_frac_pi(prec=p, limit=False), False), digits, rounding)
