"""The project anchor and the core-owned ``httk project`` command.

These cover the anchor moved into *httk-core*: creating one, discovering it by
walking upward, validating ``project.json``, the key helpers, pinning and trust,
the legacy import, and the built-in command line.
"""

import base64
import json
import stat
from pathlib import Path

import pytest

from httk.core import CLIContext
from httk.core.cli import main
from httk.core.crypto import ed25519_generate_seed, ed25519_public_key
from httk.core.project import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
    LegacyProjectError,
    canonical_public_key,
    discover_project,
    format_public_key,
    import_v1_project,
    initialize_project,
    key_fingerprint,
    parse_public_key,
    pin_project_key,
    pinned_project_key,
    project_public_key_path,
    read_project,
    read_public_key_file,
    require_project,
    trust_project_key,
    trusted_project_keys,
)
from httk.core.project.cli import command


def _write_project(project: Path, metadata: dict[str, object]) -> None:
    (project / PROJECT_DIRECTORY / PROJECT_FILE).write_text(json.dumps(metadata), encoding="utf-8")


# ---------------------------------------------------------------------------
# The anchor
# ---------------------------------------------------------------------------


def test_initialize_creates_only_the_anchor(tmp_path: Path) -> None:
    project = tmp_path / "campaign"
    metadata = initialize_project(project, name="campaign", description="a run")

    control = project / PROJECT_DIRECTORY
    assert (control / PROJECT_FILE).is_file()
    assert (control / "keys" / "project.pub").is_file()
    assert (control / "remotes").is_dir()
    # The anchor and nothing above it: a core installation makes no workspace.
    assert not (project / ".httk-workspace").exists()

    seed = control / "keys" / "project.seed"
    assert stat.S_IMODE(seed.stat().st_mode) == 0o600

    assert metadata["format"] == "httk-project" and metadata["format_version"] == 2
    assert metadata["name"] == "campaign" and metadata["description"] == "a run"
    assert str(metadata["public_key"]).startswith("ed25519:")
    assert metadata["trusted_keys"] == []
    assert read_project(project) == metadata


def test_initialize_refuses_an_existing_anchor(tmp_path: Path) -> None:
    initialize_project(tmp_path, name="one")
    with pytest.raises(FileExistsError):
        initialize_project(tmp_path, name="again")


def test_initialize_refuses_legacy_project_directories(tmp_path: Path) -> None:
    v1 = tmp_path / "v1"
    (v1 / "ht.project").mkdir(parents=True)
    with pytest.raises(LegacyProjectError, match="httk project import-v1"):
        initialize_project(v1, name="v1")
    assert not (v1 / PROJECT_DIRECTORY).exists()


def test_discover_walks_upward_and_require_refuses_when_absent(tmp_path: Path) -> None:
    project = tmp_path / "root"
    initialize_project(project, name="root")
    nested = project / "a" / "b" / "c"
    nested.mkdir(parents=True)

    assert discover_project(nested) == project.resolve()
    assert discover_project(project / PROJECT_DIRECTORY / PROJECT_FILE) == project.resolve()
    assert require_project(nested) == project.resolve()

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert discover_project(outside) is None
    with pytest.raises(ValueError, match="no httk project"):
        require_project(outside)


def test_read_project_validates_the_format(tmp_path: Path) -> None:
    initialize_project(tmp_path, name="p")
    _write_project(tmp_path, {"format": "something-else", "format_version": 1})
    with pytest.raises(ValueError, match="unsupported httk project format"):
        read_project(tmp_path)
    _write_project(tmp_path, {"format": "httk-project", "format_version": 1})
    with pytest.raises(ValueError, match="unsupported httk project format"):
        read_project(tmp_path)


def test_key_helpers_round_trip(tmp_path: Path) -> None:
    raw = ed25519_public_key(ed25519_generate_seed())
    recorded = format_public_key(raw)
    assert recorded.startswith("ed25519:")
    assert parse_public_key(recorded) == raw
    # The bare base64 spelling is accepted and canonicalized.
    bare = base64.b64encode(raw).decode("ascii")
    assert canonical_public_key(bare) == recorded
    assert key_fingerprint(recorded).startswith("sha256:")
    with pytest.raises(ValueError, match="unsupported public key algorithm"):
        parse_public_key("rsa:AAAA")

    pub = tmp_path / "k.pub"
    pub.write_text(bare + "\n", encoding="ascii")
    assert read_public_key_file(pub) == recorded


