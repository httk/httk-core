# Exact math on rationals and decimals

`httk.core.exactmath` computes with integer and rational arithmetic only — no
floating point anywhere — so results are deterministic and
platform-independent. The contract: **by default, a best effort is made to
return a symbolically exact value when one exists within reasonable
computational effort; otherwise a deterministic `Fraction` or `Decimal`
approximation.**

```python
from fractions import Fraction

from httk.core import exactmath

r3 = exactmath.sqrt(3)              # SurdScalar: exact sqrt(3), r3 * r3 == 3
exactmath.sqrt(Fraction(9, 4))      # Fraction(3, 2) — rational results stay rational
exactmath.cos(30, degrees=True)     # sqrt(3)/2, exactly
exactmath.acos(Fraction(1, 2), degrees=True)  # Fraction(60, 1), exactly
exactmath.cos(17, degrees=True)     # no exact form: a controlled rational approximation
exactmath.sqrt(2, exact=False)      # ask for the approximation explicitly
exactmath.sqrt(2, prec=Fraction(1, 10**12), exact=False)  # ... at a chosen precision
exactmath.any_to_fraction("8.04")   # Fraction(201, 25) — the written value, exactly
```

Symbolic results are `SurdScalar`/`SurdVector` values (see {doc}`vectors`),
which mix with `int`/`Fraction` exactly and with `float` as `Fraction` does.
They appear only for exact-domain input (`int`, `str`, `Fraction`,
`FracVector`); `float` input still gives a `float`.

When an approximation is returned, its domain is chosen by the input:
`Fraction`/`int`/`str` inputs give controlled rational approximations; any
`Decimal` argument (or an explicit `digits=`) instead gives a **correctly
rounded** `Decimal` to the requested number of significant figures:

```python
from decimal import Decimal

exactmath.sqrt(Decimal(2), digits=30)
# Decimal('1.41421356237309504880168872421')  — correctly rounded, half-even
```

`exact=True` demands the symbolic result and raises `ValueError` where none
exists; `exact=False` always approximates. The functions accept scalars and
vectors alike.

The full guide, {doc}`details/exactmath`, covers uncertainty-notation parsing,
best-rational approximation and continued fractions, the `coerce=` keyword,
rounding versus truncation modes, determinism and the context default, and the
termination guarantees behind correct rounding.
