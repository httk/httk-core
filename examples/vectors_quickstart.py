"""Vectors quickstart

Mixed numeric input can enter the exact-rational vector surface without converting through floats.
After exact arithmetic, choose a native or numpy view when a numerical presentation is needed.
"""

from fractions import Fraction

import numpy

from httk.core.vectors import FracVector, VectorNativeView, VectorNumpyView

vector = FracVector.create([1, Fraction(1, 2), "1/3"])
doubled = vector * 2
assert doubled == FracVector.create([2, 1, "2/3"])
assert VectorNativeView(doubled) == (2, 1, Fraction(2, 3))

numeric = VectorNumpyView(doubled)
assert isinstance(numeric, numpy.ndarray)
assert numeric.tolist() == [2.0, 1.0, 2 / 3]
print("exact:", doubled.to_fractions(), "numeric:", numeric.tolist())
