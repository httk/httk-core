from typing import Any, ClassVar

from ..views import Backend
from .textstream_api import TextstreamAPI


class TextstreamBackend(Backend["TextstreamBackend"], TextstreamAPI):
    r"""
    Abstract base class for all backends of streaming text data.

    :param backend: Initial backend value accepted by the backend family.
    :param \**hints: Backend-selection hints used by concrete backends.
    """

    backend_classes: ClassVar[list[type[Backend[Any]]]]
