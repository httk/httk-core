"""Tests for the generated core typed records (``httk.core.property_records``)."""

import datetime
import importlib
import itertools
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import pytest

from httk.core import DataRecord, PropertyDefinition, ReferenceRecord, RunEdge, WeakLink, typed_records
from httk.core._typed_record_tool import generate_typed_records
from httk.core.data_records import DataRecordEntry
from httk.core.definition_ids import CARTESIAN_SITE_FORCES, STRESS_TENSOR, TEMPERATURE
from httk.core.property_records import RECORD_KINDS, CartesianSiteForcesRecord
from httk.core.register.entries import resolve_entry_record
from httk.core.typed_records import MemberLayout, TypedRecord

_LEAVES = {"float": 1.5, "integer": 2, "string": "s", "boolean": True}


def _synthetic(item: MemberLayout) -> Any:
    counter = itertools.count()
    sizes = [size if size is not None else 2 for _, size in item.dimensions]

    def build(depth: int) -> Any:
        if depth == len(sizes):
            leaf = _LEAVES[item.leaf]
            return leaf + next(counter) if item.leaf in ("float", "integer") else leaf
        return [build(depth + 1) for _ in range(sizes[depth])]

    return build(0)


@pytest.mark.parametrize("cls", RECORD_KINDS.values(), ids=lambda cls: cls.__name__)
def test_generated_record_kind(cls: type[TypedRecord]) -> None:
    spec = cls.__httk_typed_record__
    (item,) = spec.layout
    record = cls.from_value(_synthetic(item))
    assert record.value == _synthetic(item)
    assert fields(cast(Any, cls))[0].name == item.field
    name = spec.definition.name
    assert vars(cls)["__httk_storage__"].storage_name == f"core_{name}"
    assert vars(cls)["__httk_storage__"].links == (WeakLink("references", ReferenceRecord, exposed_relationship=True),)
    assert list(vars(cls)["__httk_property_definitions__"]) == [spec.served_name]
    assert vars(cls)["__httk_property_definitions__"][spec.served_name].name == spec.served_name
    assert list(vars(cls)["__httk_stored_properties__"]) == [spec.served_name]
    assert resolve_entry_record("core-" + name.replace("_", "-")) is cls
    assert RECORD_KINDS[spec.definition_id] is cls
    assert record.definition_id == spec.definition_id


@pytest.mark.parametrize("cls", RECORD_KINDS.values(), ids=lambda cls: cls.__name__)
def test_generated_record_kind_from_data_record(cls: type[TypedRecord]) -> None:
    spec = cls.__httk_typed_record__
    (item,) = spec.layout
    stamp = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    edges = (RunEdge("input", "runs", "r1"),)
    generic = DataRecord.from_value(
        spec.definition_id,
        "generic",
        _synthetic(item),
        product_of=edges,
        id="x1",
        immutable_id="i1",
        last_modified=stamp,
    )
    record = cast(Any, cls.from_data_record(generic))
    assert record.value == generic.value and record.product_of == edges
    assert (record.id, record.immutable_id, record.last_modified) == ("x1", "i1", stamp)


_FORCES = [[0.0, 0.5, -0.5], [1.25, -2.0, 0.0], [-1.25, 1.5, 0.5], [0.0, 0.0, 0.0]]


def test_cartesian_site_forces_record_nests_one_vector_per_site() -> None:
    record = CartesianSiteForcesRecord.from_value(_FORCES)
    assert RECORD_KINDS[CARTESIAN_SITE_FORCES] is CartesianSiteForcesRecord
    assert record.cartesian_site_forces == tuple(itertools.chain.from_iterable(_FORCES))  # Row-major storage.
    assert record.value == _FORCES
    projection = vars(CartesianSiteForcesRecord)["__httk_stored_properties__"]["_httk_cartesian_site_forces"]
    assert projection.response(record) == _FORCES
    with pytest.raises(ValueError):
        CartesianSiteForcesRecord.from_value([[0.0, 0.5], [1.0, 2.0]])  # Not a 3-vector per site.


def test_cartesian_site_forces_round_trip_through_sql_store() -> None:
    sql = pytest.importorskip("httk.store.backend.sql")
    from httk.store import EntryIdScheme

    entry_records = {DataRecordEntry: (CartesianSiteForcesRecord,)}
    ids = EntryIdScheme("httk.test", "1")
    record = CartesianSiteForcesRecord.from_value(_FORCES, product_of=(RunEdge("input", "structures", "s1"),))
    with sql.Backend.sqlite() as database:
        sql.SqlStore(database, entry_records=entry_records, entry_ids=ids).save(record)
        search = sql.SqlStore(database, entry_records=entry_records, entry_ids=ids).searcher()
        (stored,) = [row.record for row in search.results(record=search.variable(CartesianSiteForcesRecord))]
        assert stored == record and stored.value == _FORCES and stored.product_of == record.product_of


def test_import_loads_no_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(definition_id: str) -> PropertyDefinition:
        raise AssertionError(f"definition loaded at import: {definition_id}")

    monkeypatch.setattr(typed_records, "load_property_definition", refuse)
    monkeypatch.delitem(sys.modules, "httk.core.property_records")
    module = importlib.import_module("httk.core.property_records")
    for cls in module.RECORD_KINDS.values():
        assert len(vars(cls)["__httk_property_definitions__"]) == 1
        assert len(vars(cls)["__httk_stored_properties__"]) == 1


def test_generator_emits_derived_kinds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rmse = "https://schemas.httk.org/defs/v0.1/derivations/rmse"
    source = generate_typed_records(
        [TEMPERATURE],
        derived=[(STRESS_TENSOR, rmse, "root-mean-square error")],
        module_doc="Probe records.",
        storage_prefix="probe",
        command="probe",
    )
    compile(source, "derived_probe_records.py", "exec")
    assert "class StressTensorRmseRecord(TypedRecord):" in source and '"DERIVED_RECORD_KINDS",' in source
    (tmp_path / "derived_probe_records.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "derived_probe_records", raising=False)
    module = importlib.import_module("derived_probe_records")
    assert list(module.RECORD_KINDS.values()) == [module.TemperatureRecord]
    cls = module.DERIVED_RECORD_KINDS[(STRESS_TENSOR, rmse)]
    assert vars(cls)["__httk_storage__"].storage_name == "probe_stress_tensor_rmse"
    record = cls.from_value([1.0, 2.0, 3.0, 0.0, 0.0, 0.0])
    assert record.value == [1.0, 2.0, 3.0, 0.0, 0.0, 0.0]
    assert list(vars(cls)["__httk_property_definitions__"]) == ["_httk_stress_tensor_rmse"]
    assert "DERIVED_RECORD_KINDS" not in generate_typed_records(
        [TEMPERATURE], module_doc="Probe records.", storage_prefix="probe", command="probe"
    )
