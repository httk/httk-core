"""The on-disk project-member registry and the kind registry."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from httk.core.project import initialize_project
from httk.core.project.members import (
    ProjectMember,
    members_path,
    project_members,
    register_project_member,
    unregister_project_member,
    update_project_member_path,
)
from httk.core.project.sealing import SealedError, seal_project, unseal_project
from httk.core.register.members import (
    known_project_member_kinds,
    project_member_handler,
    project_member_kinds,
    register_project_member_kind,
)

from _toy_member import ToyMemberHandler, toy_kind_registered


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "campaign"
    initialize_project(root, name="campaign")
    (root / "work").mkdir()
    return root


@pytest.fixture(autouse=True)
def _isolate_kinds() -> Iterator[None]:
    saved = dict(project_member_kinds._by_key)
    try:
        yield
    finally:
        project_member_kinds._by_key.clear()
        project_member_kinds._by_key.update(saved)


def test_kind_registry_resolves_and_reports() -> None:
    register_project_member_kind("toy", ToyMemberHandler)
    assert "toy" in known_project_member_kinds()
    handler = project_member_handler("toy")
    assert isinstance(handler, ToyMemberHandler)


def test_unknown_kind_names_the_kind() -> None:
    with pytest.raises(LookupError) as excinfo:
        project_member_handler("nope")
    assert "nope" in str(excinfo.value)


def test_register_is_idempotent_and_normalizes(project: Path) -> None:
    register_project_member(project, project / "work", "toy")
    members = register_project_member(project, "work", "toy")
    assert members == (ProjectMember(path="work", kind="toy"),)
    assert members_path(project).is_file()
    assert project_members(project) == (ProjectMember(path="work", kind="toy"),)


def test_register_replaces_kind(project: Path) -> None:
    register_project_member(project, "work", "toy")
    members = register_project_member(project, "work", "other")
    assert members == (ProjectMember(path="work", kind="other"),)


def test_register_refuses_path_outside_project(project: Path) -> None:
    with pytest.raises(ValueError):
        register_project_member(project, project.parent / "elsewhere", "toy")


def test_unregister_and_update(project: Path) -> None:
    (project / "moved").mkdir()
    register_project_member(project, "work", "toy")
    moved = update_project_member_path(project, "work", "moved")
    assert moved == (ProjectMember(path="moved", kind="toy"),)
    with pytest.raises(ValueError):
        update_project_member_path(project, "work", "moved")
    remaining = unregister_project_member(project, "moved")
    assert remaining == ()
    with pytest.raises(ValueError):
        unregister_project_member(project, "moved")


def test_registration_refused_while_sealed(project: Path) -> None:
    with toy_kind_registered():
        seal_project(project)
        with pytest.raises(SealedError):
            register_project_member(project, "work", "toy")
        unseal_project(project)
        register_project_member(project, "work", "toy")


def test_missing_registry_is_empty(project: Path) -> None:
    assert project_members(project) == ()
