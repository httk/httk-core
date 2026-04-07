from typing import Any, ClassVar

from ..views import Backend
from .bytestream_api import BytestreamAPI


class BytestreamBackend(Backend["BytestreamBackend"], BytestreamAPI):
    """
    Abstract base class for all backends of streaming byte data.
    """

    backend_classes: ClassVar[list[type["Backend[Any]"]]]
