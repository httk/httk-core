"""
Leaf codecs: the element-domain axis of the Vector family.

The Vector backends model the *container* axis (``frac``/``native``/``numpy``); a **leaf codec**
models the orthogonal *element-domain* axis — how a single leaf value is presented (as an ``int``,
a :class:`fractions.Fraction`, a ``float``, a :class:`decimal.Decimal`, ...). Every codec converts
FROM the canonical Fraction hub (a backend's exact ``fractions`` interchange), so it is independent
of which backend holds the data.

Conversion policy (mirroring the CellParams lossiness philosophy): because a backend always retains
the exact original, a view that cannot represent the data exactly is still produced without raising
— each codec applies a *documented default conversion*, with options to choose alternatives. Only
configuration errors — an unknown codec name or invalid options — raise :class:`ValueError`.

This registry mirrors the compression-codec registry in
:mod:`httk.core.datastream.compression`: a frozen :class:`LeafCodec` dataclass plus
:func:`register_leaf_codec`/:func:`known_leaf_codecs` for extension.
"""

import decimal
import fractions
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from httk.core import exactmath


@dataclass(frozen=True)
class LeafCodec:
    """
    A leaf codec: a documented conversion of one exact :class:`fractions.Fraction` leaf into a
    presentation leaf.

    A codec is an orthogonal layer beside the vector backends: given a value already reduced to the
    canonical Fraction hub, it produces the requested element type. Its :attr:`from_fraction`
    documents both its exactness contract (when the result is exact) and its default conversion
    (what it does when an exact result is impossible); on data it never raises.
    """

    name: str
    """Canonical codec name (e.g. ``"int"``); also how an explicit ``leaf=`` hint selects it."""

    from_fraction: Callable[..., Any]
    """Convert ``(value: fractions.Fraction, **options) -> leaf`` from the canonical Fraction hub."""

    check_options: Callable[[dict[str, Any]], None]
    """Validate an options mapping eagerly, raising :class:`ValueError` on any invalid option."""


_registry: dict[str, LeafCodec] = {}


def register_leaf_codec(codec: LeafCodec) -> None:
    """Register (or replace) a codec under its :attr:`~LeafCodec.name`."""
    _registry[codec.name] = codec


def known_leaf_codecs() -> list[str]:
    """Return the registered leaf-codec names, in registration order."""
    return list(_registry)


def leaf_codec_for_name(name: str) -> LeafCodec:
    """Return the registered codec named ``name``, or raise :class:`ValueError` listing the known
    codecs."""
    try:
        return _registry[name]
    except KeyError:
        raise ValueError(f"unknown leaf codec {name!r}; known codecs: {known_leaf_codecs()}") from None


def validate_leaf_codec(name: str, options: dict[str, Any]) -> LeafCodec:
    """
    Resolve and validate a leaf codec eagerly and return it.

    Raises :class:`ValueError` if ``name`` is not a registered codec or if ``options`` are invalid
    for it (the two configuration-error cases). This is called where a ``leaf=`` hint is received so
    that mistakes surface at view construction, never mid-conversion.
    """
    codec = leaf_codec_for_name(name)
    codec.check_options(options)
    return codec


def apply_leaf_codec(codec: LeafCodec, node: Any, **options: Any) -> Any:
    """
    Map ``codec`` over a (possibly nested) tuple of :class:`fractions.Fraction`, returning the
    converted nested structure (a bare leaf for a scalar ``node``).
    """
    if isinstance(node, tuple):
        return tuple(apply_leaf_codec(codec, e, **options) for e in node)
    return codec.from_fraction(node, **options)


# --------------------------------------------------------------------- option validators


def _check_no_options(options: dict[str, Any]) -> None:
    if options:
        raise ValueError(f"unexpected options {sorted(options)}; this leaf codec takes no options")


_ROUNDINGS = ("round", "floor", "ceil", "trunc")


