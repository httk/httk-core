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

:func:`setup` registers two optional configuration values:
``httk_docs_dev_source`` (a string formatted with ``branch=`` that names the
source of a ``dev:main``/``dev:develop`` build in the development banner,
default ``"the GitHub {branch} branch"``) and ``httk_docs_collapse_navigation``
(default ``True``: Furo's sidebar shows the global toctree collapsed to the
current page's ancestors and children).
"""

import importlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from .config import VersioningConfig, load_versioning_config
from .inventories import InventoryError, fetch_inventory, read_inventory_header
from .lockfile import LockError, read_lock_pins
from .manifests import _DEV_BRANCHES
from .release import dependency_doc_targets
from .semver import parse_version

__all__ = [
    "channel_for_label",
    "derive_internal_intersphinx_mapping",
    "document_label",
    "selector_config_literal",
    "setup",
    "version_depth",
]

_DEV_LABELS = tuple(f"dev:{branch}" for branch in _DEV_BRANCHES)
_DEFAULT_DEV_SOURCE = "the GitHub {branch} branch"


def document_label(value: str | None) -> str:
    """Return a validated documentation label, defaulting to ``dev:local``.

    Development labels are exactly ``dev:local``, ``dev:main`` and
    ``dev:develop``; release labels are ``v``-prefixed version tags.

    :param value: Requested release or development label.
    :return: Validated documentation label.
    :raises ValueError: If *value* is not a supported label.
    """

    label = value or "dev:local"
    if label == "dev:local" or label in _DEV_LABELS:
        return label
    if len(label) > 1 and label.startswith("v"):
        from .semver import parse_tag

        parse_tag(label)
        return label
    allowed = ", ".join(("dev:local", *_DEV_LABELS))
    raise ValueError(f"invalid HTTK_DOCS_VERSION label: {label!r}; expected a release tag or one of {allowed}")


def channel_for_label(label: str) -> Literal["release", "dev"]:
    """Return ``release`` for a version tag and ``dev`` for a development label.

    :param label: Documentation label to classify.
    :return: Channel associated with the label.
    """

    return "release" if label.startswith("v") else "dev"


def version_depth(label: str) -> int:
    """Return the URL path depth used by the selector for *label*.

    :param label: Documentation label whose URL depth is needed.
    :return: Number of path components before a page URL.
    """

    if label.startswith("v"):
        return 1
    if label in _DEV_LABELS:
        return 2
    return 0


def _dev_branch(label: str) -> str:
    """Return the branch of a validated ``dev:main``/``dev:develop`` label."""

    return label.removeprefix("dev:")


def selector_config_literal(label: str) -> str:
    """Render the tiny JSON configuration literal consumed by ``selector.js``.

    :param label: Documentation label to encode.
    :return: JavaScript assignment containing selector configuration.
    :raises ValueError: If *label* is not a supported documentation label.
    """

    normalized = document_label(label)
    value = {
        "version": normalized,
        "channel": channel_for_label(normalized),
        "versionPathDepth": version_depth(normalized),
    }
    return "window.HTTK_DOCS_VERSIONING = " + json.dumps(value, separators=(",", ":"), sort_keys=True) + ";"


def derive_internal_intersphinx_mapping(
    mapping: Mapping[str, tuple[str, str | list[str]]],
    config: VersioningConfig,
    pins: Mapping[str, str],
    base_url: str,
    label: str,
    *,
    temporary_inventory_dir: str | Path | None = None,
    committed_inventory_dir: str | Path | None = None,
) -> dict[str, tuple[str, str | list[str]]]:
    """Return *mapping* with declared internal dependencies versioned.

    The function is deliberately side-effect free.  The Sphinx callback fetches
    the development inventories separately, then supplies their paths here.
    ``dev:local`` is handled by the callback before this function is called so
    that the configuration object remains byte-for-byte untouched for local
    builds.

    :param mapping: Existing intersphinx mappings to copy and update.
    :param config: Configuration declaring internal dependencies.
    :param pins: Locked dependency versions for release mappings.
    :param base_url: Base URL containing dependency documentation sites.
    :param label: Release or development documentation label.
    :param temporary_inventory_dir: Directory for fetched development inventories.
    :param committed_inventory_dir: Directory containing committed release inventories.
    :return: Mapping with internal dependency targets and inventories updated.
    :raises ReleaseError: If a release dependency has no valid locked version.
    :raises ValueError: If the label or development inventory directory is invalid.
    """

    normalized = document_label(label)
    if normalized == "dev:local":
        return dict(mapping)
    channel = channel_for_label(normalized)
    result = dict(mapping)
    if channel == "release":
        targets = dependency_doc_targets(config, pins, base_url, "release")
        inventory_dir = Path(committed_inventory_dir or "docs/_inventories").resolve()
        for dependency in config.internal_dependencies:
            result[dependency.slug] = (
                targets[dependency.distribution],
                str(inventory_dir / f"{dependency.slug}.inv"),
            )
        return result

    if temporary_inventory_dir is None:
        raise ValueError(f"temporary_inventory_dir is required for {normalized} intersphinx mappings")
    targets = dependency_doc_targets(config, pins, base_url, "dev", dev_branch=_dev_branch(normalized))
    temporary = Path(temporary_inventory_dir)
    for dependency in config.internal_dependencies:
        result[dependency.slug] = (
            targets[dependency.distribution],
            str(temporary / f"{dependency.slug}.inv"),
        )
    return result


def _project_versioning_paths(app: object) -> tuple[Path, Path, Path]:
    """Return repository root, docs directory, and versioning file.

    ``confdir`` is authoritative here: Sphinx permits the source directory to
    be separate from the directory containing ``conf.py`` (including ``-c``
    and ``docs/source`` layouts).
    """

    confdir = Path(app.confdir).resolve()  # type: ignore[attr-defined]
    candidates = (
        confdir / "versioning.toml",
        confdir.parent / "versioning.toml",
        confdir.parent / "docs" / "versioning.toml",
    )
    versioning_path = next((path for path in candidates if path.is_file()), candidates[0])
    docs_dir = versioning_path.parent
    return docs_dir.parent, docs_dir, versioning_path


def _normalized_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _validate_release_inventories(config: VersioningConfig, pins: Mapping[str, str], inventory_dir: Path) -> None:
    """Validate every committed internal inventory for the locked release."""

    dependency_doc_targets(config, pins, "https://docs.httk.org", "release")
    for dependency in config.internal_dependencies:
        key = _normalized_distribution(dependency.distribution)
        expected_version = str(parse_version(pins[key]))
        path = inventory_dir / f"{dependency.slug}.inv"
        if not path.is_file():
            raise InventoryError(
                f"committed inventory {path} is missing; expected project {dependency.slug!r} "
                f"and version {expected_version!r}"
            )
        try:
            found_project, found_version = read_inventory_header(path)
        except InventoryError as exc:
            raise InventoryError(f"committed inventory {path}: {exc}") from exc
        if found_project != dependency.slug or found_version != expected_version:
            raise InventoryError(
                f"committed inventory {path}: expected project {dependency.slug!r} and version "
                f"{expected_version!r}, found project {found_project!r} and version {found_version!r}"
            )


def _rewrite_internal_mappings(app: object, _config: object) -> None:
    """Apply channel-aware internal dependency mappings before intersphinx loads."""

    root, docs_dir, versioning_path = _project_versioning_paths(app)
    if not versioning_path.is_file():
        return
    config = load_versioning_config(versioning_path)
    if not config.internal_dependencies:
        return

    label = document_label(os.environ.get("HTTK_DOCS_VERSION"))
    if label == "dev:local":
        return

    pins: dict[str, str] = {}
    if channel_for_label(label) == "release":
        lock_path = root / "docs" / "requirements.lock"
        if not lock_path.is_file():
            raise LockError(f"documentation lock is missing: {lock_path}; required for release intersphinx mappings")
        try:
            pins = read_lock_pins(lock_path)
        except OSError as exc:
            raise LockError(f"cannot read documentation lock {lock_path}: {exc}") from exc
        _validate_release_inventories(config, pins, docs_dir / "_inventories")

    temporary_directory = None
    if label in _DEV_LABELS:
        branch = _dev_branch(label)
        temporary_directory = Path(app.doctreedir) / "__httk_internal_inventories"  # type: ignore[attr-defined]
        temporary_directory.mkdir(parents=True, exist_ok=True)
        base_url = os.environ.get("HTTK_DOCS_BASE_URL", "https://docs.httk.org")
        for dependency in config.internal_dependencies:
            destination = temporary_directory / f"{dependency.slug}.inv"
            inventory_url = f"{base_url.rstrip('/')}/{dependency.slug}/dev/{branch}/objects.inv"
            try:
                fetch_inventory(
                    inventory_url,
                    destination,
                    expected_project=dependency.slug,
                    expected_version=label,
                )
            except (InventoryError, OSError) as exc:
                raise RuntimeError(
                    f"failed to fetch {label} inventory for internal dependency {dependency.slug!r} "
                    f"from {inventory_url}: {exc}"
                ) from exc

    app.config.intersphinx_mapping = derive_internal_intersphinx_mapping(  # type: ignore[attr-defined]
        app.config.intersphinx_mapping,  # type: ignore[attr-defined]
        config,
        pins,
        os.environ.get("HTTK_DOCS_BASE_URL", "https://docs.httk.org"),
        label,
        temporary_inventory_dir=temporary_directory,
        committed_inventory_dir=docs_dir / "_inventories",
    )


def _development_announcement(label: str, source: str | None) -> str:
    """Return the Furo announcement text for a development *label*."""

    if label == "dev:local":
        return "Local development build (dev:local) — content may differ from any release."
    branch = _dev_branch(label)
    built_from = (source if source is not None else _DEFAULT_DEV_SOURCE).format(branch=branch)
    return f"Development documentation ({label}) — built from {built_from}; content may differ from any release."


def _collapse_furo_navigation(
    _app: object, _pagename: str, _templatename: str, context: dict[str, Any], _doctree: object
) -> None:
    """Replace Furo's full sidebar tree with one collapsed around the current page."""

    if "toctree" not in context:
        return
    try:
        navigation = importlib.import_module("furo.navigation")
    except ImportError:
        return
    toctree_html = context["toctree"](collapse=True, titles_only=True, maxdepth=-1, includehidden=True)
    context["furo_navigation_tree"] = navigation.get_navigation_tree(toctree_html)


def setup(app: object) -> dict[str, object]:
    """Register the extension with Sphinx and inject version-selector assets.

    :param app: Sphinx application receiving the extension callbacks and assets.
    :return: Sphinx extension metadata.
    """

    # This is the sanctioned optional edge: importing this module remains
    # possible in the stdlib-only lock and release tooling.
    from sphinx.application import (  # pyright: ignore[reportMissingImports]
        Sphinx,
    )

    del Sphinx
    app.add_config_value("httk_docs_dev_source", None, "html", types=(str, type(None)))  # type: ignore[attr-defined]
    app.add_config_value("httk_docs_collapse_navigation", True, "html", types=bool)  # type: ignore[attr-defined]
    # sphinx.ext.intersphinx validates its mapping at priority 800 and loads
    # inventories at builder-inited.  Rewrite at 700 so both phases see the
    # channel-aware values, including fetched development inventories.
    app.connect("config-inited", _rewrite_internal_mappings, priority=700)  # type: ignore[attr-defined]
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
            options["announcement"] = _development_announcement(
                label,
                app.config.httk_docs_dev_source,  # type: ignore[attr-defined]
            )
    if app.config.httk_docs_collapse_navigation and app.config.html_theme == "furo":  # type: ignore[attr-defined]
        # Furo computes its full navigation tree at the default priority 500.
        app.connect("html-page-context", _collapse_furo_navigation, priority=600)  # type: ignore[attr-defined]
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
