import io
import pathlib
import urllib.request

from . import bytestream_backend, bytestream_view

type BytestreamLike = (
    bytestream_backend.BytestreamBackend
    | bytestream_view.BytestreamView
    | io.IOBase
    | io.BytesIO
    | bytes
    | bytearray
    | str
    | pathlib.Path
    | urllib.request.Request
)
