"""The core-owned ``httk project doctor|manifest|seal|unseal|verify-seal`` leaves."""

import argparse
from collections.abc import Iterator
from pathlib import Path

import pytest

from httk.core import CLIContext, register_cli_extension
from httk.core.project import initialize_project
from httk.core.project.cli import build_parser, command
from httk.core.project.members import register_project_member
from httk.core.project.sealing import resolve_seal_keys
from httk.core.register.cli import _cli_extensions
from httk.core.register.members import project_member_kinds

from _toy_member import ToyMemberHandler, toy_kind_registered


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "campaign"
    initialize_project(root, name="campaign")
    (root / "loose.txt").write_text("loose", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    kinds = dict(project_member_kinds._by_key)
    exts = {name: list(providers) for name, providers in _cli_extensions.items()}
    try:
        yield
    finally:
        project_member_kinds._by_key.clear()
        project_member_kinds._by_key.update(kinds)
        _cli_extensions.clear()
        _cli_extensions.update(exts)


def _run(project: Path, *argv: str) -> int:
    return command(list(argv), CLIContext("httk", project))


def test_doctor_reports_and_exit_zero(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(project, "doctor")
    out = capsys.readouterr().out
    assert code == 0
    assert "key_pin" in out
    assert "manifest" in out


def test_doctor_unknown_member_kind_is_error(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    register_project_member(project, "work", "ghost")
    code = _run(project, "doctor")
    out = capsys.readouterr().out
    assert "no registered handler" in out
    assert code == 1


def test_doctor_concatenates_member_findings(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        code = _run(project, "doctor")
    out = capsys.readouterr().out
    assert "toy:work" in out
    assert code == 0


def test_manifest_create_and_verify(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "manifest", "create") == 0
    assert (project / "httk_project" / "manifest.jsonl.bz2").is_file()
    code = _run(project, "manifest", "verify")
    out = capsys.readouterr().out
    assert code == 0
    assert "valid_trusted" in out


def test_seal_and_verify_seal_ok(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "seal") == 0
    code = _run(project, "verify-seal")
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip().endswith("ok")


def test_verify_seal_failed_after_tamper(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(project, "seal")
    capsys.readouterr()
    (project / "loose.txt").write_text("tampered", encoding="utf-8")
    code = _run(project, "verify-seal")
    out = capsys.readouterr().out
    assert code == 1
    assert out.strip().endswith("FAILED")


def test_verify_seal_untrusted_exit_three(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(project, "seal")
    capsys.readouterr()
    # Drop the pin so the signing key is no longer a trust anchor: the signature
    # still verifies, but nothing trusts it.
    import json

    manifest = project / "httk_project" / "project.json"
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata.pop("public_key", None)
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    code = _run(project, "verify-seal")
    out = capsys.readouterr().out
    assert code == 3
    assert out.strip().endswith("UNTRUSTED")


def test_unseal_requires_force_without_terminal(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(project, "seal")
    capsys.readouterr()
    assert _run(project, "unseal") == 1
    assert _run(project, "unseal", "--force") == 0
    from httk.core.project.sealing import is_project_sealed

    assert not is_project_sealed(project)


def test_seal_deep_verify_with_member(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    member = project / "work"
    member.mkdir()
    (member / "r.dat").write_text("r", encoding="utf-8")
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        ToyMemberHandler().seal(member, resolve_seal_keys(["project"], project_root=project))
        assert _run(project, "seal") == 0
        capsys.readouterr()
        code = _run(project, "verify-seal")
        out = capsys.readouterr().out
    assert code == 0
    assert "toy\twork" in out


def _colliding_provider(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("doctor", help="workflow doctor", description="workflow doctor")
    parser.set_defaults(handler=lambda a, c: 0, help_parser=parser)


def test_colliding_extension_leaf_is_skipped(project: Path) -> None:
    register_cli_extension("project", _colliding_provider)
    # build_parser must not raise even though the extension re-adds `doctor`.
    parser = build_parser("httk project")
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert "doctor" in sub.choices
