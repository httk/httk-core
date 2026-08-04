"""Tests for the OPTIMADE property/entry-type definition model."""

from collections.abc import Iterator

import pytest

from httk.core import (
    EntryTypeDefinition,
    PropertyDefinition,
    load_entry_type_definition,
    standard_entry_type,
)
from httk.core.property_definitions import (
    known_definition_prefixes,
    register_definition_prefix,
)

# --- Vendored standard definitions --------------------------------------------


def test_standard_entry_type_counts() -> None:
    assert len(standard_entry_type("references").properties) == 30
    assert len(standard_entry_type("files").properties) == 16
    assert len(standard_entry_type("calculations").properties) == 4


def test_standard_entry_type_unknown_lists_known() -> None:
    with pytest.raises(ValueError) as excinfo:
        standard_entry_type("structures")
    message = str(excinfo.value)
    assert "references" in message and "files" in message and "calculations" in message


def test_vendored_canonical_ids_and_format_mix() -> None:
    references = standard_entry_type("references")
    # A shared core property keeps its core $id; an entry-specific one is scoped.
    assert references.properties["id"].definition_id == "https://schemas.optimade.org/defs/v1.2/properties/core/id"
    assert (
        references.properties["title"].definition_id
        == "https://schemas.optimade.org/defs/v1.2/properties/optimade/references/title"
    )
    # Every vendored property carries the "1.2" definition format stamp.
    for prop in references.properties.values():
        assert prop.format_version == "1.2"


def test_vendored_requirements_present() -> None:
    references = standard_entry_type("references")
    assert references.properties["title"].requirements["support"] == "may"
    assert references.properties["id"].requirements["response-level"] == "always"


def test_load_entry_type_definition_is_cached() -> None:
    definition_id = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"
    a = load_entry_type_definition(definition_id)
    b = load_entry_type_definition(definition_id)
    assert a is b


def test_entry_type_definition_id_round_trip_and_extension_provenance() -> None:
    standard = standard_entry_type("calculations")
    assert standard.definition_id == "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations"
    assert EntryTypeDefinition.from_optimade("calculations", standard.as_optimade()) == standard

    extra = PropertyDefinition.from_simple("_httk_custom_total_energy", description="E", fulltype="float")
    extended = standard.extended({"_httk_custom_total_energy": extra})
    assert extended.definition_id is None
    assert extended.extends_id == standard.definition_id
    assert "$id" not in extended.as_optimade()
    assert "definition_id=None" in repr(extended)

    chained = extended.extended({"_httk_other": extra})
    assert chained.extends_id == standard.definition_id


def test_from_optimade_validation_error() -> None:
    with pytest.raises(ValueError) as excinfo:
        PropertyDefinition.from_optimade("broken", {"description": "no id/type/xtype"})
    assert "broken" in str(excinfo.value)


def test_entry_type_from_optimade_validation_error() -> None:
    with pytest.raises(ValueError):
        EntryTypeDefinition.from_optimade("widgets", {"properties": {}})


# --- from_simple golden payloads ----------------------------------------------


def test_from_simple_integer_optimade_id() -> None:
    prop = PropertyDefinition.from_simple("cogwheels", description="Number of cogwheels.", fulltype="integer")
    doc = prop.as_optimade()
    assert doc["$id"] == "https://schemas.optimade.org/defs/v1.2/properties/optimade/cogwheels"
    assert doc["x-optimade-type"] == "integer"
    assert doc["type"] == ["integer", "null"]
    assert doc["x-optimade-definition"]["format"] == "1.2"
    assert doc["$schema"].endswith("property_definition.json")
    # from_simple is implementation-neutral: no sortable/implementation yet.
    assert "sortable" not in doc
    assert "x-optimade-implementation" not in doc


def test_from_simple_httk_prefixed_id() -> None:
    prop = PropertyDefinition.from_simple("_httk_custom_total_energy", description="Total energy", fulltype="float")
    doc = prop.as_optimade()
    assert doc["$id"] == "https://schemas.httk.org/ad-hoc/defs/properties/_httk_custom_total_energy"
    assert doc["type"] == ["number", "null"]


def test_from_simple_required_response_is_non_null() -> None:
    prop = PropertyDefinition.from_simple("id", description="id", fulltype="string", required_response=True)
    doc = prop.as_optimade()
    assert doc["type"] == ["string"]
    assert prop.nullable is False


def test_from_simple_list_with_dimensions_and_generated_metadata() -> None:
    prop = PropertyDefinition.from_simple(
        "lattice_vectors",
        description="Lattice vectors.",
        fulltype="list of list of float",
        unit="angstrom",
        dimensions={"names": ["dim_lattice", "dim_spatial"], "sizes": [3, 3]},
    )
    doc = prop.as_optimade()
    assert doc["x-optimade-type"] == "list"
    assert doc["items"]["items"]["x-optimade-type"] == "float"
    assert doc["x-optimade-unit"] == "angstrom"
    assert doc["x-optimade-unit-definitions"][0]["symbol"] == "angstrom"
    assert doc["x-optimade-dimensions"] == {"names": ["dim_lattice", "dim_spatial"], "sizes": [3, 3]}
    # No explicit metadata definition, but dimensions are present -> list_axes:
    metadata = doc["x-optimade-metadata-definition"]
    assert "list_axes" in metadata["properties"]


