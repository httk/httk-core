from typing import ClassVar, Self

from ..views import View
from .bytestream_backend import BytestreamBackend


class BytestreamView(View[BytestreamBackend]):
    """
    Abstract base class for all views of streaming byte data.

    Views retain the backend and expose it through a byte-stream interface.
    """

    _backend_base_cls: ClassVar[type[BytestreamBackend]] = BytestreamBackend  # type: ignore[type-abstract]
    _view_base_cls: ClassVar[type[Self]]

    def __repr__(self) -> str:
        backend = getattr(self, "_backend", None)
        return f"{type(self).__name__}(backend={type(backend).__name__})"


BytestreamView._view_base_cls = BytestreamView
