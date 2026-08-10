import io
import urllib.parse
import urllib.request
from typing import Any, Self, cast

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon
from .compression import open_compressed, validate_compression
from .network_policy import resolve_timeout


class BytestreamRequest(BytestreamCommon, BytestreamBackend):
    r"""
    Backend for streaming byte data fetched via a urllib.request.Request.
    Response content is transparently decompressed according to the compression hint.

    :param request: Request to execute lazily when data is first read.
    :param \**hints: Backend-selection, timeout, and compression hints.
    :raises ValueError: If the compression hint is unknown.
    """

    _request: urllib.request.Request
    _timeout: float | None
    _compression: str
    _f: io.IOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt a urllib request when it matches this backend.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection and compression hints.
        :return: An initialized backend, or ``None`` when ``obj`` is not accepted.
        """
        if not isinstance(obj, urllib.request.Request):
            return None
        if hints and hints.get("kind", "request") != "request":
            return None
        return cls(obj, **hints)

    def __init__(self, request: urllib.request.Request, **hints: Any) -> None:
        self._request = request
        self._timeout = hints.get("timeout")
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            resp = urllib.request.urlopen(self._request, timeout=resolve_timeout(self._timeout))
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._request.full_url).path
            opened = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if opened is not raw else None
            self._f = opened
        return self._f

    @property
    def name(self) -> str | None:
        """Report that a request backend has no filename."""
        return None

    @property
    def url(self) -> str:
        """Return the request URL."""
        return self._request.full_url

    @property
    def request(self) -> urllib.request.Request:
        """Return the request used to fetch the stream."""
        return self._request

    @property
    def closed(self) -> bool:
        """Report whether the request backend is closed."""
        return self._closed
