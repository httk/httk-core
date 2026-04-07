from typing import Any, ClassVar

from ..views import View
from .textstream_backend import TextstreamBackend


class TextstreamView(View[TextstreamBackend]):
    """
    Abstract base class for all views of streaming text data.
    """

    _backend_base_cls: ClassVar[Any] = TextstreamBackend
    _view_base_cls: ClassVar[Any]


TextstreamView._view_base_cls = TextstreamView
