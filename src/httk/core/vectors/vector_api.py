"""
The minimal canonical vector interface shared by all vector backends and views.
"""

import fractions
from abc import ABC, abstractmethod

# The canonical interchange is exactness-preserving: a (possibly nested) tuple of
# fractions.Fraction, or a bare Fraction for a scalar. Every representation can produce this
# exactly (numpy float64 values ARE binary rationals); only the numpy *view* direction is lossy.
type Fractions = fractions.Fraction | tuple[Fractions, ...]


class VectorAPI(ABC):
    """
    Abstract base class for the canonical vector interface.

    It declares the exactness-preserving ``fractions`` accessor (a nested tuple of
    :class:`fractions.Fraction`, or a bare Fraction for a scalar) that every vector backend
    produces from its own native representation and every vector view builds its presentation
    from, together with the ``dim`` shape tuple. This is the single interchange format; there is
    no pairwise conversion between backends.
    """

    @property
    @abstractmethod
    def fractions(self) -> Fractions:
        raise NotImplementedError

    @property
    @abstractmethod
    def dim(self) -> tuple[int, ...]:
        raise NotImplementedError
