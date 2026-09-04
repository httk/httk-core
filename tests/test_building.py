from pathlib import Path

import pytest

from httk.core import _manifest
from httk.core.building import BuildSpec, artifact_excluder, read_manifest_build_spec


def _manifest_file(root: Path, text: str, name: str = "httk_test.toml") -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def _build(root: Path, body: str, *, name: str = "httk_test.toml", table: str = "thing") -> None:
    _manifest_file(root, f"[{table}.build]\n{body}\n", name)


def _read(root: Path, *, table: str = "thing") -> BuildSpec | None:
    return read_manifest_build_spec(
        root,
        manifest_name="httk_test.toml",
        table_name=table,
        protected_names=("keepme.toml",),
    )


def test_missing_manifest_and_build_table_return_none(tmp_path: Path) -> None:
    assert _read(tmp_path) is None
    _manifest_file(tmp_path, "[thing]\nname = 'test'\n")
    assert _read(tmp_path) is None


def test_valid_build_spec_roundtrips(tmp_path: Path) -> None:
    _build(tmp_path, 'command = "python build.py"\nplatform = "linux x86_64"\nartifacts = ["build", "*.o"]')
    assert _read(tmp_path) == BuildSpec("python build.py", ("build", "*.o"), "linux x86_64")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('command = "python build.py"\nartifacts = ["build"]\nbad = true', r"unknown key \[thing.build.bad\]"),
        ('artifacts = ["build"]', "command is required"),
        ('command = 1\nartifacts = ["build"]', "command must be a nonempty string"),
        ("command = 'python \"build.py'\nartifacts = [\"build\"]", "valid shell words"),
        ('command = "python build.py"\nartifacts = []', "nonempty array"),
        ('command = "python build.py"\nartifacts = ["/"]', "must be relative"),
        ('command = "python build.py"\nartifacts = ["build\\\\out"]', "no .*backslashes"),
        ('command = "python build.py"\nartifacts = ["build/../out"]', "no .*\\.\\.'"),
        ('command = "python build.py"\nartifacts = ["."]', "no .*\\.\\.'"),
        ('command = "python build.py"\nartifacts = ["*"]', "protected names"),
    ],
)
def test_build_spec_rejects_invalid_sections(tmp_path: Path, body: str, message: str) -> None:
    _build(tmp_path, body)
    with pytest.raises(ValueError, match=message):
        _read(tmp_path)


def test_platform_is_optional(tmp_path: Path) -> None:
    _build(tmp_path, 'command = "python build.py"\nartifacts = ["build"]')
    assert _read(tmp_path) == BuildSpec("python build.py", ("build",))


def test_workflow_build_messages_are_preserved(tmp_path: Path) -> None:
    _manifest_file(
        tmp_path,
        '[workflow.build]\ncommand = "python build.py"\nartifacts = ["*"]\n',
        "httk_workflow.toml",
    )
    with pytest.raises(ValueError, match="would strip the runner entry point or manifest") as error:
        read_manifest_build_spec(
            tmp_path,
            manifest_name="httk_workflow.toml",
            table_name="workflow",
            protected_names=("run", "httk_workflow.toml"),
        )
    assert str(error.value) == (
        f"{tmp_path}: [workflow.build].artifacts pattern '*' would strip the runner entry point or manifest "
        "from publication; 'run' and 'httk_workflow.toml' must remain available"
    )


def test_artifact_excluder_matches_artifacts_and_descendants() -> None:
    excluded = artifact_excluder(BuildSpec("build", ("build", "*.o")))
    assert excluded("build")
    assert excluded("build/nested/output")
    assert excluded("module.o")
    assert not excluded("builder/output")
    assert not excluded("src/module.py")
    assert not artifact_excluder(None)("anything")


def test_reject_unknown_message() -> None:
    with pytest.raises(ValueError, match=r"^root: unknown key \[thing.build.extra\]$"):
        _manifest.reject_unknown({"extra": True}, {"command"}, "[thing.build]", Path("root"))


def test_member_path_guards_and_options(tmp_path: Path) -> None:
    (tmp_path / "file.py").write_text("", encoding="utf-8")
    (tmp_path / "directory").mkdir()
    outside = tmp_path.parent / "outside.py"
    outside.write_text("", encoding="utf-8")
    (tmp_path / "escape.py").symlink_to(outside)
    (tmp_path / "link").symlink_to(tmp_path / "file.py")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "link").symlink_to(tmp_path / "file.py")

    assert _manifest.member_path(tmp_path, "file.py", "[thing.file]", python=True) == "file.py"
    assert _manifest.member_path(tmp_path, "directory", "[thing.directory]", directory_ok=True) == "directory"
    assert _manifest.member_path(tmp_path, "future/output", "[thing.output]", must_exist=False) == "future/output"
    for value in ("../outside.py", "./file.py", "nested//file.py", "escape.py", "link", "nested/link"):
        with pytest.raises(ValueError):
            _manifest.member_path(tmp_path, value, "[thing.member]")
    with pytest.raises(ValueError):
        _manifest.member_path(tmp_path, "file.txt", "[thing.file]", python=True)
    with pytest.raises(ValueError):
        _manifest.member_path(tmp_path, "directory", "[thing.directory]")
    with pytest.raises(ValueError):
        _manifest.member_path(tmp_path, "../future", "[thing.output]", must_exist=False)


@pytest.mark.parametrize(
    ("value", "type_name", "expected"),
    [
        ("text", "string", True),
        (1, "number", True),
        (1.5, "number", True),
        (True, "number", False),
        (1, "integer", True),
        (True, "integer", False),
        (False, "boolean", True),
        ([], "array", True),
        ({}, "object", True),
    ],
)
def test_matches_json_type(value: object, type_name: str, expected: bool) -> None:
    assert _manifest.matches_json_type(value, type_name) is expected


def test_load_manifest_toml_reports_line_and_column(tmp_path: Path) -> None:
    path = _manifest_file(tmp_path, "[thing\ncommand = true\n")
    # tomllib reports the syntax-error position differently across CPython versions
    # (e.g. 3.13 flags line 2 col 1, 3.14 flags line 1 col 7); assert only that a
    # line/column is surfaced, not the version-specific coordinates.
    with pytest.raises(ValueError, match=r"invalid httk_test\.toml \(line \d+, column \d+\)"):
        _manifest.load_manifest_toml(path, tmp_path)
