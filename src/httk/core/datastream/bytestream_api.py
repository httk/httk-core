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
        """Read up to ``size`` bytes, or all remaining bytes when ``size`` is negative.

        :param size: Maximum number of bytes to read.
        :return: The bytes read from the stream.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close the stream."""
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str | None:
        """Expose the source name when one exists."""
        raise NotImplementedError

    @property
    @abstractmethod
    def closed(self) -> bool:
        """Report whether the stream is closed."""
        raise NotImplementedError
