import pytest

from httk.core import has_writer_for, save
from httk.core.register import _writer_for_format, register_format_serializer, register_writer


def test_save_dispatches_writer_and_serializer(tmp_path):
    calls = []

    def writer(destination, payload, **kwargs):
        calls.append((destination, payload, kwargs))

    def serializer(obj):
        return {"format": "test-save", "value": obj}

    register_writer(
        name="test-save", writer=writer, format="test-save", extensions=(".save",), filenames=("SAVEFILE",)
    )
    register_format_serializer(format="test-save", serializer=serializer)

    assert has_writer_for(tmp_path / "x.save")
    save(7, tmp_path / "x.save", answer=42)
    assert calls == [(tmp_path / "x.save", {"format": "test-save", "value": 7}, {"answer": 42})]
    save({"format": "test-save", "raw": True}, tmp_path / "SAVEFILE")
    assert calls[-1][1] == {"format": "test-save", "raw": True}


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
