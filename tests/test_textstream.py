import io
from pathlib import Path

import pytest

from httk.core.datastream import (
    BytestreamBackend,
    BytestreamBytes,
    BytestreamBytesView,
    BytestreamFile,
    BytestreamFileView,
    BytestreamFilename,
    BytestreamFilenameView,
    TextstreamBackend,
    TextstreamFile,
    TextstreamFileView,
    TextstreamFilename,
    TextstreamFilenameView,
    TextstreamString,
    TextstreamStringView,
)
from httk.core.views import unwrap


def test_backend_create_dispatches_by_input_type(tmp_path: Path) -> None:
    p = tmp_path / "sample.txt"
    p.write_text("alpha\nbeta\n")

    with p.open("r") as f:
        backend = TextstreamBackend.create(f)
        assert isinstance(backend, TextstreamFile)
        assert backend.name == str(p)

    filename_backend = TextstreamBackend.create(str(p))
    assert isinstance(filename_backend, TextstreamFilename)
    assert filename_backend.name == str(p)

    path_backend = TextstreamBackend.create(p)
    assert isinstance(path_backend, TextstreamFilename)
    assert path_backend.name == str(p)


def test_backend_create_disambiguates_str_with_kind_hints(tmp_path: Path) -> None:
    p = tmp_path / "from-hint.txt"
    p.write_text("from-file\n")

    default_backend = TextstreamBackend.create(str(p))
    assert isinstance(default_backend, TextstreamFilename)

    filename_backend = TextstreamBackend.create(str(p), kind="filename")
    assert isinstance(filename_backend, TextstreamFilename)

    content_backend = TextstreamBackend.create(str(p), kind="content")
    assert isinstance(content_backend, TextstreamString)
    assert content_backend.read() == str(p)


def test_backend_create_raises_for_unrepresentable_or_hint_mismatch() -> None:
    with pytest.raises(TypeError):
        TextstreamBackend.create(12345)

    with pytest.raises(TypeError):
        TextstreamBackend.create("content-like", kind="file")


def test_textstream_file_view_readline_read_and_tell_behavior() -> None:
    view = TextstreamFileView(TextstreamString("a\nbb\nccc"))

    assert view.readline() == "a\n"
    assert view.read(1) == "b"
    assert view.tell() == 3
    assert view.read() == "b\nccc"
    assert view.read() == ""


def test_textstream_file_view_readlines_with_hint() -> None:
    view = TextstreamFileView(TextstreamString("a\nbb\nccc\n"))
    assert view.readlines(hint=3) == ["a\n", "bb\n"]
    assert view.read() == "ccc\n"


def test_textstream_file_view_iteration() -> None:
    view = TextstreamFileView(TextstreamString("x\ny\n"))
    assert list(view) == ["x\n", "y\n"]


def test_textstream_file_view_seek_clears_readline_buffer() -> None:
    view = TextstreamFileView(TextstreamString("first\nsecond\n"))
    assert view.readline() == "first\n"

    assert view.seek(0) == 0
    assert view.tell() == 0
    assert view.read(6) == "first\n"


def test_rewrapping_file_view_returns_same_object() -> None:
    view = TextstreamFileView(TextstreamString("hello"))
    wrapped = TextstreamFileView(view)
    assert wrapped is view


def test_views_share_backend_state_for_close() -> None:
    backend = TextstreamString("close-me")
    v1 = TextstreamFileView(backend)
    v2 = TextstreamFileView(v1)

    v1.close()
    assert v2.closed
    with pytest.raises(ValueError):
        v2.read()


def test_textstream_string_view_is_eager_and_consumes_unread_portion() -> None:
    backend = TextstreamString("head\ntail\n")
    file_view = TextstreamFileView(backend)
    assert file_view.read(5) == "head\n"

    string_view = TextstreamStringView(file_view)
    assert string_view == "tail\n"
    assert file_view.read() == ""


def test_filename_view_from_named_stream_and_string_view_from_filename(tmp_path: Path) -> None:
    p = tmp_path / "named.txt"
    p.write_text("line1\nline2\n")

    with p.open("r") as f:
        filename_view = TextstreamFilenameView(f)
        assert isinstance(filename_view, str)
        assert filename_view == str(p)

    string_view = TextstreamStringView(str(p), kind="filename")
    assert string_view.startswith("line1\n")


def test_filename_view_raises_when_backend_has_no_name() -> None:
    with pytest.raises(TypeError):
        TextstreamFilenameView(TextstreamString("no filename here"))


def test_unwrap_for_views_and_non_views(tmp_path: Path) -> None:
    p = tmp_path / "unwrap.txt"
    p.write_text("unwrap-data\n")

    backend = TextstreamBackend.create(str(p))
    file_obj = unwrap(backend)
    assert isinstance(file_obj, io.TextIOBase)
    assert file_obj.read() == "unwrap-data\n"
    file_obj.close()

    string_view = TextstreamStringView(TextstreamString("x"))
    unwrapped_string_stream = unwrap(string_view)
    assert isinstance(unwrapped_string_stream, io.TextIOBase)
    assert unwrapped_string_stream.read() == ""

    assert unwrap({"k": "v"}) == {"k": "v"}


