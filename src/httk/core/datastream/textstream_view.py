from typing import ClassVar, Self

from ..views import View
from .textstream_backend import TextstreamBackend


class TextstreamView(View[TextstreamBackend]):
    """
    Abstract base class for all views of streaming text data.
    """

    _backend_base_cls: ClassVar[type[TextstreamBackend]] = TextstreamBackend  # type: ignore[type-abstract]
    _view_base_cls: ClassVar[type[Self]]


TextstreamView._view_base_cls = TextstreamView
