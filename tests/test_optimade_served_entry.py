"""Tests for building typed entries from served-form attributes."""

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from types import ModuleType
from typing import Any, cast

import pytest

from httk.core import EntryTypeDefinition, PropertyDefinition
from httk.core.optimade import FileView, OptimadeFile, OptimadeResource, served_entry
from httk.core.register import register_entry_family, register_optimade_entry_binding
from httk.core.register.entries import _entry_families, _optimade_entry_bindings

_MODULE = "httk_test_served_entry_module"
_WIDGETS = "https://schemas.example.test/v1/widgets.json"


@dataclass(frozen=True)
class _Backend:
    resource: OptimadeResource


@dataclass(frozen=True)
class _View:
    backend: _Backend


class _WidgetEntry:
    type = "widgets"

    @classmethod
    def entry_type_definition(cls) -> EntryTypeDefinition:
        count = PropertyDefinition.from_simple("_httk_custom_count", description="Count.", fulltype="integer")
        # Shaped like an extended definition: no own IRI, the binding's IRI as extends_id.
        return EntryTypeDefinition("widgets", "Widgets.", {"_httk_custom_count": count}, extends_id=_WIDGETS)


@pytest.fixture
def widgets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    module = ModuleType(_MODULE)
    cast(Any, module).Backend = _Backend
    cast(Any, module).View = _View
    cast(Any, module).WidgetEntry = _WidgetEntry
    monkeypatch.setitem(sys.modules, _MODULE, module)
    register_optimade_entry_binding(
        name="test-widgets", definition_id=_WIDGETS, backend=f"{_MODULE}:Backend", view=f"{_MODULE}:View"
    )
    register_entry_family(name="widgets", family=f"{_MODULE}:WidgetEntry", definition_id=_WIDGETS)
    try:
        yield
    finally:
        _entry_families.pop("widgets", None)
        _optimade_entry_bindings.pop(_WIDGETS, None)


def test_served_entry_builds_synthetic_resource_through_family_binding(widgets: None) -> None:
    view = served_entry("widgets", {"_httk_custom_count": 3}, entry_id="w1")

    assert isinstance(view, _View)
    resource = view.backend.resource
    assert (resource["id"], resource["type"]) == ("w1", "widgets")
    assert resource["attributes"] == {"_httk_custom_count": 3}
    assert resource.schema.entry_type == "widgets"
    info = json.loads(resource.schema.info_document.text)
    assert info == {
        "meta": {"api_version": "1.3.0"},
        "data": {
            "properties": {
                "_httk_custom_count": {"$id": "https://schemas.httk.org/ad-hoc/defs/properties/_httk_custom_count"}
            }
        },
    }


def test_served_entry_rejects_unknown_unbound_and_unserializable_input(widgets: None) -> None:
    with pytest.raises(ValueError, match="no entry family with an OPTIMADE binding"):
        served_entry("gadgets", {})
    with pytest.raises(ValueError, match="No entry-type definition registered"):
        served_entry("widgets", {}, definition="https://schemas.example.test/entrytypes/unknown")
    with pytest.raises(ValueError, match="no OPTIMADE entry binding is registered"):
        served_entry("widgets", {}, definition=EntryTypeDefinition("widgets", "Widgets.", {}))
    with pytest.raises(ValueError, match="must be JSON-serializable"):
        served_entry("widgets", {"_httk_custom_count": object()})


def test_served_entry_uses_core_files_binding() -> None:
    view = served_entry("files", {"url": "https://example.org/a.txt", "name": "a.txt"})

    assert isinstance(view, FileView)
    assert isinstance(view.backend, OptimadeFile)
    assert (view.url, view.name) == ("https://example.org/a.txt", "a.txt")
