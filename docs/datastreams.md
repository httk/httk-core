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

## Textstream

### Common Calling Patterns

```python
import urllib.request
from pathlib import Path

from httk.core.datastream import TextstreamStringView

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

# remote content via a URL string (requires explicit kind="url")
TextstreamStringView("https://example.com/data.txt", kind="url")
```

### Example: String-Oriented Function

```python
from httk.core import TextstreamStringView
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
- `str` input is ambiguous and defaults to filename resolution unless `kind="content"` or `kind="url"` is passed.
- `TextstreamFilenameView` requires an underlying name; it raises `TypeError` when no filename exists.
- Remote text is decoded using the `encoding` hint if given, else the HTTP Content-Type charset, else utf-8.
- See [Remote Content (Request / URL)](#remote-content-request-url) for shared remote-fetch behavior.

## Bytestream

### Common Calling Patterns

```python
import urllib.request
from pathlib import Path

from httk.core import BytestreamBytesView

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

# remote content via a URL string (requires explicit kind="url")
BytestreamBytesView("https://example.com/payload.bin", kind="url")
```

### Example: Bytes-Oriented Function

```python
import hashlib

from httk.core import BytestreamBytesView, BytestreamLike


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
- For explicit interpretation when needed, pass `kind="filename"`, `kind="file"`, `kind="content"`, `kind="request"`, or `kind="url"`.
- See [Remote Content (Request / URL)](#remote-content-request-url) for shared remote-fetch behavior.

## Remote Content (Request / URL)

Both families can fetch remote content through Python's built-in `urllib.request`:

- A `urllib.request.Request` object is unambiguous and is accepted directly anywhere a `*Like` is accepted.
  Use a `Request` when you need headers, a method, or a request body; it is passed to `urllib.request.urlopen` as-is.
- A URL passed as a plain `str` is only interpreted as a URL with an explicit `kind="url"` hint.
  This is deliberate: a bare string always means a filename (or content), so handing untrusted strings
  to `*Like`-accepting functions never triggers implicit network access.

Remote backends fetch lazily: the connection is opened on first read, not when the backend or view is
created. Note that `unwrap()` also opens the connection, since it returns the underlying response object.
An optional `timeout` hint (in seconds) is forwarded to `urlopen`.

`TextstreamRequestView`/`TextstreamURLView` and their byte counterparts are the URL-facing analogues of
`*FilenameView`: they present the *source location* of a backend rather than its data. A `*URLView` is a
`str` holding the URL; a `*RequestView` is a genuine `urllib.request.Request` (preserving headers/data when
built from a request backend) and can be passed to any code that expects one. Symmetrically to
`*FilenameView` raising `TypeError` for backends with no filename, these views raise `TypeError` for
backends with no underlying URL — and remote backends have no `name`, so `*FilenameView` raises for them.

```python
import urllib.request

from httk.core import TextstreamRequestView

req = TextstreamRequestView("https://example.com/data.txt", kind="url")
# req is a urllib.request.Request and can be handed to code that expects one:
with urllib.request.urlopen(req) as resp:
    ...
```

## Shared Behavior and `unwrap`

All views/backends share two important behaviors:

- view/backends over the same underlying object share state:
  - reads advance shared position
  - close in one place closes for all
- `unwrap(obj)` returns the most raw representation available:
  - for stream backends/views this is commonly an `io` object
  - for non-view/backend objects it returns the object unchanged
