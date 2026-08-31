"""The on-disk registry of a project's members, and the handler protocol.

A *member* is a self-contained subtree a project holds whose internals another
module owns — a workflow workspace is the first one. The project records only
that a member of a given *kind* lives at a given path; everything about what the
member contains, how it is sealed, and how it is checked is delegated to the
handler that module registers for the kind (see
:mod:`httk.core.register.members`).

Core owns the verbs — seal, manifest, repair, verify — and this on-disk registry
that tells those verbs which subtrees to hand off and to whom. It interprets a
member no further than its path and kind.
"""

import os
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from .._json import read_json, write_json_atomic
from .anchor import PROJECT_DIRECTORY

__all__ = [
    "MEMBERS_FORMAT",
    "MEMBERS_FORMAT_VERSION",
    "ProjectMember",
    "ProjectMemberHandler",
    "members_path",
    "project_members",
    "register_project_member",
    "set_project_member_name",
    "unregister_project_member",
    "update_project_member_path",
]

MEMBERS_FORMAT = "httk-project-members"
MEMBERS_FORMAT_VERSION = 1


@dataclass(frozen=True)
class ProjectMember:
    """One member a project holds: a subtree of a given kind.

    :param path: The member's posix relpath below the project root (``"."`` is
        the project root itself).
    :param kind: The member kind, whose handler owns the member's internals.
    :param name: The member's recorded name, or ``None`` when it has none.
    """

    path: str
    kind: str
    name: str | None = None


class ProjectMemberHandler(Protocol):
    """What core needs from the module that owns one member kind.

    Every method takes the member's own root — ``project_root / member.path`` —
    rather than the project, so a handler never has to rediscover where it lives.
    The manifest, repair, and verify verbs core owns call exactly these; a member
    seals through its own module, and core only records the resulting digest.
    """

    def manifest_exclusions(self, project_root: Path, member_relpath: str) -> tuple[str, ...]:
        """Return the manifest exclusions this member contributes.

        These are ``fnmatch`` patterns on posix relpaths *below the project
        root* (not the member root): the member decides which of its own
        internals — control directories, working scratch — the project manifest
        must leave out, while its payload files stay covered.

        :param project_root: The project root the patterns are relative to.
        :param member_relpath: This member's relpath below the project root.
        :return: The exclusion patterns this member contributes.
        """

        ...

    def seal_digest(self, member_root: Path) -> tuple[str, str]:
        """Return this member's identifier and the SHA-256 of its seal bytes.

        The digest is what a project seal records for the member, so a project
        seal transitively pins the member without re-hashing its payload.

        :param member_root: This member's root directory.
        :return: The member identifier and the hex SHA-256 of its seal file.
        :raises httk.core.project.sealing.SealError: If the member is unsealed.
        """

        ...

    def verify(
        self,
        member_root: Path,
        *,
        trusted_keys: Sequence[str],
        deep: bool,
    ) -> tuple[dict[str, object], ...]:
        """Verify this member and return its report entries.

        Each entry is a mapping in the whole-tree verification shape — ``level``,
        ``subject``, ``valid``, ``verdict``, ``reason``, ``signers``,
        ``missing_signers``, and ``discrepancies`` (a list of ``{kind, path}``) —
        so the project report concatenates a member's entries with its own.

        :param member_root: This member's root directory.
        :param trusted_keys: Trust anchors to classify the signers against.
        :param deep: Whether to recurse into every seal the member references.
        :return: The member's verification entries.
        """

        ...

    def repair(self, member_root: Path, *, apply: bool) -> tuple[dict[str, object], ...]:
        """Repair this member, or report only, returning its findings.

        Each finding is a mapping in the repair shape — ``check``, ``status``,
        ``message``, ``repairable``, ``repaired``, ``action``, ``details`` — so
        they concatenate with core's own anchor findings. Repairs are applied by
        default; ``apply=False`` is a dry run that mutates nothing.

        :param member_root: This member's root directory.
        :param apply: Whether to apply repairs; ``False`` reports only.
        :return: The member's repair findings.
        """

        ...

    def scan_project(self, project_root: Path, *, apply: bool, adopt: bool) -> tuple[dict[str, object], ...]:
        """Optionally scan the whole project for members of this kind.

        Core calls this once per registered kind at project scope, whether or not
        any member of the kind is registered, so a handler can surface members
        present on disk but missing from ``members.json`` — the exact rescue an
        empty registry needs. Repairs are applied by default; ``apply=False`` is a
        dry run that mutates nothing, and *adopt* tells the scan whether to also
        (re)establish members' machine-local links on this machine. It is
        optional: core invokes it only when the handler defines it. Findings use
        the same mapping shape as :meth:`repair`.

        :param project_root: The project root to scan.
        :param apply: Whether to apply repairs; ``False`` reports only.
        :param adopt: Whether to adopt members of this kind on this machine.
        :return: The project-scope findings for this kind.
        """

        ...

    def adopt(self, member_root: Path, *, name: str | None) -> tuple[dict[str, object], ...]:
        """Optionally (re)establish this member's local links on this machine.

        Adoption is the act of rebuilding whatever per-user or machine-local
        links a member needs to be usable *here* — for example, httk-workflow
        registers the member's workspace in the per-user name registry under its
        recorded *name*. It is idempotent and never mutates sealed state. Core
        invokes it only when the handler defines it, passing the member's
        recorded name; findings use the same mapping shape as :meth:`repair`.

        :param member_root: This member's root directory.
        :param name: The member's recorded name, or ``None`` when it has none.
        :return: The adoption findings for this member.
        """

        ...

    def guard(self, member_root: Path) -> AbstractContextManager[object]:
        """Return a context manager fencing the member while it is snapshotted.

        A member that must be quiescent to be described faithfully — a workspace
        with running jobs — returns a guard that acquires that quiescence and
        raises if it cannot. A member with nothing to fence returns
        :func:`contextlib.nullcontext`.

        :param member_root: This member's root directory.
        :return: A context manager held around the snapshot.
        """

        ...


