#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2026 the httk AUTHORS
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
Exact decimal numbers as written in a CIF file: value, standard uncertainty and spelling.

A :class:`DecimalVector` keeps what a number token says, not only what it is worth: ``0.50``
claims more digits than ``0.5``, ``1.2345(6)`` carries the standard uncertainty ``0.0006``, and
an unquoted ``007`` may be an identifier. The token text is the canonical form of the value,
uncertainty and spelling, so equality and hashing compare tokens and distinguish ``0.50`` from
``0.5``; :meth:`DecimalVector.numerically_equal` compares values. Entries may be the CIF gaps
``?`` and ``.`` (:class:`DecimalGap`).

Nothing here computes with the numbers: construction, equality, rendering and storage never
expand a value, so ``1e-999999999`` is cheap. Convert to :class:`~httk.core.vectors.FracVector`
(``FracVector(dv)``) or floats for arithmetic; those conversions, and
:attr:`DecimalVector.precisions`, apply the size bound of :mod:`httk.core.exactmath`.
"""

import decimal
import enum
import fractions
import operator
import re
import types
from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast

from httk.core import exactmath

__all__ = ["DecimalEntry", "DecimalGap", "DecimalIndex", "DecimalScalar", "DecimalVector", "Nested"]


class DecimalGap(enum.Enum):
    """A CIF entry without a value: unknown (``?``) or inapplicable (``.``)."""

    UNKNOWN = "?"
    INAPPLICABLE = "."

    def __repr__(self) -> str:
        """Return the evaluable member name.

        :return: ``DecimalGap.UNKNOWN`` or ``DecimalGap.INAPPLICABLE``.
        """
        return f"DecimalGap.{self.name}"


#: The index of one entry: one integer per dimension, ``()`` for a scalar.
type DecimalIndex = tuple[int, ...]
#: One entry: an exact finite decimal or a gap.
type DecimalEntry = decimal.Decimal | DecimalGap
#: A scalar leaf, or nested tuples of them.
type Nested[T] = T | tuple[Nested[T], ...]

# A CIF numeric token (ASCII only, matched in full). The uncertainty may stand before the
# exponent (``1.5(2)E-3``, existing practice) or after it (``1.5E-3(2)``, the CIF 1.1 grammar).
# Decimal() never decides what is a number: it also accepts NaN, Infinity and 1_000. Each digit run
# has one way to match, so a long non-number is rejected in linear time.
_NUMBER = re.compile(
    r"(?P<sign>[+-])?(?P<mant>[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:\((?P<su1>[0-9]+)\)(?:[eE](?P<exp1>[+-]?[0-9]+))?"
    r"|(?:[eE](?P<exp2>[+-]?[0-9]+))?(?:\((?P<su2>[0-9]+)\))?)"
)
_SU = re.compile(r"\([0-9]+\)")
# Exact construction only; an exponent outside Decimal's range raises instead of becoming NaN,
# whatever the caller's global context says.
_EXACT = decimal.Context(traps=[decimal.InvalidOperation])
_GAPS = {gap.value: gap for gap in DecimalGap}


def _parse(token: str) -> tuple[decimal.Decimal, decimal.Decimal | None]:
    """Return the value and standard uncertainty of a numeric token."""
    match = _NUMBER.fullmatch(token)
    if match is None:
        raise ValueError(f"not a CIF number: {token[:60]!r}")
    exponent = match["exp1"] or match["exp2"]
    su = match["su1"] or match["su2"]
    text = (match["sign"] or "") + match["mant"] + ("" if exponent is None else "E" + exponent)
    try:
        with decimal.localcontext(_EXACT):
            value = decimal.Decimal(text)
            uncertainty = None
            if su is not None:
                digits = tuple(int(c) for c in su.lstrip("0")) or (0,)
                uncertainty = decimal.Decimal((0, digits, cast(int, value.as_tuple().exponent)))
    except decimal.InvalidOperation:
        raise ValueError(f"not a CIF number (exponent out of range): {token[:60]!r}") from None
    if not value.is_finite() or not (uncertainty is None or uncertainty.is_finite()):
        raise ValueError(f"not a CIF number: {token[:60]!r}")
    return value, uncertainty


def _render(value: decimal.Decimal, su: decimal.Decimal | None) -> str:
    """Return the canonical token for a value and its standard uncertainty."""
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)  # finite by construction
    text = "".join(map(str, digits))
    if -64 <= exponent <= 0:
        if exponent:
            text = text.rjust(1 - exponent, "0")
            text = f"{text[:exponent]}.{text[exponent:]}"
    else:
        # Never expand a large exponent into digits.
        text = f"{text}E{exponent:+d}"
    if sign:
        text = "-" + text
    if su is not None:
        text += "(" + "".join(map(str, su.as_tuple().digits)) + ")"
    return text


def _leaf_token(leaf: Any) -> str:
    """Return the token of one accepted leaf."""
    if isinstance(leaf, DecimalScalar):
        return leaf.token
    if isinstance(leaf, DecimalGap):
        return leaf.value
    if isinstance(leaf, str):
        return str.__str__(leaf)  # a plain str, whatever a subclass overrides
    if isinstance(leaf, (bool, float, fractions.Fraction)):
        raise TypeError(
            f"DecimalVector does not accept {type(leaf).__name__} leaves; use a numeric token string, Decimal or int"
        )
    if isinstance(leaf, int):
        try:
            return int.__repr__(leaf)
        except ValueError:  # beyond the interpreter's integer-to-string limit
            raise ValueError("DecimalVector integer leaf has too many digits") from None
    if isinstance(leaf, decimal.Decimal):
        if not leaf.is_finite():
            raise ValueError(f"DecimalVector entries must be finite, not {leaf!r}")
        return _render(leaf, None)
    raise TypeError(f"unsupported DecimalVector leaf type: {type(leaf).__name__}")


def _normalize(node: Any) -> tuple[Nested[str], tuple[int, ...]]:
    """Return the nested tokens and dimensions of a rectangular input."""
    if isinstance(node, DecimalVector) and not isinstance(node, DecimalScalar):
        return node._tokens, node._dim
    if not isinstance(node, (list, tuple)):
        return _leaf_token(node), ()
    items = [_normalize(item) for item in node]
    dims = {dim for _, dim in items}
    if len(dims) > 1:
        raise ValueError("DecimalVector input must be rectangular")
    return tuple(tokens for tokens, _ in items), (len(items), *(dims.pop() if dims else ()))


def _map[T](node: Any, fn: Callable[[Any, DecimalIndex], T], index: DecimalIndex = ()) -> Nested[T]:
    """Map ``fn(leaf, index)`` over nested tuples."""
    if isinstance(node, tuple):
        return tuple(_map(item, fn, (*index, i)) for i, item in enumerate(node))
    return fn(node, index)


def _flat(node: Any) -> Iterator[Any]:
    if isinstance(node, tuple):
        for item in node:
            yield from _flat(item)
    else:
        yield node


def _precision(token: str, index: DecimalIndex) -> fractions.Fraction | None:
    """Return the precision a token implies, without its uncertainty."""
    # Bound late: precision imports exactmath, which imports this package.
    from httk.core.precision import decimal_precision

    try:
        return decimal_precision(_SU.sub("", token))
    except ValueError as error:
        raise ValueError(f"entry {index}: {error}") from None


def _numeric(entry: DecimalEntry, index: DecimalIndex) -> decimal.Decimal:
    """Return a non-gap entry after the exact-size check, or raise for a gap."""
    if isinstance(entry, DecimalGap):
        raise ValueError(f"entry {index} is {entry.name.lower()} ({entry.value!r}) and has no value")
    exactmath._check_text_size(_render(entry, None))
    return entry


class DecimalVector:
    """Exact decimal numbers as written, with optional standard uncertainties.

    Any shape :class:`~httk.core.vectors.FracVector` supports, including empty dimensions.
    Each leaf is a CIF numeric token, ``"?"`` or ``"."`` (nothing is stripped), a finite
    :class:`decimal.Decimal` (canonical spelling, no uncertainty), an ``int`` (not ``bool``), a
    :class:`DecimalGap` or a :class:`DecimalScalar`. Containers are lists, tuples or
    DecimalVectors and must be rectangular. A bare leaf needs :class:`DecimalScalar`.

    :param values: The nested entries.
    :raises TypeError: For a ``float``, ``Fraction``, ``bool`` or other unsupported leaf, or a
        bare leaf.
    :raises ValueError: For a non-numeric string, a non-finite ``Decimal`` or ragged nesting.
    """

    __slots__ = ("_dim", "_spellings", "_tokens", "_uncertainties", "_values")

    def __init__(self, values: Any) -> None:
        tokens, dim = _normalize(values)
        if (dim == ()) != isinstance(self, DecimalScalar):
            raise TypeError(
                "DecimalScalar takes a single leaf" if dim else "a bare leaf needs DecimalScalar, not DecimalVector"
            )
        uncertainties: dict[DecimalIndex, decimal.Decimal] = {}
        spellings: dict[DecimalIndex, str] = {}

        def entry(token: str, index: DecimalIndex) -> DecimalEntry:
            gap = _GAPS.get(token)
            if gap is not None:
                return gap
            value, su = _parse(token)
            if su is not None:
                uncertainties[index] = su
            if token != _render(value, su):
                spellings[index] = token
            return value

        self._values: Nested[DecimalEntry] = _map(tokens, entry)
        # A leaf's token is its spelling when it has one, otherwise its canonical rendering,
        # which is exactly the normalized input token.
        self._tokens: Nested[str] = tokens
        self._dim: tuple[int, ...] = dim
        self._uncertainties: Mapping[DecimalIndex, decimal.Decimal] = types.MappingProxyType(uncertainties)
        self._spellings: Mapping[DecimalIndex, str] = types.MappingProxyType(spellings)

    @property
    def dim(self) -> tuple[int, ...]:
        """The dimensions, ``()`` for a scalar."""
        return self._dim

    @property
    def values(self) -> Nested[DecimalEntry]:
        """The entries as nested tuples of :class:`decimal.Decimal` and :class:`DecimalGap`."""
        return self._values

    @property
    def uncertainties(self) -> Mapping[DecimalIndex, decimal.Decimal]:
        """The stated standard uncertainties by index (read-only, sparse), in the value's unit."""
        return self._uncertainties

    @property
    def spellings(self) -> Mapping[DecimalIndex, str]:
        """The tokens that differ from the canonical rendering, by index (read-only, sparse)."""
        return self._spellings

    @property
    def tokens(self) -> Nested[str]:
        """The entries as CIF tokens (the spelling or else the canonical rendering, and ``?``/``.`` for gaps)."""
        return self._tokens

    @property
    def precisions(self) -> Nested[fractions.Fraction | None]:
        """The precision each entry's token implies (:func:`~httk.core.precision.decimal_precision`).

        The uncertainty is not part of the claim; gaps, integers and trailing points give ``None``.
        A token whose exact value exceeds the size bound raises :class:`ValueError`.
        """
        return _map(self._tokens, _precision)

    def __len__(self) -> int:
        """Return the length of the first dimension.

        :return: ``dim[0]``.
        :raises TypeError: For a scalar.
        """
        if not self._dim:
            raise TypeError("a DecimalScalar has no length")
        return self._dim[0]

    def __iter__(self) -> Iterator["DecimalVector"]:
        """Iterate over the first dimension.

        :return: An iterator of sub-vectors or scalars.
        """
        return (self[i] for i in range(len(self)))

    def __getitem__(self, i: int) -> "DecimalVector":
        """Return one row of the first dimension.

        :param i: The integer index.
        :return: A :class:`DecimalScalar` for a rank-1 vector, otherwise a DecimalVector.
        :raises TypeError: For a scalar or a non-integer index.
        """
        if not self._dim:
            raise TypeError("a DecimalScalar cannot be indexed")
        row = cast(tuple[Any, ...], self._tokens)[operator.index(i)]
        return DecimalScalar(row) if len(self._dim) == 1 else DecimalVector(row)

    def __eq__(self, other: object) -> bool:
        """Compare tokens exactly: ``0.50 != 0.5``, ``007 != 7`` and ``? != .``.

        :param other: The object to compare with.
        :return: Whether both have the same class and tokens.
        """
        if not isinstance(other, DecimalVector):
            return NotImplemented
        return type(self) is type(other) and self._tokens == other._tokens

    def __hash__(self) -> int:
        """Hash the class name and tokens.

        :return: The hash.
        """
        return hash((type(self).__name__, self._tokens))

    def __repr__(self) -> str:
        """Return a representation that round-trips through the constructor.

        :return: ``DecimalVector(<tokens>)``.
        """
        return f"{type(self).__name__}({self._tokens!r})"

    def __reduce__(self) -> tuple[type[Any], tuple[Any]]:
        """Pickle through the tokens.

        :return: The class and its constructor argument.
        """
        return type(self), (self._tokens,)

    def numerically_equal(self, other: "DecimalVector") -> bool:
        """Compare values exactly, ignoring uncertainties and spelling.

        :param other: The vector to compare with.
        :return: Whether both have the same dimensions and, at every index, either the same gap
            kind or equal values.
        :raises TypeError: If ``other`` is not a DecimalVector.
        """
        if not isinstance(other, DecimalVector):
            raise TypeError(f"cannot compare a DecimalVector with {type(other).__name__}")
        if self._dim != other._dim:
            return False
        for a, b in zip(_flat(self._values), _flat(other._values), strict=True):
            if isinstance(a, DecimalGap) or isinstance(b, DecimalGap):
                if a is not b:
                    return False
            elif a != b:
                return False
        return True

    def to_fractions(self) -> Nested[fractions.Fraction]:
        """Return the exact values as nested tuples of fractions, ignoring uncertainties.

        This is the leaf protocol :class:`~httk.core.vectors.FracVector` reads, so
        ``FracVector(dv)`` is the exact conversion.

        :return: The exact values.
        :raises ValueError: For a gap entry, or a value beyond the exact-size bound.
        """
        return _map(self._values, lambda entry, index: fractions.Fraction(_numeric(entry, index)))

    def to_floats(self) -> Nested[float]:
        """Return the values as nested tuples of floats, ignoring uncertainties.

        :return: The values rounded to floats.
        :raises ValueError: For a gap entry, or a value beyond the exact-size bound.
        :raises OverflowError: For a value beyond the float range.
        """
        return _map(self._values, lambda entry, index: float(fractions.Fraction(_numeric(entry, index))))


