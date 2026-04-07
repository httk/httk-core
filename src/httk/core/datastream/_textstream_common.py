import io
import os
from abc import ABC, abstractmethod

class TextstreamCommon(ABC):
    """
    Common superclass for many of the implementations of backends for streaming text data.
    """

    _f: io.TextIOBase | None
    _closed: bool

    @abstractmethod
    def _ensure_f(self) -> io.TextIOBase:
        pass
    
    def unwrap(self) -> io.TextIOBase:
        return self._ensure_f()

    def read(self, size: int = -1) -> str:
        return self._ensure_f().read(size)

    def close(self) -> None:
        if self._f is not None and not self._f.closed:
            self._f.close()
        self._closed = True

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self._ensure_f().seek(offset, whence)

    def tell(self) -> int:
        return self._ensure_f().tell()
