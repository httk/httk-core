import io
import os
from abc import ABC, abstractmethod


class TextstreamCommon(ABC):
    """
    Common superclass for many of the implementations of backends for streaming text data.
    """

    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @abstractmethod
    def _ensure_f(self) -> io.TextIOBase:
        pass

    def unwrap(self) -> io.TextIOBase:
        """Return the currently opened underlying text stream.

        :return: The stream used for reading text.
        """
        return self._ensure_f()

    def read(self, size: int = -1) -> str:
        """Read up to ``size`` characters, or all remaining characters when ``size`` is negative.

        :param size: Maximum number of characters to read.
        :return: The text read from the stream.
        """
        return self._ensure_f().read(size)

    def close(self) -> None:
        """Close the opened stream and any source stream owned by it."""
        if self._f is not None and not self._f.closed:
            self._f.close()
        # A text wrapper closes the stream it wraps but not a decompression source below it.
        if self._underlying is not None and self._underlying is not self._f and not self._underlying.closed:
            self._underlying.close()
        self._closed = True

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        """Move the stream position.

        :param offset: Position adjustment interpreted according to ``whence``.
        :param whence: Reference point for ``offset``.
        :return: The resulting absolute stream position.
        """
        return self._ensure_f().seek(offset, whence)

    def tell(self) -> int:
        """Return the current stream position.

        :return: The absolute stream position.
        """
        return self._ensure_f().tell()
