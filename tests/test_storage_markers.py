"""Tests for the stdlib-only storage marker vocabulary (httk.core.storage_markers)."""

import dataclasses
from dataclasses import dataclass
from typing import Annotated, ClassVar, get_type_hints

import pytest

from httk.core import (
    STORAGE_INFO_ATTRIBUTE,
    Indexed,
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
        Indexed().anything = 1  # type: ignore[attr-defined]


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


def test_storage_info_defaults():
    info = StorageInfo()
    assert info.table_name is None
    assert info.indexes == ()
    assert info.dedup == "content_id"


def test_storage_info_validation():
    with pytest.raises(ValueError):
        StorageInfo(dedup="never")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        StorageInfo(indexes=((),))
    assert StorageInfo(dedup="by_value").dedup == "by_value"
    assert StorageInfo(indexes=(("tag", "value"),)).indexes == (("tag", "value"),)


def test_storage_info_attribute_is_classvar_and_ignored_by_dataclass():
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


def test_stored_property_is_a_property_with_readable_annotation():
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
