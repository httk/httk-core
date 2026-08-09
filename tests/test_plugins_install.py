"""Test the local plugin install state machine."""

import importlib
import io
import json
import logging
import os
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import pytest

from httk.core.digests import sha256_file
from httk.core.plugins import (
    build_plugin,
    install_plugin,
    installed_plugins,
    plugin_program,
    uninstall_plugin,
)


def _plugin(root: Path, name: str = "demo", *, build: bool = False, executable: bool = True) -> Path:
    root.mkdir()
    (root / "httk_plugin.toml").write_text(
        f"[plugin]\nname = '{name}'\n[plugin.programs.tool]\nfile = 'bin/tool'\n"
        + ("[plugin.build]\ncommand = 'sh build.sh'\nartifacts = ['bin/tool']\n" if build else ""),
        encoding="utf-8",
    )
    (root / "bin").mkdir()
    if not build:
        tool = root / "bin/tool"
        tool.write_text("#!/bin/sh\nprintf '%s' \"$*\" > \"$1\"\n", encoding="utf-8")
        if executable:
            tool.chmod(0o755)
    return root


@pytest.fixture
def plugin_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    data = tmp_path / "data"
    monkeypatch.setenv("HTTK_DATA_HOME", str(data))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "source", data


def test_install_buildless_plugin_and_shim(plugin_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    source, data = plugin_dirs
    _plugin(source)
    installed = install_plugin(source)
    metadata = json.loads((installed.root / "plugin.json").read_text(encoding="utf-8"))
    assert metadata["format"] == "httk-plugin-install"
    assert metadata["source_kind"] == "directory"
    assert metadata["built"] is None
    assert metadata["shims"] == ["tool"]
    shim = data / "bin/tool"
    assert shim.is_file() and os.access(shim, os.X_OK)
    output = tmp_path / "args"
    subprocess.run([str(shim), str(output), "one", "two"], check=True)
    assert output.read_text(encoding="utf-8") == f"{output} one two"
    assert plugin_program("demo", "tool") == (installed.root / "bin/tool").resolve()
    assert len(installed_plugins()) == 1


def test_install_builds_plugin(plugin_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    source, data = plugin_dirs
    _plugin(source, build=True)
    (source / "tool.in").write_text("#!/bin/sh\nprintf '%s' \"$*\" > \"$1\"\n", encoding="utf-8")
    (source / "build.sh").write_text(
        "#!/bin/sh\nmkdir -p bin\ncp tool.in bin/tool\nchmod +x bin/tool\n", encoding="utf-8"
    )
    (source / "build.sh").chmod(0o755)
    installed = install_plugin(source)
    metadata = json.loads((installed.root / "plugin.json").read_text(encoding="utf-8"))
    assert metadata["built"] is True
    assert metadata["platform_tag"] == "any"
    assert "platform_output" in metadata
    output = tmp_path / "args"
    subprocess.run([str(data / "bin/tool"), str(output), "built"], check=True)
    assert output.read_text(encoding="utf-8") == f"{output} built"


def test_failed_build_remains_and_can_be_rebuilt(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    _plugin(source, build=True)
    (source / "build.sh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (source / "build.sh").chmod(0o755)
    with pytest.raises(ValueError, match=r"run: httk plugin build demo$"):
        install_plugin(source)
    root = data / "plugins/demo"
    assert root.is_dir()
    assert json.loads((root / "plugin.json").read_text(encoding="utf-8"))["built"] is False
    assert not (data / "bin/tool").exists()
    (root / "build.sh").write_text(
        "#!/bin/sh\nmkdir -p bin\nprintf '#!/bin/sh\\n' > bin/tool\nchmod +x bin/tool\n", encoding="utf-8"
    )
    (root / "build.sh").chmod(0o755)
    assert build_plugin("demo").metadata["built"] is True
    assert (data / "bin/tool").exists()


def test_non_executable_build_output_uses_failure_path(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    _plugin(source, build=True)
    (source / "build.sh").write_text("#!/bin/sh\nmkdir -p bin\ncp tool.in bin/tool\n", encoding="utf-8")
    (source / "tool.in").write_text("#!/bin/sh\n", encoding="utf-8")
    (source / "build.sh").chmod(0o755)
    with pytest.raises(ValueError, match=r"run: httk plugin build demo$"):
        install_plugin(source)
    root = data / "plugins/demo"
    assert json.loads((root / "plugin.json").read_text(encoding="utf-8"))["built"] is False
    (root / "bin/tool").chmod(0o755)
    assert build_plugin("demo").metadata["built"] is True


def test_force_replaces_plugin_and_refreshes_shim(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    _plugin(source)
    install_plugin(source)
    (data / "plugins/demo/old-marker").write_text("old", encoding="utf-8")
    replacement = source.parent / "replacement"
    _plugin(replacement)
    (replacement / "new-marker").write_text("new", encoding="utf-8")
    with pytest.raises(ValueError, match="already installed"):
        install_plugin(replacement)
    install_plugin(replacement, force=True)
    assert not (data / "plugins/demo/old-marker").exists()
    assert (data / "plugins/demo/new-marker").exists()
    assert (data / "bin/tool").exists()


def test_shim_collision_happens_before_placement(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    data.joinpath("bin").mkdir(parents=True)
    (data / "bin/tool").write_text("foreign", encoding="utf-8")
    _plugin(source)
    with pytest.raises(ValueError, match="blocked by existing shim"):
        install_plugin(source)
    assert not (data / "plugins/demo").exists()


def test_template_is_fully_validated(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    _plugin(source)
    template = source / "template"
    template.mkdir()
    (template / "httk_project_template.toml").write_text(
        "[template]\nid = 'bad'\nparameters = {broken = {type = 'string'}}\n", encoding="utf-8"
    )
    (source / "httk_plugin.toml").write_text("[plugin]\nname = 'demo'\ntemplates = ['template']\n", encoding="utf-8")
    with pytest.raises(ValueError, match="plugin 'demo' template 'template'"):
        install_plugin(source)
    assert not (data / "plugins/demo").exists()


def test_uninstall_preserves_foreign_shim(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    _plugin(source)
    install_plugin(source)
    shim = data / "bin/tool"
    shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uninstall_plugin("demo")
    assert not (data / "plugins/demo").exists()
    assert shim.exists()


def _tar_plugin(tmp_path: Path) -> Path:
    source = _plugin(tmp_path / "source")
    archive = tmp_path / "plugin.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(source, arcname="repo-main")
    return archive


def test_tar_archive_unwraps_single_top_directory(plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs
    archive = _tar_plugin(data.parent)
    installed = install_plugin(archive)
    assert installed.name == "demo"
    metadata = json.loads((installed.root / "plugin.json").read_text(encoding="utf-8"))
    assert metadata["source_kind"] == "archive"
    assert metadata["archive_sha256"] == sha256_file(archive)


def test_zip_archive_preserves_executable_program(plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs
    archive = data.parent / "plugin.zip"
    manifest = "[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = 'bin/tool'\n"
    info = zipfile.ZipInfo("bundle/httk_plugin.toml")
    tool = zipfile.ZipInfo("bundle/bin/tool")
    tool.external_attr = 0o100755 << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, manifest)
        bundle.writestr(tool, "#!/bin/sh\nexit 0\n")
    installed = install_plugin(archive)
    assert os.access(installed.root / "bin/tool", os.X_OK)
    assert os.access(data / "bin/tool", os.X_OK)


@pytest.mark.parametrize("kind", ["tar", "zip"])
def test_malicious_archive_is_rejected(plugin_dirs: tuple[Path, Path], kind: str) -> None:
    _, data = plugin_dirs
    archive = data.parent / f"bad.{kind}"
    if kind == "tar":
        with tarfile.open(archive, "w") as bundle:
            member = tarfile.TarInfo("../escape")
            member.size = 4
            bundle.addfile(member, io.BytesIO(b"oops"))
    else:
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("/escape", "oops")
    with pytest.raises(ValueError):
        install_plugin(archive)
    assert not (data / "plugins/demo").exists()


def test_zip_symlink_is_rejected(plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs
    archive = data.parent / "symlink.zip"
    member = zipfile.ZipInfo("bundle/link")
    member.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(member, "target")
    with pytest.raises(ValueError, match="unsafe zip member"):
        install_plugin(archive)
    assert not (data / "plugins/demo").exists()


def test_http_archive_download(monkeypatch: pytest.MonkeyPatch, plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs
    archive = _tar_plugin(data.parent)
    payload = archive.read_bytes()

    def open_url(url: str, *, timeout: float) -> io.BytesIO:
        assert url == "https://example.test/plugin.tar.gz"
        assert timeout == 60.0
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", open_url)
    installed = install_plugin("https://example.test/plugin.tar.gz")
    metadata = json.loads((installed.root / "plugin.json").read_text(encoding="utf-8"))
    assert metadata["source_kind"] == "url"
    assert metadata["archive_sha256"] == sha256_file(archive)


def test_http_archive_download_error(monkeypatch: pytest.MonkeyPatch, plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs

    def open_url(url: str, *, timeout: float) -> io.BytesIO:
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", open_url)
    with pytest.raises(ValueError, match="https://example.test/plugin.tar.gz"):
        install_plugin("https://example.test/plugin.tar.gz")
    assert not (data / "plugins").exists() or not any((data / "plugins").iterdir())


def _git_plugin(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _plugin(repository / "plugin")
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repository), "add", "plugin"], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=httk test",
            "-c",
            "user.email=test@example.test",
            "-C",
            str(repository),
            "commit",
            "-m",
            "plugin",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(repository), "tag", "v1"], check=True, capture_output=True)
    return repository


def test_git_archive_url_clone_and_commit_metadata(plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs
    repository = _git_plugin(data.parent)
    installed = install_plugin(f"git+{repository.as_uri()}@v1")
    metadata = json.loads((installed.root / "plugin.json").read_text(encoding="utf-8"))
    assert metadata["source_kind"] == "git"
    assert metadata["ref"] == "v1"
    assert len(metadata["commit"]) == 40
    assert not (installed.root / ".git").exists()
    assert not (installed.root / ".acquired").exists()


def test_git_refless_clone_and_bad_sources(plugin_dirs: tuple[Path, Path]) -> None:
    _, data = plugin_dirs
    repository = _git_plugin(data.parent)
    assert install_plugin(f"git+{repository.as_uri()}").name == "demo"
    with pytest.raises(ValueError):
        install_plugin(f"git+{repository.as_uri()}@missing")


@pytest.mark.parametrize("source", ["git+ssh://host/repo", "git@host:repo"])
def test_unsupported_git_urls(source: str, plugin_dirs: tuple[Path, Path]) -> None:
    with pytest.raises(ValueError, match="only https/http/file git URLs are supported"):
        install_plugin(source)


def test_nonexistent_path_is_not_a_source(plugin_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is not an installed-plugin source"):
        install_plugin(tmp_path / "missing")


def _two_program_plugin(root: Path) -> Path:
    root.mkdir()
    (root / "httk_plugin.toml").write_text(
        "[plugin]\nname = 'demo'\n"
        "[plugin.programs.first]\nfile = 'bin/first'\n"
        "[plugin.programs.second]\nfile = 'bin/second'\n"
        "[plugin.build]\ncommand = 'sh build.sh'\nartifacts = ['bin/*']\n",
        encoding="utf-8",
    )
    (root / "build.sh").write_text(
        "#!/bin/sh\nmkdir -p bin\nprintf '#!/bin/sh\\nexit 0\\n' > bin/first\n"
        "printf '#!/bin/sh\\nexit 0\\n' > bin/second\nchmod +x bin/first bin/second\n",
        encoding="utf-8",
    )
    (root / "build.sh").chmod(0o755)
    return root


def test_force_replacement_skips_invalid_old_shim_and_warns(
    plugin_dirs: tuple[Path, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source, data = plugin_dirs
    _plugin(source)
    install_plugin(source)
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    metadata_path = data / "plugins/demo/plugin.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["shims"] = [str(sentinel)]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    replacement = source.parent / "replacement"
    _plugin(replacement)
    (replacement / "httk_plugin.toml").write_text("[plugin]\nname = 'demo'\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        install_plugin(replacement, force=True)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert "Ignoring invalid plugin shim name" in caplog.text


def test_shim_write_failure_removes_partial_shims(plugin_dirs: tuple[Path, Path]) -> None:
    source, data = plugin_dirs
    _two_program_plugin(source)
    install_plugin(source)
    second = data / "bin/second"
    second.unlink()
    second.mkdir()
    with pytest.raises(ValueError, match=r"run: httk plugin build demo$"):
        build_plugin("demo")
    metadata = json.loads((data / "plugins/demo/plugin.json").read_text(encoding="utf-8"))
    assert metadata["built"] is False
    assert not (data / "bin/first").exists()
    assert second.is_dir()


def test_metadata_write_failure_removes_published_shims(
    plugin_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, data = plugin_dirs
    _plugin(source)
    install_module = importlib.import_module("httk.core.plugins.install")
    original_write_json = install_module._write_json
    failed = False

    def fail_final_metadata(path: Path, value: object) -> None:
        nonlocal failed
        if path == data / "plugins/demo/plugin.json" and not failed:
            failed = True
            raise OSError("metadata write failed")
        original_write_json(path, value)

    monkeypatch.setattr(install_module, "_write_json", fail_final_metadata)
    with pytest.raises(ValueError, match="metadata write failed"):
        install_plugin(source)
    assert not (data / "bin/tool").exists()


def test_build_platform_probe_receives_stripped_environment(
    plugin_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = plugin_dirs
    source.mkdir()
    (source / "httk_plugin.toml").write_text(
        "[plugin]\nname = 'demo'\n[plugin.programs.tool]\nfile = 'bin/tool'\n"
        "[plugin.build]\ncommand = 'sh build.sh'\nartifacts = ['bin/tool']\nplatform = 'sh probe.sh'\n",
        encoding="utf-8",
    )
    (source / "build.sh").write_text(
        "#!/bin/sh\nmkdir -p bin\nprintf '#!/bin/sh\\nexit 0\\n' > bin/tool\nchmod +x bin/tool\n",
        encoding="utf-8",
    )
    (source / "probe.sh").write_text("#!/bin/sh\nprintf '%s' \"${HTTK_SECRET:-absent}\"\n", encoding="utf-8")
    (source / "build.sh").chmod(0o755)
    (source / "probe.sh").chmod(0o755)
    monkeypatch.setenv("HTTK_SECRET", "secret")
    monkeypatch.chdir(source)
    installed = install_plugin(source)
    metadata = json.loads((installed.root / "plugin.json").read_text(encoding="utf-8"))
    assert metadata["platform_output"] == "absent"
    assert metadata["platform_tag"].startswith("absent.")
