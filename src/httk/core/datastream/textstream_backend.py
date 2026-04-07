from typing import ClassVar

from ..views import Backend
from .textstream_api import TextstreamAPI


class TextstreamBackend(Backend, TextstreamAPI):
    """
    Abstract base class for all backends of streaming text data.
    """

    backend_classes: ClassVar[list[type["TextstreamBackend"]]] = []
