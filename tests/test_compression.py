import bz2
import gzip
import io
import lzma
from collections.abc import Iterator

import pytest

from httk.core import CompressionCodec, known_compressions, register_compression
from httk.core.datastream import compression as c
from httk.core.datastream.compression import (
    codec_for_name,
    open_compressed,
    reject_text_native_compression,
    sniff_codec,
    split_compression_suffix,
    validate_compression,
)


@pytest.fixture
def clean_registry() -> Iterator[None]:
    saved = dict(c._registry)
    try:
        yield
    finally:
        c._registry.clear()
        c._registry.update(saved)


class _UnseekableRaw(io.RawIOBase):
    """A readable, non-seekable, non-peekable raw stream over a bytes payload."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def readinto(self, b: object) -> int:
        buffer = memoryview(b)  # type: ignore[arg-type]
        chunk = self._data[self._pos : self._pos + len(buffer)]
        buffer[: len(chunk)] = chunk
        self._pos += len(chunk)
        return len(chunk)


def test_builtin_registry_contents() -> None:
    names = known_compressions()
    for expected in ("gzip", "bzip2", "xz", "lzma"):
        assert expected in names


def test_codec_for_name_is_case_insensitive() -> None:
    assert codec_for_name("data.json.gz").name == "gzip"
    assert codec_for_name("ARCHIVE.TAR.BZ2").name == "bzip2"
    assert codec_for_name("blob.xz").name == "xz"
    assert codec_for_name("plain.json") is None


def test_split_compression_suffix() -> None:
    base, codec = split_compression_suffix("data.json.gz")
    assert base == "data.json"
    assert codec is not None and codec.name == "gzip"

    base, codec = split_compression_suffix("DATA.JSON.GZ")
    assert base == "DATA.JSON"
    assert codec is not None and codec.name == "gzip"

    assert split_compression_suffix("data.json") == ("data.json", None)


def test_sniff_seekable_does_not_consume() -> None:
    payload = gzip.compress(b"payload")
    stream = io.BytesIO(payload)
    returned, codec = sniff_codec(stream)
    assert returned is stream
    assert codec is not None and codec.name == "gzip"
    # The prefix was rewound, so the full compressed payload is still readable.
    assert stream.read() == payload


def test_sniff_unseekable_wraps_and_does_not_consume() -> None:
    payload = gzip.compress(b"payload")
    raw = _UnseekableRaw(payload)
    returned, codec = sniff_codec(raw)
    assert codec is not None and codec.name == "gzip"
    # The returned (wrapped) stream still yields the whole payload; then it decompresses.
    assert returned.read() == payload
    raw2 = _UnseekableRaw(payload)
    returned2, codec2 = sniff_codec(raw2)
    assert codec2 is not None
    assert codec2.open_stream(returned2).read() == b"payload"


def test_sniff_no_match_returns_none() -> None:
    stream = io.BytesIO(b"not compressed at all")
    returned, codec = sniff_codec(stream)
    assert returned is stream
    assert codec is None


def test_open_compressed_hint_semantics() -> None:
    data = b"the payload"
    packed = gzip.compress(data)

    # none: passthrough
    assert open_compressed(io.BytesIO(packed), compression="none").read() == packed

    # explicit codec name: force decompression
    assert open_compressed(io.BytesIO(packed), compression="gzip").read() == data

    # extension: decide from name only
    assert open_compressed(io.BytesIO(packed), compression="extension", name="x.gz").read() == data
    assert open_compressed(io.BytesIO(packed), compression="extension", name="x.bin").read() == packed

    # auto: extension first, else sniff
    assert open_compressed(io.BytesIO(packed), compression="auto", name="x.gz").read() == data
    assert open_compressed(io.BytesIO(packed), compression="auto", name="x.bin").read() == data
    assert open_compressed(io.BytesIO(packed), compression="auto", name=None).read() == data

    # detect: ignore the extension, sniff magic
    assert open_compressed(io.BytesIO(data), compression="detect", name="x.gz").read() == data
    assert open_compressed(io.BytesIO(packed), compression="detect").read() == data


def test_open_compressed_unknown_codec_raises() -> None:
    with pytest.raises(ValueError):
        open_compressed(io.BytesIO(b"x"), compression="zstd")


def test_validate_compression() -> None:
    for value in ("auto", "detect", "extension", "none", "gzip", "GZIP", "xz"):
        validate_compression(value)
    with pytest.raises(ValueError):
        validate_compression("zstd")
    with pytest.raises(ValueError):
        validate_compression("bogus")


def test_reject_text_native_compression() -> None:
    for value in (None, "auto", "extension", "none"):
        reject_text_native_compression(value)
    for value in ("detect", "gzip"):
        with pytest.raises(ValueError):
            reject_text_native_compression(value)


def test_bzip2_and_xz_and_lzma_roundtrips() -> None:
    data = b"round trip payload for stdlib codecs"

    assert open_compressed(io.BytesIO(bz2.compress(data)), compression="bzip2").read() == data
    assert open_compressed(io.BytesIO(lzma.compress(data)), compression="xz").read() == data

    alone = lzma.compress(data, format=lzma.FORMAT_ALONE)
    assert open_compressed(io.BytesIO(alone), compression="lzma").read() == data

    _, bz_codec = sniff_codec(io.BytesIO(bz2.compress(data)))
    assert bz_codec is not None and bz_codec.name == "bzip2"
    _, xz_codec = sniff_codec(io.BytesIO(lzma.compress(data)))
    assert xz_codec is not None and xz_codec.name == "xz"


def test_custom_codec_registration(clean_registry: None) -> None:
    def open_foo(stream: io.IOBase) -> io.IOBase:
        return io.BytesIO(stream.read()[3:])  # strip the b"FOO" marker

    register_compression(CompressionCodec("foo", (".foo",), (b"FOO",), open_foo))

    assert "foo" in known_compressions()
    assert codec_for_name("blob.foo").name == "foo"

    _, codec = sniff_codec(io.BytesIO(b"FOObar"))
    assert codec is not None and codec.name == "foo"

    assert open_compressed(io.BytesIO(b"FOObar"), compression="foo").read() == b"bar"
    assert open_compressed(io.BytesIO(b"FOObar"), compression="extension", name="x.foo").read() == b"bar"
    validate_compression("foo")
