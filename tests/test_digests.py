"""Tests for file and tree digests."""

import hashlib
import os
from pathlib import Path

import pytest

from httk.core.digests import sha256_file, tree_digest


def _write_tree(root: Path) -> None:
    (root / "nested").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "alpha").write_bytes(b"alpha")
    (root / "nested" / "beta").write_bytes(b"beta")


def test_same_content_has_same_digest(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_tree(first)
    _write_tree(second)

    assert tree_digest(first) == tree_digest(second)


def test_file_changes_and_renames_change_digest(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    _write_tree(root)
    original = tree_digest(root)

    (root / "alpha").write_bytes(b"alphA")
    changed = tree_digest(root)
    assert changed != original

    (root / "alpha").rename(root / "renamed")
    assert tree_digest(root) != changed


def test_directory_entries_affect_digest(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    original = tree_digest(root)
    (root / "empty").mkdir()

    assert tree_digest(root) != original


def test_exclude_omits_a_subtree(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    _write_tree(root)
    expected = tmp_path / "expected"
    _write_tree(expected)
    (expected / "nested" / "beta").unlink()
    (expected / "nested").rmdir()

    assert tree_digest(root, exclude=lambda relative: relative == "nested") == tree_digest(expected)


def test_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "target").write_bytes(b"target")
    (root / "link").symlink_to("target")

    with pytest.raises(ValueError, match="symlink is forbidden"):
        tree_digest(root)


def test_special_file_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    fifo = root / "fifo"
    if not hasattr(os, "mkfifo"):
        pytest.skip("os.mkfifo is unavailable")
    os.mkfifo(fifo)

    with pytest.raises(ValueError, match="special file is forbidden"):
        tree_digest(root)


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "data"
    content = b"digest me\0"
    path.write_bytes(content)

    assert sha256_file(path) == hashlib.sha256(content).hexdigest()
