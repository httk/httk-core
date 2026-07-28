#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Sphinx glue for version labels, development warnings, and the selector UI.

The module itself has no Sphinx import dependency. Sphinx is imported only by
:func:`setup`, allowing the rest of the documentation library to remain
stdlib-only and usable by release workflows.
"""

import json
import os
from pathlib import Path
from typing import Literal

__all__ = [
    "channel_for_label",
    "document_label",
    "selector_config_literal",
    "setup",
    "version_depth",
]


def document_label(value: str | None) -> str:
    """Return a validated documentation label, defaulting to ``dev:local``."""

    label = value or "dev:local"
    if label == "dev:local" or label == "dev:main":
        return label
    if len(label) > 1 and label.startswith("v"):
        from .semver import parse_tag

        parse_tag(label)
        return label
    raise ValueError(f"invalid HTTK_DOCS_VERSION label: {label!r}")


def channel_for_label(label: str) -> Literal["release", "dev"]:
    """Return ``release`` for a version tag and ``dev`` for a development label."""

    return "release" if label.startswith("v") else "dev"


def version_depth(label: str) -> int:
    """Return the URL path depth used by the selector for *label*."""

    if label.startswith("v"):
        return 1
    if label == "dev:main":
        return 2
    return 0


def selector_config_literal(label: str) -> str:
    """Render the tiny JSON configuration literal consumed by ``selector.js``."""

    normalized = document_label(label)
    value = {
        "version": normalized,
        "channel": channel_for_label(normalized),
        "versionPathDepth": version_depth(normalized),
    }
    return "window.HTTK_DOCS_VERSIONING = " + json.dumps(value, separators=(",", ":"), sort_keys=True) + ";"


def setup(app: object) -> dict[str, object]:
    """Register the extension with Sphinx and inject version-selector assets."""

    # This is the sanctioned optional edge: importing this module remains
    # possible in the stdlib-only lock and release tooling.
    from sphinx.application import (  # noqa: F401  # pyright: ignore[reportMissingImports]
        Sphinx,
    )

    del Sphinx
    label = document_label(os.environ.get("HTTK_DOCS_VERSION"))
    channel = channel_for_label(label)
    if channel == "release":
        version = label[1:]
        release = version
    else:
        version = label
        release = label
    app.config.version = version  # type: ignore[attr-defined]
    app.config.release = release  # type: ignore[attr-defined]
    if channel == "dev" and app.config.html_theme == "furo":  # type: ignore[attr-defined]
        options = app.config.html_theme_options  # type: ignore[attr-defined]
        if options is None:
            options = {}
            app.config.html_theme_options = options  # type: ignore[attr-defined]
        if "announcement" not in options:
            options["announcement"] = f"Development documentation ({label}) — content may differ from any release."
    static_path = Path(__file__).resolve().parent / "assets"
    configured = app.config.html_static_path  # type: ignore[attr-defined]
    if configured is None:
        configured = []
        app.config.html_static_path = configured  # type: ignore[attr-defined]
    if str(static_path) not in configured:
        configured.append(str(static_path))
    app.add_js_file("selector.js")  # type: ignore[attr-defined]
    app.add_css_file("selector.css")  # type: ignore[attr-defined]
    app.add_js_file(None, body=selector_config_literal(label))  # type: ignore[attr-defined]
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}
