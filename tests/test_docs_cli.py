from pathlib import Path
import zlib

import pytest

from httk.core.cli import CLIContext
from httk.core.docs import cli
from httk.core.docs.lockfile import compute_input_hash


def context(path: Path) -> CLIContext:
    return CLIContext("httk", path)


def test_cli_compose_and_filter_and_inventory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("home", encoding="utf-8")
    site = tmp_path / "site"
    assert (
        cli.command(
            ["compose", "--site", str(site), "--build", str(build), "--dev", "--slug", "core", "--url", "https://x"],
            context(tmp_path),
        )
        == 0
    )
    assert "composed dev:main" in capsys.readouterr().out
    lock = tmp_path / "lock"
    lock.write_text("# httk-core==x\nhttk-core==2.0.2\nrequests==2.32\n", encoding="utf-8")
    output = tmp_path / "filtered.txt"
    assert (
        cli.command(
            ["filter-lock", "--lock", str(lock), "--out", str(output), "--self-distribution", "core"], context(tmp_path)
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == "requests==2.32\n"
    inventory = tmp_path / "objects.inv"
    inventory.write_bytes(b"# Sphinx inventory version 2\n# Project: core\n# Version: dev:main\n" + zlib.compress(b""))
    copy = tmp_path / "copy.inv"
    assert (
        cli.command(["fetch-inventory", inventory.as_uri(), str(copy), "--expect-project", "core"], context(tmp_path))
        == 0
    )


def test_cli_compose_release_accepts_tag_and_bare_version(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("home", encoding="utf-8")
    site = tmp_path / "site"
    for spelling, normalized in (("v1.2.3", "v1.2.3"), ("1.2.4", "v1.2.4")):
        assert (
            cli.command(
                [
                    "compose",
                    "--site",
                    str(site),
                    "--build",
                    str(build),
                    "--release",
                    spelling,
                    "--slug",
                    "core",
                    "--url",
                    "https://x",
                ],
                context(tmp_path),
            )
            == 0
        )
        assert f"composed {normalized}" in capsys.readouterr().out


def test_cli_compose_immutability_failure_is_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    build = tmp_path / "build"
    build.mkdir()
    page = build / "index.html"
    page.write_text("first", encoding="utf-8")
    site = tmp_path / "site"
    arguments = [
        "compose",
        "--site",
        str(site),
        "--build",
        str(build),
        "--release",
        "v1.2.3",
        "--slug",
        "core",
        "--url",
        "https://x",
    ]
    assert cli.command(arguments, context(tmp_path)) == 0
    capsys.readouterr()
    page.write_text("different", encoding="utf-8")
    assert cli.command(arguments, context(tmp_path)) == 1
    assert "release directories are immutable" in capsys.readouterr().err


def test_cli_lock_and_lock_check_use_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Path, Path]] = []

    def fake_generate(project: Path, output: Path) -> None:
        calls.append((project, output))

    monkeypatch.setattr(cli, "generate_lock", fake_generate)
    assert cli.command(["lock"], context(tmp_path)) == 0
    assert calls == [(tmp_path, tmp_path / "docs/requirements.lock")]
    checked: list[Path] = []
    monkeypatch.setattr(cli, "check_lock", lambda project, lock: checked.append(lock))
    assert cli.command(["lock-check"], context(tmp_path)) == 0
    assert checked == [tmp_path / "docs/requirements.lock"]
    assert "current" in capsys.readouterr().out


def test_cli_failure_is_nonzero_and_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.command(
        [
            "compose",
            "--dev",
            "--slug",
            "core",
            "--url",
            "x",
            "--site",
            str(tmp_path / "s"),
            "--build",
            str(tmp_path / "missing"),
        ],
        context(tmp_path),
    )
    assert result == 1
    assert "does not exist" in capsys.readouterr().err


def test_cli_check_release_happy_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="2.0.2"\nrequires-python=">=3.12"\n', encoding="utf-8")
    digest = compute_input_hash(tmp_path / "pyproject.toml")
    (tmp_path / "docs" / "requirements.lock").write_text(
        f"# httk-docs-lock-schema: 1\n# input-hash: sha256:{digest}\n# python: 3.12\n# platform: linux\nrequests==2.32\n",
        encoding="utf-8",
    )
    assert cli.command(["check-release", "--project-dir", str(tmp_path), "--tag", "v2.0.2"], context(tmp_path)) == 0
    assert "passed" in capsys.readouterr().out


def test_cli_check_release_failure_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="2.0.2"\n', encoding="utf-8")
    assert cli.command(["check-release", "--project-dir", str(tmp_path), "--tag", "v2.0.2"], context(tmp_path)) == 1
    assert "documentation lock is missing" in capsys.readouterr().err


def test_cli_relative_project_dir_resolves_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path.parent)
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(cli, "generate_lock", lambda project, output: calls.append((project, output)))
    assert cli.command(["lock", "--project-dir", tmp_path.name], context(Path.cwd())) == 0
    assert calls == [(tmp_path, tmp_path / "docs" / "requirements.lock")]


