"""Tests for the stdlib-only storage marker vocabulary (httk.core.storage.markers)."""

import dataclasses
from dataclasses import dataclass
from typing import Annotated, ClassVar, get_type_hints

import pytest

from httk.core.storage import (
    STORAGE_INFO_ATTRIBUTE,
    Indexed,
    Inline,
    KeepStored,
    Related,
    Shape,
    Skip,
    StorageInfo,
    Unique,
    WeakLink,
    content_id,
    stored_property,
    validate_storage_record,
)


@dataclass(frozen=True)
class _Target:
    value: int


def test_keep_stored_is_exported_and_marks_file_record_location():
    import httk.core
    from httk.core import FileRecord

    assert httk.core.KeepStored is KeepStored
    metadata = get_type_hints(FileRecord, include_extras=True)["url"].__metadata__
    assert KeepStored() in metadata


def test_field_markers_are_frozen_and_equal_by_value():
    assert Indexed() == Indexed()
    assert Unique() == Unique()
    assert Skip() == Skip()
    with pytest.raises(dataclasses.FrozenInstanceError):
        Indexed().anything = 1


@dataclass(frozen=True)
class _InlineSite:
    symbol: str
    x: int


@dataclass(frozen=True)
class _LinkedSites:
    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(identity_name="test.sites")
    sites: tuple[_InlineSite, ...]


@dataclass(frozen=True)
class _InlineSites:
    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(identity_name="test.sites")
    sites: Annotated[tuple[_InlineSite, ...], Inline()]


def test_inline_marker_is_layout_only_and_ignored_by_content_identity():
    import httk.core

    assert httk.core.Inline is Inline
    assert Inline() == Inline()
    sites = (_InlineSite("Si", 1), _InlineSite("O", 2))
    assert content_id(_InlineSites(sites)) == content_id(_LinkedSites(sites))
    assert content_id(_InlineSites(())) == content_id(_LinkedSites(()))
    assert content_id(_InlineSites(sites)) != content_id(_InlineSites(sites[:1]))


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


def test_weak_link_defaults():
    link = WeakLink("projects", _Target)
    assert link.name == "projects"
    assert link.target is _Target
    assert link.exposed_relationship is False
    assert link.role is None
    assert link.description is None


def test_weak_link_full_kwargs():
    link = WeakLink(
        "projects",
        _Target,
        exposed_relationship=True,
        role="output",
        description="Produced project",
    )
    assert link.exposed_relationship is True
    assert link.role == "output"
    assert link.description == "Produced project"


def test_weak_link_invalid_name_raises():
    with pytest.raises(ValueError):
        WeakLink("not an identifier", _Target)
    with pytest.raises(ValueError):
        WeakLink("", _Target)


def test_weak_link_non_type_target_raises():
    with pytest.raises(TypeError):
        WeakLink("projects", _Target(value=1))


def test_weak_link_is_frozen_and_equal_by_value():
    assert WeakLink("projects", _Target) == WeakLink("projects", _Target)
    assert WeakLink("projects", _Target) != WeakLink("others", _Target)
    with pytest.raises(dataclasses.FrozenInstanceError):
        WeakLink("projects", _Target).role = "input"


def test_storage_info_defaults():
    info = StorageInfo()
    assert info.storage_name is None
    assert info.indexes == ()
    assert info.dedup == "content_id"
    assert info.links == ()


def test_storage_info_carries_links():
    links = (WeakLink("projects", _Target, exposed_relationship=True, role="citation"),)
    info = StorageInfo(dedup="by_value", links=links)
    assert info.links == links
    assert info.links[0].role == "citation"
    assert info.links[0].target is _Target


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


@dataclass(frozen=True)
class _Checked:
    value: int

    @classmethod
    def __httk_validate__(cls, record: "_Checked") -> None:
        _VALIDATED.append(record)
        if record.value < 0:
            raise ValueError("negative value")


@dataclass(frozen=True)
class _CheckedChild(_Checked):
    """Inherits the parent's validator, which storage does not use."""


@dataclass(frozen=True)
class _Plain:
    one: _Checked
    many: tuple[_Checked, ...]
    nested: list[tuple[_Checked, ...]]
    inherited: _CheckedChild


@dataclass(frozen=True)
class _WithSkipped:
    kept: _Checked
    scratch: Annotated[object, Skip()] = None


_CheckedRow = type("_CheckedRow", (_Checked,), {"__httk_row_base__": _Checked})


_VALIDATED: list[_Checked] = []


def test_validate_storage_record_walks_nested_records_once_each() -> None:
    _VALIDATED.clear()
    shared = _Checked(1)
    other = _Checked(2)
    record = _Plain(shared, (shared, other), [(other, _Checked(3))], _CheckedChild(-1))
    validate_storage_record(record)
    assert [item.value for item in _VALIDATED] == [1, 2, 3]


def test_validate_storage_record_without_validator_and_propagation() -> None:
    _VALIDATED.clear()
    validate_storage_record(_Target(1))
    assert _VALIDATED == []
    with pytest.raises(ValueError, match="negative value"):
        validate_storage_record(_Plain(_Checked(0), (_Checked(-5),), [], _CheckedChild(0)))
    with pytest.raises(TypeError, match="record instance"):
        validate_storage_record(_Checked)


def test_validate_storage_record_skips_skip_fields_and_uses_row_base() -> None:
    _VALIDATED.clear()
    validate_storage_record(_WithSkipped(_Checked(1), scratch=_Checked(-1)))
    assert [item.value for item in _VALIDATED] == [1]
    with pytest.raises(ValueError, match="negative value"):
        validate_storage_record(_CheckedRow(-2))
    assert [item.value for item in _VALIDATED] == [1, -2]
