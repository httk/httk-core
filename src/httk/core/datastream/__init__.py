from .bytestream_backend import BytestreamBackend
from .bytestream_bytes import BytestreamBytes
from .bytestream_bytes_view import BytestreamBytesView
from .bytestream_common import BytestreamCommon
from .bytestream_file import BytestreamFile
from .bytestream_file_view import BytestreamFileView
from .bytestream_filename import BytestreamFilename
from .bytestream_filename_view import BytestreamFilenameView
from .bytestream_like import BytestreamLike
from .bytestream_request import BytestreamRequest
from .bytestream_request_view import BytestreamRequestView
from .bytestream_url import BytestreamURL
from .bytestream_url_view import BytestreamURLView
from .bytestream_view import BytestreamView
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon
from .textstream_file import TextstreamFile
from .textstream_file_view import TextstreamFileView
from .textstream_filename import TextstreamFilename
from .textstream_filename_view import TextstreamFilenameView
from .textstream_like import TextstreamLike
from .textstream_request import TextstreamRequest
from .textstream_request_view import TextstreamRequestView
from .textstream_string import TextstreamString
from .textstream_string_view import TextstreamStringView
from .textstream_url import TextstreamURL
from .textstream_url_view import TextstreamURLView
from .textstream_view import TextstreamView

BytestreamBackend.backend_classes = [
    BytestreamFile,
    BytestreamFilename,
    BytestreamBytes,
    BytestreamRequest,
    BytestreamURL,
]
TextstreamBackend.backend_classes = [
    TextstreamFile,
    TextstreamFilename,
    TextstreamString,
    TextstreamRequest,
    TextstreamURL,
]

__all__ = [
    "BytestreamView",
    "BytestreamFileView",
    "BytestreamFilenameView",
    "BytestreamBytesView",
    "BytestreamRequestView",
    "BytestreamURLView",
    "BytestreamBackend",
    "BytestreamCommon",
    "BytestreamFile",
    "BytestreamFilename",
    "BytestreamBytes",
    "BytestreamRequest",
    "BytestreamURL",
    "BytestreamLike",
    "TextstreamView",
    "TextstreamFileView",
    "TextstreamFilenameView",
    "TextstreamStringView",
    "TextstreamRequestView",
    "TextstreamURLView",
    "TextstreamBackend",
    "TextstreamCommon",
    "TextstreamFile",
    "TextstreamFilename",
    "TextstreamString",
    "TextstreamRequest",
    "TextstreamURL",
    "TextstreamLike",
]
