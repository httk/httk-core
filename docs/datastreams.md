# Datastreams

This page documents practical usage of the datastream classes in `httk.core.datastream`.
It covers both text and byte data and shows how to write functions that accept flexible input types.

## Overview

Datastream support is split into two parallel families:

- text:
  - backends: `TextstreamFile`, `TextstreamFilename`, `TextstreamString`
  - views: `TextstreamFileView`, `TextstreamFilenameView`, `TextstreamStringView`
  - accepted union: `TextstreamLike`
- bytes:
  - backends: `BytestreamFile`, `BytestreamFilename`, `BytestreamBytes`
  - views: `BytestreamFileView`, `BytestreamFilenameView`, `BytestreamBytesView`
  - accepted union: `BytestreamLike`

In normal user code, you usually accept `*Like` and normalize immediately to one view.

## Textstream

### Common Calling Patterns

```python
from pathlib import Path

from httk.core.datastream import TextstreamStringView

# filename (str)
TextstreamStringView("README.md")

# filename (Path)
TextstreamStringView(Path("README.md"))

# open text file object
with open("README.md", "r") as f:
    TextstreamStringView(f)

# raw string content (disambiguate with kind="content")
TextstreamStringView("line1\nline2\n", kind="content")
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
- `str` input is ambiguous and defaults to filename resolution unless `kind="content"` is passed.
- `TextstreamFilenameView` requires an underlying name; it raises `TypeError` when no filename exists.

## Bytestream

### Common Calling Patterns

```python
from pathlib import Path

from httk.core import BytestreamBytesView

# filename (str)
BytestreamBytesView("payload.bin")

# filename (Path)
BytestreamBytesView(Path("payload.bin"))

# open binary file object
with open("payload.bin", "rb") as f:
    BytestreamBytesView(f)

# raw bytes or bytearray
BytestreamBytesView(b"\x00\x01\x02")
BytestreamBytesView(bytearray([0, 1, 2]))
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
- For explicit interpretation when needed, pass `kind="filename"`, `kind="file"`, or `kind="content"`.

## Shared Behavior and `unwrap`

All views/backends share two important behaviors:

- view/backends over the same underlying object share state:
  - reads advance shared position
  - close in one place closes for all
- `unwrap(obj)` returns the most raw representation available:
  - for stream backends/views this is commonly an `io` object
  - for non-view/backend objects it returns the object unchanged
