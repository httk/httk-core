"""The accepted scalar inputs for exact-math functions."""

import decimal
import fractions

from . import fracvector, surdvector

type ScalarLike = (
    int | float | str | fractions.Fraction | decimal.Decimal | fracvector.FracScalar | surdvector.SurdScalar
)
