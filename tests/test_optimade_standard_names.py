"""Tests for standard-namespace schema completion of OPTIMADE info documents."""

import datetime
import json
from pathlib import Path

import pytest

from httk.core.optimade import (
    STANDARD_NAME_EVIDENCE,
    OptimadeDocument,
    OptimadeReference,
    OptimadeResource,
    OptimadeSchemaSnapshot,
    StandardSchemaCompletion,
    complete_standard_schema,
    infer_standard_names,
    parse_optimade_api_version,
)
from httk.core.optimade.standard_names import _info_api_version, _info_properties
from httk.core.register import (
    OptimadeEntryBinding,
    _optimade_entry_bindings,
    optimade_entry_binding,
    register_optimade_entry_binding,
)
from httk.core.register.schemas import load_entry_type_definition

_FIXTURES = Path(__file__).parent / "data" / "optimade_info"
_IRI = "https://schemas.optimade.org/defs/v1.2/properties/optimade/structures/"
_REFERENCES_IRI = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references"
_FILES_IRI = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"


def _infer(**overrides: object) -> StandardSchemaCompletion:
    kwargs: dict[str, object] = {
        "entry_type": "structures",
        "api_version": "1.2.0",
        "advertised": {"nelements": {}},
        "definition_ids_by_name": {"nelements": _IRI + "nelements"},
        "introduced_in": {"nelements": "1.0"},
    }
    kwargs.update(overrides)
    return infer_standard_names(**kwargs)  # type: ignore[arg-type]


# --- pure infer_standard_names -----------------------------------------------


def test_version_parsing_accepts_major1_and_rejects_others() -> None:
    assert parse_optimade_api_version("1.2.0") == (1, 2)
    assert parse_optimade_api_version("1.1") == (1, 1)
    assert parse_optimade_api_version("1.3.0-rc.1+build") == (1, 3)
    assert parse_optimade_api_version("2.0.0") is None
    assert parse_optimade_api_version("0.9") is None
    assert parse_optimade_api_version("nope") is None
    assert parse_optimade_api_version(None) is None
    assert parse_optimade_api_version(120) is None


def test_unprefixed_name_in_range_is_inferred_with_standard_evidence() -> None:
    completion = _infer()
    assert dict(completion.definitions_by_name) == {"nelements": _IRI + "nelements"}
    assert completion.evidence_by_name == {"nelements": STANDARD_NAME_EVIDENCE}
    assert completion.api_version == "1.2.0"
    assert completion.entry_type_definition_id is None


def test_provider_prefixed_names_are_never_inferred_even_when_standard() -> None:
    completion = _infer(
        advertised={"_mp_nelements": {}, "_alexandria_x": {}},
        definition_ids_by_name={"_mp_nelements": _IRI + "nelements", "_alexandria_x": _IRI + "x"},
        introduced_in={"_mp_nelements": "1.0", "_alexandria_x": "1.0"},
    )
    assert dict(completion.definitions_by_name) == {}


def test_malformed_underscore_name_is_never_inferred() -> None:
    completion = _infer(
        advertised={"_notaprefix": {}, "_": {}},
        definition_ids_by_name={"_notaprefix": _IRI + "n", "_": _IRI + "u"},
        introduced_in={"_notaprefix": "1.0", "_": "1.0"},
    )
    assert dict(completion.definitions_by_name) == {}


def test_declared_id_wins_and_its_iri_is_not_also_inferred() -> None:
    # The declared name keeps its own identity (skipped, not inferred), and an
    # unprefixed alias that the table would map onto the same IRI is dropped.
    completion = _infer(
        advertised={"official": {"$id": _IRI + "nelements"}, "alias": {}},
        definition_ids_by_name={"official": _IRI + "official", "alias": _IRI + "nelements"},
        introduced_in={"official": "1.0", "alias": "1.0"},
    )
    assert dict(completion.definitions_by_name) == {}


