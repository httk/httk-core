import io
from collections.abc import Iterator
from typing import Any, NoReturn, Self

from ..views import unwrap
from .bytestream_api import BytestreamAPI
from .bytestream_backend import BytestreamBackend
from .bytestream_like import BytestreamLike
from .bytestream_view import BytestreamView


class BytestreamFileView(BytestreamView, io.IOBase, BytestreamAPI):
    """
    A view presenting an underlying data streaming backend via an io.IOBase-like API.
    """

    _backend: BytestreamBackend
    _readline_buffer: bytes

    def __new__(cls, obj: BytestreamLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        instance = super().__new__(cls)
        instance._backend = backend
        instance._readline_buffer = b""
        return instance

    def __init__(self, obj: BytestreamLike, **hints: Any) -> None:
        pass

    def unwrap(self) -> Any:
        return unwrap(self._backend)

    @property
    def name(self) -> str | None:
        return self._backend.name

    @property
    def closed(self) -> bool:
        return self._backend.closed

    def close(self) -> None:
        self._backend.close()

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return hasattr(self._backend, "seek") and hasattr(self._backend, "tell")

    def flush(self) -> None:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        flush = getattr(self._backend, "flush", None)
        if flush:
            flush()

    def read(self, size: int | None = -1) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")

        if size is None or size < 0:
            if self._readline_buffer:
                prefix = self._readline_buffer
                self._readline_buffer = b""
                return prefix + self._backend.read()
            return self._backend.read()

        if size == 0:
            return b""

        if self._readline_buffer:
            if len(self._readline_buffer) >= size:
                out = self._readline_buffer[:size]
                self._readline_buffer = self._readline_buffer[size:]
                return out
            prefix = self._readline_buffer
            self._readline_buffer = b""
            return prefix + self._backend.read(size - len(prefix))

        return self._backend.read(size)

    def readline(self, size: int | None = -1) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return b""
        if size is None:
            size = -1

        parts: list[bytes] = []
        total = 0

        while True:
            if self._readline_buffer:
                chunk = self._readline_buffer
                self._readline_buffer = b""
            else:
                to_read = 8192
                if size >= 0:
                    remaining = size - total
                    if remaining <= 0:
                        break
                    to_read = min(to_read, remaining)
                chunk = self._backend.read(to_read)

            if chunk == b"":
                break

            newline_pos = chunk.find(b"\n")
            if newline_pos != -1:
                newline_pos += 1
                take = chunk[:newline_pos]
                rest = chunk[newline_pos:]

                if size >= 0 and total + len(take) > size:
                    cutoff = size - total
                    parts.append(take[:cutoff])
                    self._readline_buffer = take[cutoff:] + rest
                    break

                parts.append(take)
                self._readline_buffer = rest
                break

            if size >= 0 and total + len(chunk) > size:
                cutoff = size - total
                parts.append(chunk[:cutoff])
                self._readline_buffer = chunk[cutoff:]
                break

            parts.append(chunk)
            total += len(chunk)

        return b"".join(parts)

    def readlines(self, hint: int = -1) -> list[bytes]:
        if self.closed:
            raise ValueError("I/O operation on closed file.")

        lines: list[bytes] = []
        total = 0

        while True:
            line = self.readline()
            if line == b"":
                break
            lines.append(line)
            total += len(line)
            if hint >= 0 and total >= hint:
                break

        return lines

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        line = self.readline()
        if line == b"":
            raise StopIteration
        return line

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        seek = getattr(self._backend, "seek", None)
        if not seek:
            raise io.UnsupportedOperation("underlying stream is not seekable")

        pos = seek(offset, whence)
        self._readline_buffer = b""
        return pos

    def tell(self) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        tell = getattr(self._backend, "tell", None)
        if not tell:
            raise io.UnsupportedOperation("underlying stream does not support tell()")

        pos = tell()
        return pos - len(self._readline_buffer)

    def detach(self) -> NoReturn:
        raise io.UnsupportedOperation("detach")
