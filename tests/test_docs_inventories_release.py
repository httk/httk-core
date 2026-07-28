from pathlib import Path
import zlib

import pytest

from httk.core.docs.config import InternalDependency, VersioningConfig
from httk.core.docs.inventories import InventoryError, fetch_inventory, read_inventory_header
from httk.core.docs.lockfile import compute_input_hash
from httk.core.docs.release import ReleaseError, check_release, dependency_doc_targets


def test_inventory_header_and_file_fetch(tmp_path: Path) -> None:
    source = tmp_path / "objects.inv"
    source.write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 2.0.2\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    assert read_inventory_header(source) == ("httk-core", "2.0.2")
    destination = tmp_path / "copy.inv"
    assert fetch_inventory(source.as_uri(), destination, expected_project="httk-core", expected_version="2.0.2") == (
        "httk-core",
        "2.0.2",
    )
    with pytest.raises(InventoryError, match="expected version"):
        fetch_inventory(source.as_uri(), destination, expected_version="9.9.9")


def test_malformed_inventory_header_fails(tmp_path: Path) -> None:
    source = tmp_path / "bad.inv"
    source.write_bytes(b"# Sphinx inventory version 1\n# Project: core\n# Version: dev:main\n")
    with pytest.raises(InventoryError, match="version 2"):
        read_inventory_header(source)


def test_dependency_urls() -> None:
    config = VersioningConfig(
        "core", "https://example.test/core", internal_dependencies=(InternalDependency("httk-io", "httk-io", "x"),)
    )
    assert dependency_doc_targets(config, {"httk-io": "1.2.3"}, "https://docs.httk.org", "release") == {
        "httk-io": "https://docs.httk.org/httk-io/v1.2.3/"
    }
    assert dependency_doc_targets(config, {}, "https://docs.httk.org/", "dev") == {
        "httk-io": "https://docs.httk.org/httk-io/dev/main/"
    }
    with pytest.raises(ReleaseError, match="httk-io.*docs/requirements.lock"):
        dependency_doc_targets(config, {}, "https://docs.httk.org", "release")


def test_release_checks_tag_lock_and_hash(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "2.0.2"\nrequires-python=">=3.12"\n', encoding="utf-8"
    )
    lock = tmp_path / "docs" / "requirements.lock"
    lock.write_text(
        "# httk-docs-lock-schema: 1\n# input-hash: sha256:" + "0" * 64
        + "\n# python: 3.12\n# platform: linux\nrequests==2\n",
        encoding="utf-8",
    )
    with pytest.raises(ReleaseError, match="does not match"):
        check_release(tmp_path, "v2.0.3")
    with pytest.raises(ReleaseError, match="input-hash mismatch"):
        check_release(tmp_path, "v2.0.2")


def _release_inventory_fixture(tmp_path: Path, inventory_version: str | None) -> None:
    (tmp_path / "docs" / "_inventories").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "2.0.2"\nrequires-python=">=3.12"\n', encoding="utf-8"
    )
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "core"\nrepository-url = "https://example.test/core"\n\n'
        '[[internal-dependency]]\ndistribution = "httk-io"\nslug = "httk-io"\n'
        'repository-url = "https://example.test/httk-io"\n',
        encoding="utf-8",
    )
    digest = compute_input_hash(tmp_path / "pyproject.toml")
    (tmp_path / "docs" / "requirements.lock").write_text(
        f"# httk-docs-lock-schema: 1\n# input-hash: sha256:{digest}\n# python: 3.12\n# platform: linux\nhttk-io==1.2.3\n",
        encoding="utf-8",
    )
    if inventory_version is not None:
        (tmp_path / "docs" / "_inventories" / "httk-io.inv").write_bytes(
            f"# Sphinx inventory version 2\n# Project: httk-io\n# Version: {inventory_version}\n".encode()
            + zlib.compress(b"")
        )


def test_release_checks_dependency_inventory(tmp_path: Path) -> None:
    _release_inventory_fixture(tmp_path, "1.2.3")
    assert str(check_release(tmp_path, "v2.0.2").version) == "2.0.2"


def test_release_missing_or_wrong_dependency_inventory_fails(tmp_path: Path) -> None:
    _release_inventory_fixture(tmp_path, None)
    with pytest.raises(ReleaseError, match=r"httk-io\.inv.*missing"):
        check_release(tmp_path, "v2.0.2")
    _release_inventory_fixture(tmp_path, "9.9.9")
    with pytest.raises(ReleaseError, match=r"expected project.*1\.2\.3"):
        check_release(tmp_path, "v2.0.2")
