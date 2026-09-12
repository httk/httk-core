"""Release preparation validates and preserves the working candidate before handoff."""

import os
import runpy
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/check_release.py"
CHECKER = runpy.run_path(str(SCRIPT))


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


@pytest.fixture
def candidate_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    (repo / "docs/_inventories").mkdir(parents=True)
    (repo / ".gitignore").write_text("dist/\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "httk-example"\nversion = "2.1.0"\n')
    (repo / "module.py").write_text("value = 1\n")
    (repo / "removed.py").write_text("old = True\n")
    (repo / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "alias.py").symlink_to("module.py")
    (repo / "docs/requirements.lock").write_text("original lock\n")
    (repo / "docs/_inventories/core.inv").write_bytes(b"original inventory")
    (repo / "docs/notes.md").write_text("keep these notes\n")
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Release preparation test")
    _git(repo, "config", "user.email", "release-prepare@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "Create preparation fixture")
    return repo


@pytest.mark.parametrize("version", [None, "v9.9.9"])
def test_prepare_rejects_missing_or_wrong_version_before_side_effects(tmp_path: Path, version: str | None) -> None:
    repo = tmp_path / "outside-git"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "httk-example"\nversion = "2.1.0"\n')
    output = tmp_path / "must-not-be-created"
    env = {key: value for key, value in os.environ.items() if key != "HTTK_RELEASE_VERSION"}
    env["PATH"] = ""
    if version is not None:
        env["HTTK_RELEASE_VERSION"] = version

    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(repo), "--prepare", "--output-dir", str(output)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "VERSION" in result.stderr
    assert "required" in result.stderr if version is None else "does not match" in result.stderr
    assert "v2.1.0" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
    assert {path.name for path in repo.iterdir()} == {"pyproject.toml"}


def test_next_steps_works_outside_git_without_preparing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "httk-example"\nversion = "2.1.0"\n')
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(tmp_path), "--next-steps"],
        env={**os.environ, "PATH": ""},
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "commit" in result.stdout
    assert "git tag -s v2.1.0" in result.stdout
    assert "git push" in result.stdout
    assert "GitHub release" in result.stdout
    assert {path.name for path in tmp_path.iterdir()} == {"pyproject.toml"}


def test_working_snapshot_keeps_edits_additions_modes_and_symlinks(candidate_repo: Path, tmp_path: Path) -> None:
    repo = candidate_repo
    (repo / "module.py").write_text("value = 2\n")
    (repo / "added.py").write_text("new = True\n")
    (repo / "removed.py").unlink()
    (repo / "run.sh").chmod(0o755)
    (repo / "alias.py").unlink()
    (repo / "alias.py").symlink_to("added.py")
    (repo / "dist").mkdir()
    (repo / "dist/stale.whl").write_bytes(b"ignored")
    work = tmp_path / "verification"
    work.mkdir()

    source, commit = CHECKER["_snapshot"](repo, work, working_tree=True)
    paths = CHECKER["_candidate_files"](repo)

    assert commit == _git(repo, "rev-parse", "HEAD")
    assert (source / "module.py").read_text() == "value = 2\n"
    assert (source / "added.py").read_text() == "new = True\n"
    assert (source / "run.sh").stat().st_mode & stat.S_IXUSR
    assert (source / "alias.py").is_symlink()
    assert os.readlink(source / "alias.py") == "added.py"
    assert not (source / "removed.py").exists()
    assert not (source / "dist").exists()
    assert "added.py" in paths and "removed.py" not in paths
    assert CHECKER["_manifest"](source, paths) == CHECKER["_manifest"](repo, paths)


@pytest.fixture
def refreshed_candidate(candidate_repo: Path, tmp_path: Path) -> tuple[Path, Path, dict, dict]:
    repo = candidate_repo
    original = CHECKER["_manifest"](repo, CHECKER["_candidate_files"](repo))
    work = tmp_path / "verification"
    work.mkdir()
    source, _ = CHECKER["_snapshot"](repo, work, working_tree=True)
    (source / "docs/requirements.lock").write_text("refreshed lock\n")
    (source / "docs/_inventories/core.inv").write_bytes(b"refreshed inventory")
    (source / "docs/_inventories/python.inv").write_bytes(b"new inventory")
    candidate = CHECKER["_manifest"](source, sorted(set(original) | set(CHECKER["_release_inputs"](source))))
    return repo, source, original, candidate


def test_copyback_changes_only_verified_release_inputs(refreshed_candidate: tuple[Path, Path, dict, dict]) -> None:
    repo, source, original, candidate = refreshed_candidate
    inputs = CHECKER["_release_inputs"](source)
    assert set(inputs) == {"docs/requirements.lock", "docs/_inventories/core.inv", "docs/_inventories/python.inv"}
    # A build output and unrelated source edit must not be copied with the inputs.
    (source / "artifact.whl").write_bytes(b"build output")
    (source / "docs/notes.md").write_text("not a release input\n")

    CHECKER["_copy_inputs"](repo, source, original, candidate)

    for name in inputs:
        assert (repo / name).read_bytes() == (source / name).read_bytes()
    untouched = sorted(set(original) - set(inputs))
    assert CHECKER["_manifest"](repo, untouched) == {name: original[name] for name in untouched}
    assert not (repo / "artifact.whl").exists()
    assert CHECKER["_manifest"](repo, CHECKER["_candidate_files"](repo)) == candidate


@pytest.mark.parametrize("change", ["modify", "add", "delete"])
def test_copyback_rejects_concurrent_changes_before_writing_inputs(
    refreshed_candidate: tuple[Path, Path, dict, dict],
    change: str,
) -> None:
    repo, source, original, candidate = refreshed_candidate
    if change == "modify":
        (repo / "docs/requirements.lock").write_text("concurrent lock edit\n")
    elif change == "add":
        (repo / "concurrent.py").write_text("new = True\n")
    else:
        (repo / "module.py").unlink()
    before = CHECKER["_manifest"](repo, CHECKER["_candidate_files"](repo))

    with pytest.raises(ValueError, match="changed during preparation"):
        CHECKER["_copy_inputs"](repo, source, original, candidate)

    assert CHECKER["_manifest"](repo, CHECKER["_candidate_files"](repo)) == before
    assert not (repo / "docs/_inventories/python.inv").exists()


def test_source_guard_accepts_ignored_build_outputs(refreshed_candidate: tuple[Path, Path, dict, dict]) -> None:
    repo, source, _, candidate = refreshed_candidate
    (source / "dist").mkdir()
    (source / "dist/example.whl").write_bytes(b"build output")

    CHECKER["_assert_source_unchanged"](repo, source, candidate)


@pytest.mark.parametrize("change", ["add", "modify"])
def test_source_guard_rejects_gate_changes_to_source(
    refreshed_candidate: tuple[Path, Path, dict, dict],
    change: str,
) -> None:
    repo, source, _, candidate = refreshed_candidate
    if change == "add":
        (source / "added source.py").write_text("new = True\n")
        message = "added source files"
    else:
        (source / "module.py").write_text("value = 9\n")
        message = "changed candidate source files"

    with pytest.raises(ValueError, match=message):
        CHECKER["_assert_source_unchanged"](repo, source, candidate)
