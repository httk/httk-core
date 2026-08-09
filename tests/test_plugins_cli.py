import json
import os
from pathlib import Path

import pytest

from httk.core import CLIContext
from httk.core.plugins import install_plugin, shims_home
from httk.core.plugins.cli import command


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    data = tmp_path / "data"
    monkeypatch.setenv("HTTK_DATA_HOME", str(data))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path / "path"), os.defpath]))
    return data, tmp_path


def _plugin(root: Path, name: str = "demo", *, description: str = "A demo plugin", program: str = "tool") -> Path:
    (root / "bin").mkdir(parents=True)
    (root / "httk_plugin.toml").write_text(
        f"[plugin]\nname = '{name}'\ndescription = '{description}'\ntemplates = ['template']\n"
        f"workflows = ['workflow']\n[plugin.programs.{program}]\nfile = 'bin/tool'\n"
        "description = 'the tool'\n",
        encoding="utf-8",
    )
    tool = root / "bin/tool"
    tool.write_text("#!/bin/sh\nprintf '%s' \"$*\" > \"$1\"\n", encoding="utf-8")
    tool.chmod(0o755)
    template = root / "template"
    template.mkdir()
    (template / "httk_project_template.toml").write_text(
        "[template]\nid = 'starter'\ndescription = 'a starter'\n", encoding="utf-8"
    )
    workflow = root / "workflow"
    workflow.mkdir()
    (workflow / "httk_workflow.toml").write_text("[workflow]\nname = 'demo'\n", encoding="utf-8")
    return root


def _context(tmp_path: Path) -> CLIContext:
    return CLIContext(program="httk", cwd=tmp_path)


def test_install_and_path_hint(homes: tuple[Path, Path], capsys) -> None:
    data, tmp_path = homes
    source = _plugin(tmp_path / "source")
    assert command(["install", str(source)], _context(tmp_path)) == 0
    output = capsys.readouterr().out
    assert f"Installed plugin 'demo' from {source}" in output
    assert f"add {shims_home()} to PATH" in output
    monkeypatch_path = os.pathsep.join([str(shims_home()), str(tmp_path / "path")])
    os.environ["PATH"] = monkeypatch_path
    assert command(["install", str(source), "--force"], _context(tmp_path)) == 0
    assert f"add {shims_home()} to PATH" not in capsys.readouterr().out
    assert (data / "plugins/demo").is_dir()


def test_install_failure_uses_command_error(homes: tuple[Path, Path], capsys) -> None:
    _, tmp_path = homes
    assert command(["install", str(tmp_path / "missing")], _context(tmp_path)) == 2
    assert capsys.readouterr().err.startswith("httk plugin:")


def test_list(homes: tuple[Path, Path], capsys) -> None:
    _, tmp_path = homes
    assert command(["list"], _context(tmp_path)) == 0
    assert capsys.readouterr().out == "no plugins installed\n"
    one = _plugin(tmp_path / "one", "one", description="One")
    two = _plugin(tmp_path / "two", "two", description="Two", program="other")
    install_plugin(one)
    install_plugin(two)
    assert command(["list"], _context(tmp_path)) == 0
    assert capsys.readouterr().out == "one  One\ntwo  Two\n"


def test_show_text_and_json(homes: tuple[Path, Path], capsys) -> None:
    _, tmp_path = homes
    install_plugin(_plugin(tmp_path / "source"))
    assert command(["show", "demo"], _context(tmp_path)) == 0
    output = capsys.readouterr().out
    assert "name                  demo" in output
    assert "templates:" in output and "starter  a starter" in output
    assert "workflows:" in output and "  workflow" in output
    assert "programs:" in output and "tool  bin/tool  the tool" in output
    assert command(["show", "demo", "--json"], _context(tmp_path)) == 0
    description = json.loads(capsys.readouterr().out)
    assert description["name"] == "demo"
    assert description["templates"][0]["id"] == "starter"
    assert description["programs"][0]["name"] == "tool"
    assert command(["show", "missing"], _context(tmp_path)) == 2
    assert "httk plugin:" in capsys.readouterr().err


def test_build_uninstall_path_and_run(homes: tuple[Path, Path], capsys) -> None:
    _, tmp_path = homes
    source = tmp_path / "source"
    source.mkdir()
    (source / "httk_plugin.toml").write_text(
        "[plugin]\nname = 'built'\n[plugin.programs.tool]\nfile = 'bin/tool'\n"
        "[plugin.build]\ncommand = '/bin/sh build.sh'\nartifacts = ['bin/tool']\n",
        encoding="utf-8",
    )
    (source / "build.sh").write_text(
        "#!/bin/sh\nmkdir -p bin\ncp tool.in bin/tool\nchmod +x bin/tool\n",
        encoding="utf-8",
    )
    (source / "build.sh").chmod(0o755)
    (source / "tool.in").write_text("#!/bin/sh\nprintf '%s' \"$*\" > \"$1\"\n", encoding="utf-8")
    assert command(["install", str(source)], _context(tmp_path)) == 0
    assert " (built)" in capsys.readouterr().out
    result = tmp_path / "args"
    assert command(["path", "built", "tool"], _context(tmp_path)) == 0
    path = Path(capsys.readouterr().out.strip())
    assert path.is_absolute()
    assert command(["run", "built", "tool", str(result), "--flag"], _context(tmp_path)) == 0
    assert result.read_text(encoding="utf-8") == f"{result} --flag"
    assert command(["uninstall", "built"], _context(tmp_path)) == 0
    assert "Uninstalled plugin 'built'" in capsys.readouterr().out


def test_run_propagates_program_exit_code(homes: tuple[Path, Path]) -> None:
    _, tmp_path = homes
    source = _plugin(tmp_path / "source")
    (source / "bin/tool").write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    (source / "bin/tool").chmod(0o755)
    install_plugin(source)
    assert command(["run", "demo", "tool", "--flag"], _context(tmp_path)) == 9
