import errno
import os
import shutil
from pathlib import Path
from typing import Literal

import pytest

from httk.core.docs import sitetree
from httk.core.docs.manifests import read_version_manifest
from httk.core.docs.semver import Version
from httk.core.docs.sitetree import ComposeError, ImmutabilityError, compose_site


def make_build(path: Path, text: str = "home") -> None:
    (path / "reference").mkdir(parents=True)
    (path / "index.html").write_text(text, encoding="utf-8")
    (path / "reference" / "api.html").write_text("api", encoding="utf-8")


def compose(root: Path, build: Path, target: Version | Literal["dev"], dev_branch: str = "main"):
    return compose_site(
        root,
        build,
        slug="core",
        site_url="https://docs.httk.org/core",
        source_commit="sha",
        target=target,
        dev_branch=dev_branch,
    )


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


def test_dev_branches_are_replaced_independently(tmp_path: Path) -> None:
    root = tmp_path / "site"
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_build(first, "one")
    make_build(second, "two")
    compose(root, first, Version(1, 0, 0))
    compose(root, first, "dev")
    release_tree = sitetree._tree(root / "v1.0.0")
    result = compose(root, second, "dev", "develop")
    assert result.versions == ("v1.0.0", "dev:main", "dev:develop")
    assert result.default_target == "v1.0.0"
    assert (root / "dev/main/index.html").read_text(encoding="utf-8") == "one"
    assert (root / "dev/develop/index.html").read_text(encoding="utf-8") == "two"
    assert '"version": "dev:develop"' in (root / "dev/develop/pages.json").read_text(encoding="utf-8")
    assert sitetree._tree(root / "v1.0.0") == release_tree
    assert sitetree._tree(root / "latest") == release_tree
    compose(root, second, "dev")
    assert (root / "dev/main/index.html").read_text(encoding="utf-8") == "two"
    assert (root / "dev/develop/index.html").read_text(encoding="utf-8") == "two"
    manifest = read_version_manifest(root / "versions.json")
    assert [item["path"] for item in manifest["versions"]] == ["v1.0.0/", "dev/main/", "dev/develop/"]
    assert "url=latest/" in (root / "index.html").read_text(encoding="utf-8")


def test_develop_only_site_defaults_to_develop(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    result = compose(root, build, "dev", "develop")
    assert result.default_target == "dev:develop"
    assert result.versions == ("dev:develop",)
    assert not (root / "dev/main").exists()
    assert "url=dev/develop/" in (root / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("branch", ["", "Main", "feature", "a/b"])
def test_unsupported_dev_branch_is_rejected(tmp_path: Path, branch: str) -> None:
    build = tmp_path / "build"
    make_build(build)
    with pytest.raises(ValueError, match="unsupported development docs branch"):
        compose(tmp_path / "site", build, "dev", branch)
    assert not (tmp_path / "site").exists()


def test_dev_swap_recovery_is_per_branch(tmp_path: Path) -> None:
    root = tmp_path / "site"
    main_build = tmp_path / "main"
    develop_build = tmp_path / "develop"
    make_build(main_build, "main")
    make_build(develop_build, "develop")
    compose(root, main_build, "dev")
    compose(root, develop_build, "dev", "develop")
    # An interrupted develop swap is restored to dev/develop, never adopted as dev/main.
    shutil.rmtree(root / "dev/main")
    os.rename(root / "dev/develop", root / ".old-dev-develop-interrupted")
    release = tmp_path / "release"
    make_build(release, "release")
    compose(root, release, Version(1, 0, 0))
    assert (root / "dev/develop/index.html").read_text(encoding="utf-8") == "develop"
    assert not (root / "dev/main").exists()
    assert not (root / ".old-dev-develop-interrupted").exists()
    # An interrupted main swap is restored while composing develop.
    compose(root, main_build, "dev")
    os.rename(root / "dev/main", root / ".old-dev-main-interrupted")
    compose(root, develop_build, "dev", "develop")
    assert (root / "dev/main/index.html").read_text(encoding="utf-8") == "main"
    assert not (root / ".old-dev-main-interrupted").exists()
    # Leftovers next to a live tree are removed without touching the other branch.
    leftover = root / ".old-dev-develop-leftover"
    leftover.mkdir()
    (leftover / "index.html").write_text("stale", encoding="utf-8")
    compose(root, main_build, "dev")
    assert not leftover.exists()
    assert (root / "dev/develop/index.html").read_text(encoding="utf-8") == "develop"
    assert read_version_manifest(root / "versions.json")["default"]["name"] == "v1.0.0"


def test_build_cache_is_never_published(tmp_path: Path) -> None:
    root = tmp_path / "site"
    build = tmp_path / "build"
    make_build(build)
    (build / ".buildinfo").write_text("config", encoding="utf-8")
    compose(root, build, Version(1, 0, 0))
    compose(root, build, "dev")
    # Trees published before the cache was excluded still carry it.
    for tree in ("v1.0.0", "latest", "dev/main"):
        (root / tree / ".doctrees").mkdir()
        (root / tree / ".doctrees" / "environment.pickle").write_bytes(b"cache")
        (root / tree / "reference" / "x.pickle").write_bytes(b"cache")
    (build / ".doctrees").mkdir()
    (build / ".doctrees" / "index.doctree").write_bytes(b"cache")
    (build / "x.pickle").write_bytes(b"cache")
    result = compose(root, build, Version(1, 0, 0))
    assert result.unchanged
    for tree in ("v1.0.0", "latest", "dev/main"):
        assert not (root / tree / ".doctrees").exists()
        assert not (root / tree / "reference" / "x.pickle").exists()
        assert (root / tree / "index.html").is_file()
    compose(root, build, "dev", "develop")
    assert (root / "dev/develop/.buildinfo").is_file()
    assert not (root / "dev/develop/.doctrees").exists()
    assert not (root / "dev/develop/x.pickle").exists()
    snapshot = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    again = compose(root, build, Version(1, 0, 0))
    assert again.unchanged
    assert not again.changed
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == snapshot
    assert not [path for path in root.rglob("*") if path.name == ".doctrees" or path.suffix == ".pickle"]


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
