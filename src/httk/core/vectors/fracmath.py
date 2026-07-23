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
Exact-rational math on Python :class:`fractions.Fraction` values.

This module provides the transcendental and helper functions used by
:class:`~httk.core.vectors.fracvector.FracVector`. Every function computes a rational
(``Fraction``) approximation to a target precision, so results are exact rationals that
approximate the true (generally irrational) value to within ``prec``.

Note: a possible future performance follow-up is to soft-import the third-party
``cfractions`` accelerator in place of the standard-library :mod:`fractions`; the
legacy code did so, but on Python 3.12 the standard library is used unconditionally.
"""

import fractions
from collections.abc import Iterator
from functools import reduce
from typing import Any, cast

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


def frac_sqrt(
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
def frac_cos(
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
        x *= frac_pi(prec=prec, limit=True) / 180
    if abs(x) > 4:
        twopi = 2 * frac_pi(prec=prec, limit=True)
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


def frac_sin(
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
        x *= frac_pi(prec=prec) / 180
    if abs(x) > 4:
        twopi = 2 * frac_pi(prec=prec)
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


def frac_exp(
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


def frac_pi(prec: fractions.Fraction = default_accuracy, limit: bool = True) -> fractions.Fraction:
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


def frac_log(
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
    if x < 0:
        raise ValueError("frac_log: logarithm of negative number.")
    elif base == 1:
        raise ValueError("frac_log: logarithm of base 1 not valid.")
    elif x == base:
        return fractions.Fraction(1)
    elif x == 0:
        raise ValueError("frac_log: logarithm of zero.")

    if base is None:
        log_base: fractions.Fraction | int = 1
    else:
        # base may be an int here (e.g. from frac_log10); the recursion mirrors the legacy code.
        log_base = frac_log(cast(fractions.Fraction, base), prec=prec, limit=limit)

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


def frac_log10(
    x: fractions.Fraction, prec: fractions.Fraction = default_accuracy, limit: bool = True
) -> fractions.Fraction:
    """
    Return a rational approximation of the base-10 logarithm of ``x`` to precision ``prec``.
    """
    return frac_log(x, base=10, prec=prec, limit=limit)


def frac_tan(
    x: fractions.Fraction, degrees: bool = False, prec: fractions.Fraction = default_accuracy, limit: bool = True
) -> fractions.Fraction:
    """
    Return a rational approximation of the tangent of ``x`` to precision ``prec``.
    """
    s = frac_sin(x, prec=prec, limit=False) / frac_cos(x, prec=prec, limit=False)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def frac_asin(
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
            return frac_pi(prec=prec, limit=limit) / -2
        elif x == 0:
            return fractions.Fraction(0)
        elif x == 1:
            return frac_pi(prec=prec, limit=limit) / 2

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
        s = s * 180 / frac_pi(prec=prec, limit=limit)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def frac_acos(
    x: fractions.Fraction, degrees: bool = False, prec: fractions.Fraction = default_accuracy, limit: bool = True
) -> fractions.Fraction:
    """
    Return a rational approximation of the arc cosine (in radians, or degrees if
    ``degrees`` is True) of ``x`` to precision ``prec``.
    """
    if abs(x) > 1:
        raise ValueError("Domain error: acos accepts -1 <= x <= 1")
    PI = frac_pi(prec=prec, limit=False)

    if x == 1:
        return fractions.Fraction(0)
    else:
        if x == -1:
            return PI
        elif x == 0:
            return PI / 2

    s = PI / 2 - frac_atan2(x, frac_sqrt(1 - x**2, prec=prec, limit=limit), prec=prec, limit=limit)

    if degrees:
        s = s * 180 / PI
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def frac_atan(
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
        PI = frac_pi(prec=prec, limit=False)
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
        s = s * 180 / frac_pi(prec=prec, limit=limit)
    if limit:
        s = s.limit_denominator(int(1 / prec))
    return s


def frac_atan2(
    y: fractions.Fraction,
    x: fractions.Fraction,
    degrees: bool = False,
    prec: fractions.Fraction = default_accuracy,
    limit: bool = True,
) -> fractions.Fraction:
    """
    Return a rational approximation of the arc tangent of ``y/x`` in radians.

    Unlike ``atan(y/x)``, the signs of both ``x`` and ``y`` are considered.
    """
    if x != 0:
        a = y and frac_atan(y / x, prec=prec, limit=limit) or fractions.Fraction(0)
        if x < 0:
            if y > 0:
                a += frac_pi(prec=prec, limit=limit)
            else:
                a -= frac_pi(prec=prec, limit=limit)
        return a

    if y != 0:
        return frac_atan(fractions.Fraction(0), prec=prec, limit=limit)
    elif x < 0:
        return frac_pi(prec=prec, limit=limit)
    else:
        return fractions.Fraction(0)