def test_from_simple_definition_id_override() -> None:
    prop = PropertyDefinition.from_simple(
        "nelements",
        description="n",
        fulltype="integer",
        definition_id="https://schemas.optimade.org/defs/v1.2/properties/optimade/structures/nelements",
    )
    assert prop.definition_id.endswith("/structures/nelements")


def test_from_simple_timestamp_and_dict() -> None:
    ts = PropertyDefinition.from_simple("modification_timestamp", description="t", fulltype="timestamp").as_optimade()
    assert ts["format"] == "date-time"
    assert ts["type"] == ["string", "null"]
    checksums = PropertyDefinition.from_simple(
        "checksums", description="c", fulltype="dict", dict_properties={"md5": "string", "sha256": "string"}
    ).as_optimade()
    assert set(checksums["properties"]) == {"md5", "sha256"}


# --- with_implementation ------------------------------------------------------


def test_with_implementation_overlay_leaves_original_untouched() -> None:
    prop = PropertyDefinition.from_simple("nelements", description="n", fulltype="integer")
    overlaid = prop.with_implementation(sortable=True, response_default=False)
    overlaid_doc = overlaid.as_optimade()
    assert overlaid_doc["x-optimade-implementation"] == {"sortable": True, "response-default": False}
    assert overlaid_doc["sortable"] is True
    assert overlaid_doc["$id"] == prop.definition_id
    assert overlaid_doc["x-optimade-definition"] == prop.as_optimade()["x-optimade-definition"]
    # The original is unchanged:
    assert "x-optimade-implementation" not in prop.as_optimade()
    assert "sortable" not in prop.as_optimade()


def test_with_implementation_partial_keys() -> None:
    prop = PropertyDefinition.from_simple("nelements", description="n", fulltype="integer")
    doc = prop.with_implementation(response_default=True).as_optimade()
    assert doc["x-optimade-implementation"] == {"response-default": True}
    assert "sortable" not in doc


# --- EntryTypeDefinition.extended ---------------------------------------------


def test_extended_prefixed_custom_property() -> None:
    calc = standard_entry_type("calculations")
    energy = PropertyDefinition.from_simple("_httk_custom_total_energy", description="E", fulltype="float")
    extended = calc.extended({"_httk_custom_total_energy": energy})
    assert "_httk_custom_total_energy" in extended.properties
    assert "_httk_custom_total_energy" not in calc.properties  # original untouched


def test_extended_collision_error() -> None:
    calc = standard_entry_type("calculations")
    clashing = PropertyDefinition.from_simple("id", description="dup", fulltype="string")
    with pytest.raises(ValueError) as excinfo:
        calc.extended({"id": clashing})
    assert "id" in str(excinfo.value)


def test_extended_unprefixed_rejected_unless_allowed() -> None:
    calc = standard_entry_type("calculations")
    widget = PropertyDefinition.from_simple("cogwheels", description="w", fulltype="integer")
    with pytest.raises(ValueError) as excinfo:
        calc.extended({"cogwheels": widget})
    assert all(prefix in str(excinfo.value) for prefix in known_definition_prefixes())
    # allow_unprefixed lets it through:
    extended = calc.extended({"cogwheels": widget}, allow_unprefixed=True)
    assert "cogwheels" in extended.properties


def test_accessors() -> None:
    prop = standard_entry_type("files").properties["url"]
    assert prop.name == "url"
    assert prop.optimade_type == "string"
    assert prop.nullable is False
    assert prop.unit == "inapplicable"
    assert isinstance(prop.description, str)


# --- definition-prefix registry -----------------------------------------------


@pytest.fixture
def _clean_example_prefix() -> Iterator[None]:
    from httk.core.property_definitions import _DEFINITION_PREFIXES

    _DEFINITION_PREFIXES.pop("_exmpl_", None)
    try:
        yield
    finally:
        _DEFINITION_PREFIXES.pop("_exmpl_", None)


def test_pre_registered_prefixes() -> None:
    prefixes = known_definition_prefixes()
    assert set(prefixes) == {"_httk_"}


def test_register_prefix_gives_from_simple_id(_clean_example_prefix: None) -> None:
    register_definition_prefix("_exmpl_", "https://schemas.example.org/ad-hoc/defs/properties")
    assert "_exmpl_" in known_definition_prefixes()
    doc = PropertyDefinition.from_simple("_exmpl_wave_class", description="wave class", fulltype="string").as_optimade()
    assert doc["$id"] == "https://schemas.example.org/ad-hoc/defs/properties/_exmpl_wave_class"
    assert doc["x-optimade-definition"]["label"] == "exmpl_wave_class_exmpl"


def test_extended_accepts_registered_prefix_and_rejects_before(_clean_example_prefix: None) -> None:
    calc = standard_entry_type("calculations")
    prop = PropertyDefinition.from_simple("_exmpl_wave_class", description="w", fulltype="string")
    # Before registration the prefix is not recognized.
    with pytest.raises(ValueError):
        calc.extended({"_exmpl_wave_class": prop})
    register_definition_prefix("_exmpl_", "https://schemas.example.org/ad-hoc/defs/properties")
    extended = calc.extended({"_exmpl_wave_class": prop})
    assert "_exmpl_wave_class" in extended.properties


def test_register_prefix_rejects_invalid_format() -> None:
    for bad in ("exmpl", "_Exmpl_", "_exmpl", "exmpl_", "__", "_ex-l_"):
        with pytest.raises(ValueError):
            register_definition_prefix(bad, "https://example.org/defs")
