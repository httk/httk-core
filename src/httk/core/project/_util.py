"""Private JSON helpers for the project anchor.

The on-disk representation of ``project.json`` is shared with *httk-workflow*:
compact, key-sorted, non-ASCII-preserving encoding with a trailing newline,
written atomically by rename.
"""

import json
import os
import tempfile
from pathlib import Path


def json_bytes(value: object) -> bytes:
    """Encode compact, deterministic UTF-8 JSON."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def read_json(path: Path) -> dict[str, object]:
    """Read a JSON object from *path*.

    :param path: File to read.
    :return: The decoded JSON object.
    :raises ValueError: If the file cannot be read or does not hold a JSON object.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json_atomic(path: Path, value: object, *, durable: bool = False) -> None:
    """Atomically replace *path* with the JSON encoding of *value*.

    :param path: File to replace.
    :param value: JSON-encodable value to write.
    :param durable: Whether to ``fsync`` the file and its directory so the write survives a crash.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json_bytes(value))
            handle.write(b"\n")
            if durable:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temporary, path)
        if durable:
            _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
