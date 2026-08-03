import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon
from .compression import open_compressed, validate_compression
from .network_policy import NETWORK_SCHEMES, require_network_consent, resolve_timeout

_URL_SCHEMES = ("http", "https", "ftp", "file")


class BytestreamURL(BytestreamCommon, BytestreamBackend):
    """
    Backend for streaming byte data fetched from a URL string.
    A bare string is interpreted as a URL when its scheme is one of http, https, ftp, or file,
    or when an explicit kind="url" hint is given.
    """

    _url: str
    _timeout: float | None
    _needs_consent: bool
    _compression: str
    _f: io.IOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, url: str, **hints: Any) -> Any:
        if not isinstance(url, str):
            return None
        kind = hints.get("kind")
        if kind == "url":
            if not urllib.parse.urlsplit(url).scheme:
                return None
            return super().__new__(cls)
        if kind is None and urllib.parse.urlsplit(url).scheme in _URL_SCHEMES:
            return super().__new__(cls)
        return None

    def __init__(self, url: str, **hints: Any) -> None:
        self._url = url
        self._timeout = hints.get("timeout")
        self._needs_consent = hints.get("kind") != "url" and urllib.parse.urlsplit(url).scheme in NETWORK_SCHEMES
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            if self._needs_consent:
                require_network_consent(self._url)
            resp = urllib.request.urlopen(self._url, timeout=resolve_timeout(self._timeout))
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._url).path
            opened = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if opened is not raw else None
            self._f = opened
        return self._f

    @property
    def name(self) -> str | None:
        return None

    @property
    def url(self) -> str:
        return self._url

    @property
    def closed(self) -> bool:
        return self._closed
