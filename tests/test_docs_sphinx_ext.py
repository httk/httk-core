from pathlib import Path
import zlib

import pytest

from httk.core.docs.config import InternalDependency, VersioningConfig
from httk.core.docs.release import ReleaseError
from httk.core.docs.sphinx_ext import (
    channel_for_label,
    derive_internal_intersphinx_mapping,
    document_label,
    selector_config_literal,
    version_depth,
)


def test_sphinx_helpers() -> None:
    assert document_label(None) == "dev:local"
    assert channel_for_label("v2.0.2") == "release"
    assert channel_for_label("dev:main") == "dev"
    assert version_depth("v2.0.2") == 1
    assert version_depth("dev:main") == 2
    assert version_depth("dev:local") == 0
    assert '"versionPathDepth":1' in selector_config_literal("v2.0.2")
    with pytest.raises(ValueError):
        document_label("v1.2")


def test_internal_mapping_derivation_is_channel_aware(tmp_path: Path) -> None:
    config = VersioningConfig(
        "consumer",
        "https://example.test/consumer",
        internal_dependencies=(InternalDependency("httk-core", "httk-core", "https://example.test/core"),),
    )
    mapping = {
        "python": ("https://docs.python.org/3", "_inventories/python.inv"),
        "httk-core": ("https://docs.httk.org/httk-core/", "_inventories/httk-core.inv"),
    }
    assert derive_internal_intersphinx_mapping(
        mapping,
        config,
        {"httk-core": "2.0.2"},
        "https://docs.httk.org",
        "v2.1.0",
        committed_inventory_dir=tmp_path / "inventories",
    ) == {
        "python": ("https://docs.python.org/3", "_inventories/python.inv"),
        "httk-core": (
            "https://docs.httk.org/httk-core/v2.0.2/",
            str((tmp_path / "inventories" / "httk-core.inv").resolve()),
        ),
    }
    assert derive_internal_intersphinx_mapping(
        mapping, config, {}, "https://docs.httk.org", "dev:main", temporary_inventory_dir="/tmp/inventories"
    )["httk-core"] == (
        "https://docs.httk.org/httk-core/dev/main/",
        "/tmp/inventories/httk-core.inv",
    )
    assert derive_internal_intersphinx_mapping(
        mapping, config, {}, "https://docs.httk.org", "dev:local"
    ) == mapping
    with pytest.raises(ReleaseError, match="httk-core.*requirements.lock"):
        derive_internal_intersphinx_mapping(mapping, config, {}, "https://docs.httk.org", "v2.1.0")


def test_internal_mapping_injects_missing_internal_entries_and_preserves_external() -> None:
    config = VersioningConfig(
        "consumer",
        "https://example.test/consumer",
        internal_dependencies=(InternalDependency("httk-core", "httk-core", "https://example.test/core"),),
    )
    mapping = {"python": ("file:///python", "python.inv")}
    result = derive_internal_intersphinx_mapping(
        mapping, config, {}, "https://docs.httk.org", "dev:main", temporary_inventory_dir="/tmp"
    )
    assert result["python"] == mapping["python"]
    assert result["httk-core"] == (
        "https://docs.httk.org/httk-core/dev/main/",
        "/tmp/httk-core.inv",
    )


def test_sphinx_build_injects_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sphinx = pytest.importorskip("sphinx")
    del sphinx
    source = tmp_path / "source"
    source.mkdir()
    (source / "conf.py").write_text(
        "extensions = ['httk.core.docs.sphinx_ext']\nproject = 'test'\nhtml_theme = 'furo'\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    output = tmp_path / "_build"
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:main")
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(source), str(output), str(tmp_path / "doctrees"), "html", freshenv=True)
    app.build(force_all=True)
    assert app.config.version == "dev:main"
    assert app.config.release == "dev:main"
    assert "Development documentation (dev:main)" in app.config.html_theme_options["announcement"]
    assert (output / "_static" / "selector.js").is_file()
    assert "HTTK_DOCS_VERSIONING" in (output / "index.html").read_text(encoding="utf-8")


