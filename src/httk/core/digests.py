"""Compute deterministic SHA-256 digests for files and directory trees.

Hash tree paths and entries in sorted order without following symlinks.
"""

import errno
import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path

__all__ = ["sha256_file", "tree_digest"]


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one regular file.

    The file is opened without blocking and checked with ``fstat`` before any
    read, so a FIFO or device in its place is refused instead of hanging or
    feeding the digest. A symlink is followed, as before.

    :param path: Regular file to hash.
    :return: Lowercase SHA-256 digest.
    :raises ValueError: If *path* is a FIFO, device, socket, or other special file.
    :raises OSError: If *path* cannot be opened, or is a directory.
    """

    digest = hashlib.sha256()
    _hash_regular_file(digest.update, path, follow_symlinks=True)
    return digest.hexdigest()


def _hash_regular_file(update: Callable[[bytes], object], path: Path, *, follow_symlinks: bool) -> None:
    """Feed one regular file to *update*, refusing anything else without blocking.

    The file is opened ``O_NONBLOCK`` (and ``O_NOFOLLOW`` unless
    *follow_symlinks*) and checked with ``fstat`` before any read, so an entry
    swapped for a FIFO, device or symlink after it was classified is refused.
    """

    nonblocking = getattr(os, "O_NONBLOCK", 0)
    flags = os.O_RDONLY | nonblocking | getattr(os, "O_CLOEXEC", 0)
    if not follow_symlinks:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if not follow_symlinks and exc.errno == errno.ELOOP:
            raise ValueError(f"symlink is forbidden in immutable bundle: {path}") from exc
        raise
    try:
        mode = os.fstat(descriptor).st_mode
        if stat.S_ISDIR(mode):
            # As opening a directory for reading always reported it.
            raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(path))
        if not stat.S_ISREG(mode):
            raise ValueError(f"not a regular file: {path}")
        if nonblocking:
            os.set_blocking(descriptor, True)
        while chunk := os.read(descriptor, 1024 * 1024):
            update(chunk)
    finally:
        os.close(descriptor)


def tree_digest(
    path: Path,
    *,
    skip: Callable[[str], bool] | None = None,
    exclude: Callable[[str], bool] | None = None,
) -> str:
    """Hash a tree without following symlinks.

    *skip* names top-level entries to leave out of the digest entirely.
    *exclude* names relative POSIX paths to leave out; excluding a directory
    also leaves out its descendants.

    :param path: Root directory to hash.
    :param skip: Optional predicate for top-level entries to omit.
    :param exclude: Optional predicate for relative POSIX paths to omit.
    :return: Lowercase SHA-256 digest.
    :raises ValueError: If the tree contains a symlink or special file.
    """

    digest = hashlib.sha256()
    excluded_directories: list[str] = []
    for entry in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        parts = entry.relative_to(path).parts
        relative_text = entry.relative_to(path).as_posix()
        if skip is not None and parts and skip(parts[0]):
            continue
        if any(relative_text.startswith(directory + "/") for directory in excluded_directories):
            continue
        if exclude is not None and exclude(relative_text):
            if entry.is_dir():
                excluded_directories.append(relative_text)
            continue
        relative = relative_text.encode()
        if entry.is_symlink():
            raise ValueError(f"symlink is forbidden in immutable bundle: {entry}")
        if entry.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif entry.is_file():
            digest.update(b"F\0" + relative + b"\0")
            # Opened without following or blocking: an entry swapped for a
            # symlink or FIFO since it was classified is refused, not read.
            _hash_regular_file(digest.update, entry, follow_symlinks=False)
        else:
            raise ValueError(f"special file is forbidden in immutable bundle: {entry}")
    return digest.hexdigest()
