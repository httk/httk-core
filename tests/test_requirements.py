"""Minimum-version ``requires`` in plugin and project-template manifests."""

import importlib.metadata
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from httk.core import CLIContext
from httk.core.git_sources import installed_git_members
from httk.core.plugins import install_plugin, parse_plugin_manifest, plugin_program, plugins_home
from httk.core.plugins.cli import command as plugin_command
from httk.core.project.templates import (
    install_template,
    instantiate_template,
    parse_template_manifest,
    resolve_template,
)
from httk.core.requirements import (
    Requirement,
    RequirementError,
    check_requirements,
    parse_requirements,
    unmet_requirements,
)

MISSING = "surely-not-installed-httk-dist"


@pytest.fixture(autouse=True)
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))


def _installed_as(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    monkeypatch.setattr(importlib.metadata, "version", lambda name: version)


def test_parse_normalizes_names_and_keeps_text() -> None:
    assert parse_requirements(["HTTK_Core >= 2.1", "a.b-_c>=0"], "where") == (
        Requirement("httk-core", (2, 1), "HTTK_Core>=2.1"),
        Requirement("a-b-c", (0,), "a.b-_c>=0"),
    )
    assert parse_requirements([], "where") == ()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not a list", "where must be an array of strings"),
        ([1], r"where\[0\] must be a string"),
        (["httk-core"], "must have the form NAME>=VERSION"),
        (["httk-core==2.1"], "must have the form NAME>=VERSION"),
        (["httk-core<=2,>=1"], "must have the form NAME>=VERSION"),
        (["httk-core[extra]>=2"], "must have the form NAME>=VERSION"),
        ([">=2"], "invalid distribution name ''"),
        (["-bad>=2"], "invalid distribution name '-bad'"),
        (["httk-core>=2.1rc1"], "must be a plain release"),
        (["httk-core>=2.*"], "must be a plain release"),
        (["httk-core>=2,<3"], "must be a plain release"),
        (["httk-core>="], "must be a plain release"),
        (["httk-core>=1", "HTTK.core>=2"], r"where\[1\] 'HTTK.core>=2' repeats distribution 'httk-core'"),
    ],
)
def test_parse_rejects(value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_requirements(value, "where")


@pytest.mark.parametrize(
    ("installed", "met"),
    [
        ("2.2.0", True),
        ("2.2", True),
        ("2.2.0.0", True),
        ("2.10", True),
        ("3", True),
        ("2.2.0.post1", True),
        ("2.2.0-1", True),
        ("2.2.0+g1234", True),
        ("2.2.0.post1.dev2", True),
        ("1!0.1", True),
        ("2.2.1rc1", True),
        ("2.1.9", False),
        ("2.2.0rc1", False),
        ("2.2.0a1", False),
        ("2.2.0.dev3", False),
        ("2.2.0rc1.post1", False),
    ],
)
def test_comparison(monkeypatch: pytest.MonkeyPatch, installed: str, met: bool) -> None:
    _installed_as(monkeypatch, installed)
    unmet = unmet_requirements(parse_requirements(["dist>=2.2.0"], "w"))
    assert unmet == (() if met else (f"dist>=2.2.0 (installed: {installed})",))


def test_unparseable_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    assert unmet_requirements(parse_requirements([f"{MISSING}>=1"], "w")) == (f"{MISSING}>=1 (not installed)",)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: None)  # dist-info without Version
    assert unmet_requirements(parse_requirements(["dist>=1"], "w")) == (
        "dist>=1 (installed version None is not a valid version)",
    )
    _installed_as(monkeypatch, "banana")
    assert unmet_requirements(parse_requirements(["dist>=1"], "w")) == (
        "dist>=1 (installed version 'banana' is not a valid version)",
    )


def test_check_real_distributions() -> None:
    check_requirements(parse_requirements(["httk_core>=2"], "w") + parse_requirements(["HTTK.Core>=0.0.1"], "w"), "x")
    with pytest.raises(
        RequirementError,
        match=rf"thing has unmet requirements: httk-core>=999 \(installed: .*\); {MISSING}>=1 \(not installed\)$",
    ):
        check_requirements(parse_requirements(["httk-core>=999", f"{MISSING}>=1"], "w"), "thing")