class DecimalScalar(DecimalVector):
    """One exact decimal number as written, or a gap (``dim == ()``).

    :param value: A numeric token, ``"?"`` or ``"."``, a finite :class:`decimal.Decimal`, an
        ``int``, a :class:`DecimalGap` or a DecimalScalar.
    :raises TypeError: For an unsupported leaf or a container.
    :raises ValueError: For a non-numeric string or a non-finite ``Decimal``.
    """

    __slots__ = ()

    def __init__(self, value: "str | decimal.Decimal | int | DecimalGap | DecimalScalar") -> None:
        super().__init__(value)

    def __bool__(self) -> bool:
        """Refuse a truth value: the entry may be zero or a gap.

        :return: Never returns.
        :raises TypeError: Always; compare ``value`` instead.
        """
        raise TypeError("a DecimalScalar has no truth value; compare its value")

    @property
    def value(self) -> DecimalEntry:
        """The value, or the gap."""
        return cast(DecimalEntry, self._values)

    @property
    def uncertainty(self) -> decimal.Decimal | None:
        """The standard uncertainty, or ``None`` when none was stated."""
        return self._uncertainties.get(())

    @property
    def spelling(self) -> str | None:
        """The token when it differs from the canonical rendering, else ``None``."""
        return self._spellings.get(())

    @property
    def token(self) -> str:
        """The CIF token."""
        return cast(str, self._tokens)

    @property
    def precision(self) -> fractions.Fraction | None:
        """The precision the token implies (see :attr:`DecimalVector.precisions`)."""
        return cast(fractions.Fraction | None, self.precisions)
