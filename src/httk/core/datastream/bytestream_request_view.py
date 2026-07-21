import urllib.request
from typing import Any, Self

from ..views import unwrap
from .bytestream_backend import BytestreamBackend
from .bytestream_like import BytestreamLike
from .bytestream_view import BytestreamView


class BytestreamRequestView(BytestreamView, urllib.request.Request):
    """
    A view presenting an underlying data streaming backend via a urllib.request.Request.
    This view is mostly useful for providing a Request to functions that will open it.
    Note: this view is not lazy (it does not fetch); it only mirrors the underlying request/URL.

    Raises TypeError if created with a streaming data source that does not come with a URL.
    """

    _backend: BytestreamBackend

    def __new__(cls, obj: BytestreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        request = getattr(backend, "request", None)
        if request is not None:
            full_url, data, headers = request.full_url, request.data, request.headers
        else:
            url = getattr(backend, "url", None)
            if url is None:
                raise TypeError("This backend cannot be represented as a Request (no underlying URL)")
            full_url, data, headers = url, None, {}
        instance = super().__new__(cls)
        # Request is mutable, so its state is initialized here in __new__ (keeping __init__ a no-op),
        # so that rewrapping an existing view via cls(view) does not re-initialize it.
        urllib.request.Request.__init__(instance, full_url, data=data, headers=headers)
        instance._backend = backend
        return instance

    def __init__(self, obj: BytestreamLike, **hints: Any) -> None:
        pass

    def unwrap(self) -> Any:
        return unwrap(self._backend)