def test_sphinx_build_dev_local_keeps_internal_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "docs"
    source.mkdir()
    (source / "_inventories").mkdir()
    (source / "_inventories" / "httk-core.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: dev:main\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (tmp_path / "docs" / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (source / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {'httk-core': ('https://docs.httk.org/httk-core/', '_inventories/httk-core.inv')}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:local")
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)
    assert app.config.intersphinx_mapping["httk-core"][1] == (
        "https://docs.httk.org/httk-core/",
        ("_inventories/httk-core.inv",),
    )
    app.build(force_all=True)


def test_sphinx_build_release_rewrites_internal_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "docs"
    source.mkdir()
    (source / "_inventories").mkdir()
    (source / "_inventories" / "httk-core.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 2.0.2\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (source / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (source / "requirements.lock").write_text("httk-core==2.0.2\n", encoding="utf-8")
    (source / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {'httk-core': ('https://old', 'old.inv')}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "v2.1.0")
    monkeypatch.setenv("HTTK_DOCS_BASE_URL", "file:///docs")
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)
    assert app.config.intersphinx_mapping["httk-core"][1] == (
        "file:///docs/httk-core/v2.0.2/",
        (str((source / "_inventories" / "httk-core.inv").resolve()),),
    )
    app.build(force_all=True)


def test_sphinx_release_rejects_mismatched_committed_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "docs"
    (source / "_inventories").mkdir(parents=True)
    (source / "_inventories" / "httk-core.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 9.9.9\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (source / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n', encoding="utf-8"
    )
    (source / "requirements.lock").write_text("httk-core==2.0.2\n", encoding="utf-8")
    (source / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "v2.1.0")
    from sphinx.application import Sphinx

    with pytest.raises(Exception, match="expected project.*2.0.2"):
        Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)


def test_sphinx_out_of_tree_source_uses_confdir_and_absolute_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    repo = tmp_path / "repo"
    confdir = repo / "docs"
    source = repo / "source"
    (confdir / "_inventories").mkdir(parents=True)
    source.mkdir(parents=True)
    (confdir / "_inventories" / "httk-core.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 2.0.2\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (confdir / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n', encoding="utf-8"
    )
    (confdir / "requirements.lock").write_text("httk-core==2.0.2\n", encoding="utf-8")
    (confdir / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "v2.1.0")
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(confdir), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)
    assert app.config.intersphinx_mapping["httk-core"][1] == (
        "https://docs.httk.org/httk-core/v2.0.2/",
        (str((confdir / "_inventories" / "httk-core.inv").resolve()),),
    )


def test_sphinx_build_dev_main_fetches_temporary_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "docs"
    source.mkdir()
    fixture = tmp_path / "published" / "httk-core" / "dev" / "main"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: dev:main\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (source / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n', encoding="utf-8"
    )
    (source / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {'httk-core': ('https://old', 'old.inv')}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:main")
    monkeypatch.setenv("HTTK_DOCS_BASE_URL", (tmp_path / "published").as_uri())
    from sphinx.application import Sphinx

    doctrees = tmp_path / "doctrees"
    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(doctrees), "html", freshenv=True)
    assert app.config.intersphinx_mapping["httk-core"][1] == (
        f"{(tmp_path / 'published').as_uri()}/httk-core/dev/main/",
        (str(doctrees / "__httk_internal_inventories" / "httk-core.inv"),),
    )
    app.build(force_all=True)
    assert (doctrees / "__httk_internal_inventories" / "httk-core.inv").is_file()


def test_sphinx_dev_main_rejects_wrong_inventory_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "docs"
    source.mkdir()
    fixture = tmp_path / "published" / "httk-core" / "dev" / "main"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: 2.0.2\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (source / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n', encoding="utf-8"
    )
    (source / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:main")
    monkeypatch.setenv("HTTK_DOCS_BASE_URL", (tmp_path / "published").as_uri())
    from sphinx.application import Sphinx

    with pytest.raises(Exception, match="expected version 'dev:main'"):
        Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)


def test_sphinx_release_preserves_configured_announcement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "source"
    source.mkdir()
    (source / "conf.py").write_text(
        "extensions = ['httk.core.docs.sphinx_ext']\nproject = 'test'\nhtml_theme = 'furo'\n"
        "html_theme_options = {'announcement': 'Custom announcement'}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "v2.1.0")
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)
    app.build(force_all=True)
    assert app.config.version == "2.1.0"
    assert app.config.release == "2.1.0"
    assert app.config.html_theme_options["announcement"] == "Custom announcement"


