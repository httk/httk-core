"""Fetch URL sources through OPTIMADE or the registered file-reader pipeline."""

from typing import Any
from urllib.parse import urlsplit

from .datastream import TextstreamFileView
from .loading import adapt_result, has_reader_for, load_source, reader_uses_extension
from .optimade.resources import is_optimade_entry_url, optimade_resource_from_url, redact_optimade_url


def fetch(
    url: str,
    *,
    raw: bool = False,
    timeout: float | None = None,
    kind: str | None = None,
    **kwargs: Any,
) -> Any:
    r"""Fetch a URL as an OPTIMADE entry or a registered file format.

    ``kind="optimade"`` forces OPTIMADE handling and ``kind="load"`` forces
    file-reader handling. With no ``kind``, a reader-claimed extension wins over
    an OPTIMADE-shaped path; a reader-claimed basename is ambiguous and requires
    an explicit ``kind``. ``file://`` URLs are supported in either branch.
    Redirects follow ``urllib`` defaults.

    As the explicit URL entry point, this function supplies the same network
    consent represented by :class:`~httk.core.DatastreamURL`; it does not use
    implicit bare-string network access for the reader branch.

    :param url: URL to fetch.
    :param raw: Whether to return a neutral payload without a format adapter.
    :param timeout: Optional timeout for URL-backed reader access or OPTIMADE requests.
    :param kind: Optional branch selector: ``"optimade"`` or ``"load"``.
    :param \**kwargs: Additional options passed to the file reader.
    :return: The fetched OPTIMADE resource or loaded file value.
    :raises ValueError: If the URL, ``kind``, or automatic branch selection is invalid.
    """

    split = urlsplit(url)
    if not split.scheme:
        raise ValueError(f"fetch requires a URL; use httk.core.load({redact_optimade_url(url)!r}) for local files")
    if kind not in (None, "optimade", "load"):
        raise ValueError("fetch kind must be 'optimade' or 'load'")

    is_entry_url = is_optimade_entry_url(url)
    reader_claimed = has_reader_for(split.path)
    if kind == "optimade" or (kind is None and is_entry_url and not reader_claimed):
        resource = optimade_resource_from_url(url, timeout=timeout)
        return adapt_result({"format": "optimade-entry", "resource": resource}, raw)
    if kind == "load" or (kind is None and reader_claimed and (not is_entry_url or reader_uses_extension(split.path))):
        return load_source(TextstreamFileView(url, kind="url", timeout=timeout), split.path, raw=raw, **kwargs)
    if kind is None and is_entry_url and reader_claimed:
        raise ValueError(
            f"URL {redact_optimade_url(url)!r} is both an OPTIMADE entry and a reader-claimed file; "
            "pass kind='optimade' or kind='load'"
        )
    raise ValueError(
        f"Could not fetch {redact_optimade_url(url)!r}: it is neither an OPTIMADE single-entry URL nor a URL with "
        "a registered reader; "
        "pass kind='optimade' or kind='load' to choose explicitly"
    )
