import datetime
import math
from dataclasses import dataclass, fields
from fractions import Fraction
from typing import Annotated, ClassVar

import pytest

from httk.core import FracScalar, FracVector, SurdScalar, SurdVector
from httk.core.register import (
    entry_family_info,
    entry_record_info,
    known_entry_families,
    known_entry_records,
    register_entry_family,
    register_entry_record,
    resolve_entry_family,
    resolve_entry_record,
)
from httk.core.storage import (
    IdentitySkip,
    Skip,
    StorageInfo,
    StorageProjectionCycleError,
    canonical_form,
    content_id,
    register_canonical_encoder,
    resolve_storage_record,
    storage_identity_name,
)


@dataclass(frozen=True)
class _Plain:
    value: object


@dataclass(frozen=True)
class _CycleNode:
    child: "_CycleNode | None"


@dataclass(frozen=True)
class _Golden:
    __httk_storage__ = StorageInfo(identity_name="golden.record")
    count: int
    ratio: Fraction
    labels: tuple[str, ...]


@dataclass
class _MutableBacking:
    value: int


class _NotABacking:
    pass


def test_plain_identity_tags_bool_int_and_signed_zero() -> None:
    assert content_id(_Plain(True)) != content_id(_Plain(1))
    assert content_id(_Plain(0.0)) != content_id(_Plain(-0.0))
    assert '"version":1' in canonical_form(_Plain(1))
    assert '"type":"int"' in canonical_form(_Plain(1))
    with pytest.raises(ValueError, match="nonfinite"):
        canonical_form(_Plain(math.nan))


def test_skip_and_identity_skip_are_excluded() -> None:
    @dataclass(frozen=True)
    class Record:
        value: int
        scratch: Annotated[str, Skip()]
        cache: Annotated[str, IdentitySkip()]

    assert content_id(Record(1, "a", "x")) == content_id(Record(1, "b", "y"))


def test_skip_markers_inside_optional_annotations_are_honored() -> None:
    @dataclass(frozen=True)
    class Record:
        value: int
        skip_outer: Annotated[str | None, Skip()]
        skip_inner: Annotated[str, IdentitySkip()] | None

    assert content_id(Record(1, "a", "x")) == content_id(Record(1, "b", "y"))


def test_projected_identity_skip_field_is_required_but_skip_may_be_omitted() -> None:
    @dataclass(frozen=True)
    class Source:
        value: int

    @dataclass(frozen=True)
    class Record:
        value: int
        metadata: Annotated[str, IdentitySkip()]
        scratch: Annotated[str, Skip()]

        __httk_canonical_source__ = Source

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value, "scratch": "unused"}

    with pytest.raises(ValueError, match="metadata"):
        canonical_form(Source(1), as_record=Record)


def test_identity_name_inheritance_is_independent_of_storage_name() -> None:
    with pytest.raises(ValueError, match="surrounding whitespace"):
        StorageInfo(identity_name=" logical")

    @dataclass(frozen=True)
    class Base:
        __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
            storage_name="physical_base", identity_name="logical-base"
        )
        value: int

    @dataclass(frozen=True)
    class Child(Base):
        __httk_storage__ = StorageInfo(storage_name="physical-child")

    assert storage_identity_name(Child) == "logical-base"
    assert StorageInfo(identity_name="x", storage_name="one") != StorageInfo(identity_name="x", storage_name="two")

    @dataclass(frozen=True)
    class Other:
        __httk_storage__ = StorageInfo(storage_name="different", identity_name="logical-base")
        value: int

    assert content_id(Child(1)) == content_id(Other(1))


def test_binding_is_exact_class_only() -> None:
    @dataclass(frozen=True)
    class Record:
        value: int

    @dataclass(frozen=True)
    class Source:
        value: int

        __httk_storage_record__ = Record

    @dataclass(frozen=True)
    class Child(Source):
        pass

    assert resolve_storage_record(Source(1)) is Record
    assert resolve_storage_record(Child(1)) is Child


