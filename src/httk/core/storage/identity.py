"""Canonical content identity for plain and projected frozen records."""

import dataclasses
import datetime
import decimal
import fractions
import hashlib
import json
import math
import types
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

from .markers import STORAGE_INFO_ATTRIBUTE, IdentitySkip, Skip, StorageInfo, stored_property

__all__ = [
    "StorageProjectionCycleError",
    "canonical_form",
    "content_id",
    "project_storage_record",
    "register_canonical_encoder",
    "resolve_storage_record",
    "storage_identity_name",
]

STORAGE_RECORD_ATTRIBUTE = "__httk_storage_record__"
CANONICAL_SOURCE_ATTRIBUTE = "__httk_canonical_source__"
CANONICAL_PROJECT_ATTRIBUTE = "__httk_project__"
_MISSING = object()
_canonical_encoders: dict[type[Any], Callable[[Any], Any]] = {}


class StorageProjectionCycleError(ValueError):
    """Raised when a projected record graph contains an active cycle."""

    def __init__(self, path: str, record_type: type[Any]) -> None:
        self.path = path
        self.record_type = record_type
        where = path or "<root>"
        super().__init__(f"cyclic storage projection at {where} ({record_type.__qualname__})")


def register_canonical_encoder(python_type: type[Any], encoder: Callable[[Any], Any]) -> None:
    """Register one deterministic encoder for an exact custom Python type."""
    if not isinstance(python_type, type):
        raise TypeError("python_type must be a class")
    if not callable(encoder):
        raise TypeError("encoder must be callable")
    if python_type in _canonical_encoders:
        raise ValueError(f"canonical encoder is already registered for {python_type!r}")
    _canonical_encoders[python_type] = encoder


def resolve_storage_record(source: Any, *, as_record: type[Any] | None = None) -> type[Any]:
    """Resolve the exact record target for ``source`` without constructing it."""
    if as_record is not None:
        target = as_record
    else:
        source_type = type(source)
        target = vars(source_type).get(STORAGE_RECORD_ATTRIBUTE, source_type)
    _validate_record_type(target)
    return target


def project_storage_record(record_type: type[Any], source: Any) -> Mapping[str, object]:
    """Project and validate one record level, returning field values by name."""
    _validate_record_type(record_type)
    fields = dataclasses.fields(record_type)
    source_marker = _record_declaration(record_type, CANONICAL_SOURCE_ATTRIBUTE)
    if source_marker is not _MISSING:
        if not isinstance(source_marker, type):
            raise TypeError(f"{record_type.__name__}.{CANONICAL_SOURCE_ATTRIBUTE} must be a class")
        descriptor = _record_declaration(record_type, CANONICAL_PROJECT_ATTRIBUTE)
        if not isinstance(descriptor, classmethod):
            raise TypeError(f"{record_type.__name__}.{CANONICAL_PROJECT_ATTRIBUTE} must be a classmethod")
        if isinstance(source, record_type):
            values = {field.name: getattr(source, field.name) for field in fields}
        else:
            if not isinstance(source, source_marker):
                raise TypeError(
                    f"{record_type.__name__}.{CANONICAL_SOURCE_ATTRIBUTE} expects "
                    f"{getattr(source_marker, '__name__', source_marker)!r}, got {type(source).__name__}"
                )
            projected = descriptor.__get__(None, record_type)(source)
            if not isinstance(projected, Mapping):
                raise TypeError(f"{record_type.__name__}.{CANONICAL_PROJECT_ATTRIBUTE} must return a Mapping")
            values = dict(projected)
            if not all(isinstance(name, str) for name in values):
                raise TypeError(f"projection for {record_type.__name__} must use string field names")
            known = {field.name for field in fields}
            unknown = set(values) - known
            if unknown:
                raise ValueError(
                    f"projection for {record_type.__name__} names unknown fields: {', '.join(sorted(unknown))}"
                )
    else:
        if not isinstance(source, record_type):
            raise TypeError(
                f"{record_type.__name__} is not a projection for {type(source).__name__}; "
                f"declare {CANONICAL_SOURCE_ATTRIBUTE} and {CANONICAL_PROJECT_ATTRIBUTE}"
            )
        values = {field.name: getattr(source, field.name) for field in fields}

    result: dict[str, object] = {}
    for field in fields:
        if field.name not in values:
            if _field_has_marker(record_type, field.name, field.type, Skip):
                continue
            raise ValueError(f"projection for {record_type.__name__} omitted field {field.name!r}")
        result[field.name] = values[field.name]
    return result


