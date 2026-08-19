import datetime
import decimal
import json
import math
import pickle
import random
import sys
from dataclasses import dataclass, fields
from fractions import Fraction
from typing import Annotated, Any, ClassVar, cast

import pytest

import httk.core.storage.identity as identity_module
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
class _ListCycleNode:
    children: list["_ListCycleNode"]


@dataclass(frozen=True)
class _MappingCycleNode:
    children: dict[str, "_MappingCycleNode"]


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


@dataclass(frozen=True)
class _PickleRecord:
    value: int


def test_plain_identity_tags_bool_int_and_signed_zero() -> None:
    assert content_id(_Plain(True)) != content_id(_Plain(1))
    assert content_id(_Plain(0.0)) != content_id(_Plain(-0.0))
    assert '"version":2' in canonical_form(_Plain(1))
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

    cast(Any, ChildSource).__httk_storage_record__ = AlternateRecord
    cast(Any, ParentSource).__httk_storage_record__ = ParentRecord
    source = ParentSource(
        ChildSource(4),
        [ChildSource(5)],
        (ChildSource(6), ChildSource(7)),
        {"child": ChildSource(8)},
    )
    form = canonical_form(source, as_record=ParentRecord)
    encoded_fields = dict(json.loads(form)["fields"])
    refs = (
        encoded_fields["child"],
        encoded_fields["children"]["value"][0],
        encoded_fields["pair"]["value"][0],
        encoded_fields["pair"]["value"][1],
        dict(encoded_fields["mapping"]["value"])["child"],
    )
    children = (source.child, source.children[0], source.pair[0], source.pair[1], source.mapping["child"])
    assert all(ref["type"] == "record_ref" for ref in refs)
    assert [ref["content_id"] for ref in refs] == [content_id(child, as_record=ChildRecord) for child in children]
    assert content_id(ChildSource(4), as_record=ChildRecord) != content_id(ChildSource(4), as_record=AlternateRecord)


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


def test_content_id_cache_hits_root_and_reuses_a_cached_child(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    @dataclass(frozen=True)
    class Parent:
        child: Child

    calls = 0
    original = identity_module._canonical_json

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(identity_module, "_canonical_json", counted)
    child = Child(3)
    first = content_id(Parent(child))
    first_calls = calls
    second = content_id(Parent(child))
    assert first == second
    assert calls - first_calls == 1  # only the fresh parent is encoded

    root = Parent(child)
    content_id(root)
    root_calls = calls
    assert content_id(root) == content_id(root)
    assert calls == root_calls


def test_content_id_cache_is_keyed_by_as_record_type() -> None:
    @dataclass(frozen=True)
    class Source:
        value: int

    @dataclass(frozen=True)
    class First:
        value: int

        __httk_canonical_source__ = Source

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value}

    @dataclass(frozen=True)
    class Second:
        value: int

        __httk_canonical_source__ = Source

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value + 1}

    source = Source(4)
    first = content_id(source, as_record=First)
    second = content_id(source, as_record=Second)
    assert first != second
    cached = cast(Any, source)._httk_cached_content_ids
    assert set(cached[1]) == {First, Second}


def test_custom_projector_bypasses_cache_in_both_directions() -> None:
    source = _Plain(8)
    calls = 0

    def custom(record_type, value):
        nonlocal calls
        calls += 1
        return {"value": value.value}

    first = content_id(source, projector=custom)
    second = content_id(source, projector=custom)
    assert first == second
    assert calls == 2
    assert not hasattr(source, "_httk_cached_content_ids")

    content_id(source)
    content_id(source, projector=custom)
    assert calls == 3  # a default cache cannot affect the custom route


