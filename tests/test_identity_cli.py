"""The core-owned ``httk init`` and ``httk identity`` command-line wiring.

The library-level behaviour of operator identity — resolution order, literal
selectors, signing, seed handling, key permissions — lives in
``httk.core.identity`` and is covered by ``tests/test_operator_identity.py``.
What is covered here is only the command-line wiring: that ``httk init`` and
``httk identity add|list|default|remove`` drive the identity store in
``identity.json`` and report it the way operators depend on.
"""

import json
from pathlib import Path

import pytest

from httk.core.cli import CLIContext, main
from httk.core.identity import (
    identity_key_paths,
    read_identity_config,
    write_identity_config,
)
from httk.core.identity_cli import identity_command, init_command


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


def _context() -> CLIContext:
    return CLIContext("httk", Path.cwd())


def _identity(*arguments: str) -> int:
    return identity_command(list(arguments), _context())


def _init(*arguments: str) -> int:
    return init_command(list(arguments), _context())


def test_root_help_lists_init_and_identity() -> None:
    import httk.core  # noqa: F401  # trigger command discovery

    from httk.core.register import known_cli_commands

    assert "init" in known_cli_commands()
    assert "identity" in known_cli_commands()


def test_root_help_prints_the_summaries(capsys: pytest.CaptureFixture[str]) -> None:
    import httk.core  # noqa: F401

    assert main(["--help"]) == 0
    printed = capsys.readouterr().out
    assert "init" in printed and "identity" in printed
    assert "write the per-user configuration and identity key" in printed
    assert "manage named operator identities" in printed


def test_init_is_xdg_isolated_and_private_key_is_0600(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _init("--name", "A User", "--email", "a@example.test", "--non-interactive") == 0
    private, public = identity_key_paths()
    assert private.is_file() and public.is_file()
    assert private.stat().st_mode & 0o777 == 0o600
    stored = read_identity_config()
    assert stored["name"] == "A User" and stored["email"] == "a@example.test"


def test_init_updates_name_and_email_on_an_existing_identity() -> None:
    assert _init("--name", "First", "--email", "first@example.test", "--non-interactive") == 0
    seed_before = identity_key_paths()[0].read_bytes()
    assert _init("--name", "Second", "--email", "second@example.test", "--non-interactive") == 0
    stored = read_identity_config()
    assert stored["name"] == "Second" and stored["email"] == "second@example.test"
    # Idempotent on the key: the seed is kept, never regenerated.
    assert identity_key_paths()[0].read_bytes() == seed_before


def test_init_non_interactive_refuses_a_missing_value(capsys: pytest.CaptureFixture[str]) -> None:
    assert _init("--non-interactive") == 2
    assert "missing required value 'name'" in capsys.readouterr().err
    assert not identity_key_paths()[0].exists()


def test_identity_cli_round_trip_and_key_permissions(capsys: pytest.CaptureFixture[str]) -> None:
    assert _identity("add", "alice", "--name", "Alice", "--email", "alice@example.test") == 0
    first = json.loads(capsys.readouterr().out)
    assert first["default"]
    assert identity_key_paths("alice")[0].stat().st_mode & 0o777 == 0o600
    assert identity_key_paths("alice")[1].exists()

    assert _identity("add", "ci_bot", "--name", "CI", "--email", "ci@example.test", "--default") == 0
    capsys.readouterr()
    assert _identity("list", "--json") == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["short"] for item in listed] == ["alice", "ci_bot"]
    assert listed[1]["default"] and listed[1]["public_key"].startswith("ed25519:")
    stored = read_identity_config()
    configured = stored["identities"]
    assert stored["default_identity"] == "ci_bot"
    assert isinstance(configured, dict) and set(configured) == {"alice", "ci_bot"}

    assert _identity("default", "ci_bot") == 0
    capsys.readouterr()
    assert _identity("remove", "ci_bot") == 0
    output = capsys.readouterr().out
    assert "identity-ci_bot.seed" in output and identity_key_paths("ci_bot")[0].exists()
    assert read_identity_config()["default_identity"] == "alice"


def test_add_succeeds_without_default_in_existing_multi_identity_config(capsys: pytest.CaptureFixture[str]) -> None:
    write_identity_config(
        {
            "identities": {
                "alice": {"name": "Alice", "email": "alice@example.test"},
                "bob": {"name": "Bob", "email": "bob@example.test"},
            },
        }
    )
    assert _identity("add", "carol", "--name", "Carol", "--email", "carol@example.test") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["default"] is False
    values = read_identity_config()
    configured = values["identities"]
    assert isinstance(configured, dict)
    assert set(configured) == {"alice", "bob", "carol"}
    assert "default_identity" not in values


def test_dangling_default_is_loud_warned_and_cleared(capsys: pytest.CaptureFixture[str]) -> None:
    write_identity_config(
        {
            "identities": {"alice": {"name": "Alice", "email": "alice@example.test"}},
            "default_identity": "missing",
        }
    )
    assert _identity("list", "--json") == 0
    assert "is not a configured identity" in capsys.readouterr().err

    assert _identity("remove", "alice") == 0
    assert "default_identity" not in read_identity_config()


def test_identity_add_rejects_an_invalid_short(capsys: pytest.CaptureFixture[str]) -> None:
    assert _identity("add", "Not-valid", "--name", "N", "--email", "e@example.test") == 2
    assert "must match" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("name", "email"),
    (("Bad\nName", "bad@example.test"), ("Bad<Name", "bad@example.test"), ("Good", "bad"), ("Good", "bad > @x")),
)
def test_identity_add_rejects_unforwardable_labels(
    capsys: pytest.CaptureFixture[str], name: str, email: str
) -> None:
    assert _identity("add", "bad", "--name", name, "--email", email) == 2
    assert "identity" in capsys.readouterr().err
    assert not identity_key_paths("bad")[0].exists()


def test_init_reports_corrupt_identity_config_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    from httk.core.identity import identity_config_path

    path = identity_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"format": "not-httk-identity"}', encoding="utf-8")
    assert _init("--name", "A", "--email", "a@example.test", "--non-interactive") == 2
    assert "identity configuration is not" in capsys.readouterr().err


def test_identity_remove_is_best_effort(capsys: pytest.CaptureFixture[str]) -> None:
    assert _identity("add", "a", "--name", "A", "--email", "a@example.test") == 0
    assert _identity("add", "c", "--name", "C", "--email", "c@example.test") == 0
    capsys.readouterr()
    assert _identity("remove", "a", "bogus", "c") == 1
    captured = capsys.readouterr()
    assert "identity bogus:" in captured.err
    assert "removed a" in captured.out and "removed c" in captured.out
    assert not read_identity_config().get("identities")
