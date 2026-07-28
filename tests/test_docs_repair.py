from pathlib import Path

import pytest

from httk.core.cli_context import CLIContext
from httk.core.docs import cli
from httk.core.docs.semver import Version
from httk.core.docs.sitetree import ComposeError, ImmutabilityError, compose_site


def make_build(path: Path, text: str) -> None:
    path.mkdir()
    (path / "index.html").write_text(text, encoding="utf-8")
    (path / "api.html").write_text(f"api:{text}", encoding="utf-8")


def test_repair_replaces_existing_release_transactionally(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    original = tmp_path / "original"
    replacement = tmp_path / "replacement"
    make_build(original, "original")
    make_build(replacement, "replacement")
    site = tmp_path / "site"
    compose_site(site, original, slug="core", site_url="https://docs.example/core", source_commit=None, target=Version(1, 0, 0))

    with caplog.at_level("WARNING"):
        result = compose_site(
            site,
            replacement,
            slug="core",
            site_url="https://docs.example/core",
            source_commit=None,
            target=Version(1, 0, 0),
            repair=True,
        )

    assert result.changed
    assert (site / "v1.0.0" / "index.html").read_text(encoding="utf-8") == "replacement"
    assert "repairing immutable documentation release v1.0.0" in caplog.text
    assert not list(site.glob(".old-release-*"))


def test_repair_of_nonexistent_release_fails(tmp_path: Path) -> None:
    build = tmp_path / "build"
    make_build(build, "new")
    with pytest.raises(ComposeError, match="cannot repair nonexistent release v1.0.0"):
        compose_site(
            tmp_path / "site",
            build,
            slug="core",
            site_url="https://docs.example/core",
            source_commit=None,
            target=Version(1, 0, 0),
            repair=True,
        )


def test_normal_compose_still_refuses_different_release(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_build(first, "first")
    make_build(second, "second")
    site = tmp_path / "site"
    compose_site(site, first, slug="core", site_url="https://docs.example/core", source_commit=None, target=Version(1, 0, 0))
    with pytest.raises(ImmutabilityError, match="immutable"):
        compose_site(site, second, slug="core", site_url="https://docs.example/core", source_commit=None, target=Version(1, 0, 0))


def test_cli_repair_uses_release_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    original = tmp_path / "original"
    replacement = tmp_path / "replacement"
    make_build(original, "original")
    make_build(replacement, "replacement")
    site = tmp_path / "site"
    arguments = [
        "compose",
        "--site",
        str(site),
        "--build",
        str(original),
        "--release",
        "v1.0.0",
        "--slug",
        "core",
        "--url",
        "https://docs.example/core",
    ]
    assert cli.command(arguments, CLIContext("httk", tmp_path)) == 0
    capsys.readouterr()
    arguments[arguments.index("--release")] = "--repair"
    arguments[arguments.index("v1.0.0")] = "v1.0.0"
    arguments[arguments.index("--build") + 1] = str(replacement)
    assert cli.command(arguments, CLIContext("httk", tmp_path)) == 0
    assert (site / "v1.0.0" / "index.html").read_text(encoding="utf-8") == "replacement"
