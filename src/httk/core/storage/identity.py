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
    """Raise when a projected record graph contains an active cycle.

    :param path: The canonical field path where the cycle was detected.
    :param record_type: The record class being projected when the cycle was found.
    """

    def __init__(self, path: str, record_type: type[Any]) -> None:
        self.path = path
        self.record_type = record_type
        where = path or "<root>"
        super().__init__(f"cyclic storage projection at {where} ({record_type.__qualname__})")


def register_canonical_encoder(python_type: type[Any], encoder: Callable[[Any], Any]) -> None:
    """Register one deterministic encoder for an exact custom Python type.

    Leaf values use exact-type lookup, so a registered encoder for a base class
    does not apply to subclasses. The encoder must return JSON-compatible data.

    :param python_type: The exact custom class to encode.
    :param encoder: The deterministic encoder callable.
    :raises TypeError: If the type or encoder is invalid.
    :raises ValueError: If an encoder is already registered for the class.
    """
    if not isinstance(python_type, type):
        raise TypeError("python_type must be a class")
    if not callable(encoder):
        raise TypeError("encoder must be callable")
    if python_type in _canonical_encoders:
        raise ValueError(f"canonical encoder is already registered for {python_type!r}")
    _canonical_encoders[python_type] = encoder


def resolve_storage_record(source: Any, *, as_record: type[Any] | None = None) -> type[Any]:
    """Resolve the exact record target for ``source`` without constructing it.

    :param source: The source value whose storage record target is requested.
    :param as_record: An explicit record class override, if supplied.
    :return: The validated frozen dataclass record class.
    :raises TypeError: If the resolved target is not a frozen dataclass.
    """
    if as_record is not None:
        target = as_record
    else:
        source_type = type(source)
        target = vars(source_type).get(STORAGE_RECORD_ATTRIBUTE, source_type)
    _validate_record_type(target)
    return target


