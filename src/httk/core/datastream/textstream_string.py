import io
from typing import Any, Self

from .compression import reject_text_native_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamString(TextstreamCommon, TextstreamBackend):
    r"""
    Backend for streaming text backed by an actual string

    :param content: Text to expose as a stream.
    :param \**hints: Backend-selection and compression hints.
    :raises ValueError: If the compression hint is not a no-op mode for text-native content.
    """

    s: str
    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt string content when it matches this backend.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection hints.
        :return: An initialized backend, or ``None`` when ``obj`` is not accepted.
        """
        if not isinstance(obj, str):
            return None
        if hints and hints.get("kind", "content") != "content":
            return None
        return cls(obj, **hints)

    def __init__(self, content: str, **hints: Any) -> None:
        reject_text_native_compression(hints.get("compression"))
        self.s = content
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            self._f = io.StringIO(self.s)
        return self._f

    @property
    def name(self) -> str | None:
        """Report that an in-memory stream has no source name."""
        return None

    @property
    def closed(self) -> bool:
        """Report whether the in-memory stream is closed."""
        return self._closed
