"""Tests for the standard-entry-type dataclasses and their providers."""

import pytest

from httk.core import (
    Calculation,
    CalculationEntryProvider,
    EntryTypeDefinition,
    File,
    FileEntryProvider,
    Reference,
    ReferenceEntryProvider,
    known_entry_providers,
)
from httk.core._plugins import resolve_callable
from httk.core.register import entry_providers

# --- dataclass create/validation ----------------------------------------------


def test_reference_create_from_dict_and_instance() -> None:
    ref = Reference.create({"title": "T", "doi": "10.1/x", "authors": ({"name": "Ada"},)})
    assert ref.title == "T"
    assert ref.authors == ({"name": "Ada"},)
    assert Reference.create(ref) is ref


def test_create_unknown_key_error_names_it() -> None:
    with pytest.raises(ValueError) as excinfo:
        File.create({"url": "http://x", "bogus": 1})
    assert "bogus" in str(excinfo.value)


def test_calculation_minimal_fields() -> None:
    calc = Calculation.create({"last_modified": "2024-01-01T00:00:00Z"})
    assert calc.immutable_id is None
    assert calc.last_modified == "2024-01-01T00:00:00Z"


# --- provider round trips -----------------------------------------------------


def test_reference_provider_round_trip() -> None:
    provider = ReferenceEntryProvider({"ref-1": {"title": "T", "doi": "10.1/x"}})
    entry_types = provider.entry_types()
    assert set(entry_types) == {"references"}
    assert isinstance(entry_types["references"], EntryTypeDefinition)
    columns = provider.columns("references")
    assert columns["id"] == "__id"
    assert columns["type"] == "type"
    assert columns["title"] == "title"
    records = list(provider.records("references"))
    assert records[0]["__id"] == "ref-1"
    assert records[0]["type"] == "references"
    assert records[0]["title"] == "T"
    assert records[0]["url"] is None
    # Every served column key is present in every record:
    for record in records:
        for column in columns.values():
            assert column in record


def test_file_provider_records() -> None:
    provider = FileEntryProvider({"f-1": File(url="http://x/INCAR", name="INCAR", size=512)})
    record = list(provider.records("files"))[0]
    assert record["url"] == "http://x/INCAR"
    assert record["size"] == 512


def test_calculation_provider_columns_cover_id_type() -> None:
    provider = CalculationEntryProvider({"calc-1": Calculation()})
    columns = provider.columns("calculations")
    assert {"id", "type"} <= set(columns)


def test_provider_rejects_wrong_entry_type() -> None:
    provider = ReferenceEntryProvider({})
    with pytest.raises(KeyError):
        provider.columns("files")


# --- registry -----------------------------------------------------------------


def test_core_providers_registered() -> None:
    assert {"core-references", "core-files", "core-calculations"} <= set(known_entry_providers())


def test_registered_factories_resolve_and_build() -> None:
    for name, entry_type in (
        ("core-references", "references"),
        ("core-files", "files"),
        ("core-calculations", "calculations"),
    ):
        factory = resolve_callable(entry_providers.require(name).handler)
        provider = factory({})
        assert list(provider.entry_types()) == [entry_type]
