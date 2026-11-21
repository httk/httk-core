"""The core-owned ``httk project check|repair|manifest|seal|unseal|verify`` leaves."""

from collections.abc import Iterator
from pathlib import Path

import _toy_member
import pytest
from _toy_member import ToyMemberHandler, toy_kind_registered

from httk.core import CLIContext
from httk.core.identity import add_identity
from httk.core.project import initialize_project
from httk.core.project.cli import command
from httk.core.project.members import register_project_member
from httk.core.project.sealing import resolve_seal_keys
from httk.core.register.members import project_member_kinds, register_project_member_kind


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "campaign"
    initialize_project(root, name="campaign")
    (root / "loose.txt").write_text("loose", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Redirect the per-user config home so a real ~/.config/httk identity key
    # cannot become a trust anchor and turn an "untrusted" seal into a trusted
    # one (or vice versa).
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    kinds = dict(project_member_kinds._by_key)
    try:
        yield
    finally:
        project_member_kinds._by_key.clear()
        project_member_kinds._by_key.update(kinds)


def _run(project: Path, *argv: str) -> int:
    return command(list(argv), CLIContext("httk", project))


def test_repair_reports_and_exit_zero(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(project, "repair")
    out = capsys.readouterr().out
    assert code == 0
    assert "key_pin" in out
    assert "manifest" in out


def test_repair_unknown_member_kind_is_error(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    register_project_member(project, "work", "ghost")
    code = _run(project, "repair")
    out = capsys.readouterr().out
    assert "no registered handler" in out
    assert code == 1


def test_repair_concatenates_member_findings(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        code = _run(project, "repair")
    out = capsys.readouterr().out
    assert "toy:work" in out
    # Default applies repairs (apply=True) to each member.
    assert _toy_member.REPAIR_CALLS == [("work", True)]
    assert code == 0


def test_manifest_and_verify_manifest(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "manifest") == 0
    assert (project / "httk_project" / "manifest.jsonl.bz2").is_file()
    capsys.readouterr()
    code = _run(project, "verify", "--manifest")
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines() == ["valid", out.splitlines()[1]]
    assert out.splitlines()[1].startswith("valid_trusted: ")


@pytest.mark.parametrize("order", ["target-first", "option-first"])
def test_verify_manifest_of_named_project(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], order: str
) -> None:
    assert _run(project, "manifest") == 0
    capsys.readouterr()
    argv = [str(project), "--manifest"] if order == "target-first" else ["--manifest", str(project)]
    # Run from elsewhere so only the TARGET can name the project.
    assert _run(tmp_path, "verify", *argv) == 0
    assert capsys.readouterr().out.startswith("valid\nvalid_trusted: ")


def test_verify_manifest_path_and_tamper(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    elsewhere = tmp_path / "elsewhere.jsonl.bz2"
    assert _run(project, "manifest", str(project), "--manifest", str(elsewhere)) == 0
    assert elsewhere.is_file()
    capsys.readouterr()
    assert _run(project, "verify", "--manifest-file", str(elsewhere), str(project)) == 0
    assert "valid_trusted" in capsys.readouterr().out
    (project / "loose.txt").write_text("tampered", encoding="utf-8")
    assert _run(project, "verify", str(project), "--manifest-file", str(elsewhere)) == 1
    assert capsys.readouterr().out.startswith("invalid\n")


def test_verify_export_mode_selected_by_zip_target(project: Path, tmp_path: Path, capsys) -> None:
    from httk.core.project.export import export_project

    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    export_project(first, project)
    export_project(second, project)
    assert _run(tmp_path, "verify", str(first), str(second)) == 0
    out = capsys.readouterr().out
    assert f"=== {first} ===" in out and f"=== {second} ===" in out
    assert out.count("fingerprint: sha256:") == 2


@pytest.mark.parametrize(
    ("extra", "option"),
    [
        (["--shallow"], "--shallow"),
        (["--json"], "--json"),
        (["--manifest"], "--manifest"),
        (["--manifest-file", "m.jsonl.bz2"], "--manifest-file"),
    ],
)
def test_verify_export_rejects_options_of_other_modes(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], option: str
) -> None:
    from httk.core.project.export import export_project

    archive = tmp_path / "a.zip"
    export_project(archive, project)
    assert _run(tmp_path, "verify", str(archive), *extra) == 2
    assert f"{option} does not apply to export verification" in capsys.readouterr().err


def test_verify_missing_zip_target_reaches_export_verification(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(project, "seal") == 0
    capsys.readouterr()
    assert _run(project, "verify", "typo.zip") == 1
    captured = capsys.readouterr()
    assert "invalid export ZIP" in captured.err
    assert "ok" not in captured.out


def test_verify_directory_named_zip_is_export_mode(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "seal") == 0
    (project / "dir.zip").mkdir()
    capsys.readouterr()
    assert _run(project, "verify", str(project / "dir.zip")) == 1
    assert "invalid export ZIP" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["EXPORT.ZIP", "backup.httkexport"])
def test_verify_export_by_suffix_case_or_zip_content(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    from httk.core.project.export import export_project

    archive = tmp_path / "export.zip"
    export_project(archive, project)
    renamed = archive.rename(tmp_path / name)
    assert _run(tmp_path, "verify", str(renamed)) == 0
    assert "fingerprint: sha256:" in capsys.readouterr().out


def test_verify_rejects_mixed_and_non_directory_targets(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(project, "verify", "a.zip", str(project)) == 2
    assert "cannot mix export ZIPs and project targets" in capsys.readouterr().err
    missing = tmp_path / "no-such-project"
    assert _run(project, "verify", str(missing)) == 2
    assert f"seal verification TARGET is not a directory: {missing}" in capsys.readouterr().err
    assert _run(project, "verify", "--manifest", str(project / "loose.txt")) == 2
    assert "manifest verification TARGET is not a directory" in capsys.readouterr().err


def test_verify_rejects_inapplicable_options(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "verify", "--expect-key", "sha256:00") == 2
    assert "--expect-key does not apply to seal verification" in capsys.readouterr().err
    assert _run(project, "verify", "--manifest", "--shallow") == 2
    assert "--shallow does not apply to manifest verification" in capsys.readouterr().err
    assert _run(project, "verify", str(project), str(project)) == 2
    assert "at most one project TARGET" in capsys.readouterr().err


def test_seal_and_verify_seal_ok(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "seal") == 0
    code = _run(project, "verify")
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip().endswith("ok")


def test_verify_seal_failed_after_tamper(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(project, "seal")
    capsys.readouterr()
    (project / "loose.txt").write_text("tampered", encoding="utf-8")
    code = _run(project, "verify")
    out = capsys.readouterr().out
    assert code == 1
    assert out.strip().endswith("FAILED")


def test_verify_seal_json_shape(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    _run(project, "seal")
    capsys.readouterr()
    assert _run(project, "verify", "--json", "--shallow") == 0
    document = json.loads(capsys.readouterr().out)
    assert set(document) == {"entries", "ok", "trusted"}
    assert document["ok"] is True and document["trusted"] is True


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
    code = _run(project, "verify")
    out = capsys.readouterr().out
    assert code == 3
    assert out.strip().endswith("UNTRUSTED")


def test_verify_seal_trusts_all_local_operator_identity_keys(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    add_identity("alice", "Alice", "alice@example.test")
    add_identity("bob", "Bob", "bob@example.test")
    assert _run(project, "seal", "--keys", "identity:bob") == 0
    capsys.readouterr()

    import json

    manifest = project / "httk_project" / "project.json"
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata.pop("public_key", None)
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    code = _run(project, "verify")
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip().endswith("ok")


def test_unseal_requires_yes_without_terminal(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(project, "seal")
    capsys.readouterr()
    assert _run(project, "unseal") == 1
    assert "requires --yes" in capsys.readouterr().err
    assert _run(project, "unseal", "--force") == 2
    assert _run(project, "unseal", "--yes") == 0
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
        code = _run(project, "verify")
        out = capsys.readouterr().out
    assert code == 0
    assert "toy\twork" in out


def test_repair_runs_scan_project_with_empty_registry(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # No members registered; the kind's project-scope scan must still run.
    with toy_kind_registered():
        code = _run(project, "repair")
    out = capsys.readouterr().out
    assert "toy:scan" in out
    assert code == 0
    # Default drives the scan with repairs on and adoption on.
    assert _toy_member.SCAN_CALLS == [(True, True)]


def test_repair_no_adopt_skips_adoption(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        code = _run(project, "repair", "--no-adopt")
    assert code == 0
    assert _toy_member.SCAN_CALLS == [(True, False)]
    assert _toy_member.REPAIR_CALLS == [("work", True)]


def test_check_mutates_nothing(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    (project / "work").mkdir()
    # Unnamed: httk-workflow's workspace scan, when installed, flags named non-workspace members.
    # An unpinned key is repairable, so a mutating run would pin it.
    metadata_path = project / "httk_project" / "project.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.pop("public_key", None)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with toy_kind_registered():
        register_project_member(project, "work", "toy")
        before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
        code = _run(project, "check", "--json")
        after = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
    assert code == 0
    assert before == after
    report = json.loads(capsys.readouterr().out)
    assert report["apply"] is False and report["repaired"] == 0
    # apply=False propagates to both the per-member repair and the kind scan, and nothing is adopted.
    assert _toy_member.REPAIR_CALLS == [("work", False)]
    assert _toy_member.SCAN_CALLS == [(False, True)]
    assert _toy_member.ADOPT_CALLS == []
    assert _run(project, "check", "--no-adopt") == 2
    assert _run(project, "repair", "--dry-run") == 2


class _AdoptOnlyHandler:
    """A member kind with an ``adopt`` hook but no project-scope scan."""

    def repair(self, member_root: Path, *, apply: bool) -> tuple[dict[str, object], ...]:
        return ()

    def adopt(self, member_root: Path, *, name: str | None) -> tuple[dict[str, object], ...]:
        return ToyMemberHandler().adopt(member_root, name=name)


def test_repair_adopts_scanless_kind_once_with_recorded_name(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    register_project_member_kind("adoptonly", _AdoptOnlyHandler)
    _toy_member.ADOPT_CALLS.clear()
    register_project_member(project, "work", "adoptonly", name="alpha")
    code = _run(project, "repair")
    out = capsys.readouterr().out
    assert code == 0
    assert _toy_member.ADOPT_CALLS == [("work", "alpha")]
    assert "toy:adopt:work" in out
    assert "alpha" in out


def test_repair_leaves_adoption_to_the_scan_when_a_kind_has_one(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "work").mkdir()
    with toy_kind_registered():
        register_project_member(project, "work", "toy", name="alpha")
        assert _run(project, "repair") == 0
        out = capsys.readouterr().out
    # The toy kind defines both hooks: only its scan adopts, the per-member hook never runs.
    assert _toy_member.ADOPT_CALLS == []
    assert _toy_member.SCAN_CALLS == [(True, True)]
    assert "toy:adopt:work" not in out


def test_repair_no_adopt_skips_adopt_hook(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "work").mkdir()
    with toy_kind_registered():
        # Unnamed: httk-workflow's workspace scan, when installed, flags named non-workspace members.
        register_project_member(project, "work", "toy")
        assert _run(project, "repair", "--no-adopt") == 0
    assert _toy_member.ADOPT_CALLS == []


def test_adopt_verb_is_gone(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "adopt") == 2
    assert "invalid choice: 'adopt'" in capsys.readouterr().err
