"""Test project-template manifests, resolution, and instantiation."""

import json
import stat
from pathlib import Path

import pytest

from httk.core.project.templates import (
    ProjectTemplate,
    TemplateParameter,
    available_templates,
    check_parameters,
    instantiate_template,
    parse_template_manifest,
    resolve_template,
)


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))


def _manifest(root: Path, text: str) -> None:
    (root / "httk_project_template.toml").write_text(text, encoding="utf-8")


def _template(root: Path, text: str = "[template]\nid = 'demo'\n") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _manifest(root, text)
    return root


def _installed_plugin(root: Path, name: str, template_id: str = "demo") -> Path:
    plugin = root / "data" / "plugins" / name
    template = plugin / "template"
    template.mkdir(parents=True)
    _manifest(template, f"[template]\nid = '{template_id}'\n")
    (plugin / "plugin.json").write_text(json.dumps({"built": True}), encoding="utf-8")
    (plugin / "httk_plugin.toml").write_text(f"[plugin]\nname = '{name}'\ntemplates = ['template']\n", encoding="utf-8")
    return template


def test_minimal_and_full_manifest(tmp_path: Path) -> None:
    minimal = _template(tmp_path / "minimal")
    assert parse_template_manifest(minimal) == ProjectTemplate("demo", None, (), None, (), minimal)

    full = tmp_path / "full"
    full.mkdir()
    (full / "copy.txt").write_text("copy", encoding="utf-8")
    (full / "hook.py").write_text("", encoding="utf-8")
    _manifest(
        full,
        """[template]
id = "full"
description = "Full template"
files = ["copy.txt"]

[template.instantiate]
file = "hook.py"

[template.parameters.name]
type = "string"
description = "A name"

[template.parameters.count]
type = "integer"
default = 2
""",
    )
    expected = parse_template_manifest(full)
    assert expected.id == "full"
    assert expected.files == ("copy.txt",)
    assert expected.instantiate_file == "hook.py"
    assert expected.parameters == (
        TemplateParameter("name", "string", "A name", None, False),
        TemplateParameter("count", "integer", None, 2, True),
    )


