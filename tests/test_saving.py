import os
from pathlib import Path

import pytest

from httk.core import has_writer_for, save
from httk.core.register import _writer_for_format, known_writer_formats, register_format_serializer, register_writer


def test_save_dispatches_writer_and_serializer(tmp_path):
    calls = []

    def writer(destination, payload, **kwargs):
        calls.append((destination, payload, kwargs))
        Path(destination).write_text(str(payload))

    def serializer(obj):
        return {"format": "test-save", "value": obj}

    register_writer(name="test-save", writer=writer, format="test-save", extensions=(".save",), filenames=("SAVEFILE",))
    register_format_serializer(format="test-save", serializer=serializer)

    assert has_writer_for(tmp_path / "x.save")
    save(7, tmp_path / "x.save", answer=42)
    assert calls[0][0].name == "x.save"
    assert calls[0][0] != tmp_path / "x.save"
    assert calls[0][1:] == ({"format": "test-save", "value": 7}, {"answer": 42})
    assert (tmp_path / "x.save").is_file()
    save({"format": "test-save", "raw": True}, tmp_path / "SAVEFILE")
    assert calls[-1][1] == {"format": "test-save", "raw": True}


@pytest.mark.parametrize("suffix", ["", ".gz", ".bz2", ".xz", ".lzma"])
def test_save_failure_keeps_destination_and_cleans_staging(tmp_path, suffix):
    def writer(destination, payload):
        if isinstance(destination, os.PathLike):
            Path(destination).write_text("partial")
        else:
            destination.write("partial")
        raise ValueError("late validation")

    format_name = "atomic-failure" + suffix
    register_writer(name=format_name, writer=writer, format=format_name, extensions=(".atomic",))
    target = tmp_path / ("data.atomic" + suffix)
    target.write_bytes(b"previous contents")
    with pytest.raises(ValueError, match="late validation"):
        save({"format": format_name}, target)
    assert target.read_bytes() == b"previous contents"
    assert list(tmp_path.iterdir()) == [target]


def test_save_preserves_symlinks_permissions_and_hardlink_contents(tmp_path):
    def writer(destination, payload):
        assert Path(destination).name == "LINK"
        Path(destination).write_bytes(b"replacement")

    register_writer(name="atomic-links", writer=writer, format="atomic-links")
    target = tmp_path / "original"
    target.write_bytes(b"original")
    target.chmod(0o640)
    hardlink = tmp_path / "hardlink"
    hardlink.hardlink_to(target)
    symlink = tmp_path / "LINK"
    symlink.symlink_to(target.name)
    save({"format": "atomic-links"}, symlink, format="atomic-links")
    assert symlink.is_symlink()
    assert target.read_bytes() == b"replacement"
    assert target.stat().st_mode & 0o777 == 0o640
    assert hardlink.read_bytes() == b"original"


def test_save_replacement_failure_keeps_destination(tmp_path, monkeypatch):
    from httk.core import _atomic_write

    target = tmp_path / "out"
    target.write_bytes(b"old")

    def refuse_replace(*args):
        raise PermissionError("replacement refused")

    monkeypatch.setattr(_atomic_write.os, "replace", refuse_replace)
    with pytest.raises(PermissionError, match="replacement refused"):
        with _atomic_write.atomic_destination(target) as staged:
            staged.write_bytes(b"new")
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_save_refuses_urls_and_reports_missing_serializer(tmp_path):
    register_writer(name="no-serializer", writer=lambda *_args: None, format="no-serializer", extensions=(".nosave",))
    with pytest.raises(ValueError, match="local files"):
        save({}, "https://example.test/x.nosave")
    with pytest.raises(ValueError, match="no-serializer"):
        save(object(), tmp_path / "x.nosave")


def test_writer_extension_collision_reindexes_format_dispatch():
    first = lambda *_args: None
    second = lambda *_args: None
    register_writer(name="collision-first", writer=first, format="collision-first", extensions=(".collision",))
    register_writer(name="collision-second", writer=second, format="collision-second", extensions=(".collision",))
    assert _writer_for_format("collision-first") is None
    registry, key = _writer_for_format("collision-second")
    assert key == ".collision"
    assert registry.get(key).handler is second


def test_known_writer_formats_are_sorted_and_copied():
    register_writer(name="format-z", writer=lambda *_args: None, format="format-z")
    register_writer(name="format-a", writer=lambda *_args: None, format="format-a")

    formats = known_writer_formats()
    assert {"format-a", "format-z"} <= set(formats)
    assert formats == sorted(formats)
    formats.append("not-registered")
    assert "not-registered" not in known_writer_formats()
