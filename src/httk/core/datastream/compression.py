import bz2
import gzip
import io
import lzma
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, cast


@dataclass(frozen=True)
class CompressionCodec:
    """
    A decompression codec for a single container format.

    A codec is an orthogonal layer below the datastream backends: it turns a compressed
    binary stream into an uncompressed binary stream, independently of where the compressed
    bytes come from (a filename, an open file, raw bytes, or a remote response).

    :param name: Canonical name used to select the codec explicitly.
    :param extensions: Filename suffixes that identify the codec.
    :param magics: Leading byte signatures used to detect the codec.
    :param open_stream: Function that wraps compressed bytes for reading.
    """

    name: str
    """Canonical, lower-case codec name (e.g. ``"gzip"``); also how an explicit hint selects it."""

    extensions: tuple[str, ...]
    """Recognized filename suffixes including the leading dot (e.g. ``(".gz",)``)."""

    magics: tuple[bytes, ...]
    """Leading magic-byte signatures; an empty tuple means the format cannot be sniffed."""

    open_stream: Callable[[io.IOBase], io.IOBase]
    """Wrap a compressed binary stream and return a readable, decompressed binary stream."""


_registry: dict[str, CompressionCodec] = {}
_MODES = frozenset({"auto", "detect", "extension", "none"})


def register_compression(codec: CompressionCodec) -> None:
    """Register (or replace) a codec under its :attr:`~CompressionCodec.name` (case-insensitive).

    :param codec: Codec to add to the registry.
    """
    _registry[codec.name.lower()] = codec


def known_compressions() -> list[str]:
    """Return the registered codec names, in registration order.

    :return: The registered codec names.
    """
    return list(_registry)


def codec_for_name(name: str) -> CompressionCodec | None:
    """Return the codec whose extension matches the trailing suffix of ``name``, else ``None``.

    :param name: Filename or URL path to inspect.
    :return: The matching codec, or ``None`` when no suffix is recognized.
    """
    lowered = name.lower()
    for codec in _registry.values():
        for ext in codec.extensions:
            if lowered.endswith(ext.lower()):
                return codec
    return None


def split_compression_suffix(name: str) -> tuple[str, CompressionCodec | None]:
    """
    Split a trailing compression extension off ``name``.

    ``"data.json.gz"`` becomes ``("data.json", <gzip codec>)``; a name with no recognized
    compression extension is returned unchanged with ``None``.

    :param name: Filename or URL path to split.
    :return: The name without its recognized suffix and the matching codec, if any.
    """
    codec = codec_for_name(name)
    if codec is None:
        return name, None
    lowered = name.lower()
    for ext in codec.extensions:
        if lowered.endswith(ext.lower()):
            return name[: -len(ext)], codec
    return name, codec


def _max_magic_len() -> int:
    return max((len(magic) for codec in _registry.values() for magic in codec.magics), default=0)


def _match_magic(prefix: bytes) -> CompressionCodec | None:
    for codec in _registry.values():
        for magic in codec.magics:
            if magic and prefix.startswith(magic):
                return codec
    return None


def sniff_codec(stream: io.IOBase) -> tuple[io.IOBase, CompressionCodec | None]:
    """
    Detect a codec from the leading magic bytes of ``stream`` without consuming data.

    A seekable stream is read and rewound; an unseekable stream is peeked (directly when it
    supports ``peek``, otherwise via a wrapping :class:`io.BufferedReader`). The returned
    stream must be used in place of the input, since it may be the wrapper.

    :param stream: Binary stream whose leading bytes should be inspected.
    :return: The stream to continue reading and the detected codec, if any.
    """
    max_len = _max_magic_len()
    if max_len == 0:
        return stream, None
    if stream.seekable():
        reader = cast(io.BufferedIOBase, stream)
        pos = reader.tell()
        prefix = reader.read(max_len)
        reader.seek(pos)
        return stream, _match_magic(prefix)
    peek = getattr(stream, "peek", None)
    if callable(peek):
        return stream, _match_magic(cast(bytes, peek(max_len))[:max_len])
    buffered = io.BufferedReader(cast(io.RawIOBase, stream))
    return buffered, _match_magic(buffered.peek(max_len)[:max_len])


