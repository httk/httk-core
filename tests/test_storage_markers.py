"""Tests for the stdlib-only storage marker vocabulary (httk.core.storage.markers)."""

import dataclasses
from dataclasses import dataclass
from typing import Annotated, ClassVar, get_type_hints

import pytest

from httk.core.storage import (
    STORAGE_INFO_ATTRIBUTE,
    Indexed,
    Related,
    RelationshipLink,
    Shape,
    Skip,
    StorageInfo,
    Unique,
    stored_property,
)


def test_field_markers_are_frozen_and_equal_by_value():
    assert Indexed() == Indexed()
    assert Unique() == Unique()
    assert Skip() == Skip()
    with pytest.raises(dataclasses.FrozenInstanceError):
        Indexed().anything = 1


def test_shape_fixed_and_variable():
    fixed = Shape(3, 3)
    assert (fixed.rows, fixed.cols) == (3, 3)
    variable = Shape(0, 3)
    assert variable.rows == 0
    assert Shape(4).cols == 1


def test_shape_validation():
    with pytest.raises(ValueError):
        Shape(-1)
    with pytest.raises(ValueError):
        Shape(3, 0)


def test_related_defaults_and_equality():
    marker = Related()
    assert marker.role is None
    assert marker.description is None
    assert marker.serve is True
    assert Related() == Related()
    assert Related(role="input", description="d") == Related(role="input", description="d")
    assert Related(role="input") != Related(role="output")
    assert Related(serve=False).serve is False


def test_related_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Related().role = "input"


def test_relationship_link_endpoints():
    link = RelationshipLink("structure", "reference")
    assert (link.source, link.target) == ("structure", "reference")
    assert link.role is None and link.description is None
    inverse = RelationshipLink("structure", None, role="output", description="Produced structure")
    assert inverse.target is None
    assert inverse.role == "output"
    assert inverse.description == "Produced structure"
    assert RelationshipLink(None, "reference").source is None


def test_relationship_link_invariants():
    with pytest.raises(ValueError):
        RelationshipLink(None, None)
    with pytest.raises(ValueError):
        RelationshipLink("structure", "structure")


def test_relationship_link_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        RelationshipLink("a", "b").role = "input"


def test_storage_info_defaults():
    info = StorageInfo()
    assert info.storage_name is None
    assert info.indexes == ()
    assert info.dedup == "content_id"
    assert info.links == ()


def test_storage_info_carries_links():
    links = (RelationshipLink("structure", "reference", role="citation"),)
    info = StorageInfo(dedup="by_value", links=links)
    assert info.links == links
    assert info.links[0].role == "citation"


def test_storage_info_validation():
    with pytest.raises(ValueError):
        StorageInfo(dedup="never")
    with pytest.raises(ValueError):
        StorageInfo(indexes=((),))
    assert StorageInfo(dedup="by_value").dedup == "by_value"
    assert StorageInfo(indexes=(("tag", "value"),)).indexes == (("tag", "value"),)


def test_storage_info_attribute_is_classvar_and_ignored_by_dataclass() -> None:
    @dataclass(frozen=True)
    class Record:
        __httk_storage__: ClassVar[StorageInfo] = StorageInfo(indexes=(("a", "b"),))

        a: Annotated[str, Indexed()]
        b: int
        c: Annotated[float, Skip()] = 0.0

    assert STORAGE_INFO_ATTRIBUTE == "__httk_storage__"
    assert getattr(Record, STORAGE_INFO_ATTRIBUTE).indexes == (("a", "b"),)
    assert [field.name for field in dataclasses.fields(Record)] == ["a", "b", "c"]
    hints = get_type_hints(Record, include_extras=True)
    assert Indexed() in hints["a"].__metadata__
    assert Skip() in hints["c"].__metadata__


def test_stored_property_is_a_property_with_readable_annotation() -> None:
    @dataclass(frozen=True)
    class Record:
        symbols: tuple[str, ...]

        @stored_property
        def natoms(self) -> int:
            return len(self.symbols)

    assert isinstance(Record.natoms, property)
    assert isinstance(Record.natoms, stored_property)
    assert Record(symbols=("O", "Ca", "Ti")).natoms == 3
    assert Record.natoms.fget is not None
    assert get_type_hints(Record.natoms.fget)["return"] is int
    # A plain property must remain distinguishable from a stored one.
    assert not isinstance(property(lambda _: None), stored_property)


def test_stored_property_requires_a_return_annotation():
    with pytest.raises(TypeError, match="return annotation"):

        @stored_property
        def value(_):
            return 1
