"""Tests for :func:`httk.core.load` dispatch (extensions + basenames + compression)."""

from collections.abc import Iterator
from typing import Any

import pytest

from httk.core import load
from httk.core.register import (
    known_extensions,
    known_filenames,
    loader_filenames,
    loaders,
)


def _stub_loader(filename: str, **kwargs: Any) -> dict[str, Any]:
    """A loader that just echoes the filename it received."""
    return {"filename": filename, "kwargs": kwargs}


@pytest.fixture
def _register_stub() -> Iterator[None]:
    loaders.register(key=".stub", handler=_stub_loader, name="stub")
    loader_filenames.register(key="contcar", handler=_stub_loader, name="stub")
    try:
        yield
    finally:
        loaders._by_key.pop(".stub", None)
        loader_filenames._by_key.pop("contcar", None)


def test_known_registries_separate(_register_stub: None) -> None:
    assert ".stub" in known_extensions()
    assert "contcar" in known_filenames()
    # A basename key never leaks into the extension registry (separate namespaces).
    assert "contcar" not in known_extensions()


def test_dispatch_by_basename_passes_original_path(_register_stub: None) -> None:
    result = load("/some/dir/CONTCAR")
    assert result["filename"] == "/some/dir/CONTCAR"


def test_dispatch_by_basename_strips_compression(_register_stub: None) -> None:
    # A ".bz2" suffix is stripped to reveal the CONTCAR basename, but the loader
    # still receives the original, still-compressed path.
    result = load("/some/dir/CONTCAR.bz2")
    assert result["filename"] == "/some/dir/CONTCAR.bz2"


def test_dispatch_by_extension_over_compression(_register_stub: None) -> None:
    result = load("/some/dir/data.stub.gz")
    assert result["filename"] == "/some/dir/data.stub.gz"


def test_case_insensitive_basename(_register_stub: None) -> None:
    assert load("contcar")["filename"] == "contcar"


def test_unknown_raises_clear_error(_register_stub: None) -> None:
    with pytest.raises(ValueError) as excinfo:
        load("/tmp/mystery.xyz")
    message = str(excinfo.value)
    assert "mystery.xyz" in message
    assert "Known extensions" in message
    assert "known filenames" in message
