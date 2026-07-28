from pathlib import Path

import pytest

from httk.core.docs.sphinx_ext import channel_for_label, document_label, selector_config_literal, version_depth


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
