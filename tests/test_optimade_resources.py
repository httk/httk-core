"""Focused tests for exact, immutable OPTIMADE source resources and bindings."""

import io
import json
import sys
import urllib.request
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
from email.message import Message
from pathlib import Path
from types import ModuleType

import pytest

import httk.core.optimade_resources as resources
from httk.core import (
    CalculationView,
    FileView,
    IncompleteOptimadeResourceError,
    OptimadeCalculation,
    OptimadeDocument,
    OptimadeEntryBinding,
    OptimadeFile,
    OptimadeReference,
    OptimadeResource,
    OptimadeSchemaSnapshot,
    ReferenceView,
    decode_optimade_value,
    is_optimade_entry_url,
    known_optimade_entry_bindings,
    optimade_document_root,
    optimade_entry_binding,
    redact_optimade_url,
    register_optimade_entry_binding,
)
from httk.core.optimade_resources import (
    optimade_entry_url_info,
    optimade_resource_from_url,
    redact_optimade_document_text,
)
from httk.core.register import _optimade_entry_bindings


class _Response(io.BytesIO):
    headers = Message()


_ENTRY = json.dumps(
    {"data": {"id": "material-1", "type": "structures", "attributes": {"chemical_formula_reduced": "Si"}}}
)
_INFO = json.dumps(
    {
        "data": {
            "description": "Structure entries",
            "properties": {"chemical_formula_reduced": {"$id": "https://example.test/chemical_formula_reduced"}},
        }
    }
)


def _urlopen_responses(calls: list[tuple[str, float | None]], responses: dict[str, str | Exception]):
    def fake(url: str, *, timeout: float | None) -> _Response:
        calls.append((url, timeout))
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return _Response(response.encode())

    return fake


def _resource(text: str, index: int = 0) -> OptimadeResource:
    document = OptimadeDocument(text, "https://example.test/v1/structures")
    schema = OptimadeSchemaSnapshot("structures", document)
    return OptimadeResource(document, index, schema)


def test_source_models_are_frozen_plain_dataclasses() -> None:
    document = OptimadeDocument('{"data": []}', "https://example.test")
    snapshot = OptimadeSchemaSnapshot("structures", document)
    resource = OptimadeResource(document, 0, snapshot)
    assert [field.name for field in fields(OptimadeDocument)] == ["text", "source_url"]
    assert [field.name for field in fields(OptimadeSchemaSnapshot)] == ["entry_type", "info_document"]
    assert [field.name for field in fields(OptimadeResource)] == ["document", "data_index", "schema"]
    with pytest.raises(FrozenInstanceError):
        document.text = "changed"  # type: ignore[misc]
    assert hash(document) == hash(OptimadeDocument(document.text, document.source_url))
    assert resource == OptimadeResource(document, 0, snapshot)
    assert hash(resource) == hash(OptimadeResource(document, 0, snapshot))
    # Mapping's ABC base itself has slots, but these concrete dataclasses must
    # retain an ordinary instance dictionary for lazy SQL reconstruction.
    assert hasattr(document, "__dict__")
    assert hasattr(snapshot, "__dict__")
    assert hasattr(resource, "__dict__")