def test_unwritable_tuple_sources_and_attribute_collisions_skip_install() -> None:
    @dataclass(frozen=True)
    class Record:
        value: int

        __httk_canonical_source__ = tuple

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source[0]}

    source = (7,)
    assert content_id(source, as_record=Record) == content_id(source, as_record=Record)
    assert not hasattr(source, "_httk_cached_content_ids")

    @dataclass(frozen=True)
    class CollisionSource:
        value: int

        _httk_cached_content_ids = "occupied"

    calls = 0

    @dataclass(frozen=True)
    class CollisionRecord:
        value: int

        __httk_canonical_source__ = CollisionSource

        @classmethod
        def __httk_project__(cls, source):
            nonlocal calls
            calls += 1
            return {"value": source.value}

    collision = CollisionSource(7)
    content_id(collision, as_record=CollisionRecord)
    content_id(collision, as_record=CollisionRecord)
    assert calls == 2
    assert collision._httk_cached_content_ids == "occupied"


def test_views_are_valid_sources_but_never_cache_carriers() -> None:
    from httk.core.views import View

    class SyntheticView(View):
        def __init__(self, value):
            self.value = value

    @dataclass(frozen=True)
    class Record:
        value: int

        __httk_canonical_source__ = SyntheticView

        @classmethod
        def __httk_project__(cls, source):
            return {"value": source.value}

    view = SyntheticView(9)
    first = content_id(view, as_record=Record)
    second = content_id(view, as_record=Record)
    assert first == second
    assert not hasattr(view, "_httk_cached_content_ids")


def test_epoch_replaces_stale_cache_and_pickle_miss_is_replaced() -> None:
    record = _PickleRecord(11)
    content_id(record)
    old = cast(Any, record)._httk_cached_content_ids

    class EpochLeaf:
        pass

    register_canonical_encoder(EpochLeaf, lambda value: {"value": 1})
    assert content_id(record) == content_id(_PickleRecord(11))
    assert cast(Any, record)._httk_cached_content_ids is not old

    pickled = pickle.loads(pickle.dumps(record))
    stale = cast(Any, pickled)._httk_cached_content_ids
    content_id(pickled)
    assert pickled._httk_cached_content_ids is not stale

    calls = 0
    original = identity_module._canonical_json

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    # The first call after installation is a cache hit, so no canonical JSON
    # is rendered; this specifically checks that the stale pickle container was
    # replaced rather than left in place.
    identity_module._canonical_json = counted
    try:
        content_id(pickled)
    finally:
        identity_module._canonical_json = original
    assert calls == 0


def test_late_annotation_resolution_does_not_install_fallback_cache() -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    late_type: type[Any] = dataclass(frozen=True)(
        type(
            "LateIdentityRecord",
            (),
            {"__module__": __name__, "__annotations__": {"child": "_LateIdentityChild"}},
        )
    )
    source = late_type(Child(2))
    with pytest.raises(TypeError, match="field annotation"):
        content_id(source)
    assert not hasattr(source, "_httk_cached_content_ids")

    module = sys.modules[__name__]
    cast(Any, module)._LateIdentityChild = Child
    try:
        content_id(source)
        assert hasattr(source, "_httk_cached_content_ids")
    finally:
        delattr(module, "_LateIdentityChild")


def test_mid_traversal_registration_installs_no_mixed_epoch_cache() -> None:
    class TriggerLeaf:
        def __init__(self, value):
            self.value = value

    class RegisteredLater(int):
        pass

    state = False

    def trigger_encoder(value):
        nonlocal state
        if not state:
            register_canonical_encoder(RegisteredLater, lambda item: {"value": int(item)})
            state = True
        return {"value": value.value}

    register_canonical_encoder(TriggerLeaf, trigger_encoder)

    @dataclass(frozen=True)
    class Record:
        first: TriggerLeaf
        later: RegisteredLater

    record = Record(TriggerLeaf(5), RegisteredLater(7))
    first = content_id(record)
    assert not hasattr(record, "_httk_cached_content_ids")
    # The later field is encoded from the operation-start snapshot as an int,
    # not with the encoder registered by the first field.  The next operation
    # sees that registration and therefore produces the custom node.
    second = content_id(record)
    assert second != first
    assert hasattr(record, "_httk_cached_content_ids")


