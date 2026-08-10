"""
A view presenting any vector backend as nested tuples, with a selectable leaf codec.
"""

from typing import Any, Self

from httk.core.views import unwrap

from .leaf_codecs import apply_leaf_codec, leaf_codec_for_name, validate_leaf_codec
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_native import VectorNativeBackend
from .vector_view import VectorView


def _tupleize(node: Any) -> Any:
    """
    Present nested data as nested tuples, tuple-izing every list/tuple container but leaving leaf
    objects **untouched** — the identical ``int``/``float``/:class:`decimal.Decimal`/... instances.
    """
    if isinstance(node, (list, tuple)):
        return tuple(_tupleize(e) for e in node)
    return node


class VectorNativeView(VectorView, tuple):
    r"""
    A view presenting an underlying vector backend as nested tuples, with a selectable *leaf codec*.

    The leaf codec is the element-domain axis (see :mod:`httk.core.vectors.leaf_codecs`); it is
    chosen with the ``leaf=`` hint plus any codec options (``rounding=``, ``digits=``, ...). There
    are three modes:

    - **preserve-original** (``leaf=None``, and the source is natively-held data): the backend's
      original nested leaves are presented *verbatim* — the same objects, only containers tuple-ized
      (``Decimal``\\ s in, the same ``Decimal``\\ s out).
    - **exact default** (``leaf=None``, source crossing from a frac/numpy backend): the ``"exact"``
      codec — ``int`` when integral, else :class:`fractions.Fraction`, never a float.
    - **explicit codec** (``leaf="int"``/``"float"``/``"decimal"``/``"fraction"``/...): every element
      is converted from the backend's exact ``fractions`` interchange through that codec.

    The codec name and its options are validated eagerly at construction (an unknown codec name or
    invalid option raises :class:`ValueError`); a codec never raises on the *data* — a value it
    cannot represent exactly takes the codec's documented default conversion, because the backend
    keeps the exact original. A scalar source is presented as a single-element tuple.

    :param obj: The source value to present.
    :param \**hints: Backend-selection, leaf-codec, and codec-option hints.
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        leaf = hints.pop("leaf", None)
        backend = cls._prepare_backend(obj, hints)
        if leaf is None:
            if isinstance(backend, VectorNativeBackend):
                native = _tupleize(backend.native)
            else:
                native = apply_leaf_codec(leaf_codec_for_name("exact"), backend.fractions)
        else:
            options = {k: v for k, v in hints.items() if k != "kind"}
            codec = validate_leaf_codec(leaf, options)
            native = apply_leaf_codec(codec, backend.fractions, **options)
        if isinstance(native, tuple):
            instance = super().__new__(cls, native)
        else:
            instance = super().__new__(cls, (native,))
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        """Return the underlying unwrapped vector."""
        return unwrap(self._backend)

    def unview(self) -> Any:
        """Return a plain tuple containing the presented leaves."""
        # The view IS its presentation tuple; shed to a plain tuple (shallow, leaves shared).
        return tuple(self)
