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
Exact square-root arithmetic: :class:`SurdVector` and :class:`SurdScalar`.

Where :class:`~httk.core.vectors.fracvector.FracVector` closes the rationals under ``+,-,*,/``,
:class:`SurdVector` closes the rationals *and the square roots of arbitrary positive rationals*
under those same operations. It is the exact-arithmetic model for **Cartesian** crystallographic
geometry, where :class:`~httk.core.vectors.fracvector.FracVector` alone is not enough.

Why a square-root extension, and where
--------------------------------------

Symmetry operations and Wyckoff coordinates live in **fractional** coordinates and are already
exactly closed over :class:`~httk.core.vectors.fracvector.FracVector`: point-group operations are integer matrices and
translations are rationals, so no radicals ever appear. Radicals appear only when one moves to a
**Cartesian** frame: the hexagonal/trigonal basis carries a :math:`\\sqrt 3`, Cartesian rotation
matrices carry :math:`\\sqrt 2`/:math:`\\sqrt 3`, and a bond length is :math:`\\sqrt{\\text{rational}}`
under a rational metric. :class:`SurdVector` is exactly the arithmetic closure needed there.

The purpose boundary (magnitudes vs. linear structure)
------------------------------------------------------

For pure **magnitude** questions — comparing, sorting or testing equality of distances — the
*squared* representation is exact, cheaper, and already fully supported by :class:`~httk.core.vectors.fracvector.FracVector`: a
squared length ``lengthsqr`` is rational and a metric/Gram matrix ``G = B*B^T`` is rational, so
"is bond A shorter than bond B?" is an exact rational comparison of ``lengthsqr`` values. That
remains the recommended fast path.

Squaring fails, however, as soon as radicals sit inside **additive / linear** structure, and that
is exactly where :class:`SurdVector` earns its keep:

- components are signed and additive, and :math:`(a+b)^2 \\neq a^2 + b^2` — the cross term is
  itself a radical;
- a metric determines a basis only up to an orthogonal transformation, so squaring throws away
  orientation and chirality;
- even scalar sums are not closed under squaring: :math:`(\\sqrt2+\\sqrt3)^2 = 5 + 2\\sqrt6`.

So :class:`SurdVector` composes *with* the squared strategy rather than replacing it: its canonical
form collapses to the plain rational whenever a value happens to be rational, so a computation that
lands back in the rationals is transparently rational again.

The mathematical model
----------------------

The values form the **field** :math:`\\mathbb{Q}[\\sqrt n : n \\text{ squarefree}]` — finite sums
:math:`\\sum_r q_r\\sqrt r` with rational coefficients :math:`q_r`, the rationals being the radicand
:math:`r = 1` term. The canonical form is the map ``{squarefree radicand -> rational coefficient}``
with no zero entries; it is **unique** because the :math:`\\sqrt r` (over squarefree :math:`r`) are
linearly independent over :math:`\\mathbb{Q}`. Consequences used throughout:

- **Equality and zero-detection are exact**: equal values have equal coefficient maps.
- **Products combine radicands**: :math:`\\sqrt r\\,\\sqrt s = c\\,\\sqrt t` where
  :math:`r s = c^2 t` with :math:`t` squarefree (see ``square_part``).
- **Division is a true field inverse** via iterated per-prime conjugation: for each prime :math:`p`
  dividing a radicand of the denominator, multiply numerator and denominator by the conjugate that
  flips the sign of every :math:`\\sqrt r` with :math:`p \\mid r`; each such step eliminates :math:`p`.
  The coefficient count can grow like :math:`2^k` in the number :math:`k` of distinct primes among
  the denominator's radicands — tiny in practice (crystallographic denominators involve one or two
  radicands).
- **Sign is exactly decidable**: refine rational lower/upper bounds on each :math:`\\sqrt r` (via
  :func:`~httk.core.vectors.exactmath.integer_sqrt` at increasing precision) until the summed
  interval excludes zero. This terminates because a nonzero surd is never zero.
- **Square roots are closed over positive rationals but NOT over surds** (no nested radicals):
  :meth:`~httk.core.vectors.surdvector.SurdVector.sqrt_of` takes any nonnegative rational to an exact surd, but there is no exact
  :math:`\\sqrt{1+\\sqrt2}`. Hence :meth:`~httk.core.vectors.surdvector.SurdVector.length` is exact precisely when ``lengthsqr`` is
  rational — which canonical arithmetic guarantees whenever the geometry is metric-rational (the
  crystallographic case); otherwise it raises.
