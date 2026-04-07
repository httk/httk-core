import io
from pathlib import Path
from typing import TypeAlias

from .textstream_backend import TextstreamBackend
from .textstream_view import TextstreamView

# TextstreamView: TypeAlias = TextstreamFileView | TextstreamFilenameView | TextstreamStringView
# TextstreamImplementation: TypeAlias = TextstreamFile | TextstreamFilename | TextstreamString
TextstreamLike: TypeAlias = TextstreamBackend | TextstreamView | io.TextIOBase | io.StringIO | str | Path
