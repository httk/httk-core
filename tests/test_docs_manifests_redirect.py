import json
from pathlib import Path

import pytest

from httk.core.docs.manifests import (
    build_page_manifest,
    build_version_manifest,
    read_version_manifest,
    write_page_manifest,
    write_version_manifest,
)
from httk.core.docs.redirect import root_redirect_html, write_root_redirect
from httk.core.docs.semver import Version


def test_manifests_are_ordered(tmp_path: Path) -> None:
    html = tmp_path / "v2.0.0"
    (html / "reference").mkdir(parents=True)
    (html / "index.html").write_text("", encoding="utf-8")
    (html / "reference" / "z.html").write_text("", encoding="utf-8")
    (html / "reference" / "a.html").write_text("", encoding="utf-8")
    pages = build_page_manifest("v2.0.0", html)
    assert pages["pages"] == ["index.html", "reference/a.html", "reference/z.html"]
    root = build_version_manifest(
        "core", "https://docs.httk.org/core", "abc", [Version(1, 0, 0), Version(2, 0, 0)], ["main"]
    )
    assert [item["name"] for item in root["versions"]] == ["v2.0.0", "v1.0.0", "dev:main"]
    assert root["default"]["name"] == "v2.0.0"
    assert root["default"]["path"] == "latest/"
    write_version_manifest(tmp_path / "versions.json", root)
    write_page_manifest(html / "pages.json", pages)
    assert read_version_manifest(tmp_path / "versions.json")["project"] == "core"
    assert json.loads((html / "pages.json").read_text(encoding="utf-8"))["version"] == "v2.0.0"


def test_manifest_without_releases_or_source_commit() -> None:
    manifest = build_version_manifest("core", "https://docs.httk.org/core", None, [], [])
    assert manifest["source_commit"] is None
    assert manifest["versions"] == []
    assert manifest["default"] == {"name": "dev:main", "path": "dev/main/", "channel": "dev"}


def test_manifest_lists_both_dev_trees_in_fixed_order() -> None:
    manifest = build_version_manifest(
        "core", "https://docs.httk.org/core", "abc", [Version(1, 0, 0)], ["develop", "main"]
    )
    assert manifest["versions"] == [
        {"name": "v1.0.0", "path": "v1.0.0/", "channel": "release"},
        {"name": "dev:main", "path": "dev/main/", "channel": "dev"},
        {"name": "dev:develop", "path": "dev/develop/", "channel": "dev"},
    ]
    assert manifest["default"] == {"name": "v1.0.0", "path": "latest/", "channel": "release"}
    both = build_version_manifest("core", "https://docs.httk.org/core", None, [], ("develop", "main"))
    assert both["default"] == {"name": "dev:main", "path": "dev/main/", "channel": "dev"}
    develop_only = build_version_manifest("core", "https://docs.httk.org/core", None, [], ["develop"])
    assert [item["name"] for item in develop_only["versions"]] == ["dev:develop"]
    assert develop_only["default"] == {"name": "dev:develop", "path": "dev/develop/", "channel": "dev"}


@pytest.mark.parametrize("branch", ["", "Main", "feature", "a/b"])
def test_manifest_rejects_unsupported_dev_branch(branch: str) -> None:
    with pytest.raises(ValueError, match="unsupported development docs branch"):
        build_version_manifest("core", "https://docs.httk.org/core", None, [], [branch])


def test_root_redirect_is_relative(tmp_path: Path) -> None:
    html = root_redirect_html("v2.1.0/")
    assert html.startswith("<!doctype html>")
    assert 'http-equiv="refresh"' in html
    assert "url=v2.1.0/" in html
    assert "canonical" not in html
    write_root_redirect(tmp_path, "dev/main/")
    assert "dev/main/" in (tmp_path / "index.html").read_text(encoding="utf-8")
