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

import functools
import math

from httk.core import exactmath

# Trial division covers primes below this bound; the cofactor is handled by Miller-Rabin and
# Pollard-Brent rho.
_TRIAL_BOUND = 100_000
# Pollard-Brent iterations one call may spend on a cofactor of at most 128 bits; larger cofactors
# get proportionally less (each iteration costs more), so any input gives up within seconds.
_RHO_BUDGET = 1 << 22
# ponytail: cofactors above this many bits are refused outright (one Miller-Rabin round costs
# ~0.03 s at 2048 bits and grows cubically); raise it if exact surds of huge radicands matter.
_MAX_FACTOR_BITS = 2048
# Miller-Rabin bases: the first 13 primes are a deterministic test below 3.3e24; the remainder
# extend confidence beyond it.
_MR_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97)


@functools.cache
def _small_primes() -> tuple[int, ...]:
    sieve = bytearray([1]) * _TRIAL_BOUND
    sieve[0:2] = b"\x00\x00"
    for i in range(2, math.isqrt(_TRIAL_BOUND - 1) + 1):
        if sieve[i]:
            sieve[i * i :: i] = bytes(len(range(i * i, _TRIAL_BOUND, i)))
    return tuple(i for i, flag in enumerate(sieve) if flag)


def _is_probable_prime(n: int) -> bool:
    # ponytail: fixed-base Miller-Rabin is deterministic only below 3.3e24; beyond it a composite
    # that is a strong pseudoprime to all 25 bases would be taken as prime (none arises naturally;
    # switch to Baillie-PSW if adversarial radicands matter).
    if n < 2:
        return False
    for p in _MR_BASES:
        if n % p == 0:
            return n == p
    d = n - 1
    shift = (d & -d).bit_length() - 1
    d >>= shift
    for a in _MR_BASES:
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(shift - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _spend(budget: list[int], steps: int, n: int) -> None:
    """Debit ``steps`` iterations from ``budget`` before they run, or raise when it cannot pay."""
    if budget[0] < steps:
        raise ValueError(
            f"square_part: cannot factor a {n.bit_length()}-bit radicand exactly within the "
            "factoring budget; use an approximate value (e.g. exact=False or to_floats())"
        )
    budget[0] -= steps


def _brent(n: int, budget: list[int]) -> int:
    """Return a nontrivial factor of the odd composite ``n`` (Pollard-Brent rho)."""
    for c in range(1, 1 << 30):
        y, r, q, g = 2, 1, 1, 1
        x = ys = y
        while g == 1:
            x = y
            _spend(budget, r, n)
            for _ in range(r):
                y = (y * y + c) % n
            k = 0
            while k < r and g == 1:
                ys = y
                steps = min(128, r - k)
                _spend(budget, steps, n)
                for _ in range(steps):
                    y = (y * y + c) % n
                    q = q * abs(x - y) % n
                g = math.gcd(q, n)
                k += steps
            r *= 2
        if g == n:
            g = 1
            while g == 1:
                _spend(budget, 1, n)
                ys = (ys * ys + c) % n
                g = math.gcd(abs(x - ys), n)
        if g != n:
            return g
    raise AssertionError("unreachable")


def _budget_for(n: int) -> list[int]:
    """Return a fresh, size-scaled iteration budget for factoring ``n``."""
    if n.bit_length() > _MAX_FACTOR_BITS:
        raise ValueError(
            f"square_part: cannot factor a {n.bit_length()}-bit radicand exactly (above "
            f"{_MAX_FACTOR_BITS} bits); use an approximate value (e.g. exact=False or to_floats())"
        )
    return [max(1024, _RHO_BUDGET // max(1, (n.bit_length() // 64) ** 2))]


def prime_factor(n: int) -> int:
    """
    Return a prime factor of ``n >= 2``: the smallest one when it lies below the trial bound.

    :param n: An integer ``>= 2``.
    :return: A prime dividing ``n``.
    :raises ValueError: If ``n < 2``, or if ``n`` cannot be factored within the budget.
    """
    if n < 2:
        raise ValueError(f"prime_factor: expected an integer >= 2, got {n!r}")
    for p in _small_primes():
        if p * p > n:
            return n
        if n % p == 0:
            return p
    budget = _budget_for(n)
    while not _is_probable_prime(n):
        root = math.isqrt(n)
        n = root if root * root == n else _brent(n, budget)
    return n


def _prime_factors(n: int, out: dict[int, int], budget: list[int]) -> None:
    """Add the prime factorization of ``n`` (no prime factors below the trial bound) to ``out``."""
    if n == 1:
        return
    root = math.isqrt(n)
    if root * root == n:
        inner: dict[int, int] = {}
        _prime_factors(root, inner, budget)
        for p, e in inner.items():
            out[p] = out.get(p, 0) + 2 * e
        return
    if _is_probable_prime(n):
        out[n] = out.get(n, 0) + 1
        return
    d = _brent(n, budget)
    _prime_factors(d, out, budget)
    _prime_factors(n // d, out, budget)


def square_part(n: int) -> tuple[int, int]:
    """
    Factor ``n = s**2 * r`` with ``r`` squarefree, returning ``(s, r)`` for ``n >= 1``.

    This is exactly what is needed to canonicalize a radical: ``sqrt(n) == s * sqrt(r)`` with the
    smallest possible ``r`` (squarefree).

    Factors of 2 are removed by bit counting and every other prime below 100000 by trial division
    (dividing out its powers by repeated squaring). The remaining cofactor is factored exactly
    with Miller-Rabin primality tests and Pollard-Brent rho, so decimal-derived radicands (whose
    denominators are powers of 2 and 5) stay fast. The computation is exact integer arithmetic.

    :param n: A positive value (``n >= 1``).
    :return: The pair ``(s, r)`` with ``n == s * s * r`` and ``r`` squarefree.
    :raises ValueError: If ``n < 1``, or if the cofactor cannot be factored within the budget.
    """
    if n < 1:
        raise ValueError(f"square_part: expected a positive integer, got {n!r}")
    twos = (n & -n).bit_length() - 1
    m = n >> twos
    s = 1 << (twos // 2)
    r = 2 if twos % 2 else 1
    for p in _small_primes()[1:]:
        if p * p > m:
            break
        if m % p == 0:
            m, e = exactmath._remove_factor(m, p)
            s *= p ** (e // 2)
            if e % 2:
                r *= p
    if m > 1:
        if m < _TRIAL_BOUND * _TRIAL_BOUND:
            r *= m  # no factor below its square root: m is prime
        else:
            factors: dict[int, int] = {}
            _prime_factors(m, factors, _budget_for(m))
            for p, e in factors.items():
                s *= p ** (e // 2)
                if e % 2:
                    r *= p
    return s, r
