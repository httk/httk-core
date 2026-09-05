"""Exception-safe local file replacement for filename-sensitive format writers."""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

__all__ = ["atomic_destination"]


@contextmanager
def atomic_destination(destination: str | os.PathLike[str]) -> Iterator[Path]:
    """Yield a same-filesystem staging path and publish it only on success.

    Follow symlinks, preserve existing permission bits, and retain the requested
    basename for filename-sensitive writers. Replacing a hard link leaves its
    other links unchanged. This does not provide crash durability or serialize
    concurrent writers. The caller must close all output streams before exit.

    :param destination: Output filename whose resolved parent directory exists.
    :yields: A staging path retaining the requested basename for the writer.
    :raises ValueError: If the resolved destination exists and is not a regular file.
    :raises OSError: If staging or publishing the output fails.
    """
    requested = Path(destination)
    target = requested.resolve()
    try:
        previous = target.stat()
    except FileNotFoundError:
        mode = None
    else:
        if not stat.S_ISREG(previous.st_mode):
            raise ValueError(f"save destination must be a regular file: {destination}")
        mode = stat.S_IMODE(previous.st_mode)
    with TemporaryDirectory(prefix=".httk-save-", dir=target.parent) as directory:
        staged = Path(directory) / requested.name
        yield staged
        if mode is not None:
            staged.chmod(mode)
        os.replace(staged, target)
