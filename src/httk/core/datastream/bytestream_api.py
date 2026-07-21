from abc import ABC, abstractmethod


class BytestreamAPI(ABC):
    """
    Abstract base class for a bare minimum API for streamable byte data.

    Supports:
    * read, close, name, and closed with the meanings defined by io.IOBase

    Since it is a *minimal* streaming data API it deliberately omits:
    seek, tell, etc.; there should be no assumption that the underlying
    data source is seekable. However, many backend implementations
    may choose to support them.
    """

    @abstractmethod
    def read(self, size: int = -1) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str | None:
        raise NotImplementedError

    @property
    @abstractmethod
    def closed(self) -> bool:
        raise NotImplementedError
