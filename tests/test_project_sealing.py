"""Project seal documents and whole-tree verification."""

from pathlib import Path

import pytest

from httk.core.project import initialize_project
from httk.core.project.members import register_project_member
from httk.core.project.sealing import (
    SealError,
    build_seal_body,
    is_project_sealed,
    project_seal_path,
    read_seal,
    resolve_seal_keys,
    seal_project,
    unseal_project,
    verify_project,
    verify_seal,
    write_seal,
)

from _toy_member import ToyMemberHandler, toy_kind_registered


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "campaign"
    initialize_project(root, name="campaign")
    (root / "loose.txt").write_text("loose", encoding="utf-8")
    return root


def _seal_member(root: Path, relpath: str) -> None:
    keys = resolve_seal_keys(["project"], project_root=root)
    ToyMemberHandler().seal(root / relpath, keys)


def test_seal_and_verify_projectless_member(project: Path) -> None:
    with toy_kind_registered():
        member = project / "work"
        member.mkdir()
        (member / "result.dat").write_text("r", encoding="utf-8")
        register_project_member(project, "work", "toy")
        _seal_member(project, "work")
        seal_project(project)
        assert is_project_sealed(project)

        report = verify_project(project, trusted_keys=(), deep=True)
        # Two entries: the project and the member, both valid (signatures verify)
        # but untrusted because no anchor was supplied.
        levels = [entry["level"] for entry in report.entries]
        assert levels == ["project", "toy"]
        assert report.ok
        assert all(entry["verdict"] == "valid_unknown_key" for entry in report.entries)


def test_trusted_when_pinned_key_supplied(project: Path) -> None:
    with toy_kind_registered():
        member = project / "work"
        member.mkdir()
        register_project_member(project, "work", "toy")
        _seal_member(project, "work")
        seal_project(project)
        from httk.core.project.anchor import read_project

        pinned = str(read_project(project)["public_key"])
        report = verify_project(project, trusted_keys=[pinned], deep=True)
        assert report.ok
        assert all(entry["verdict"] == "valid_trusted" for entry in report.entries)


def test_seal_refuses_unsealed_member(project: Path) -> None:
    with toy_kind_registered():
        (project / "work").mkdir()
        register_project_member(project, "work", "toy")
        with pytest.raises(SealError) as excinfo:
            seal_project(project)
        assert "work" in str(excinfo.value)


def test_seal_refuses_unknown_kind(project: Path) -> None:
    (project / "work").mkdir()
    register_project_member(project, "work", "ghost")
    with pytest.raises(SealError) as excinfo:
        seal_project(project)
    assert "ghost" in str(excinfo.value)


def test_verify_reports_member_tamper(project: Path) -> None:
    with toy_kind_registered():
        member = project / "work"
        member.mkdir()
        (member / "result.dat").write_text("r", encoding="utf-8")
        register_project_member(project, "work", "toy")
        _seal_member(project, "work")
        seal_project(project)
        (member / "result.dat").write_text("tampered", encoding="utf-8")
        report = verify_project(project, trusted_keys=(), deep=True)
        assert not report.ok
        member_entry = next(entry for entry in report.entries if entry["level"] == "toy")
        assert member_entry["verdict"] == "invalid"


def test_verify_missing_handler_is_invalid_entry(project: Path) -> None:
    member = project / "work"
    member.mkdir()
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        _seal_member(project, "work")
        seal_project(project)
    # Kind registration dropped: the project seal still exists but no handler.
    report = verify_project(project, trusted_keys=(), deep=True)
    assert not report.ok
    member_entry = next(entry for entry in report.entries if entry["level"] == "member")
    assert "no handler" in str(member_entry["reason"])


def test_verify_unsealed_project(project: Path) -> None:
    report = verify_project(project)
    assert not report.ok
    assert report.entries[0]["verdict"] == "invalid"
    assert report.entries[0]["reason"] == "not sealed"


def test_seal_roundtrip_signature(project: Path) -> None:
    seal_project(project)
    verification = verify_seal(project_seal_path(project))
    assert verification.valid
    seal = read_seal(project_seal_path(project))
    assert seal.kind == "project"
    unseal_project(project)
    assert not is_project_sealed(project)


def test_write_seal_read_seal_roundtrip(project: Path) -> None:
    keys = resolve_seal_keys(["project"], project_root=project)
    body = build_seal_body("custom", {"id": "x"}, [{"path": "a", "type": "file"}])
    path = project / "httk_project" / "custom-seal.json"
    write_seal(path, body, keys.keys)
    seal = read_seal(path)
    assert seal.kind == "custom"
    assert seal.subject == {"id": "x"}
    assert list(seal.records) == [{"path": "a", "type": "file"}]
    assert verify_seal(path).valid


def test_verify_signed_body_valid_tampered_and_untrusted(project: Path) -> None:
    from httk.core._json import json_bytes
    from httk.core.crypto import ed25519_public_key
    from httk.core.project import format_public_key, key_fingerprint
    from httk.core.project.sealing import sign_seal_body, verify_signed_body

    seed = b"\x01" * 32
    fingerprint = key_fingerprint(format_public_key(ed25519_public_key(seed)))
    body = build_seal_body("custom", {"id": "x"}, [{"path": "a", "type": "file"}])
    body_sha256, signatures = sign_seal_body(body, [("identity", seed)])
    body_bytes = json_bytes(body)

    valid = verify_signed_body(body_bytes, body_sha256, signatures)
    assert valid.valid and valid.verdict == "valid_unknown_key"

    trusted = verify_signed_body(body_bytes, body_sha256, signatures, trusted_keys=[fingerprint])
    assert trusted.verdict == "valid_trusted"

    tampered = verify_signed_body(body_bytes + b" ", body_sha256, signatures)
    assert not tampered.valid and tampered.verdict == "invalid"

    untrusted = verify_signed_body(body_bytes, body_sha256, signatures, trusted_keys=["sha256:deadbeef"])
    assert untrusted.verdict == "valid_unknown_key"
