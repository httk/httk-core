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


def test_standard_entry_type_unknown_lists_available() -> None:
    with pytest.raises(ValueError) as excinfo:
        standard_entry_type("no_such_entry_type")
    message = str(excinfo.value)
    assert "references" in message and "files" in message and "calculations" in message
    assert "httk-atomistic" in message


def test_standard_entry_type_registered_structures() -> None:
    pytest.importorskip("httk.atomistic")
    structures = standard_entry_type("structures")
    assert structures.name == "structures"
    assert structures.definition_id == "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/structures"


def test_standard_entry_type_picks_highest_version(monkeypatch: pytest.MonkeyPatch) -> None:
    from httk.core.register import schemas

    base = "https://schemas.optimade.org/defs/v{}/entrytypes/optimade/fake"
    iris = [base.format("1.2"), base.format("1.10"), "https://example.org/defs/v9.9/entrytypes/optimade/fake"]
    monkeypatch.setattr(schemas, "known_entry_type_definitions", lambda: iris)
    monkeypatch.setattr(schemas, "load_entry_type_definition", lambda iri: iri)
    assert standard_entry_type("fake") == base.format("1.10")


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


def test_definition_reprs_are_constructor_shaped_and_abbreviated() -> None:
    entry = standard_entry_type("references")
    entry_repr = repr(entry)
    assert entry_repr.startswith("EntryTypeDefinition(")
    assert " object at 0x" not in entry_repr
    assert "..." in entry_repr
    assert "properties=" in entry_repr

    prop = entry.properties["id"]
    prop_repr = repr(prop)
    assert prop_repr.startswith("PropertyDefinition(")
    assert " object at 0x" not in prop_repr
    assert "..." in prop_repr
    assert "definition_id=" in prop_repr
    # The field names shown are real constructor/known attributes, not the old id=.
    assert "id=" not in prop_repr.replace("definition_id=", "")


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


# --- EntryTypeDefinition.served_form ------------------------------------------

_RUNS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/runs"
_RECORDS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/records"


def test_served_form_prefixes_vendored_runs() -> None:
    served = load_entry_type_definition(_RUNS_DEFINITION_ID).served_form()
    assert served.name == "_httk_runs"
    # A renamed served form is a new document: identity cleared, internal IRI kept as extends_id.
    assert served.definition_id is None
    assert served.extends_id == _RUNS_DEFINITION_ID
    assert set(served.properties) == {
        "id",
        "type",
        "immutable_id",
        "last_modified",
        "_httk_workflow_declaration_uri",
        "_httk_workflow_definition_uri",
        "_httk_source_id",
    }
    # Renaming keeps the published $id; only the wire name changes.
    workflow = served.properties["_httk_workflow_declaration_uri"]
    assert workflow.name == "_httk_workflow_declaration_uri"
    assert workflow.definition_id == "https://schemas.httk.org/defs/v0.1/properties/core/workflow_declaration_uri"


def test_served_form_prefixes_vendored_records() -> None:
    served = load_entry_type_definition(_RECORDS_DEFINITION_ID).served_form()
    assert served.name == "_httk_records"
    assert served.definition_id is None
    assert served.extends_id == _RECORDS_DEFINITION_ID
    assert set(served.properties) == {"id", "type", "immutable_id", "last_modified"}


def test_served_form_of_standard_definition_is_identity() -> None:
    references = standard_entry_type("references")
    served = references.served_form()
    assert served is references
    assert served == references
    assert served.name == "references"


def test_served_form_is_idempotent() -> None:
    for definition_id in (_RUNS_DEFINITION_ID, _RECORDS_DEFINITION_ID):
        served = load_entry_type_definition(definition_id).served_form()
        assert served.served_form() == served
        assert served.served_form() is served


def test_served_form_does_not_double_prefix_existing_prefix() -> None:
    calc = standard_entry_type("calculations")
    energy = PropertyDefinition.from_simple("_httk_total_energy", description="E", fulltype="float")
    served = calc.extended({"_httk_total_energy": energy}).served_form()
    # The extended entry keeps its standard IRI, so its name stays bare.
    assert served.name == "calculations"
    assert "_httk_total_energy" in served.properties
    assert "_httk__httk_total_energy" not in served.properties


