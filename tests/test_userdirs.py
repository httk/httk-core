"""Tests for per-user httk directories."""

from pathlib import Path

from httk.core.userdirs import config_home, data_home


def test_httk_overrides_win_and_expanduser(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("HTTK_CONFIG_HOME", "~/config")
    monkeypatch.setenv("HTTK_DATA_HOME", "~/data")

    assert config_home() == (home / "config").resolve()
    assert data_home() == (home / "data").resolve()


def test_xdg_homes_are_respected(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    monkeypatch.delenv("HTTK_CONFIG_HOME", raising=False)
    monkeypatch.delenv("HTTK_DATA_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))

    assert config_home() == (config / "httk").resolve()
    assert data_home() == (data / "httk").resolve()


def test_defaults_use_home(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    for name in ("HTTK_CONFIG_HOME", "HTTK_DATA_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)

    assert config_home() == (home / ".config" / "httk").resolve()
    assert data_home() == (home / ".local" / "share" / "httk").resolve()
