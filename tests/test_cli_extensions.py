import argparse
from collections.abc import Iterator
from pathlib import Path

import pytest

from httk.core import CLIContext, cli_extensions, register_cli_extension
from httk.core.project.cli import command
from httk.core.register.cli import _cli_extensions


@pytest.fixture(autouse=True)
def _isolate_extensions() -> Iterator[None]:
    """Snapshot and restore the global extension registry per test."""

    saved = {command: list(providers) for command, providers in _cli_extensions.items()}
    try:
        yield
    finally:
        _cli_extensions.clear()
        _cli_extensions.update(saved)


def _frobnicate(arguments: argparse.Namespace, context: CLIContext) -> int:
    print("frobnicated")
    return 0


def _provider(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("frobnicate", help="a toy leaf", description="a toy leaf")
    parser.set_defaults(handler=_frobnicate, help_parser=parser)


@pytest.mark.parametrize("name", ["", "Bad", "-x", "with space"])
def test_invalid_command_names(name: str) -> None:
    with pytest.raises(ValueError):
        register_cli_extension(name, _provider)


def test_reserved_command_name() -> None:
    with pytest.raises(ValueError):
        register_cli_extension("help", _provider)


def test_non_callable_provider() -> None:
    with pytest.raises(TypeError):
        register_cli_extension("project", 42)  # type: ignore[arg-type]


def test_bad_lazy_reference() -> None:
    with pytest.raises(ValueError):
        register_cli_extension("project", "no-separator")


def test_duplicate_registration() -> None:
    register_cli_extension("dup-ext-test", _provider)
    with pytest.raises(ValueError):
        register_cli_extension("dup-ext-test", _provider)


def test_lazy_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "lazy_ext_test.py").write_text(
        "def provider(subparsers):\n    return None\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    register_cli_extension("lazy-ext-test", "lazy_ext_test:provider")
    (resolved,) = cli_extensions("lazy-ext-test")
    assert callable(resolved)
    import lazy_ext_test

    assert resolved is lazy_ext_test.provider


def test_registration_order() -> None:
    def second(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
        return None

    register_cli_extension("order-ext-test", _provider)
    register_cli_extension("order-ext-test", second)
    assert cli_extensions("order-ext-test") == (_provider, second)


def test_no_extensions_is_empty() -> None:
    assert cli_extensions("unregistered-ext-test") == ()


def test_end_to_end_leaf_runs_and_help_lists(capsys: pytest.CaptureFixture[str]) -> None:
    register_cli_extension("project", _provider)
    context = CLIContext("httk", Path.cwd())

    assert command(["frobnicate"], context) == 0
    assert capsys.readouterr().out.strip() == "frobnicated"

    assert command(["--help"], context) == 0
    assert "frobnicate" in capsys.readouterr().out
