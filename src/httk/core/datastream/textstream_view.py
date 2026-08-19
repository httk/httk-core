from typing import ClassVar, Self

from ..views import View
from .textstream_backend import TextstreamBackend


class TextstreamView(View[TextstreamBackend]):
    """
    Abstract base class for all views of streaming text data.

    Views retain the backend and expose it through a text-stream interface.
    """

    _backend_base_cls: ClassVar[type[TextstreamBackend]] = TextstreamBackend  # type: ignore[type-abstract]
    _view_base_cls: ClassVar[type[Self]]

    def __repr__(self) -> str:
        backend = getattr(self, "_backend", None)
        return f"{type(self).__name__}(backend={type(backend).__name__})"


TextstreamView._view_base_cls = TextstreamView
