"""A toy project-member handler used to exercise the core member machinery.

The toy is a ``toy`` kind whose member is an ordinary subdirectory. It seals
itself with a trivial core-format seal written through the same sealing
primitives core uses, so a project seal can transitively cover it and the whole
verify/manifest/doctor path can be driven without *httk-workflow* installed.
"""

import contextlib
import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path

from httk.core.project import sealing
from httk.core.records import file_records

_SEAL = ".toy-seal.json"


class ToyMemberHandler:
    """A minimal :class:`~httk.core.project.members.ProjectMemberHandler`."""

    def manifest_exclusions(self, project_root: Path, member_relpath: str) -> tuple[str, ...]:
        return (f"{member_relpath}/{_SEAL}",)

    def seal(self, member_root: Path, keys: object) -> Path:
        assert isinstance(keys, sealing.SealKeys)
        records = file_records(member_root, exclusions=(_SEAL,))
        body = sealing.build_seal_body("toy", {"member": member_root.name}, records)
        return sealing.write_seal(member_root / _SEAL, body, keys.keys)

    def seal_digest(self, member_root: Path) -> tuple[str, str]:
        path = member_root / _SEAL
        if not path.is_file():
            raise sealing.SealError(f"toy member is unsealed: {member_root}")
        return member_root.name, hashlib.sha256(path.read_bytes()).hexdigest()

    def verify(
        self, member_root: Path, *, trusted_keys: Sequence[str], deep: bool
    ) -> tuple[dict[str, object], ...]:
        path = member_root / _SEAL
        if not path.is_file():
            absent = sealing.SealVerification(False, sealing.INVALID, "not sealed", (), (), ())
            return (absent.as_entry("toy", member_root.name),)
        base = sealing.verify_seal(path, trusted_keys=trusted_keys)
        seal = sealing.read_seal(path)
        actual = file_records(member_root, exclusions=(_SEAL,))
        combined = sealing._combine(base, sealing.diff_records(list(seal.records), actual))
        return (combined.as_entry("toy", member_root.name),)

    def doctor(self, member_root: Path, *, repair: bool) -> tuple[dict[str, object], ...]:
        sealed = (member_root / _SEAL).is_file()
        return (
            {
                "check": f"toy:{member_root.name}",
                "status": "ok" if sealed else "warning",
                "message": "the toy member is sealed" if sealed else "the toy member is not sealed",
                "repairable": False,
                "repaired": False,
                "action": None,
                "details": {},
            },
        )

    def scan_project(self, project_root: Path, *, repair: bool) -> tuple[dict[str, object], ...]:
        # A stand-in for a real "unregistered members under this project" scan:
        # runs at project scope regardless of what members.json records.
        return (
            {
                "check": "toy:scan",
                "status": "ok",
                "message": f"toy scanned {project_root.name}",
                "repairable": False,
                "repaired": False,
                "action": None,
                "details": {},
            },
        )

    def guard(self, member_root: Path) -> contextlib.AbstractContextManager[object]:
        return contextlib.nullcontext()


@contextlib.contextmanager
def toy_kind_registered(kind: str = "toy") -> Iterator[None]:
    """Register the toy handler for *kind* and restore the registry afterwards."""

    from httk.core.register.members import project_member_kinds, register_project_member_kind

    saved = dict(project_member_kinds._by_key)
    register_project_member_kind(kind, ToyMemberHandler)
    try:
        yield
    finally:
        project_member_kinds._by_key.clear()
        project_member_kinds._by_key.update(saved)
