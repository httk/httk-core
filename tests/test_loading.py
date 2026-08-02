"""Tests for :func:`httk.core.load` dispatch (extensions + basenames + compression)."""

from collections.abc import Iterator
from typing import Any

import pytest

from httk.core import load
from httk.core.register import (
    format_adapters,
    known_extensions,
    known_filenames,
    known_format_adapters,
    loader_filenames,
    loaders,
    register_format_adapter,
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


def _synthetic_loader(filename: str, **kwargs: Any) -> dict[str, Any]:
    return {"format": "synthetic", "filename": filename, "kwargs": kwargs}


def _unadapted_mapping_loader(filename: str, **kwargs: Any) -> dict[str, Any]:
    return {"format": "no-adapter", "filename": filename, "kwargs": kwargs}


def _scalar_loader(filename: str, **kwargs: Any) -> int:
    return 42


def _synthetic_adapter(payload: dict[str, Any]) -> tuple[str, str]:
    return ("adapted", payload["filename"])


@pytest.fixture
def _register_format_stubs() -> Iterator[None]:
    loaders.register(key=".synthetic", handler=_synthetic_loader, name="synthetic-loader")
    loaders.register(key=".no-adapter", handler=_unadapted_mapping_loader, name="unadapted-loader")
    loaders.register(key=".scalar", handler=_scalar_loader, name="scalar-loader")
    register_format_adapter(
        name="synthetic-adapter",
        adapter=_synthetic_adapter,
        formats=("synthetic",),
    )
    try:
        yield
    finally:
        for key in (".synthetic", ".no-adapter", ".scalar"):
            loaders._by_key.pop(key, None)
        format_adapters._by_key.pop("synthetic", None)


def test_format_adapter_registry_and_load_dispatch(_register_format_stubs: None) -> None:
    assert known_format_adapters()["synthetic"] == "synthetic-adapter"
    assert load("sample.synthetic") == ("adapted", "sample.synthetic")


def test_raw_bypasses_format_adapter(_register_format_stubs: None) -> None:
    result = load("sample.synthetic", raw=True)
    assert result["format"] == "synthetic"


def test_unknown_format_mapping_passes_through(_register_format_stubs: None) -> None:
    result = load("sample.no-adapter")
    assert result["format"] == "no-adapter"


def test_non_mapping_loader_result_passes_through(_register_format_stubs: None) -> None:
    assert load("sample.scalar") == 42


def test_duplicate_format_adapter_names_both_registrants() -> None:
    register_format_adapter(name="first-adapter", adapter=lambda value: value, formats=("duplicate",))
    try:
        with pytest.raises(ValueError, match="first-adapter.*second-adapter"):
            register_format_adapter(name="second-adapter", adapter=lambda value: value, formats=("duplicate",))
    finally:
        format_adapters._by_key.pop("duplicate", None)


def test_identical_format_adapter_registration_is_idempotent() -> None:
    def adapter(value: Any) -> Any:
        return value

    register_format_adapter(name="repeatable", adapter=adapter, formats=("repeatable",))
    register_format_adapter(name="repeatable", adapter=adapter, formats=("repeatable",))
    try:
        assert known_format_adapters()["repeatable"] == "repeatable"
    finally:
        format_adapters._by_key.pop("repeatable", None)


@pytest.mark.parametrize("formats", ["cif", ("",), (1,), (None,)])
def test_format_adapter_formats_must_be_nonempty_string_tags(formats: Any) -> None:
    with pytest.raises(ValueError, match="format"):
        register_format_adapter(name="invalid-formats", adapter=lambda value: value, formats=formats)
