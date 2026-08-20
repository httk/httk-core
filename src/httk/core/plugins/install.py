"""Install, build, and uninstall httk plugins from local directories."""

import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import cast

from ..building import BuildError, BuildResult, execute_build
from ..digests import sha256_file, tree_digest
from ..project import templates as _templates
from .installed import PLUGIN_METADATA, InstalledPlugin, plugin_root, plugins_home, shims_home
from .manifest import PluginManifest, parse_plugin_manifest

__all__ = ["build_plugin", "install_plugin", "uninstall_plugin"]

_BUILD_COMMAND = "run: httk plugin build {}"
_PROGRAM_NAME_RE = re.compile(r"[a-z0-9._-]+")
_LOGGER = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _metadata(root: Path) -> dict[str, object]:
    try:
        with (root / PLUGIN_METADATA).open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {PLUGIN_METADATA}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{PLUGIN_METADATA} must contain a JSON object")
    return cast(dict[str, object], value)


def _installed(root: Path) -> InstalledPlugin:
    return InstalledPlugin(root.name, root, parse_plugin_manifest(root), _metadata(root))


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _shim_names(metadata: Mapping[str, object]) -> tuple[str, ...]:
    raw = metadata.get("shims", ())
    if not isinstance(raw, list):
        _LOGGER.warning("Ignoring invalid plugin shims field")
        return ()
    result: list[str] = []
    for value in raw:
        if (
            not isinstance(value, str)
            or _PROGRAM_NAME_RE.fullmatch(value) is None
            or value in {".", ".."}
            or value.startswith("-")
            or value != Path(value).name
        ):
            _LOGGER.warning("Ignoring invalid plugin shim name %r", value)
            continue
        result.append(value)
    return tuple(result)


def _program_files(metadata: Mapping[str, object]) -> Mapping[str, str]:
    raw = metadata.get("programs", {})
    if not isinstance(raw, dict):
        return {}
    return {name: value for name, value in raw.items() if isinstance(name, str) and isinstance(value, str)}


def _remove_shims(root: Path, metadata: Mapping[str, object], *, verify_target: bool) -> None:
    programs = _program_files(metadata)
    for name in _shim_names(metadata):
        shim = shims_home() / name
        if not os.path.lexists(shim):
            continue
        if verify_target:
            target = root / PurePosixPath(programs.get(name, ""))
            try:
                text = shim.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if _shim_text(target) != text:
                continue
        if shim.is_dir() and not shim.is_symlink():
            _LOGGER.warning("Skipping directory at plugin shim path %s", shim)
            continue
        if not shim.is_file() and not shim.is_symlink():
            _LOGGER.warning("Skipping non-file at plugin shim path %s", shim)
            continue
        try:
            shim.unlink()
        except OSError as exc:
            _LOGGER.warning("Cannot remove plugin shim %s: %s", shim, exc)


def _shim_owner(name: str, program: str) -> bool:
    root = plugins_home() / name
    if not root.is_dir() or root.is_symlink() or not (root / PLUGIN_METADATA).is_file():
        return False
    try:
        return program in _shim_names(_metadata(root))
    except ValueError:
        return False


def _check_shim_collisions(name: str, manifest: PluginManifest) -> None:
    for program in manifest.programs:
        shim = shims_home() / program.name
        if os.path.lexists(shim) and not _shim_owner(name, program.name):
            raise ValueError(f"plugin program {program.name!r} is blocked by existing shim {shim}")


def _verify_programs(root: Path, manifest: PluginManifest) -> None:
    for program in manifest.programs:
        path = root / PurePosixPath(program.file)
        if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"plugin program {program.name!r} is not a regular executable file: {path}")


def _shim_text(path: Path) -> str:
    escaped = str(path.resolve()).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    return f'#!/bin/sh\nexec "{escaped}" "$@"\n'


def _write_shims(root: Path, manifest: PluginManifest) -> None:
    destination = shims_home()
    destination.mkdir(parents=True, exist_ok=True)
    for program in manifest.programs:
        shim = destination / program.name
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{program.name}.tmp.", dir=destination)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(_shim_text(root / PurePosixPath(program.file)))
            os.chmod(temporary, 0o755)
            os.replace(temporary, shim)
        finally:
            temporary.unlink(missing_ok=True)


def _mark_failed(root: Path, metadata: dict[str, object]) -> None:
    _remove_shims(root, metadata, verify_target=True)
    metadata["built"] = False
    metadata.pop("built_at", None)
    metadata.pop("platform_tag", None)
    metadata.pop("platform_output", None)
    _write_json(root / PLUGIN_METADATA, metadata)


