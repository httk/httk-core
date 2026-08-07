from typing import Any, ClassVar

from ..views import Backend
from .bytestream_api import BytestreamAPI


class BytestreamBackend(Backend["BytestreamBackend"], BytestreamAPI):
    r"""
    Abstract base class for all backends of streaming byte data.

    :param backend: Initial backend value accepted by the backend family.
    :param \**hints: Backend-selection hints used by concrete backends.
    """

    backend_classes: ClassVar[list[type[Backend[Any]]]]
