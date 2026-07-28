import os
import shutil
import subprocess
from pathlib import Path

import pytest

from httk.core.docs.gitsite import commit_site


def _git(repository: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(["git", *arguments], cwd=repository, capture_output=True, text=True, check=True, env=env)
    return result.stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required for the site commit test")
def test_commit_site_ignores_hostile_git_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("site", encoding="utf-8")

    monkeypatch.setenv("GIT_AUTHOR_NAME", "attacker")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "attacker@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "attacker")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "attacker@example.invalid")
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-a-repository"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "not-a-worktree"))

    commit_site(site, "docs-site", "publish", repository=repository)

    clean_environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    author = _git(repository, "show", "-s", "--format=%an%x00%ae", "docs-site", env=clean_environment)
    assert author == "httk docs bot\x00docs-bot@httk.org"
