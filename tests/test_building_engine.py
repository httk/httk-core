import hashlib
import json
import os
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


def test_platform_tag_cache_includes_probe_environment(tmp_path: Path) -> None:
    probe = tmp_path / "probe.sh"
    count = tmp_path / "count"
    probe.write_text(
        "#!/bin/sh\nprintf x >> \"$PROBE_COUNT\"\nprintf '%s' \"$PROBE_VALUE\"\n",
        encoding="utf-8",
    )
    command = f"sh {probe}"
    first_env = dict(os.environ, PROBE_COUNT=str(count), PROBE_VALUE="first")
    second_env = dict(os.environ, PROBE_COUNT=str(count), PROBE_VALUE="second")

    first = platform_tag(command, env=first_env)
    cached = platform_tag(command, env=first_env)
    second = platform_tag(command, env=second_env)

    assert first == cached
    assert first[0] != second[0]
    assert count.read_text(encoding="utf-8") == "xx"


def test_execute_build_reports_failure_and_writes_log(tmp_path: Path) -> None:
    source = _source(tmp_path, "echo build-output; exit 7")
    log_path = tmp_path / "logs" / "build.log"

    with pytest.raises(BuildError, match="exit code 7") as failure:
        execute_build(
            source,
            BuildSpec("sh build.sh", ("bin-out",)),
            strip_env_prefixes=(),
            log_path=log_path,
        )

    assert failure.value.code == "runner_build_failed"
    assert str(failure.value) == "build command 'sh build.sh' failed with exit code 7"
    assert log_path.read_text(encoding="utf-8") == (
        f"command: sh build.sh\n"
        f"cwd: {source}\n"
        f"exit code: 7\n"
        "platform output: ''\n"
        "build output was inherited by the terminal\n"
    )


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


def test_execute_build_cleans_environment_for_platform_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source(tmp_path, "cp src.txt bin-out")
    (source / "probe.sh").write_text(
        "#!/bin/sh\nprintf '%s|%s' \"${HTTK_SECRET-}\" \"${HTTK_KEEP-}\"\n", encoding="utf-8"
    )
    monkeypatch.setenv("HTTK_SECRET", "secret")
    monkeypatch.setenv("HTTK_KEEP", "kept")

    result = execute_build(
        source,
        BuildSpec("sh build.sh", ("bin-out",), platform=f"sh {source / 'probe.sh'}"),
        strip_env_prefixes=("HTTK_",),
        keep_env=("HTTK_KEEP",),
    )

    assert result.platform_output == "|kept"


def test_execute_build_can_route_stdout_to_stderr(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    source = _source(tmp_path, "echo live-output; cp src.txt bin-out")

    execute_build(
        source,
        BuildSpec("sh build.sh", ("bin-out",)),
        strip_env_prefixes=(),
        stdout_to_stderr=True,
    )

    assert "live-output" in capfd.readouterr().err


def test_write_and_read_generation(tmp_path: Path) -> None:
    source = _source(tmp_path, "mkdir -p nested; cp src.txt nested/bin-out")
    result = execute_build(source, BuildSpec("sh build.sh", ("nested",)), strip_env_prefixes=())
    builds_root = tmp_path / "builds"
    stamp = {"format": "httk-test-build", "format_version": 2, "source_sha256": "abc"}

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
        {"format": "httk-test-build", "format_version": 2, "source_sha256": "abc"},
    )
    (generation / "build.json").write_text(
        json.dumps({"format": "other", "format_version": 2, "source_sha256": "abc"}), encoding="utf-8"
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
        {"format": "httk-test-build", "format_version": 2, "source_sha256": "abc"},
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
