"""The signed project manifest."""

from pathlib import Path

import pytest

from httk.core.project import initialize_project
from httk.core.project.manifests import create_manifest, verify_manifest
from httk.core.project.members import register_project_member

from _toy_member import toy_kind_registered


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "campaign"
    initialize_project(root, name="campaign")
    (root / "data.txt").write_text("payload", encoding="utf-8")
    return root


def test_create_then_verify_is_trusted(project: Path) -> None:
    path = create_manifest(project)
    assert path.is_file()
    verification = verify_manifest(project)
    assert verification.verdict == "valid_trusted"
    assert verification.valid


def test_tampering_is_detected(project: Path) -> None:
    create_manifest(project)
    (project / "data.txt").write_text("tampered", encoding="utf-8")
    verification = verify_manifest(project)
    assert not verification.valid
    assert verification.verdict == "invalid"


def test_member_manifest_exclusions_are_applied(project: Path) -> None:
    member = project / "work"
    member.mkdir()
    (member / ".toy-seal.json").write_text("{}", encoding="utf-8")
    (member / "kept.txt").write_text("k", encoding="utf-8")
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        create_manifest(project)
        # The member's own seal file is excluded, so writing it again after the
        # manifest is created is not a discrepancy; its payload is still covered.
        (member / ".toy-seal.json").write_text('{"x":1}', encoding="utf-8")
        assert verify_manifest(project).valid
        # A payload file the member did not exclude is covered.
        (member / "kept.txt").write_text("changed", encoding="utf-8")
        assert not verify_manifest(project).valid


def test_verify_without_manifest_raises(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verify_manifest(project)
