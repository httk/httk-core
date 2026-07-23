"""Tests for the EntryProvider contract and the provider registry."""

from collections.abc import Iterable, Mapping
from typing import Any

from httk.core import (
    EntryProvider,
    EntryTypeDefinition,
    PropertyDefinition,
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

    def columns(self, entry_type: str) -> Mapping[str, str]:
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
    columns = provider.columns("widgets")
    assert "id" in columns and "type" in columns
    records = list(provider.records("widgets"))
    assert {r["__id"] for r in records} == {"w-1", "w-2"}
    # Every column key is present in every record:
    for record in records:
        for column in columns.values():
            assert column in record


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
