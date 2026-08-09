"""Canonical text rendering for exact rational values."""

import fractions


def fraction_to_text(value: fractions.Fraction) -> str:
    """Return reduced ``p/q`` text with an explicit positive denominator.

    :param value: The canonical fraction to render.
    :return: ``numerator/denominator`` text, including ``/1`` for integers.
    """
    return f"{value.numerator}/{value.denominator}"
