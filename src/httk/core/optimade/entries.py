"""Typed, exact OPTIMADE resource backends for core standard entry types.

The resource and its schema snapshot remain the sole source of truth.  A
typed backend recognizes values by property-definition IRI from the supplied
``/info/<entry>`` document; a remote transport name is only an address after
that IRI match has been established.  The record views deliberately defer all
document parsing and generated-record construction until ``.record`` (or a
delegated field) is requested.
"""

import datetime
from collections.abc import Callable, Mapping
from dataclasses import MISSING, dataclass, field, fields
from decimal import Decimal
from types import MappingProxyType
from typing import ClassVar, Self, cast
from urllib.parse import urlsplit

from ..entry_types import Calculation, File, Reference
from ..property_definitions import EntryTypeDefinition, PropertyDefinition, standard_entry_type
from ..register.entries import optimade_entry_binding
from ..storage.markers import stored_property
from .resources import FrozenJson, OptimadeResource, optimade_document_root

type OptimadeValueDecoder = Callable[[object, PropertyDefinition], object]

_MISSING = object()
_CORE_ID = "https://schemas.optimade.org/defs/v1.2/properties/core/id"
_CORE_TYPE = "https://schemas.optimade.org/defs/v1.2/properties/core/type"


class IncompleteOptimadeResourceError(ValueError):
    """A resource lacks, nulls, or malforms a local record property."""


def _is_definition_iri(value: object) -> bool:
    """Return whether *value* is a minimally well-formed absolute IRI."""

    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        return bool(urlsplit(value).scheme)
    except ValueError:
        return False