def test_resource_is_lazy_decimal_exact_and_immutable() -> None:
    resource = _resource('{"data": [{"type": "structures", "number": 1.2300e+4, "list": [{"x": 2.50}]}]}')
    assert isinstance(resource["number"], Decimal)
    assert resource["number"] == Decimal("1.2300e+4")
    assert isinstance(resource.unwrap(), Mapping)
    nested = resource["list"]
    assert isinstance(nested[0], Mapping)
    assert nested[0]["x"] == Decimal("2.50")
    with pytest.raises(TypeError):
        resource.unwrap()["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        nested[0]["x"] = Decimal(3)  # type: ignore[index]


def test_generic_resource_envelope_id_and_type_are_lazy_stored_properties() -> None:
    resource = _resource('{"data": [{"id": "source-1", "type": "odd-transport-name"}]}')
    assert resource.id == "source-1"
    assert resource.type == "odd-transport-name"
    with pytest.raises(ValueError, match="nonempty"):
        _ = _resource('{"data": [{"id": "", "type": "x"}]}').id
    with pytest.raises(ValueError, match="nonempty"):
        _ = _resource('{"data": [{"id": "x", "type": null}]}').type


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("not json", ValueError),
        ("[]", ValueError),
        ('{"data": null}', ValueError),
        ('{"data": [null]}', ValueError),
        ('{"data": []}', IndexError),
    ],
)
def test_resource_rejects_bad_shape_lazily(text: str, error: type[Exception]) -> None:
    resource = _resource(text)
    with pytest.raises(error):
        resource.unwrap()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.test/v1/structures/id", ("structures", "https://example.test/v1/info/structures")),
        ("https://example.test/v1.3/structures/id", ("structures", "https://example.test/v1.3/info/structures")),
        ("https://example.test/v1.3.0/structures/id/", ("structures", "https://example.test/v1.3.0/info/structures")),
        ("https://example.test/structures/id", ("structures", "https://example.test/info/structures")),
        (
            "https://example.test/api/structures/id?response_fields=id",
            ("structures", "https://example.test/api/info/structures"),
        ),
        ("https://example.test/v1/structures", None),
        ("https://example.test/v1/not-Valid/id", None),
    ],
)
def test_optimade_entry_url_shape(url: str, expected: tuple[str, str] | None) -> None:
    assert optimade_entry_url_info(url) == expected
    assert is_optimade_entry_url(url) is (expected is not None)


def test_optimade_resource_from_url_assembles_single_entry_and_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://example.test/v1.3/structures/material-1?response_fields=id"
    info_url = "https://example.test/v1.3/info/structures"
    calls: list[tuple[str, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_responses(calls, {url: _ENTRY, info_url: _INFO}))

    resource = optimade_resource_from_url(url, timeout=4.5)

    assert resource.id == "material-1"
    assert resource.type == "structures"
    assert resource.schema.entry_type == "structures"
    assert resource.document.source_url == url
    assert resource.schema.info_document.source_url == info_url
    assert optimade_document_root(resource.schema.info_document)["data"]["properties"] is not None
    assert calls == [(url, 4.5), (info_url, 4.5)]


@pytest.mark.parametrize("entry", ["not JSON", json.dumps({"data": []}), json.dumps({"meta": {}})])
def test_optimade_resource_from_url_rejects_non_single_entry(monkeypatch: pytest.MonkeyPatch, entry: str) -> None:
    url = "https://example.test/v1/structures/material-1"
    calls: list[tuple[str, float | None]] = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_responses(calls, {url: entry}))

    with pytest.raises(ValueError, match="example\\.test"):
        optimade_resource_from_url(url)
    assert calls == [(url, 30.0)]


def test_optimade_resource_from_url_names_derived_info_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://example.test/v1/structures/material-1"
    info_url = "https://example.test/v1/info/structures"
    calls: list[tuple[str, float | None]] = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _urlopen_responses(calls, {url: _ENTRY, info_url: OSError("unavailable")}),
    )

    with pytest.raises(ValueError, match="v1/info/structures"):
        optimade_resource_from_url(url)
    assert calls == [(url, 30.0), (info_url, 30.0)]


@pytest.mark.parametrize("endpoint", ["info", "links", "versions", "extensions"])
def test_optimade_resource_from_url_rejects_non_entry_endpoints(endpoint: str) -> None:
    url = f"https://example.test/v1/{endpoint}/structures"
    assert not is_optimade_entry_url(url)
    with pytest.raises(ValueError, match="Not an OPTIMADE single-entry URL"):
        optimade_resource_from_url(url)


def test_optimade_url_errors_redact_credentials() -> None:
    url = "https://example.test/v1/info/structures?access_token=SECRET&keep=yes"
    with pytest.raises(ValueError) as excinfo:
        optimade_resource_from_url(url)

    message = str(excinfo.value)
    assert redact_optimade_url(url) in message
    assert "SECRET" not in message


