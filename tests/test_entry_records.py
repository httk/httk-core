"""Declarative entries retain exact identity and explicit serving semantics."""

from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from typing import Annotated

import pytest

from httk.core import DataEntryRecord, EntryRecord, Property, PropertyDefinition, content_id, entry_record
from httk.core.register import known_entry_families, known_entry_records
from httk.core.storage import stored_property_projections


@entry_record("tests.measurement")
class Measurement(DataEntryRecord):
    energy: Annotated[float, Property(description="Energy per atom.", unit="eV")]
    label: Annotated[str, Property(description="Sample label.")]
    private_note: str = ""


def test_frozen_record_metadata_and_identity():
    record = Measurement(-1.2, "sample")
    assert isinstance(record, EntryRecord)
    assert record.id is None
    with pytest.raises(FrozenInstanceError):
        record.energy = 1.0
    with pytest.raises(TypeError):
        Measurement(-1.2, "sample", "note", "positional-id")
    assert all(item.kw_only for item in fields(EntryRecord))
    identified = replace(record, id="test-1-1", immutable_id="test-1-1~1")
    assert record == identified and content_id(record) == content_id(identified)
    assert content_id(replace(record, energy=-2.0)) != content_id(record)
    assert content_id(replace(record, private_note="different")) != content_id(record)


def test_definitions_and_distinct_callback_closures():
    definition = Measurement.entry_type_definition()
    energy = definition.properties["_httk_custom_energy"]
    assert energy.optimade_type == "float"
    assert energy.as_optimade()["x-optimade-unit"] == "eV"
    assert "_httk_custom_private_note" not in definition.properties
    projections = stored_property_projections(Measurement)
    record = Measurement(-1.2, "sample")
    assert projections["_httk_custom_energy"].response(record) == -1.2
    assert projections["_httk_custom_label"].response(record) == "sample"
    assert all(p.query is not None and p.sort is not None for p in projections.values())
    assert definition.served_form().name == "_httk_records"


def test_stable_names_do_not_register_plugins_or_depend_on_python_names():
    families = known_entry_families()
    records = known_entry_records()

    @entry_record("tests.measurement")
    class Renamed(DataEntryRecord):
        energy: Annotated[float, Property(description="Energy per atom.", unit="eV")]
        label: Annotated[str, Property(description="Sample label.")]
        private_note: str = ""

    assert content_id(Renamed(-1.2, "sample")) == content_id(Measurement(-1.2, "sample"))
    assert Renamed.__httk_storage__ == Measurement.__httk_storage__
    assert known_entry_families() == families and known_entry_records() == records


def test_subclasses_require_opt_in_and_get_separate_maps():
    class Undecorated(Measurement):
        pass

    with pytest.raises(TypeError, match="decorated"):
        Undecorated.entry_type_definition()
    with pytest.raises(TypeError, match="directly"):
        stored_property_projections(Undecorated)

    @entry_record("tests.other-measurement")
    class Other(Measurement):
        pass

    assert Other.__httk_stored_properties__ is not Measurement.__httk_stored_properties__
    assert content_id(Other(-1.2, "sample")) != content_id(Measurement(-1.2, "sample"))


def test_existing_property_definition_and_nullable_field():
    definition = PropertyDefinition.from_simple("_httk_custom_count", description="Count.", fulltype="integer")

    @entry_record("tests.count")
    class Count(DataEntryRecord):
        value: Annotated[int | None, definition]

    assert Count.entry_type_definition().properties[definition.name] is definition
    assert Count(None).value is None


@pytest.mark.parametrize("annotation", [Fraction, list[float], float | str])
def test_lossy_or_non_scalar_properties_require_explicit_projections(annotation):
    class Unsupported(DataEntryRecord):
        value: Annotated[annotation, Property(description="Unsupported.")]

    with pytest.raises(TypeError, match="explicit projections"):
        entry_record("tests.unsupported")(Unsupported)


