from typing import Any, Self

from ..views import unwrap
from .textstream_backend import TextstreamBackend
from .textstream_like import TextstreamLike
from .textstream_view import TextstreamView


class TextstreamStringView(TextstreamView, str):
    r"""
    A view presenting an underlying data streaming as a string.
    This view can be used both to pass a string in place of streaming data, and for reading streaming data into a string.
    Note: this view is not lazy (this is impossible for views inherting str, since str is immutable), hence all the streaming data
    is read immedately upon creating this view.

    :param obj: Text-stream source to present or consume.
    :param \**hints: Backend-selection and compression hints.
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
        """Return the raw representation of the wrapped backend.

        :return: The backend's most raw available representation.
        """
        return unwrap(self._backend)

    def unview(self) -> str:
        """Return the presented text as a plain string.

        :return: A plain string containing the presented text.
        """
        # Shed to a plain str of the presented data (builtin subclass shedding copies).
        return str(self)
