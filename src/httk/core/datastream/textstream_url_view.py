from typing import Any, Self

from ..views import unwrap
from .textstream_backend import TextstreamBackend
from .textstream_like import TextstreamLike
from .textstream_view import TextstreamView


class TextstreamURLView(TextstreamView, str):
    r"""
    A view presenting an underlying data streaming backend via a URL string.
    This view is mostly useful for providing a URL to functions that will open it.
    Note: this view is not lazy (this is impossible for views inheriting str, since str is immutable).

    Raises TypeError if created with a streaming data source that does not come with a URL.

    :param obj: Text-stream source whose URL should be presented.
    :param \**hints: Backend-selection, consent, encoding, timeout, and compression hints.
    :raises TypeError: If the source has no URL.
    """

    _backend: TextstreamBackend

    def __new__(cls, obj: TextstreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, str) and "kind" not in hints:
            hints["kind"] = "url"
        backend = cls._prepare_backend(obj, hints)
        url = getattr(backend, "url", None)
        if url is None:
            raise TypeError("This backend cannot be represented as a URL (no underlying URL)")
        instance = super().__new__(cls, url)
        instance._backend = backend
        return instance

    def __init__(self, obj: TextstreamLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        """Return the raw representation of the wrapped backend.

        :return: The backend's most raw available representation.
        """
        return unwrap(self._backend)
