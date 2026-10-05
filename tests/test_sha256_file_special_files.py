"""``sha256_file`` refuses special files without blocking and keeps its digests."""

import hashlib
import os
import threading
from pathlib import Path

import pytest

from httk.core.digests import sha256_file


def test_a_regular_file_digest_is_unchanged(tmp_path: Path) -> None:
    content = os.urandom(3 * 1024 * 1024 + 17)
    path = tmp_path / "file"
    path.write_bytes(content)
    assert sha256_file(path) == hashlib.sha256(content).hexdigest()
    (tmp_path / "empty").write_bytes(b"")
    assert sha256_file(tmp_path / "empty") == hashlib.sha256(b"").hexdigest()


def test_a_symlink_to_a_regular_file_is_still_followed(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"content")
    (tmp_path / "link").symlink_to(tmp_path / "file")
    assert sha256_file(tmp_path / "link") == hashlib.sha256(b"content").hexdigest()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs need a POSIX platform")
def test_a_fifo_is_refused_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    outcome: list[BaseException | str] = []

    def target() -> None:
        try:
            outcome.append(sha256_file(fifo))
        except BaseException as exc:
            outcome.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(5.0)
    assert not thread.is_alive(), "sha256_file blocked on a FIFO"
    assert isinstance(outcome[0], ValueError) and "not a regular file" in str(outcome[0])


def test_a_directory_is_still_reported_as_a_directory(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError):
        sha256_file(tmp_path)


def _golden_tree(root: Path) -> None:
    (root / "nested").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "alpha").write_bytes(b"alpha")
    (root / "nested" / "beta").write_bytes(b"beta" * 300_000)


def _reference_tree_digest(root: Path) -> str:
    """The tree digest exactly as it was computed before the hardened open."""

    digest = hashlib.sha256()
    for entry in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = entry.relative_to(root).as_posix().encode()
        if entry.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        else:
            digest.update(b"F\0" + relative + b"\0" + entry.read_bytes())
    return digest.hexdigest()


def test_tree_digests_are_byte_identical(tmp_path: Path) -> None:
    from httk.core.digests import tree_digest

    _golden_tree(tmp_path / "tree")
    assert tree_digest(tmp_path / "tree") == _reference_tree_digest(tmp_path / "tree")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs need a POSIX platform")
def test_a_tree_entry_swapped_for_a_fifo_after_classification_is_refused_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from httk.core.digests import tree_digest

    root = tmp_path / "tree"
    _golden_tree(root)
    victim = root / "alpha"
    real_is_file = Path.is_file

    def classify_then_swap(self: Path) -> bool:
        result = real_is_file(self)
        if self == victim and result:
            # The entry is classified as a regular file, then swapped for a
            # FIFO before it is opened, as a racing writer could.
            victim.unlink()
            os.mkfifo(victim)
        return result

    monkeypatch.setattr(Path, "is_file", classify_then_swap)
    outcome: list[BaseException | str] = []

    def target() -> None:
        try:
            outcome.append(tree_digest(root))
        except BaseException as exc:
            outcome.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(5.0)
    assert not thread.is_alive(), "tree_digest blocked on a FIFO"
    assert isinstance(outcome[0], ValueError) and "not a regular file" in str(outcome[0])


def test_a_tree_entry_swapped_for_a_symlink_after_classification_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from httk.core.digests import tree_digest

    root = tmp_path / "tree"
    _golden_tree(root)
    (tmp_path / "secret").write_bytes(b"secret")
    victim = root / "alpha"
    real_is_file = Path.is_file

    def classify_then_swap(self: Path) -> bool:
        result = real_is_file(self)
        if self == victim and result:
            victim.unlink()
            victim.symlink_to(tmp_path / "secret")
        return result

    monkeypatch.setattr(Path, "is_file", classify_then_swap)
    with pytest.raises(ValueError, match="symlink is forbidden"):
        tree_digest(root)