def test_version_gating_in_both_directions() -> None:
    late = {
        "advertised": {"fractional_site_positions": {}},
        "definition_ids_by_name": {"fractional_site_positions": _IRI + "fsp"},
        "introduced_in": {"fractional_site_positions": "1.3"},
    }
    assert dict(_infer(api_version="1.3.0", **late).definitions_by_name) == {"fractional_site_positions": _IRI + "fsp"}
    assert dict(_infer(api_version="1.1.0", **late).definitions_by_name) == {}
    early = {
        "advertised": {"nelements": {}},
        "definition_ids_by_name": {"nelements": _IRI + "nelements"},
        "introduced_in": {"nelements": "1.0"},
    }
    assert dict(_infer(api_version="1.1.0", **early).definitions_by_name) == {"nelements": _IRI + "nelements"}


@pytest.mark.parametrize("api_version", [None, "garbage", "2.0.0", "0.9.0"])
def test_absent_malformed_or_non_major1_version_disables_inference(api_version: str | None) -> None:
    completion = _infer(api_version=api_version)
    assert dict(completion.definitions_by_name) == {}
    assert completion.evidence_by_name == {}


def test_names_absent_from_table_or_definition_map_are_not_inferred() -> None:
    # Absent from introduced_in (the table).
    assert dict(_infer(introduced_in={}).definitions_by_name) == {}
    # Absent from the definition map.
    assert dict(_infer(definition_ids_by_name={}).definitions_by_name) == {}


def test_two_names_colliding_on_one_iri_are_both_dropped() -> None:
    completion = _infer(
        advertised={"a": {}, "b": {}},
        definition_ids_by_name={"a": _IRI + "same", "b": _IRI + "same"},
        introduced_in={"a": "1.0", "b": "1.0"},
    )
    assert dict(completion.definitions_by_name) == {}
    assert completion.evidence_by_name == {}


def test_completion_mappings_are_frozen() -> None:
    completion = _infer()
    with pytest.raises(TypeError):
        completion.definitions_by_name["x"] = "y"  # type: ignore[index]
    with pytest.raises(TypeError):
        completion.evidence_by_name["x"] = "y"  # type: ignore[index]


# --- registry-driven complete_standard_schema --------------------------------


def _snapshot(text: str, entry_type: str = "structures") -> OptimadeSchemaSnapshot:
    document = OptimadeDocument(text, f"https://example.test/v1/info/{entry_type}")
    return OptimadeSchemaSnapshot(entry_type, document)


@pytest.mark.parametrize(
    ("filename", "api_version"),
    [
        ("alexandria_pbe_info_structures.json", "1.1.0"),
        ("oqmd_info_structures.json", "1.2.0"),
        ("cod_info_structures.json", "1.1.0"),
    ],
)
def test_real_provider_fixtures_complete_only_standard_names(filename: str, api_version: str) -> None:
    # Distribution-agnostic: whether a ``structures`` table is registered (by
    # httk-atomistic in the shared venv) or not, the completion must not raise,
    # must report the declared version, and must only ever bind unprefixed
    # advertised names to standard IRIs, never a declared ``$id``'s IRI.
    text = (_FIXTURES / filename).read_text(encoding="utf-8")
    properties = json.loads(text)["data"]["properties"]
    declared_iris = {doc["$id"] for doc in properties.values() if isinstance(doc, dict) and "$id" in doc}

    completion = complete_standard_schema(_snapshot(text))

    assert completion.api_version == api_version
    for name, iri in completion.definitions_by_name.items():
        assert name in properties, name
        assert not name.startswith("_"), name
        assert iri not in declared_iris, iri
    assert set(completion.evidence_by_name.values()) <= {STANDARD_NAME_EVIDENCE}
    assert completion.definitions_by_name.keys() == completion.evidence_by_name.keys()


