"""Tests for the simulation-code support registry tier."""

import sys
from pathlib import Path

import pytest

import httk.registry
from httk.core._discover import discover_and_register
from httk.core.register import (
    CodeSupport,
    CollectorSupport,
    code_support,
    codes,
    collector_support,
    known_codes,
    known_collectors,
    register_code,
    register_collector,
)


@pytest.fixture(autouse=True)
def _isolated_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codes, "_codes", {})
    monkeypatch.setattr(codes, "_collectors", {})


def test_register_and_lookup_round_trip() -> None:
    register_code("demo_code", bridge="demo_pkg._bridge", bash_api="demo_pkg:httk-demo.sh")
    register_code("another", bridge="another_pkg")
    assert known_codes() == ("another", "demo_code")
    assert code_support("demo_code") == CodeSupport("demo_code", "demo_pkg._bridge", "demo_pkg:httk-demo.sh")
    assert code_support("another").bash_api_path() is None


def test_unknown_code_raises_key_error() -> None:
    with pytest.raises(KeyError, match="no code support registered"):
        code_support("missing")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "Vasp", "bridge": "pkg"},
        {"name": "1vasp", "bridge": "pkg"},
        {"name": "va-sp", "bridge": "pkg"},
        {"name": "vasp", "bridge": ""},
        {"name": "vasp", "bridge": "pkg:bridge"},
        {"name": "vasp", "bridge": "pkg..bridge"},
        {"name": "vasp", "bridge": "pkg", "bash_api": "pkg"},
        {"name": "vasp", "bridge": "pkg", "bash_api": "pkg:a:b.sh"},
        {"name": "vasp", "bridge": "pkg", "bash_api": ":a.sh"},
        {"name": "vasp", "bridge": "pkg", "bash_api": "pkg:"},
        {"name": "vasp", "bridge": "pkg", "bash_api": "pkg:sub/a.sh"},
        {"name": "vasp", "bridge": "pkg", "bash_api": "pkg:../a.sh"},
        {"name": "vasp", "bridge": "pkg", "bash_api": "pkg:.."},
    ],
)
def test_registration_validation(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        register_code(**kwargs)
    assert known_codes() == ()


def test_duplicate_registration() -> None:
    register_code("vasp", bridge="pkg._bridge", bash_api="pkg:a.sh")
    register_code("vasp", bridge="pkg._bridge", bash_api="pkg:a.sh")
    with pytest.raises(ValueError, match="different values"):
        register_code("vasp", bridge="pkg._bridge")
    assert code_support("vasp").bash_api == "pkg:a.sh"


def test_bridge_and_bash_api_resolve_lazily(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "httk_test_code_pkg"
    package.mkdir()
    package.joinpath("__init__.py").write_text("", encoding="utf-8")
    package.joinpath("_bridge.py").write_text("def run_command(namespace):\n    return 0\n", encoding="utf-8")
    package.joinpath("httk-demo.sh").write_text("# demo\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    register_code("demo", bridge="httk_test_code_pkg._bridge", bash_api="httk_test_code_pkg:httk-demo.sh")
    assert "httk_test_code_pkg._bridge" not in sys.modules
    support = code_support("demo")
    assert support.resolve_bridge().run_command(None) == 0
    path = support.bash_api_path()
    assert path is not None and path.is_file() and path.read_text(encoding="utf-8") == "# demo\n"

    register_code("broken", bridge="httk_test_code_pkg._bridge", bash_api="httk_test_code_pkg:absent.sh")
    with pytest.raises(FileNotFoundError):
        code_support("broken").bash_api_path()
    for module in ("httk_test_code_pkg", "httk_test_code_pkg._bridge"):
        sys.modules.pop(module, None)


def test_discovery_walks_codes_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "codes" / "test_discovery_codes"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        "from httk.core.register import register_code\nregister_code('discovered', bridge='not_imported._bridge')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(httk.registry, "__path__", [str(tmp_path), *httk.registry.__path__])
    try:
        discover_and_register()
        assert code_support("discovered").bridge == "not_imported._bridge"
        assert "not_imported" not in sys.modules
    finally:
        sys.modules.pop("httk.registry.codes.test_discovery_codes", None)


def test_collector_register_and_lookup() -> None:
    register_collector("vasp.calculation.relax", package="pkg:collectors/vasp-relax")
    register_collector("qe.calculation.pw", package="pkg2:c")
    assert known_collectors() == ("qe.calculation.pw", "vasp.calculation.relax")
    assert collector_support("qe.calculation.pw") == CollectorSupport("qe.calculation.pw", "pkg2:c")


def test_collector_duplicate_registration() -> None:
    register_collector("a.b", package="pkg:x")
    register_collector("a.b", package="pkg:x")
    with pytest.raises(ValueError, match="different values"):
        register_collector("a.b", package="pkg:y")


@pytest.mark.parametrize(
    ("name", "package"),
    [
        ("Bad", "pkg:x"),
        ("1a", "pkg:x"),
        ("a..b", "pkg:x"),
        ("a", "pkg"),
        ("a", "pkg:"),
        ("a", ":x"),
        ("a", "pkg:../x"),
        ("a", "pkg:x/../y"),
        ("a", "pkg:./x"),
        ("a", "pkg:x//y"),
        ("a", "pkg:/x"),
        ("a", "pkg:x/"),
    ],
)
def test_collector_validation(name: str, package: str) -> None:
    with pytest.raises(ValueError):
        register_collector(name, package=package)
    assert known_collectors() == ()


def test_unknown_collector_raises_key_error() -> None:
    register_collector("known.one", package="pkg:x")
    with pytest.raises(KeyError, match="known.one"):
        collector_support("missing")


def test_collector_path_does_not_import_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "pkgx"
    (package / "collectors" / "demo").mkdir(parents=True)
    package.joinpath("__init__.py").write_text('raise RuntimeError("imported")\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert CollectorSupport("demo", "pkgx:collectors/demo").path() == package / "collectors" / "demo"
    assert "pkgx" not in sys.modules


def test_collector_path_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pkgy").mkdir()
    (tmp_path / "pkgy" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        CollectorSupport("demo", "pkgy:nope").path()
    with pytest.raises(FileNotFoundError):
        CollectorSupport("demo", "no_such_pkg_zzz:x").path()
    with pytest.raises(FileNotFoundError):
        CollectorSupport("demo", "no_such_pkg_zzz.sub:x").path()
