"""Explicit URL intent for lazy datastream consumers."""

from dataclasses import dataclass
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https", "ftp", "file"})


@dataclass(frozen=True, slots=True, init=False)
class DatastreamURL:
    """An explicit network-consent value carrying a URL and optional timeout for lazy consumers, which resolve it through the existing
    fetch/loader machinery; constructing it performs no network I/O."""

    _url: str
    _timeout: float | None

    def __init__(self, url: str, *, timeout: float | None = None) -> None:
        if urlsplit(url).scheme not in _ALLOWED_SCHEMES:
            allowed = ", ".join(sorted(_ALLOWED_SCHEMES))
            raise ValueError(f"DatastreamURL requires one of the allowed URL schemes: {allowed}")
        object.__setattr__(self, "_url", url)
        object.__setattr__(self, "_timeout", timeout)

    @property
    def url(self) -> str:
        return self._url

    @property
    def timeout(self) -> float | None:
        return self._timeout

    def __repr__(self) -> str:
        from ..optimade.resources import redact_optimade_url

        return f"DatastreamURL(url={redact_optimade_url(self._url)!r}, timeout={self._timeout!r})"
