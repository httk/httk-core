from collections.abc import Mapping
from pathlib import Path
from typing import get_type_hints

import pytest

from httk.core import CLIContext, File
from httk.core._registry_tool import (
    check_core_records,
    check_property_records,
    command,
    type_annotation_for_fulltype,
)
from httk.core._typed_record_tool import check_typed_records
from httk.core.register import known_cli_commands


@pytest.mark.parametrize(
    ("fulltype", "annotation"),
    (
        ("string", "str"),
        ("integer", "int"),
        ("boolean", "bool"),
        ("float", "float"),
        ("timestamp", "datetime.datetime"),
        ("dict", "Mapping[str, Any]"),
        ("list of string", "tuple[str, ...]"),
        ("list of list of float", "tuple[tuple[float, ...], ...]"),
    ),
)
def test_type_annotation_inverse(fulltype: str, annotation: str) -> None:
    assert type_annotation_for_fulltype(fulltype) == annotation


def test_generated_core_records_are_current() -> None:
    assert check_core_records()


def test_checksums_annotation_uses_schema_value_type() -> None:
    assert get_type_hints(File)["checksums"] == Mapping[str, str] | None


def test_registry_cli_is_registered() -> None:
    assert "registry" in known_cli_commands()


def test_registry_gen_refuses_non_source_layout(monkeypatch, capsys) -> None:
    from httk.core import _registry_tool as registry_tool

    monkeypatch.setattr(registry_tool, "__file__", "/tmp/site-packages/httk/core/_registry_tool.py")
    assert command(["gen", "core"], CLIContext("httk", Path.cwd())) == 1
    assert "source checkout" in capsys.readouterr().err


def test_registry_gen_refuses_symlinked_target(tmp_path, monkeypatch, capsys) -> None:
    from httk.core import _registry_tool as registry_tool

    core = tmp_path / "src" / "httk" / "core"
    core.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "httk-core"\n', encoding="utf-8")
    target = core / "entry_types.py"
    target.symlink_to(tmp_path.parent / f"{tmp_path.name}-outside.py")
    monkeypatch.setattr(registry_tool, "__file__", str(core / "_registry_tool.py"))
    assert command(["gen", "core"], CLIContext("httk", Path.cwd())) == 1
    assert "outside the source checkout" in capsys.readouterr().err


def test_generated_property_records_are_current() -> None:
    assert check_property_records()


def test_missing_generated_module_is_not_current(tmp_path, monkeypatch, capsys) -> None:
    from httk.core import _registry_tool as registry_tool

    assert not check_typed_records(tmp_path / "property_records.py", "anything")
    core = tmp_path / "src" / "httk" / "core"
    core.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "httk-core"\n', encoding="utf-8")
    monkeypatch.setattr(registry_tool, "__file__", str(core / "_registry_tool.py"))
    assert not check_core_records() and not check_property_records()
    for record in ("core", "property-records"):
        assert command(["check", record], CLIContext("httk", Path.cwd())) == 1
        err = capsys.readouterr().err
        assert "is missing" in err and f"Regenerate with: httk registry gen {record}" in err
    assert command(["gen", "property-records"], CLIContext("httk", Path.cwd())) == 0
    assert check_property_records()
