from abc import ABC, abstractmethod


class TextstreamAPI(ABC):
    """
    Abstract base class for a bare minimum API for streamable text data.

    Supports:
    * read, close, name, and closed with the meanings defined by io.IOBase

    Since it is a *minimal* streaming data API it deliberately omits:
    seek, tell, etc.; there should be no assumption that the underlying
    data source is seekable. However, many backend implementations
    may chose to support them.
    """

    @abstractmethod
    def read(self, size: int = -1) -> str:
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