def test_served_form_classifies_via_extends_id() -> None:
    base = load_entry_type_definition(_RUNS_DEFINITION_ID)
    via_extends = EntryTypeDefinition(
        "runs", base.description, dict(base.properties), definition_id=None, extends_id=_RUNS_DEFINITION_ID
    )
    served = via_extends.served_form()
    assert served.name == "_httk_runs"
    assert served.definition_id is None
    assert served.extends_id == _RUNS_DEFINITION_ID
    assert "_httk_workflow_declaration_uri" in served.properties


def test_apply_definition_prefix_public_transform() -> None:
    from httk.core import apply_definition_prefix

    # A registered httk IRI prefixes the name; None or an unregistered IRI is bare.
    assert apply_definition_prefix("has_input", _RUNS_DEFINITION_ID) == "_httk_has_input"
    assert apply_definition_prefix("has_input", None) == "has_input"
    assert apply_definition_prefix("has_input", "https://schemas.optimade.org/x") == "has_input"
    # Idempotent: an already-prefixed name is never re-prefixed.
    assert apply_definition_prefix("_httk_has_input", _RUNS_DEFINITION_ID) == "_httk_has_input"


def test_property_served_form_prefixes_curated_definition() -> None:
    from httk.core import load_property_definition

    d = load_property_definition("https://schemas.httk.org/defs/v0.1/properties/core/total_energy")
    served = d.served_form()
    assert served.name == "_httk_total_energy"
    assert served.definition_id == d.definition_id
    assert served.as_optimade().get("x-optimade-unit") == d.as_optimade().get("x-optimade-unit")
    assert served.served_form() is served
    custom = PropertyDefinition.from_simple("_httk_custom_x", description="X.", fulltype="float")
    assert custom.served_form() is custom


def test_property_served_form_of_standard_definition_is_identity() -> None:
    from httk.core.property_definitions import standard_entry_type

    for definition in standard_entry_type("references").properties.values():
        assert definition.served_form() is definition


# --- unit engine embedding and check() ----------------------------------------

_CORE_IDS = [
    "total_energy",
    "average_total_energy",
    "potential_energy",
    "kinetic_energy",
    "enthalpy",
    "temperature",
    "volume",
    "pressure",
    "stress_tensor",
]


def test_definition_ids_match_vendored_core_definitions() -> None:
    from httk.core import definition_ids, load_property_definition

    for name in _CORE_IDS:
        iri = getattr(definition_ids, name.upper())
        assert iri == f"https://schemas.httk.org/defs/v0.1/properties/core/{name}"
        assert load_property_definition(iri).definition_id == iri


def _embedded(prop: PropertyDefinition) -> list[str]:
    return [d["symbol"] for d in prop.unit_definitions]


def test_from_simple_embeds_unit_engine_documents() -> None:
    pressure = PropertyDefinition.from_simple("_httk_p", description="p", fulltype="float", unit="GPa")
    assert _embedded(pressure) == ["G", "Pa"]
    volume = PropertyDefinition.from_simple("_httk_v", description="v", fulltype="float", unit="angstrom^3")
    assert _embedded(volume) == ["angstrom"]
    for prop in (pressure, volume):
        for doc in prop.unit_definitions:
            assert "$schema" not in doc
            assert all(doc.get(key) for key in ("title", "symbol", "display-symbol", "description"))
    assert "$schema" in pressure.as_optimade()


@pytest.mark.parametrize("unit", ["m/s", "nosuchunit", "s*m"])
def test_from_simple_rejects_bad_units(unit: str) -> None:
    with pytest.raises(ValueError):
        PropertyDefinition.from_simple("_httk_x", description="x", fulltype="float", unit=unit)


def test_from_simple_dimensionless_embeds_nothing() -> None:
    prop = PropertyDefinition.from_simple("_httk_x", description="x", fulltype="float", unit="dimensionless")
    assert prop.unit_definitions == ()
    assert "x-optimade-unit-definitions" not in prop.as_optimade()


def test_unit_definitions_are_copies() -> None:
    prop = PropertyDefinition.from_simple("_httk_v", description="v", fulltype="float", unit="angstrom")
    prop.unit_definitions[0]["title"] = "changed"  # type: ignore[index]
    assert prop.unit_definitions[0]["title"] != "changed"