def test_sphinx_non_furo_dev_does_not_add_announcement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "source"
    source.mkdir()
    (source / "conf.py").write_text(
        "extensions = ['httk.core.docs.sphinx_ext']\nproject = 'test'\nhtml_theme = 'alabaster'\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:main")
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)
    app.build(force_all=True)
    assert "announcement" not in app.config.html_theme_options


@pytest.mark.parametrize("label", ["dev:", "dev:Main", "dev:feature", "dev:a/b", "dev:main/", "dev"])
def test_unsupported_development_labels_are_rejected(label: str) -> None:
    with pytest.raises(ValueError, match="invalid HTTK_DOCS_VERSION label.*dev:local, dev:main, dev:develop"):
        document_label(label)


def test_dev_develop_label_helpers_and_mapping() -> None:
    assert document_label("dev:develop") == "dev:develop"
    assert channel_for_label("dev:develop") == "dev"
    assert version_depth("dev:develop") == 2
    assert '"version":"dev:develop"' in selector_config_literal("dev:develop")
    assert '"versionPathDepth":2' in selector_config_literal("dev:develop")
    config = VersioningConfig(
        "consumer",
        "https://example.test/consumer",
        internal_dependencies=(InternalDependency("httk-core", "httk-core", "https://example.test/core"),),
    )
    assert derive_internal_intersphinx_mapping(
        {}, config, {}, "https://docs.httk.org", "dev:develop", temporary_inventory_dir="/tmp/inventories"
    ) == {"httk-core": ("https://docs.httk.org/httk-core/dev/develop/", "/tmp/inventories/httk-core.inv")}
    with pytest.raises(ValueError, match="temporary_inventory_dir is required for dev:develop"):
        derive_internal_intersphinx_mapping({}, config, {}, "https://docs.httk.org", "dev:develop")


def _write_dev_consumer(tmp_path: Path, published_version: bytes) -> Path:
    source = tmp_path / "docs"
    source.mkdir()
    fixture = tmp_path / "published" / "httk-core" / "dev" / "develop"
    fixture.mkdir(parents=True)
    (fixture / "objects.inv").write_bytes(
        b"# Sphinx inventory version 2\n# Project: httk-core\n# Version: " + published_version + b"\n"
        b"# The remainder of this file is compressed using zlib.\n" + zlib.compress(b"")
    )
    (source / "versioning.toml").write_text(
        '[site]\nslug = "consumer"\nrepository-url = "https://example.test/consumer"\n'
        '\n[[internal-dependency]]\ndistribution = "httk-core"\nslug = "httk-core"\n'
        'repository-url = "https://example.test/core"\n',
        encoding="utf-8",
    )
    (source / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx', 'httk.core.docs.sphinx_ext']\nproject = 'consumer'\n"
        "intersphinx_mapping = {'httk-core': ('https://old', 'old.inv')}\n",
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    return source


def test_sphinx_build_dev_develop_fetches_temporary_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = _write_dev_consumer(tmp_path, b"dev:develop")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:develop")
    monkeypatch.setenv("HTTK_DOCS_BASE_URL", (tmp_path / "published").as_uri())
    from sphinx.application import Sphinx

    doctrees = tmp_path / "doctrees"
    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(doctrees), "html", freshenv=True)
    assert app.config.intersphinx_mapping["httk-core"][1] == (
        f"{(tmp_path / 'published').as_uri()}/httk-core/dev/develop/",
        (str(doctrees / "__httk_internal_inventories" / "httk-core.inv"),),
    )
    app.build(force_all=True)
    assert (doctrees / "__httk_internal_inventories" / "httk-core.inv").is_file()


def test_sphinx_dev_develop_rejects_dev_main_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sphinx")
    source = _write_dev_consumer(tmp_path, b"dev:main")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:develop")
    monkeypatch.setenv("HTTK_DOCS_BASE_URL", (tmp_path / "published").as_uri())
    from sphinx.application import Sphinx

    with pytest.raises(Exception, match="failed to fetch dev:develop inventory.*expected version 'dev:develop'"):
        Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)


