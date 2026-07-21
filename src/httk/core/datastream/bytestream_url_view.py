from typing import Any, Self

from ..views import unwrap
from .bytestream_backend import BytestreamBackend
from .bytestream_like import BytestreamLike
from .bytestream_view import BytestreamView


class BytestreamURLView(BytestreamView, str):
    """
    A view presenting an underlying data streaming backend via a URL string.
    This view is mostly useful for providing a URL to functions that will open it.
    Note: this view is not lazy (this is impossible for views inheriting str, since str is immutable).

    Raises TypeError if created with a streaming data source that does not come with a URL.
    """

    _backend: BytestreamBackend

    def __new__(cls, obj: BytestreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        url = getattr(backend, "url", None)
        if url is None:
            raise TypeError("This backend cannot be represented as a URL (no underlying URL)")
        instance = super().__new__(cls, url)
        instance._backend = backend
        return instance

    def __init__(self, obj: BytestreamLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        return unwrap(self._backend)
