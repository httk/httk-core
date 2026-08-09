"""Provide an httk-internal toolkit for strict httk-owned TOML manifests.

Reject unknown keys and unsafe package members at manifest boundaries.
"""

import os
import tomllib
from collections.abc import Collection, Mapping
from pathlib import Path, PurePosixPath


def manifest_error(directory: Path, message: str) -> ValueError:
    """Create a manifest validation error.

    :param directory: Locate the manifest or package.
    :param message: Describe the validation failure.
    :return: The formatted validation error.
    """

    return ValueError(f"{directory}: {message}")


def require_table(value: object, path: str, directory: Path) -> Mapping[str, object]:
    """Require a TOML value to be a table.

    :param value: Check this TOML value.
    :param path: Name the manifest table.
    :param directory: Locate the manifest or package.
    :return: The validated table.
    :raises ValueError: If the value is not a table.
    """

    if not isinstance(value, Mapping):
        raise manifest_error(directory, f"{path} must be a table")
    return value


def reject_unknown(table: Mapping[str, object], allowed: Collection[str], path: str, directory: Path) -> None:
    """Reject keys not listed in an allowed manifest table.

    :param table: Inspect this manifest table.
    :param allowed: Name the accepted keys.
    :param path: Name the manifest table.
    :param directory: Locate the manifest or package.
    :raises ValueError: If the table contains an unknown key.
    """

    for key in table:
        if key not in allowed:
            dotted = path[1:-1] if path.startswith("[") and path.endswith("]") else path
            prefix = f"{dotted}." if dotted else ""
            raise manifest_error(directory, f"unknown key [{prefix}{key}]")


def require_string(
    table: Mapping[str, object], key: str, path: str, directory: Path, *, required: bool = False
) -> str | None:
    """Read a required or optional nonempty manifest string.

    :param table: Inspect this manifest table.
    :param key: Name the string member.
    :param path: Name the manifest table.
    :param directory: Locate the manifest or package.
    :param required: Require the member to be present.
    :return: The validated string, or ``None`` when optional and absent.
    :raises ValueError: If the member has the wrong type or is empty.
    """

    if key not in table:
        if required:
            raise manifest_error(directory, f"{path}.{key} is required")
        return None
    value = table[key]
    if not isinstance(value, str) or not value:
        raise manifest_error(directory, f"{path}.{key} must be a nonempty string")
    return value


def optional_string(table: Mapping[str, object], key: str, path: str, directory: Path) -> str | None:
    """Read an optional manifest string.

    :param table: Inspect this manifest table.
    :param key: Name the string member.
    :param path: Name the manifest table.
    :param directory: Locate the manifest or package.
    :return: The string, or ``None`` when absent.
    :raises ValueError: If the member is present with the wrong type.
    """

    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise manifest_error(directory, f"{path}.{key} must be a string")
    return value


def member_path(
    directory: Path,
    value: object,
    path: str,
    *,
    python: bool = False,
    directory_ok: bool = False,
    must_exist: bool = True,
) -> str:
    """Validate a relative, package-contained member path.

    :param directory: Locate the package directory.
    :param value: Supply the member path.
    :param path: Name the manifest member.
    :param python: Require a ``.py`` member.
    :param directory_ok: Accept a directory as well as a regular file.
    :param must_exist: Require the member to exist when true.
    :return: The normalized relative POSIX member path.
    :raises ValueError: If the path is unsafe or has the wrong kind.
    """

    if not isinstance(value, str) or not value:
        raise manifest_error(directory, f"{path} must name a relative regular file")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise manifest_error(directory, f"{path} must name a relative member without '..': {value!r}")
    if python and relative.suffix != ".py":
        raise manifest_error(directory, f"{path} must name a .py member: {value!r}")
    candidate = directory.joinpath(*relative.parts)
    root = directory.resolve()
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise manifest_error(directory, f"{path} member does not exist: {value!r}") from exc
    if not resolved.is_relative_to(root) or candidate.is_symlink():
        raise manifest_error(directory, f"{path} must name a regular member below the package: {value!r}")
    for index in range(1, len(relative.parts)):
        if directory.joinpath(*relative.parts[:index]).is_symlink():
            raise manifest_error(directory, f"{path} must not traverse a symlink: {value!r}")
    if must_exist and not candidate.is_file() and not (directory_ok and candidate.is_dir()):
        raise manifest_error(directory, f"{path} must name a regular member below the package: {value!r}")
    return relative.as_posix()


def executable_member(directory: Path, value: object, path: str) -> tuple[str, bool]:
    """Validate a Python or executable package member and return its kind.

    :param directory: Locate the package directory.
    :param value: Supply the member path.
    :param path: Name the manifest member.
    :return: The normalized member path and whether it is executable.
    :raises ValueError: If the member is unsafe or not executable.
    """

    if isinstance(value, str) and PurePosixPath(value).suffix == ".py":
        return member_path(directory, value, path, python=True), False
    member = member_path(directory, value, path)
    candidate = directory.joinpath(*PurePosixPath(member).parts)
    if not os.access(candidate, os.X_OK):
        raise manifest_error(directory, f"{path} must name a .py member or an executable member (chmod +x): {value!r}")
    return member, True


def matches_json_type(value: object, type_name: str) -> bool:
    """Check a value against one of the manifest JSON-compatible types.

    :param value: Check this value.
    :param type_name: Name the JSON-compatible type.
    :return: Whether the value matches the type.
    """

    if type_name == "string":
        return isinstance(value, str)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    return isinstance(value, dict)


def load_manifest_toml(path: Path, directory: Path) -> Mapping[str, object]:
    """Load and decode a strict-manifest TOML file.

    :param path: Locate the TOML file.
    :param directory: Locate the manifest or package for error messages.
    :return: The decoded TOML document.
    :raises ValueError: If the file cannot be read or decoded.
    """

    manifest_text = ""
    try:
        manifest_text = path.read_bytes().decode("utf-8")
        raw = tomllib.loads(manifest_text)
    except (OSError, UnicodeError) as exc:
        raise manifest_error(directory, f"cannot read {path.name}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        lineno = getattr(exc, "lineno", None) or len(manifest_text.splitlines())
        colno = getattr(exc, "colno", None) or len(manifest_text.rsplit("\n", 1)[-1]) + 1
        raise manifest_error(directory, f"invalid {path.name} (line {lineno}, column {colno}): {exc}") from exc
    if not isinstance(raw, dict):  # pragma: no cover - tomllib always returns a dict
        raise manifest_error(directory, "manifest must be a table")
    return raw