def test_check_accepts_and_rejects_with_json_path() -> None:
    from httk.core import definition_ids, load_property_definition

    stress = load_property_definition(definition_ids.STRESS_TENSOR)
    stress.check([1, 2.5, 3, 4, 5, 6])
    stress.check(None)
    with pytest.raises(ValueError, match=r"stress_tensor.*stress_tensor\[2\]"):
        stress.check([1, 2, "x", 4, 5, 6])
    with pytest.raises(ValueError, match="length 3, expected 6"):
        stress.check([1, 2, 3])
    with pytest.raises(ValueError):
        stress.check([1, 2, 3, 4, 5, float("nan")])
    with pytest.raises(ValueError):
        stress.check([1, 2, 3, 4, 5, None])

    ints = PropertyDefinition.from_simple("_httk_n", description="n", fulltype="integer", required_response=True)
    ints.check(3)
    with pytest.raises(ValueError):
        ints.check(True)
    with pytest.raises(ValueError, match="null"):
        ints.check(None)

    nested = PropertyDefinition.from_simple(
        "_httk_t", description="t", fulltype="list of list of float", unit="GPa", required_response=True
    )
    nested.check([[1.0, 2.0], [3.0]])
    with pytest.raises(ValueError, match=r"_httk_t\[1\]\[0\]"):
        nested.check([[1.0, 2.0], ["a"]])


def _level(kind: str, **extra: object) -> dict[str, object]:
    return {
        "x-optimade-type": kind,
        "type": [{"list": "array", "dictionary": "object", "float": "number"}[kind]],
        **extra,
    }


def _dims(names: list[str], sizes: list[int | None]) -> dict[str, object]:
    return {"x-optimade-dimensions": {"names": names, "sizes": sizes}}


def _dict_definition(name: str, members: dict[str, object], required: list[str]) -> PropertyDefinition:
    doc = {"$id": f"urn:test:{name}", "description": name, **_level("dictionary"), "properties": members}
    return PropertyDefinition.from_optimade(name, {**doc, "required": required})


def _series() -> PropertyDefinition:
    spatial = _level("list", items=_level("float"), **_dims(["dim_spatial"], [3]))
    return _dict_definition(
        "_httk_msd",
        {
            "lag_times": _level("list", items=_level("float"), **_dims(["_httk_dim_lags"], [None])),
            "msd": _level(
                "list",
                items=_level("list", items=spatial, **_dims(["dim_spatial"], [3])),
                **_dims(["_httk_dim_lags"], [None]),
            ),
        },
        ["lag_times", "msd"],
    )


def test_check_series_dictionary_shared_dimensions_and_required() -> None:
    eye = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    series = _series()
    series.check({"lag_times": [0.0, 1.0], "msd": [eye, eye]})
    with pytest.raises(
        ValueError, match=r"_httk_msd: _httk_msd\.msd .*'_httk_dim_lags'.*_httk_msd\.lag_times has length 2"
    ):
        series.check({"lag_times": [0.0, 1.0], "msd": [eye]})
    with pytest.raises(ValueError, match="missing required member 'msd'"):
        series.check({"lag_times": [0.0]})
    with pytest.raises(ValueError, match=r"msd\[0\]\[2\] has length 2, expected 3"):
        series.check({"lag_times": [0.0], "msd": [[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0]]]})


def test_check_two_name_level_maps_names_to_nested_depths() -> None:
    def matrix(sizes: list[int | None]) -> PropertyDefinition:
        doc = _level(
            "list", items=_level("list", items=_level("float")), **_dims(["dim_lattice", "dim_lattice"], sizes)
        )
        return PropertyDefinition.from_optimade("_httk_m", {"$id": "urn:test:m", "description": "m", **doc})

    fixed = matrix([3, 3])
    fixed.check([[1.0] * 3] * 3)
    for bad in ([[1.0] * 2] * 3, [[1.0] * 3] * 2):
        with pytest.raises(ValueError, match="expected 3"):
            fixed.check(bad)
    free = matrix([None, None])
    free.check([[1.0] * 2] * 2)
    with pytest.raises(ValueError, match="dim_lattice"):
        free.check([[1.0] * 2] * 3)


