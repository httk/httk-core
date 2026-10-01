# Exact math on rationals and decimals

`httk.core.exactmath` computes with integer and rational arithmetic only — no
floating point anywhere — so results are deterministic and
platform-independent. Parse written values exactly, then compute to the
precision you ask for:

```python
from fractions import Fraction

from httk.core import exactmath

exactmath.any_to_fraction("8.04")   # Fraction(201, 25) — the written value, exactly
exactmath.sqrt(Fraction(9, 4))      # Fraction(3, 2) — exact results when they exist
exactmath.sqrt(2, prec=Fraction(1, 10**12))  # a controlled rational approximation
```

Two result domains, chosen by the input: `Fraction`/`int`/`str` inputs give
exact rationals or controlled rational approximations; any `Decimal` argument
(or an explicit `digits=`) instead gives a **correctly rounded** `Decimal` to
the requested number of significant figures:

```python
from decimal import Decimal

exactmath.sqrt(Decimal(2), digits=30)
# Decimal('1.41421356237309504880168872421')  — correctly rounded, half-even
```

`exact=True` on `sqrt` returns exact radicals as `SurdScalar`s (see
{doc}`vectors`), and the functions accept scalars and vectors alike.

The full guide, {doc}`details/exactmath`, covers uncertainty-notation parsing,
best-rational approximation and continued fractions, the `coerce=` keyword,
rounding versus truncation modes, determinism and the context default, and the
termination guarantees behind correct rounding.