def _build_and_verify(root: Path, manifest: PluginManifest, metadata: dict[str, object]) -> None:
    result: BuildResult | None = None
    if manifest.build is not None:
        try:
            result = execute_build(
                root,
                manifest.build,
                strip_env_prefixes=("HTTK_",),
                keep_env=("HTTK_CONFIG_HOME", "HTTK_DATA_HOME"),
                log_path=root / "plugin-build.log",
            )
        except BuildError as exc:
            _mark_failed(root, metadata)
            raise ValueError(f"{exc}; {_BUILD_COMMAND.format(manifest.name)}") from exc
    try:
        _verify_programs(root, manifest)
    except ValueError as exc:
        _mark_failed(root, metadata)
        raise ValueError(f"{exc}; {_BUILD_COMMAND.format(manifest.name)}") from exc

    if result is not None:
        metadata.update(
            built=True,
            built_at=_utc_now(),
            platform_tag=result.tag,
            platform_output=result.platform_output,
        )
    try:
        _write_shims(root, manifest)
        _write_json(root / PLUGIN_METADATA, metadata)
    except Exception as exc:
        if manifest.build is not None:
            _mark_failed(root, metadata)
            raise ValueError(f"cannot write plugin shims: {exc}; {_BUILD_COMMAND.format(manifest.name)}") from exc
        _remove_shims(root, metadata, verify_target=True)
        _write_json(root / PLUGIN_METADATA, metadata)
        raise ValueError(f"cannot write plugin shims: {exc}") from exc


def _git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_SYSTEM"] = os.devnull
    return environment


def _run_git(cwd: Path, arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=_git_environment(),
        )
    except FileNotFoundError as exc:
        raise ValueError("git is not available on PATH") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
    return result


def _git_source(value: str) -> tuple[str, str | None]:
    remainder = value[4:]
    if remainder.startswith("git@"):  # Keep the diagnostic useful for the common SSH shorthand.
        raise ValueError("only https/http/file git URLs are supported")
    ref: str | None = None
    if "@" in remainder:
        left, candidate = remainder.rsplit("@", 1)
        authority = left.split("://", 1)[1].split("/", 1)[0] if "://" in left else ""
        if "://" in left and "@" not in authority:
            if not candidate:
                raise ValueError("git ref must not be empty")
            remainder, ref = left, candidate
    parsed = urllib.parse.urlsplit(remainder)
    if parsed.scheme not in {"https", "http", "file"} or (parsed.scheme != "file" and not parsed.netloc):
        raise ValueError("only https/http/file git URLs are supported")
    return remainder, ref


def _clone_git(value: str, scratch: Path) -> tuple[Path, dict[str, object]]:
    url, ref = _git_source(value)
    repository = scratch / "repo"
    arguments = ["clone", "--depth", "1"]
    if ref is not None:
        arguments.extend(["--branch", ref])
    arguments.extend([url, str(repository)])
    result = _run_git(scratch, arguments, check=False)
    if result.returncode != 0:
        sha_ref = ref is not None and 7 <= len(ref) <= 40 and all(char in "0123456789abcdef" for char in ref)
        if not sha_ref:
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
        _remove_path(repository)
        repository.mkdir()
        _run_git(repository, ["init"])
        _run_git(repository, ["remote", "add", "origin", url])
        fetch_arguments = ["fetch", "--depth", "1", "origin"]
        if ref is not None:
            fetch_arguments.append(ref)
        _run_git(repository, fetch_arguments)
        _run_git(repository, ["checkout", "FETCH_HEAD"])
    commit = _run_git(repository, ["rev-parse", "HEAD"]).stdout.strip()
    _remove_path(repository / ".git")
    return repository, {"source_kind": "git", **({"ref": ref} if ref is not None else {}), "commit": commit}


def _unwrap_tree(root: Path) -> Path:
    if (root / "httk_plugin.toml").is_file():
        return root
    entries = list(root.iterdir())
    directories = [entry for entry in entries if entry.is_dir()]
    regular_files = [entry for entry in entries if entry.is_file() and not entry.is_symlink()]
    if len(directories) == 1 and not regular_files:
        return directories[0]
    return root


def _copy_acquired(source: Path, staging: Path) -> None:
    shutil.copytree(source, staging, dirs_exist_ok=True, symlinks=False)


