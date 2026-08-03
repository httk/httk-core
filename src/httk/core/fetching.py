"""Fetch URL sources through OPTIMADE or the registered file-loader pipeline."""

from typing import Any
from urllib.parse import urlsplit

from .datastream import TextstreamFileView
from .loading import adapt_result, has_loader_for, load_source, loader_uses_extension
from .optimade.resources import is_optimade_entry_url, optimade_resource_from_url, redact_optimade_url


def fetch(
    url: str,
    *,
    raw: bool = False,
    timeout: float | None = None,
    kind: str | None = None,
    **kwargs: Any,
) -> Any:
    """Fetch a URL as an OPTIMADE entry or a registered file format.

    ``kind="optimade"`` forces OPTIMADE handling and ``kind="load"`` forces
    file-loader handling. With no ``kind``, a loader-claimed extension wins over
    an OPTIMADE-shaped path; a loader-claimed basename is ambiguous and requires
    an explicit ``kind``. ``file://`` URLs are supported in either branch.
    Redirects follow ``urllib`` defaults.
    """

    split = urlsplit(url)
    if not split.scheme:
        raise ValueError(f"fetch requires a URL; use httk.core.load({redact_optimade_url(url)!r}) for local files")
    if kind not in (None, "optimade", "load"):
        raise ValueError("fetch kind must be 'optimade' or 'load'")

    is_entry_url = is_optimade_entry_url(url)
    loader_claimed = has_loader_for(split.path)
    if kind == "optimade" or (kind is None and is_entry_url and not loader_claimed):
        resource = optimade_resource_from_url(url, timeout=timeout)
        return adapt_result({"format": "optimade-entry", "resource": resource}, raw)
    if kind == "load" or (kind is None and loader_claimed and (not is_entry_url or loader_uses_extension(split.path))):
        return load_source(TextstreamFileView(url, kind="url", timeout=timeout), split.path, raw=raw, **kwargs)
    if kind is None and is_entry_url and loader_claimed:
        raise ValueError(
            f"URL {redact_optimade_url(url)!r} is both an OPTIMADE entry and a loader-claimed file; "
            "pass kind='optimade' or kind='load'"
        )
    raise ValueError(
        f"Could not fetch {redact_optimade_url(url)!r}: it is neither an OPTIMADE single-entry URL nor a URL with "
        "a registered loader; "
        "pass kind='optimade' or kind='load' to choose explicitly"
    )