def test_cache_hot_and_epoch_cold_graphs_have_identical_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    @dataclass(frozen=True)
    class NoneChild:
        __httk_storage__ = StorageInfo(dedup="none")
        value: int

    @dataclass(frozen=True)
    class Graph:
        children: tuple[Child, ...]
        named: dict[str, Child]
        none_child: NoneChild
        metadata: Annotated[str, IdentitySkip()]

    graphs: list[Graph] = []
    for seed in range(20):
        generator = random.Random(seed)
        children = tuple(Child(generator.randrange(-20, 21)) for _ in range(generator.randrange(1, 7)))
        graphs.append(
            Graph(
                children,
                {str(index): child for index, child in enumerate(children)},
                NoneChild(generator.randrange(-20, 21)),
                f"metadata-{seed}",
            )
        )

    json_calls = 0
    sha_calls = 0
    original_json = identity_module._canonical_json
    original_sha256 = identity_module.hashlib.sha256

    def counted_json(value):
        nonlocal json_calls
        json_calls += 1
        return original_json(value)

    def counted_sha256(*args, **kwargs):
        nonlocal sha_calls
        sha_calls += 1
        return original_sha256(*args, **kwargs)

    monkeypatch.setattr(identity_module, "_canonical_json", counted_json)
    monkeypatch.setattr(identity_module.hashlib, "sha256", counted_sha256)
    hot: list[str] = []
    for graph in graphs:
        content_id(graph)  # prime and install the root and reachable children
        before_json, before_sha = json_calls, sha_calls
        hot_digest = content_id(graph)
        assert json_calls == before_json
        assert sha_calls == before_sha
        assert cast(Any, graph)._httk_cached_content_ids[1][Graph] == hot_digest
        hot.append(hot_digest)

    class ColdEpochMarker:
        pass

    register_canonical_encoder(ColdEpochMarker, lambda value: {"value": 0})
    cold = [
        content_id(
            Graph(
                tuple(Child(child.value) for child in graph.children),
                {str(index): Child(child.value) for index, child in enumerate(graph.children)},
                NoneChild(graph.none_child.value),
                f"changed-metadata-{index}",
            )
        )
        for index, graph in enumerate(graphs)
    ]
    assert hot == cold


def test_failed_root_does_not_install_pending_child_cache() -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    class Unsupported:
        pass

    @dataclass(frozen=True)
    class Root:
        a_child: Child
        z_bad: object

    child = Child(4)
    root = Root(child, Unsupported())
    with pytest.raises(TypeError, match="unsupported value type"):
        content_id(root)
    assert not hasattr(root, "_httk_cached_content_ids")
    assert not hasattr(child, "_httk_cached_content_ids")


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


def test_record_cycles_report_direct_list_and_mapping_paths() -> None:
    direct = _CycleNode(None)
    object.__setattr__(direct, "child", direct)
    with pytest.raises(StorageProjectionCycleError) as direct_error:
        canonical_form(direct)
    assert direct_error.value.path == "child"

    via_list = _ListCycleNode([])
    via_list.children.append(via_list)
    with pytest.raises(StorageProjectionCycleError) as list_error:
        canonical_form(via_list)
    assert list_error.value.path == "children[0]"

    via_mapping = _MappingCycleNode({})
    via_mapping.children["self"] = via_mapping
    with pytest.raises(StorageProjectionCycleError) as mapping_error:
        canonical_form(via_mapping)
    assert mapping_error.value.path == "children.self"


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
        FracScalar._of(2, 3),
        FracVector([[Fraction(1, 2), 2]]),
        SurdVector.sqrt_of(2),
        SurdVector([1, 2]),
        datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
    )
    equivalent = Values(
        Fraction(2, 3),
        FracScalar._of(4, 6),
        FracVector([[Fraction(1, 2), Fraction(4, 2)]]),
        SurdVector.sqrt_of(2),
        SurdVector([1, 2]),
        datetime.datetime(2025, 12, 31, 22, tzinfo=datetime.UTC),
    )
    assert content_id(value) == content_id(equivalent)