def members_path(project_root: str | os.PathLike[str]) -> Path:
    """Return where a project's member registry lives.

    :param project_root: The project root whose member registry path to build.
    :return: The ``httk_project/members.json`` path.
    """

    return Path(project_root).expanduser().resolve() / PROJECT_DIRECTORY / "members.json"


def project_members(project_root: str | os.PathLike[str]) -> tuple[ProjectMember, ...]:
    """Return the members registered in a project, in recorded order.

    A missing registry is an empty project, not an error.

    :param project_root: The project root whose members to read.
    :return: The registered members.
    :raises ValueError: If the registry file is malformed.
    """

    path = members_path(project_root)
    if not path.is_file():
        return ()
    document = read_json(path)
    if document.get("format") != MEMBERS_FORMAT or document.get("format_version") != MEMBERS_FORMAT_VERSION:
        raise ValueError(f"not an {MEMBERS_FORMAT} version {MEMBERS_FORMAT_VERSION} document: {path}")
    raw = document.get("members", [])
    if not isinstance(raw, list):
        raise ValueError(f"project members must be an array: {path}")
    members: list[ProjectMember] = []
    seen: set[str] = set()
    seen_names: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("kind"), str):
            raise ValueError(f"malformed project member record: {item!r}")
        name = item.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError(f"project member name must be a string or absent in {path}: {item!r}")
        relpath = str(item["path"])
        posix = PurePosixPath(relpath)
        if posix.is_absolute() or ".." in posix.parts:
            raise ValueError(f"project member path is absolute or escapes the project in {path}: {relpath!r}")
        if relpath in seen:
            raise ValueError(f"project member path is recorded more than once in {path}: {relpath!r}")
        seen.add(relpath)
        if isinstance(name, str):
            if name in seen_names:
                raise ValueError(f"project member name is recorded more than once in {path}: {name!r}")
            seen_names.add(name)
        members.append(ProjectMember(path=relpath, kind=str(item["kind"]), name=name))
    return tuple(members)


def _relative_member_path(project_root: Path, path: str | os.PathLike[str]) -> str:
    """Normalize *path* to a posix relpath under *project_root*, or refuse it."""

    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else project_root / candidate
    try:
        relative = absolute.resolve().relative_to(project_root)
    except ValueError:
        raise ValueError(f"project member path is outside the project: {path}") from None
    return relative.as_posix()


def _write_members(path: Path, members: Sequence[ProjectMember]) -> None:
    document = {
        "format": MEMBERS_FORMAT,
        "format_version": MEMBERS_FORMAT_VERSION,
        "members": [
            {"path": member.path, "kind": member.kind, **({"name": member.name} if member.name is not None else {})}
            for member in members
        ],
    }
    write_json_atomic(path, document, durable=True)


def _refuse_when_sealed(project_root: Path) -> None:
    # Imported lazily: sealing imports the member registry, so the reverse edge
    # must not be a module-load-time import.
    from .sealing import is_project_sealed

    if is_project_sealed(project_root):
        from .sealing import SealedError

        raise SealedError("cannot change project members while the project is sealed; unseal it first")


