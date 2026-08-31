"""Deterministic filesystem records for signed manifests and seals.

A *record list* is the canonical description of what a directory tree contained
at one moment: one entry per file, symlink, and directory, sorted by path, with
a file's size, SHA-256, and owner-execute bit. It never follows symlinks, so a
symlink is recorded by its target rather than by what it points at. The same
record list underlies both the signed project manifest and every seal, so a
covered byte cannot change without a later verification noticing.
"""

import os
import stat
from collections.abc import Callable, Iterator, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from .digests import sha256_file

__all__ = ["file_records"]


def _excluded(relative: str, patterns: Sequence[str]) -> bool:
    return any(fnmatchcase(relative, pattern) for pattern in patterns)


def file_records(
    root: str | os.PathLike[str],
    *,
    exclusions: Sequence[str] = (),
    skip: Callable[[Path], bool] | None = None,
) -> list[dict[str, object]]:
    """Return the sorted, deterministic records of the tree rooted at *root*.

    Symlinks are never followed: a symlink is recorded as its target text and a
    directory is recorded as its own entry before its contents. A file record
    carries its ``size``, ``sha256``, and ``executable`` (the owner-execute
    bit). Two seams keep out what a record list must not cover: *exclusions* are
    ``fnmatch`` patterns matched case-sensitively against each entry's posix
    relpath, and *skip*, when given, is a predicate on the absolute path of each
    entry — an entry it accepts is left out entirely, and a directory it accepts
    is not descended into.

    :param root: The directory tree to describe.
    :param exclusions: ``fnmatch`` patterns on posix relpaths to leave out.
    :param skip: A predicate on absolute paths; a truthy result omits the entry.
    :return: The record dictionaries, sorted by posix relpath.
    :raises ValueError: If the tree holds a special filesystem entry.
    """

    base = Path(root)
    paths: list[Path] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as scan:
            for raw in scan:
                entry = Path(raw.path)
                relative = entry.relative_to(base).as_posix()
                if _excluded(relative, exclusions):
                    continue
                if skip is not None and skip(entry):
                    continue
                mode = raw.stat(follow_symlinks=False).st_mode
                paths.append(entry)
                if stat.S_ISDIR(mode):
                    visit(entry)

    visit(base)
    return list(_emit(base, paths))


def _emit(base: Path, paths: Sequence[Path]) -> Iterator[dict[str, object]]:
    for entry in sorted(paths, key=lambda item: item.relative_to(base).as_posix()):
        relative = entry.relative_to(base).as_posix()
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode):
            yield {"path": relative, "type": "symlink", "target": os.readlink(entry)}
        elif stat.S_ISDIR(mode):
            yield {"path": relative, "type": "directory"}
        elif stat.S_ISREG(mode):
            yield {
                "path": relative,
                "type": "file",
                "size": entry.stat().st_size,
                "sha256": sha256_file(entry),
                "executable": bool(mode & 0o100),
            }
        else:
            raise ValueError(f"record list rejects special filesystem entry: {relative}")
