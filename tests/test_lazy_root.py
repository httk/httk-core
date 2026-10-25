"""The ``httk.core`` and ``httk.core.register`` roots re-export lazily, keeping every ``httk`` command start cheap."""

import ast
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import httk.core
import httk.core.register

_SRC = str(Path(httk.core.__file__).resolve().parents[2])
_PACKAGES = (httk.core, httk.core.register)


def _run(code: str, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, *args, *(["-c", code] if code else [])],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": _SRC},
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    ("package", "name"),
    # The register root also re-exports private names that tests and sibling modules import.
    [(package, name) for package in _PACKAGES for name in sorted({*package.__all__, *vars(package)["_LAZY_EXPORTS"]})],
)
def test_every_root_export_resolves(package: ModuleType, name: str) -> None:
    # ``__import__`` with a fromlist is what ``from <package> import <name>`` executes.
    imported = getattr(__import__(package.__name__, fromlist=[name]), name)
    assert imported is getattr(package, name)
    assert name in dir(package)


@pytest.mark.parametrize("package", _PACKAGES)
def test_unknown_root_attribute_raises(package: ModuleType) -> None:
    with pytest.raises(AttributeError, match="no_such_name"):
        _ = package.no_such_name


@pytest.mark.parametrize("package", _PACKAGES)
def test_stub_mirrors_the_lazy_root(package: ModuleType) -> None:
    # The stub is the static view (type checkers, API reference); the runtime map must say the same.
    stub = ast.parse(Path(package.__file__ or "").with_suffix(".pyi").read_text(encoding="utf-8"))
    imported = {
        alias.name: node.module
        for node in stub.body
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
        for alias in node.names
    }
    assert imported == vars(package)["_LAZY_EXPORTS"]  # private: not part of the stub
    modules = {
        alias.name
        for node in stub.body
        if isinstance(node, ast.ImportFrom) and node.level == 1 and not node.module
        for alias in node.names
    }
    assert modules == vars(package).get("_LAZY_MODULES", set())
    (stub_all,) = (
        node.value
        for node in stub.body
        if isinstance(node, ast.Assign) and [ast.unparse(target) for target in node.targets] == ["__all__"]
    )
    assert ast.literal_eval(stub_all) == package.__all__
    assert ast.get_docstring(stub, clean=False) == package.__doc__


_FORBIDDEN = (
    "numpy",
    "httk.core.vectors",
    "httk.core.exactmath",
    "httk.core.datastream",
    "httk.core.optimade",
    "httk.core.fetching",
    "httk.core.loading",
    "httk.core.data_records",
    "importlib.metadata",
)


def test_cli_import_stays_lean() -> None:
    probe = (
        "import sys, httk.core.cli; "
        "from httk.core.register.cli import known_cli_commands; "
        f"print(sorted(m for m in {_FORBIDDEN!r} if m in sys.modules), "
        "'httk.core.register.cli' in sys.modules, bool(known_cli_commands()))"
    )
    # Discovery ran (CLI commands registered) without pulling the public surface or numpy.
    assert _run(probe) == "[] True True"


@pytest.mark.parametrize(
    "code",
    [
        "import httk.core.vectors as v; assert v.FracVector([1, 2]) + 1 == v.FracVector([2, 3])",
        (
            "import httk.core.exactmath as e; from httk.core.vectors import FracVector; "
            "assert e.sqrt(FracVector([1, 4])) == FracVector([1, 2])"
        ),
        "from httk.core import exactmath; assert exactmath.sqrt(4) == 2",
        "from httk.core import FracVector; assert FracVector([1, 2]) + 1 == FracVector([2, 3])",
    ],
)
def test_exactmath_vectors_cycle_in_every_import_order(code: str) -> None:
    _run(code)


def test_cli_version_reads_metadata_lazily() -> None:
    assert re.fullmatch(r"\S+ \S*\d\S*", _run("", "-m", "httk.core.cli", "--version"))


def test_exactmath_is_a_lazy_root_attribute() -> None:
    probe = (
        "import sys, httk.core; loaded = 'httk.core.exactmath' in sys.modules; "
        "listed = 'exactmath' in dir(httk.core); "
        "print(loaded, listed, httk.core.exactmath is sys.modules['httk.core.exactmath'])"
    )
    assert _run(probe) == "False True True"


def test_builtin_coercers_resolve_from_the_lazy_root() -> None:
    probe = (
        "from decimal import Decimal; from fractions import Fraction; "
        "from httk.core import coerce, coerce_view; "
        "assert coerce(Fraction(1, 2), float) == 0.5; "
        "assert coerce(0.5, Fraction) == Fraction(1, 2); "
        "assert coerce(3, Decimal) == Decimal(3); "
        "print(type(coerce_view([1, 2], tuple)).__name__, tuple(coerce_view([1, 2], tuple)))"
    )
    assert _run(probe) == "VectorNativeView (1, 2)"