def storage_identity_name(record_type: type[Any]) -> str:
    """Return the logical identity name, independent of physical storage naming."""
    if not isinstance(record_type, type):
        raise TypeError("record_type must be a class")
    for base in record_type.__mro__:
        declared = vars(base).get(STORAGE_INFO_ATTRIBUTE)
        if declared is None:
            continue
        if not isinstance(declared, StorageInfo):
            raise TypeError(f"{base.__name__}.{STORAGE_INFO_ATTRIBUTE} must be a StorageInfo")
        if declared.identity_name is not None:
            return declared.identity_name
    return f"{record_type.__module__}.{record_type.__qualname__}"


def canonical_form(
    obj: Any,
    *,
    as_record: type[Any] | None = None,
    projector: Callable[[type[Any], Any], Mapping[str, object]] = project_storage_record,
) -> str:
    """Return the versioned, type-tagged canonical JSON for a record value.

    Storage integrations may supply a caching ``projector`` to reuse the exact
    per-record mappings traversed while computing identity.
    """
    encoder = _Encoder(projector)
    target = resolve_storage_record(obj, as_record=as_record)
    value = encoder.record(obj, target, ())
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def content_id(
    obj: Any,
    *,
    as_record: type[Any] | None = None,
    projector: Callable[[type[Any], Any], Mapping[str, object]] = project_storage_record,
) -> str:
    """Return the lowercase SHA-256 content identity of ``obj``."""
    return hashlib.sha256(canonical_form(obj, as_record=as_record, projector=projector).encode("utf-8")).hexdigest()


