import io
import urllib.request
from email.message import Message
from typing import Any

import pytest

from httk.core import DatasetLoader
from httk.core.datastream import (
    BytestreamBackend,
    BytestreamBytesView,
    BytestreamFileView,
    BytestreamURLView,
    TextstreamBackend,
    TextstreamFileView,
    TextstreamStringView,
    TextstreamURLView,
    network_policy,
)


class _FakeResponse(io.BytesIO):
    headers = Message()


def _urlopen_fake(calls: list[tuple[Any, float | None]], body: bytes = b"body"):
    def fake(url: Any, *, timeout: float | None) -> _FakeResponse:
        calls.append((url, timeout))
        return _FakeResponse(body)

    return fake


def test_bare_network_strings_require_consent_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))

    text = TextstreamFileView("https://example.test/data")
    binary = BytestreamFileView("https://example.test/data")
    assert calls == []

    for stream in (text, binary):
        with pytest.raises(PermissionError) as error:
            stream.read()
        assert "https://example.test/data" in str(error.value)
        assert "httk.core.fetch" in str(error.value)
        assert 'kind="url"' in str(error.value)
    assert calls == []


def test_explicit_url_views_and_requests_open(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))
    url = "https://example.test/data"

    assert TextstreamFileView(url, kind="url").read() == "body"
    assert BytestreamFileView(url, kind="url").read() == b"body"
    assert TextstreamFileView(TextstreamURLView(url)).read() == "body"
    assert BytestreamFileView(BytestreamURLView(url)).read() == b"body"
    assert TextstreamFileView(urllib.request.Request(url)).read() == "body"
    assert BytestreamFileView(urllib.request.Request(url)).read() == b"body"
    assert len(calls) == 6


def test_request_backend_receives_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))
    url = "https://example.test/request"

    TextstreamFileView(urllib.request.Request(url), timeout=8.5).read()
    BytestreamFileView(urllib.request.Request(url), timeout=9.5).read()

    assert [timeout for _, timeout in calls] == [8.5, 9.5]


def test_timeout_is_resolved_when_explicit_stream_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))
    url = "https://example.test/open-time"

    gated = TextstreamFileView(url)
    explicit = TextstreamFileView(url, kind="url")
    monkeypatch.setattr(network_policy, "DEFAULT_NETWORK_TIMEOUT", 12.5)

    explicit.read()

    assert calls == [(url, 12.5)]
    with pytest.raises(PermissionError):
        gated.read()
    assert calls == [(url, 12.5)]


def test_eager_string_and_bytes_views_gate_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))
    url = "https://example.test/eager"

    with pytest.raises(PermissionError):
        TextstreamStringView(url)
    with pytest.raises(PermissionError):
        BytestreamBytesView(url)
    assert calls == []


def test_view_adoption_preserves_gated_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))
    url = "https://example.test/adopt"

    text_backend = TextstreamBackend.create(url)
    text_view = TextstreamFileView(TextstreamFileView(text_backend))
    bytes_backend = BytestreamBackend.create(url)
    bytes_view = BytestreamFileView(BytestreamFileView(bytes_backend))

    with pytest.raises(PermissionError):
        text_view.read()
    with pytest.raises(PermissionError):
        bytes_view.read()
    assert calls == []


def test_bare_file_url_is_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))

    assert TextstreamFileView("file:///tmp/local.json").read() == "body"
    assert calls == [("file:///tmp/local.json", 30.0)]


def test_network_timeout_default_hint_and_module_override(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))

    TextstreamFileView("https://example.test/default", kind="url").read()
    BytestreamFileView("https://example.test/hint", kind="url", timeout=7.5).read()
    monkeypatch.setattr(network_policy, "DEFAULT_NETWORK_TIMEOUT", 4.25)
    TextstreamFileView("https://example.test/override", kind="url").read()

    assert [timeout for _, timeout in calls] == [30.0, 7.5, 4.25]


def test_dataloader_forwards_url_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls, b"{}"))

    assert DatasetLoader("network_policy_loader", "https://example.test/data", kind="url").data == {}
    assert len(calls) == 1


def test_dataloader_bare_url_requires_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_fake(calls))

    loader = DatasetLoader("network_policy_bare_loader", "https://example.test/data")
    with pytest.raises(PermissionError):
        _ = loader.data
    assert calls == []


def test_network_consent_error_redacts_credentials() -> None:
    url = "https://example.test/data?access_token=SECRET&keep=yes"

    with pytest.raises(PermissionError) as error:
        TextstreamFileView(url).read()

    message = str(error.value)
    assert "SECRET" not in message
    assert "https://example.test/data?keep=yes" in message
