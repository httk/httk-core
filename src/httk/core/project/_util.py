"""Private JSON helpers for the project anchor.

The on-disk representation of ``project.json`` is deliberately identical, byte
for byte, to the one *httk-workflow* wrote before the anchor moved here, so a
project initialized by either release reads unchanged by the other. That means
the same compact, key-sorted, non-ASCII-preserving encoding with a trailing
newline, written atomically by rename.
"""

import json
import os
import tempfile
from pathlib import Path


def json_bytes(value: object) -> bytes:
    """Encode compact, deterministic UTF-8 JSON."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def write_json_atomic(path: Path, value: object) -> None:
    """Atomically replace *path* with the JSON encoding of *value*."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json_bytes(value))
            handle.write(b"\n")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
