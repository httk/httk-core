"""Test plugin manifests and the installed-plugin read API."""

import json
import logging
from pathlib import Path

import pytest

from httk.core.plugins import installed_plugins, plugin_program, plugin_root
from httk.core.plugins.manifest import PluginManifest, parse_plugin_manifest


def _manifest(root: Path, text: str) -> None:
    (root / "httk_plugin.toml").write_text(text, encoding="utf-8")


def _plugin(root: Path, name: str = "demo") -> None:
    _manifest(root, f"[plugin]\nname = '{name}'\n")


def test_minimal_manifest(tmp_path: Path) -> None:
    _plugin(tmp_path)
    result = parse_plugin_manifest(tmp_path)
    assert result == PluginManifest("demo", None, (), (), (), None, tmp_path)


def test_full_manifest_and_deferred_artifact(tmp_path: Path) -> None:
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "httk_project_template.toml").write_text("", encoding="utf-8")
    (tmp_path / "workflow").mkdir()
    (tmp_path / "workflow" / "httk_workflow.toml").write_text("", encoding="utf-8")
    _manifest(
        tmp_path,
        """[plugin]
name = "demo"
description = "A demo"
templates = ["template"]
workflows = ["workflow"]

[plugin.programs.tool]
file = "build/tool"
description = "Tool"

[plugin.build]
command = "make"
artifacts = ["build/*"]
""",
    )
    result = parse_plugin_manifest(tmp_path)
    assert result.templates == ("template",)
    assert result.workflows == ("workflow",)
    assert result.programs[0].file == "build/tool"


@pytest.mark.parametrize(
    "text",
    [
        "[plugin]\nname = 'Bad'\n",
        "[plugin]\nname = 'has space'\n",
        "[plugin]\nname = '-bad'\n",
        "[plugin]\nname = '..'\n",
        "[plugin]\nname = 'good'\n[plugin.programs.Bad]\nfile = 'tool'\n",
    ],
)
def test_name_rules(tmp_path: Path, text: str) -> None:
    _manifest(tmp_path, text)
    with pytest.raises(ValueError):
        parse_plugin_manifest(tmp_path)


@pytest.mark.parametrize("name", ["Bad", "has space", "-bad", ".."])
def test_program_name_rules(tmp_path: Path, name: str) -> None:
    _manifest(tmp_path, f"[plugin]\nname = 'demo'\n[plugin.programs.\"{name}\"]\nfile = 'tool'\n")
    with pytest.raises(ValueError):
        parse_plugin_manifest(tmp_path)


def test_unknown_keys_and_build_vocabulary(tmp_path: Path) -> None:
    _manifest(tmp_path, "[plugin]\nname = 'demo'\nextra = true\n")
    with pytest.raises(ValueError, match=r"unknown key \[plugin\.extra\]"):
        parse_plugin_manifest(tmp_path)
    _manifest(tmp_path, "[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = 'tool'\nextra = true\n")
    with pytest.raises(ValueError, match=r"unknown key \[plugin\.programs\.tool\.extra\]"):
        parse_plugin_manifest(tmp_path)
    _manifest(tmp_path, "[plugin]\nname = 'demo'\n[plugin.build]\ncommand = 'make'\nunknown = true\n")
    with pytest.raises(ValueError, match=r"\[plugin\.build\."):
        parse_plugin_manifest(tmp_path)


@pytest.mark.parametrize("kind", ["templates", "workflows"])
def test_member_directory_requires_marker(tmp_path: Path, kind: str) -> None:
    (tmp_path / "member").mkdir()
    _manifest(tmp_path, f"[plugin]\nname = 'demo'\n{kind} = ['member']\n")
    with pytest.raises(ValueError, match="must contain regular file"):
        parse_plugin_manifest(tmp_path)


def test_directory_duplicates_and_overlap(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "httk_project_template.toml").write_text("", encoding="utf-8")
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "httk_workflow.toml").write_text("", encoding="utf-8")
    _manifest(tmp_path, "[plugin]\nname = 'demo'\ntemplates = ['a', 'a']\n")
    with pytest.raises(ValueError):
        parse_plugin_manifest(tmp_path)
    _manifest(tmp_path, "[plugin]\nname = 'demo'\ntemplates = ['a']\nworkflows = ['a/b']\n")
    with pytest.raises(ValueError):
        parse_plugin_manifest(tmp_path)


@pytest.mark.parametrize("file", ["../tool", "/tmp/tool", "link"])
def test_program_path_guards(tmp_path: Path, file: str) -> None:
    outside = tmp_path.parent / "tool"
    outside.write_text("", encoding="utf-8")
    (tmp_path / "link").symlink_to(outside)
    _manifest(tmp_path, f"[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = '{file}'\n")
    with pytest.raises(ValueError):
        parse_plugin_manifest(tmp_path)


def test_program_file_existence_rules(tmp_path: Path) -> None:
    _manifest(tmp_path, "[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = 'tool'\n")
    with pytest.raises(ValueError, match="does not exist"):
        parse_plugin_manifest(tmp_path)
    _manifest(
        tmp_path,
        "[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = 'tool'\n"
        "[plugin.build]\ncommand = 'make'\nartifacts = ['tool']\n",
    )
    assert parse_plugin_manifest(tmp_path).programs[0].file == "tool"
    _manifest(
        tmp_path,
        "[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = 'tool'\n"
        "[plugin.build]\ncommand = 'make'\nartifacts = ['other']\n",
    )
    with pytest.raises(ValueError, match="does not exist"):
        parse_plugin_manifest(tmp_path)


def _installed(root: Path, name: str, *, built: bool = True, malformed: bool = False) -> None:
    plugin = root / "plugins" / name
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({"built": built}), encoding="utf-8")
    if malformed:
        _manifest(plugin, "[plugin]\nname = 'bad'\n[broken\n")
        return
    (plugin / "tool").write_text("#!/bin/sh\n", encoding="utf-8")
    _manifest(plugin, "[plugin]\nname = '" + name + "'\n[plugin.programs.tool]\nfile = 'tool'\n")


def test_installed_plugins_skip_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path))
    _installed(tmp_path, "alpha")
    _installed(tmp_path, "zeta")
    _installed(tmp_path, "broken", malformed=True)
    with caplog.at_level(logging.WARNING):
        result = installed_plugins()
    assert [plugin.name for plugin in result] == ["alpha", "zeta"]
    assert "broken" in caplog.text


def test_plugin_root_and_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path))
    _installed(tmp_path, "demo")
    assert plugin_root("demo") == tmp_path / "plugins" / "demo"
    assert plugin_program("demo", "tool") == (tmp_path / "plugins" / "demo" / "tool").resolve()
    with pytest.raises(ValueError, match="not installed"):
        plugin_root("missing")
    with pytest.raises(ValueError, match="does not declare program"):
        plugin_program("demo", "missing")


def test_plugin_program_not_built_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path))
    _installed(tmp_path, "demo", built=False)
    with pytest.raises(ValueError, match=r"run: httk plugin build demo$"):
        plugin_program("demo", "tool")
