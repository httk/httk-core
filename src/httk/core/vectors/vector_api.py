"""
The minimal canonical vector interface shared by all vector backends and views.
"""

import fractions
from abc import ABC, abstractmethod
from typing import Any

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

    On top of the two abstract accessors it provides the guaranteed float renderings
    :meth:`to_floats` and :meth:`to_float`, derived from the ``fractions`` hub — so *whatever*
    object the family hands you, ``.to_floats()`` works. (The exact value types
    :class:`~httk.core.vectors.fracvector.FracVector` and
    :class:`~httk.core.vectors.surdvector.SurdVector` honor the same contract with their own
    implementations.)
    """

    @property
    @abstractmethod
    def fractions(self) -> Fractions:
        """Return the exact Fraction interchange representation."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dim(self) -> tuple[int, ...]:
        """Return the tensor shape as a tuple of dimensions."""
        raise NotImplementedError

    def to_floats(self) -> Any:
        """
        Return the value as nested lists of floats.

        The value as (possibly nested) plain lists of ``float`` — a bare ``float`` for a scalar.

        Derived from the exact ``fractions`` hub; nested lists match the
        ``numpy.ndarray.tolist()`` convention and are directly JSON-serializable.

        :return: The rendered value.
        """

        def rec(node: Fractions) -> Any:
            if isinstance(node, tuple):
                return [rec(e) for e in node]
            return float(node)

        return rec(self.fractions)

    def to_float(self) -> float:
        """
        Return the scalar value as a plain ``float``.

        Raises :class:`TypeError` on a non-scalar.

        :return: The rendered scalar value.
        :raises TypeError: If the value is not scalar.
        """
        value = self.fractions
        if isinstance(value, tuple):
            raise TypeError(f"to_float: expected a scalar, got shape {self.dim}")
        return float(value)