def test_bytestream_backend_create_dispatches_by_input_type(tmp_path: Path) -> None:
    p = tmp_path / "sample.bin"
    p.write_bytes(b"alpha\nbeta\n")

    with p.open("rb") as f:
        backend = BytestreamBackend.create(f)
        assert isinstance(backend, BytestreamFile)
        assert backend.name == str(p)

    filename_backend = BytestreamBackend.create(str(p))
    assert isinstance(filename_backend, BytestreamFilename)
    assert filename_backend.name == str(p)

    path_backend = BytestreamBackend.create(p)
    assert isinstance(path_backend, BytestreamFilename)
    assert path_backend.name == str(p)

    bytes_backend = BytestreamBackend.create(b"abc")
    assert isinstance(bytes_backend, BytestreamBytes)
    assert bytes_backend.read() == b"abc"

    bytearray_backend = BytestreamBackend.create(bytearray(b"xyz"))
    assert isinstance(bytearray_backend, BytestreamBytes)
    assert bytearray_backend.read() == b"xyz"


def test_bytestream_backend_create_raises_for_unrepresentable_or_hint_mismatch() -> None:
    with pytest.raises(TypeError):
        BytestreamBackend.create(12345)

    with pytest.raises(TypeError):
        BytestreamBackend.create(b"content-like", kind="file")


def test_bytestream_file_view_readline_read_and_tell_behavior() -> None:
    view = BytestreamFileView(BytestreamBytes(b"a\nbb\nccc"))

    assert view.readline() == b"a\n"
    assert view.read(1) == b"b"
    assert view.tell() == 3
    assert view.read() == b"b\nccc"
    assert view.read() == b""


def test_bytestream_file_view_readlines_with_hint() -> None:
    view = BytestreamFileView(BytestreamBytes(b"a\nbb\nccc\n"))
    assert view.readlines(hint=3) == [b"a\n", b"bb\n"]
    assert view.read() == b"ccc\n"


def test_bytestream_file_view_iteration() -> None:
    view = BytestreamFileView(BytestreamBytes(b"x\ny\n"))
    assert list(view) == [b"x\n", b"y\n"]


def test_bytestream_file_view_seek_clears_readline_buffer() -> None:
    view = BytestreamFileView(BytestreamBytes(b"first\nsecond\n"))
    assert view.readline() == b"first\n"

    assert view.seek(0) == 0
    assert view.tell() == 0
    assert view.read(6) == b"first\n"


def test_bytestream_rewrapping_file_view_returns_same_object() -> None:
    view = BytestreamFileView(BytestreamBytes(b"hello"))
    wrapped = BytestreamFileView(view)
    assert wrapped is view


def test_bytestream_views_share_backend_state_for_close() -> None:
    backend = BytestreamBytes(b"close-me")
    v1 = BytestreamFileView(backend)
    v2 = BytestreamFileView(v1)

    v1.close()
    assert v2.closed
    with pytest.raises(ValueError):
        v2.read()


def test_bytestream_bytes_view_is_eager_and_consumes_unread_portion() -> None:
    backend = BytestreamBytes(b"head\ntail\n")
    file_view = BytestreamFileView(backend)
    assert file_view.read(5) == b"head\n"

    bytes_view = BytestreamBytesView(file_view)
    assert bytes_view == b"tail\n"
    assert file_view.read() == b""


def test_bytestream_filename_view_from_named_stream_and_bytes_view_from_filename(tmp_path: Path) -> None:
    p = tmp_path / "named.bin"
    p.write_bytes(b"line1\nline2\n")

    with p.open("rb") as f:
        filename_view = BytestreamFilenameView(f)
        assert isinstance(filename_view, str)
        assert filename_view == str(p)

    bytes_view = BytestreamBytesView(str(p), kind="filename")
    assert bytes_view.startswith(b"line1\n")


def test_bytestream_filename_view_raises_when_backend_has_no_name() -> None:
    with pytest.raises(TypeError):
        BytestreamFilenameView(BytestreamBytes(b"no filename here"))


def test_bytestream_unwrap_for_views_and_non_views(tmp_path: Path) -> None:
    p = tmp_path / "unwrap.bin"
    p.write_bytes(b"unwrap-data\n")

    backend = BytestreamBackend.create(str(p))
    file_obj = unwrap(backend)
    assert isinstance(file_obj, io.IOBase)
    assert file_obj.read() == b"unwrap-data\n"
    file_obj.close()

    bytes_view = BytestreamBytesView(BytestreamBytes(b"x"))
    unwrapped_bytes_stream = unwrap(bytes_view)
    assert isinstance(unwrapped_bytes_stream, io.IOBase)
    assert unwrapped_bytes_stream.read() == b""

    assert unwrap({"k": "v"}) == {"k": "v"}
