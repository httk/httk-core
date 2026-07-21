import io
import pathlib

from . import textstream_backend, textstream_view

type TextstreamLike = (
    textstream_backend.TextstreamBackend
    | textstream_view.TextstreamView
    | io.TextIOBase
    | io.StringIO
    | str
    | pathlib.Path
)
