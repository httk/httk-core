"""Compute deterministic SHA-256 digests for files and directory trees.

Hash tree paths and entries in sorted order without following symlinks.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

__all__ = ["sha256_file", "tree_digest"]


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one regular file.

    :param path: Regular file to hash.
    :return: Lowercase SHA-256 digest.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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
            with entry.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
        else:
            raise ValueError(f"special file is forbidden in immutable bundle: {entry}")
    return digest.hexdigest()
