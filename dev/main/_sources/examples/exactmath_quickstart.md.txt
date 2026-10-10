# Exact math quickstart

By default exactmath returns a symbolically exact value where one exists (square roots and the
supported degree angles), a rational where the answer is rational, and otherwise a deterministic
Fraction approximation. Decimal inputs or ``digits=`` select correctly-rounded Decimals instead.

```{literalinclude} ../../examples/exactmath_quickstart.py
:language: python
:lines: 7-
```
