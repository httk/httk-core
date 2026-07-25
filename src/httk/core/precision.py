"""How precisely a number was written down.

A data file states its numbers to a definite number of digits, and that is a claim about
precision: ``0.3333`` says the value is known to about ``1e-4``, while ``0.33`` says only
``1e-2``. Recovering that claim is what lets a matching tolerance — or an spglib
``symprec`` — be *derived from the data* rather than guessed at, which is otherwise a
recurring source of arbitrary constants.

The value returned is an **absolute** bound, in whatever units the number was written in.
It is not a relative precision and not a significant-figure count: ``0.0001`` and
``9999.9999`` both report ``1e-4``.

This is deliberately a separate concept from the *arithmetic* precision in
:mod:`~httk.core.vectors.exactmath`, which governs how far an inexact computation is
carried. This module is about what the source said; that one is about what we compute.
"""

import fractions
import re
from typing import Iterable

__all__ = ["combined_precision", "decimal_precision"]

#: A decimal literal: optional sign, then digits with an optional point in any of the
#: usual arrangements, then an optional exponent. Anything else is not a decimal and gets
#: no precision claim rather than a guessed one.
_DECIMAL = re.compile(
    r"""
    ^
    [+-]?
    (?:
        (?P<int_only>\d+)                       # 10
      | (?P<int_part>\d*) \. (?P<frac>\d*)      # 0.123, .25, 5.
    )
    (?: [eE] (?P<exponent>[+-]?\d+) )?
    $
    """,
    re.VERBOSE,
)

#: Values a CIF uses for "unknown" and "inapplicable". Neither states a precision.
_NON_VALUES = frozenset({"?", "."})


def decimal_precision(text: object) -> fractions.Fraction | None:
    """The absolute precision implied by how a number was written, or ``None``.

    ``None`` means the literal makes no precision claim, which is a different thing from
    claiming perfect precision. It is returned for an empty or missing value, for CIF's
    ``?`` and ``.`` placeholders, for anything that is not a decimal literal, and — this
    one matters — for an exact rational such as ``"1/3"``, which states a value rather
    than a measurement and so should not drag a structure's precision down to
    the width of its last digit.

    Examples, all exact:

    * ``"0.123"`` -> ``1/1000`` — three digits after the point
    * ``"-0.5"`` -> ``1/10`` — the sign is not part of the claim
    * ``".25"`` -> ``1/100`` — a leading point is still two digits
    * ``"5."`` -> ``1`` — a trailing point states no fraction
    * ``"10"`` -> ``1`` — an integer literal is precise to the unit
    * ``"1.2e-3"`` -> ``1/10000`` — one digit, then scaled by the exponent
    * ``"1/3"`` -> ``None`` — exact, not measured
    * ``"?"`` -> ``None`` — no value at all
    """
    if text is None:
        return None
    literal = str(text).strip()
    if not literal or literal in _NON_VALUES:
        return None
    if "/" in literal:
        # A rational literal is an exact statement, not a rounded measurement.
        return None

    match = _DECIMAL.match(literal)
    if match is None:
        return None

    if match.group("int_only") is not None:
        digits_after_point = 0
    else:
        # A point with nothing on either side ("." alone) is not a number; the regex
        # allows both parts to be empty, so reject that here rather than reporting a
        # precision for it.
        if not match.group("int_part") and not match.group("frac"):
            return None
        digits_after_point = len(match.group("frac"))

    exponent = int(match.group("exponent") or 0)
    return fractions.Fraction(10) ** (exponent - digits_after_point)


def combined_precision(values: Iterable[object]) -> fractions.Fraction | None:
    """The precision of a set of values taken together: the **coarsest** of them.

    A structure is only as precisely stated as its least precisely stated number, so one
    sloppy ``0.5`` among a table of six-decimal coordinates really does mean the table is
    good to ``1e-1``. Taking the coarsest is the conservative reading and the one that
    keeps a derived tolerance from being too tight to match anything.

    Each value may be a literal to be interpreted by :func:`decimal_precision`, or an
    already-computed precision as a :class:`~fractions.Fraction`, :class:`int`, or
    :class:`float` — a standard uncertainty read from a file, say. Floats convert through
    their decimal spelling, so ``0.005`` lands on ``1/200`` rather than a binary
    approximation of it. Values that state no precision are skipped, and ``None`` is
    returned when none of them state one.
    """
    coarsest: fractions.Fraction | None = None
    for value in values:
        precision = _as_precision(value)
        if precision is None:
            continue
        if coarsest is None or precision > coarsest:
            coarsest = precision
    return coarsest


def _as_precision(value: object) -> fractions.Fraction | None:
    """One entry of :func:`combined_precision`, as a precision or ``None``."""
    if value is None:
        return None
    if isinstance(value, fractions.Fraction):
        return value if value > 0 else None
    if isinstance(value, bool):
        # bool is an int subclass, and "True" is not a precision.
        return None
    if isinstance(value, (int, float)):
        exact = fractions.Fraction(str(value))
        return exact if exact > 0 else None
    return decimal_precision(value)
