from pathlib import Path

import pytest

from httk.core.docs.config import ConfigError, load_versioning_config


def test_load_versioning_config(tmp_path: Path) -> None:
    path = tmp_path / "versioning.toml"
    path.write_text(
        '[site]\nslug = "httk-atomistic"\nrepository-url = "https://github.com/httk/httk-atomistic"\n'
        'main-branch = "trunk"\nimport-roots = ["httk/atomistic"]\n\n'
        '[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://github.com/httk/httk-core"\nmain-branch = "stable"\n',
        encoding="utf-8",
    )
    config = load_versioning_config(path)
    assert config.main_branch == "trunk"
    assert config.import_roots == ("httk/atomistic",)
    assert config.internal_dependencies[0].distribution == "httk-core"
    assert config.internal_dependencies[0].main_branch == "stable"


def test_config_unknown_key_names_file_and_key(tmp_path: Path) -> None:
    path = tmp_path / "versioning.toml"
    path.write_text('[site]\nslug = ""\nrepository-url = "https://example.test"\nslgu = "typo"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"versioning\.toml: site\.slgu: unknown key"):
        load_versioning_config(path)


def test_config_accepts_empty_top_site_slug(tmp_path: Path) -> None:
    path = tmp_path / "versioning.toml"
    path.write_text('[site]\nslug = ""\nrepository-url = "https://docs.example.test"\n', encoding="utf-8")
    assert load_versioning_config(path).slug == ""


def test_config_rejects_empty_internal_dependency_slug(tmp_path: Path) -> None:
    path = tmp_path / "versioning.toml"
    path.write_text(
        '[site]\nslug = "site"\nrepository-url = "https://example.test"\n'
        '[[internal-dependency]]\ndistribution = "httk-core"\nslug = ""\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"internal-dependency\[0\]\.slug: must be a non-empty string"):
        load_versioning_config(path)


def test_config_missing_key_names_file_and_key(tmp_path: Path) -> None:
    path = tmp_path / "versioning.toml"
    path.write_text("[site]\nslug = \"x\"\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"versioning\.toml: site\.repository-url: is required"):
        load_versioning_config(path)


def test_config_unknown_dependency_key_names_file_and_key(tmp_path: Path) -> None:
    path = tmp_path / "versioning.toml"
    path.write_text(
        '[site]\nslug = "x"\nrepository-url = "https://example.test"\n'
        '[[internal-dependency]]\ndistribution = "httk-core"\nslug = "core"\n'
        'repository-url = "https://example.test/core"\nmain-brnch = "typo"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"versioning\.toml: internal-dependency\[0\]\.main-brnch: unknown key"):
        load_versioning_config(path)
