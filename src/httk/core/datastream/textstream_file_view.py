import io
from typing import Any, Iterator, NoReturn, Self

from .textstream_api import TextstreamAPI
from .textstream_backend import TextstreamBackend
from .textstream_view import TextstreamView


class TextstreamFileView(TextstreamView, io.TextIOBase, TextstreamAPI):
    """
    A view presenting an underlying data streaming backend via the full io.TextIOBase API, which is a superset of TextstreamAPI.
    """

    _backend: TextstreamBackend
    _readline_buffer: str

    def __new__(cls, obj: "TextstreamLike", **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(TextstreamBackend, TextstreamView, obj, hints)
        instance = super().__new__(cls)
        instance._backend = backend
        instance._readline_buffer = ""
        return instance

    def __init__(self, obj: "TextstreamLike", **hints: Any) -> None:
        pass

    def unwrap(self) -> Any:
        return unwrap_if_possible(self._backend)

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
        if hasattr(self._backend, "flush"):
            self._backend.flush()  # type: ignore[attr-defined]

    def read(self, size: int = -1) -> str:
        if self.closed:
            raise ValueError("I/O operation on closed file.")

        if size < 0:
            if self._readline_buffer:
                prefix = self._readline_buffer
                self._readline_buffer = ""
                return prefix + self._backend.read()
            return self._backend.read()

        if size == 0:
            return ""

        if self._readline_buffer:
            if len(self._readline_buffer) >= size:
                out = self._readline_buffer[:size]
                self._readline_buffer = self._readline_buffer[size:]
                return out
            prefix = self._readline_buffer
            self._readline_buffer = ""
            return prefix + self._backend.read(size - len(prefix))

        return self._backend.read(size)

    def readline(self, size: int = -1) -> str:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == 0:
            return ""

        parts: list[str] = []
        total = 0

        while True:
            if self._readline_buffer:
                chunk = self._readline_buffer
                self._readline_buffer = ""
            else:
                to_read = 8192
                if size >= 0:
                    remaining = size - total
                    if remaining <= 0:
                        break
                    to_read = min(to_read, remaining)
                chunk = self._backend.read(to_read)

            if chunk == "":
                break

            newline_pos = chunk.find("\n")
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

        return "".join(parts)

    def readlines(self, hint: int = -1) -> list[str]:
        if self.closed:
            raise ValueError("I/O operation on closed file.")

        lines: list[str] = []
        total = 0

        while True:
            line = self.readline()
            if line == "":
                break
            lines.append(line)
            total += len(line)
            if hint >= 0 and total >= hint:
                break

        return lines

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        line = self.readline()
        if line == "":
            raise StopIteration
        return line

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if not hasattr(self._backend, "seek"):
            raise io.UnsupportedOperation("underlying stream is not seekable")

        pos = self._backend.seek(offset, whence)  # type: ignore[attr-defined]
        self._readline_buffer = ""
        return cast(int, pos)

    def tell(self) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if not hasattr(self._backend, "tell"):
            raise io.UnsupportedOperation("underlying stream does not support tell()")

        pos = self._backend.tell()  # type: ignore[attr-defined]
        return cast(int, pos) - len(self._readline_buffer)

    def detach(self) -> NoReturn:
        raise io.UnsupportedOperation("detach")

    @property
    def encoding(self) -> str | None:
        return cast(str | None, getattr(self._backend, "encoding", None))

    @property
    def errors(self) -> str | None:
        return cast(str | None, getattr(self._backend, "errors", None))

    @property
    def newlines(self) -> str | tuple[str, ...] | None:
        return cast(str | tuple[str, ...] | None, getattr(self._backend, "newlines", None))
