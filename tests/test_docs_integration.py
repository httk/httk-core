import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from httk.core.cli import CLIContext
from httk.core.docs import cli


def _run_git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repository, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _make_build(path: Path, label: str) -> None:
    path.mkdir()
    (path / "index.html").write_text(f"index:{label}", encoding="utf-8")
    (path / "guide.html").write_text(f"guide:{label}", encoding="utf-8")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _compose(site: Path, build: Path, *target: str) -> None:
    arguments = [
        "compose",
        "--site",
        str(site),
        "--build",
        str(build),
        *target,
        "--slug",
        "httk-core",
        "--url",
        "https://docs.httk.org/httk-core",
    ]
    assert cli.command(arguments, CLIContext("httk", site.parent)) == 0


def _commit_site(repository: Path, site: Path, message: str) -> None:
    environment = os.environ.copy()
    source_root = Path(__file__).resolve().parents[1]
    environment["PYTHONPATH"] = str(source_root / "src")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "httk.core.docs",
            "commit-site",
            "--site",
            str(site),
            "--repo",
            str(repository),
            "--branch",
            "docs-site",
            "--message",
            message,
        ],
        cwd=repository,
        env=environment,
        check=True,
    )


def _assert_branch_tree(repository: Path, site: Path) -> None:
    assert _run_git(repository, "rev-list", "--count", "docs-site") == "1"
    names = _run_git(repository, "ls-tree", "-r", "--name-only", "docs-site").splitlines()
    expected = sorted(path for path in _tree_bytes(site) if path != ".git")
    assert names == expected
    for name in expected:
        assert (
            subprocess.run(["git", "show", f"docs-site:{name}"], cwd=repository, capture_output=True, check=True).stdout
            == (site / name).read_bytes()
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required for the site branch integration test")
def test_versioned_site_lifecycle_and_orphan_site_commits(tmp_path: Path) -> None:
    site = tmp_path / "site"
    release_one = tmp_path / "release-one"
    dev_initial = tmp_path / "dev-initial"
    release_two = tmp_path / "release-two"
    dev_changed = tmp_path / "dev-changed"
    _make_build(release_one, "release-one")
    _make_build(dev_initial, "dev-initial")
    _make_build(release_two, "release-two")
    _make_build(dev_changed, "dev-changed")

    _compose(site, release_one, "--release", "v0.1.0")
    _compose(site, dev_initial, "--dev")
    _compose(site, release_two, "--release", "v0.2.0")
    release_snapshots = {name: _tree_bytes(site / name) for name in ("v0.1.0", "v0.2.0")}

    repository = tmp_path / "repository"
    repository.mkdir()
    _run_git(repository, "init", "-b", "main")
    _commit_site(repository, site, "dev: initial")
    _assert_branch_tree(repository, site)

    _compose(site, dev_changed, "--dev")
    _commit_site(repository, site, "dev: changed")
    _assert_branch_tree(repository, site)

    assert _tree_bytes(site / "v0.1.0") == release_snapshots["v0.1.0"]
    assert _tree_bytes(site / "v0.2.0") == release_snapshots["v0.2.0"]
    manifest = json.loads((site / "versions.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in manifest["versions"]] == ["v0.2.0", "v0.1.0", "dev:main"]
    assert manifest["default"]["name"] == "v0.2.0"
    assert 'url=v0.2.0/' in (site / "index.html").read_text(encoding="utf-8")
    for version in ("v0.1.0", "v0.2.0", "dev/main"):
        assert (site / version / "pages.json").is_file()
    assert (site / ".nojekyll").is_file()
