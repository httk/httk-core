#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
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
Private helper: extract the square part of a positive integer.

This backs the canonicalization of radicands in
:mod:`httk.core.vectors.surdvector` — it rewrites ``sqrt(n)`` as ``s * sqrt(r)`` with ``r``
squarefree.
"""

from httk.core import exactmath


def square_part(n: int) -> tuple[int, int]:
    """
    Factor ``n = s**2 * r`` with ``r`` squarefree, returning ``(s, r)`` for ``n >= 1``.

    This is exactly what is needed to canonicalize a radical: ``sqrt(n) == s * sqrt(r)`` with the
    smallest possible ``r`` (squarefree).

    Cost: trial division by every integer up to the cube root of ``n`` (dividing out squares of
    prime factors as they are found), followed by a single perfect-square test on the cofactor.
    After all prime factors ``p <= n**(1/3)`` are removed, the remaining cofactor ``m`` has every
    prime factor greater than its own cube root, so it is one of ``1``, ``p``, ``p**2`` or
    ``p*q`` (distinct primes); only the ``p**2`` case is non-squarefree, and it is detected by an
    exact integer square-root test (:func:`~httk.core.exactmath.integer_sqrt`). The whole
    computation is exact integer arithmetic; at the tiny magnitudes that arise in crystallographic
    geometry (products of small squarefree radicands) it is trivial.

    Args:
        n: a positive integer (``n >= 1``).

    Returns:
        The pair ``(s, r)`` with ``n == s * s * r`` and ``r`` squarefree.
    """
    if n < 1:
        raise ValueError(f"square_part: expected a positive integer, got {n!r}")
    s = 1
    r = 1
    m = n
    d = 2
    while d * d * d <= m:
        if m % d == 0:
            e = 0
            while m % d == 0:
                m //= d
                e += 1
            s *= d ** (e // 2)
            if e % 2 == 1:
                r *= d
        d += 1
    # Every prime factor of the remaining cofactor m now exceeds m**(1/3), so m is 1, p, p**2 or
    # p*q. Only p**2 is non-squarefree, detected as a perfect square.
    if m > 1:
        root = exactmath.integer_sqrt(m)
        if root * root == m:
            s *= root
        else:
            r *= m
    return s, r
