"""Exercise the standalone release checker's process and filesystem boundaries."""

import os
import runpy
import stat
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/check_release.py"))


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


@pytest.fixture
def committed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Release checker test")
    _git(repo, "config", "user.email", "release-checker@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / ".gitignore").write_text(".venv/\ndist/\n")
    script = repo / "example.sh"
    script.write_text("#!/bin/sh\nprintf 'committed example\\n'\n")
    script.chmod(0o755)
    _git(repo, "add", ".gitignore", "example.sh")
    _git(repo, "commit", "--quiet", "-m", "Create release fixture")
    return repo


def test_snapshot_exports_committed_files_and_executable_modes(committed_repo: Path, tmp_path: Path) -> None:
    for ignored in (".venv", "dist"):
        directory = committed_repo / ignored
        directory.mkdir()
        (directory / "stale.txt").write_text("must not reach verification")
    work = tmp_path / "verification"
    work.mkdir()

    source, commit = CHECKER["_snapshot"](committed_repo, work)

    assert commit == _git(committed_repo, "rev-parse", "HEAD")
    assert source != committed_repo
    assert {path.name for path in source.iterdir()} == {".gitignore", "example.sh"}
    assert (source / "example.sh").read_bytes() == (committed_repo / "example.sh").read_bytes()
    assert (source / "example.sh").stat().st_mode & stat.S_IXUSR
    assert subprocess.check_output([str(source / "example.sh")], text=True) == "committed example\n"


@pytest.mark.parametrize("dirty_kind", ["modified", "staged", "untracked"])
def test_snapshot_rejects_uncommitted_files(committed_repo: Path, tmp_path: Path, dirty_kind: str) -> None:
    if dirty_kind == "untracked":
        (committed_repo / "untracked.txt").write_text("uncommitted")
    else:
        (committed_repo / "example.sh").write_text("uncommitted")
        if dirty_kind == "staged":
            _git(committed_repo, "add", "example.sh")
    work = tmp_path / "verification"
    work.mkdir()

    with pytest.raises(ValueError, match="uncommitted|clean|dirty"):
        CHECKER["_snapshot"](committed_repo, work)

    assert not (work / "source").exists()


def test_snapshot_rejects_gitlinks(committed_repo: Path, tmp_path: Path) -> None:
    commit = _git(committed_repo, "rev-parse", "HEAD")
    (committed_repo / "dependency").mkdir()
    _git(committed_repo, "update-index", "--add", "--cacheinfo", f"160000,{commit},dependency")
    _git(committed_repo, "commit", "--quiet", "-m", "Add unsupported gitlink")
    assert not _git(committed_repo, "status", "--porcelain")
    work = tmp_path / "verification"
    work.mkdir()

    with pytest.raises(ValueError, match="gitlink|submodule"):
        CHECKER["_snapshot"](committed_repo, work)


def test_environment_removes_workspace_and_gate_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_venv = tmp_path / "old-venv"
    (old_venv / "bin").mkdir(parents=True)
    (old_venv / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    alias = tmp_path / "aliased-bin"
    alias.symlink_to(old_venv / "bin", target_is_directory=True)
    poisoned = {
        "PYTHONPATH": "/workspace/sibling/src",
        "PYTHONHOME": "/workspace/python",
        "MYPYPATH": "/workspace/sibling/src",
        "VIRTUAL_ENV": str(old_venv),
        "CONDA_PREFIX": "/workspace/conda",
        "PYTEST_ADDOPTS": "-k never_run_any_tests",
        "PYTEST_PLUGINS": "workspace_plugin",
        "HTTK_TEST_PROFILE": "fast",
        "PIP_EXTRA_INDEX_URL": "https://example.invalid/simple",
        "PIP_FIND_LINKS": "/workspace/wheels",
        "PIP_CONSTRAINT": "/workspace/constraints.txt",
        "PIP_NO_DEPS": "1",
        "MAKEFLAGS": "--just-print",
        "MFLAGS": "-n",
        "MAKEFILES": "/workspace/override.mk",
        "GNUMAKEFLAGS": "--just-print",
        "PYTHON": str(old_venv / "bin/python"),
        "NPM": "true",
        "DIST_DIR": "/workspace/dist",
        "DOCS_BASE_URL": "file:///workspace/docs",
    }
    for key, value in poisoned.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PATH", os.pathsep.join([str(old_venv / "bin"), str(alias), "relative-bin", "/usr/bin"]))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.invalid:3128")
    monkeypatch.setenv("PIP_CONFIG_FILE", "/workspace/pip.conf")
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.invalid/simple")
    work = tmp_path / "verification"

    env = CHECKER["_environment"](work)

    assert not set(poisoned).intersection(env)
    assert env["PIP_CONFIG_FILE"] == os.devnull
    assert env["PIP_INDEX_URL"] == "https://pypi.org/simple"
    assert env["PIP_CACHE_DIR"].startswith(str(work) + os.sep)
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PATH"].split(os.pathsep) == [str(work / ".venv/bin"), "/usr/bin"]
    assert env["HTTPS_PROXY"] == "http://proxy.example.invalid:3128"


def test_run_retains_output_and_propagates_failure(tmp_path: Path) -> None:
    log = tmp_path / "failed-gate.log"
    command = [
        sys.executable,
        "-I",
        "-c",
        (
            "import os, sys; print(os.getcwd()); print('stdout evidence'); "
            "print('stderr evidence', file=sys.stderr); sys.exit(7)"
        ),
    ]

    with pytest.raises(subprocess.CalledProcessError) as error:
        CHECKER["_run"](command, tmp_path, dict(os.environ), log)

    assert error.value.returncode == 7
    assert error.value.cmd == command
    output = log.read_text()
    assert str(tmp_path) in output
    assert "stdout evidence" in output
    assert "stderr evidence" in output