class _Encoder:
    def __init__(self, projector: Callable[[type[Any], Any], Mapping[str, object]]) -> None:
        self._projector = projector
        self._active: set[tuple[type[Any], int]] = set()
        self._active_containers: set[int] = set()

    def record(self, source: Any, record_type: type[Any], path: tuple[str, ...]) -> dict[str, Any]:
        key = (record_type, id(source))
        if key in self._active:
            raise StorageProjectionCycleError(_format_path(path), record_type)
        self._active.add(key)
        try:
            values = self._projector(record_type, source)
            annotations = _record_annotations(record_type)
            fields = []
            for name in sorted(values):
                if _identity_excluded(record_type, name):
                    continue
                fields.append([name, self.value(values[name], annotations.get(name), (*path, name))])
            return {
                "fields": fields,
                "identity_name": storage_identity_name(record_type),
                "type": "record",
                "version": 1,
            }
        finally:
            self._active.remove(key)

    def value(self, value: Any, annotation: Any, path: tuple[str, ...]) -> Any:
        encoder = _canonical_encoders.get(type(value))
        if encoder is not None:
            return self._custom(value, encoder, path)
        for ancestor in type(value).__mro__[1:]:
            if ancestor in _canonical_encoders:
                raise TypeError(
                    f"no canonical encoder is registered for {type(value).__name__}; "
                    f"the registered ancestor {ancestor.__name__} cannot be used because canonical encoders are exact-type"
                )
        if value is None:
            return {"type": "null"}
        annotation = _unwrap_annotation(annotation)
        origin = get_origin(annotation)
        args = get_args(annotation)
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            _validate_record_type(annotation)
            return self.record(value, annotation, path)
        if origin is list and isinstance(value, list):
            element_annotation = args[0] if args else Any
            return self._container(
                value,
                path,
                lambda: {
                    "type": "list",
                    "value": [
                        self.value(item, element_annotation, (*path, f"[{index}]")) for index, item in enumerate(value)
                    ],
                },
            )
        if origin is tuple and isinstance(value, (list, tuple)):
            element_annotations = args
            if len(element_annotations) == 2 and element_annotations[1] is Ellipsis:
                element_annotations = (element_annotations[0],) * len(value)
            return self._container(
                value,
                path,
                lambda: {
                    "type": "tuple",
                    "value": [
                        self.value(
                            item,
                            element_annotations[index] if index < len(element_annotations) else Any,
                            (*path, f"[{index}]"),
                        )
                        for index, item in enumerate(value)
                    ],
                },
            )
        if isinstance(value, bool):
            return {"type": "bool", "value": value}
        if isinstance(value, int):
            return {"type": "int", "value": str(value)}
        if isinstance(value, fractions.Fraction):
            return _rational(value)
        if isinstance(value, decimal.Decimal):
            if not value.is_finite():
                raise ValueError("nonfinite Decimal values cannot have a content identity")
            numerator, denominator = value.as_integer_ratio()
            return _rational(fractions.Fraction(numerator, denominator))
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("nonfinite float values cannot have a content identity")
            return {"type": "float", "value": value.hex()}
        if isinstance(value, str):
            return {"type": "string", "value": value}
        if isinstance(value, bytes):
            return {"type": "bytes", "value": value.hex()}
        if isinstance(value, datetime.datetime):
            aware = value.utcoffset() is not None
            instant = value.astimezone(datetime.UTC) if aware else value
            return {
                "type": "datetime",
                "value": instant.isoformat(timespec="microseconds"),
                "aware": aware,
            }
        if isinstance(value, datetime.date):
            return {"type": "date", "value": value.isoformat()}
        if _is_frac(value):
            return _frac(value)
        if _is_surd(value):
            return _surd(value)
        if isinstance(origin, type) and issubclass(origin, Mapping) and isinstance(value, Mapping):
            value_annotation = args[1] if len(args) > 1 else Any
            return self._mapping(value, value_annotation, path)
        if isinstance(value, Mapping):
            return self._mapping(value, Any, path)
        if isinstance(value, (list, tuple)):
            return self._container(
                value,
                path,
                lambda: {
                    "type": "list" if isinstance(value, list) else "tuple",
                    "value": [self.value(item, Any, (*path, f"[{index}]")) for index, item in enumerate(value)],
                },
            )
        if dataclasses.is_dataclass(value):
            raise TypeError(f"field annotation does not declare a frozen record target for {type(value).__name__}")
        raise TypeError(f"unsupported value type for content identity: {type(value).__name__}")

    def _custom(self, value: Any, encoder: Callable[[Any], Any], path: tuple[str, ...]) -> Any:
        encoded = encoder(value)
        _validate_json_compatible(encoded, path)
        python_name = f"{type(value).__module__}.{type(value).__qualname__}"
        return {"type": "custom", "python_type": python_name, "value": self.value(encoded, Any, path)}

    def _container(self, value: Any, path: tuple[str, ...], encode: Callable[[], Any]) -> Any:
        marker = id(value)
        if marker in self._active_containers:
            raise StorageProjectionCycleError(_format_path(path), type(value))
        self._active_containers.add(marker)
        try:
            return encode()
        finally:
            self._active_containers.remove(marker)

    def _mapping(self, value: Mapping[Any, Any], value_annotation: Any, path: tuple[str, ...]) -> Any:
        if not all(isinstance(key, str) for key in value):
            raise TypeError("mapping keys must be strings for a content identity")
        return self._container(
            value,
            path,
            lambda: {
                "type": "mapping",
                "value": [[key, self.value(value[key], value_annotation, (*path, key))] for key in sorted(value)],
            },
        )


def _validate_record_type(record_type: Any) -> None:
    if not isinstance(record_type, type) or not dataclasses.is_dataclass(record_type):
        raise TypeError("storage record target must be a dataclass")
    params = getattr(record_type, "__dataclass_params__", None)
    if params is None or not params.frozen:
        raise TypeError(f"{record_type.__name__} must be a frozen dataclass")


