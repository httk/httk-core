from typing import Any, Self

from ..views import unwrap
from .bytestream_backend import BytestreamBackend
from .bytestream_like import BytestreamLike
from .bytestream_view import BytestreamView


class BytestreamBytesView(BytestreamView, bytes):
    """
    A view presenting underlying streaming byte data as bytes.
    This view can be used both to pass bytes in place of streaming data, and for reading streaming data into bytes.
    Note: this view is not lazy (this is impossible for views inheriting bytes, since bytes is immutable), hence all
    streaming data is read immediately upon creating this view.
    """

    _backend: BytestreamBackend

    def __new__(cls, obj: BytestreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        instance = super().__new__(cls, backend.read())
        instance._backend = backend
        return instance

    def __init__(self, obj: BytestreamLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        return unwrap(self._backend)

    def unview(self) -> bytes:
        # Shed to a plain bytes of the presented data (builtin subclass shedding copies).
        return bytes(self)
