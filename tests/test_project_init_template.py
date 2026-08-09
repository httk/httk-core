"""Test project initialization from static and installed templates."""

import json
from pathlib import Path

import pytest

from httk.core import CLIContext
from httk.core.plugins import plugins_home
from httk.core.project import PROJECT_DIRECTORY, PROJECT_FILE, read_project
from httk.core.project.cli import command


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))


def _context(root: Path) -> CLIContext:
    return CLIContext("httk", root)


def _template(root: Path, manifest: str, *, files: dict[str, str] | None = None) -> Path:
    """Create one template directory for a CLI test."""

    root.mkdir(parents=True)
    (root / "httk_project_template.toml").write_text(manifest, encoding="utf-8")
    for name, content in (files or {}).items():
        member = root / name
        member.parent.mkdir(parents=True, exist_ok=True)
        member.write_text(content, encoding="utf-8")
    return root


def _plugin(name: str, template_id: str, description: str = "") -> Path:
    """Create an installed-plugin directory containing one template."""

    root = plugins_home() / name
    template = root / "template"
    template.mkdir(parents=True)
    (template / "httk_project_template.toml").write_text(
        f"[template]\nid = '{template_id}'\ndescription = '{description}'\n",
        encoding="utf-8",
    )
    (root / "plugin.json").write_text('{"built": true}', encoding="utf-8")
    (root / "httk_plugin.toml").write_text(
        f"[plugin]\nname = '{name}'\ntemplates = ['template']\n",
        encoding="utf-8",
    )
    return template


def test_init_with_explicit_static_template(tmp_path: Path, capsys) -> None:
    source = _template(
        tmp_path / "template",
        "[template]\nid = 'starter'\nfiles = ['README.md']\n",
        files={"README.md": "hello\n"},
    )
    target = tmp_path / "project"

    assert command(["init", str(target), "--template", str(source)], _context(tmp_path)) == 0
    assert (target / PROJECT_DIRECTORY / PROJECT_FILE).is_file()
    assert (target / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert "Initialized httk project" in capsys.readouterr().out


def test_plugin_selectors_ambiguity_and_list(tmp_path: Path, capsys) -> None:
    _plugin("alpha", "unique", "A unique template")
    _plugin("one", "same")
    _plugin("two", "same")

    assert command(["init", "--list-templates"], _context(tmp_path)) == 0
    output = capsys.readouterr().out
    assert "alpha:unique  A unique template" in output
    assert "one:same  " in output and "two:same  " in output
    assert output.endswith("templates can also be given as a directory path\n")

    qualified = tmp_path / "qualified"
    assert command(["init", str(qualified), "--template", "alpha:unique"], _context(tmp_path)) == 0
    assert (qualified / PROJECT_FILE).exists() is False
    assert (qualified / PROJECT_DIRECTORY / PROJECT_FILE).is_file()

    bare = tmp_path / "bare"
    assert command(["init", str(bare), "--template", "unique"], _context(tmp_path)) == 0
    assert (bare / PROJECT_DIRECTORY / PROJECT_FILE).is_file()

    ambiguous = tmp_path / "ambiguous"
    assert command(["init", str(ambiguous), "--template", "same"], _context(tmp_path)) == 2
    error = capsys.readouterr().err
    assert "one:same, two:same" in error
    assert not ambiguous.exists()


def test_list_templates_when_none_are_installed(tmp_path: Path, capsys) -> None:
    assert command(["init", "--list-templates"], _context(tmp_path)) == 0
    assert capsys.readouterr().out == "no templates available\n"


def test_parameters_parse_json_and_validate_before_disk(tmp_path: Path, capsys) -> None:
    source = _template(
        tmp_path / "template",
        """[template]
id = 'parameters'
[template.instantiate]
file = 'hook.py'
[template.parameters.n]
type = 'integer'
[template.parameters.text]
type = 'string'
""",
        files={
            "hook.py": """import json
from pathlib import Path
request = json.loads(__import__('sys').stdin.read())
Path('parameters.json').write_text(json.dumps(request['parameters']))
print(json.dumps({'notes': ['parameters checked']}))
""",
        },
    )
    missing = tmp_path / "missing"
    assert command(["init", str(missing), "--template", str(source)], _context(tmp_path)) == 2
    assert not missing.exists()
    assert "missing mandatory" in capsys.readouterr().err

    target = tmp_path / "parameterized"
    assert (
        command(
            [
                "init",
                str(target),
                "--template",
                str(source),
                "--parameter",
                "n=3",
                "--parameter",
                'text="hello=world"',
            ],
            _context(tmp_path),
        )
        == 0
    )
    assert json.loads((target / "parameters.json").read_text(encoding="utf-8")) == {
        "n": 3,
        "text": "hello=world",
    }
    assert "note: parameters checked" in capsys.readouterr().out

    undeclared = tmp_path / "undeclared"
    assert (
        command(["init", str(undeclared), "--template", str(source), "--parameter", "other=true"], _context(tmp_path))
        == 2
    )
    assert not undeclared.exists()
    assert "declares no parameters" in capsys.readouterr().err


def test_parameter_and_list_combinations_fail(tmp_path: Path, capsys) -> None:
    target = tmp_path / "plain"
    assert command(["init", str(target), "--parameter", "x=1"], _context(tmp_path)) == 2
    assert not target.exists()
    assert "requires --template" in capsys.readouterr().err

    assert command(["init", str(target), "--list-templates"], _context(tmp_path)) == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_hook_failure_rolls_back_fresh_target_and_preserves_nonempty_target(tmp_path: Path, capsys) -> None:
    source = _template(
        tmp_path / "failing",
        "[template]\nid = 'failing'\n[template.instantiate]\nfile = 'hook.py'\n",
        files={
            "hook.py": """from pathlib import Path
Path('hook-created.txt').write_text('partial')
raise SystemExit(1)
""",
        },
    )
    fresh = tmp_path / "fresh"
    assert command(["init", str(fresh), "--template", str(source)], _context(tmp_path)) == 2
    assert not fresh.exists()

    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "user.txt").write_text("keep", encoding="utf-8")
    assert command(["init", str(existing), "--template", str(source)], _context(tmp_path)) == 2
    assert (existing / "user.txt").read_text(encoding="utf-8") == "keep"
    assert (existing / PROJECT_DIRECTORY).is_dir()
    assert (existing / "hook-created.txt").is_file()
    assert "partial state left in" in capsys.readouterr().err


def test_project_info_is_passed_to_hook(tmp_path: Path) -> None:
    source = _template(
        tmp_path / "info",
        "[template]\nid = 'info'\n[template.instantiate]\nfile = 'hook.py'\n",
        files={
            "hook.py": """import json
from pathlib import Path
request = json.loads(__import__('sys').stdin.read())
Path('project-info.json').write_text(json.dumps(request['project']))
print('{}')
""",
        },
    )
    target = tmp_path / "project"
    assert (
        command(
            ["init", str(target), "--name", "Example", "--description", "A project", "--template", str(source)],
            _context(tmp_path),
        )
        == 0
    )
    info = json.loads((target / "project-info.json").read_text(encoding="utf-8"))
    assert info["name"] == "Example"
    assert info["description"] == "A project"
    assert info["project_id"] == read_project(target)["project_id"]
