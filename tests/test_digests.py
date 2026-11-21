"""Tests for file and tree digests."""

import bz2
import gzip
import hashlib
import lzma
import os
import sys
from pathlib import Path

import pytest

from httk.core.digests import content_sha256_file, sha256_file, tree_digest


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


_ZSTD_MODULE = "compression.zstd" if sys.version_info >= (3, 14) else "backports.zstd"


def test_content_sha256_file_hashes_decompressed_bytes(tmp_path: Path) -> None:
    plain = b"EIGENVAL\n" * 1000
    zstd = pytest.importorskip(_ZSTD_MODULE)
    for suffix, compress in (
        (".zst", zstd.compress),
        (".gz", gzip.compress),
        (".bz2", bz2.compress),
        (".xz", lzma.compress),
    ):
        path = tmp_path / f"EIGENVAL{suffix}"
        path.write_bytes(compress(plain))
        assert content_sha256_file(path) == hashlib.sha256(plain).hexdigest()
        assert sha256_file(path) != hashlib.sha256(plain).hexdigest()
    (tmp_path / "EIGENVAL").write_bytes(plain)
    assert content_sha256_file(tmp_path / "EIGENVAL") is None
    assert content_sha256_file(str(tmp_path / "EIGENVAL")) is None


def test_content_sha256_file_max_bytes_bounds_decompression(tmp_path: Path) -> None:
    zstd = pytest.importorskip(_ZSTD_MODULE)
    plain = bytes(8 * 1024 * 1024)
    bomb = tmp_path / "zeros.zst"
    bomb.write_bytes(zstd.compress(plain))
    with pytest.raises(ValueError, match="max_bytes=1048576"):
        content_sha256_file(bomb, max_bytes=1024 * 1024)
    assert content_sha256_file(bomb, max_bytes=None) == hashlib.sha256(plain).hexdigest()
    assert content_sha256_file(bomb, max_bytes=len(plain)) == hashlib.sha256(plain).hexdigest()


def test_content_sha256_file_garbage_raises(tmp_path: Path) -> None:
    zstd = pytest.importorskip(_ZSTD_MODULE)
    garbage = tmp_path / "x.zst"
    garbage.write_bytes(b"not zstandard data")
    with pytest.raises(zstd.ZstdError):
        content_sha256_file(garbage)


def test_content_sha256_file_refuses_special_files(tmp_path: Path) -> None:
    (tmp_path / "d.zst").mkdir()
    with pytest.raises(IsADirectoryError):
        content_sha256_file(tmp_path / "d.zst")
    if not hasattr(os, "mkfifo"):
        pytest.skip("os.mkfifo is unavailable")
    os.mkfifo(tmp_path / "x.zst")
    with pytest.raises(ValueError, match="not a regular file"):
        content_sha256_file(tmp_path / "x.zst")
