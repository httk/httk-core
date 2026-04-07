import io
from pathlib import Path
from typing import TypeAlias

from .bytestream_backend import BytestreamBackend
from .bytestream_view import BytestreamView

BytestreamLike: TypeAlias = BytestreamBackend | BytestreamView | io.IOBase | io.BytesIO | bytes | bytearray | str | Path