def test_rational_leaf_text_and_structural_vector_nodes() -> None:
    def node(value: object) -> object:
        return dict(json.loads(canonical_form(_Plain(value)))["fields"])["value"]

    assert node(Fraction(0)) == {"type": "rational", "value": "0/1"}
    assert node(Fraction(-3, 2)) == {"type": "rational", "value": "-3/2"}
    assert node(Fraction(5)) == {"type": "rational", "value": "5/1"}
    assert node(decimal.Decimal("1.50")) == {"type": "rational", "value": "3/2"}
    assert node(FracScalar._of(10, 2)) == {"type": "rational", "value": "5/1"}
    assert node(FracVector([[Fraction(1, 2), 2]])) == {
        "type": "frac_vector",
        "value": {"denominator": 2, "nominators": [[1, 4]]},
    }
    assert node(SurdVector.sqrt_of(2)) == {
        "dimension": [],
        "type": "surd_scalar",
        "value": [[2, {"type": "frac_vector", "value": {"denominator": 1, "nominators": 1}}]],
    }
    assert node(SurdVector([1, 2])) == {
        "dimension": [2],
        "type": "surd_vector",
        "value": [[1, {"type": "frac_vector", "value": {"denominator": 1, "nominators": [1, 2]}}]],
    }


def _mutation_graph(**overrides: object) -> object:
    @dataclass(frozen=True)
    class Leaf:
        label: str
        number: int
        ratio: Fraction

    @dataclass(frozen=True)
    class NoneLeaf:
        __httk_storage__ = StorageInfo(dedup="none")
        number: int
        text: str

    @dataclass(frozen=True)
    class Branch:
        title: str
        none_child: NoneLeaf
        mapped: dict[str, Leaf]

    @dataclass(frozen=True)
    class Root:
        enabled: bool
        branch: Branch
        leaves: tuple[Leaf, ...]

    values = {
        "enabled": True,
        "title": "branch",
        "none_number": 11,
        "none_text": "none",
        "mapped_a_label": "mapped-a",
        "mapped_a_number": 21,
        "mapped_a_ratio": Fraction(1, 3),
        "mapped_b_label": "mapped-b",
        "mapped_b_number": 22,
        "mapped_b_ratio": Fraction(2, 3),
        "tuple_a_label": "tuple-a",
        "tuple_a_number": 31,
        "tuple_a_ratio": Fraction(3, 5),
        "tuple_b_label": "tuple-b",
        "tuple_b_number": 32,
        "tuple_b_ratio": Fraction(4, 5),
    }
    values.update(overrides)

    def leaf(prefix: str) -> Leaf:
        return Leaf(values[f"{prefix}_label"], values[f"{prefix}_number"], values[f"{prefix}_ratio"])  # type: ignore[arg-type]

    return Root(
        values["enabled"],  # type: ignore[arg-type]
        Branch(
            values["title"],  # type: ignore[arg-type]
            NoneLeaf(values["none_number"], values["none_text"]),  # type: ignore[arg-type]
            {"a": leaf("mapped_a"), "b": leaf("mapped_b")},
        ),
        (leaf("tuple_a"), leaf("tuple_b")),
    )


def test_every_included_leaf_mutation_changes_three_level_root_digest() -> None:
    baseline = content_id(_mutation_graph())
    mutations = {
        "enabled": False,
        "title": "changed-branch",
        "none_number": 12,
        "none_text": "changed-none",
        "mapped_a_label": "changed-mapped-a",
        "mapped_a_number": 121,
        "mapped_a_ratio": Fraction(5, 7),
        "mapped_b_label": "changed-mapped-b",
        "mapped_b_number": 122,
        "mapped_b_ratio": Fraction(6, 7),
        "tuple_a_label": "changed-tuple-a",
        "tuple_a_number": 131,
        "tuple_a_ratio": Fraction(7, 9),
        "tuple_b_label": "changed-tuple-b",
        "tuple_b_number": 132,
        "tuple_b_ratio": Fraction(8, 9),
    }
    for field_name, changed_value in mutations.items():
        assert content_id(_mutation_graph(**{field_name: changed_value})) != baseline, field_name