@pytest.mark.parametrize(
    "text",
    [
        "this is not json",
        "[1, 2, 3]",
        '{"data": {"description": "no properties"}, "meta": {"api_version": "1.1.0"}}',
        '{"data": {"properties": {}}}',
    ],
)
def test_malformed_info_documents_never_raise(text: str) -> None:
    completion = complete_standard_schema(_snapshot(text, entry_type="references"))
    assert isinstance(completion, StandardSchemaCompletion)
    assert dict(completion.definitions_by_name) == {}


def test_declared_version_is_read_from_the_info_document_meta() -> None:
    text = '{"data": {"properties": {}}, "meta": {"api_version": "1.1.0"}}'
    assert complete_standard_schema(_snapshot(text, entry_type="references")).api_version == "1.1.0"


def test_info_helpers_extract_meta_and_properties_defensively() -> None:
    good = OptimadeDocument(
        '{"data": {"properties": {"nelements": {}}}, "meta": {"api_version": "1.2.0"}}',
        "https://example.test/v1/info/structures",
    )
    assert _info_api_version(good) == "1.2.0"
    assert dict(_info_properties(good)) == {"nelements": {}}
    bad = OptimadeDocument("not json", "https://example.test/v1/info/structures")
    assert _info_api_version(bad) is None
    assert dict(_info_properties(bad)) == {}
    no_meta = OptimadeDocument('{"data": {"properties": {}}}', "https://example.test/v1/info/structures")
    assert _info_api_version(no_meta) is None


# --- integration against real httk-core-owned tables -------------------------


def _info(entry_type: str, api_version: str, names: tuple[str, ...]) -> str:
    advertised = ", ".join(f'"{name}": {{}}' for name in names)
    return f'{{"data": {{"properties": {{{advertised}}}}}, "meta": {{"api_version": "{api_version}"}}}}'


def test_references_table_infers_standard_names_only() -> None:
    references = load_entry_type_definition(_REFERENCES_IRI)
    text = _info(
        "references",
        "1.0.0",
        ("doi", "authors", "title", "_exmpl_internal", "not_a_reference_field"),
    )
    completion = complete_standard_schema(_snapshot(text, entry_type="references"))
    assert completion.entry_type_definition_id == _REFERENCES_IRI
    assert dict(completion.definitions_by_name) == {
        "doi": references.properties["doi"].definition_id,
        "authors": references.properties["authors"].definition_id,
        "title": references.properties["title"].definition_id,
    }
    assert "_exmpl_internal" not in completion.definitions_by_name
    assert "not_a_reference_field" not in completion.definitions_by_name


def test_files_table_gates_inference_on_the_declared_version() -> None:
    files = load_entry_type_definition(_FILES_IRI)
    names = ("url", "checksums")
    # All files names are standard as of format 1.2, so a 1.1.0 service declares
    # a version too old to bind them.
    gated = complete_standard_schema(_snapshot(_info("files", "1.1.0", names), entry_type="files"))
    assert dict(gated.definitions_by_name) == {}
    assert gated.entry_type_definition_id == _FILES_IRI
    # A 1.2.0 service is in range, so both bind to the vendored IRIs.
    ok = complete_standard_schema(_snapshot(_info("files", "1.2.0", names), entry_type="files"))
    assert ok.entry_type_definition_id == _FILES_IRI
    assert dict(ok.definitions_by_name) == {
        "url": files.properties["url"].definition_id,
        "checksums": files.properties["checksums"].definition_id,
    }


def test_entry_type_definition_id_set_only_when_inference_is_possible() -> None:
    # references has a real owner-declared table, so the id depends solely on
    # whether the info document's declared version is usable.
    no_version = complete_standard_schema(_snapshot('{"data": {"properties": {"doi": {}}}}', entry_type="references"))
    assert no_version.entry_type_definition_id is None
    bad_major = complete_standard_schema(_snapshot(_info("references", "2.0.0", ("doi",)), entry_type="references"))
    assert bad_major.entry_type_definition_id is None


