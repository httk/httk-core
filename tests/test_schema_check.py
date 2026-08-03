"""Tests for structural record/schema compatibility checks."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any

from httk.core import (
    Calculation,
    EntryTypeDefinition,
    File,
    FracVector,
    PropertyDefinition,
    Reference,
    Shape,
    load_entry_type_definition,
)
from httk.core.schema_check import check_record_matches_definition

type Tags = tuple[str, ...]
type Tag = str
type ShapedVector = Annotated[FracVector, Shape(0, 3)]
type ShapedVectorAlias = ShapedVector


def _definition(**properties: tuple[str, bool]) -> EntryTypeDefinition:
    return EntryTypeDefinition(
        "synthetic",
        "synthetic",
        {
            name: PropertyDefinition.from_simple(
                name,
                description=name,
                fulltype=fulltype,
                required_response=required,
            )
            for name, (fulltype, required) in properties.items()
        },
    )


def test_compatible_record_passes() -> None:
    @dataclass
    class Record:
        name: str | None
        count: int
        tags: tuple[str, ...]
        metadata: Mapping[str, Any]

    definition = _definition(
        name=("string", False),
        count=("integer", True),
        tags=("list of string", True),
        metadata=("dict", True),
    )
    assert check_record_matches_definition(Record, definition) == []


def test_pep695_alias_matches_list_shape() -> None:
    @dataclass
    class Record:
        tags: Tags

    assert check_record_matches_definition(Record, _definition(tags=("list of string", True))) == []


def test_pep695_alias_of_annotated_shape_matches_dimensions() -> None:
    @dataclass
    class Record:
        vectors: ShapedVectorAlias

    definition = EntryTypeDefinition(
        "synthetic",
        "synthetic",
        {
            "vectors": PropertyDefinition.from_simple(
                "vectors",
                description="vectors",
                fulltype="list of list of float",
                dimensions={"names": ["rows", "cols"], "sizes": [None, 3]},
                required_response=True,
            )
        },
    )
    assert check_record_matches_definition(Record, definition) == []


def test_pep695_alias_inside_container_matches_element_shape() -> None:
    @dataclass
    class Record:
        tags: list[Tag]

    assert check_record_matches_definition(Record, _definition(tags=("list of string", True))) == []


def test_missing_and_extra_names_are_reported_in_both_directions() -> None:
    @dataclass
    class Record:
        present: str
        missing: str

    messages = check_record_matches_definition(
        Record,
        _definition(present=("string", True), extra=("string", True)),
    )
    assert messages == [
        (
            "field 'missing' maps to property 'missing', but that property is missing from the definition "
            "(field -> property)"
        ),
        "property 'extra' has no corresponding field in the record (property -> field)",
    ]


def test_nullability_disagreements_are_reported_in_both_directions() -> None:
    @dataclass
    class Record:
        nullable: str | None
        required: str

    messages = check_record_matches_definition(
        Record,
        _definition(nullable=("string", True), required=("string", False)),
    )
    assert messages == [
        (
            "field 'nullable' for property 'nullable' is nullable, but the property is non-nullable "
            "(field -> property nullability)"
        ),
        (
            "field 'required' for property 'required' is non-nullable, but the property is nullable "
            "(property -> field nullability)"
        ),
    ]


def test_scalar_and_list_element_type_mismatches_are_reported() -> None:
    @dataclass
    class Record:
        count: float
        labels: list[int]

    messages = check_record_matches_definition(
        Record,
        _definition(count=("integer", True), labels=("list of string", True)),
    )
    assert len(messages) == 2
    assert all("field -> property type shape" in message for message in messages)
    assert any("field 'count'" in message and "property 'count'" in message for message in messages)
    assert any("field 'labels'" in message and "property 'labels'" in message for message in messages)


def test_shape_marker_matches_dimensions_and_variable_rows() -> None:
    @dataclass
    class Fixed:
        vectors: Annotated[FracVector, Shape(3, 3)]

    @dataclass
    class Variable:
        vectors: Annotated[FracVector, Shape(0, 3)]

    fixed = EntryTypeDefinition(
        "synthetic",
        "synthetic",
        {
            "vectors": PropertyDefinition.from_simple(
                "vectors",
                description="vectors",
                fulltype="list of list of float",
                dimensions={"names": ["rows", "cols"], "sizes": [3, 3]},
                required_response=True,
            )
        },
    )
    assert check_record_matches_definition(Fixed, fixed) == []

    wrong_shape = Annotated[FracVector, Shape(2, 3)]

    @dataclass
    class Wrong:
        vectors: wrong_shape

    messages = check_record_matches_definition(Wrong, fixed)
    assert len(messages) == 1
    assert "field 'vectors'" in messages[0]
    assert "property 'vectors'" in messages[0]
    assert "dimensions" in messages[0]

    variable = EntryTypeDefinition(
        "synthetic",
        "synthetic",
        {
            "vectors": PropertyDefinition.from_simple(
                "vectors",
                description="vectors",
                fulltype="list of list of float",
                dimensions={"names": ["rows", "cols"], "sizes": [None, 3]},
                required_response=True,
            )
        },
    )
    assert check_record_matches_definition(Variable, variable) == []


def test_internal_fields_property_keys_and_ignored_properties() -> None:
    @dataclass
    class Record:
        source_name: str
        cache: int

    definition = _definition(served=("string", True), id=("string", True), type=("string", True))
    assert (
        check_record_matches_definition(
            Record,
            definition,
            property_keys={"source_name": "served"},
            internal_fields=("cache",),
        )
        == []
    )


def test_messages_are_order_stable_and_name_both_sides() -> None:
    @dataclass
    class Record:
        first: float
        second: int

    first = _definition(first=("integer", True), second=("string", True))
    reversed_definition = EntryTypeDefinition(
        "synthetic",
        "synthetic",
        dict(reversed(list(first.properties.items()))),
    )
    messages = check_record_matches_definition(Record, first)
    assert messages == check_record_matches_definition(Record, reversed_definition)
    assert all("field '" in message and "property '" in message and "->" in message for message in messages)


# The real record tier matches the registered standard schemas.
_EXPECTED: dict[type, list[str]] = {
    Reference: [],
    File: [],
    Calculation: [],
}


def test_standard_record_schema_discrepancies_are_pinned() -> None:
    pairs = (
        (
            Reference,
            "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
        ),
        (File, "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"),
        (
            Calculation,
            "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
        ),
    )
    for record, iri in pairs:
        messages = check_record_matches_definition(record, load_entry_type_definition(iri))
        assert sorted(messages) == sorted(_EXPECTED[record])
