"""Policy and timeout helpers for network-backed datastream opens."""

DEFAULT_NETWORK_TIMEOUT: float | None = 30.0
"""Default timeout for each network open; read freshly for every open, or ``None`` to disable."""

NETWORK_SCHEMES = frozenset({"http", "https", "ftp"})
"""Schemes treated as network access; ``file`` is local I/O and deliberately absent."""


def require_network_consent(url: str) -> None:
    """Future seam for an opt-in network policy; currently all implicit access is refused."""
    from ..optimade.resources import redact_optimade_url

    redacted_url = redact_optimade_url(url)
    raise PermissionError(
        f"Implicit network access from bare string {redacted_url!r} is not permitted; use "
        "httk.core.fetch(url), construct TextstreamURLView or BytestreamURLView, "
        'pass kind="url", or pass a urllib.request.Request.'
    )


def resolve_timeout(hint: float | None) -> float | None:
    """Return an explicit timeout or the current module default."""
    return hint if hint is not None else DEFAULT_NETWORK_TIMEOUT
