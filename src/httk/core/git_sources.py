"""Fetch, cache and install members of git repositories named by git URIs.

A git URI has the form ``git+SCHEME://AUTHORITY/PATH[@REF][#SUBDIR]`` with
``SCHEME`` one of ``https``, ``http`` or ``file``. The repository is cloned at
``REF`` (a branch, tag, abbreviated or full commit hash, or the remote default
branch when omitted), and the member is the directory ``SUBDIR`` (or the
repository root), which must hold the consumer's marker file. The canonical URI
always carries the full commit hash, a lowercased scheme and host, and no
trailing slashes; the repository path is kept verbatim, so ``…/repo`` and
``…/repo.git`` are distinct URIs.

Checkout trees are cached per repository and commit under
``data_home() / "git"``; they carry no ``.git`` directory and are safe to
delete. Referencing a URI with :func:`install_git_member` records one installed
entry under ``data_home() / KIND / "installed"``, where ``KIND`` names the
consumer (for example ``"templates"``). Git runs with the global and system
configuration, hooks, credential helpers and terminal prompts disabled, so only
repositories reachable without credentials are supported. The cache-only
lookups (:func:`cached_git_checkout`, :func:`installed_git_members`,
:func:`installed_git_member`, :func:`resolve_installed_name` and
:func:`uninstall_git_members`) never run git and never fetch.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from httk.core.userdirs import data_home

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "GitUri",
    "InstalledGitMember",
    "cached_git_checkout",
    "fetch_git_checkout",
    "git_member",
    "install_git_member",
    "installed_git_member",
    "installed_git_members",
    "parse_git_uri",
    "resolve_installed_name",
    "uninstall_git_members",
]

_SCHEMES = frozenset({"https", "http", "file"})
_FULL_HASH = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
_KIND = re.compile(r"[a-z0-9][a-z0-9_-]*")
_CHECKOUT_FORMAT = "httk-git-checkout"
_INSTALLED_FORMAT = "httk-git-installed"


@dataclass(frozen=True)
class GitUri:
    """One parsed git URI.

    :param repository: Give the canonical ``git+scheme://authority/path`` repository.
    :param ref: Give the branch, tag or commit, or ``None`` for the default branch.
    :param subdir: Give the member directory, or ``None`` for the repository root.
    """

    repository: str
    ref: str | None
    subdir: str | None

    @property
    def pinned(self) -> bool:
        """Whether the ref is a full commit hash."""

        return self.ref is not None and _FULL_HASH.fullmatch(self.ref) is not None

    def __str__(self) -> str:
        """Return the URI text.

        :return: ``repository[@ref][#subdir]``.
        """

        ref = f"@{self.ref}" if self.ref is not None else ""
        subdir = f"#{self.subdir}" if self.subdir is not None else ""
        return f"{self.repository}{ref}{subdir}"


@dataclass(frozen=True)
class InstalledGitMember:
    """One installed git member entry.

    :param kind: Give the consumer kind, such as ``"templates"``.
    :param uri: Give the canonical pinned URI.
    :param repository: Give the canonical repository part of the URI.
    :param commit: Give the full commit hash.
    :param subdir: Give the member directory, or ``None`` for the repository root.
    :param names: Give the short names the member claims.
    :param referenced_at: Give the ISO timestamp of the latest explicit reference.
    :param path: Give the member directory inside the cached checkout tree.
    """

    kind: str
    uri: str
    repository: str
    commit: str
    subdir: str | None
    names: tuple[str, ...]
    referenced_at: str
    path: Path


def parse_git_uri(text: str) -> GitUri:
    """Parse and canonicalize a ``git+scheme://authority/path[@ref][#subdir]`` URI.

    The ref is split off at the last ``@`` of the path, so repository paths
    that themselves contain ``@`` are not supported.

    :param text: Supply the URI text.
    :return: The parsed URI with a lowercased scheme, host and hash and no trailing slashes.
    :raises ValueError: If the text is not a supported git URI.
    """

    if not isinstance(text, str) or not text.startswith("git+"):
        raise ValueError(f"a git URI must start with 'git+': {text!r}")
    if any(character.isspace() or ord(character) < 32 for character in text):
        raise ValueError(f"git URI must not contain whitespace or control characters: {text!r}")
    body = text[4:]
    scheme, separator, rest = body.partition("://")
    scheme = scheme.lower()
    if not separator or scheme not in _SCHEMES:
        raise ValueError(
            f"unsupported git URI {text!r}: only git+https://, git+http:// and git+file:// "
            "are supported (not ssh or git@host:path)"
        )
    rest, hashmark, fragment = rest.partition("#")
    if "?" in rest:
        raise ValueError(f"git URI must not contain a query: {text!r}")
    authority, slash, path = rest.partition("/")
    path = slash + path
    if "@" in authority:
        raise ValueError(f"git URI must not carry userinfo or credentials: {text!r}")
    if not authority and scheme != "file":
        raise ValueError(f"git URI must name a host: {text!r}")
    ref: str | None = None
    if "@" in path:
        path, ref = path.rsplit("@", 1)
        if not ref:
            raise ValueError(f"git URI has an empty ref after '@': {text!r}")
        if ref.startswith("-"):
            raise ValueError(f"git URI ref must not start with '-': {text!r}")
        if _FULL_HASH.fullmatch(ref):
            ref = ref.lower()
    path = path.rstrip("/")
    if not path:
        raise ValueError(f"git URI must name a repository path: {text!r}")
    subdir: str | None = None
    if hashmark:
        if not fragment:
            raise ValueError(f"git URI has an empty subdirectory after '#': {text!r}")
        subdir = fragment.removesuffix("/")
        if subdir.startswith("/") or "\\" in subdir or any(part in {"", ".", ".."} for part in subdir.split("/")):
            raise ValueError(f"git URI subdirectory must be a plain relative path: {fragment!r}")
    return GitUri(f"git+{scheme}://{authority.lower()}{path}", ref, subdir)


def _uri(uri: str | GitUri) -> GitUri:
    return uri if isinstance(uri, GitUri) else parse_git_uri(uri)


def _checkouts(repository: str) -> Path:
    return data_home() / "git" / hashlib.sha256(repository.encode()).hexdigest()[:16]


def _installed_directory(kind: str) -> Path:
    if not isinstance(kind, str) or _KIND.fullmatch(kind) is None or kind == "git":
        raise ValueError(f"installed member kind must match [a-z0-9][a-z0-9_-]* and not be 'git': {kind!r}")
    return data_home() / kind / "installed"


def _installed_path(kind: str, uri: str) -> Path:
    return _installed_directory(kind) / f"{hashlib.sha256(uri.encode()).hexdigest()[:32]}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _write_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _git(cwd: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_TERMINAL_PROMPT="0")
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise ValueError("git is not available on PATH") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
    return result


def fetch_git_checkout(uri: str | GitUri) -> tuple[GitUri, Path]:
    """Return the canonical pinned URI and cached checkout tree, cloning only on a cache miss.

    A pinned URI whose commit is already cached runs no git at all.

    :param uri: Supply a ``git+…`` URI or a parsed one.
    :return: The URI pinned to the full commit hash, and the checkout tree root.
    :raises ValueError: If the URI is invalid or git fails.
    """

    parsed = _uri(uri)
    parent = _checkouts(parsed.repository)
    if parsed.pinned:
        assert parsed.ref is not None
        if (parent / parsed.ref).is_dir():
            return parsed, parent / parsed.ref
    parent.mkdir(parents=True, exist_ok=True)
    url = parsed.repository[len("git+") :]
    scratch = Path(tempfile.mkdtemp(prefix=".fetch-", dir=parent))
    try:
        work = scratch / "tree"
        if parsed.pinned:
            assert parsed.ref is not None
            work.mkdir()
            _git(work, "init", "-q")
            _git(work, "remote", "add", "origin", url)
            if _git(work, "fetch", "--depth", "1", "origin", parsed.ref, check=False).returncode == 0:
                _git(work, "checkout", "-q", "--detach", "FETCH_HEAD")
            else:
                _git(work, "fetch", "origin")
                _git(work, "checkout", "-q", "--detach", parsed.ref)
            if _git(work, "rev-parse", "HEAD").stdout.strip().lower() != parsed.ref:
                raise ValueError(f"{parsed.repository}: fetched commit does not match {parsed.ref}")
        elif parsed.ref is None:
            _git(scratch, "clone", "-q", "--depth", "1", url, str(work))
        elif _git(
            scratch, "clone", "-q", "--depth", "1", "--branch", parsed.ref, url, str(work), check=False
        ).returncode:
            shutil.rmtree(work, ignore_errors=True)
            _git(scratch, "clone", "-q", url, str(work))
            commit = _git(work, "rev-parse", "--verify", "--end-of-options", f"{parsed.ref}^{{commit}}").stdout.strip()
            _git(work, "checkout", "-q", "--detach", commit)
        commit = _git(work, "rev-parse", "HEAD").stdout.strip().lower()
        tree = parent / commit
        if not tree.is_dir():
            shutil.rmtree(work / ".git")
            _write_json(
                parent / f"{commit}.json",
                {
                    "format": _CHECKOUT_FORMAT,
                    "format_version": 1,
                    "repository": parsed.repository,
                    "commit": commit,
                    "fetched_at": _now(),
                },
            )
            try:
                os.rename(work, tree)
            except OSError:
                if not tree.is_dir():  # a concurrent fetch that won the rename is fine
                    raise
        return GitUri(parsed.repository, commit, parsed.subdir), tree
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def cached_git_checkout(uri: str | GitUri) -> Path | None:
    """Return the cached checkout tree of a pinned URI without running git.

    :param uri: Supply a ``git+…`` URI or a parsed one.
    :return: The tree root, or ``None`` if the URI is not pinned or not cached.
    :raises ValueError: If the URI text is invalid.
    """

    parsed = _uri(uri)
    if not parsed.pinned:
        return None
    assert parsed.ref is not None
    tree = _checkouts(parsed.repository) / parsed.ref
    return tree if tree.is_dir() else None


def _member_directory(tree: Path, uri: GitUri) -> Path:
    member = tree
    for part in uri.subdir.split("/") if uri.subdir is not None else ():
        member = member / part
        if member.is_symlink() or not member.is_dir():
            raise ValueError(f"{uri.subdir!r} is not a directory in {uri.repository} at {uri.ref}")
    if not member.resolve().is_relative_to(tree.resolve()):
        raise ValueError(f"{uri.subdir!r} leaves the checkout of {uri.repository} at {uri.ref}")
    return member


def git_member(tree: Path, uri: GitUri, marker: str) -> Path:
    """Return the member directory *uri* names inside a checkout *tree*.

    :param tree: Give the checkout tree root.
    :param uri: Give the URI whose subdirectory names the member.
    :param marker: Give the file name the member directory must hold.
    :return: The member directory.
    :raises ValueError: If the subdirectory is missing, leaves the tree, or lacks the marker.
    """

    member = _member_directory(tree, uri)
    if not (member / marker).is_file():
        if uri.subdir is not None:
            raise ValueError(f"{uri.subdir!r} has no {marker} in {uri.repository} at {uri.ref}")
        candidates = sorted(
            entry.name
            for entry in tree.iterdir()
            if entry.is_dir() and not entry.is_symlink() and (entry / marker).is_file()
        )
        found = f"; subdirectories with one: {', '.join(candidates)}" if candidates else ""
        raise ValueError(
            f"{uri.repository} at {uri.ref} has no top-level {marker}; name the member directory with #subdir{found}"
        )
    return member


def install_git_member(kind: str, uri: str, marker: str, names: Callable[[Path], Sequence[str]]) -> InstalledGitMember:
    """Fetch the member a git URI names and record it as installed.

    The entry is written only after *names* accepts the member. Every call
    refreshes ``referenced_at``, which decides which commit a short name means.

    :param kind: Name the consumer kind, such as ``"templates"``.
    :param uri: Supply a ``git+…`` URI.
    :param marker: Give the file name the member directory must hold.
    :param names: Validate the member directory and return the short names it claims.
    :return: The installed entry.
    :raises ValueError: If the URI or kind is invalid, git fails, or the member is missing or invalid.
    """

    _installed_directory(kind)  # refuse a bad kind before fetching
    canonical, tree = fetch_git_checkout(uri)
    member = git_member(tree, canonical, marker)
    claimed = tuple(names(member))
    if not all(isinstance(name, str) and name for name in claimed):
        raise ValueError(f"{canonical}: claimed names must be non-empty strings: {claimed!r}")
    assert canonical.ref is not None
    installed = InstalledGitMember(
        kind, str(canonical), canonical.repository, canonical.ref, canonical.subdir, claimed, _now(), member
    )
    _write_json(
        _installed_path(kind, installed.uri),
        {
            "format": _INSTALLED_FORMAT,
            "format_version": 1,
            "kind": kind,
            "uri": installed.uri,
            "repository": installed.repository,
            "commit": installed.commit,
            "subdir": installed.subdir,
            "names": list(claimed),
            "referenced_at": installed.referenced_at,
        },
    )
    return installed


def _read_entry(kind: str, path: Path) -> InstalledGitMember:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("format") != _INSTALLED_FORMAT:
        raise ValueError("not an installed git member entry")
    if document.get("format_version") != 1:
        raise ValueError(f"unsupported format_version {document.get('format_version')!r}")
    uri = parse_git_uri(document["uri"])
    names = document["names"]
    referenced_at = document["referenced_at"]
    if (
        document.get("kind") != kind
        or not uri.pinned
        or str(uri) != document["uri"]
        or path != _installed_path(kind, str(uri))
        or document.get("repository") != uri.repository
        or document.get("commit") != uri.ref
        or document.get("subdir") != uri.subdir
        or not isinstance(names, list)
        or not all(isinstance(name, str) and name for name in names)
        or not isinstance(referenced_at, str)
    ):
        raise ValueError("inconsistent installed git member entry")
    tree = cached_git_checkout(uri)
    if tree is None:
        raise ValueError(f"cached checkout is missing: {_checkouts(uri.repository) / str(uri.ref)}")
    assert uri.ref is not None
    member = _member_directory(tree, uri)
    return InstalledGitMember(kind, str(uri), uri.repository, uri.ref, uri.subdir, tuple(names), referenced_at, member)


def installed_git_members(kind: str) -> tuple[InstalledGitMember, ...]:
    """Return the installed entries of *kind*, sorted by URI, without running git.

    Malformed or inconsistent entries and entries whose checkout is missing are
    skipped with a warning.

    :param kind: Name the consumer kind, such as ``"templates"``.
    :return: The installed entries.
    :raises ValueError: If the kind is invalid.
    """

    directory = _installed_directory(kind)
    members: list[InstalledGitMember] = []
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
        try:
            members.append(_read_entry(kind, path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _LOGGER.warning("Skipping installed git %s entry %s: %s", kind, path, exc)
    return tuple(sorted(members, key=lambda member: member.uri))


def installed_git_member(kind: str, uri: str) -> InstalledGitMember | None:
    """Return the installed entry for exactly this pinned URI, without running git.

    :param kind: Name the consumer kind, such as ``"templates"``.
    :param uri: Supply a ``git+…`` URI; it is canonicalized first.
    :return: The entry, or ``None`` if the URI is not pinned or not installed.
    :raises ValueError: If the kind or URI is invalid.
    """

    parsed = parse_git_uri(uri)
    if not parsed.pinned:
        return None
    return next((member for member in installed_git_members(kind) if member.uri == str(parsed)), None)


def resolve_installed_name(kind: str, name: str) -> InstalledGitMember | None:
    """Return the installed entry a short name means: the latest referenced one.

    :param kind: Name the consumer kind, such as ``"templates"``.
    :param name: Give the short name.
    :return: The latest-referenced entry claiming *name*, or ``None`` if none does.
    :raises ValueError: If entries from several lineages (repository and subdirectory) claim *name*.
    """

    matches = [member for member in installed_git_members(kind) if name in member.names]
    if len({(member.repository, member.subdir) for member in matches}) > 1:
        raise ValueError(
            f"name {name!r} is claimed by several installed git {kind} "
            f"({', '.join(member.uri for member in matches)}); reference one by its URI"
        )
    return max(matches, key=lambda member: member.referenced_at, default=None)


def uninstall_git_members(kind: str, selector: str) -> tuple[InstalledGitMember, ...]:
    """Remove installed entries without running git; cached checkout trees stay.

    A pinned URI removes that entry; an unpinned URI (no ref, a branch, tag or
    abbreviated hash) removes every entry of its repository and subdirectory; a
    short name removes every entry of the lineage :func:`resolve_installed_name`
    selects.

    :param kind: Name the consumer kind, such as ``"templates"``.
    :param selector: Give a ``git+…`` URI or a short name.
    :return: The removed entries.
    :raises ValueError: If the selector is invalid, ambiguous, or matches nothing.
    """

    members = installed_git_members(kind)
    if selector.startswith("git+"):
        parsed = parse_git_uri(selector)
        if parsed.pinned:
            removed = [member for member in members if member.uri == str(parsed)]
        else:
            removed = [
                member for member in members if (member.repository, member.subdir) == (parsed.repository, parsed.subdir)
            ]
    else:
        chosen = resolve_installed_name(kind, selector)
        removed = (
            []
            if chosen is None
            else [
                member for member in members if (member.repository, member.subdir) == (chosen.repository, chosen.subdir)
            ]
        )
    if not removed:
        raise ValueError(f"no installed git {kind} match {selector!r}")
    for member in removed:
        _installed_path(kind, member.uri).unlink(missing_ok=True)
    return tuple(removed)
