"""Exact math quickstart

By default exactmath returns a symbolically exact value where one exists (square roots and the
supported degree angles), a rational where the answer is rational, and otherwise a deterministic
Fraction approximation. Decimal inputs or ``digits=`` select correctly-rounded Decimals instead.
"""

from decimal import Decimal
from fractions import Fraction

from httk.core import exactmath
from httk.core.vectors import SurdScalar, SurdVector

root = exactmath.sqrt(2)
assert isinstance(root, SurdScalar) and root * root == 2
assert exactmath.cos(30, degrees=True) == SurdVector.sqrt_of(3) / 2
assert exactmath.acos(Fraction(1, 2), degrees=True) == 60

fraction_root = exactmath.sqrt(Fraction(9, 4))
approx_root = exactmath.sqrt(2, exact=False)
decimal_root = exactmath.sqrt(Decimal(2), digits=12)
assert isinstance(fraction_root, Fraction) and fraction_root == Fraction(3, 2)
assert isinstance(approx_root, Fraction)
assert decimal_root == Decimal("1.41421356237")
print(root, fraction_root, approx_root, decimal_root)
