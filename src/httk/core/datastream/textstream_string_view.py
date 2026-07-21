from typing import Any, Self

from ..views import unwrap
from .textstream_backend import TextstreamBackend
from .textstream_like import TextstreamLike
from .textstream_view import TextstreamView


class TextstreamStringView(TextstreamView, str):
    """
    A view presenting an underlying data streaming as a string.
    This view can be used both to pass a string in place of streaming data, and for reading streaming data into a string.
    Note: this view is not lazy (this is impossible for views inherting str, since str is immutable), hence all the streaming data
    is read immedately upon creating this view.
    """

    _backend: TextstreamBackend

    def __new__(cls, obj: TextstreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        instance = super().__new__(cls, backend.read())
        instance._backend = backend
        return instance

    def __init__(self, obj: TextstreamLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        return unwrap(self._backend)
