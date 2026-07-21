import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamURL(TextstreamCommon, TextstreamBackend):
    """
    Backend for streaming text fetched from a URL string.
    A URL string is only interpreted as such given an explicit kind="url" hint.
    """

    _url: str
    _timeout: float | None
    _encoding: str | None
    _f: io.TextIOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, url: str, **hints: Any) -> Any:
        if not isinstance(url, str):
            return None
        if hints.get("kind") != "url":
            return None
        if not urllib.parse.urlsplit(url).scheme:
            return None
        return super().__new__(cls)

    def __init__(self, url: str, **hints: Any) -> None:
        self._url = url
        self._timeout = hints.get("timeout")
        self._encoding = hints.get("encoding")
        self._f = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            if self._timeout is None:
                resp = urllib.request.urlopen(self._url)
            else:
                resp = urllib.request.urlopen(self._url, timeout=self._timeout)
            encoding = self._encoding or resp.headers.get_content_charset() or "utf-8"
            self._f = io.TextIOWrapper(cast(io.BufferedReader, resp), encoding=encoding)
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
