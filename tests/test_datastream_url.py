"""Tests for explicit lazy datastream URL intent."""

import urllib.request
from dataclasses import FrozenInstanceError

import pytest

from httk.core import DatastreamURL


def test_construction_does_not_open_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: calls.append((args, kwargs)))

    token = DatastreamURL("https://example.test/data", timeout=4.5)

    assert token.url == "https://example.test/data"
    assert token.timeout == 4.5
    assert calls == []


@pytest.mark.parametrize("scheme", ["http", "https", "ftp", "file"])
def test_allowed_schemes(scheme: str) -> None:
    assert DatastreamURL(f"{scheme}://example.test/data").url.startswith(f"{scheme}:")


@pytest.mark.parametrize("url", ["", "mailto:user@example.test", "data:text/plain,body", "data"])
def test_rejects_disallowed_or_schemeless_urls(url: str) -> None:
    with pytest.raises(ValueError, match="allowed URL schemes") as excinfo:
        DatastreamURL(url)
    assert all(scheme in str(excinfo.value) for scheme in ("http", "https", "ftp", "file"))


def test_repr_redacts_credentials_and_value_is_immutable() -> None:
    token = DatastreamURL("https://user:pass@example.test/data?keep=yes#access_token=SECRET")

    assert "SECRET" not in repr(token)
    assert "access_token" not in repr(token)
    with pytest.raises(FrozenInstanceError):
        token._url = "https://example.test/other"  # type: ignore[misc]


def test_equality_and_hash_use_url_and_timeout() -> None:
    first = DatastreamURL("https://example.test/data", timeout=2.0)

    assert first == DatastreamURL("https://example.test/data", timeout=2.0)
    assert first != DatastreamURL("https://example.test/data", timeout=3.0)
    assert hash(first) == hash(DatastreamURL("https://example.test/data", timeout=2.0))