def project_storage_record(record_type: type[Any], source: Any) -> Mapping[str, object]:
    """Project and validate one record level, returning field values by name.

    Projection classes may declare a source class and classmethod projection;
    otherwise ``source`` must already be an instance of ``record_type``.

    :param record_type: The frozen dataclass record class to project.
    :param source: A record instance or declared projection source.
    :return: Field values present at this record level.
    :raises TypeError: If the record or projection declaration is invalid.
    :raises ValueError: If a projection omits a required field or names an unknown one.
    """
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
    """Return the logical identity name, independent of physical storage naming.

    :param record_type: The record class whose logical identity name is requested.
    :return: The declared identity name or the fully qualified class name.
    :raises TypeError: If ``record_type`` is not a class or has an invalid storage declaration.
    """
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

    Record fields marked with :class:`~httk.core.storage.IdentitySkip`, or
    represented by :class:`~httk.core.storage.stored_property`, are outside the
    content identity. Registered custom encoders apply only to exact leaf types.

    :param obj: The record or projected source to encode.
    :param as_record: An explicit record class override, if supplied.
    :param projector: The record-level projection function.
    :return: Versioned, type-tagged canonical JSON.
    :raises TypeError: If a value or projection cannot be represented.
    :raises ValueError: If a projection is invalid or contains a cycle.
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
    """Return the lowercase SHA-256 content identity of ``obj``.

    The digest covers :func:`~httk.core.storage.identity.canonical_form`, including exact-type leaf
    encodings and excluding fields marked with :class:`~httk.core.storage.markers.IdentitySkip`.

    :param obj: The record or projected source to identify.
    :param as_record: An explicit record class override, if supplied.
    :param projector: The record-level projection function.
    :return: The lowercase SHA-256 hexadecimal digest.
    :raises TypeError: If a value or projection cannot be represented.
    :raises ValueError: If a projection is invalid or contains a cycle.
    """
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
            excluded = _identity_excluded_names(record_type)
            plans = _field_plans(record_type)
            fields = []
            for name in sorted(values):
                if name in excluded:
                    continue
                fields.append([name, self.value(values[name], plans.get(name, _ANY_PLAN), (*path, name))])
            return {
                "fields": fields,
                "identity_name": storage_identity_name(record_type),
                "type": "record",
                "version": 1,
            }
        finally:
            self._active.remove(key)

    def value(self, value: Any, plan: "_AnnotationPlan", path: tuple[str, ...]) -> Any:
        value_type = type(value)
        encoder = _canonical_encoders.get(value_type)
        if encoder is not None:
            return self._custom(value, encoder, path)
        if _canonical_encoders:
            for ancestor in value_type.__mro__[1:]:
                if ancestor in _canonical_encoders:
                    raise TypeError(
                        f"no canonical encoder is registered for {value_type.__name__}; "
                        f"the registered ancestor {ancestor.__name__} cannot be used "
                        "because canonical encoders are exact-type"
                    )
        if value is None:
            return {"type": "null"}
        record_annotation = plan.record_annotation
        if record_annotation is not None:
            _validate_record_type(record_annotation)
            return self.record(value, record_annotation, path)
        if plan.is_list and isinstance(value, list):
            element_plan = plan.list_element_plan or _ANY_PLAN
            return self._container(
                value,
                path,
                lambda: {
                    "type": "list",
                    "value": [
                        self.value(item, element_plan, (*path, f"[{index}]")) for index, item in enumerate(value)
                    ],
                },
            )
        if plan.is_tuple and isinstance(value, (list, tuple)):
            return self._container(
                value,
                path,
                lambda: {
                    "type": "tuple",
                    "value": [
                        self.value(item, _tuple_element_plan(plan, index), (*path, f"[{index}]"))
                        for index, item in enumerate(value)
                    ],
                },
            )
        kind = _leaf_kind(value_type)
        if kind:
            if kind == _LEAF_INT:
                return {"type": "int", "value": str(value)}
            if kind == _LEAF_FRACTION:
                return _rational(value)
            if kind == _LEAF_FRAC:
                return _frac(value)
            if kind == _LEAF_FLOAT:
                if not math.isfinite(value):
                    raise ValueError("nonfinite float values cannot have a content identity")
                return {"type": "float", "value": value.hex()}
            if kind == _LEAF_STR:
                return {"type": "string", "value": value}
            if kind == _LEAF_BOOL:
                return {"type": "bool", "value": value}
            if kind == _LEAF_BYTES:
                return {"type": "bytes", "value": value.hex()}
            if kind == _LEAF_DECIMAL:
                if not value.is_finite():
                    raise ValueError("nonfinite Decimal values cannot have a content identity")
                numerator, denominator = value.as_integer_ratio()
                return _rational(fractions.Fraction(numerator, denominator))
            if kind == _LEAF_DATETIME:
                aware = value.utcoffset() is not None
                instant = value.astimezone(datetime.UTC) if aware else value
                return {
                    "type": "datetime",
                    "value": instant.isoformat(timespec="microseconds"),
                    "aware": aware,
                }
            if kind == _LEAF_DATE:
                return {"type": "date", "value": value.isoformat()}
            return _surd(value)  # _LEAF_SURD
        if plan.is_mapping and isinstance(value, Mapping):
            return self._mapping(value, plan.mapping_value_plan or _ANY_PLAN, path)
        if isinstance(value, Mapping):
            return self._mapping(value, _ANY_PLAN, path)
        if isinstance(value, (list, tuple)):
            return self._container(
                value,
                path,
                lambda: {
                    "type": "list" if isinstance(value, list) else "tuple",
                    "value": [self.value(item, _ANY_PLAN, (*path, f"[{index}]")) for index, item in enumerate(value)],
                },
            )
        if dataclasses.is_dataclass(value):
            raise TypeError(f"field annotation does not declare a frozen record target for {value_type.__name__}")
        raise TypeError(f"unsupported value type for content identity: {value_type.__name__}")

    def _custom(self, value: Any, encoder: Callable[[Any], Any], path: tuple[str, ...]) -> Any:
        encoded = encoder(value)
        _validate_json_compatible(encoded, path)
        python_name = f"{type(value).__module__}.{type(value).__qualname__}"
        return {"type": "custom", "python_type": python_name, "value": self.value(encoded, _ANY_PLAN, path)}

    def _container(self, value: Any, path: tuple[str, ...], encode: Callable[[], Any]) -> Any:
        marker = id(value)
        if marker in self._active_containers:
            raise StorageProjectionCycleError(_format_path(path), type(value))
        self._active_containers.add(marker)
        try:
            return encode()
        finally:
            self._active_containers.remove(marker)

    def _mapping(self, value: Mapping[Any, Any], value_plan: "_AnnotationPlan", path: tuple[str, ...]) -> Any:
        if not all(isinstance(key, str) for key in value):
            raise TypeError("mapping keys must be strings for a content identity")
        return self._container(
            value,
            path,
            lambda: {
                "type": "mapping",
                "value": [[key, self.value(value[key], value_plan, (*path, key))] for key in sorted(value)],
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


# Evaluated annotations are pure per class, and resolving them sits on the hot
# path of every content_id/canonical_form call, so cache per record type. Only
# successful resolutions are cached: the fallback stays a per-call decision, so
# a later successful resolution (e.g. after a partial import completes) is
# still picked up.
_RESOLVED_ANNOTATIONS: dict[type[Any], dict[str, Any]] = {}


def _record_annotations(record_type: type[Any]) -> dict[str, Any]:
    cached = _RESOLVED_ANNOTATIONS.get(record_type)
    if cached is not None:
        return cached
    try:
        resolved = get_type_hints(record_type, include_extras=True)
    except (NameError, TypeError, AttributeError):
        return {field.name: field.type for field in dataclasses.fields(record_type)}
    _RESOLVED_ANNOTATIONS[record_type] = resolved
    return resolved


def _unwrap_annotation(annotation: Any) -> Any:
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if get_origin(annotation) in (Union, types.UnionType):
        non_none = tuple(argument for argument in get_args(annotation) if argument is not type(None))
        if len(non_none) == 1:
            return _unwrap_annotation(non_none[0])
    return annotation


# --- Type-invariant introspection caches -------------------------------------
#
# Memory contract: every cache below is keyed EXCLUSIVELY on a record class or a
# runtime leaf type. Their combined size therefore scales only with the number
# of distinct record classes and leaf value types the process encounters, never
# with the number of record instances, field values, or content_id calls. The
# nested plans held inside ``_FIELD_PLANS`` scale with the annotation structure
# of those classes (still bounded by the classes themselves), and ``_leaf_kind``
# adds one small int per leaf type. Nothing here is keyed per instance/value.

# Leaf-value kinds decided by a value's exact runtime type alone. Resolving them
# once per type replaces the per-value ``isinstance`` ladder in ``_Encoder.value``.
_LEAF_NOT = 0
_LEAF_BOOL = 1
_LEAF_INT = 2
_LEAF_FRACTION = 3
_LEAF_DECIMAL = 4
_LEAF_FLOAT = 5
_LEAF_STR = 6
_LEAF_BYTES = 7
_LEAF_DATETIME = 8
_LEAF_DATE = 9
_LEAF_FRAC = 10
_LEAF_SURD = 11

# (FracScalar, FracVector, SurdScalar, SurdVector), imported lazily once to keep
# the isinstance/leaf-codec dispatch off the local-import path per value.
_VECTOR_TYPES: tuple[type[Any], type[Any], type[Any], type[Any]] | None = None

_LEAF_KINDS: dict[type[Any], int] = {}
_FIELD_PLANS: dict[type[Any], dict[str, "_AnnotationPlan"]] = {}
_IDENTITY_EXCLUDED: dict[type[Any], frozenset[str]] = {}


def _vector_types() -> tuple[type[Any], type[Any], type[Any], type[Any]]:
    global _VECTOR_TYPES
    if _VECTOR_TYPES is None:
        from ..vectors import FracScalar, FracVector, SurdScalar, SurdVector

        _VECTOR_TYPES = (FracScalar, FracVector, SurdScalar, SurdVector)
    return _VECTOR_TYPES


def _compute_leaf_kind(value_type: type[Any]) -> int:
    if issubclass(value_type, bool):
        return _LEAF_BOOL
    if issubclass(value_type, int):
        return _LEAF_INT
    if issubclass(value_type, fractions.Fraction):
        return _LEAF_FRACTION
    if issubclass(value_type, decimal.Decimal):
        return _LEAF_DECIMAL
    if issubclass(value_type, float):
        return _LEAF_FLOAT
    if issubclass(value_type, str):
        return _LEAF_STR
    if issubclass(value_type, bytes):
        return _LEAF_BYTES
    if issubclass(value_type, datetime.datetime):
        return _LEAF_DATETIME
    if issubclass(value_type, datetime.date):
        return _LEAF_DATE
    vectors = _vector_types()
    if issubclass(value_type, vectors[:2]):
        return _LEAF_FRAC
    if issubclass(value_type, vectors[2:]):
        return _LEAF_SURD
    return _LEAF_NOT


def _leaf_kind(value_type: type[Any]) -> int:
    kind = _LEAF_KINDS.get(value_type)
    if kind is not None:
        return kind
    kind = _compute_leaf_kind(value_type)
    _LEAF_KINDS[value_type] = kind
    return kind


class _AnnotationPlan:
    """The static, per-annotation dispatch decision hoisted out of ``value``.

    Every attribute is derived from the field/element annotation alone: the
    ``get_origin``/``get_args``/``_unwrap_annotation`` work and the record vs
    typed-container decision that :meth:`_Encoder.value` would otherwise redo for
    every value carrying this annotation. Child plans for typed container
    elements are precomputed so recursion never revisits annotation reflection.
    """

    __slots__ = (
        "is_list",
        "is_mapping",
        "is_tuple",
        "list_element_plan",
        "mapping_value_plan",
        "record_annotation",
        "tuple_element_plans",
        "tuple_variadic",
    )

    def __init__(
        self,
        record_annotation: type[Any] | None,
        is_list: bool,
        is_tuple: bool,
        is_mapping: bool,
        list_element_plan: "_AnnotationPlan | None",
        tuple_element_plans: "tuple[_AnnotationPlan, ...]",
        tuple_variadic: bool,
        mapping_value_plan: "_AnnotationPlan | None",
    ) -> None:
        self.record_annotation = record_annotation
        self.is_list = is_list
        self.is_tuple = is_tuple
        self.is_mapping = is_mapping
        self.list_element_plan = list_element_plan
        self.tuple_element_plans = tuple_element_plans
        self.tuple_variadic = tuple_variadic
        self.mapping_value_plan = mapping_value_plan


def _build_plan(annotation: Any) -> _AnnotationPlan:
    unwrapped = _unwrap_annotation(annotation)
    origin = get_origin(unwrapped)
    args = get_args(unwrapped)
    record_annotation = unwrapped if isinstance(unwrapped, type) and dataclasses.is_dataclass(unwrapped) else None
    is_list = origin is list
    is_tuple = origin is tuple
    is_mapping = isinstance(origin, type) and issubclass(origin, Mapping)
    list_element_plan: _AnnotationPlan | None = None
    tuple_element_plans: tuple[_AnnotationPlan, ...] = ()
    tuple_variadic = False
    mapping_value_plan: _AnnotationPlan | None = None
    if record_annotation is None:
        if is_list:
            list_element_plan = _build_plan(args[0]) if args else _ANY_PLAN
        elif is_tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                tuple_variadic = True
                tuple_element_plans = (_build_plan(args[0]),)
            else:
                tuple_element_plans = tuple(_build_plan(argument) for argument in args)
        elif is_mapping:
            mapping_value_plan = _build_plan(args[1]) if len(args) > 1 else _ANY_PLAN
    return _AnnotationPlan(
        record_annotation,
        is_list,
        is_tuple,
        is_mapping,
        list_element_plan,
        tuple_element_plans,
        tuple_variadic,
        mapping_value_plan,
    )


# The shared plan for untyped values (``Any``/missing annotation), which also
# serves list/tuple/mapping elements whose annotation is unparameterized.
_ANY_PLAN = _build_plan(Any)


def _tuple_element_plan(plan: _AnnotationPlan, index: int) -> _AnnotationPlan:
    plans = plan.tuple_element_plans
    if plan.tuple_variadic:
        return plans[0]
    return plans[index] if index < len(plans) else _ANY_PLAN


def _field_plans(record_type: type[Any]) -> dict[str, _AnnotationPlan]:
    cached = _FIELD_PLANS.get(record_type)
    if cached is not None:
        return cached
    annotations = _record_annotations(record_type)
    plans = {name: _build_plan(annotation) for name, annotation in annotations.items()}
    # Only cache alongside a resolved annotation set (see ``_record_annotations``):
    # a plan built from the string-annotation fallback must not outlive it.
    if record_type in _RESOLVED_ANNOTATIONS:
        _FIELD_PLANS[record_type] = plans
    return plans


def _identity_excluded_names(record_type: type[Any]) -> frozenset[str]:
    cached = _IDENTITY_EXCLUDED.get(record_type)
    if cached is not None:
        return cached
    _record_annotations(record_type)  # trigger annotation resolution before deciding to cache
    excluded = frozenset(
        field.name for field in dataclasses.fields(record_type) if _identity_excluded(record_type, field.name)
    )
    if record_type in _RESOLVED_ANNOTATIONS:
        _IDENTITY_EXCLUDED[record_type] = excluded
    return excluded


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


def _rational(value: fractions.Fraction) -> dict[str, Any]:
    return {"type": "rational", "value": [value.numerator, value.denominator]}


def _frac(value: Any) -> dict[str, Any]:
    frac_scalar = _vector_types()[0]
    simplified = value.simplify()

    def noms(node: Any) -> Any:
        return [noms(item) for item in node] if isinstance(node, tuple) else node

    return {
        "type": "frac_scalar" if isinstance(value, frac_scalar) else "frac_vector",
        "value": {"denominator": simplified.denom, "nominators": noms(simplified.noms)},
    }


def _surd(value: Any) -> dict[str, Any]:
    surd_scalar = _vector_types()[2]
    return {
        "type": "surd_scalar" if isinstance(value, surd_scalar) else "surd_vector",
        "dimension": list(value.dim),
        "value": [[radicand, _frac(value.coefficient(radicand))] for radicand in value.radicands],
    }