def test_metadata_overrides_fail_before_dataclass_conversion():
    class OverrideId(DataEntryRecord):
        id: str

    class OverrideImmutableId(DataEntryRecord):
        immutable_id: str

    class OverrideLastModified(DataEntryRecord):
        last_modified: str

    for record in (OverrideId, OverrideImmutableId, OverrideLastModified):
        with pytest.raises(TypeError, match="metadata fields"):
            entry_record("tests.override")(record)
        assert "__dataclass_fields__" not in vars(record)


def test_bad_or_conflicting_declarations_fail_early():
    with pytest.raises(ValueError, match="stable name"):
        entry_record(" ")

    with pytest.raises(TypeError, match="EntryRecord subclass"):
        entry_record("tests.bad")(type("Unrelated", (), {}))

    with pytest.raises(TypeError, match="replaces @dataclass"):
        entry_record("tests.twice")(Measurement)

    class Duplicate(DataEntryRecord):
        a: Annotated[float, Property(name="_httk_custom_same", description="First.")]
        b: Annotated[float, Property(name="_httk_custom_same", description="Second.")]

    with pytest.raises(ValueError, match="duplicate"):
        entry_record("tests.duplicate")(Duplicate)

    class Unprefixed(DataEntryRecord):
        value: Annotated[float, Property(name="energy", description="Energy.")]

    with pytest.raises(ValueError, match="prefix"):
        entry_record("tests.unprefixed")(Unprefixed)

    integer = PropertyDefinition.from_simple("_httk_custom_bad", description="Integer.", fulltype="integer")

    class Incompatible(DataEntryRecord):
        value: Annotated[float, integer]

    with pytest.raises(ValueError, match="conflicts"):
        entry_record("tests.incompatible")(Incompatible)


def test_general_entry_record_reuses_standard_property_definition():
    from httk.core import standard_entry_type

    references = standard_entry_type("references")

    @entry_record("tests.reference")
    class Citation(EntryRecord):
        type = "references"
        definition_id = references.definition_id
        title: Annotated[str, references.properties["title"]]

    assert Citation("A study").title == "A study"
    assert Citation.entry_type_definition().properties["title"] == references.properties["title"]
    assert stored_property_projections(Citation)["title"].response(Citation("A study")) == "A study"

    class MissingFamily(EntryRecord):
        pass

    with pytest.raises(TypeError, match="type and definition_id"):
        entry_record("tests.missing")(MissingFamily)

    class EmptyName(DataEntryRecord):
        value: Annotated[float, Property(name="", description="Energy.")]

    with pytest.raises(ValueError, match="nonempty identifier"):
        entry_record("tests.empty-name")(EmptyName)


def test_entry_metadata_validation_and_optional_definition_contract():
    import datetime

    with pytest.raises(ValueError, match="timezone-aware"):
        Measurement(-1.2, "sample", last_modified=datetime.datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="nonempty string"):
        Measurement(-1.2, "sample", id=" ")
    assert Measurement(-1.2, "sample", last_modified=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))

    required = PropertyDefinition.from_simple(
        "_httk_custom_value", description="Required value.", fulltype="float", required_response=True
    )

    class OptionalValue(DataEntryRecord):
        value: Annotated[float | None, required]

    with pytest.raises(ValueError, match="conflicts"):
        entry_record("tests.optional")(OptionalValue)


def test_served_property_cannot_be_skipped_or_class_metadata():
    from typing import ClassVar
    from httk.core import Skip

    class Skipped(DataEntryRecord):
        value: Annotated[float, Property(description="Value."), Skip()]

    with pytest.raises(ValueError, match="skipped field"):
        entry_record("tests.skipped")(Skipped)

    class ClassValue(DataEntryRecord):
        value: ClassVar[Annotated[float, Property(description="Value.")]] = 0.0

    with pytest.raises(TypeError, match="instance field"):
        entry_record("tests.class-value")(ClassValue)