@pytest.mark.parametrize(
    ("label", "extra_conf", "expected"),
    [
        (
            "dev:main",
            "",
            (
                "Development documentation (dev:main) — built from the GitHub main branch; "
                "content may differ from any release."
            ),
        ),
        (
            "dev:develop",
            "",
            (
                "Development documentation (dev:develop) — built from the GitHub develop branch; "
                "content may differ from any release."
            ),
        ),
        ("dev:local", "", "Local development build (dev:local) — content may differ from any release."),
        (
            "dev:develop",
            "httk_docs_dev_source = \"this site's GitHub main branch and its modules' GitHub {branch} branches\"\n",
            (
                "Development documentation (dev:develop) — built from this site's GitHub main branch and its "
                "modules' GitHub develop branches; content may differ from any release."
            ),
        ),
    ],
)
def test_sphinx_development_banner_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str, extra_conf: str, expected: str
) -> None:
    pytest.importorskip("sphinx")
    source = tmp_path / "source"
    source.mkdir()
    (source / "conf.py").write_text(
        "extensions = ['httk.core.docs.sphinx_ext']\nproject = 'test'\nhtml_theme = 'furo'\n" + extra_conf,
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Test\n====\n\nHello.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", label)
    from sphinx.application import Sphinx

    app = Sphinx(str(source), str(source), str(tmp_path / "_build"), str(tmp_path / "doctrees"), "html", freshenv=True)
    assert app.config.html_theme_options["announcement"] == expected


def _sidebar(html: str) -> str:
    start = html.index('<div class="sidebar-tree">')
    return html[start : html.index("</aside>", start)]


@pytest.mark.parametrize(
    ("extra_conf", "overrides", "collapsed"),
    [
        ("", {}, True),
        ("httk_docs_collapse_navigation = False\n", {}, False),
        ("", {"httk_docs_collapse_navigation": "0"}, False),
    ],
)
def test_sphinx_furo_navigation_is_collapsed_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra_conf: str, overrides: dict[str, str], collapsed: bool
) -> None:
    pytest.importorskip("sphinx")
    pytest.importorskip("furo")
    source = tmp_path / "source"
    for section in ("alpha", "beta"):
        (source / section).mkdir(parents=True)
    (source / "conf.py").write_text(
        "extensions = ['httk.core.docs.sphinx_ext']\nproject = 'test'\nhtml_theme = 'furo'\n" + extra_conf,
        encoding="utf-8",
    )
    (source / "index.rst").write_text("Home\n====\n\n.. toctree::\n\n   alpha/index\n   beta/index\n", encoding="utf-8")
    (source / "alpha" / "index.rst").write_text("Alpha\n=====\n\n.. toctree::\n\n   one\n   two\n", encoding="utf-8")
    (source / "alpha" / "one.rst").write_text("Alpha one\n=========\n\nText.\n", encoding="utf-8")
    (source / "alpha" / "two.rst").write_text("Alpha two\n=========\n\nText.\n", encoding="utf-8")
    (source / "beta" / "index.rst").write_text("Beta\n====\n\n.. toctree::\n\n   three\n", encoding="utf-8")
    (source / "beta" / "three.rst").write_text("Beta three\n==========\n\nText.\n", encoding="utf-8")
    monkeypatch.setenv("HTTK_DOCS_VERSION", "dev:local")
    from sphinx.application import Sphinx

    output = tmp_path / "_build"
    app = Sphinx(
        str(source),
        str(source),
        str(output),
        str(tmp_path / "doctrees"),
        "html",
        confoverrides=overrides,
        freshenv=True,
    )
    app.build(force_all=True)
    sidebar = _sidebar((output / "alpha" / "one.html").read_text(encoding="utf-8"))
    assert 'href="../beta/index.html"' in sidebar
    assert 'class="toctree-l2 current current-page"><a class="current reference internal" href="#">Alpha one' in sidebar
    assert 'href="two.html"' in sidebar
    assert ('href="../beta/three.html"' in sidebar) is not collapsed
    home = _sidebar((output / "index.html").read_text(encoding="utf-8"))
    assert 'href="alpha/index.html"' in home and 'href="beta/index.html"' in home
    assert ('href="alpha/one.html"' in home) is not collapsed
