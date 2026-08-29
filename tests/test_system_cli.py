"""Tests for the ``httk system`` command."""

import io
import sys
from pathlib import Path

import pytest

from httk.core.cli import main


def _homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    config = tmp_path / "config"
    data = tmp_path / "data"
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(config))
    monkeypatch.setenv("HTTK_DATA_HOME", str(data))
    return config, data


def _populate(*homes: Path) -> None:
    for home in homes:
        home.mkdir()
        (home / "state").write_text("state", encoding="utf-8")


def test_force_reset_removes_both_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, data = _homes(tmp_path, monkeypatch)
    _populate(config, data)

    assert main(["system", "reset", "--force"]) == 0
    assert not config.exists()
    assert not data.exists()


def test_non_tty_reset_refuses_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, data = _homes(tmp_path, monkeypatch)
    _populate(config, data)
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))

    assert main(["system", "reset"]) == 2
    assert config.is_dir()
    assert data.is_dir()


class _PromptStdin:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        return self.answer


@pytest.mark.parametrize(("answer", "status", "removed"), [("n\n", 1, False), ("y\n", 0, True)])
def test_prompt_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
    status: int,
    removed: bool,
) -> None:
    config, data = _homes(tmp_path, monkeypatch)
    _populate(config, data)
    monkeypatch.setattr(sys, "stdin", _PromptStdin(answer))

    assert main(["system", "reset"]) == status
    assert config.exists() is not removed
    assert data.exists() is not removed


def test_force_reset_allows_absent_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, data = _homes(tmp_path, monkeypatch)

    assert main(["system", "reset", "--force"]) == 0
    assert not config.exists()
    assert not data.exists()


@pytest.mark.parametrize("config_target", ["/", "home"])
def test_force_reset_refuses_root_or_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_target: str) -> None:
    config = Path(config_target) if config_target == "/" else tmp_path
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(config))
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    survivor = tmp_path / "survivor"
    survivor.write_text("keep", encoding="utf-8")

    assert main(["system", "reset", "--force"]) == 2
    assert survivor.read_text(encoding="utf-8") == "keep"
