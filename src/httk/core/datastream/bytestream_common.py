import io
import os
from abc import ABC, abstractmethod
from typing import cast


class BytestreamCommon(ABC):
    """
    Common superclass for many of the implementations of backends for streaming byte data.
    """

    _f: io.IOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @abstractmethod
    def _ensure_f(self) -> io.IOBase:
        pass

    def unwrap(self) -> io.IOBase:
        return self._ensure_f()

    def read(self, size: int = -1) -> bytes:
        return cast(bytes, self._ensure_f().read(size))

    def close(self) -> None:
        if self._f is not None and not self._f.closed:
            self._f.close()
        # A decompression wrapper does not close the source stream it reads from, so close it too.
        if self._underlying is not None and self._underlying is not self._f and not self._underlying.closed:
            self._underlying.close()
        self._closed = True

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return cast(int, self._ensure_f().seek(offset, whence))

    def tell(self) -> int:
        return cast(int, self._ensure_f().tell())