def _check_int_options(options: dict[str, Any]) -> None:
    extra = set(options) - {"rounding"}
    if extra:
        raise ValueError(f"unexpected options {sorted(extra)} for leaf codec 'int'; only 'rounding' is accepted")
    rounding = options.get("rounding", "round")
    if rounding not in _ROUNDINGS:
        raise ValueError(f"unknown rounding {rounding!r} for leaf codec 'int'; expected one of {list(_ROUNDINGS)}")


def _check_decimal_options(options: dict[str, Any]) -> None:
    extra = set(options) - {"digits"}
    if extra:
        raise ValueError(f"unexpected options {sorted(extra)} for leaf codec 'decimal'; only 'digits' is accepted")
    digits = options.get("digits")
    if digits is not None and (not isinstance(digits, int) or isinstance(digits, bool) or digits <= 0):
        raise ValueError(f"invalid digits {digits!r} for leaf codec 'decimal'; expected a positive integer")


# --------------------------------------------------------------------- built-in conversions


def _exact_from_fraction(value: fractions.Fraction) -> int | fractions.Fraction:
    """``int`` when the value is integral, else the exact :class:`fractions.Fraction`. Always
    exact — never a float."""
    return int(value) if value.denominator == 1 else value


def _fraction_from_fraction(value: fractions.Fraction) -> fractions.Fraction:
    """The value itself, always as an exact (reduced) :class:`fractions.Fraction`. Always exact."""
    return value


def _int_from_fraction(value: fractions.Fraction, rounding: str = "round") -> int:
    """
    An ``int``. Exact when the value is integral; otherwise rounded per ``rounding``:

    - ``"round"`` (default) — nearest, ties to even, matching Python's :func:`round` on a Fraction;
    - ``"floor"`` — toward negative infinity;
    - ``"ceil"`` — toward positive infinity;
    - ``"trunc"`` — toward zero.

    Never raises on data.
    """
    if rounding == "round":
        return round(value)
    if rounding == "floor":
        return math.floor(value)
    if rounding == "ceil":
        return math.ceil(value)
    if rounding == "trunc":
        return math.trunc(value)
    raise ValueError(f"unknown rounding {rounding!r} for leaf codec 'int'; expected one of {list(_ROUNDINGS)}")


def _float_from_fraction(value: fractions.Fraction) -> float:
    """A ``float``. Inherently lossy: the value is rounded to the nearest IEEE-754 binary double,
    so e.g. ``1/3`` becomes its nearest binary rational. Documented, never raises."""
    return float(value)


def _decimal_from_fraction(value: fractions.Fraction, digits: int | None = None) -> decimal.Decimal:
    """
    A :class:`decimal.Decimal`.

    **Exact** when the reduced denominator is of the form ``2**a * 5**b`` (a finite decimal
    expansion): the exact decimal is produced with no rounding, regardless of the active decimal
    context. Otherwise the value has no finite decimal expansion, so it is quantized to ``digits``
    significant digits (default: the active :func:`decimal.getcontext` precision) with round-half-
    even. Never raises on data.
    """
    # The finite-expansion (2**a * 5**b) detection and exact construction is shared with the
    # exact-math module (:func:`httk.core.exactmath._finite_decimal_expansion`).
    finite = exactmath._finite_decimal_expansion(value)
    if finite is not None:
        return finite
    precision = decimal.getcontext().prec if digits is None else digits
    context = decimal.Context(prec=precision, rounding=decimal.ROUND_HALF_EVEN)
    return context.divide(decimal.Decimal(value.numerator), decimal.Decimal(value.denominator))


register_leaf_codec(LeafCodec("exact", _exact_from_fraction, _check_no_options))
register_leaf_codec(LeafCodec("fraction", _fraction_from_fraction, _check_no_options))
register_leaf_codec(LeafCodec("int", _int_from_fraction, _check_int_options))
register_leaf_codec(LeafCodec("float", _float_from_fraction, _check_no_options))
register_leaf_codec(LeafCodec("decimal", _decimal_from_fraction, _check_decimal_options))