def test_documented_identity_equivalences_and_distinctions() -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    @dataclass(frozen=True)
    class Parent:
        children: tuple[Child, Child]

    shared = Child(3)
    assert content_id(Parent((shared, shared))) == content_id(Parent((Child(3), Child(3))))

    @dataclass(frozen=True)
    class WithMetadata:
        value: int
        metadata: Annotated[str, IdentitySkip()]

    assert content_id(WithMetadata(1, "first")) == content_id(WithMetadata(1, "second"))

    @dataclass(frozen=True)
    class FirstLogicalRecord:
        __httk_storage__ = StorageInfo(identity_name="tests.same-logical-record")
        value: int

    @dataclass(frozen=True)
    class SecondLogicalRecord:
        __httk_storage__ = StorageInfo(identity_name="tests.same-logical-record")
        value: int

    assert content_id(FirstLogicalRecord(4)) == content_id(SecondLogicalRecord(4))
    assert content_id(_Plain(decimal.Decimal("1.50"))) == content_id(_Plain(Fraction(3, 2)))
    assert content_id(_Plain(True)) != content_id(_Plain(1))
    assert content_id(_Plain(1)) != content_id(_Plain(Fraction(1)))

    class IntSubclass(int):
        pass

    assert content_id(_Plain(IntSubclass(7))) == content_id(_Plain(7))

    @dataclass(frozen=True)
    class TupleNormalized:
        values: tuple[int, ...]

    assert content_id(TupleNormalized([1, 2])) == content_id(TupleNormalized((1, 2)))  # type: ignore[arg-type]


def test_record_ref_domain_is_separate_from_record_ref_shaped_string() -> None:
    @dataclass(frozen=True)
    class Child:
        value: int

    @dataclass(frozen=True)
    class StringParent:
        __httk_storage__ = StorageInfo(identity_name="tests.record-ref-domain")
        child: str

    @dataclass(frozen=True)
    class RecordParent:
        __httk_storage__ = StorageInfo(identity_name="tests.record-ref-domain")
        child: Child

    child = Child(9)
    reference_text = json.dumps(
        {"content_id": content_id(child), "type": "record_ref"},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert content_id(StringParent(reference_text)) != content_id(RecordParent(child))


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


def test_record_annotation_precedes_custom_encoder_but_untyped_leaf_uses_it() -> None:
    @dataclass(frozen=True)
    class EncodedRecord:
        value: int

    @dataclass(frozen=True)
    class Parent:
        child: EncodedRecord

    encoded: list[EncodedRecord] = []

    def encode(value: EncodedRecord) -> object:
        encoded.append(value)
        return {"encoded": value.value}

    register_canonical_encoder(EncodedRecord, encode)
    child = EncodedRecord(7)
    parent_node = dict(json.loads(canonical_form(Parent(child)))["fields"])["child"]
    assert parent_node == {"content_id": content_id(child), "type": "record_ref"}
    assert encoded == []

    leaf_node = dict(json.loads(canonical_form(_Plain(child)))["fields"])["value"]
    assert leaf_node["type"] == "custom"
    assert leaf_node["python_type"] == f"{EncodedRecord.__module__}.{EncodedRecord.__qualname__}"
    assert encoded == [child]


def test_canonical_version_two_golden_vector() -> None:
    form = canonical_form(_Golden(7, Fraction(2, 3), ("a", "b")))
    assert form == (
        '{"fields":[["count",{"type":"int","value":"7"}],'
        '["labels",{"type":"tuple","value":[{"type":"string","value":"a"},'
        '{"type":"string","value":"b"}]}],["ratio",{"type":"rational","value":"2/3"}]],'
        '"identity_name":"golden.record","type":"record","version":2}'
    )
    assert (
        content_id(_Golden(7, Fraction(2, 3), ("a", "b")))
        == "5fbd9d653af588e954d394d2f5489536d6fabb0b797c2de24be2f6e7d5f86d0b"
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
