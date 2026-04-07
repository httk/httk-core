from typing import ClassVar, Self

from ..views import View
from .bytestream_backend import BytestreamBackend


class BytestreamView(View[BytestreamBackend]):
    """
    Abstract base class for all views of streaming byte data.
    """

    _backend_base_cls: ClassVar[type[BytestreamBackend]] = BytestreamBackend  # type: ignore[type-abstract]
    _view_base_cls: ClassVar[type[Self]]


BytestreamView._view_base_cls = BytestreamView
