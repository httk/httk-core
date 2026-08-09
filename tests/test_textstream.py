import gzip
import io
import urllib.request
from pathlib import Path
from typing import cast

import pytest

from httk.core.datastream import (
    BytestreamBackend,
    BytestreamBytes,
    BytestreamBytesView,
    BytestreamFile,
    BytestreamFilename,
    BytestreamFilenameView,
    BytestreamFileView,
    BytestreamRequest,
    BytestreamRequestView,
    BytestreamURL,
    BytestreamURLView,
    TextstreamBackend,
    TextstreamFile,
    TextstreamFilename,
    TextstreamFilenameView,
    TextstreamFileView,
    TextstreamRequest,
    TextstreamRequestView,
    TextstreamString,
    TextstreamStringView,
    TextstreamURL,
    TextstreamURLView,
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


# --- Request/URL backends and views (urllib-based, using file:// URLs, no network) ---


def test_textstream_request_backend_auto_dispatch_and_lazy_read(tmp_path: Path) -> None:
    p = tmp_path / "req.txt"
    p.write_text("request-body\n")
    uri = p.as_uri()

    backend = TextstreamBackend.create(urllib.request.Request(uri))
    assert isinstance(backend, TextstreamRequest)
    assert backend.name is None
    assert backend.url == uri
    assert backend.read() == "request-body\n"


def test_bytestream_request_backend_auto_dispatch_and_lazy_read(tmp_path: Path) -> None:
    p = tmp_path / "req.bin"
    p.write_bytes(b"request-body\n")
    uri = p.as_uri()

    backend = BytestreamBackend.create(urllib.request.Request(uri))
    assert isinstance(backend, BytestreamRequest)
    assert backend.name is None
    assert backend.url == uri
    assert backend.read() == b"request-body\n"


def test_textstream_url_backend_auto_recognizes_scheme_and_kind_overrides(tmp_path: Path) -> None:
    p = tmp_path / "url.txt"
    p.write_text("url-body\n")
    uri = p.as_uri()

    url_backend = TextstreamBackend.create(uri, kind="url")
    assert isinstance(url_backend, TextstreamURL)
    assert url_backend.name is None
    assert url_backend.url == uri
    assert url_backend.read() == "url-body\n"

    # An explicit URL hint selects the URL backend.
    auto_backend = TextstreamBackend.create(uri, kind="url")
    assert isinstance(auto_backend, TextstreamURL)
    assert auto_backend.read() == "url-body\n"

    # kind="filename" still forces a filename interpretation of the same string.
    forced_filename = TextstreamBackend.create(uri, kind="filename")
    assert isinstance(forced_filename, TextstreamFilename)

    # A schemeless string is a filename by default.
    assert isinstance(TextstreamBackend.create(str(p)), TextstreamFilename)

    with pytest.raises(TypeError):
        TextstreamBackend.create("no-scheme", kind="url")


def test_bytestream_url_backend_auto_recognizes_scheme_and_kind_overrides(tmp_path: Path) -> None:
    p = tmp_path / "url.bin"
    p.write_bytes(b"url-body\n")
    uri = p.as_uri()

    url_backend = BytestreamBackend.create(uri, kind="url")
    assert isinstance(url_backend, BytestreamURL)
    assert url_backend.read() == b"url-body\n"

    auto_backend = BytestreamBackend.create(uri, kind="url")
    assert isinstance(auto_backend, BytestreamURL)
    assert auto_backend.read() == b"url-body\n"

    forced_filename = BytestreamBackend.create(uri, kind="filename")
    assert isinstance(forced_filename, BytestreamFilename)

    assert isinstance(BytestreamBackend.create(str(p)), BytestreamFilename)

    with pytest.raises(TypeError):
        BytestreamBackend.create("no-scheme", kind="url")


def test_filename_view_raises_for_url_backend(tmp_path: Path) -> None:
    p = tmp_path / "no-filename.txt"
    p.write_text("data\n")
    uri = p.as_uri()

    text_url = TextstreamBackend.create(uri, kind="url")
    with pytest.raises(TypeError):
        TextstreamFilenameView(text_url)

    bytes_url = BytestreamBackend.create(uri, kind="url")
    with pytest.raises(TypeError):
        BytestreamFilenameView(bytes_url)


def test_url_view_from_url_and_request_backends_and_type_error(tmp_path: Path) -> None:
    p = tmp_path / "urlview.txt"
    p.write_text("uv\n")
    uri = p.as_uri()

    text_url = TextstreamBackend.create(uri, kind="url")
    url_view = TextstreamURLView(text_url)
    assert isinstance(url_view, str)
    assert url_view == uri

    request_backend = TextstreamBackend.create(urllib.request.Request(uri))
    assert TextstreamURLView(request_backend) == uri

    with pytest.raises(TypeError):
        TextstreamURLView(TextstreamString("no url here"))

    bytes_url = BytestreamBackend.create(uri, kind="url")
    assert BytestreamURLView(bytes_url) == uri
    with pytest.raises(TypeError):
        BytestreamURLView(BytestreamBytes(b"no url here"))


def test_request_view_is_request_with_matching_url_and_copies_headers(tmp_path: Path) -> None:
    p = tmp_path / "reqview.txt"
    p.write_text("rv\n")
    uri = p.as_uri()

    url_backend = TextstreamBackend.create(uri, kind="url")
    request_view = TextstreamRequestView(url_backend)
    assert isinstance(request_view, urllib.request.Request)
    assert request_view.full_url == uri

    original = urllib.request.Request(uri, headers={"X-Test": "yes"})
    request_backend = TextstreamBackend.create(original)
    copied_view = TextstreamRequestView(request_backend)
    assert copied_view.full_url == uri
    assert copied_view.headers == original.headers

    # Rewrapping an existing request view returns the same object (no re-init).
    assert TextstreamRequestView(copied_view) is copied_view


def test_bytestream_request_view_from_url_backend(tmp_path: Path) -> None:
    p = tmp_path / "b-reqview.bin"
    p.write_bytes(b"rv\n")
    uri = p.as_uri()

    url_backend = BytestreamBackend.create(uri, kind="url")
    request_view = BytestreamRequestView(url_backend)
    assert isinstance(request_view, urllib.request.Request)
    assert request_view.full_url == uri


def test_textstream_url_decoding_default_utf8_and_encoding_hint(tmp_path: Path) -> None:
    utf8_path = tmp_path / "utf8.txt"
    utf8_path.write_text("héllo\n", encoding="utf-8")
    utf8_backend = TextstreamBackend.create(utf8_path.as_uri(), kind="url")
    assert utf8_backend.read() == "héllo\n"

    latin_path = tmp_path / "latin.txt"
    latin_path.write_bytes("café\n".encode("latin-1"))
    latin_backend = TextstreamBackend.create(latin_path.as_uri(), kind="url", encoding="latin-1")
    assert latin_backend.read() == "café\n"


def test_request_backend_close_without_fetch_then_read_raises(tmp_path: Path) -> None:
    p = tmp_path / "lazy.txt"
    p.write_text("never-read\n")
    uri = p.as_uri()

    backend = TextstreamBackend.create(urllib.request.Request(uri))
    backend.close()
    assert backend.closed
    with pytest.raises(ValueError):
        backend.read()

    bytes_backend = BytestreamBackend.create(uri, kind="url")
    bytes_backend.close()
    with pytest.raises(ValueError):
        bytes_backend.read()


# --- Compression layer through the byte/text backends and views ---


def test_bytestream_filename_decompresses_by_extension_default(tmp_path: Path) -> None:
    p = tmp_path / "payload.bin.gz"
    with gzip.open(p, "wb") as f:
        f.write(b"decompressed-bytes")
    assert BytestreamBytesView(str(p)) == b"decompressed-bytes"


def test_bytestream_filename_hidden_gzip_needs_auto_or_codec(tmp_path: Path) -> None:
    raw = gzip.compress(b"hidden")
    p = tmp_path / "payload.bin"  # extension does not reveal the compression
    p.write_bytes(raw)

    # Default "extension" trusts the (non-compression) suffix: bytes are left compressed.
    assert BytestreamBytesView(str(p)) == raw
    assert BytestreamBytesView(str(p), compression="none") == raw

    # Sniffing or forcing the codec decompresses.
    assert BytestreamBytesView(str(p), compression="auto") == b"hidden"
    assert BytestreamBytesView(str(p), compression="detect") == b"hidden"
    assert BytestreamBytesView(str(p), compression="gzip") == b"hidden"


def test_bytestream_bytes_sniffs_gzip_by_default() -> None:
    raw = gzip.compress(b"in-memory")
    assert BytestreamBytesView(raw) == b"in-memory"
    assert BytestreamBytesView(raw, compression="none") == raw


def test_bytestream_unknown_codec_raises_eagerly(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        BytestreamBytesView(str(p), compression="zstd")


def test_textstream_string_rejects_non_noop_compression() -> None:
    with pytest.raises(ValueError):
        TextstreamString("x", kind="content", compression="gzip")
    with pytest.raises(ValueError):
        TextstreamString("x", kind="content", compression="detect")
    # No-op modes are silently accepted for text-native sources.
    assert TextstreamString("x", kind="content", compression="none").read() == "x"


def test_textstream_filename_gz_with_encoding_hint(tmp_path: Path) -> None:
    p = tmp_path / "note.txt.gz"
    with gzip.open(p, "wb") as f:
        f.write("café\n".encode("latin-1"))
    view = TextstreamFileView(str(p), encoding="latin-1")
    assert view.read() == "café\n"


def test_textstream_filename_defaults_to_utf8(tmp_path: Path) -> None:
    p = tmp_path / "uni.txt"
    p.write_text("héllo\n", encoding="utf-8")
    assert TextstreamStringView(str(p)) == "héllo\n"


def test_bytestream_file_object_sniffs_when_auto(tmp_path: Path) -> None:
    p = tmp_path / "opened.bin"
    with gzip.open(p, "wb") as f:
        f.write(b"through-open-file")
    with p.open("rb") as fobj:
        assert BytestreamBytesView(fobj) == b"through-open-file"


def test_compression_close_releases_underlying_file(tmp_path: Path) -> None:
    p = tmp_path / "close.bin.gz"
    with gzip.open(p, "wb") as f:
        f.write(b"data")
    backend = cast(BytestreamFilename, BytestreamBackend.create(str(p)))
    assert backend.read() == b"data"
    backend.close()
    assert backend.closed
    # The raw file underneath the gzip wrapper is closed too.
    assert backend._underlying is not None and backend._underlying.closed
