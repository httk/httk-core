# Datastreams

This page documents practical usage of the datastream classes in `httk.core.datastream`.
It covers both text and byte data and shows how to write functions that accept flexible input types.

## Overview

Datastream support is split into two parallel families:

- text:
  - backends: `TextstreamFile`, `TextstreamFilename`, `TextstreamString`, `TextstreamRequest`, `TextstreamURL`
  - views: `TextstreamFileView`, `TextstreamFilenameView`, `TextstreamStringView`, `TextstreamRequestView`, `TextstreamURLView`
  - accepted union: `TextstreamLike`
- bytes:
  - backends: `BytestreamFile`, `BytestreamFilename`, `BytestreamBytes`, `BytestreamRequest`, `BytestreamURL`
  - views: `BytestreamFileView`, `BytestreamFilenameView`, `BytestreamBytesView`, `BytestreamRequestView`, `BytestreamURLView`
  - accepted union: `BytestreamLike`

In normal user code, you usually accept `*Like` and normalize immediately to one view.

### Network consent

Bare URL strings never open the network: they raise `PermissionError` with guidance.
Explicit consent is provided by the lazy `DatastreamURL` token, eager `httk.core.fetch`,
`urllib.request.Request`, the `*URLView`s, or `kind="url"`. The default network timeout
is 30 seconds. `file://` URLs are local.

## Textstream

### Common Calling Patterns

```python
import urllib.request
from pathlib import Path

from httk.core.datastream import TextstreamFileView, TextstreamStringView

# filename (str)
TextstreamStringView("README.md")

# filename (Path)
TextstreamStringView(Path("README.md"))

# already-open text file object: mainly useful when other code you do not
# control opened the file for you; when starting from a filename, pass it
# directly instead (as in the first example)
with open("README.md", "r") as f:
    TextstreamStringView(f)

# raw string content (disambiguate with kind="content")
TextstreamStringView("line1\nline2\n", kind="content")

# remote content via a urllib request object
TextstreamStringView(urllib.request.Request("https://example.com/data.txt"))

# remote content with explicit consent
TextstreamFileView("https://example.com/data.txt", kind="url")
```

### Example: String-Oriented Function

```python
from httk.core.datastream import TextstreamStringView
from httk.core import TextstreamLike


def header_text(slike: TextstreamLike, **hints: object) -> str:
    text = TextstreamStringView(slike, **hints)
    return text.splitlines()[0] if text else ""
```

Use `TextstreamStringView` when the algorithm naturally wants complete in-memory string data.

### Example: Streaming Function

```python
from httk.core import TextstreamFileView
from httk.core import TextstreamLike


def count_nonempty_lines(slike: TextstreamLike, **hints: object) -> int:
    stream = TextstreamFileView(slike, **hints)
    return sum(1 for line in stream if line.strip())
```

Use `TextstreamFileView` when line-by-line processing is natural and you do not want eager full materialization.

### Textstream Notes

