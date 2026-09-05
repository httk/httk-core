# Datastreams

Datastreams let a function accept data however the caller has it — a filename,
an open file, in-memory content, or (with explicit consent) a URL — and
normalize it once. Accept the `*Like` union, build the view your algorithm
wants, and write against that view only (the pattern from
{doc}`view_backend_pattern`):

```python
from httk.core import TextstreamFileView, TextstreamLike


def count_nonempty_lines(slike: TextstreamLike, **hints: object) -> int:
    stream = TextstreamFileView(slike, **hints)
    return sum(1 for line in stream if line.strip())


count_nonempty_lines("POSCAR")            # a filename
count_nonempty_lines("a\n\nb", kind="content")  # raw content, disambiguated
```

Two parallel families exist: `Textstream*` for text and `Bytestream*` for
bytes. Compressed files (`.gz`, `.bz2`, `.xz`) decompress transparently on
read, and in-memory gzip is sniffed by default.

Bare URL strings never open the network — they raise `PermissionError`.
Consent is explicit: `httk.core.fetch(url)` for eager download, the lazy
`DatastreamURL(url)` token, or a `urllib.request.Request` object.

The full guide, {doc}`details/datastreams`, covers every backend and view,
string- versus streaming-oriented functions, byte streams, request handling
and timeouts, compression control, and shared stream-state behavior with
`unwrap`.
