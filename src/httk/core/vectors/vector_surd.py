"""
Backend wrapping a SurdVector in the exact squarefree-radical representation.
"""

import decimal
import fractions
from typing import Any

from .surdvector import SurdVector
from .vector_api import Fractions
from .vector_backend import VectorBackend
from .vector_frac import _fracvector_to_fractions

# Guard digits added to the active decimal context precision when a lossy (irrational) surd must be
# reduced to the rational ``fractions`` hub, mirroring exactmath's Ziv guard convention.
_HUB_GUARD_DIGITS = 3


class VectorSurd(VectorBackend):
    """
    Backend for a vector backed by an exact :class:`~httk.core.vectors.surdvector.SurdVector`
    (or :class:`~httk.core.vectors.surdvector.SurdScalar`), kind ``"surd"``.

    ``unwrap`` returns the exact SurdVector. The canonical ``fractions`` hub is **exact** whenever
    the value is rational (a surd whose canonical form has only the radicand-1 term), matching the
    established backend-keeps-the-original principle; when the value is genuinely irrational it is
    reduced to a *deterministic* rational approximation at the active decimal context precision plus
    a small guard (lossy but reproducible), and the exact original remains recoverable via
    ``unwrap``.
    """

    _surdvector: SurdVector

    # Cannot type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: Any, **hints: Any) -> Any:
        if not isinstance(obj, SurdVector):
            return None
        if hints and hints.get("kind", "surd") != "surd":
            return None
        return super().__new__(cls)

    def __init__(self, obj: SurdVector, **hints: Any) -> None:
        self._surdvector = obj

    @property
    def fractions(self) -> Fractions:
        surd = self._surdvector
        if surd.is_rational:
            return _fracvector_to_fractions(surd.coefficient(1))
        prec = fractions.Fraction(1, 10 ** (decimal.getcontext().prec + _HUB_GUARD_DIGITS))
        return _fracvector_to_fractions(surd._approx_fracvector(prec))

    @property
    def dim(self) -> tuple[int, ...]:
        return self._surdvector.dim

    def unwrap(self) -> Any:
        return self._surdvector