def _plugin(root: Path, requires: str, template_requires: str = "[]") -> Path:
    (root / "bin").mkdir(parents=True)
    (root / "httk_plugin.toml").write_text(
        f"[plugin]\nname = 'demo'\nrequires = {requires}\ntemplates = ['tpl']\n"
        "[plugin.programs.tool]\nfile = 'bin/tool'\n",
        encoding="utf-8",
    )
    tool = root / "bin/tool"
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)
    (root / "tpl").mkdir()
    (root / "tpl/httk_project_template.toml").write_text(
        f"[template]\nname = 'starter'\nrequires = {template_requires}\n", encoding="utf-8"
    )
    return root


def test_manifests_reject_bad_requires(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\[plugin\]\.requires must be an array"):
        parse_plugin_manifest(_plugin(tmp_path / "a", "'httk-core>=2'"))
    with pytest.raises(ValueError, match=r"\[template\]\.requires\[0\] must be a string"):
        parse_template_manifest(_plugin(tmp_path / "b", "[]", "[2]") / "tpl")


def test_plugin_install_refuses_unmet_and_places_nothing(tmp_path: Path) -> None:
    source = _plugin(tmp_path / "source", f"['httk-core>=2', '{MISSING}>=1']")
    with pytest.raises(
        RequirementError, match=rf"plugin 'demo' has unmet requirements: {MISSING}>=1 \(not installed\)"
    ):
        install_plugin(source)
    assert not plugins_home().exists() or list(plugins_home().iterdir()) == []


def test_plugin_use_rechecks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    install_plugin(_plugin(tmp_path / "source", "['httk-core>=2.0']", "['httk-core>=2.1']"))
    context = CLIContext(program="httk", cwd=tmp_path)
    assert plugin_command(["show", "--json", "demo"], context) == 0
    assert json.loads(capsys.readouterr().out)[0]["requires"] == ["httk-core>=2.0"]
    assert resolve_template("demo:starter").name == "starter"
    assert resolve_template("starter").name == "starter"
    assert plugin_command(["run", "demo", "tool"], context) == 0

    _installed_as(monkeypatch, "1.9")
    assert plugin_command(["run", "demo", "tool"], context) == 2
    assert "plugin 'demo' has unmet requirements: httk-core>=2.0 (installed: 1.9)" in capsys.readouterr().err
    with pytest.raises(RequirementError, match="plugin 'demo'"):
        plugin_program("demo", "tool")
    for selector in ("demo:starter", "starter"):
        with pytest.raises(RequirementError, match="plugin 'demo'"):
            resolve_template(selector)

    _installed_as(monkeypatch, "2.0")  # plugin met, template's own requires not
    with pytest.raises(RequirementError, match=r"template 'starter' has unmet requirements: httk-core>=2.1"):
        resolve_template("demo:starter")


def test_template_directory_and_instantiate_refuse(tmp_path: Path) -> None:
    root = _plugin(tmp_path / "source", "[]", f"['{MISSING}>=1']") / "tpl"
    template = parse_template_manifest(root)
    with pytest.raises(RequirementError, match="template 'starter'"):
        resolve_template(str(root))
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(RequirementError, match="template 'starter'"):
        instantiate_template(template, project, {}, project_info={})
    assert list(project.iterdir()) == []


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")
def test_template_install_refuses_unmet(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _plugin(repository, "[]", f"['{MISSING}>=1']")
    git = ["git", "-c", "user.name=T", "-c", "user.email=t@example.test"]
    subprocess.run([*git, "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run([*git, "add", "-A"], cwd=repository, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "one"], cwd=repository, check=True)
    with pytest.raises(RequirementError, match="template 'starter'"):
        install_template(f"git+file://{repository}#tpl")
    assert installed_git_members("templates") == ()