def _extract_zip(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = member.filename
                path = PurePosixPath(name)
                mode = member.external_attr >> 16
                if (
                    not name
                    or "\\" in name
                    or path.is_absolute()
                    or any(part == ".." for part in path.parts)
                    or PureWindowsPath(name).drive
                    or (mode and (mode & 0o170000) == 0o120000)
                ):
                    raise ValueError(f"unsafe zip member {name!r}")
                target = destination / path
                if name.endswith("/") or (mode and (mode & 0o170000) == 0o040000):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if mode and (mode & 0o170000) not in {0, 0o100000}:
                    raise ValueError(f"unsupported zip member {name!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(member))
                if mode:
                    target.chmod(mode & 0o7777)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"cannot extract zip archive {archive}: {exc}") from exc


def _extract_archive(archive: Path, destination: Path) -> None:
    if tarfile.is_tarfile(archive):
        try:
            with tarfile.open(archive) as bundle:
                bundle.extractall(destination, filter="data")
        except (OSError, tarfile.TarError) as exc:
            raise ValueError(f"cannot extract tar archive {archive}: {exc}") from exc
        return
    if zipfile.is_zipfile(archive):
        _extract_zip(archive, destination)
        return
    raise ValueError(f"{archive!r} is not a recognized archive")


def _download_archive(url: str, destination: Path) -> Path:
    archive = destination / "download"
    try:
        with urllib.request.urlopen(url, timeout=60.0) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    except Exception as exc:
        raise ValueError(f"could not download plugin archive {url!r}: {exc}") from exc
    return archive


def _acquire(source: str | Path, staging: Path) -> tuple[dict[str, object], str]:
    original = str(source)
    acquired = staging / ".acquired"
    acquired.mkdir()
    if isinstance(source, str) and source.startswith("git+"):
        tree, git_metadata = _clone_git(source, acquired)
        _copy_acquired(_unwrap_tree(tree), staging)
        shutil.rmtree(acquired)
        return git_metadata, original
    if isinstance(source, str) and source.startswith("git@"):
        raise ValueError("only https/http/file git URLs are supported")

    path = Path(source).expanduser() if isinstance(source, (str, Path)) else None
    if path is not None and path.is_dir() and not path.is_symlink():
        shutil.rmtree(acquired)
        shutil.copytree(path, staging, symlinks=False, dirs_exist_ok=True)
        return {"source_kind": "directory"}, original

    archive: Path | None = None
    metadata: dict[str, object]
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        archive = _download_archive(source, acquired)
        metadata = {"source_kind": "url"}
    elif path is not None and path.is_file() and not path.is_symlink():
        archive = path
        metadata = {"source_kind": "archive"}
    else:
        raise ValueError(
            f"{source!r} is not an installed-plugin source: expected a plugin directory, a .tar/.zip archive, "
            "an http(s) archive URL, or a git+https URL"
        )

    assert archive is not None
    metadata["archive_sha256"] = sha256_file(archive)
    extracted = acquired / "extract"
    extracted.mkdir()
    _extract_archive(archive, extracted)
    _copy_acquired(_unwrap_tree(extracted), staging)
    shutil.rmtree(acquired)
    return metadata, original


def install_plugin(source: str | Path, *, force: bool = False) -> InstalledPlugin:
    """Install one plugin from an existing local directory.

    ``source_sha256`` is pre-build provenance: build output and the build log
    may change the installed tree after this digest is recorded.

    :param source: Supply the local plugin directory.
    :param force: Replace an installed plugin with the same name.
    :return: The installed plugin.
    :raises ValueError: If the source or plugin is invalid or cannot be built.
    """

    home = plugins_home()
    home.mkdir(parents=True, exist_ok=True)
    staging = home / f".staging-{uuid.uuid4()}"
    staging.mkdir()
    try:
        acquisition, original_source = _acquire(source, staging)
        manifest = parse_plugin_manifest(staging)

        for member in manifest.templates:
            try:
                _templates.parse_template_manifest(staging / PurePosixPath(member))
            except (OSError, ValueError) as exc:
                raise ValueError(f"plugin {manifest.name!r} template {member!r}: {exc}") from exc

        target = home / manifest.name
        if os.path.lexists(target) and not force:
            raise ValueError(f"plugin {manifest.name!r} is already installed; use --force to replace it")
        _check_shim_collisions(manifest.name, manifest)
        metadata: dict[str, object] = {
            "format": "httk-plugin-install",
            "format_version": 2,
            "name": manifest.name,
            "source": original_source,
            **acquisition,
            # This is intentionally computed before plugin.json and any build output exist.
            "source_sha256": tree_digest(staging),
            "installed_at": _utc_now(),
            "built": None if manifest.build is None else False,
            "programs": {program.name: program.file for program in manifest.programs},
            "shims": [program.name for program in manifest.programs],
        }
        _write_json(staging / PLUGIN_METADATA, metadata)

        old: Path | None = None
        old_metadata: dict[str, object] | None = None
        if force and os.path.lexists(target):
            old = home / f".old-{uuid.uuid4()}"
            if target.is_dir() and not target.is_symlink() and (target / PLUGIN_METADATA).is_file():
                try:
                    old_metadata = _metadata(target)
                except ValueError:
                    old_metadata = None
            # ponytail: no install lock; single-user directory is the concurrency ceiling.
            os.replace(target, old)
        try:
            os.replace(staging, target)
        except BaseException:
            if old is not None and os.path.lexists(old) and not os.path.lexists(target):
                os.replace(old, target)
            raise
        if old is not None and old_metadata is not None:
            _remove_shims(old, old_metadata, verify_target=False)
        if old is not None and os.path.lexists(old):
            _remove_path(old)

        installed = _installed(target)
        _build_and_verify(target, installed.manifest, dict(installed.metadata))
        return _installed(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def build_plugin(name: str) -> InstalledPlugin:
    """Build and publish the declared programs of an installed plugin."""

    root = plugin_root(name)
    installed = _installed(root)
    _check_shim_collisions(name, installed.manifest)
    _build_and_verify(root, installed.manifest, dict(installed.metadata))
    return _installed(root)


def uninstall_plugin(name: str) -> None:
    """Remove an installed plugin and its still-owned shims."""

    root = plugin_root(name)
    metadata = _metadata(root)
    _remove_shims(root, metadata, verify_target=True)
    _remove_path(root)