def test_pin_and_trust_round_trip(tmp_path: Path) -> None:
    initialize_project(tmp_path, name="p")
    # A project made before pinning existed has no public_key; re-pinning adopts
    # exactly the key that is in the tree right now.
    metadata = read_project(tmp_path)
    own = metadata["public_key"]
    del metadata["public_key"]
    _write_project(tmp_path, metadata)
    assert pinned_project_key(read_project(tmp_path)) is None

    pinned = pin_project_key(tmp_path)
    assert pinned["public_key"] == own
    assert pinned_project_key(read_project(tmp_path)) == own
    assert read_public_key_file(project_public_key_path(tmp_path)) == own

    collaborator = format_public_key(ed25519_public_key(ed25519_generate_seed()))
    trust_project_key(tmp_path, collaborator)
    assert set(trusted_project_keys(read_project(tmp_path))) == {own, collaborator}
    # Adopting the same key twice records it once.
    trust_project_key(tmp_path, collaborator)
    assert read_project(tmp_path)["trusted_keys"] == [collaborator]


def test_import_v1_creates_the_anchor_and_adopts_legacy_keys(tmp_path: Path) -> None:
    project = tmp_path / "legacy"
    legacy = project / "ht.project"
    (legacy / "keys").mkdir(parents=True)
    seed = ed25519_generate_seed()
    recorded = format_public_key(ed25519_public_key(seed))
    (legacy / "keys" / "old.pub").write_text(
        base64.b64encode(ed25519_public_key(seed)).decode("ascii") + "\n",
        encoding="ascii",
    )
    (legacy / "config").write_text("[main]\nproject_name = legacy\n", encoding="utf-8")

    with pytest.raises(LegacyProjectError, match="httk project import-v1"):
        discover_project(project)
    with pytest.raises(LegacyProjectError, match="httk project import-v1"):
        require_project(project)

    metadata = import_v1_project(project)
    assert metadata["name"] == "legacy"
    assert metadata["imported_from"] == str(legacy.resolve())
    assert metadata["trusted_keys"] == [recorded]
    assert metadata["legacy_queue_imported"] is False
    # The anchor import makes no workspace either.
    assert not (project / ".httk-workspace").exists()
    assert (project / PROJECT_DIRECTORY / "keys" / "legacy-public" / "old.pub").is_file()


# ---------------------------------------------------------------------------
# The umbrella command line
# ---------------------------------------------------------------------------


def test_cli_init_and_show(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["project", "init", "--name", "demo", "--description", "hi", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "Initialized httk project" in printed and "demo" in printed
    assert (tmp_path / PROJECT_DIRECTORY / PROJECT_FILE).is_file()

    # Mirrors `git init`: refuses an existing project rather than reinitializing.
    assert main(["project", "init", "--name", "demo", str(tmp_path)]) == 1
    assert "already an httk project" in capsys.readouterr().err

    assert main(["project", "show"]) == 0
    rendered = capsys.readouterr().out
    assert "demo" in rendered and "key_pinned" in rendered and "yes" in rendered

    assert main(["project", "show", "--json"]) == 0
    description = json.loads(capsys.readouterr().out)
    assert description[0]["format"] == "httk-project-description"
    assert description[0]["project"]["name"] == "demo"
    assert description[0]["keys"]["pinned"] is True
    assert description[0]["keys"]["public_key"]["fingerprint"].startswith("sha256:")


def test_cli_init_defaults_the_name_to_the_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "named-dir"
    target.mkdir()
    monkeypatch.chdir(target)
    assert main(["project", "init", str(target)]) == 0
    capsys.readouterr()
    assert read_project(target)["name"] == "named-dir"


def test_cli_show_refuses_v1_and_import_v1_creates_anchor(tmp_path: Path, monkeypatch, capsys) -> None:
    legacy = tmp_path / "ht.project"
    (legacy / "keys").mkdir(parents=True)
    (legacy / "config").write_text("[main]\nproject_name = imported\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["project", "init", str(tmp_path)]) == 1
    assert "httk project import-v1" in capsys.readouterr().err

    assert main(["project", "show"]) == 1
    assert "httk project import-v1" in capsys.readouterr().err

    assert main(["project", "import-v1", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert f"imported {legacy.resolve()} -> {tmp_path / PROJECT_DIRECTORY}" in output
    assert read_project(tmp_path)["name"] == "imported"
    assert (tmp_path / PROJECT_DIRECTORY / PROJECT_FILE).is_file()


def test_cli_show_path_error_does_not_abort_later_projects(tmp_path: Path, capsys) -> None:
    project = tmp_path / "valid"
    initialize_project(project, name="valid")
    assert command(["show", "~__httk_missing_user__", str(project)], CLIContext("httk", tmp_path)) == 1
    assert f"=== {project} ===" in capsys.readouterr().out


def test_bare_project_command_prints_help(tmp_path) -> None:
    context = CLIContext("httk", tmp_path)
    assert command([], context) == 0


def test_legacy_error_carries_root(tmp_path: Path) -> None:
    (tmp_path / "ht.project").mkdir()
    with pytest.raises(LegacyProjectError) as error:
        discover_project(tmp_path)
    assert error.value.root == tmp_path


def test_initialize_project_has_no_legacy_bypass_parameter() -> None:
    import inspect

    assert "_allow_legacy_v1" not in inspect.signature(initialize_project).parameters