def open_compressed(stream: io.IOBase, *, compression: str = "auto", name: str | None = None) -> io.IOBase:
    """
    Return a decompressed view of ``stream`` according to the ``compression`` hint.

    Values are ``"none"`` (passthrough), ``"extension"`` (decide from ``name`` only),
    ``"detect"`` (always sniff magic bytes), ``"auto"`` (extension if recognized, else sniff),
    or a registered codec name (force that codec; an unknown name raises :class:`ValueError`).
    When no codec applies the stream is returned unchanged.

    :param stream: Compressed or uncompressed binary stream to expose.
    :param compression: Mode or codec name controlling decompression.
    :param name: Optional source name used for extension-based selection.
    :return: A decompressed stream, or the original stream when no codec applies.
    :raises ValueError: If ``compression`` names an unknown codec.
    """
    token = compression.lower()
    if token == "none":
        return stream
    if token == "extension":
        codec = codec_for_name(name) if name is not None else None
        return codec.open_stream(stream) if codec is not None else stream
    if token == "auto":
        codec = codec_for_name(name) if name is not None else None
        if codec is not None:
            return codec.open_stream(stream)
        stream, codec = sniff_codec(stream)
        return codec.open_stream(stream) if codec is not None else stream
    if token == "detect":
        stream, codec = sniff_codec(stream)
        return codec.open_stream(stream) if codec is not None else stream
    codec = _registry.get(token)
    if codec is None:
        raise ValueError(f"unknown compression codec {compression!r}; known codecs: {known_compressions()}")
    return codec.open_stream(stream)


def validate_compression(compression: str) -> None:
    """Raise :class:`ValueError` unless ``compression`` is a known mode or registered codec name.

    :param compression: Mode or codec name to validate.
    :raises ValueError: If ``compression`` is unknown.
    """
    token = compression.lower()
    if token in _MODES or token in _registry:
        return
    raise ValueError(
        f"unknown compression {compression!r}; expected one of {sorted(_MODES)} "
        f"or a registered codec name ({known_compressions()})"
    )


def reject_text_native_compression(compression: str | None) -> None:
    """
    Validate a ``compression`` hint for a text-native source (an open text stream or a string).

    Such sources carry no compressed bytes to decode, so only the no-op modes ``"auto"``,
    ``"extension"``, and ``"none"`` are accepted; a codec name or ``"detect"`` raises
    :class:`ValueError`. ``None`` (no hint given) is accepted.

    :param compression: Optional compression hint supplied for a text-native source.
    :raises ValueError: If the hint requests native decompression or magic detection.
    """
    if compression is None or compression.lower() in ("auto", "extension", "none"):
        return
    raise ValueError(f"compression={compression!r} does not apply to a text-native source")


def _open_gzip(stream: io.IOBase) -> io.IOBase:
    return gzip.GzipFile(fileobj=cast(IO[bytes], stream))


def _open_bzip2(stream: io.IOBase) -> io.IOBase:
    return bz2.BZ2File(cast(IO[bytes], stream))


def _open_xz(stream: io.IOBase) -> io.IOBase:
    return lzma.LZMAFile(cast(IO[bytes], stream))


def _open_lzma(stream: io.IOBase) -> io.IOBase:
    return lzma.LZMAFile(cast(IO[bytes], stream), format=lzma.FORMAT_ALONE)


register_compression(CompressionCodec("gzip", (".gz",), (b"\x1f\x8b",), _open_gzip))
register_compression(CompressionCodec("bzip2", (".bz2",), (b"BZh",), _open_bzip2))
register_compression(CompressionCodec("xz", (".xz",), (b"\xfd7zXZ\x00",), _open_xz))
register_compression(CompressionCodec("lzma", (".lzma",), (), _open_lzma))
