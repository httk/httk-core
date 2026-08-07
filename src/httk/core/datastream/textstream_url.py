import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .compression import open_compressed, validate_compression
from .network_policy import NETWORK_SCHEMES, require_network_consent, resolve_timeout
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon

_URL_SCHEMES = ("http", "https", "ftp", "file")


class TextstreamURL(TextstreamCommon, TextstreamBackend):
    r"""
    Backend for streaming text fetched from a URL string.
    A bare string is interpreted as a URL when its scheme is one of http, https, ftp, or file,
    or when an explicit kind="url" hint is given.
    Network access from an implicit bare network URL requires explicit consent before opening;
    URL views and ``kind="url"`` provide that consent. Content is transparently decompressed
    before text decoding.

    :param url: URL to fetch lazily when text is first read.
    :param \**hints: Backend-selection, consent, encoding, timeout, and compression hints.
    :raises ValueError: If the compression hint is unknown.
    """

    _url: str
    _timeout: float | None
    _needs_consent: bool
    _encoding: str | None
    _compression: str
    _f: io.TextIOBase | None
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
        self._encoding = hints.get("encoding")
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            if self._needs_consent:
                require_network_consent(self._url)
            resp = urllib.request.urlopen(self._url, timeout=resolve_timeout(self._timeout))
            encoding = self._encoding or resp.headers.get_content_charset() or "utf-8"
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._url).path
            decompressed = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if decompressed is not raw else None
            self._f = io.TextIOWrapper(cast(io.BufferedReader, decompressed), encoding=encoding)
        return self._f

    @property
    def name(self) -> str | None:
        """Report that a URL backend has no filename."""
        return None

    @property
    def url(self) -> str:
        """Return the source URL."""
        return self._url

    @property
    def closed(self) -> bool:
        """Report whether the URL backend is closed."""
        return self._closed
