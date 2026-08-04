"""Exact math quickstart

Exact mode keeps square roots and supported degree trigonometry symbolic instead of approximating.
The ordinary Fraction mode and the Decimal mode selected by ``digits=`` remain available beside it.
"""

from decimal import Decimal
from fractions import Fraction

from httk.core import exactmath
from httk.core.vectors import SurdVector

root = exactmath.sqrt(Fraction(2), exact=True)
assert root * root == SurdVector.create(2)
assert exactmath.cos(Fraction(30), degrees=True, exact=True) == SurdVector.sqrt_of(3) / 2

fraction_root = exactmath.sqrt(Fraction(9, 4))
decimal_root = exactmath.sqrt(Decimal(2), digits=12)
assert isinstance(fraction_root, Fraction) and fraction_root == Fraction(3, 2)
assert decimal_root == Decimal("1.41421356237")
print(root, fraction_root, decimal_root)