"""

import fractions
from typing import Any

from httk.core.vectors._squarefree import square_part
from httk.core.vectors.exactmath import (
    _to_decimal,
    _validate_decimal_params,
    any_to_fraction,
    integer_sqrt,
)
from httk.core.vectors.fracvector import FracVector


def _fracvector_is_zero(fv: FracVector) -> bool:
    """Return True iff every element of ``fv`` is zero."""

    def rec(node: Any) -> bool:
        if isinstance(node, (tuple, list)):
            return all(rec(e) for e in node)
        return node == 0

    return rec(fv.noms)


def _zero_fracvector(dim: tuple[int, ...]) -> FracVector:
    """A zero FracVector of the given shape (``dim == ()`` yields a scalar zero)."""
    if dim == ():
        return FracVector(0, 1)
    return FracVector.zeros(dim)


def _max_abs_leaf(fv: FracVector) -> fractions.Fraction:
    """Return the largest absolute leaf value of ``fv`` as a Fraction (0 for an all-zero tensor)."""
    biggest = fv._reduce_over_noms(lambda acc, x: max(acc, abs(x)), initializer=0)
    return fractions.Fraction(biggest, fv.denom)


def _smallest_prime_factor(n: int) -> int:
    """Return the smallest prime factor of ``n >= 2`` (trivial trial division; radicands are tiny)."""
    d = 2
    while d * d <= n:
        if n % d == 0:
            return d
        d += 1
    return n


def _scalar_to_fraction(value: Any) -> fractions.Fraction:
    """Coerce an int/Fraction/scalar-FracVector/rational-SurdScalar/str into an exact Fraction."""
    if isinstance(value, fractions.Fraction):
        return value
    if isinstance(value, bool):  # avoid bool-as-int surprises
        raise TypeError("SurdVector: bool is not a valid scalar")
    if isinstance(value, int):
        return fractions.Fraction(value)
    if isinstance(value, SurdVector):
        if value._dim != () or not value.is_rational:
            raise ValueError("SurdVector: expected a rational scalar")
        return value._rational_fraction()
    if isinstance(value, FracVector):
        return value.to_fraction()
    return fractions.Fraction(value)


def _add_component(components: dict[int, FracVector], radicand: int, fv: FracVector) -> None:
    """Accumulate ``fv`` into ``components[radicand]`` (FracVector addition)."""
    if radicand in components:
        components[radicand] = components[radicand] + fv
    else:
        components[radicand] = fv


class SurdVector:
    """
    An *immutable* exact tensor over the squarefree-radical field
    :math:`\\mathbb{Q}[\\sqrt n : n\\ \\text{squarefree}]`.

    A SurdVector is a map ``{squarefree radicand -> FracVector coefficient}`` (all coefficients
    sharing one ``dim``); radicand ``1`` is the rational part. It is stored **canonically** —
    coefficients simplified, all-zero coefficients dropped — so the representation is unique and
    equality/zero-detection are exact. Like :class:`~httk.core.vectors.fracvector.FracVector` it is
    immutable and hashable.

    See the module docstring for the field facts, the fractional-vs-Cartesian motivation, and the
    magnitude-vs-linear-structure purpose boundary.
    """

    _components: dict[int, FracVector]
    _dim: tuple[int, ...]

    #### Construction

    def __init__(self, components: dict[int, FracVector], dim: tuple[int, ...]) -> None:
        """
        Low-level constructor: store ``components`` (canonicalized) over shape ``dim``.

        Prefer :meth:`~httk.core.vectors.surdvector.SurdVector.create`, :meth:`~httk.core.vectors.surdvector.SurdVector.sqrt_of` or :meth:`~httk.core.vectors.surdvector.SurdVector.from_radicand_map`; this assumes the
        coefficients are already FracVectors sharing ``dim``.
        """
        canon: dict[int, FracVector] = {}
        for radicand, comp in components.items():
            simplified = comp.simplify()
            if not _fracvector_is_zero(simplified):
                canon[radicand] = simplified
        self._components = canon
        self._dim = dim

    @staticmethod
    def _make(components: dict[int, FracVector], dim: tuple[int, ...]) -> "SurdVector":
        """Build a canonical SurdVector, returning a :class:`SurdScalar` when ``dim == ()``."""
        target = SurdScalar if dim == () else SurdVector
        return target(components, dim)

    @classmethod
    def create(cls, obj: Any) -> "SurdVector":
        """
        Create a SurdVector from a :class:`~httk.core.vectors.fracvector.FracVector`, nested rationals, or another SurdVector.

        A SurdVector is returned unchanged; anything else is built through
        :meth:`~httk.core.vectors.fracvector.FracVector.create` and embedded exactly at radicand 1 (so every rational value is
        representable, and a rational input stays rational).
        """
        if isinstance(obj, SurdVector):
            return obj
        fv = FracVector.create(obj)
        return cls._make({1: fv}, fv.dim)

    @classmethod
    def from_radicand_map(cls, mapping: dict[int, Any]) -> "SurdVector":
        """
        Compose a SurdVector from a ``{radicand -> coefficient}`` mapping.

        Radicands are positive integers and need not be squarefree — each is normalized via
        ``square_part`` (``sqrt(radicand) = s*sqrt(r)``) and the
        coefficients (FracVector-like, all of one shape) folded together canonically.
        """
        components: dict[int, FracVector] = {}
        dim: tuple[int, ...] | None = None
        for radicand, coeff in mapping.items():
            if radicand < 1:
                raise ValueError(f"SurdVector.from_radicand_map: radicands must be >= 1, got {radicand!r}")
            fv = coeff if isinstance(coeff, FracVector) else FracVector.create(coeff)
            if dim is None:
                dim = fv.dim
            elif fv.dim != dim:
                raise ValueError("SurdVector.from_radicand_map: all coefficients must share one shape")
            s, r = square_part(radicand)
            _add_component(components, r, fv * s)
        if dim is None:
            dim = ()
        return cls._make(components, dim)

    @classmethod
    def sqrt_of(cls, q: Any) -> "SurdScalar":
        """
        Return the exact square root of a nonnegative rational ``q`` as a :class:`SurdScalar`.

        The result is a plain rational when ``q`` is a perfect square (e.g. ``sqrt_of(4/9) == 2/3``)
        and otherwise a single-radical surd (``sqrt_of(8) == 2*sqrt(2)``). ``sqrt(p/q)`` is
        normalized as ``sqrt(p*q)/q`` so the stored radicand is always a positive squarefree integer
        (``sqrt_of(1/2) == sqrt(2)/2``). Raises :class:`ValueError` on a negative argument — there is
        no exact square root of a surd (no nested radicals), only of a rational.
        """
        qf = _scalar_to_fraction(q)
        if qf < 0:
            raise ValueError(f"SurdVector.sqrt_of: cannot take the square root of the negative rational {qf}")
        if qf == 0:
            return SurdScalar({}, ())
        n = qf.numerator * qf.denominator
        s, r = square_part(n)
        coeff = fractions.Fraction(s, qf.denominator)
        return SurdScalar({r: FracVector(coeff.numerator, coeff.denominator)}, ())

    @classmethod
    def zero(cls, dim: tuple[int, ...] = ()) -> "SurdVector":
        """The zero SurdVector of shape ``dim`` (a :class:`SurdScalar` for the default ``()``)."""
        return cls._make({}, dim)

    @classmethod
    def one(cls) -> "SurdScalar":
        """The scalar ``1``."""
        return SurdScalar({1: FracVector(1, 1)}, ())

    #### Properties / predicates

    @property
    def dim(self) -> tuple[int, ...]:
        """The shape tuple, as for :attr:`~httk.core.vectors.fracvector.FracVector.dim`."""
        return self._dim

    @property
    def is_rational(self) -> bool:
        """True iff the value is purely rational (only the radicand-1 term is present)."""
        return all(radicand == 1 for radicand in self._components)

    def is_zero(self) -> bool:
        """True iff the value is exactly zero (empty canonical form)."""
        return len(self._components) == 0

    @property
    def radicands(self) -> tuple[int, ...]:
        """The sorted squarefree radicands present in the canonical form."""
        return tuple(sorted(self._components))

    def coefficient(self, radicand: int) -> FracVector:
        """The FracVector coefficient of ``sqrt(radicand)`` (a zero tensor when absent)."""
        return self._components.get(radicand, _zero_fracvector(self._dim))

    def _rational_fraction(self) -> fractions.Fraction:
        """The rational value as a Fraction (scalar; assumes :attr:`~httk.core.vectors.surdvector.SurdVector.is_rational`)."""
        comp = self._components.get(1)
        if comp is None:
            return fractions.Fraction(0)
        return comp.to_fraction()

    #### Coercion

    @staticmethod
    def _coerce(other: Any) -> "SurdVector | None":
        if isinstance(other, SurdVector):
            return other
        if isinstance(other, bool):
            return None
        if isinstance(other, (int, fractions.Fraction, FracVector)):
            return SurdVector.create(FracVector.create(other))
        return None

    #### Ring operations

    def __add__(self, other: Any) -> "SurdVector":
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        if self._dim != coerced._dim:
            raise ValueError(f"SurdVector: shape mismatch {self._dim} vs {coerced._dim} in addition")
        result: dict[int, FracVector] = dict(self._components)
        for radicand, comp in coerced._components.items():
            _add_component(result, radicand, comp)
        return self._make(result, self._dim)

    def __radd__(self, other: Any) -> "SurdVector":
        return self.__add__(other)

    def __neg__(self) -> "SurdVector":
        return self._make({radicand: -comp for radicand, comp in self._components.items()}, self._dim)

    def __sub__(self, other: Any) -> "SurdVector":
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        return self.__add__(-coerced)

    def __rsub__(self, other: Any) -> "SurdVector":
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        return coerced.__add__(-self)

    def _mul_surd(self, other: "SurdVector") -> "SurdVector":
        """Multiply two SurdVectors with FracVector matrix-multiplication semantics per radicand."""
        result: dict[int, FracVector] = {}
        for r, a in self._components.items():
            for s, b in other._components.items():
                c, t = square_part(r * s)  # sqrt(r)*sqrt(s) = c*sqrt(t)
                _add_component(result, t, a.mul(b) * c)
        result_dim = _zero_fracvector(self._dim).mul(_zero_fracvector(other._dim)).dim
        return self._make(result, result_dim)

    def __mul__(self, other: Any) -> "SurdVector":
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        return self._mul_surd(coerced)

    def __rmul__(self, other: Any) -> "SurdVector":
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        return coerced._mul_surd(self)

    def __truediv__(self, other: Any) -> "SurdVector":
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        if coerced._dim != ():
            raise ValueError("SurdVector: division is only defined by a scalar divisor")
        return self._mul_surd(coerced._as_scalar()._inverse())

    #### Linear algebra

    def _element(self, index: tuple[int, ...]) -> "SurdScalar":
        """Return element ``index`` as a :class:`SurdScalar` (per-radicand FracVector indexing)."""
        if self._dim == ():
            return SurdScalar(dict(self._components), ())
        comps: dict[int, FracVector] = {radicand: comp[index] for radicand, comp in self._components.items()}
        return SurdScalar(comps, ())

    @staticmethod
    def _from_scalar_grid(grid: Any, dim: tuple[int, ...]) -> "SurdVector":
        """Assemble a SurdVector from a nested list of :class:`SurdScalar` elements."""
        radicands: set[int] = set()

        def collect(node: Any) -> None:
            if isinstance(node, list):
                for e in node:
                    collect(e)
            else:
                radicands.update(node._components)

        collect(grid)
        components: dict[int, FracVector] = {}
        for radicand in radicands:

            def build(node: Any, radicand: int = radicand) -> Any:
                if isinstance(node, list):
                    return [build(e) for e in node]
                comp = node._components.get(radicand)
                return comp.to_fraction() if comp is not None else fractions.Fraction(0)

            components[radicand] = FracVector.create(build(grid))
        return SurdVector._make(components, dim)

    def T(self) -> "SurdVector":
        """Return the transpose, transposing each radicand's coefficient tensor."""
        transposed = {radicand: comp.T() for radicand, comp in self._components.items()}
        dim = _zero_fracvector(self._dim).T().dim
        return self._make(transposed, dim)

    def dot(self, other: Any) -> "SurdScalar":
        """Vector dot product of two 1-D SurdVectors (``sum a_i b_i``)."""
        coerced = self._coerce(other)
        if coerced is None:
            raise TypeError("SurdVector.dot: unsupported operand")
        if len(self._dim) != 1 or self._dim != coerced._dim:
            raise ValueError(f"SurdVector.dot: needs two 1-D vectors of equal length, got {self._dim}, {coerced._dim}")
        total: SurdVector = SurdScalar({}, ())
        for i in range(self._dim[0]):
            total = total + self._element((i,)) * coerced._element((i,))
        return total._as_scalar()

    def lengthsqr(self) -> "SurdScalar":
        """Return the squared length ``A * A^T`` as a :class:`SurdScalar`."""
        if self._dim == ():
            return (self._as_scalar() * self._as_scalar())._as_scalar()
        if len(self._dim) == 1:
            total: SurdVector = SurdScalar({}, ())
            for i in range(self._dim[0]):
                e = self._element((i,))
                total = total + e * e
            return total._as_scalar()
        raise ValueError(f"SurdVector.lengthsqr: needs a scalar or 1-D vector, got shape {self._dim}")

    def length(self) -> "SurdScalar":
        """
        Return the exact length ``sqrt(lengthsqr)`` as a :class:`SurdScalar`.

        Exact precisely when ``lengthsqr`` is rational — which canonical arithmetic guarantees for a
        difference of Cartesian sites under a rational metric (the crystallographic case). When
        ``lengthsqr`` is itself irrational the length would be a nested radical
        (``sqrt(a + b*sqrt(c))``), which is outside the field, so this raises :class:`ValueError`.
        """
        lsq = self.lengthsqr()
        if not lsq.is_rational:
            raise ValueError(
                "SurdVector.length: lengthsqr is irrational, so the length is a nested radical "
                "outside the surd field; use lengthsqr() for an exact squared magnitude"
            )
        return self.sqrt_of(lsq._rational_fraction())

    def det(self) -> "SurdScalar":
        """Return the determinant of a 3x3 SurdVector as a :class:`SurdScalar`."""
        if self._dim != (3, 3):
            raise ValueError(f"SurdVector.det: only 3x3 implemented, got shape {self._dim}")

        def e(i: int, j: int) -> SurdScalar:
            return self._element((i, j))

        return (
            e(0, 0) * e(1, 1) * e(2, 2)
            + e(0, 1) * e(1, 2) * e(2, 0)
            + e(0, 2) * e(1, 0) * e(2, 1)
            - e(0, 2) * e(1, 1) * e(2, 0)
            - e(0, 1) * e(1, 0) * e(2, 2)
            - e(0, 0) * e(1, 2) * e(2, 1)
        )._as_scalar()

    def inv(self) -> "SurdVector":
        """Return the inverse of a 3x3 SurdVector via the adjugate and the scalar field inverse."""
        if self._dim != (3, 3):
            raise ValueError(f"SurdVector.inv: only 3x3 implemented, got shape {self._dim}")

        def e(i: int, j: int) -> SurdScalar:
            return self._element((i, j))

        det = self.det()
        if det.is_zero():
            raise ZeroDivisionError("SurdVector.inv: cannot invert a singular matrix")
        det_inv = det._inverse()
        adjugate = [
            [
                e(1, 1) * e(2, 2) - e(1, 2) * e(2, 1),
                e(0, 2) * e(2, 1) - e(0, 1) * e(2, 2),
                e(0, 1) * e(1, 2) - e(0, 2) * e(1, 1),
            ],
            [
                e(1, 2) * e(2, 0) - e(1, 0) * e(2, 2),
                e(0, 0) * e(2, 2) - e(0, 2) * e(2, 0),
                e(0, 2) * e(1, 0) - e(0, 0) * e(1, 2),
            ],
            [
                e(1, 0) * e(2, 1) - e(1, 1) * e(2, 0),
                e(0, 1) * e(2, 0) - e(0, 0) * e(2, 1),
                e(0, 0) * e(1, 1) - e(0, 1) * e(1, 0),
            ],
        ]
        grid = [[(adjugate[i][j] * det_inv)._as_scalar() for j in range(3)] for i in range(3)]
        return self._from_scalar_grid(grid, (3, 3))

    def _as_scalar(self) -> "SurdScalar":
        """Return this value as a :class:`SurdScalar` (assumes ``dim == ()``)."""
        if isinstance(self, SurdScalar):
            return self
        return SurdScalar(dict(self._components), self._dim)

    #### Rendering

    def _approx_fracvector(self, prec: fractions.Fraction) -> FracVector:
        """
        A FracVector rational approximation with elementwise error at most ``prec``.

        Each ``sqrt(r)`` is replaced by its rational lower bound ``floor(sqrt(r)*M)/M`` for a common
        ``M`` chosen so that the total weighted error per element is at most ``prec``; the result is
        the exact FracVector combination of those bounds. Rational values come back exactly.
        """
        if self.is_rational:
            return self._components.get(1, _zero_fracvector(self._dim))
        weight = fractions.Fraction(0)
        for radicand, comp in self._components.items():
            if radicand != 1:
                weight += _max_abs_leaf(comp)
        m = int(weight / prec) + 2 if prec > 0 else 2
        result = _zero_fracvector(self._dim)
        for radicand, comp in self._components.items():
            if radicand == 1:
                approx = fractions.Fraction(1)
            else:
                approx = fractions.Fraction(integer_sqrt(radicand * m * m), m)
            result = result + comp * approx
        return result

    def to_fractions_approx(self, prec: fractions.Fraction = fractions.Fraction(1, 10**30)) -> Any:
        """
        A deterministic nested list of :class:`fractions.Fraction` within ``prec`` of the true value.

        Exact (not merely within ``prec``) whenever the value is rational. This is the
        ``compute(prec)``-shaped rational approximation reused by the Decimal rendering.
        """
        return self._approx_fracvector(prec).to_fractions()

    def to_floats(self, prec: fractions.Fraction = fractions.Fraction(1, 10**30)) -> Any:
        """A nested list of floats (via a high-precision exact rational approximation)."""
        return self._approx_fracvector(prec).to_floats()

    #### Equality / hashing / display

    def __eq__(self, other: Any) -> bool:
        coerced = self._coerce(other)
        if coerced is None:
            return NotImplemented
        if self._dim != coerced._dim:
            return False
        if self._components.keys() != coerced._components.keys():
            return False
        return all(self._components[r] == coerced._components[r] for r in self._components)

    def __ne__(self, other: Any) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        """
        A hash consistent with :meth:`__eq__`.

        Delegates to each component's own hash rather than reaching for its raw
        ``(denom, noms)`` pair. :meth:`__init__` canonicalizes the components and drops
        zero ones, so the component set is already unambiguous, but a coefficient's stored
        representation still is not — and :meth:`FracVector.__hash__` is the thing that
        knows how to reduce it. Going through it keeps the two classes from drifting apart.
        """
        items = tuple(sorted((radicand, hash(comp)) for radicand, comp in self._components.items()))
        return hash((self._dim, items))

    def _term_str(self, radicand: int, comp: FracVector) -> str:
        if comp.dim == ():
            coeff = comp.to_fraction()
            coeff_str = str(coeff.numerator) if coeff.denominator == 1 else f"({coeff.numerator}/{coeff.denominator})"
            return coeff_str if radicand == 1 else f"{coeff_str}*sqrt({radicand})"
        return str(comp) if radicand == 1 else f"sqrt({radicand})*{comp}"

    def __str__(self) -> str:
        if not self._components:
            return "0"
        return " + ".join(self._term_str(radicand, comp) for radicand, comp in sorted(self._components.items()))

    def __repr__(self) -> str:
        items = ", ".join(f"{radicand}: {comp!r}" for radicand, comp in sorted(self._components.items()))
        return f"{type(self).__name__}({{{items}}}, {self._dim!r})"


