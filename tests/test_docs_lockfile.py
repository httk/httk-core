from pathlib import Path

import pytest

from httk.core.docs.lockfile import (
    LockError,
    check_lock,
    compute_input_hash,
    filter_lock_pins,
    generate_lock,
    internal_pins,
    read_lock_pins,
)


PYPROJECT = '''[project]
requires-python = ">=3.12"
dependencies = ["requests>=2"]
[project.optional-dependencies]
docs = ["sphinx"]
'''


def test_input_hash_ignores_toml_formatting(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT, encoding="utf-8")
    first = compute_input_hash(path)
    path.write_text(
        '[project]\ndependencies=["requests>=2"]\nrequires-python=">=3.12"\n'
        '[project.optional-dependencies]\ndocs=["sphinx"]\n',
        encoding="utf-8",
    )
    assert compute_input_hash(path) == first
    path.write_text(
        '[project]\ndependencies=["requests>=2"]\nrequires-python=">=3.12"\n'
        '[project.optional-dependencies]\ndocs=["sphinx"]\n',
        encoding="utf-8",
    )
    path.write_text(PYPROJECT.replace('dependencies = ["requests>=2"]', 'dependencies = ["requests>=2", "furo"]').replace('docs = ["sphinx"]', 'docs = ["sphinx", "myst-parser"]'), encoding="utf-8")
    reordered = compute_input_hash(path)
    path.write_text(PYPROJECT.replace('dependencies = ["requests>=2"]', 'dependencies = ["furo", "requests>=2"]').replace('docs = ["sphinx"]', 'docs = ["myst-parser", "sphinx"]'), encoding="utf-8")
    assert compute_input_hash(path) == reordered


def test_generate_check_and_filter_with_stub(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    stub = tmp_path / "uv-stub"
    stub.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'Sphinx==8.0' 'httk-core==2.0.2' 'requests==2.32' > \"${12}\"\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    lock = tmp_path / "docs" / "requirements.lock"
    generate_lock(tmp_path, lock, command_prefix=[str(stub)])
    assert read_lock_pins(lock) == {"httk-core": "2.0.2", "requests": "2.32", "sphinx": "8.0"}
    check_lock(tmp_path, lock)
    assert internal_pins(read_lock_pins(lock)) == {"httk-core": "2.0.2"}
    assert filter_lock_pins(read_lock_pins(lock), drop=["requests"]) == {"sphinx": "8.0"}
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.replace("sphinx", "furo"), encoding="utf-8")
    with pytest.raises(LockError, match="regenerate with make docs-lock"):
        check_lock(tmp_path, lock)


def test_generate_rejects_unrecognized_resolver_lines(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    stub = tmp_path / "uv-stub"
    stub.write_text("#!/bin/sh\nprintf '%s\\n' 'not-a-pin' > \"${12}\"\n", encoding="utf-8")
    stub.chmod(0o755)
    with pytest.raises(LockError, match="unrecognized lock line"):
        generate_lock(tmp_path, tmp_path / "requirements.lock", command_prefix=[str(stub)])


def test_missing_lock_is_clear(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    with pytest.raises(LockError, match="lock file missing"):
        check_lock(tmp_path, tmp_path / "requirements.lock")


def test_schema_header_is_required(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    digest = compute_input_hash(pyproject)
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"# input-hash: sha256:{digest}\n", encoding="utf-8")
    with pytest.raises(LockError, match="schema header missing"):
        check_lock(tmp_path, lock)


def test_filter_normalizes_mapping_keys() -> None:
    pins = {"HTTK_Core": "2.0.2", "Requests": "2.32"}
    assert filter_lock_pins(pins, drop=[]) == {"requests": "2.32"}
    assert internal_pins(pins) == {"httk-core": "2.0.2"}


def test_duplicate_and_empty_pins_fail(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    digest = compute_input_hash(pyproject)
    headers = f"# httk-docs-lock-schema: 1\n# input-hash: sha256:{digest}\n# python: 3.12\n# platform: linux\n"
    duplicate = tmp_path / "duplicate.lock"
    duplicate.write_text(headers + "Foo-Bar==1\nfoo_bar==2\n", encoding="utf-8")
    with pytest.raises(LockError, match="duplicate"):
        check_lock(tmp_path, duplicate)
    empty = tmp_path / "empty.lock"
    empty.write_text(headers, encoding="utf-8")
    with pytest.raises(LockError, match="no pins"):
        check_lock(tmp_path, empty)


def test_header_values_are_strict(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    digest = compute_input_hash(pyproject)
    for expected, python_header, platform_header in (
        ("python header", "# python: 3.11", "# platform: linux"),
        ("platform header", "# python: 3.12", "# platform: win32"),
    ):
        lock = tmp_path / f"{expected.replace(' ', '-')}.lock"
        lock.write_text(
            f"# httk-docs-lock-schema: 1\n# input-hash: sha256:{digest}\n{python_header}\n{platform_header}\nrequests==2\n",
            encoding="utf-8",
        )
        with pytest.raises(LockError, match=expected):
            check_lock(tmp_path, lock)
