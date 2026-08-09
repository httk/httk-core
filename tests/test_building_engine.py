import hashlib
import json
from pathlib import Path

import pytest

from httk.core.building import (
    DEFAULT_TAG,
    BuildError,
    BuildSpec,
    execute_build,
    overlay_artifacts,
    platform_tag,
    registered_generation,
    write_generation,
)


def _source(root: Path, body: str) -> Path:
    source = root / "source"
    source.mkdir()
    (source / "src.txt").write_text("source\n", encoding="utf-8")
    (source / "build.sh").write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    return source


def test_execute_build_collects_artifacts(tmp_path: Path) -> None:
    source = _source(tmp_path, "cp src.txt bin-out")
    result = execute_build(source, BuildSpec("sh build.sh", ("bin-out",)), strip_env_prefixes=())

    assert result.tag == DEFAULT_TAG
    assert result.platform_output == ""
    assert result.artifact_files == ("bin-out",)
    assert (source / "bin-out").read_text(encoding="utf-8") == "source\n"


def test_platform_tag_sanitizes_and_caches_output(tmp_path: Path) -> None:
    probe = tmp_path / "probe.sh"
    probe.write_text("#!/bin/sh\nprintf 'linux-x86\\n'\n", encoding="utf-8")
    command = f"sh {probe}"
    tag, output = platform_tag(command)
    probe.write_text("#!/bin/sh\nprintf changed\n", encoding="utf-8")

    cached_tag, cached_output = platform_tag(command)

    assert tag == f"linux-x86.{hashlib.sha256(output.encode()).hexdigest()[:8]}"
    assert (cached_tag, cached_output) == (tag, output)


def test_execute_build_reports_failure_and_writes_log(tmp_path: Path) -> None:
    source = _source(tmp_path, "echo build-tail; exit 7")
    log_path = tmp_path / "logs" / "build.log"

    with pytest.raises(BuildError, match="exit code 7.*build-tail") as failure:
        execute_build(
            source,
            BuildSpec("sh build.sh", ("bin-out",)),
            strip_env_prefixes=(),
            log_path=log_path,
        )

    assert failure.value.code == "runner_build_failed"
    assert "build-tail" in log_path.read_text(encoding="utf-8")


def test_execute_build_rejects_empty_artifact_match(tmp_path: Path) -> None:
    source = _source(tmp_path, "cp src.txt other-out")

    with pytest.raises(BuildError, match="no artifacts matching") as failure:
        execute_build(source, BuildSpec("sh build.sh", ("bin-out",)), strip_env_prefixes=())

    assert failure.value.code == "runner_build_failed"


def test_execute_build_strips_environment_and_keeps_requested_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path, "printf '%s|%s' \"${HTTK_FOO-}\" \"${HTTK_KEEP-}\" > bin-out")
    monkeypatch.setenv("HTTK_FOO", "stripped")
    monkeypatch.setenv("HTTK_KEEP", "kept")

    execute_build(
        source,
        BuildSpec("sh build.sh", ("bin-out",)),
        strip_env_prefixes=("HTTK_",),
        keep_env=("HTTK_KEEP",),
    )

    assert (source / "bin-out").read_text(encoding="utf-8") == "|kept"


def test_write_and_read_generation(tmp_path: Path) -> None:
    source = _source(tmp_path, "mkdir -p nested; cp src.txt nested/bin-out")
    result = execute_build(source, BuildSpec("sh build.sh", ("nested",)), strip_env_prefixes=())
    builds_root = tmp_path / "builds"
    stamp = {"format": "httk-test-build", "format_version": 1, "source_sha256": "abc"}

    generation = write_generation(builds_root, "group/item", result.tag, source, result.artifact_files, stamp)
    tag_root = builds_root / "group" / "item" / result.tag
    pointer = json.loads((tag_root / "current.json").read_text(encoding="utf-8"))

    assert generation == tag_root / pointer["generation"]
    assert generation.name.startswith("gen-")
    assert (generation / "build.json").is_file()
    assert not list(tag_root.glob(".gen-*"))
    assert (
        registered_generation(
            builds_root,
            "group/item",
            result.tag,
            format_name="httk-test-build",
            expected_source_sha256="abc",
        )
        == generation / "artifacts"
    )
    assert (
        registered_generation(
            builds_root,
            "group/item",
            result.tag,
            format_name="httk-test-build",
            expected_source_sha256="wrong",
        )
        is None
    )

    (tag_root / "current.json").unlink()
    assert (
        registered_generation(
            builds_root,
            "group/item",
            result.tag,
            format_name="httk-test-build",
            expected_source_sha256="abc",
        )
        is None
    )


def test_registered_generation_rejects_wrong_format(tmp_path: Path) -> None:
    source = _source(tmp_path, "cp src.txt bin-out")
    builds_root = tmp_path / "builds"
    generation = write_generation(
        builds_root,
        "item",
        DEFAULT_TAG,
        source,
        ("src.txt",),
        {"format": "httk-test-build", "format_version": 1, "source_sha256": "abc"},
    )
    (generation / "build.json").write_text(
        json.dumps({"format": "other", "format_version": 1, "source_sha256": "abc"}), encoding="utf-8"
    )

    assert (
        registered_generation(
            builds_root, "item", DEFAULT_TAG, format_name="httk-test-build", expected_source_sha256="abc"
        )
        is None
    )


def test_registered_generation_allows_unspecified_source_digest(tmp_path: Path) -> None:
    source = _source(tmp_path, "cp src.txt bin-out")
    builds_root = tmp_path / "builds"
    write_generation(
        builds_root,
        "item",
        DEFAULT_TAG,
        source,
        ("src.txt",),
        {"format": "httk-test-build", "format_version": 1, "source_sha256": "abc"},
    )

    assert (
        registered_generation(
            builds_root, "item", DEFAULT_TAG, format_name="httk-test-build", expected_source_sha256=None
        )
        is not None
    )
    assert (
        registered_generation(
            builds_root, "item", DEFAULT_TAG, format_name="httk-test-build", expected_source_sha256="wrong"
        )
        is None
    )


def test_overlay_artifacts_copies_nested_files(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts" / "nested"
    artifacts.mkdir(parents=True)
    (artifacts / "out").write_text("new", encoding="utf-8")
    target = tmp_path / "staged" / "nested"
    target.mkdir(parents=True)
    (target / "out").write_text("old", encoding="utf-8")

    overlay_artifacts(tmp_path / "artifacts", tmp_path / "staged")

    assert (target / "out").read_text(encoding="utf-8") == "new"