class SurdScalar(SurdVector):
    """
    A scalar :class:`SurdVector` (shape ``()``): a single field element
    :math:`\\sum_r q_r\\sqrt r`.

    Adds the scalar-only operations — the field inverse, exact sign and ordering, and Decimal
    rendering — that need a single value rather than a tensor.
    """

    #### Field inverse

    def _conjugate(self, p: int) -> "SurdScalar":
        """Flip the sign of every term whose radicand is divisible by the prime ``p``."""
        comps: dict[int, FracVector] = {}
        for radicand, comp in self._components.items():
            comps[radicand] = -comp if radicand % p == 0 else comp
        return SurdScalar(comps, ())

    def _some_prime(self) -> int:
        """The smallest prime dividing some radicand ``> 1`` present (assumes one exists)."""
        for radicand in sorted(self._components):
            if radicand > 1:
                return _smallest_prime_factor(radicand)
        raise ValueError("SurdScalar: no irrational radicand present")

    def _inverse(self) -> "SurdScalar":
        """
        The multiplicative inverse ``1/self`` via iterated per-prime conjugation.

        Starting from ``num = 1`` and ``den = self``, for each prime ``p`` dividing a radicand of
        ``den`` both are multiplied by ``den``'s conjugate at ``p`` (sign flipped on the ``p | r``
        terms), which eliminates ``p`` from ``den``; after all distinct primes are cleared ``den`` is
        rational and the inverse is ``num / den``. The coefficient count can grow like ``2^k`` in the
        number ``k`` of distinct primes (tiny in practice).
        """
        if self.is_zero():
            raise ZeroDivisionError("SurdScalar: division by zero")
        num: SurdScalar = SurdVector.one()
        den: SurdScalar = self
        while any(radicand > 1 for radicand in den._components):
            conj = den._conjugate(den._some_prime())
            num = num._mul_surd(conj)._as_scalar()
            den = den._mul_surd(conj)._as_scalar()
        den_frac = den._rational_fraction()
        return num._mul_surd(SurdScalar({1: FracVector(den_frac.denominator, den_frac.numerator)}, ()))._as_scalar()

    def inverse(self) -> "SurdScalar":
        """The multiplicative inverse ``1/self`` (raises :class:`ZeroDivisionError` on zero)."""
        return self._inverse()

    #### Exact sign and ordering

    def sign(self) -> int:
        """
        Return the exact sign of the value: ``-1``, ``0`` or ``1``.

        For an irrational value the sign is decided by refining rational lower/upper bounds on each
        ``sqrt(r)`` (from :func:`~httk.core.vectors.exactmath.integer_sqrt` at increasing precision)
        and summing the weighted intervals until the total interval excludes zero — which always
        happens in finitely many steps because a nonzero surd is bounded away from zero.
        """
        if self.is_zero():
            return 0
        if self.is_rational:
            q = self._rational_fraction()
            return 1 if q > 0 else -1
        m = 4
        while True:
            scale = 10**m
            scale_sqr = scale * scale
            low = fractions.Fraction(0)
            high = fractions.Fraction(0)
            for radicand, comp in self._components.items():
                q = comp.to_fraction()
                if radicand == 1:
                    low += q
                    high += q
                    continue
                root = integer_sqrt(radicand * scale_sqr)
                r_low = fractions.Fraction(root, scale)
                r_high = fractions.Fraction(root + 1, scale)
                if q >= 0:
                    low += q * r_low
                    high += q * r_high
                else:
                    low += q * r_high
                    high += q * r_low
            if low > 0:
                return 1
            if high < 0:
                return -1
            m += 1

    def _compare(self, other: Any) -> int:
        coerced = self._coerce(other)
        if coerced is None:
            raise TypeError("SurdScalar: unsupported comparison operand")
        if coerced._dim != ():
            raise ValueError("SurdScalar: can only compare against a scalar")
        return (self - coerced)._as_scalar().sign()

    def __lt__(self, other: Any) -> bool:
        return self._compare(other) < 0

    def __le__(self, other: Any) -> bool:
        return self._compare(other) <= 0

    def __gt__(self, other: Any) -> bool:
        return self._compare(other) > 0

    def __ge__(self, other: Any) -> bool:
        return self._compare(other) >= 0

    #### Exact degree-mode trigonometry (Niven's theorem)

    @classmethod
    def cos_degrees(cls, q: Any) -> "SurdScalar | None":
        """
        Return ``cos(q degrees)`` as an exact :class:`SurdScalar`, or None when it is not a surd.

        The value lies in the squarefree-radical field precisely when the angle, reduced modulo
        360, is a **multiple of 15 or of 36 degrees** — e.g. :math:`\\cos 30° = \\tfrac{\\sqrt3}2`,
        :math:`\\cos 15° = \\tfrac{\\sqrt6+\\sqrt2}4`, :math:`\\cos 36° = \\tfrac{1+\\sqrt5}4`.
        ``q`` may be an int, :class:`~fractions.Fraction`, or numeric string (parsed via
        :func:`~httk.core.vectors.exactmath.any_to_fraction`).

        That list is **complete**: :math:`\\cos(2\\pi a/b)` lies in a field generated by square
        roots of rationals iff the Galois group :math:`(\\mathbb{Z}/b)^\\times/\\{\\pm1\\}` of
        :math:`\\mathbb{Q}(\\cos 2\\pi/b)` has exponent at most 2, which holds exactly for
        :math:`b \\in \\{1,2,3,4,5,6,8,10,12,24\\}` — the rational-degree angles that are multiples
        of 15° or 36°. (Niven's theorem is the rational-value special case of this classification.)
        A ``None`` result is therefore a proof that the exact cosine lies outside
        :math:`\\mathbb{Q}[\\sqrt n]` — use :func:`~httk.core.vectors.exactmath.cos` with
        ``degrees=True`` for a deterministic rational approximation in that case.
        """
        qf = any_to_fraction(q)
        reduced = qf - 360 * (qf // 360)
        if reduced.denominator == 1:
            return _niven_cos_table().get(int(reduced))
        return None

    @classmethod
    def sin_degrees(cls, q: Any) -> "SurdScalar | None":
        """
        Return ``sin(q degrees)`` as an exact :class:`SurdScalar`, or None when it is irrational.

        Computed as ``cos(90 - q)`` degrees, so exactness follows the same classification as
        :meth:`cos_degrees` applied to ``90 - q``: exact for all multiples of 15 degrees, otherwise
        None (a proof that the exact sine is outside the field). Note the asymmetry with
        :meth:`cos_degrees` for the 36° family: :math:`\\cos 36°` is an exact surd but
        :math:`\\sin 36° = \\cos 54°` is not (54 is a multiple of neither 15 nor 36).
        """
        qf = any_to_fraction(q)
        return cls.cos_degrees(90 - qf)

    def acos_degrees(self) -> "fractions.Fraction | None":
        """
        Return the exact ``arccos`` of this value in **degrees** over :math:`[0, 180]`, or None.

        This is the reverse table lookup: the result is an exact rational number of degrees
        precisely when the value equals the cosine of a multiple of 15° or 36° (the complete set of
        rational-degree angles with surd cosines — see :meth:`cos_degrees`), decided by exact surd
        equality; otherwise None (the exact angle is then irrational in degrees). Raises
        :class:`ValueError` — decided exactly via :meth:`sign` — when the value lies outside
        :math:`[-1, 1]`.
        """
        if self > 1 or self < -1:
            raise ValueError(f"SurdScalar.acos_degrees: value {self} is outside the domain [-1, 1]")
        for angle, cosine in sorted(_niven_cos_table().items()):
            if angle > 180:
                break
            if self == cosine:
                return fractions.Fraction(angle)
        return None

    #### Rendering

    def _scalar_approx(self, prec: fractions.Fraction) -> fractions.Fraction:
        """A single Fraction within ``prec`` of the value (exact when rational)."""
        return self._approx_fracvector(prec).to_fraction()

    def to_float(self, prec: fractions.Fraction = fractions.Fraction(1, 10**30)) -> float:
        """The value as a float (via a high-precision exact rational approximation)."""
        return float(self._scalar_approx(prec))

    def __float__(self) -> float:
        """``float(x)`` renders the scalar like :meth:`to_float` (default precision)."""
        return self.to_float()

    def to_decimal(
        self,
        digits: int | None = None,
        rounding: str = "half_even",
        max_refinements: int | None = None,
    ) -> Any:
        """
        Render the value as a correctly-rounded :class:`decimal.Decimal`.

        Reuses the exact-math module's Ziv refinement loop
        (``_to_decimal``): a rational value renders exactly (its
        finite expansion when it fits, else quantized), and an irrational surd — never on a rational
        rounding boundary — is rendered by refining the rational approximation until the rounding is
        determined. ``digits`` (significant digits; default: the active decimal context precision),
        ``rounding`` (``"half_even"``/``"down"``) and ``max_refinements`` match
        :func:`~httk.core.vectors.exactmath.sqrt` in Decimal mode.
        """
        _validate_decimal_params(digits, rounding, max_refinements)
        if self.is_rational:
            value = self._rational_fraction()

            def compute(_prec: fractions.Fraction) -> tuple[fractions.Fraction, bool]:
                return value, True

        else:

            def compute(_prec: fractions.Fraction) -> tuple[fractions.Fraction, bool]:
                return self._scalar_approx(_prec), False

        return _to_decimal(compute, digits, rounding, max_refinements)


# The exact cosines of the special angles, keyed by integer degrees in ``[0, 360)``. The angles
# with a cosine in the squarefree-radical field are exactly the multiples of 15 and of 36 degrees
# (see :meth:`SurdScalar.cos_degrees` for the Galois-theoretic classification; Niven's theorem is
# its rational-value special case), so this table is complete. Built lazily (once) since the
# :class:`SurdScalar` values need the class to be defined.
_NIVEN_COS_DEGREES: "dict[int, SurdScalar] | None" = None


def _niven_cos_table() -> "dict[int, SurdScalar]":
    """Return the cached ``{degrees -> cos as SurdScalar}`` table over the special angles."""
    global _NIVEN_COS_DEGREES
    if _NIVEN_COS_DEGREES is None:
        one = SurdVector.one()
        # First quadrant: every multiple of 15 or 36 in [0, 90].
        base: dict[int, SurdVector] = {
            0: one,
            15: (SurdVector.sqrt_of(6) + SurdVector.sqrt_of(2)) / 4,
            30: SurdVector.sqrt_of(3) / 2,
            36: (one + SurdVector.sqrt_of(5)) / 4,
            45: SurdVector.sqrt_of(2) / 2,
            60: one / 2,
            72: (SurdVector.sqrt_of(5) - one) / 4,
            75: (SurdVector.sqrt_of(6) - SurdVector.sqrt_of(2)) / 4,
            90: SurdVector.zero(),
        }
        table: dict[int, SurdScalar] = {}
        for angle, value in base.items():
            table[angle] = value._as_scalar()
            table[180 - angle] = (-value)._as_scalar()  # cos(180 - x) = -cos(x): covers [90, 180]
        for angle in list(table):
            if 0 < angle < 180:
                table[360 - angle] = table[angle]  # cos(360 - x) = cos(x): covers (180, 360)
        _NIVEN_COS_DEGREES = table
    return _NIVEN_COS_DEGREES
