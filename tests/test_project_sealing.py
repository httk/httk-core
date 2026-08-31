"""Project seal documents and whole-tree verification."""

from pathlib import Path

import pytest

from httk.core.project import initialize_project
from httk.core.project.members import register_project_member
from httk.core.project.sealing import (
    SealError,
    is_project_sealed,
    project_seal_path,
    read_seal,
    resolve_seal_keys,
    seal_project,
    unseal_project,
    verify_project,
    verify_seal,
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