def test_check_distinct_dimension_names_may_differ_and_scope_per_element() -> None:
    rdf = _dict_definition(
        "_httk_rdf",
        {
            "bin_edges": _level("list", items=_level("float"), **_dims(["_httk_dim_bin_edges"], [None])),
            "g": _level("list", items=_level("float"), **_dims(["_httk_dim_bins"], [None])),
        },
        ["bin_edges", "g"],
    )
    rdf.check({"bin_edges": [0.0, 1.0, 2.0], "g": [0.5, 1.5]})

    # Like upstream ``species``: ``dim_species_chemical_symbols`` is shared within each species, not across species.
    symbols = _dims(["dim_species_chemical_symbols"], [None])
    member = _level(
        "dictionary",
        properties={
            "chemical_symbols": _level("list", items={"x-optimade-type": "string", "type": ["string"]}, **symbols),
            "concentration": _level("list", items=_level("float"), **symbols),
        },
    )
    doc = _level("list", items=member, **_dims(["dim_species"], [None]))
    species = PropertyDefinition.from_optimade("species", {"$id": "urn:test:species", "description": "s", **doc})
    alloy = {"chemical_symbols": ["Ti", "Zr"], "concentration": [0.5, 0.5]}
    species.check([{"chemical_symbols": ["O"], "concentration": [1.0]}, alloy])
    with pytest.raises(ValueError, match="dim_species_chemical_symbols"):
        species.check([{**alloy, "concentration": [1.0]}])


def test_check_enforces_enum_at_every_level() -> None:
    def string(**extra: object) -> dict[str, object]:
        return {"x-optimade-type": "string", "type": ["string"], **extra}

    top = PropertyDefinition.from_optimade(
        "_httk_k", {"$id": "urn:test:k", "description": "k", **string(enum=["a", "b"])}
    )
    top.check("a")
    with pytest.raises(ValueError, match=r"_httk_k: _httk_k is 'c', expected one of \['a', 'b'\]"):
        top.check("c")
    with pytest.raises(ValueError, match="must not be null"):
        top.check(None)
    nullable = string(enum=["a"])
    nullable["type"] = ["string", "null"]
    PropertyDefinition.from_optimade("_httk_n", {"$id": "urn:test:n", "description": "n", **nullable}).check(None)
    listed = PropertyDefinition.from_optimade(
        "_httk_l", {"$id": "urn:test:l", "description": "l", **string(enum=["a", None])}
    )
    listed.check(None)
    ints = {"$id": "urn:test:i", "description": "i", "x-optimade-type": "integer", "type": ["integer"], "enum": [1]}
    with pytest.raises(ValueError, match="expected one of"):
        PropertyDefinition.from_optimade("_httk_i", ints).check(True)

    spectrum = _dict_definition("_httk_vps", {"window": string(enum=["none", "hann"])}, ["window"])
    spectrum.check({"window": "hann"})
    with pytest.raises(ValueError, match=r"_httk_vps\.window is 'hamming', expected one of \['none', 'hann'\]"):
        spectrum.check({"window": "hamming"})


def _no_none(value: object) -> bool:
    if isinstance(value, dict):
        return all(item is not None and _no_none(item) for item in value.values())
    if isinstance(value, list):
        return all(item is not None and _no_none(item) for item in value)
    return True


def test_embedded_unit_definitions_have_no_nulls_and_match_rendered() -> None:
    from httk.core import definition_ids, load_property_definition

    prop = PropertyDefinition.from_simple("_httk_v", description="v", fulltype="float", unit="GPa*angstrom^3*eV")
    for doc in prop.unit_definitions:
        assert _no_none(dict(doc))
        assert all(doc.get(key) for key in ("title", "symbol", "display-symbol", "description"))
    mine = {d["symbol"]: d for d in prop.unit_definitions}
    rendered = {d["symbol"]: d for d in load_property_definition(definition_ids.VOLUME).unit_definitions}
    assert mine["angstrom"] == rendered["angstrom"]
    for source, symbols in ((definition_ids.PRESSURE, ("G", "Pa")), (definition_ids.ENTHALPY, ("eV",))):
        theirs = {d["symbol"]: d for d in load_property_definition(source).unit_definitions}
        for symbol in symbols:
            assert mine[symbol] == theirs[symbol]