def _record_declaration(record_type: type[Any], name: str) -> Any:
    for base in record_type.__mro__:
        if name in vars(base):
            return vars(base)[name]
    return _MISSING


def _record_annotations(record_type: type[Any]) -> dict[str, Any]:
    try:
        return get_type_hints(record_type, include_extras=True)
    except (NameError, TypeError, AttributeError):
        return {field.name: field.type for field in dataclasses.fields(record_type)}


def _unwrap_annotation(annotation: Any) -> Any:
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if get_origin(annotation) in (Union, types.UnionType):
        non_none = tuple(argument for argument in get_args(annotation) if argument is not type(None))
        if len(non_none) == 1:
            return _unwrap_annotation(non_none[0])
    return annotation


def _field_markers(record_type: type[Any], name: str, annotation: Any = None) -> tuple[Any, ...]:
    if annotation is None:
        annotation = _record_annotations(record_type).get(name)
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        return args[1:] + _field_markers(record_type, name, args[0])
    if origin in (Union, types.UnionType):
        return tuple(
            marker
            for argument in get_args(annotation)
            for marker in _field_markers(record_type, name, argument)
            if argument is not type(None)
        )
    return ()


def _field_has_marker(record_type: type[Any], name: str, annotation: Any, marker_type: type[Any]) -> bool:
    return any(isinstance(marker, marker_type) for marker in _field_markers(record_type, name, annotation))


def _identity_excluded(record_type: type[Any], name: str, annotation: Any = None) -> bool:
    member = next((vars(base).get(name) for base in record_type.__mro__ if name in vars(base)), None)
    if isinstance(member, stored_property):
        return True
    return _field_has_marker(record_type, name, annotation, Skip) or _field_has_marker(
        record_type, name, annotation, IdentitySkip
    )


def _validate_json_compatible(value: Any, path: tuple[str, ...], active: set[int] | None = None) -> None:
    """Validate the deliberately small result contract of custom encoders."""
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite float values cannot have a content identity")
        return
    if active is None:
        active = set()
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            raise StorageProjectionCycleError(_format_path(path), type(value))
        if not all(isinstance(key, str) for key in value):
            raise TypeError("custom canonical encoder mappings must use string keys")
        active.add(marker)
        try:
            for key, item in value.items():
                _validate_json_compatible(item, (*path, key), active)
        finally:
            active.remove(marker)
        return
    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active:
            raise StorageProjectionCycleError(_format_path(path), type(value))
        active.add(marker)
        try:
            for index, item in enumerate(value):
                _validate_json_compatible(item, (*path, f"[{index}]"), active)
        finally:
            active.remove(marker)
        return
    raise TypeError("custom canonical encoder must return JSON-compatible scalar, sequence, or mapping")


def _format_path(path: tuple[str, ...]) -> str:
    result = ""
    for part in path:
        result += part if part.startswith("[") else ("." if result else "") + part
    return result


def _is_frac(value: Any) -> bool:
    from ..vectors import FracScalar, FracVector

    return isinstance(value, (FracScalar, FracVector))


def _is_surd(value: Any) -> bool:
    from ..vectors import SurdScalar, SurdVector

    return isinstance(value, (SurdScalar, SurdVector))


def _rational(value: fractions.Fraction) -> dict[str, Any]:
    return {"type": "rational", "value": [value.numerator, value.denominator]}


def _frac(value: Any) -> dict[str, Any]:
    from ..vectors import FracScalar

    simplified = value.simplify()

    def noms(node: Any) -> Any:
        return [noms(item) for item in node] if isinstance(node, tuple) else node

    return {
        "type": "frac_scalar" if isinstance(value, FracScalar) else "frac_vector",
        "value": {"denominator": simplified.denom, "nominators": noms(simplified.noms)},
    }


def _surd(value: Any) -> dict[str, Any]:
    from ..vectors import SurdScalar

    return {
        "type": "surd_scalar" if isinstance(value, SurdScalar) else "surd_vector",
        "dimension": list(value.dim),
        "value": [[radicand, _frac(value.coefficient(radicand))] for radicand in value.radicands],
    }