- `TextstreamStringView` is eager: it reads remaining stream content immediately.
- A bare URL string never opens the network: it raises `PermissionError` with guidance to use an explicit consent object. `file://` is local. Any other `str` defaults to filename resolution.
- `TextstreamFilenameView` requires an underlying name; it raises `TypeError` when no filename exists.
- Remote text is decoded using the `encoding` hint if given, else the HTTP Content-Type charset, else utf-8. `TextstreamFilename` reads local files as utf-8 by default; pass `encoding` to override.
- See [Remote Content (Request / URL)](#remote-content-request-url) for shared remote-fetch behavior and [Compressed Content](#compressed-content) for transparent decompression.

## Bytestream

### Common Calling Patterns

```python
import urllib.request
from pathlib import Path

from httk.core.datastream import BytestreamBytesView
from httk.core import BytestreamFileView

# filename (str)
BytestreamBytesView("payload.bin")

# filename (Path)
BytestreamBytesView(Path("payload.bin"))

# already-open binary file object: mainly useful when other code you do not
# control opened the file for you; when starting from a filename, pass it
# directly instead (as in the first example)
with open("payload.bin", "rb") as f:
    BytestreamBytesView(f)

# raw bytes or bytearray
BytestreamBytesView(b"\x00\x01\x02")
BytestreamBytesView(bytearray([0, 1, 2]))

# remote content via a urllib request object
BytestreamBytesView(urllib.request.Request("https://example.com/payload.bin"))

# remote content with explicit consent
BytestreamFileView("https://example.com/payload.bin", kind="url")
```

### Example: Bytes-Oriented Function

```python
import hashlib

from httk.core.datastream import BytestreamBytesView
from httk.core import BytestreamLike


def digest_payload(blike: BytestreamLike, **hints: object) -> str:
    payload = BytestreamBytesView(blike, **hints)
    return hashlib.sha256(payload).hexdigest()
```

### Example: Chunked Streaming Function

```python
from httk.core import BytestreamFileView, BytestreamLike


def first_chunk(blike: BytestreamLike, size: int = 4096, **hints: object) -> bytes:
    stream = BytestreamFileView(blike, **hints)
    return stream.read(size)
```

### Bytestream Notes

- `BytestreamBytesView` is eager: it reads remaining stream content immediately.
- `BytestreamFilenameView` requires an underlying name and raises `TypeError` if unavailable.
- A bare URL string never opens the network and raises `PermissionError` with guidance. `file://` is local. Any other `str` defaults to a filename.
- For explicit interpretation when needed, pass `kind="filename"`, `kind="file"`, `kind="content"`, `kind="request"`, or `kind="url"`; `kind="url"` is explicit network consent.
- See [Remote Content (Request / URL)](#remote-content-request-url) for shared remote-fetch behavior and [Compressed Content](#compressed-content) for transparent decompression.

## Remote Content (Request / URL)

Both families can fetch remote content through Python's built-in `urllib.request`:

- A `urllib.request.Request` object is unambiguous and is accepted directly anywhere a `*Like` is accepted.
  Use a `Request` when you need headers, a method, or a request body; it is passed to `urllib.request.urlopen` as-is.
- A bare URL string never opens the network and raises `PermissionError` with guidance. A schemeless string means a
  filename (or, with `kind="content"`, literal content). Explicit consent is provided by `DatastreamURL`,
  `urllib.request.Request`, a `*URLView`, or `kind="url"`; `file://` is local.

Remote backends fetch lazily: the connection is opened on first read, not when the backend or view is
created. Note that `unwrap()` also opens the connection, since it returns the underlying response object.
An optional `timeout` hint (in seconds) is forwarded to `urlopen`.
The default network timeout is 30 seconds.

`DatastreamURL` is a lazy consent token: constructing it validates the URL and stores an optional timeout, but performs
no network I/O. `httk.core.fetch(url)` is the eager alternative. `TextstreamRequestView`/`TextstreamURLView` and their byte counterparts are the URL-facing analogues of
`*FilenameView`: they present the *source location* of a backend rather than its data. A `*URLView` is a
`str` holding the URL; a `*RequestView` is a genuine `urllib.request.Request` (preserving headers/data when
built from a request backend) and can be passed to any code that expects one. Symmetrically to
`*FilenameView` raising `TypeError` for backends with no filename, these views raise `TypeError` for
backends with no underlying URL — and remote backends have no `name`, so `*FilenameView` raises for them.

The token is intended for lazy consumers that accept `DatastreamLike`-style
inputs. A plain string remains a path; the token says that this source is a
URL which the consumer may fetch when its data is first needed.

```python
from httk.atomistic import UnitcellStructureView
from httk.core import DatastreamURL, fetch

url = "https://example.org/data.cif"
consent = DatastreamURL(url, timeout=10)  # validates; performs no I/O
structure = UnitcellStructureView(consent)
cell = structure.cell  # fetches and parses lazily, on first data access

# fetch() is the eager alternative.
result = fetch(url, timeout=10, kind="load")
```

`UnitcellStructureView` accepts the token through the atomistic structure
input union and resolves it through the existing fetch/reader machinery. Any
consumer whose input contract declares `DatastreamLike` can participate in
the same lazy-consent protocol.

```python
import urllib.request

from httk.core.datastream import TextstreamRequestView

req = TextstreamRequestView("https://example.com/data.txt", kind="url")
# req is a urllib.request.Request and can be handed to code that expects one:
with urllib.request.urlopen(req) as resp:
    ...
```

## Compressed Content

Compression is an orthogonal layer *below* the backends: it turns a compressed byte stream into
an uncompressed one (and, for text, before decoding), independently of where the bytes come from.
The same codecs therefore apply to filenames, open files, raw bytes, and remote responses, so a
`data.json.gz` filename or a gzipped URL loads with no extra ceremony. The stdlib codecs `gzip`,
`bzip2`, `xz`, and `lzma` are built in.

A `compression` hint (parallel to `kind`) selects how a codec is chosen:

- `"auto"` — use the filename extension if it is a known compression suffix, otherwise sniff the
  leading magic bytes.
- `"detect"` — always sniff the magic bytes, ignoring the extension.
- `"extension"` — decide from the name only; never sniff.
- `"none"` — no decompression.
- a registered codec name (e.g. `"gzip"`) — force that codec; an unknown name raises `ValueError`.

Defaults depend on the source: filename-based backends default to `"extension"` (a `data.json.gz`
name decompresses, a compressed file with a plain name does not unless you ask); all other
byte-producing sources — open files, raw bytes, `Request`, and URL strings — default to `"auto"`.
Resolution is lazy: like the rest of the stream layer, the extension check or magic sniff only runs
on the first read, and sniffing never consumes data. Compression does not apply to text-native
sources (an already-open text stream or a literal string); for those, only the no-op modes are
accepted and a codec name or `"detect"` raises `ValueError`.

```python
import gzip

from httk.core.datastream import BytestreamBytesView
from httk.core import DatasetLoader

# Transparent: extension recognized, decompressed on read.
DatasetLoader("symmetry", "data/spacegroups.json.gz")

# In-memory gzip is sniffed by default ("auto").
BytestreamBytesView(gzip.compress(b"payload"))  # -> b"payload"

# Force or disable decompression explicitly.
BytestreamBytesView("blob.dat", compression="gzip")
BytestreamBytesView("archive.gz", compression="none")  # raw compressed bytes
```

Register additional codecs (for example, a third-party `zstd`) with `register_compression`;
`known_compressions()` lists the registered names.

```python
import io

from httk.core import CompressionCodec, register_compression

register_compression(
    CompressionCodec(
        name="zstd",
        extensions=(".zst",),
        magics=(b"\x28\xb5\x2f\xfd",),
        open_stream=lambda stream: io.BytesIO(...),  # return a decompressed binary stream
    )
)
```

Archives (`.tar.*`, `.zip`), write-side compression, and HTTP `Content-Encoding` negotiation are
out of scope for this layer.

## Loading files by type

`httk.core.load` and its reader registry are documented in {doc}`registry`;
see the {ref}`readers` section for dispatch details.
Datastreams supply the reader with local or remote streaming input, including
transparent decompression.

## Shared Behavior and `unwrap`

Views and backends for one datastream share the same stream state:

- reads through one view advance the position seen by the others, and closing
  one closes the backend for all views;
- `unwrap` on a text or byte backend/view returns its concrete underlying
  `io.TextIOBase` or `io.IOBase`, creating the lazy stream if needed;
- string and bytes views still unwrap through their backends to those `io`
  objects, while filename and URL views unwrap to the corresponding opened
  stream rather than to their displayed `str` value;
- raw `str`, `bytes`, and `Path` values passed directly to `unwrap` are
  returned unchanged;
- `unwrap` on an object that is not a datastream backend or view returns that
  object unchanged.