def test_optimade_resource_from_file_url(tmp_path: Path) -> None:
    entry_path = tmp_path / "v1" / "structures" / "material-1"
    info_path = tmp_path / "v1" / "info" / "structures"
    entry_path.parent.mkdir(parents=True)
    info_path.parent.mkdir(parents=True)
    entry_path.write_text(_ENTRY, encoding="utf-8")
    info_path.write_text(_INFO, encoding="utf-8")

    resource = optimade_resource_from_url(entry_path.as_uri())

    assert resource.id == "material-1"
    assert resource.schema.info_document.source_url == info_path.as_uri()


def test_equivalent_documents_share_process_local_lazy_parse_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    text = '{"data": [{"id": "one"}]}'
    calls = 0
    original_loads = resources.json.loads

    def counting_loads(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original_loads(*args, **kwargs)

    monkeypatch.setattr(resources.json, "loads", counting_loads)
    first = _resource(text)
    second = _resource(text)
    assert first.unwrap()["id"] == "one"
    assert second.unwrap()["id"] == "one"
    assert calls == 1


def test_safe_document_creation_redacts_only_top_level_pagination() -> None:
    text = (
        '{ "data" : [ { "number" : 1.2300e+4, "attributes" : {'
        '"url" : "https://user:semantic@example.test/file?token=semantic-secret", '
        '"https://example.test/key?token=semantic-key" : "exact", '
        '"links" : { "next" : "?token=semantic-nested" } }, '
        '"relationships" : { "files" : { "links" : {'
        '"related" : "https://user:semantic@example.test/related?api_key=semantic-related" } } } } ], '
        '"extensions" : { "href" : "?token=semantic-extension" }, '
        '"links" : { "next" : "https://user:cursor@example.test/next?keep=ok&TOKEN=cursor-secret" } }'
    )
    document = OptimadeDocument.create(text, "https://user:secret@example.test/v1?api_key=hide&keep=ok#frag")
    assert document.text == (
        '{ "data" : [ { "number" : 1.2300e+4, "attributes" : {'
        '"url" : "https://user:semantic@example.test/file?token=semantic-secret", '
        '"https://example.test/key?token=semantic-key" : "exact", '
        '"links" : { "next" : "?token=semantic-nested" } }, '
        '"relationships" : { "files" : { "links" : {'
        '"related" : "https://user:semantic@example.test/related?api_key=semantic-related" } } } } ], '
        '"extensions" : { "href" : "?token=semantic-extension" }, '
        '"links" : { "next" : "https://example.test/next?keep=ok" } }'
    )
    assert document.source_url == "https://example.test/v1?keep=ok"
    assert "semantic-secret" in document.text
    assert "semantic-key" in document.text
    assert "semantic-nested" in document.text
    assert "semantic-related" in document.text
    assert "semantic-extension" in document.text
    assert "cursor-secret" not in document.text
    assert "secret" not in document.source_url
    assert "hide" not in document.source_url
    assert redact_optimade_document_text('{"number": 1.2300e+4}') == '{"number": 1.2300e+4}'
    malformed = '{"url":"https://user:secret@example.test/path?token=hide'
    assert redact_optimade_document_text(malformed) == malformed
    assert redact_optimade_url("/v1/structures?page_offset=2&token=secret") == "/v1/structures?page_offset=2"
    assert (
        redact_optimade_url("https://example.test/v1/structures#access_token=secret")
        == "https://example.test/v1/structures"
    )
    assert redact_optimade_url("?page_cursor=x&api_key=secret") == "?page_cursor=x"
    assert redact_optimade_url("../structures?key=secret") == "../structures"
    link_object = (
        '{"links":{"next":{"href":"?page_cursor=x&api_key=secret","meta":{"href":"?token=semantic"}}},"number":1.2300}'
    )
    safe_link_object = '{"links":{"next":{"href":"?page_cursor=x","meta":{"href":"?token=semantic"}}},"number":1.2300}'
    assert redact_optimade_document_text(link_object) == safe_link_object
    exact_next = '{"links":{"next":"https:\\/\\/example.test\\/next?keep=a%20b"},"number":1.2300}'
    assert redact_optimade_document_text(exact_next) == exact_next
    escaped_secret = (
        '{"links":{"next":"https:\\/\\/user:pw@example.test\\/next?keep=a%20b&token=secret"},"number":1.2300}'
    )
    escaped_safe = '{"links":{"next":"https:\\/\\/example.test\\/next?keep=a%20b"},"number":1.2300}'
    assert redact_optimade_document_text(escaped_secret) == escaped_safe
    semantic = '{"url":"?page_cursor=x&api_key=semantic", "number": 1.2300}'
    assert redact_optimade_document_text(semantic) == semantic
    assert redact_optimade_url("not-a-url?token=unchanged") == "not-a-url?token=unchanged"


def _install_binding_module(monkeypatch: pytest.MonkeyPatch) -> str:
    name = "httk_test_optimade_binding_module"
    module = ModuleType(name)

    class Backend:
        pass

    class View:
        pass

    def decoder(value: object) -> object:
        return value

    module.Backend = Backend
    module.View = View
    module.decoder = decoder
    module.not_a_class = 3
    monkeypatch.setitem(sys.modules, name, module)
    return name


def test_optimade_binding_registry_is_strict_lazy_and_copy_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _install_binding_module(monkeypatch)
    definition_id = "https://schemas.example.test/entrytypes/widgets"
    property_id = "https://schemas.example.test/properties/widget_count"
    decoders = {property_id: f"{module}:decoder"}
    register_optimade_entry_binding(
        name="test-widgets",
        definition_id=definition_id,
        backend=f"{module}:Backend",
        view=f"{module}:View",
        property_decoders=decoders,
        query_fields=(property_id,),
    )
    try:
        binding = optimade_entry_binding(definition_id)
        assert binding is not None
        decoders.clear()
        assert binding.name == "test-widgets"
        assert binding.query_fields == (property_id,)
        assert binding.property_decoders == {property_id: f"{module}:decoder"}
        with pytest.raises(TypeError):
            binding.property_decoders[property_id] = "other:decoder"  # type: ignore[index]
        assert definition_id in known_optimade_entry_bindings()
        assert binding.resolve_backend().__name__ == "Backend"
        assert binding.resolve_view().__name__ == "View"
        assert binding.resolve_property_decoder(property_id)("value") == "value"  # type: ignore[operator]
        assert binding.resolve_property_decoder("https://missing.example/property") is None
        with pytest.raises(ValueError, match="already registered"):
            register_optimade_entry_binding(
                name="duplicate",
                definition_id=definition_id,
                backend=f"{module}:Backend",
                view=f"{module}:View",
            )
    finally:
        _optimade_entry_bindings.pop(definition_id, None)


def test_binding_validation_and_resolution_type_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _install_binding_module(monkeypatch)
    with pytest.raises(ValueError, match="strict 'module:attr'"):
        OptimadeEntryBinding("bad", "https://example.test/type", "bad", f"{module}:View")
    with pytest.raises(ValueError, match="listed more than once"):
        OptimadeEntryBinding(
            "duplicate-query",
            "https://example.test/type",
            f"{module}:Backend",
            f"{module}:View",
            query_fields=("https://example.test/property", "https://example.test/property"),
        )
    binding = OptimadeEntryBinding(
        "not-class",
        "https://example.test/not-class",
        f"{module}:not_a_class",
        f"{module}:View",
    )
    with pytest.raises(TypeError):
        binding.resolve_backend()
    decoder_binding = OptimadeEntryBinding(
        "not-callable-decoder",
        "https://example.test/not-callable-decoder",
        f"{module}:Backend",
        f"{module}:View",
        property_decoders={"https://example.test/property": f"{module}:not_a_class"},
    )
    with pytest.raises(TypeError):
        decoder_binding.resolve_property_decoder("https://example.test/property")


def test_binding_query_field_none_and_empty_tuple_are_distinct() -> None:
    module = "httk_unimportable_binding_test"
    derived_id = "https://example.test/entrytypes/derived"
    empty_id = "https://example.test/entrytypes/empty"
    register_optimade_entry_binding(
        name="derived-query-fields",
        definition_id=derived_id,
        backend=f"{module}:Backend",
        view=f"{module}:View",
        query_fields=None,
    )
    register_optimade_entry_binding(
        name="empty-query-fields",
        definition_id=empty_id,
        backend=f"{module}:Backend",
        view=f"{module}:View",
        query_fields=(),
    )
    try:
        assert optimade_entry_binding(derived_id).query_fields is None  # type: ignore[union-attr]
        assert optimade_entry_binding(empty_id).query_fields == ()  # type: ignore[union-attr]
    finally:
        _optimade_entry_bindings.pop(derived_id, None)
        _optimade_entry_bindings.pop(empty_id, None)


def test_binding_registration_never_imports_targets_eagerly() -> None:
    definition_id = "https://example.test/entrytypes/lazy"
    register_optimade_entry_binding(
        name="lazy",
        definition_id=definition_id,
        backend="httk_unimportable_binding_test:Backend",
        view="httk_unimportable_binding_test:View",
    )
    try:
        binding = optimade_entry_binding(definition_id)
        assert binding is not None
        assert "httk_unimportable_binding_test" not in sys.modules
        with pytest.raises(ModuleNotFoundError):
            binding.resolve_backend()
    finally:
        _optimade_entry_bindings.pop(definition_id, None)


# --- typed standard resources -------------------------------------------------


_ENTRY_IRIS = {
    "references": "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
    "files": "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
    "calculations": "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
}
_PROPERTY_BASE = "https://schemas.optimade.org/defs/v1.2/properties/core/"


def _typed_resource(entry_type: str, properties: dict[str, object], attributes: str = "{}") -> OptimadeResource:
    info_properties = ", ".join(f'"{remote}": {{"$id": "{iri}"}}' for remote, iri in properties.items())
    info = OptimadeDocument(
        f'{{"data": {{"properties": {{{info_properties}}}}}}}',
        f"https://example.test/v1/info/{entry_type}",
    )
    document = OptimadeDocument(
        f'{{"data": [{{"id": "entry-1", "type": "transport-{entry_type}", '
        f'"attributes": {attributes}, "_unknown": {{"number": 1.2300}}}}]}}',
        f"https://example.test/v1/{entry_type}",
    )
    return OptimadeResource(document, 0, OptimadeSchemaSnapshot(entry_type, info))


def test_builtin_bindings_resolve_to_prefix_first_classes() -> None:
    expected = {
        _ENTRY_IRIS["references"]: (OptimadeReference, ReferenceView),
        _ENTRY_IRIS["files"]: (OptimadeFile, FileView),
        _ENTRY_IRIS["calculations"]: (OptimadeCalculation, CalculationView),
    }
    for definition_id, (backend, view) in expected.items():
        binding = optimade_entry_binding(definition_id)
        assert binding is not None
        assert binding.query_fields is None
        assert binding.resolve_backend() is backend
        assert binding.resolve_view() is view


def test_typed_backend_uses_property_iris_not_transport_names_and_stores_portables() -> None:
    core = _PROPERTY_BASE
    resource = _typed_resource(
        "references",
        {
            "identifier-renamed": core + "id",
            "record-type-renamed": core + "type",
            "stable-renamed": core + "immutable_id",
            "changed-renamed": core + "last_modified",
            "title-renamed": "https://schemas.optimade.org/defs/v1.2/properties/optimade/references/title",
        },
        '{"stable-renamed": "immutable-1", "changed-renamed": "2024-02-03T04:05:06Z", "title-renamed": "A reference"}',
    )
    backend = OptimadeReference(resource)
    assert [field.name for field in fields(backend)] == ["resource"]
    assert backend.kind == "optimade"
    assert backend.unwrap() is resource
    assert backend.raw["_unknown"]["number"] == Decimal("1.2300")
    assert backend.id == "entry-1"
    assert backend.type == "transport-references"
    assert backend.immutable_id == "immutable-1"
    assert backend.last_modified is not None
    assert backend.last_modified.tzinfo is not None
    view = ReferenceView(backend)
    assert view.backend is backend
    assert ReferenceView(view) is view
    view_hash = hash(view)
    assert view.title == "A reference"
    assert view.record is view.record
    assert hash(view) == view_hash
    assert view == ReferenceView(backend)


def test_typed_backend_never_recognizes_same_spelled_wrong_or_missing_iri() -> None:
    resource = _typed_resource(
        "references",
        {
            "id": "https://example.test/properties/not-id",
            "type": "https://example.test/properties/not-type",
            "title": "https://example.test/properties/not-title",
        },
        '{"title": "must not be recognized"}',
    )
    backend = OptimadeReference(resource)
    with pytest.raises(ValueError, match="semantic property 'id'"):
        _ = backend.id
    assert ReferenceView(backend).record.title is None

    invalid_id = _typed_resource("references", {"title": 1}, '{"title": "also unrecognized"}')
    assert ReferenceView(OptimadeReference(invalid_id)).record.title is None


def test_info_document_shape_and_duplicate_iris_are_rejected() -> None:
    document = OptimadeDocument('{"data": [{"id": "x", "type": "x"}]}', "https://example.test/v1")
    malformed = OptimadeResource(
        document,
        0,
        OptimadeSchemaSnapshot("references", OptimadeDocument('{"data": []}', "https://example.test/info")),
    )
    with pytest.raises(ValueError, match="data.*object"):
        _ = OptimadeReference(malformed).id
    duplicate = _typed_resource(
        "references",
        {"one": _PROPERTY_BASE + "id", "two": _PROPERTY_BASE + "id"},
    )
    with pytest.raises(ValueError, match="both"):
        _ = OptimadeReference(duplicate).id


def test_typed_view_is_parse_and_materialization_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    # Local vendored-schema loading is unrelated to remote document parsing;
    # warm it before counting the latter.
    from httk.core import standard_entry_type

    standard_entry_type("files")
    resource = _typed_resource(
        "files",
        {
            "id-field": _PROPERTY_BASE + "id",
            "type-field": _PROPERTY_BASE + "type",
            "url-field": "https://schemas.optimade.org/defs/v1.2/properties/optimade/files/url",
            "name-field": "https://schemas.optimade.org/defs/v1.2/properties/optimade/files/name",
        },
        '{"url-field": "https://example.test/a", "name-field": "a"}',
    )
    calls = 0
    original = resources.json.loads

    def counting_loads(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(resources.json, "loads", counting_loads)
    backend = OptimadeFile(resource)
    view = FileView(backend)
    assert calls == 0
    assert view.record.name == "a"
    assert calls == 2
    assert view.record.name == "a"
    assert calls == 2


def test_required_null_and_optional_missing_properties_are_explicit() -> None:
    required_missing = _typed_resource(
        "files",
        {
            "url": "https://schemas.optimade.org/defs/v1.2/properties/optimade/files/url",
            "name": "https://schemas.optimade.org/defs/v1.2/properties/optimade/files/name",
        },
        '{"url": null}',
    )
    with pytest.raises(IncompleteOptimadeResourceError, match="null semantic property 'url'"):
        _ = FileView(OptimadeFile(required_missing)).record
    optional_missing = _typed_resource("calculations", {}, "{}")
    record = CalculationView(OptimadeCalculation(optional_missing)).record
    assert record.immutable_id is None
    assert record.last_modified is None


def test_generic_decoder_is_exact_and_immutable() -> None:
    from httk.core import PropertyDefinition

    floats = PropertyDefinition.from_simple("value", description="value", fulltype="float")
    lists = PropertyDefinition.from_simple("value", description="value", fulltype="list of float")
    dictionary = PropertyDefinition.from_simple("value", description="value", fulltype="dict")
    timestamp = PropertyDefinition.from_simple("value", description="value", fulltype="timestamp")
    assert decode_optimade_value(floats, Decimal("1.2300")) == Decimal("1.2300")
    assert decode_optimade_value(lists, (Decimal("2.50"),)) == (Decimal("2.50"),)
    decoded_dictionary = decode_optimade_value(dictionary, {"nested": [Decimal("3.40")]})
    assert decoded_dictionary["nested"] == (Decimal("3.40"),)
    with pytest.raises(TypeError):
        decoded_dictionary["x"] = "no"  # type: ignore[index]
    assert decode_optimade_value(timestamp, "2024-01-01T00:00:00Z").tzinfo is not None
    with pytest.raises(ValueError, match="UTC offset"):
        decode_optimade_value(timestamp, "2024-01-01T00:00:00")
