import io
from typing import Any, Self

from .compression import reject_text_native_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamFile(TextstreamCommon, TextstreamBackend):
    r"""
    Backend for file-based (io.TextIOBase-conforming) streaming text data

    :param obj: Open text stream to adopt and close with this backend.
    :param \**hints: Backend-selection and compression hints.
    :raises ValueError: If the compression hint is not a no-op mode for text-native content.
    """

    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt a text stream when it matches this backend.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection hints.
        :return: An initialized backend, or ``None`` when ``obj`` is not accepted.
        """
        if not isinstance(obj, io.TextIOBase):
            return None
        if hints and hints.get("kind", "file") != "file":
            return None
        return cls(obj, **hints)

    def __init__(self, obj: io.TextIOBase, **hints: Any) -> None:
        reject_text_native_compression(hints.get("compression"))
        self._f = obj
        # Compression cannot layer under an already-decoded text stream, so nothing to chain-close.
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._f is None or self._f.closed:
            raise ValueError("I/O operation on closed stream")
        return self._f

    @property
    def name(self) -> str | None:
        """Return the adopted stream's name when it provides one."""
        self._ensure_f()
        return getattr(self._f, "name", None)

    @property
    def closed(self) -> bool:
        """Report whether the adopted stream is closed."""
        return self._f is None or self._f.closed