def register_project_member(
    project_root: str | os.PathLike[str],
    path: str | os.PathLike[str],
    kind: str,
    *,
    name: str | None = None,
) -> tuple[ProjectMember, ...]:
    """Record that a member of *kind* lives at *path*, idempotently.

    The path is normalized to a posix relpath below the project root and a path
    outside the project is refused. Registering the same path again replaces its
    kind and name.

    :param project_root: The project root whose registry to update.
    :param path: The member's path, absolute or relative to the project root.
    :param kind: The member kind whose handler owns the member.
    :param name: The member's recorded name, or ``None`` for none.
    :return: The members after the update.
    :raises httk.core.project.sealing.SealedError: If the project is sealed.
    :raises ValueError: If the path is outside the project or the name duplicates another member's.
    """

    root = Path(project_root).expanduser().resolve()
    _refuse_when_sealed(root)
    relative = _relative_member_path(root, path)
    members = [member for member in project_members(root) if member.path != relative]
    if name is not None and any(member.name == name for member in members):
        raise ValueError(f"project member name {name!r} is already recorded in {members_path(root)}")
    members.append(ProjectMember(path=relative, kind=kind, name=name))
    members.sort(key=lambda member: member.path)
    _write_members(members_path(root), members)
    return tuple(members)


def unregister_project_member(
    project_root: str | os.PathLike[str],
    path: str | os.PathLike[str],
) -> tuple[ProjectMember, ...]:
    """Remove the member recorded at *path*.

    :param project_root: The project root whose registry to update.
    :param path: The member's path, absolute or relative to the project root.
    :return: The members after the removal.
    :raises httk.core.project.sealing.SealedError: If the project is sealed.
    :raises ValueError: If the path is outside the project or no member is recorded there.
    """

    root = Path(project_root).expanduser().resolve()
    _refuse_when_sealed(root)
    relative = _relative_member_path(root, path)
    members = list(project_members(root))
    kept = [member for member in members if member.path != relative]
    if len(kept) == len(members):
        raise ValueError(f"no project member is recorded at {relative!r}")
    _write_members(members_path(root), kept)
    return tuple(kept)


def update_project_member_path(
    project_root: str | os.PathLike[str],
    old: str | os.PathLike[str],
    new: str | os.PathLike[str],
) -> tuple[ProjectMember, ...]:
    """Move the member recorded at *old* to *new*, keeping its kind.

    :param project_root: The project root whose registry to update.
    :param old: The member's current path, absolute or relative to the root.
    :param new: The member's new path, absolute or relative to the root.
    :return: The members after the move.
    :raises httk.core.project.sealing.SealedError: If the project is sealed.
    :raises ValueError: If a path is outside the project or no member is at *old*.
    """

    root = Path(project_root).expanduser().resolve()
    _refuse_when_sealed(root)
    old_relative = _relative_member_path(root, old)
    new_relative = _relative_member_path(root, new)
    members = list(project_members(root))
    if all(member.path != old_relative for member in members):
        raise ValueError(f"no project member is recorded at {old_relative!r}")
    moved = [
        ProjectMember(path=new_relative, kind=member.kind, name=member.name) if member.path == old_relative else member
        for member in members
    ]
    moved.sort(key=lambda member: member.path)
    _write_members(members_path(root), moved)
    return tuple(moved)


def set_project_member_name(
    project_root: str | os.PathLike[str],
    path: str | os.PathLike[str],
    name: str | None,
) -> tuple[ProjectMember, ...]:
    """Set (or clear) the recorded name of the member at *path*.

    :param project_root: The project root whose registry to update.
    :param path: The member's path, absolute or relative to the project root.
    :param name: The name to record, or ``None`` to clear it.
    :return: The members after the update.
    :raises httk.core.project.sealing.SealedError: If the project is sealed.
    :raises ValueError: If no member is at *path* or the name duplicates another member's.
    """

    root = Path(project_root).expanduser().resolve()
    _refuse_when_sealed(root)
    relative = _relative_member_path(root, path)
    members = list(project_members(root))
    if all(member.path != relative for member in members):
        raise ValueError(f"no project member is recorded at {relative!r}")
    if name is not None and any(member.path != relative and member.name == name for member in members):
        raise ValueError(f"project member name {name!r} is already recorded in {members_path(root)}")
    renamed = [
        ProjectMember(path=member.path, kind=member.kind, name=name) if member.path == relative else member
        for member in members
    ]
    _write_members(members_path(root), renamed)
    return tuple(renamed)
