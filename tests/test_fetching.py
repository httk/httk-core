"""Focused URL dispatch tests for :func:`httk.core.fetch`."""

import io
import json
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from httk.core import fetch, is_optimade_entry_url
from httk.core.register import format_adapters, loader_filenames, loaders, register_format_adapter


class _Response(io.BytesIO):
    headers = Message()


_ENTRY = json.dumps({"data": {"id": "material-1", "type": "structures", "attributes": {}}})
_INFO = json.dumps({"data": {"description": "Structure entries", "properties": {}}})


def _urlopen_responses(calls: list[tuple[str, float | None]], responses: dict[str, str]):
    def fake(url: str, *, timeout: float | None) -> _Response:
        calls.append((url, timeout))
        return _Response(responses[url].encode())

    return fake


def test_fetch_optimade_raw_payload_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://example.test/v1/structures/material-1"
    info_url = "https://example.test/v1/info/structures"
    calls: list[tuple[str, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_responses(calls, {url: _ENTRY, info_url: _INFO}))

    adapter = format_adapters._by_key.pop("optimade-entry", None)
    try:
        payload = fetch(url, timeout=9.0)
        raw_payload = fetch(url, raw=True, timeout=9.0)
    finally:
        if adapter is not None:
            format_adapters._by_key["optimade-entry"] = adapter

    assert payload["format"] == "optimade-entry"
    assert payload["resource"].id == "material-1"
    assert raw_payload["format"] == "optimade-entry"
    assert calls == [(url, 9.0), (info_url, 9.0), (url, 9.0), (info_url, 9.0)]


def test_fetch_optimade_uses_registered_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://example.test/v1/structures/material-1"
    info_url = "https://example.test/v1/info/structures"
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_responses([], {url: _ENTRY, info_url: _INFO}))
    adapter = format_adapters._by_key.pop("optimade-entry", None)
    try:
        register_format_adapter(
            name="test-optimade", adapter=lambda payload: payload["resource"].id, formats=("optimade-entry",)
        )
        assert fetch(url) == "material-1"
    finally:
        format_adapters._by_key.pop("optimade-entry", None)
        if adapter is not None:
            format_adapters._by_key["optimade-entry"] = adapter


def test_fetch_forced_optimade_accepts_hyphenated_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://example.test/v1/renamed-files/material-1"
    info_url = "https://example.test/v1/info/renamed-files"
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_responses([], {url: _ENTRY, info_url: _INFO}))

    assert fetch(url, kind="optimade", raw=True)["resource"].schema.entry_type == "renamed-files"


def _stream_loader(source: Any, **kwargs: Any) -> dict[str, Any]:
    assert not isinstance(source, str)
    return {"text": source.read(), "kwargs": kwargs}


def _identity_loader(source: Any, **kwargs: Any) -> dict[str, Any]:
    assert not isinstance(source, str)
    return {"source": source, "kwargs": kwargs}


def test_fetch_file_url_uses_stream_loader(tmp_path: Path) -> None:
    path = tmp_path / "x.stub"
    path.write_text("stream body", encoding="utf-8")
    loaders.register(key=".stub", handler=_stream_loader, name="stream-loader")
    try:
        assert is_optimade_entry_url(path.as_uri())
        assert fetch(path.as_uri()) == {"text": "stream body", "kwargs": {}}
    finally:
        loaders._by_key.pop(".stub", None)


def test_fetch_prefers_loader_extension_over_optimade_shape() -> None:
    url = "https://example.test/v1/structures/material.stub"
    loaders.register(key=".stub", handler=_identity_loader, name="stream-loader")
    try:
        # The loader branch is selected without opening its lazy stream.
        assert fetch(url)["kwargs"] == {}
    finally:
        loaders._by_key.pop(".stub", None)


def test_fetch_rejects_ambiguous_loader_basename() -> None:
    loader_filenames.register(key="material", handler=_stream_loader, name="stream-loader")
    try:
        with pytest.raises(ValueError, match="kind='optimade'.*kind='load'"):
            fetch("https://example.test/v1/structures/material")
    finally:
        loader_filenames._by_key.pop("material", None)


def test_fetch_rejects_scheme_less_and_unknown_url() -> None:
    with pytest.raises(ValueError, match="httk\\.core\\.load"):
        fetch("local.stub")
    with pytest.raises(ValueError, match="neither an OPTIMADE.*registered loader"):
        fetch("https://example.test/unknown")


def test_fetch_errors_redact_credentials() -> None:
    url = "https://example.test/unknown?keep=yes#access_token=SECRET"
    with pytest.raises(ValueError) as excinfo:
        fetch(url)

    message = str(excinfo.value)
    assert "https://example.test/unknown?keep=yes" in message
    assert "SECRET" not in message
    assert "#" not in message
