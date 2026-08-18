"""Tests for the ``httk convert`` command (:func:`httk.core.converting.command`)."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from httk.core import CLIContext
from httk.core.converting import command
from httk.core.register import readers, register_writer, writers
from httk.core.register.io import _writer_formats, _writers_by_format


def _reader(source: str, **kwargs: Any) -> dict[str, Any]:
    with open(source, encoding="utf-8") as handle:
        return {"format": "convtest", "text": handle.read(), "kwargs": kwargs}


def _writer(destination: Any, payload: dict[str, Any], **kwargs: Any) -> None:
    Path(os.fspath(destination)).write_text(payload["text"], encoding="utf-8")


@pytest.fixture
def _register_stubs() -> Iterator[None]:
    readers.register(key=".ina", handler=_reader, name="convtest")
    register_writer(name="convtest", writer=_writer, format="convtest", extensions=(".outa",))
    try:
        yield
    finally:
        readers._by_key.pop(".ina", None)
        writers._by_key.pop(".outa", None)
        _writer_formats.pop((id(writers), ".outa"), None)
        _writers_by_format.pop("convtest", None)


def _context(cwd: Path) -> CLIContext:
    return CLIContext(program="httk", cwd=cwd)


def test_convert_round_trips(_register_stubs: None, tmp_path: Path) -> None:
    (tmp_path / "in.ina").write_text("hello", encoding="utf-8")
    assert command(["in.ina", "out.outa"], _context(tmp_path)) == 0
    assert (tmp_path / "out.outa").read_text(encoding="utf-8") == "hello"


def test_unknown_input_extension_fails(_register_stubs: None, tmp_path: Path, capsys) -> None:
    (tmp_path / "in.mystery").write_text("hello", encoding="utf-8")
    assert command(["in.mystery", "out.outa"], _context(tmp_path)) == 2
    assert "in.mystery" in capsys.readouterr().err


def test_unknown_output_destination_fails(_register_stubs: None, tmp_path: Path, capsys) -> None:
    (tmp_path / "in.ina").write_text("hello", encoding="utf-8")
    assert command(["in.ina", "out.mystery"], _context(tmp_path)) == 2
    assert "out.mystery" in capsys.readouterr().err


def test_format_forwards_to_save(_register_stubs: None, tmp_path: Path) -> None:
    (tmp_path / "in.ina").write_text("hello", encoding="utf-8")
    # ``out.dat`` has no writer by name; ``--format convtest`` selects one.
    assert command(["in.ina", "out.dat", "--format", "convtest"], _context(tmp_path)) == 0
    assert (tmp_path / "out.dat").read_text(encoding="utf-8") == "hello"
