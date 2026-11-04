"""Views pickle by reconstructing from their backend (parallel bulk ingest needs it)."""

import importlib
import io
import pickle
import pkgutil
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import httk.core
from httk.core import View
from httk.core.datastream.bytestream_bytes_view import BytestreamBytesView
from httk.core.datastream.bytestream_file_view import BytestreamFileView
from httk.core.datastream.bytestream_filename_view import BytestreamFilenameView
from httk.core.datastream.bytestream_request_view import BytestreamRequestView
from httk.core.datastream.bytestream_url_view import BytestreamURLView
from httk.core.datastream.textstream_file_view import TextstreamFileView
from httk.core.datastream.textstream_filename_view import TextstreamFilenameView
from httk.core.datastream.textstream_request_view import TextstreamRequestView
from httk.core.datastream.textstream_string import TextstreamString
from httk.core.datastream.textstream_string_view import TextstreamStringView
from httk.core.datastream.textstream_url_view import TextstreamURLView
from httk.core.vectors.vector_frac_view import VectorFracView
from httk.core.vectors.vector_native_view import VectorNativeView
from httk.core.vectors.vector_numpy_view import VectorNumpyView
from httk.core.vectors.vector_surd_view import VectorSurdView

DATA = [[1, 2], [3, 4]]
URL = "https://example.org/data.cif"

VECTOR_VIEWS = [VectorFracView, VectorSurdView, VectorNativeView, VectorNumpyView]


@pytest.mark.parametrize("cls", VECTOR_VIEWS, ids=lambda cls: cls.__name__)
def test_vector_view_round_trips(cls: type[Any]) -> None:
    view = cls(DATA)
    restored = pickle.loads(pickle.dumps(view))
    assert type(restored) is cls
    assert repr(restored.unview()) == repr(view.unview())
    assert restored._backend.fractions == view._backend.fractions


def test_backend_less_frac_view_round_trips_from_its_value() -> None:
    derived = VectorFracView(DATA) * 2
    assert getattr(derived, "_backend", None) is None
    restored = pickle.loads(pickle.dumps(derived))
    assert type(restored) is VectorFracView
    assert restored == derived


def _text_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.txt"
    path.write_text("hello\n")
    return path


# Designed behaviour: in-memory, filename, URL and request sources round-trip; eagerly read
# string/bytes views carry their presented value; open OS file handles raise TypeError.
ROUND_TRIPS: dict[str, Callable[[Path], Any]] = {
    "TextstreamStringView": lambda tmp: TextstreamStringView(TextstreamString("hello")),
    "TextstreamStringView-consumed": lambda tmp: TextstreamStringView(io.StringIO("hello")),
    "BytestreamBytesView": lambda tmp: BytestreamBytesView(b"hello"),
    "BytestreamBytesView-consumed": lambda tmp: BytestreamBytesView(io.BytesIO(b"hello")),
    "TextstreamFileView-memory": lambda tmp: TextstreamFileView(io.StringIO("hello")),
    "BytestreamFileView-memory": lambda tmp: BytestreamFileView(io.BytesIO(b"hello")),
    "TextstreamFilenameView": lambda tmp: TextstreamFilenameView(str(_text_file(tmp))),
    "BytestreamFilenameView": lambda tmp: BytestreamFilenameView(str(_text_file(tmp))),
    "TextstreamURLView": lambda tmp: TextstreamURLView(URL),
    "BytestreamURLView": lambda tmp: BytestreamURLView(URL),
    "TextstreamRequestView": lambda tmp: TextstreamRequestView(urllib.request.Request(URL)),
    "BytestreamRequestView": lambda tmp: BytestreamRequestView(urllib.request.Request(URL)),
}


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_datastream_view_round_trips(name: str, tmp_path: Path) -> None:
    view = ROUND_TRIPS[name](tmp_path)
    restored = pickle.loads(pickle.dumps(view))
    assert type(restored) is type(view)
    if isinstance(view, str | bytes):
        assert restored == view
    assert getattr(restored, "full_url", None) == getattr(view, "full_url", None)


@pytest.mark.parametrize("cls,mode", [(TextstreamFileView, "r"), (BytestreamFileView, "rb")])
def test_open_file_backed_view_refuses_pickling(cls: type[Any], mode: str, tmp_path: Path) -> None:
    with open(_text_file(tmp_path), mode) as handle, pytest.raises(TypeError, match="cannot pickle"):
        pickle.dumps(cls(handle))


def test_every_core_view_is_covered() -> None:
    for module in pkgutil.walk_packages(httk.core.__path__, "httk.core."):
        try:
            importlib.import_module(module.name)
        except ImportError:  # optional dependency missing
            continue
    seen: set[type] = set()
    pending: list[type] = [View]
    while pending:
        for sub in pending.pop().__subclasses__():
            if sub not in seen:
                seen.add(sub)
                pending.append(sub)
    covered = {cls.__name__ for cls in VECTOR_VIEWS} | {name.split("-")[0] for name in ROUND_TRIPS}
    concrete = {cls.__name__ for cls in seen if cls.__module__.startswith("httk.core.") and "__new__" in vars(cls)}
    assert concrete - covered == set()