def test_completion_cache_reflects_binding_reregistration() -> None:
    original = optimade_entry_binding(_REFERENCES_IRI)
    assert original is not None
    doi_iri = load_entry_type_definition(_REFERENCES_IRI).properties["doi"].definition_id
    snapshot = _snapshot(_info("references", "1.0.0", ("doi",)), entry_type="references")
    # The real table marks doi standard since 1.0, so a 1.0.0 service binds it.
    assert dict(complete_standard_schema(snapshot).definitions_by_name) == {"doi": doi_iri}
    _optimade_entry_bindings.pop(_REFERENCES_IRI, None)
    try:
        # Same IRI, different object and table: doi is now too new for 1.0.0.
        register_optimade_entry_binding(
            name=original.name,
            definition_id=_REFERENCES_IRI,
            backend=original.backend,
            view=original.view,
            standard_property_versions={"doi": "1.3"},
        )
        # The same snapshot object must not return the stale cached completion.
        assert dict(complete_standard_schema(snapshot).definitions_by_name) == {}
    finally:
        _optimade_entry_bindings.pop(_REFERENCES_IRI, None)
        _optimade_entry_bindings[_REFERENCES_IRI] = original


def test_backend_last_modified_is_bound_from_a_standard_name_without_id() -> None:
    # End-to-end: no ``$id`` anywhere, only the declared version and the
    # standard name ``last_modified`` drive the binding in entries.py.
    info = OptimadeDocument(
        '{"data": {"properties": {"last_modified": {}}}, "meta": {"api_version": "1.2.0"}}',
        "https://example.test/v1/info/references",
    )
    entry = OptimadeDocument(
        '{"data": {"id": "ref-1", "type": "references", "attributes": {"last_modified": "2023-11-16T07:57:59Z"}}}',
        "https://example.test/v1/references/ref-1",
    )
    backend = OptimadeReference(OptimadeResource(entry, 0, OptimadeSchemaSnapshot("references", info)))
    last_modified = backend.last_modified
    assert last_modified is not None
    assert last_modified.tzinfo is not None
    assert last_modified == datetime.datetime(2023, 11, 16, 7, 57, 59, tzinfo=datetime.UTC)


# --- binding registration validation -----------------------------------------


def test_standard_property_versions_registers_and_freezes() -> None:
    definition_id = "https://schemas.example.test/entrytypes/versioned"
    register_optimade_entry_binding(
        name="versioned",
        definition_id=definition_id,
        backend="httk_unimportable_binding_test:Backend",
        view="httk_unimportable_binding_test:View",
        standard_property_versions={"nelements": "1.0", "structure_features": "1.2.0"},
    )
    try:
        binding = optimade_entry_binding(definition_id)
        assert binding is not None
        assert dict(binding.standard_property_versions) == {"nelements": "1.0", "structure_features": "1.2.0"}
        with pytest.raises(TypeError):
            binding.standard_property_versions["x"] = "1.0"  # type: ignore[index]
    finally:
        _optimade_entry_bindings.pop(definition_id, None)


def test_standard_property_versions_defaults_to_empty_frozen_mapping() -> None:
    binding = OptimadeEntryBinding(
        "empty-versions",
        "https://example.test/entrytypes/empty-versions",
        "httk_unimportable_binding_test:Backend",
        "httk_unimportable_binding_test:View",
    )
    assert dict(binding.standard_property_versions) == {}
    with pytest.raises(TypeError):
        binding.standard_property_versions["x"] = "1.0"  # type: ignore[index]


@pytest.mark.parametrize(
    ("versions", "error"),
    [
        ({"nelements": "not-a-version"}, ValueError),
        ({"nelements": "2.0.0"}, ValueError),
        ({"nelements": 12}, ValueError),
        ({"": "1.0"}, ValueError),
        (["nelements"], TypeError),
    ],
)
def test_malformed_standard_property_versions_are_rejected(versions: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        OptimadeEntryBinding(
            "bad-versions",
            "https://example.test/entrytypes/bad-versions",
            "httk_unimportable_binding_test:Backend",
            "httk_unimportable_binding_test:View",
            standard_property_versions=versions,  # type: ignore[arg-type]
        )
