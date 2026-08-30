"""Tests for signed project redistribution exports."""

import base64
import json
import zipfile
from pathlib import Path

import pytest

from httk.core import CLIContext
from httk.core.crypto import ed25519_generate_seed, ed25519_public_key, ed25519_sign
from httk.core.project import (
    PROJECT_DIRECTORY,
    import_v1_project,
    initialize_project,
    export_project,
    verify_export,
)
from httk.core.project.cli import command


def _replace_members(source: Path, destination: Path, replacements: dict[str, bytes]) -> None:
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as changed:
        for info in original.infolist():
            changed.writestr(info, replacements.get(info.filename, original.read(info)))


def test_export_round_trip_excludes_private_key_and_is_reproducible(tmp_path: Path) -> None:
    project = tmp_path / "project"
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    initialize_project(project, name="exported")
    (project / "raw.txt").write_text("raw\n", encoding="utf-8")

    export_project(first, project)
    export_project(second, project)
    assert first.read_bytes() == second.read_bytes()
    report = verify_export(first)
    assert report["valid"] is True
    assert report["status"] == "self-consistent but UNAUTHENTICATED (trust-on-first-use)"
    with zipfile.ZipFile(first) as archive:
        assert "project/httk_project/keys/project.seed" not in archive.namelist()
        assert "project/httk_project/keys/project.pub" in archive.namelist()


def test_private_key_suffixes_v1_paths_and_content_copies_are_blocked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project, name="exported")
    seed = project / PROJECT_DIRECTORY / "keys" / "project.seed"

    (project / "UPPER.KEY").write_bytes(b"private")
    with pytest.raises(ValueError, match="private-key-like"):
        export_project(tmp_path / "uppercase.zip", project)
    (project / "UPPER.KEY").unlink()

    (project / "copy.priv").write_bytes(b"private")
    with pytest.raises(ValueError, match="private-key-like"):
        export_project(tmp_path / "priv.zip", project)
    (project / "copy.priv").unlink()

    decoded = base64.b64decode(seed.read_bytes())
    for name, content in (("decoded-copy", decoded), ("reencoded-copy", base64.b64encode(decoded))):
        (project / f"{name}.txt").write_bytes(content)
        with pytest.raises(ValueError, match="content matches"):
            export_project(tmp_path / f"{name}.zip", project)
        (project / f"{name}.txt").unlink()

    v1_private = project / "ht.project" / "keys" / "old.priv"
    v1_private.parent.mkdir(parents=True)
    v1_private.write_bytes(b"v1 private material")
    (project / "notes.txt").write_bytes(v1_private.read_bytes())
    with pytest.raises(ValueError, match="content matches"):
        export_project(tmp_path / "copied-v1-key.zip", project)

    assert "exact and re-encoded copies of known private material" in (export_project.__doc__ or "")
    assert "truncated secrets are outside" in (export_project.__doc__ or "")


def test_imported_v1_private_key_path_is_excluded(tmp_path: Path) -> None:
    project = tmp_path / "imported"
    legacy = project / "ht.project"
    (legacy / "keys").mkdir(parents=True)
    (legacy / "keys" / "old.priv").write_bytes(b"old private key")
    import_v1_project(project, source=legacy, name="imported")
    output = tmp_path / "imported.zip"
    export_project(output, project)
    with zipfile.ZipFile(output) as archive:
        assert "project/ht.project/keys/old.priv" not in archive.namelist()


def test_signature_must_match_pinned_key_and_expect_key_authenticates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    export = tmp_path / "export.zip"
    initialize_project(project, name="exported")
    export_project(export, project)
    fingerprint = verify_export(export)["fingerprint"]
    assert isinstance(fingerprint, str)
    assert verify_export(export, expect_key=fingerprint)["authenticated"] is True
    assert verify_export(export, trusted_keys=(fingerprint,))["authenticated"] is True
    with pytest.raises(ValueError, match="expected signer fingerprint"):
        verify_export(export, expect_key="sha256:" + "0" * 64)

    attacker_seed = ed25519_generate_seed()
    attacker_public = ed25519_public_key(attacker_seed)
    with zipfile.ZipFile(export) as archive:
        manifest = archive.read("export/manifest.json")
        attacker_signature = json.dumps(
            {
                "algorithm": "Ed25519",
                "public_key": "ed25519:" + base64.b64encode(attacker_public).decode("ascii"),
                "signature": base64.b64encode(ed25519_sign(attacker_seed, manifest)).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")
    changed = tmp_path / "attacker.zip"
    _replace_members(export, changed, {"export/signature": attacker_signature})
    with pytest.raises(ValueError, match="pinned project key"):
        verify_export(changed)


def test_cli_marks_untrusted_exports_as_unauthenticated(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "project"
    export = tmp_path / "export.zip"
    initialize_project(project, name="exported")
    export_project(export, project)
    assert command(["verify-export", str(export)], CLIContext("httk", tmp_path)) == 0
    assert "self-consistent but UNAUTHENTICATED (trust-on-first-use)" in capsys.readouterr().out


def test_export_tamper_and_output_alias_are_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    export = tmp_path / "export.zip"
    tampered = tmp_path / "tampered.zip"
    initialize_project(project, name="exported")
    (project / "raw.txt").write_text("raw\n", encoding="utf-8")
    export_project(export, project)
    _replace_members(export, tampered, {"project/raw.txt": b"tampered\n"})
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_export(tampered)
    with pytest.raises(ValueError, match="protected project data"):
        export_project(project / PROJECT_DIRECTORY / "keys" / "project.pub", project)


@pytest.mark.parametrize(
    ("builder", "message"),
    [
        (lambda path: path.write_bytes(b""), "invalid export ZIP"),
        (lambda path: path.write_bytes(b"PK\x03\x04"), "invalid export ZIP"),
    ],
)
def test_empty_and_truncated_exports_have_named_errors(tmp_path: Path, builder, message: str) -> None:
    path = tmp_path / "broken.zip"
    builder(path)
    with pytest.raises(ValueError, match=message):
        verify_export(path)


def test_missing_manifest_and_signature_are_distinct(tmp_path: Path) -> None:
    project = tmp_path / "project"
    export = tmp_path / "export.zip"
    initialize_project(project, name="exported")
    export_project(export, project)
    with zipfile.ZipFile(export) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    no_manifest = tmp_path / "no-manifest.zip"
    _replace_members(export, no_manifest, {})
    with zipfile.ZipFile(no_manifest, "w") as archive:
        for name, data in members.items():
            if name != "export/manifest.json":
                archive.writestr(name, data)
    with pytest.raises(ValueError, match="missing export manifest"):
        verify_export(no_manifest)

    no_signature = tmp_path / "no-signature.zip"
    with zipfile.ZipFile(no_signature, "w") as archive:
        for name, data in members.items():
            if name != "export/signature":
                archive.writestr(name, data)
    with pytest.raises(ValueError, match="missing export signature"):
        verify_export(no_signature)
