from typing import Any, Self

from ..views import unwrap
from .textstream_backend import TextstreamBackend
from .textstream_like import TextstreamLike
from .textstream_view import TextstreamView


class TextstreamFilenameView(TextstreamView, str):
    """
    A view presenting an underlying data streaming backend via a filename.
    This view is probably mostly useful for providing filenames to functions that will open them.
    Note: this view is not lazy (this is impossible for views inherting str, since str is immutable)

    Raises TypeError if created with a streaming data source that does not have a name.
    """

    _backend: TextstreamBackend

    def __new__(cls, obj: TextstreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        if backend.name is None:
            raise TypeError("This backend cannot be represented as a filename (no underlying filename)")
        instance = super().__new__(cls, backend.name)
        instance._backend = backend
        return instance

    def __init__(self, obj: TextstreamLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        return unwrap(self._backend)
