"""Tests for the EntryProvider contract and the provider registry."""

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any

import pytest

from httk.core import (
    EntryProvider,
    EntryTypeDefinition,
    PropertyDefinition,
    RelatedEntry,
    known_entry_providers,
    register_entry_provider,
)
from httk.core._plugins import resolve_callable
from httk.core.register import entry_providers


class ToyProvider(EntryProvider):
    """A minimal provider serving one ``widgets`` entry type."""

    def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
        return {
            "widgets": EntryTypeDefinition(
                "widgets",
                "A widgets entry.",
                {
                    "id": PropertyDefinition.from_simple("id", description="The widget id.", required_response=True),
                    "type": PropertyDefinition.from_simple(
                        "type", description="The entry type.", required_response=True
                    ),
                    "cogs": PropertyDefinition.from_simple("cogs", description="Number of cogs.", fulltype="integer"),
                },
            )
        }

    def property_keys(self, entry_type: str) -> Mapping[str, str]:
        return {"id": "__id", "type": "type", "cogs": "cogs"}

    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        return [
            {"__id": "w-1", "type": "widgets", "cogs": 3},
            {"__id": "w-2", "type": "widgets", "cogs": 5},
        ]


def make_toy_provider() -> ToyProvider:
    return ToyProvider()


def test_toy_provider_satisfies_contract() -> None:
    provider = ToyProvider()
    assert set(provider.entry_types()) == {"widgets"}
    property_keys = provider.property_keys("widgets")
    assert "id" in property_keys and "type" in property_keys
    records = list(provider.records("widgets"))
    assert {r["__id"] for r in records} == {"w-1", "w-2"}
    # Every record key is present in every record:
    for record in records:
        for key in property_keys.values():
            assert key in record


def test_stale_provider_defining_only_columns_cannot_be_instantiated() -> None:
    """A pre-rename provider (``columns`` instead of ``property_keys``) fails loudly."""

    class StaleProvider(EntryProvider):
        def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
            return {}

        def columns(self, entry_type: str) -> Mapping[str, str]:  # the pre-rename name
            return {"id": "id", "type": "type"}

        def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
            return []

    with pytest.raises(TypeError, match="property_keys"):
        StaleProvider()  # type: ignore[abstract]


def test_default_relationships_is_empty() -> None:
    assert ToyProvider().relationships("widgets") == {}


def test_related_entry_defaults_and_equality() -> None:
    entry = RelatedEntry("references", "ref-1")
    assert entry.entry_type == "references"
    assert entry.id == "ref-1"
    assert entry.description is None
    assert entry.role is None
    assert entry == RelatedEntry("references", "ref-1")
    assert entry != RelatedEntry("references", "ref-2")
    with_meta = RelatedEntry("files", "f-1", description="Input file", role="input")
    assert with_meta == RelatedEntry("files", "f-1", description="Input file", role="input")
    assert with_meta != entry


def test_related_entry_is_frozen_with_slots() -> None:
    entry = RelatedEntry("references", "ref-1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.id = "ref-2"  # type: ignore[misc]
    assert not hasattr(entry, "__dict__")  # slots


def test_registration_and_factory_resolution_round_trip() -> None:
    register_entry_provider(name="toy-widgets", factory="test_entry_provider:make_toy_provider")
    try:
        assert "toy-widgets" in known_entry_providers()
        factory = resolve_callable(entry_providers.require("toy-widgets").handler)
        provider = factory()
        assert isinstance(provider, EntryProvider)
        assert set(provider.entry_types()) == {"widgets"}
    finally:
        entry_providers._by_key.pop("toy-widgets", None)