def test_nested_projection_does_not_construct_records_and_as_record_is_alternate() -> None:
    @dataclass(frozen=True)
    class ChildSource:
        value: int

    @dataclass(frozen=True)
    class AlternateRecord:
        value: int

        __httk_canonical_source__ = ChildSource

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value + 100}

    @dataclass(frozen=True)
    class ChildRecord:
        value: int

        __httk_canonical_source__ = ChildSource

        def __post_init__(self) -> None:
            raise AssertionError("canonical projection must not construct a record")

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value}

    @dataclass(frozen=True)
    class ParentSource:
        child: ChildSource
        children: list[ChildSource]
        pair: tuple[ChildSource, ChildSource]
        mapping: dict[str, ChildSource]

    @dataclass(frozen=True)
    class ParentRecord:
        child: ChildRecord
        children: list[ChildRecord]
        pair: tuple[ChildRecord, ChildRecord]
        mapping: dict[str, ChildRecord]

        __httk_canonical_source__ = ParentSource

        @classmethod
        def __httk_project__(cls, source):
            return {
                "child": source.child,
                "children": source.children,
                "pair": source.pair,
                "mapping": source.mapping,
            }

    ChildSource.__httk_storage_record__ = AlternateRecord
    ParentSource.__httk_storage_record__ = ParentRecord
    source = ParentSource(
        ChildSource(4),
        [ChildSource(5)],
        (ChildSource(6), ChildSource(7)),
        {"child": ChildSource(8)},
    )
    form = canonical_form(source, as_record=ParentRecord)
    assert "ChildRecord" in form
    assert "AlternateRecord" not in form
    assert content_id(ChildSource(4), as_record=ChildRecord)


def test_canonical_projector_can_cache_each_traversed_record_level() -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    @dataclass(frozen=True)
    class Parent:
        child: Child

    calls: list[tuple[type, object]] = []

    def caching_projector(record_type, source):
        calls.append((record_type, source))
        return {field.name: getattr(source, field.name) for field in fields(record_type)}

    value = Parent(Child(3))
    assert content_id(value, projector=caching_projector)
    assert calls == [(Parent, value), (Child, value.child)]


def test_projection_declarations_are_inherited_by_storage_only_record_subclasses() -> None:
    @dataclass(frozen=True)
    class Source:
        value: int

    @dataclass(frozen=True)
    class BaseRecord:
        value: int
        __httk_storage__ = StorageInfo(storage_name="base", identity_name="logical")
        __httk_canonical_source__ = Source

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value}

    @dataclass(frozen=True)
    class ChildRecord(BaseRecord):
        __httk_storage__ = StorageInfo(storage_name="child")

    source = Source(9)
    assert storage_identity_name(ChildRecord) == "logical"
    assert content_id(source, as_record=BaseRecord) == content_id(source, as_record=ChildRecord)


def test_shared_dag_is_allowed_and_cycles_report_a_field_path() -> None:
    @dataclass(frozen=True)
    class Pair:
        left: _CycleNode
        right: _CycleNode

    leaf = _CycleNode(None)
    parent = _CycleNode(leaf)
    assert content_id(Pair(leaf, leaf))
    with pytest.raises(StorageProjectionCycleError, match="child.child"):
        object.__setattr__(leaf, "child", leaf)
        canonical_form(parent)


def test_list_and_mapping_cycles_raise_projection_cycle_errors() -> None:
    @dataclass(frozen=True)
    class ContainerRecord:
        items: list[object]
        values: dict[str, object]

    items: list[object] = []
    values: dict[str, object] = {}
    items.append(items)
    values["self"] = values
    with pytest.raises(StorageProjectionCycleError, match=r"items\[0\]"):
        canonical_form(ContainerRecord(items, {}))
    with pytest.raises(StorageProjectionCycleError, match=r"values\.self"):
        canonical_form(ContainerRecord([], values))


