"""Tests for signed project redistribution seals."""

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
    seal_project,
    verify_seal,
)
from httk.core.project.cli import command


def _replace_members(source: Path, destination: Path, replacements: dict[str, bytes]) -> None:
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as changed:
        for info in original.infolist():
            changed.writestr(info, replacements.get(info.filename, original.read(info)))


def test_seal_round_trip_excludes_private_key_and_is_reproducible(tmp_path: Path) -> None:
    project = tmp_path / "project"
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    initialize_project(project, name="sealed")
    (project / "raw.txt").write_text("raw\n", encoding="utf-8")

    seal_project(first, project)
    seal_project(second, project)
    assert first.read_bytes() == second.read_bytes()
    report = verify_seal(first)
    assert report["valid"] is True
    assert report["status"] == "self-consistent but UNAUTHENTICATED (trust-on-first-use)"
    with zipfile.ZipFile(first) as archive:
        assert "project/httk_project/keys/project.seed" not in archive.namelist()
        assert "project/httk_project/keys/project.pub" in archive.namelist()


def test_private_key_suffixes_v1_paths_and_content_copies_are_blocked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project, name="sealed")
    seed = project / PROJECT_DIRECTORY / "keys" / "project.seed"

    (project / "UPPER.KEY").write_bytes(b"private")
    with pytest.raises(ValueError, match="private-key-like"):
        seal_project(tmp_path / "uppercase.zip", project)
    (project / "UPPER.KEY").unlink()

    (project / "copy.priv").write_bytes(b"private")
    with pytest.raises(ValueError, match="private-key-like"):
        seal_project(tmp_path / "priv.zip", project)
    (project / "copy.priv").unlink()

    decoded = base64.b64decode(seed.read_bytes())
    for name, content in (("decoded-copy", decoded), ("reencoded-copy", base64.b64encode(decoded))):
        (project / f"{name}.txt").write_bytes(content)
        with pytest.raises(ValueError, match="content matches"):
            seal_project(tmp_path / f"{name}.zip", project)
        (project / f"{name}.txt").unlink()

    v1_private = project / "ht.project" / "keys" / "old.priv"
    v1_private.parent.mkdir(parents=True)
    v1_private.write_bytes(b"v1 private material")
    (project / "notes.txt").write_bytes(v1_private.read_bytes())
    with pytest.raises(ValueError, match="content matches"):
        seal_project(tmp_path / "copied-v1-key.zip", project)

    assert "exact and re-encoded copies of known private material" in (seal_project.__doc__ or "")
    assert "truncated secrets are outside" in (seal_project.__doc__ or "")


def test_imported_v1_private_key_path_is_excluded(tmp_path: Path) -> None:
    project = tmp_path / "imported"
    legacy = project / "ht.project"
    (legacy / "keys").mkdir(parents=True)
    (legacy / "keys" / "old.priv").write_bytes(b"old private key")
    import_v1_project(project, source=legacy, name="imported")
    output = tmp_path / "imported.zip"
    seal_project(output, project)
    with zipfile.ZipFile(output) as archive:
        assert "project/ht.project/keys/old.priv" not in archive.namelist()


def test_signature_must_match_pinned_key_and_expect_key_authenticates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    seal = tmp_path / "seal.zip"
    initialize_project(project, name="sealed")
    seal_project(seal, project)
    fingerprint = verify_seal(seal)["fingerprint"]
    assert isinstance(fingerprint, str)
    assert verify_seal(seal, expect_key=fingerprint)["authenticated"] is True
    assert verify_seal(seal, trusted_keys=(fingerprint,))["authenticated"] is True
    with pytest.raises(ValueError, match="expected signer fingerprint"):
        verify_seal(seal, expect_key="sha256:" + "0" * 64)

    attacker_seed = ed25519_generate_seed()
    attacker_public = ed25519_public_key(attacker_seed)
    with zipfile.ZipFile(seal) as archive:
        manifest = archive.read("seal/manifest.json")
        attacker_signature = json.dumps(
            {
                "algorithm": "Ed25519",
                "public_key": "ed25519:" + base64.b64encode(attacker_public).decode("ascii"),
                "signature": base64.b64encode(ed25519_sign(attacker_seed, manifest)).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")
    changed = tmp_path / "attacker.zip"
    _replace_members(seal, changed, {"seal/signature": attacker_signature})
    with pytest.raises(ValueError, match="pinned project key"):
        verify_seal(changed)


def test_cli_marks_untrusted_seals_as_unauthenticated(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "project"
    seal = tmp_path / "seal.zip"
    initialize_project(project, name="sealed")
    seal_project(seal, project)
    assert command(["verify-seal", str(seal)], CLIContext("httk", tmp_path)) == 0
    assert "self-consistent but UNAUTHENTICATED (trust-on-first-use)" in capsys.readouterr().out


def test_seal_tamper_and_output_alias_are_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    seal = tmp_path / "seal.zip"
    tampered = tmp_path / "tampered.zip"
    initialize_project(project, name="sealed")
    (project / "raw.txt").write_text("raw\n", encoding="utf-8")
    seal_project(seal, project)
    _replace_members(seal, tampered, {"project/raw.txt": b"tampered\n"})
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_seal(tampered)
    with pytest.raises(ValueError, match="protected project data"):
        seal_project(project / PROJECT_DIRECTORY / "keys" / "project.pub", project)


@pytest.mark.parametrize(
    ("builder", "message"),
    [
        (lambda path: path.write_bytes(b""), "invalid seal ZIP"),
        (lambda path: path.write_bytes(b"PK\x03\x04"), "invalid seal ZIP"),
    ],
)
def test_empty_and_truncated_seals_have_named_errors(tmp_path: Path, builder, message: str) -> None:
    path = tmp_path / "broken.zip"
    builder(path)
    with pytest.raises(ValueError, match=message):
        verify_seal(path)


def test_missing_manifest_and_signature_are_distinct(tmp_path: Path) -> None:
    project = tmp_path / "project"
    seal = tmp_path / "seal.zip"
    initialize_project(project, name="sealed")
    seal_project(seal, project)
    with zipfile.ZipFile(seal) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    no_manifest = tmp_path / "no-manifest.zip"
    _replace_members(seal, no_manifest, {})
    with zipfile.ZipFile(no_manifest, "w") as archive:
        for name, data in members.items():
            if name != "seal/manifest.json":
                archive.writestr(name, data)
    with pytest.raises(ValueError, match="missing seal manifest"):
        verify_seal(no_manifest)

    no_signature = tmp_path / "no-signature.zip"
    with zipfile.ZipFile(no_signature, "w") as archive:
        for name, data in members.items():
            if name != "seal/signature":
                archive.writestr(name, data)
    with pytest.raises(ValueError, match="missing seal signature"):
        verify_seal(no_signature)
