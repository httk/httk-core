import errno
import os
from pathlib import Path

import pytest

from httk.core.docs import sitetree
from httk.core.docs.manifests import read_version_manifest
from httk.core.docs.semver import Version
from httk.core.docs.sitetree import ComposeError, ImmutabilityError, compose_site


def make_build(path: Path, text: str = "home") -> None:
    (path / "reference").mkdir(parents=True)
    (path / "index.html").write_text(text, encoding="utf-8")
    (path / "reference" / "api.html").write_text("api", encoding="utf-8")


def compose(root: Path, build: Path, target: Version | str):
    return compose_site(
        root, build, slug="core", site_url="https://docs.httk.org/core", source_commit="sha", target=target
    )  # type: ignore[arg-type]


def test_fresh_dev_and_release_composition(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    result = compose(root, build, "dev")
    assert result.default_target == "dev:main"
    assert (root / "dev/main/index.html").is_file()
    assert (root / ".nojekyll").is_file()
    release = compose(root, build, Version(1, 0, 0))
    assert release.default_target == "v1.0.0"
    assert (root / "dev/main/index.html").is_file()
    assert sitetree._tree(root / "latest") == sitetree._tree(root / "v1.0.0")
    assert "url=latest/" in (root / "index.html").read_text(encoding="utf-8")


def test_dev_replace_and_release_add_preserve_other_versions(tmp_path: Path) -> None:
    root = tmp_path / "site"
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_build(first, "one")
    make_build(second, "two")
    compose(root, first, Version(1, 0, 0))
    compose(root, first, Version(2, 0, 0))
    compose(root, first, "dev")
    compose(root, second, "dev")
    assert (root / "v1.0.0/index.html").read_text(encoding="utf-8") == "one"
    assert (root / "v2.0.0/index.html").read_text(encoding="utf-8") == "one"
    assert (root / "dev/main/index.html").read_text(encoding="utf-8") == "two"
    assert read_version_manifest(root / "versions.json")["default"]["name"] == "v2.0.0"
    assert "url=latest/" in (root / "index.html").read_text(encoding="utf-8")


def test_newest_release_refreshes_latest(tmp_path: Path) -> None:
    root = tmp_path / "site"
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_build(first, "one")
    make_build(second, "two")
    compose(root, first, Version(1, 0, 0))
    compose(root, second, Version(2, 0, 0))
    assert sitetree._tree(root / "latest") == sitetree._tree(root / "v2.0.0")
    assert (root / "latest/index.html").read_text(encoding="utf-8") == "two"


def test_dev_only_compose_has_no_latest(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    compose(root, build, "dev")
    assert not (root / "latest").exists()
    assert "url=dev/main/" in (root / "index.html").read_text(encoding="utf-8")


def test_identical_release_noop_and_different_release_fails(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    changed = tmp_path / "changed"
    make_build(build)
    make_build(changed, "changed")
    compose(root, build, Version(1, 0, 0))
    latest_inode = (root / "latest").stat().st_ino
    result = compose(root, build, Version(1, 0, 0))
    assert result.unchanged
    assert not result.changed
    assert (root / "latest").stat().st_ino == latest_inode
    with pytest.raises(ImmutabilityError, match="immutable.*manual repair workflow"):
        compose(root, changed, Version(1, 0, 0))


def test_failed_release_copy_leaves_no_release_and_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    original_copy2 = sitetree.shutil.copy2
    calls = 0

    def fail_after_one(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        original_copy2(source, destination)
        if calls == 1:
            raise OSError("injected copy failure")

    monkeypatch.setattr(sitetree.shutil, "copy2", fail_after_one)
    with pytest.raises(OSError, match="injected"):
        compose(root, build, Version(3, 0, 0))
    assert not (root / "v3.0.0").exists()
    monkeypatch.setattr(sitetree.shutil, "copy2", original_copy2)
    compose(root, build, Version(3, 0, 0))
    assert (root / "v3.0.0" / "index.html").is_file()


def test_stale_staging_is_cleaned_at_start(tmp_path: Path) -> None:
    root = tmp_path / "site"
    stale = root / ".staging-v9.9.9-old"
    stale.mkdir(parents=True)
    (stale / "partial.html").write_text("partial", encoding="utf-8")
    build = tmp_path / "build"
    make_build(build)
    compose(root, build, "dev")
    assert not stale.exists()


def test_latest_swap_recovery_restores_or_cleans_leftovers(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    compose(root, build, Version(1, 0, 0))
    os.rename(root / "latest", root / ".old-latest-interrupted")
    compose(root, build, Version(1, 0, 0))
    assert (root / "latest").is_dir()
    leftover = root / ".old-latest-cleanup"
    leftover.mkdir()
    (leftover / "partial.html").write_text("partial", encoding="utf-8")
    compose(root, build, Version(1, 0, 0))
    assert not leftover.exists()


def test_latest_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    compose(root, build, Version(1, 0, 0))
    (root / "latest").rename(root / "latest.old")
    (root / "latest").symlink_to(root / "v1.0.0", target_is_directory=True)
    with pytest.raises(ComposeError, match="latest"):
        compose(root, build, Version(1, 0, 0))


def test_stale_latest_is_removed_by_dev_compose(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    (root / "latest").mkdir(parents=True)
    (root / "latest/index.html").write_text("stale", encoding="utf-8")
    stale_staging = root / ".staging-latest-interrupted"
    stale_staging.mkdir()
    (stale_staging / "partial.html").write_text("partial", encoding="utf-8")
    compose(root, build, "dev")
    assert not (root / "latest").exists()
    assert not stale_staging.exists()


def test_source_symlink_and_fifo_are_rejected(tmp_path: Path) -> None:
    build = tmp_path / "build"
    make_build(build)
    (build / "linked.html").symlink_to(build / "index.html")
    with pytest.raises(ComposeError, match="symlink"):
        compose(tmp_path / "site", build, "dev")
    (build / "linked.html").unlink()
    fifo = build / "pipe"
    try:
        os.mkfifo(fifo)
    except (AttributeError, OSError):
        pytest.skip("FIFO creation is unavailable")
    with pytest.raises(ComposeError, match="non-regular"):
        compose(tmp_path / "site-fifo", build, "dev")


def test_nonempty_destination_rename_race_uses_immutable_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    original_rename = sitetree.os.rename

    def rename_with_nonempty_appearance(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        destination_path = Path(destination)
        if destination_path.name == "v4.0.0":
            destination_path.mkdir()
            (destination_path / "concurrent.html").write_text("other", encoding="utf-8")
            raise OSError(errno.ENOTEMPTY, "destination appeared")
        original_rename(source, destination)

    monkeypatch.setattr(sitetree.os, "rename", rename_with_nonempty_appearance)
    with pytest.raises(ImmutabilityError, match="immutable.*manual repair workflow"):
        compose(root, build, Version(4, 0, 0))
