#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Read and validate Sphinx intersphinx v2 inventory headers."""

import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

__all__ = ["InventoryError", "fetch_inventory", "read_inventory_header"]


class InventoryError(RuntimeError):
    """Raised when an inventory cannot be fetched or has unexpected metadata."""


_ALLOWED_SCHEMES = frozenset({"http", "https", "file"})
_MAX_INVENTORY_BYTES = 64 * 1024 * 1024
_READ_CHUNK_SIZE = 1024 * 1024


def _validate_url(url: str) -> None:
    scheme = urlsplit(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise InventoryError(f"inventory URL has unsupported scheme {scheme!r}: {url}")


class _AllowedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: object, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> Request | None:
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


def _inventory_bytes(path_or_bytes: str | Path | bytes) -> bytes:
    if isinstance(path_or_bytes, bytes):
        return path_or_bytes
    return Path(path_or_bytes).read_bytes()


def read_inventory_header(path_or_bytes: str | Path | bytes) -> tuple[str, str]:
    """Return project and version from the plain-text inventory header.

    :param path_or_bytes: Inventory file path or its contents.
    :return: Project and version declared by the inventory.
    :raises InventoryError: If the inventory does not have the expected header.
    """

    raw = _inventory_bytes(path_or_bytes)
    lines = raw.splitlines()
    if not lines or lines[0].decode("utf-8", "replace") != "# Sphinx inventory version 2":
        raise InventoryError("inventory does not have a Sphinx inventory version 2 header")
    if len(lines) < 3 or not lines[1].startswith(b"# Project: ") or not lines[2].startswith(b"# Version: "):
        raise InventoryError("inventory header is missing Project or Version")
    project = lines[1][len(b"# Project: ") :].decode("utf-8", "replace").strip()
    version = lines[2][len(b"# Version: ") :].decode("utf-8", "replace").strip()
    return project, version


def fetch_inventory(
    url: str,
    dest: str | Path,
    *,
    expected_project: str | None = None,
    expected_version: str | None = None,
) -> tuple[str, str]:
    """Fetch an inventory from HTTP(S) or ``file://``, validate it, and save it.

    :param url: HTTP(S) or ``file://`` URL of the inventory.
    :param dest: Destination path for the validated inventory.
    :param expected_project: Required project header, when supplied.
    :param expected_version: Required version header, when supplied.
    :return: Project and version declared by the fetched inventory.
    :raises InventoryError: If fetching, validation, or saving the inventory fails.
    """

    _validate_url(url)
    try:
        opener = build_opener(_AllowedRedirectHandler)
        with opener.open(url, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > _MAX_INVENTORY_BYTES:
                raise InventoryError(f"inventory {url} exceeds the 64 MiB size limit")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(_READ_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_INVENTORY_BYTES:
                    raise InventoryError(f"inventory {url} exceeds the 64 MiB size limit")
                chunks.append(chunk)
            final_url = response.geturl()
            _validate_url(final_url)
            data = b"".join(chunks)
    except OSError as exc:
        raise InventoryError(f"cannot fetch inventory {url}: {exc}") from exc
    except ValueError as exc:
        raise InventoryError(f"invalid inventory response from {url}: {exc}") from exc
    try:
        project, version = read_inventory_header(data)
    except InventoryError as exc:
        raise InventoryError(f"inventory {url}: {exc}") from exc
    if expected_project is not None and project != expected_project:
        raise InventoryError(f"inventory {url}: expected project {expected_project!r}, found {project!r}")
    if expected_version is not None and version != expected_version:
        raise InventoryError(f"inventory {url}: expected version {expected_version!r}, found {version!r}")
    destination = Path(dest)
    if destination.is_symlink():
        raise InventoryError(f"refusing symlink inventory destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return project, version
