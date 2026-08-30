from pathlib import Path

import pytest

from httk.core import CLIContext, register_cli_command
from httk.core.cli import main
from httk.core.register import known_cli_commands


def test_lazy_registration_help_and_dispatch(tmp_path: Path, monkeypatch, capsys) -> None:
    module = tmp_path / "lazy_cli_test.py"
    imported = tmp_path / "imported"
    module.write_text(
        f"""from pathlib import Path
Path({str(imported)!r}).touch()
def command(argv, context):
    print(context.program, context.cwd, ",".join(argv))
    return 7
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    register_cli_command("lazy-cli-test", "lazy_cli_test:command", "a lazy test command")
    assert "lazy-cli-test" in known_cli_commands()
    assert main(["--help"]) == 0
    assert "a lazy test command" in capsys.readouterr().out
    assert not imported.exists()
    assert main(["lazy-cli-test", "one", "two"]) == 7
    assert imported.exists()
    assert "one,two" in capsys.readouterr().out


def test_core_registers_plugin_command() -> None:
    from httk import core

    assert core is not None
    assert "plugin" in known_cli_commands()


def test_chdir_is_exposed_in_context(tmp_path: Path) -> None:
    observed: list[CLIContext] = []

    def handler(argv, context):
        observed.append(context)
        return 0

    register_cli_command("context-cli-test", handler, "context test")
    previous = Path.cwd()
    try:
        assert main(["-C", str(tmp_path), "context-cli-test"]) == 0
    finally:
        # The root CLI intentionally retains -C for the process invocation.
        import os

        os.chdir(previous)
    assert observed == [CLIContext(program="httk", cwd=tmp_path.resolve())]


@pytest.mark.parametrize("name", ["Help", "two_words", "-bad", "bad-", "bad--name"])
def test_invalid_command_names(name: str) -> None:
    with pytest.raises(ValueError):
        register_cli_command(name, lambda argv, context: 0, "invalid")


def test_duplicate_and_reserved_registration() -> None:
    register_cli_command("duplicate-cli-test", lambda argv, context: 0, "first")
    with pytest.raises(ValueError, match="already registered"):
        register_cli_command("duplicate-cli-test", lambda argv, context: 0, "second")
    with pytest.raises(ValueError, match="reserved"):
        register_cli_command("help", lambda argv, context: 0, "reserved")


def test_unknown_command(capsys) -> None:
    assert main(["definitely-unknown"]) == 2
    assert "unknown command" in capsys.readouterr().err


def _register_help_probe(tmp_path: Path, monkeypatch, name: str) -> str:
    module = tmp_path / "help_probe_cli.py"
    module.write_text(
        """def command(argv, context):
    print(",".join(argv))
    return 0
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    register_cli_command(name, "help_probe_cli:command", "help probe command")
    return name


def test_trailing_help_rewritten(tmp_path: Path, monkeypatch, capsys) -> None:
    name = _register_help_probe(tmp_path, monkeypatch, "x-help-test-1")
    assert main([name, "a", "b", "help"]) == 0
    assert capsys.readouterr().out.strip() == "a,b,--help"


def test_help_drops_following_tokens(tmp_path: Path, monkeypatch, capsys) -> None:
    name = _register_help_probe(tmp_path, monkeypatch, "x-help-test-2")
    assert main([name, "a", "help", "ignored"]) == 0
    assert capsys.readouterr().out.strip() == "a,--help"


def test_help_after_option_not_rewritten(tmp_path: Path, monkeypatch, capsys) -> None:
    name = _register_help_probe(tmp_path, monkeypatch, "x-help-test-3")
    assert main([name, "--opt", "help"]) == 0
    assert capsys.readouterr().out.strip() == "--opt,help"


def test_root_help_command_appends_help(tmp_path: Path, monkeypatch, capsys) -> None:
    name = _register_help_probe(tmp_path, monkeypatch, "x-help-test-4")
    assert main(["help", name, "a"]) == 0
    assert capsys.readouterr().out.strip() == "a,--help"


def test_root_help_command_with_trailing_help(tmp_path: Path, monkeypatch, capsys) -> None:
    name = _register_help_probe(tmp_path, monkeypatch, "x-help-test-5")
    assert main(["help", name, "a", "help"]) == 0
    assert capsys.readouterr().out.strip() == "a,--help"


def test_bare_help_and_unknown(capsys) -> None:
    assert main(["help"]) == 0
    assert "usage:" in capsys.readouterr().out
    assert main(["help", "no-such-cmd"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_convert_help_end_to_end(capsys) -> None:
    assert main(["convert", "help"]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "INPUT" in out


def test_project_help_lists_subcommands(capsys) -> None:
    assert main(["project", "help"]) == 0
    assert "init" in capsys.readouterr().out