def _frozen_recursive(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _frozen_recursive(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_frozen_recursive(item) for item in value)
    if isinstance(value, list):
        return tuple(_frozen_recursive(item) for item in value)
    return value


def _decode_by_payload(payload: Mapping[str, object], value: object) -> object:
    """Decode *value* according to one OPTIMADE property-definition payload."""

    if value is None:
        return None
    optimade_type = payload.get("x-optimade-type")
    if optimade_type == "string":
        if not isinstance(value, str):
            raise TypeError("expected a string")
        return value
    if optimade_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("expected an integer")
        return value
    if optimade_type == "boolean":
        if not isinstance(value, bool):
            raise TypeError("expected a boolean")
        return value
    if optimade_type == "float":
        if not isinstance(value, Decimal | int) or isinstance(value, bool):
            raise TypeError("expected an exact JSON number (Decimal or int)")
        return value
    if optimade_type == "timestamp":
        if not isinstance(value, str):
            raise TypeError("expected an RFC3339 timestamp string")
        try:
            decoded = datetime.datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid RFC3339 timestamp {value!r}") from exc
        if decoded.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        return decoded
    if optimade_type == "list":
        if not isinstance(value, tuple | list):
            raise TypeError("expected a JSON array")
        items = payload.get("items")
        if not isinstance(items, Mapping):
            raise ValueError("list definition lacks an object 'items' schema")
        return tuple(_decode_by_payload(cast(Mapping[str, object], items), item) for item in value)
    if optimade_type == "dictionary":
        if not isinstance(value, Mapping):
            raise TypeError("expected a JSON object")
        return _frozen_recursive(value)
    raise ValueError(f"unsupported OPTIMADE property type {optimade_type!r}")


def decode_optimade_value(definition: PropertyDefinition, value: object) -> object:
    """Decode one value exactly from its local property definition.

    Binding-specific decoder callables use the stable signature
    ``decoder(value, definition)`` and replace this generic decoder for their
    exact property-definition IRI.  JSON floats are retained as
    :class:`~decimal.Decimal`; nested lists and dictionaries become tuples and
    immutable mappings.

    :param definition: Local property definition that describes the value.
    :param value: Raw value to decode.
    :return: Decoded value with nested containers made immutable.
    :raises TypeError: If the value does not match the declared property shape.
    :raises ValueError: If the property definition is unsupported or malformed.
    """

    return _decode_by_payload(cast(Mapping[str, object], definition.as_optimade()), value)


@dataclass(frozen=True)
class OptimadeEntryBackend:
    """Store one typed handle around an authoritative OPTIMADE resource.

    :param resource: Source resource and its schema provenance.
    """

    resource: OptimadeResource

    kind: ClassVar[str] = "optimade"
    entry_type_name: ClassVar[str]
    entry_type_definition_id: ClassVar[str]

    def __post_init__(self) -> None:
        if not isinstance(self.resource, OptimadeResource):
            raise TypeError("resource must be an OptimadeResource")

    @property
    def raw(self) -> Mapping[str, FrozenJson]:
        """The immutable JSON API resource mapping, retaining source provenance."""

        return self.resource.unwrap()

    def unwrap(self) -> OptimadeResource:
        """Return the exact source resource, including document and schema provenance.

        :return: The source resource represented by this backend.
        """

        return self.resource

    @property
    def local_schema(self) -> EntryTypeDefinition:
        """Return the standard local schema for this backend."""

        return standard_entry_type(self.entry_type_name)

    @property
    def _remote_names_by_definition_id(self) -> Mapping[str, str]:
        """Map semantic property IRIs to remote names from the frozen info document."""

        root = optimade_document_root(self.resource.schema.info_document)
        data = root.get("data")
        if not isinstance(data, Mapping):
            raise ValueError("OPTIMADE info document root member 'data' must be an object")
        properties = data.get("properties")
        if not isinstance(properties, Mapping):
            raise ValueError("OPTIMADE info document data member 'properties' must be an object")
        names: dict[str, str] = {}
        for remote_name, document in properties.items():
            if not isinstance(remote_name, str):
                raise ValueError("OPTIMADE info document property names must be strings")
            if not isinstance(document, Mapping):
                raise ValueError(f"OPTIMADE info property {remote_name!r} must be an object")
            definition_id = document.get("$id")
            if not _is_definition_iri(definition_id):
                # A transport label without a valid semantic identity is simply
                # unknown; it must never be recognized by spelling.
                continue
            definition_id = cast(str, definition_id)
            if definition_id in names:
                raise ValueError(
                    "OPTIMADE info document assigns definition IRI "
                    f"{definition_id!r} to both {names[definition_id]!r} and {remote_name!r}"
                )
            names[definition_id] = remote_name
        return MappingProxyType(names)

    def value_by_definition_id(self, definition_id: str, *, default: object = _MISSING) -> object:
        """Return a raw value by exact semantic IRI, retaining missing vs. null.

        Values are intentionally undecoded here.  This lets record views name
        missing/null semantic properties accurately and gives callers access to
        exact raw JSON before selecting a representation.

        :param definition_id: Semantic property IRI to look up.
        :param default: Value to return when the property is not present.
        :return: The raw property value, or ``default`` when it is absent.
        :raises ValueError: If the resource attributes or schema mapping is malformed.
        """

        if definition_id not in self._remote_names_by_definition_id:
            return default
        if definition_id == _CORE_ID:
            return self.raw.get("id", default)
        if definition_id == _CORE_TYPE:
            return self.raw.get("type", default)
        attributes = self.raw.get("attributes")
        if not isinstance(attributes, Mapping):
            if attributes is None:
                return default
            raise ValueError("OPTIMADE resource top-level 'attributes' must be an object when present")
        return attributes.get(self._remote_names_by_definition_id[definition_id], default)

    def decode_value(self, definition: PropertyDefinition, value: object) -> object:
        """Decode *value*, applying an exact-IRI binding override when present.

        :param definition: Local property definition for the value.
        :param value: Raw value to decode.
        :return: Decoded value from the matching generic or binding-specific decoder.
        :raises TypeError: If the value does not match the selected property decoder.
        :raises ValueError: If the property definition or value is invalid.
        """

        binding = optimade_entry_binding(self.entry_type_definition_id)
        decoder = binding.resolve_property_decoder(definition.definition_id) if binding is not None else None
        if decoder is None:
            return decode_optimade_value(definition, value)
        return cast(OptimadeValueDecoder, decoder)(value, definition)

    @stored_property
    def id(self) -> str:
        """Return the semantic resource identifier."""

        value = self.value_by_definition_id(_CORE_ID)
        if not isinstance(value, str) or not value:
            raise ValueError("OPTIMADE semantic property 'id' must be a nonempty string")
        return value

    @stored_property
    def type(self) -> str:
        """Return the semantic resource type identifier."""

        value = self.value_by_definition_id(_CORE_TYPE)
        if not isinstance(value, str) or not value:
            raise ValueError("OPTIMADE semantic property 'type' must be a nonempty string")
        return value

    @stored_property
    def immutable_id(self) -> str | None:
        """Return the optional immutable semantic identifier."""

        return cast(str | None, self._portable_value("immutable_id", str))

    @stored_property
    def last_modified(self) -> datetime.datetime | None:
        """Return the optional last-modified timestamp."""

        return cast(datetime.datetime | None, self._portable_value("last_modified", datetime.datetime))

    def _portable_value(self, name: str, expected_class: object) -> object:
        definition = self.local_schema.properties[name]
        raw = self.value_by_definition_id(definition.definition_id)
        if raw is _MISSING or raw is None:
            return None
        value = self.decode_value(definition, raw)
        if not isinstance(value, cast(type[object], expected_class)):
            raise ValueError(f"OPTIMADE semantic property {name!r} has an invalid type")
        return value


@dataclass(frozen=True)
class OptimadeReference(OptimadeEntryBackend):
    """Bind an OPTIMADE resource to the standard references schema.

    :param resource: Source resource and its schema provenance.
    """

    entry_type_name: ClassVar[str] = "references"
    entry_type_definition_id: ClassVar[str] = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references"


@dataclass(frozen=True)
class OptimadeFile(OptimadeEntryBackend):
    """Bind an OPTIMADE resource to the standard files schema.

    :param resource: Source resource and its schema provenance.
    """

    entry_type_name: ClassVar[str] = "files"
    entry_type_definition_id: ClassVar[str] = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"


@dataclass(frozen=True)
class OptimadeCalculation(OptimadeEntryBackend):
    """Bind an OPTIMADE resource to the standard calculations schema.

    :param resource: Source resource and its schema provenance.
    """

    entry_type_name: ClassVar[str] = "calculations"
    entry_type_definition_id: ClassVar[str] = "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations"


@dataclass(frozen=True, slots=True, init=False)
class OptimadeEntryView:
    """Present one typed resource backend as a lazy generated record.

    :param backend: Typed backend to present, or an existing compatible view.
    """

    _backend: OptimadeEntryBackend
    _record: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    backend_class: ClassVar[type[OptimadeEntryBackend]]
    record_class: ClassVar[type[Reference] | type[File] | type[Calculation]]

    def __new__(cls, backend: object) -> Self:
        if isinstance(backend, cls):
            return backend
        return object.__new__(cls)

    def __init__(self, backend: "OptimadeEntryBackend | OptimadeEntryView") -> None:
        if isinstance(backend, type(self)):
            return
        if not isinstance(backend, self.backend_class):
            raise TypeError(f"{type(self).__name__} requires {self.backend_class.__name__}")
        object.__setattr__(self, "_backend", backend)
        object.__setattr__(self, "_record", None)

    def __repr__(self) -> str:
        backend = getattr(self, "_backend", None)
        return f"{type(self).__name__}(backend={type(backend).__name__})"

    @property
    def backend(self) -> OptimadeEntryBackend:
        """Return the typed backend behind this view."""

        return self._backend

    def unwrap(self) -> OptimadeResource:
        """Return the exact source resource behind this view."""

        return self._backend.unwrap()

    @property
    def id(self) -> str:
        """Return the resource identifier."""

        return self._backend.id

    @property
    def type(self) -> str:
        """Return the resource type identifier."""

        return self._backend.type

    @property
    def record(self) -> Reference | File | Calculation:
        """Return the lazily materialized canonical record."""

        cached = self._record
        if cached is None:
            cached = self._materialize_record()
            object.__setattr__(self, "_record", cached)
        return cast(Reference | File | Calculation, cached)

    def _materialize_record(self) -> Reference | File | Calculation:
        values: dict[str, object] = {}
        definitions = self._backend.local_schema.properties
        for record_field in fields(self.record_class):
            definition = definitions[record_field.name]
            raw = self._backend.value_by_definition_id(definition.definition_id)
            required = record_field.default is MISSING and record_field.default_factory is MISSING
            if raw is _MISSING:
                if required:
                    raise IncompleteOptimadeResourceError(f"missing semantic property {record_field.name!r}")
                values[record_field.name] = None
                continue
            if raw is None:
                if required or not definition.nullable:
                    raise IncompleteOptimadeResourceError(f"null semantic property {record_field.name!r}")
                values[record_field.name] = None
                continue
            try:
                values[record_field.name] = self._backend.decode_value(definition, raw)
            except (TypeError, ValueError) as exc:
                raise IncompleteOptimadeResourceError(
                    f"invalid semantic property {record_field.name!r}: {exc}"
                ) from exc
        try:
            return self.record_class.create(values)
        except (TypeError, ValueError) as exc:
            raise IncompleteOptimadeResourceError(f"could not construct OPTIMADE record: {exc}") from exc

    def __getattr__(self, name: str) -> object:
        # Record fields are intentionally delegated only after lazy record
        # materialization.  Unknown extension fields stay on ``backend.raw``.
        if name in {field.name for field in fields(self.record_class)}:
            return getattr(self.record, name)
        raise AttributeError(name)


class ReferenceView(OptimadeEntryView):
    """Present an :class:`OptimadeReference` as a lazy canonical view.

    :param backend: Reference backend to present, or an existing compatible view.
    """

    backend_class = OptimadeReference
    record_class = Reference


class FileView(OptimadeEntryView):
    """Present an :class:`OptimadeFile` as a lazy canonical view.

    :param backend: File backend to present, or an existing compatible view.
    """

    backend_class = OptimadeFile
    record_class = File


class CalculationView(OptimadeEntryView):
    """Present an :class:`OptimadeCalculation` as a lazy canonical view.

    :param backend: Calculation backend to present, or an existing compatible view.
    """

    backend_class = OptimadeCalculation
    record_class = Calculation