@pytest.mark.parametrize(
    "text",
    [
        "[template]\nid = 'demo'\nextra = true\n",
        "[template]\nid = 'demo'\n[template.instantiate]\nfile = 'hook.py'\nextra = true\n",
        "[template]\nid = 'demo'\n[template.parameters.x]\ntype = 'string'\nextra = true\n",
    ],
)
def test_manifest_unknown_keys(tmp_path: Path, text: str) -> None:
    (tmp_path / "hook.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        parse_template_manifest(_template(tmp_path, text))


@pytest.mark.parametrize("template_id", ["Bad", "has space", "-bad", ".", ".."])
def test_manifest_id_rules(tmp_path: Path, template_id: str) -> None:
    with pytest.raises(ValueError):
        parse_template_manifest(_template(tmp_path, f"[template]\nid = '{template_id}'\n"))


@pytest.mark.parametrize("name", ["bad-name", "1bad", "has space"])
def test_manifest_parameter_name_rules(tmp_path: Path, name: str) -> None:
    text = f"[template]\nid = 'demo'\n[template.parameters.'{name}']\ntype = 'string'\n"
    with pytest.raises(ValueError):
        parse_template_manifest(_template(tmp_path, text))


def test_manifest_protected_overlap_and_parameter_errors(tmp_path: Path) -> None:
    (tmp_path / "hook.py").write_text("", encoding="utf-8")
    _manifest(tmp_path, "[template]\nid = 'demo'\nfiles = ['httk_project_template.toml']\n")
    with pytest.raises(ValueError):
        parse_template_manifest(tmp_path)
    _manifest(
        tmp_path,
        "[template]\nid = 'demo'\nfiles = ['hook.py']\n[template.instantiate]\nfile = 'hook.py'\n",
    )
    with pytest.raises(ValueError):
        parse_template_manifest(tmp_path)
    _manifest(tmp_path, "[template]\nid = 'demo'\nfiles = ['a', 'a']\n")
    (tmp_path / "a").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_template_manifest(tmp_path)
    (tmp_path / "nested").mkdir()
    _manifest(tmp_path, "[template]\nid = 'demo'\nfiles = ['nested', 'nested/x']\n")
    (tmp_path / "nested" / "x").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_template_manifest(tmp_path)

    _manifest(tmp_path, "[template]\nid = 'demo'\n[template.parameters.x]\ntype = 'string'\n")
    with pytest.raises(ValueError, match=r"no \[template.instantiate\]"):
        parse_template_manifest(tmp_path)
    _manifest(
        tmp_path,
        "[template]\nid = 'demo'\n[template.parameters.x]\ntype = 'integer'\ndefault = 'no'\n",
    )
    _manifest(
        tmp_path,
        "[template]\nid = 'demo'\n[template.instantiate]\nfile = 'hook.py'\n"
        "[template.parameters.x]\ntype = 'integer'\ndefault = 'no'\n",
    )
    with pytest.raises(ValueError, match="default"):
        parse_template_manifest(tmp_path)


def test_manifest_hook_must_be_python_or_executable(tmp_path: Path) -> None:
    (tmp_path / "hook.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(ValueError, match="executable"):
        parse_template_manifest(
            _template(tmp_path, "[template]\nid = 'demo'\n[template.instantiate]\nfile = 'hook.sh'\n")
        )


def test_check_parameters() -> None:
    template = ProjectTemplate(
        "demo",
        None,
        (),
        "hook.py",
        (
            TemplateParameter("name", "string", None, None, False),
            TemplateParameter("count", "integer", None, 3, True),
        ),
        Path("."),
    )
    with pytest.raises(ValueError, match="name.*other|other.*name"):
        check_parameters(
            ProjectTemplate(
                template.id,
                template.description,
                template.files,
                template.instantiate_file,
                (*template.parameters, TemplateParameter("other", "boolean", None, None, False)),
                template.root,
            ),
            {},
        )
    with pytest.raises(ValueError, match="declares no parameters"):
        check_parameters(template, {"other": True})
    with pytest.raises(ValueError, match="JSON.*quote"):
        check_parameters(template, {"name": 1})
    assert check_parameters(template, {"name": "Ada"}) == {"name": "Ada", "count": 3}
    assert check_parameters(template, {"name": "Ada", "count": 4}) == {"name": "Ada", "count": 4}


def test_resolve_templates(tmp_path: Path) -> None:
    explicit = _template(tmp_path / "explicit")
    assert resolve_template(str(explicit)).root == explicit
    _installed_plugin(tmp_path, "alpha", "unique")
    _installed_plugin(tmp_path, "one", "same")
    _installed_plugin(tmp_path, "two", "same")
    assert resolve_template("alpha:unique").id == "unique"
    assert resolve_template("unique").id == "unique"
    with pytest.raises(ValueError, match="alpha:unique|one:same"):
        resolve_template("missing")
    with pytest.raises(ValueError, match="one:same, two:same"):
        resolve_template("same")
    with pytest.raises(ValueError, match="not installed"):
        resolve_template("missing:unique")
    with pytest.raises(ValueError, match="no template"):
        resolve_template("alpha:missing")
    assert [(name, template.id) for name, template in available_templates()] == [
        ("alpha", "unique"),
        ("one", "same"),
        ("two", "same"),
    ]


def test_static_instantiation_copies_modes_and_preflights(tmp_path: Path) -> None:
    source = _template(tmp_path / "source", "[template]\nid = 'demo'\nfiles = ['file.txt', 'directory']\n")
    file = source / "file.txt"
    file.write_text("file", encoding="utf-8")
    file.chmod(0o751)
    (source / "directory").mkdir()
    (source / "directory" / "nested.txt").write_text("nested", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    assert instantiate_template(parse_template_manifest(source), project, {}, project_info={}) == ()
    assert (project / "file.txt").read_text(encoding="utf-8") == "file"
    assert stat.S_IMODE((project / "file.txt").stat().st_mode) == 0o751
    assert (project / "directory" / "nested.txt").read_text(encoding="utf-8") == "nested"

    collision_source = _template(tmp_path / "collision", "[template]\nid = 'demo'\nfiles = ['a', 'b']\n")
    (collision_source / "a").write_text("a", encoding="utf-8")
    (collision_source / "b").write_text("b", encoding="utf-8")
    collision_project = tmp_path / "collision-project"
    collision_project.mkdir()
    (collision_project / "b").write_text("old", encoding="utf-8")
    with pytest.raises(ValueError, match="b"):
        instantiate_template(parse_template_manifest(collision_source), collision_project, {}, project_info={})
    assert not (collision_project / "a").exists()
    assert (collision_project / "b").read_text(encoding="utf-8") == "old"


def test_symlink_inside_directory_is_rejected(tmp_path: Path) -> None:
    source = _template(tmp_path / "source", "[template]\nid = 'demo'\nfiles = ['directory']\n")
    (source / "directory").mkdir()
    outside = tmp_path / "outside"
    outside.write_text("outside", encoding="utf-8")
    (source / "directory" / "link").symlink_to(outside)
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(ValueError, match="symlink"):
        instantiate_template(parse_template_manifest(source), project, {}, project_info={})
    assert not (project / "directory").exists()


def _write_python_hook(source: Path, body: str) -> None:
    (source / "hook.py").write_text(
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "from httk.core.project.templates import template_instantiate_main\n" + body,
        encoding="utf-8",
    )


def test_python_hook_round_trip_and_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_WORKFLOW_SOMETHING", "secret")
    source = _template(
        tmp_path / "source",
        """[template]
id = "demo"
[template.instantiate]
file = "hook.py"
[template.parameters.name]
type = "string"
""",
    )
    _write_python_hook(
        source,
        """def handle(request):
    assert request.template == "demo"
    assert request.parameters == {"name": "Ada"}
    assert request.project["label"] == "test"
    assert request.project["root"] == str(Path.cwd())
    assert "HTTK_WORKFLOW_SOMETHING" not in os.environ
    assert "HTTK_DATA_HOME" in os.environ
    Path("created.txt").write_text(json.dumps(dict(request.project)), encoding="utf-8")
    return {"notes": ["created", "ok"]}

template_instantiate_main(handle)
""",
    )
    project = tmp_path / "project"
    project.mkdir()
    assert instantiate_template(
        parse_template_manifest(source), project, {"name": "Ada"}, project_info={"label": "test"}
    ) == ("created", "ok")
    assert (project / "created.txt").is_file()


def test_executable_hook_and_failures(tmp_path: Path) -> None:
    source = _template(
        tmp_path / "source",
        "[template]\nid = 'demo'\n[template.instantiate]\nfile = 'hook.sh'\n",
    )
    hook = source / "hook.sh"
    hook.write_text("#!/bin/sh\nprintf '{\"notes\":[\"shell\"]}\\n'\n", encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    project = tmp_path / "project"
    project.mkdir()
    assert instantiate_template(parse_template_manifest(source), project, {}, project_info={}) == ("shell",)

    failing = _template(
        tmp_path / "failing",
        "[template]\nid = 'demo'\n[template.instantiate]\nfile = 'hook.sh'\n",
    )
    fail_hook = failing / "hook.sh"
    fail_hook.write_text("#!/bin/sh\nprintf '%s' 'stderr tail' >&2\nexit 3\n", encoding="utf-8")
    fail_hook.chmod(fail_hook.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "fail-project").mkdir()
    with pytest.raises(ValueError, match="exit 3.*stderr tail"):
        instantiate_template(parse_template_manifest(failing), tmp_path / "fail-project", {}, project_info={})

    bad = _template(
        tmp_path / "bad",
        "[template]\nid = 'demo'\n[template.instantiate]\nfile = 'hook.sh'\n",
    )
    bad_hook = bad / "hook.sh"
    bad_hook.write_text("#!/bin/sh\nprintf 'not json\\n'\n", encoding="utf-8")
    bad_hook.chmod(bad_hook.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "bad-project").mkdir()
    with pytest.raises(ValueError, match="invalid JSON"):
        instantiate_template(parse_template_manifest(bad), tmp_path / "bad-project", {}, project_info={})
