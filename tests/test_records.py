"""The deterministic filesystem record list."""

import os
from pathlib import Path

import pytest

from httk.core.records import file_records


def _by_path(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(record["path"]): record for record in records}


def test_file_symlink_and_directory_records(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("hello", encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    (tmp_path / "link").symlink_to("sub/a.txt")

    records = file_records(tmp_path)
    by_path = _by_path(records)

    assert by_path["sub"]["type"] == "directory"
    assert by_path["sub/a.txt"]["type"] == "file"
    assert by_path["sub/a.txt"]["size"] == 5
    assert by_path["sub/a.txt"]["executable"] is False
    assert by_path["run.sh"]["executable"] is True
    assert by_path["link"] == {"path": "link", "type": "symlink", "target": "sub/a.txt"}
    # Sorted by posix relpath, parent before child.
    paths = [str(record["path"]) for record in records]
    assert paths == sorted(paths)


def test_symlinks_are_never_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "to_dir").symlink_to(outside)

    records = file_records(root)
    by_path = _by_path(records)
    assert by_path["to_dir"]["type"] == "symlink"
    # A followed symlink would have recorded outside/secret as root/to_dir/secret.
    assert "to_dir/secret" not in by_path


def test_exclusions_are_fnmatch_on_relpaths(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("k", encoding="utf-8")
    (tmp_path / "control").mkdir()
    (tmp_path / "control" / "state").write_text("s", encoding="utf-8")

    records = file_records(tmp_path, exclusions=("control", "control/**"))
    assert set(_by_path(records)) == {"keep.txt"}


def test_skip_predicate_prunes_directories(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("k", encoding="utf-8")
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "deep.txt").write_text("d", encoding="utf-8")

    records = file_records(tmp_path, skip=lambda path: path.name == "payload")
    # Skipping the directory prunes it and everything beneath it.
    assert set(_by_path(records)) == {"keep.txt"}


def test_special_entry_is_rejected(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        file_records(tmp_path)
