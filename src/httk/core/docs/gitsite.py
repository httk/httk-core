#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Create the single orphan commit used by a generated documentation site."""

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CommitSiteResult", "GitSiteError", "GitUnavailableError", "commit_site"]


class GitSiteError(RuntimeError):
    """Raised when a generated site cannot be committed to a Git repository."""


class GitUnavailableError(GitSiteError):
    """Raised when the ``git`` executable is not available."""


@dataclass(frozen=True)
class CommitSiteResult:
    """Summarize a site commit operation.

    :param repository: Repository receiving the generated objects.
    :param branch: Branch replaced by the new commit.
    :param commit: Identifier of the parentless commit.
    :param tree: Identifier of the committed site tree.
    """

    repository: Path
    branch: str
    commit: str
    tree: str


def _run_git(
    repository: Path,
    arguments: list[str],
    *,
    input_data: bytes | None = None,
    check: bool = True,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    sanitized_environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    sanitized_environment["GIT_CONFIG_GLOBAL"] = os.devnull
    sanitized_environment["GIT_CONFIG_SYSTEM"] = os.devnull
    if environment is not None:
        sanitized_environment.update(environment)
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *arguments],
            cwd=repository,
            input=input_data,
            capture_output=True,
            check=False,
            env=sanitized_environment,
        )
    except FileNotFoundError as exc:
        raise GitUnavailableError("git is not available on PATH") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise GitSiteError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
    return result


def _repository_from(path: Path) -> Path:
    result = _run_git(path, ["rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        raise GitSiteError(f"{path} is not inside a Git repository")
    return Path(result.stdout.decode().strip()).resolve()


def _resolve_repository(site: Path, repository: Path | None) -> Path:
    if repository is not None:
        root = repository.expanduser().resolve()
        if not root.is_dir():
            raise GitSiteError(f"Git repository directory does not exist: {root}")
        return _repository_from(root)
    try:
        return _repository_from(site)
    except GitSiteError as site_error:
        try:
            return _repository_from(Path.cwd().resolve())
        except GitSiteError:
            raise site_error


def _hash_blob(repository: Path, content: bytes) -> str:
    result = _run_git(repository, ["hash-object", "-w", "--stdin"], input_data=content)
    return result.stdout.decode().strip()


def _make_tree(repository: Path, directory: Path, *, root: bool = False) -> str:
    entries: list[bytes] = []
    for entry in sorted(os.scandir(directory), key=lambda item: item.name):
        # A worktree has a .git file at its root. It is Git administration data,
        # not part of the generated site tree.
        if root and entry.name == ".git":
            continue
        path = Path(entry.path)
        if entry.is_symlink():
            mode = "120000"
            kind = "blob"
            object_id = _hash_blob(repository, os.fsencode(os.readlink(path)))
        elif entry.is_dir(follow_symlinks=False):
            mode = "040000"
            kind = "tree"
            object_id = _make_tree(repository, path)
        elif entry.is_file(follow_symlinks=False):
            mode = "100755" if os.access(path, os.X_OK) else "100644"
            kind = "blob"
            object_id = _hash_blob(repository, path.read_bytes())
        else:
            raise GitSiteError(f"unsupported site entry (not a regular file, directory, or symlink): {path}")
        entries.append(f"{mode} {kind} {object_id}\t".encode() + os.fsencode(entry.name) + b"\0")
    result = _run_git(repository, ["mktree", "-z"], input_data=b"".join(entries))
    return result.stdout.decode().strip()


def commit_site(
    site_directory: str | Path,
    branch: str,
    message: str,
    *,
    repository: str | Path | None = None,
    author_name: str | None = None,
    author_email: str | None = None,
    committer_name: str | None = None,
    committer_email: str | None = None,
) -> CommitSiteResult:
    """Replace *branch* with one parentless commit containing *site_directory*.

    The site is converted directly into Git objects, so the caller's index and
    checked-out files are not changed. Ref leases for concurrent publishers
    remain the caller's responsibility when pushing the resulting branch. Git
    dates remain ambient, so commit IDs are intentionally not deterministic.

    :param site_directory: Generated site tree to commit.
    :param branch: Branch to replace with the generated commit.
    :param message: Commit message for the generated commit.
    :param repository: Repository to update, or the site/current repository.
    :param author_name: Git author name, using the docs-bot default when omitted.
    :param author_email: Git author email, using the docs-bot default when omitted.
    :param committer_name: Git committer name, using the docs-bot default when omitted.
    :param committer_email: Git committer email, using the docs-bot default when omitted.
    :return: Identifiers and paths for the generated commit.
    :raises GitSiteError: If the site, repository, branch, or Git operation is invalid.
    :raises GitUnavailableError: If the ``git`` executable is unavailable.
    """

    site = Path(site_directory).expanduser().resolve()
    if site.is_symlink() or not site.is_dir():
        raise GitSiteError(f"site directory does not exist or is not a directory: {site}")
    root = _resolve_repository(site, Path(repository) if repository is not None else None)
    check = _run_git(root, ["check-ref-format", "--branch", branch], check=False)
    if check.returncode != 0:
        detail = (check.stderr or check.stdout).decode(errors="replace").strip()
        raise GitSiteError(f"invalid branch name {branch!r}: {detail}")
    tree = _make_tree(root, site, root=True)
    identity = {
        "GIT_AUTHOR_NAME": author_name if author_name is not None else "httk docs bot",
        "GIT_AUTHOR_EMAIL": author_email if author_email is not None else "docs-bot@httk.org",
        "GIT_COMMITTER_NAME": committer_name if committer_name is not None else "httk docs bot",
        "GIT_COMMITTER_EMAIL": committer_email if committer_email is not None else "docs-bot@httk.org",
    }
    commit = (
        _run_git(
            root,
            [
                "commit-tree",
                tree,
                "-m",
                message,
            ],
            environment=identity,
        )
        .stdout.decode()
        .strip()
    )
    _run_git(root, ["update-ref", f"refs/heads/{branch}", commit])
    return CommitSiteResult(root, branch, commit, tree)
