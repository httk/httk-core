import json
import os
import subprocess
from pathlib import Path
from typing import cast

import pytest

from httk.core.cli import CLIContext
from httk.core.docs import cli
from httk.core.docs.ecosystem import (
    EcosystemManifestError,
    build_ecosystem_manifest,
    verify_ecosystem_manifest,
    write_ecosystem_manifest,
)


def _git(path: Path, *arguments: str) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.test",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.test",
    }
    subprocess.run(["git", *arguments], cwd=path, env=environment, check=True, capture_output=True)


def _checkout(parent: Path, name: str, version: str | None, tag: str | None) -> Path:
    path = parent / name
    path.mkdir()
    _git(path, "init", "-q")
    if version is not None:
        (path / "pyproject.toml").write_text(f"[project]\nname = '{name}'\nversion = '{version}'\n", encoding="utf-8")
    (path / "README.md").write_text(name, encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "initial")
    if tag is not None:
        _git(path, "tag", tag)
    return path


def _superproject(tmp_path: Path, checkouts: list[Path]) -> Path:
    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    _git(root, "init", "-q")
    names = [checkout.name for checkout in checkouts]
    (root / ".gitmodules").write_text(
        "".join(
            f'[submodule "submodules/{name}"]\npath = submodules/{name}\nurl = https://example.test/{name}\n'
            for name in names
        ),
        encoding="utf-8",
    )
    _git(root, "add", ".gitmodules")
    for checkout in checkouts:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=checkout, check=True, capture_output=True, text=True
        ).stdout.strip()
        _git(root, "update-index", "--add", "--cacheinfo", f"160000,{commit},submodules/{checkout.name}")
    return root


def test_build_and_write_ecosystem_manifest(tmp_path: Path) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    tagged = _checkout(submodules, "tagged", "1.2.3", "v1.2.3")
    untagged = _checkout(submodules, "untagged", "2.0.0", None)
    root = _superproject(tmp_path, [tagged, untagged])
    assert root == submodules.parent

    manifest = build_ecosystem_manifest(submodules)
    assert manifest["schema_version"] == 1
    modules = cast(dict[str, dict[str, str | None]], manifest["modules"])
    assert list(modules) == ["tagged", "untagged"]
    assert modules["tagged"]["version"] == "v1.2.3"
    assert modules["untagged"]["version"] is None
    output = tmp_path / "ecosystem.json"
    write_ecosystem_manifest(manifest, output)
    assert json.loads(output.read_text(encoding="utf-8")) == manifest
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_require_release_tags_names_untagged_and_mismatched_modules(tmp_path: Path) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    untagged = _checkout(submodules, "untagged", "2.0.0", None)
    mismatched = _checkout(submodules, "mismatched", "3.0.0", "v4.0.0")
    _superproject(tmp_path, [untagged, mismatched])
    with pytest.raises(EcosystemManifestError, match="mismatched.*untagged|untagged.*mismatched"):
        build_ecosystem_manifest(submodules, require_release_tags=True)


def test_verify_detects_semantic_drift(tmp_path: Path) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    tagged = _checkout(submodules, "tagged", "1.2.3", "v1.2.3")
    _superproject(tmp_path, [tagged])
    output = tmp_path / "ecosystem.json"
    write_ecosystem_manifest(build_ecosystem_manifest(submodules), output)
    verify_ecosystem_manifest(submodules, output, require_release_tags=True)
    value = json.loads(output.read_text(encoding="utf-8"))
    value["modules"]["tagged"]["commit"] = "0" * 40
    output.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(EcosystemManifestError, match="drift"):
        verify_ecosystem_manifest(submodules, output)


def test_cli_writes_and_verifies_ecosystem_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    tagged = _checkout(submodules, "tagged", "1.2.3", "v1.2.3")
    _superproject(tmp_path, [tagged])
    output = tmp_path / "ecosystem.json"
    context = CLIContext("httk", tmp_path)
    assert cli.command(["ecosystem-manifest", "--submodules-dir", str(submodules), "--out", str(output)], context) == 0
    assert "wrote ecosystem manifest" in capsys.readouterr().out
    assert (
        cli.command(["ecosystem-manifest", "--submodules-dir", str(submodules), "--verify", str(output)], context) == 0
    )
    assert "is current" in capsys.readouterr().out


def test_discovery_rejects_missing_expected_checkout(tmp_path: Path) -> None:
    source = _checkout(tmp_path, "missing", "1.0.0", "v1.0.0")
    root = tmp_path / "site"
    root.mkdir()
    _git(root, "init", "-q")
    submodules = root / "submodules"
    submodules.mkdir()
    (root / ".gitmodules").write_text(
        '[submodule "submodules/missing"]\npath = submodules/missing\nurl = https://example.test/missing\n',
        encoding="utf-8",
    )
    _git(root, "add", ".gitmodules")
    commit = _git_output(source, "rev-parse", "HEAD")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{commit},submodules/missing")
    with pytest.raises(EcosystemManifestError, match="expected module checkout is missing"):
        build_ecosystem_manifest(submodules)


def _git_output(path: Path, *arguments: str) -> str:
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(
        ["git", *arguments], cwd=path, env=environment, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_discovery_rejects_unexpected_extra_directory(tmp_path: Path) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    expected = _checkout(submodules, "expected", "1.0.0", "v1.0.0")
    (submodules / "extra").mkdir()
    _superproject(tmp_path, [expected])
    with pytest.raises(EcosystemManifestError, match="unexpected checkout directories: extra"):
        build_ecosystem_manifest(submodules)


def test_discovery_rejects_non_gitlink_path(tmp_path: Path) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    expected = _checkout(submodules, "expected", "1.0.0", "v1.0.0")
    root = _superproject(tmp_path, [expected])
    blob = root / "blob"
    blob.write_text("not a gitlink", encoding="utf-8")
    blob_id = _git_output(root, "hash-object", "-w", str(blob))
    _git(root, "update-index", "--add", "--cacheinfo", f"100644,{blob_id},submodules/expected")
    with pytest.raises(EcosystemManifestError, match="submodule path is not a gitlink"):
        build_ecosystem_manifest(submodules)


def test_discovery_rejects_empty_expected_set(tmp_path: Path) -> None:
    root = tmp_path / "site"
    root.mkdir()
    _git(root, "init", "-q")
    submodules = root / "submodules"
    submodules.mkdir()
    (root / ".gitmodules").write_text("", encoding="utf-8")
    _git(root, "add", ".gitmodules")
    with pytest.raises(EcosystemManifestError, match="declares no submodules"):
        build_ecosystem_manifest(submodules)


def test_discovery_rejects_gitlink_head_mismatch(tmp_path: Path) -> None:
    submodules = tmp_path / "site" / "submodules"
    submodules.mkdir(parents=True)
    expected = _checkout(submodules, "expected", "1.0.0", "v1.0.0")
    _superproject(tmp_path, [expected])
    (expected / "later.txt").write_text("later", encoding="utf-8")
    _git(expected, "add", "later.txt")
    _git(expected, "commit", "-qm", "later")
    with pytest.raises(EcosystemManifestError, match="gitlink mismatch for expected"):
        build_ecosystem_manifest(submodules)


def test_write_refuses_symlink_destination(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    target = tmp_path / "target.json"
    target.write_text("keep", encoding="utf-8")
    output.symlink_to(target)
    with pytest.raises(EcosystemManifestError, match="refusing symlink manifest destination"):
        write_ecosystem_manifest({"schema_version": 1, "modules": {}}, output)
    assert target.read_text(encoding="utf-8") == "keep"
