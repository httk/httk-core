from dataclasses import dataclass

import pytest

from httk.core import StoredEntryProjection, StoredEntryValue, stored_entry_projection


@dataclass(frozen=True)
class EntryRecord:
    id: str
    formula: str

    __httk_entry_projection__ = StoredEntryProjection(
        "structures",
        "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/structures",
        {"id": "id", "chemical_formula_reduced": "formula"},
        frozenset({"id", "chemical_formula_reduced"}),
        ("structure_record",),
    )


def test_stored_entry_projection_is_immutable_and_validates_record_fields() -> None:
    projection = stored_entry_projection(EntryRecord)
    assert projection is EntryRecord.__httk_entry_projection__
    assert projection.property_fields["chemical_formula_reduced"] == "formula"
    assert projection.obsolete_storage_names == ("structure_record",)
    with pytest.raises(TypeError):
        projection.property_fields["elements"] = "elements"

    @dataclass(frozen=True)
    class Broken:
        id: str

        __httk_entry_projection__ = StoredEntryProjection(
            "structures",
            "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/structures",
            {"id": "missing"},
        )

    with pytest.raises(ValueError, match="unknown dataclass fields"):
        stored_entry_projection(Broken)


def test_stored_entry_projection_rejects_invalid_contracts() -> None:
    with pytest.raises(ValueError, match="absolute IRI"):
        StoredEntryProjection("structures", "relative", {"id": "id"})
    with pytest.raises(ValueError, match="standard 'id'"):
        StoredEntryProjection("structures", "https://example.org/structures", {"formula": "formula"})
    with pytest.raises(ValueError, match="constant"):
        StoredEntryProjection("structures", "https://example.org/structures", {"id": "id", "type": "kind"})
    with pytest.raises(ValueError, match="must be mapped"):
        StoredEntryProjection(
            "structures",
            "https://example.org/structures",
            {"id": "id"},
            frozenset({"elements"}),
        )


def test_nested_stored_entry_values_are_structurally_typed() -> None:
    @dataclass(frozen=True)
    class Nested:
        internal: str

        def to_stored_entry_value(self) -> object:
            return {"public": self.internal}

    value: StoredEntryValue = Nested("yes")
    assert value.to_stored_entry_value() == {"public": "yes"}
