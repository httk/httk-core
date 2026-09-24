"""Project templates installed from git URIs: CLI, resolution and uninstall."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_project_init_template import _plugin

from httk.core import CLIContext
from httk.core.project import PROJECT_DIRECTORY, PROJECT_FILE
from httk.core.project.cli import command
from httk.core.project.templates import parse_template_manifest, resolve_template, uninstall_templates

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))


def _git(cwd: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(root: Path, name: str = "starter") -> tuple[str, str]:
    """Create a repository with one template in ``tpl``; return its base URI and commit."""

    template = root / "tpl"
    template.mkdir(parents=True)
    (template / "httk_project_template.toml").write_text(
        f"[template]\nname = '{name}'\ndescription = 'From git'\nfiles = ['README.md']\n", encoding="utf-8"
    )
    (template / "README.md").write_text("hello\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "one")
    return f"git+file://{root}", _git(root, "rev-parse", "HEAD")


def _context(root: Path) -> CLIContext:
    return CLIContext("httk", root)


def test_install_list_and_uninstall(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base, commit = _repository(tmp_path / "repo")
    uri = f"{base}@{commit}#tpl"
    assert command(["template", "install", f"{base}#tpl", f"{base}#missing"], _context(tmp_path)) == 1
    captured = capsys.readouterr()
    assert captured.out == f"Installed template 'starter' from {uri}\n"
    assert "#missing" in captured.err and "'missing' is not a directory" in captured.err

    assert command(["template", "install", "--json", f"{base}@main#tpl"], _context(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out) == [{"uri": uri, "name": "starter"}]
    assert command(["template", "list"], _context(tmp_path)) == 0
    assert capsys.readouterr().out == f"{uri}  From git\n"
    assert command(["template", "list", "--json"], _context(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"name": "starter", "description": "From git", "selector": uri, "source": {"kind": "git", "uri": uri}}
    ]
    assert resolve_template("starter").root.name == "tpl"

    assert command(["template", "uninstall", "starter", "starter"], _context(tmp_path)) == 1
    captured = capsys.readouterr()
    assert captured.out == f"Uninstalled template 'starter' {uri}\n"
    assert "no installed git templates match 'starter'" in captured.err
    assert command(["template", "list"], _context(tmp_path)) == 0
    assert capsys.readouterr().out == "no templates available\n"


def test_init_with_a_git_uri_installs_the_template(tmp_path: Path) -> None:
    base, commit = _repository(tmp_path / "repo")
    project = tmp_path / "project"
    assert command(["init", "--template", f"{base}#tpl", str(project)], _context(tmp_path)) == 0
    assert (project / PROJECT_DIRECTORY / PROJECT_FILE).is_file()
    assert (project / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert resolve_template("starter").name == "starter"
    assert command(["template", "uninstall", f"{base}@{commit}#tpl"], _context(tmp_path)) == 0


def test_bare_name_claimed_by_plugin_and_git_is_ambiguous(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base, commit = _repository(tmp_path / "repo")
    _plugin("alpha", "starter")
    _plugin("beta", "plugin-only")
    assert command(["template", "install", f"{base}#tpl"], _context(tmp_path)) == 0
    with pytest.raises(ValueError, match=re.escape(f"ambiguous; use one of: alpha:starter, {base}@{commit}#tpl")):
        resolve_template("starter")
    assert resolve_template("alpha:starter").name == "starter"
    assert resolve_template("plugin-only").name == "plugin-only"
    capsys.readouterr()
    assert command(["template", "list"], _context(tmp_path)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "alpha:starter  ",
        "beta:plugin-only  ",
        f"{base}@{commit}#tpl  From git",
    ]
    assert command(["template", "uninstall", "plugin-only", "beta:plugin-only"], _context(tmp_path)) == 1
    assert capsys.readouterr().err.count("provided by plugin beta; remove it with 'httk plugin uninstall'") == 2
    assert command(["template", "uninstall", "starter"], _context(tmp_path)) == 0  # the git one only
    assert resolve_template("starter").root.parent.name == "alpha"


def test_template_id_key_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "httk_project_template.toml").write_text("[template]\nid = 'old'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        parse_template_manifest(tmp_path)


def test_name_claimed_by_two_git_sources_and_a_plugin(tmp_path: Path) -> None:
    one, one_commit = _repository(tmp_path / "one")
    two, two_commit = _repository(tmp_path / "two")
    _plugin("alpha", "starter")
    assert command(["template", "install", f"{one}#tpl", f"{two}#tpl"], _context(tmp_path)) == 0
    one_uri, two_uri = f"{one}@{one_commit}#tpl", f"{two}@{two_commit}#tpl"
    with pytest.raises(ValueError, match=re.escape(f"ambiguous; use one of: alpha:starter, {one_uri}, {two_uri}")):
        resolve_template("starter")
    with pytest.raises(ValueError, match="several installed git templates.*by its URI"):
        uninstall_templates("starter")
    assert [member.uri for member in uninstall_templates(one_uri)] == [one_uri]
    with pytest.raises(ValueError, match=re.escape(f"use one of: alpha:starter, {two_uri}")):
        resolve_template("starter")
