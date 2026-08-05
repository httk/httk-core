from typing import Any, Self

from ..views import unwrap
from .bytestream_backend import BytestreamBackend
from .bytestream_like import BytestreamLike
from .bytestream_view import BytestreamView


class BytestreamFilenameView(BytestreamView, str):
    """
    A view presenting an underlying data streaming backend via a filename.
    This view is mostly useful for providing filenames to functions that will open them.
    Note: this view is not lazy (this is impossible for views inheriting str, since str is immutable).

    Raises TypeError if created with a streaming data source that does not come with a name.
    """

    _backend: BytestreamBackend

    def __new__(cls, obj: BytestreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        if backend.name is None:
            raise TypeError("This backend cannot be represented as a filename (no underlying filename)")
        instance = super().__new__(cls, backend.name)
        instance._backend = backend
        return instance

    def __init__(self, obj: BytestreamLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        return unwrap(self._backend)

    def unview(self) -> str:
        # Shed to a plain str of the presented filename.
        return str(self)