def test_cli_refresh_inventories_release_file_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "docs" / "_inventories").mkdir(parents=True)
    fixture = tmp_path / "published" / "httk-core" / "v2.0.2"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 2.0.2\n" + zlib.compress(b"")
    )
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "requirements.lock").write_text("httk-core==2.0.2\n", encoding="utf-8")
    base = (tmp_path / "published").as_uri()
    assert (
        cli.command(
            ["refresh-inventories", "--project-dir", str(tmp_path), "--base-url", base, "--channel", "release"],
            context(tmp_path),
        )
        == 0
    )
    assert (tmp_path / "docs" / "_inventories" / "httk-core.inv").is_file()
    assert "v2.0.2" in capsys.readouterr().out


def test_cli_refresh_inventories_missing_pin_is_clean_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "requirements.lock").write_text("requests==2.32\n", encoding="utf-8")
    assert (
        cli.command(
            [
                "refresh-inventories",
                "--project-dir",
                str(tmp_path),
                "--base-url",
                "file:///missing",
                "--channel",
                "release",
            ],
            context(tmp_path),
        )
        == 1
    )
    assert "httk-core" in capsys.readouterr().err


def test_cli_refresh_inventories_wrong_project_is_clean_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "docs" / "_inventories").mkdir(parents=True)
    fixture = tmp_path / "published" / "httk-core" / "v2.0.2"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: other-project\n# Version: 2.0.2\n" + zlib.compress(b"")
    )
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "requirements.lock").write_text("httk-core==2.0.2\n", encoding="utf-8")
    assert (
        cli.command(
            [
                "refresh-inventories",
                "--project-dir",
                str(tmp_path),
                "--base-url",
                (tmp_path / "published").as_uri(),
                "--channel",
                "release",
            ],
            context(tmp_path),
        )
        == 1
    )
    assert "expected project 'httk-core'" in capsys.readouterr().err


def test_cli_refresh_inventories_wrong_version_is_clean_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "docs" / "_inventories").mkdir(parents=True)
    fixture = tmp_path / "published" / "httk-core" / "v2.0.2"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 9.9.9\n" + zlib.compress(b"")
    )
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "requirements.lock").write_text("httk-core==2.0.2\n", encoding="utf-8")
    assert (
        cli.command(
            [
                "refresh-inventories",
                "--project-dir",
                str(tmp_path),
                "--base-url",
                (tmp_path / "published").as_uri(),
                "--channel",
                "release",
            ],
            context(tmp_path),
        )
        == 1
    )
    assert "expected version '2.0.2'" in capsys.readouterr().err


def test_cli_refresh_inventories_second_failure_preserves_all_originals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory_dir = tmp_path / "docs" / "_inventories"
    inventory_dir.mkdir(parents=True)
    first_original = b"first-original"
    second_original = b"second-original"
    (inventory_dir / "httk-core.inv").write_bytes(first_original)
    (inventory_dir / "httk-io.inv").write_bytes(second_original)
    fixture = tmp_path / "published" / "httk-core" / "v2.0.2"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 2.0.2\n" + zlib.compress(b"")
    )
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-io"\nslug = "httk-io"\n'
        'repository-url = "https://example.test/io"\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "requirements.lock").write_text("httk-core==2.0.2\nhttk-io==1.0.0\n", encoding="utf-8")
    assert (
        cli.command(
            [
                "refresh-inventories",
                "--project-dir",
                str(tmp_path),
                "--base-url",
                (tmp_path / "published").as_uri(),
                "--channel",
                "release",
            ],
            context(tmp_path),
        )
        == 1
    )
    assert "httk-io" in capsys.readouterr().err
    assert (inventory_dir / "httk-core.inv").read_bytes() == first_original
    assert (inventory_dir / "httk-io.inv").read_bytes() == second_original