def test_exact_numeric_and_datetime_values_are_stable() -> None:
    @dataclass(frozen=True)
    class Values:
        fraction: Fraction
        scalar: FracScalar
        vector: FracVector
        surd: SurdScalar
        surd_vector: SurdVector
        when: datetime.datetime

    value = Values(
        Fraction(2, 3),
        FracScalar(2, 3),
        FracVector.create([[Fraction(1, 2), 2]]),
        SurdVector.sqrt_of(2),
        SurdVector.create([1, 2]),
        datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
    )
    equivalent = Values(
        Fraction(2, 3),
        FracScalar(4, 6),
        FracVector.create([[Fraction(1, 2), Fraction(4, 2)]]),
        SurdVector.sqrt_of(2),
        SurdVector.create([1, 2]),
        datetime.datetime(2025, 12, 31, 22, tzinfo=datetime.UTC),
    )
    assert content_id(value) == content_id(equivalent)


def test_custom_canonical_encoder_is_deterministic_and_strict() -> None:
    class Scalar:
        def __init__(self, value: int) -> None:
            self.value = value

    register_canonical_encoder(Scalar, lambda value: {"z": value.value, "a": [value.value]})
    assert content_id(_Plain(Scalar(3))) == content_id(_Plain(Scalar(3)))
    assert f'"python_type":"{Scalar.__module__}.{Scalar.__qualname__}"' in canonical_form(_Plain(Scalar(3)))

    class ChildScalar(Scalar):
        pass

    with pytest.raises(TypeError, match="ChildScalar.*Scalar.*exact-type"):
        content_id(_Plain(ChildScalar(3)))

    class IntScalar(int):
        pass

    register_canonical_encoder(IntScalar, lambda value: {"integer": int(value)})
    assert '"type":"custom"' in canonical_form(_Plain(IntScalar(3)))
    with pytest.raises(ValueError, match="already registered"):
        register_canonical_encoder(Scalar, lambda value: value.value)


def test_canonical_version_one_golden_vector() -> None:
    form = canonical_form(_Golden(7, Fraction(2, 3), ("a", "b")))
    assert form == (
        '{"fields":[["count",{"type":"int","value":"7"}],'
        '["labels",{"type":"tuple","value":[{"type":"string","value":"a"},'
        '{"type":"string","value":"b"}]}],["ratio",{"type":"rational","value":[2,3]}]],'
        '"identity_name":"golden.record","type":"record","version":1}'
    )
    assert (
        content_id(_Golden(7, Fraction(2, 3), ("a", "b")))
        == "30971f03da2bd1990a5d5a7d7849c23195d5adca2973a882bde5abd39bee6a7d"
    )


class _Family:
    pass


@dataclass(frozen=True)
class _Backing:
    value: int


def test_entry_family_and_backing_registries_are_lazy_and_strict() -> None:
    family_name = "identity-test-family"
    backing_name = "identity-test-backing"
    family_ref = f"{__name__}:_Family"
    backing_ref = f"{__name__}:_Backing"
    register_entry_family(name=family_name, family=family_ref, definition_id="definition")
    register_entry_record(name=backing_name, family=family_name, record=backing_ref)
    assert family_name in known_entry_families()
    assert backing_name in known_entry_records(family_name)
    assert entry_family_info(family_name) == (family_ref, "definition")
    assert entry_record_info(backing_name) == (backing_ref, family_name, None)
    assert resolve_entry_family(family_name) is _Family
    assert resolve_entry_record(backing_name) is _Backing
    mutable_name = "identity-test-mutable-backing"
    plain_name = "identity-test-plain-backing"
    register_entry_record(name=mutable_name, family=family_name, record=f"{__name__}:_MutableBacking")
    register_entry_record(name=plain_name, family=family_name, record=f"{__name__}:_NotABacking")
    with pytest.raises(TypeError, match="non-frozen dataclass"):
        resolve_entry_record(mutable_name)
    with pytest.raises(TypeError, match="non-frozen dataclass"):
        resolve_entry_record(plain_name)
    assert {backing_name, mutable_name, plain_name} <= set(known_entry_records(family_name))
    with pytest.raises(ValueError, match="strict"):
        register_entry_family(name="bad-identity-family", family="not-a-reference")
    with pytest.raises(ValueError, match="No entry family"):
        register_entry_record(name="bad-identity-record", family="missing", record=backing_ref)
