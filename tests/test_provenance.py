"""Tests for the core provenance records."""

import datetime
from dataclasses import replace
from typing import Any, cast

import pytest

from httk.core import ProductLink, Run, RunEdge, RunEntry
from httk.core.storage import content_id, project_storage_record


def test_run_edge_create_and_validation() -> None:
    edge = RunEdge("input", "calculations", "calc-1")
    assert RunEdge.from_obj(edge) is edge
    assert RunEdge.from_obj({"label": "input", "entry_type": "calculations", "entry_id": "calc-1"}) == edge
    for field_name in ("label", "entry_type", "entry_id"):
        with pytest.raises(ValueError, match=field_name):
            RunEdge(
                " " if field_name == "label" else "x",
                " " if field_name == "entry_type" else "x",
                " " if field_name == "entry_id" else "x",
            )


def test_run_constructor_and_create_coerce_edges_and_timestamp() -> None:
    timestamp = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)
    run = Run(
        "https://example.org/workflow/1",
        inputs=cast(Any, [{"label": "input", "entry_type": "calculations", "entry_id": "calc-1"}]),
        artifacts=(RunEdge("artifact", "files", "file-1"),),
        outputs=cast(Any, iter((RunEdge("output", "_httk_records", "record-1"),))),
        source_id="source",
        immutable_id="immutable",
        last_modified=timestamp,
    )
    assert run.inputs == (RunEdge("input", "calculations", "calc-1"),)
    assert run.source_id == "source"
    assert run.last_modified == timestamp
    created = Run.from_obj(
        {
            "workflow_declaration_uri": "https://example.org/workflow/1",
            "inputs": [{"label": "input", "entry_type": "calculations", "entry_id": "calc-1"}],
            "last_modified": "2026-01-02T03:04:05+00:00",
        }
    )
    assert created == Run("https://example.org/workflow/1", inputs=run.inputs, last_modified=timestamp)
    assert created.type == "_httk_runs"
    assert created.source_id is None
    assert created.id is None
    with pytest.raises(ValueError, match="Unknown field"):
        Run.from_obj({"unknown": 1})


def test_run_edges_are_unique_per_side_but_not_across_sides() -> None:
    with pytest.raises(ValueError, match="inputs"):
        Run(inputs=(RunEdge("same", "files", "one"), RunEdge("same", "files", "two")))
    run = Run(inputs=(RunEdge("same", "files", "one"),), outputs=(RunEdge("same", "files", "two"),))
    assert run.inputs[0].label == run.outputs[0].label


def test_run_rejects_bad_uri_and_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="workflow_declaration_uri"):
        Run(" ")
    with pytest.raises(ValueError, match="last_modified"):
        Run(last_modified=datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC).replace(tzinfo=None))


def test_product_link_and_logical_family() -> None:
    link = ProductLink("_httk_records", "record-1", "_httk_records", "record-2", "curated")
    assert ProductLink.from_obj(link) is link
    assert (
        ProductLink.from_obj(
            {
                "source_type": "_httk_records",
                "source_id": "record-1",
                "target_type": "_httk_records",
                "target_id": "record-2",
                "label": "curated",
            }
        )
        == link
    )
    with pytest.raises(ValueError, match="source and target"):
        ProductLink("_httk_records", "record-1", "_httk_records", "record-1", "self")
    assert RunEntry.type == "_httk_runs"
    assert RunEntry.definition_id == "https://schemas.httk.org/defs/v0.1/entrytypes/runs"
    with pytest.raises(TypeError, match="store a Run directly"):
        RunEntry()


def test_provenance_content_id_pins() -> None:
    edge = RunEdge("input", "calculations", "calc-1")
    run = Run(
        "https://example.org/workflow/1",
        inputs=(edge,),
        artifacts=(RunEdge("artifact", "files", "file-1"),),
        outputs=(RunEdge("output", "_httk_records", "record-1"),),
        source_id="source",
        immutable_id="immutable",
        last_modified=datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
    )
    link = ProductLink(
        "_httk_records", "record-1", "_httk_records", "record-2", "curated", "https://example.org/workflow/1"
    )
    # A changed value means a storage-identity break.
    assert content_id(edge) == "4e18906b8f17b826a58e360963965da3a0729b6d3c282332826801ad4d669c62"
    # A changed value means a storage-identity break; metadata is excluded.
    assert content_id(run) == "a4796f0c0a30e4e9e94390c4950a9eceeac7b4e0091ca5d64beab1fe364df833"
    # A changed value means a storage-identity break.
    assert content_id(link) == "796d2b00369533e0698a79b8208efc21eaaf4782a5cfe6f3b3ceb19afcfeb3d8"
    assert content_id(run) == content_id(
        Run(
            run.workflow_declaration_uri,
            run.inputs,
            run.artifacts,
            run.outputs,
            run.source_id,
            id="other",
            immutable_id="other-immutable",
            last_modified=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
        )
    )


def test_run_source_id_participates_in_content_identity() -> None:
    first = Run(source_id="job-a")
    second = Run(source_id="job-b")
    assert content_id(first) != content_id(second)
    assert content_id(first) == content_id(Run(source_id="job-a"))


def test_run_ids_are_stored_metadata_outside_content_identity() -> None:
    run = Run(inputs=(RunEdge("input", "files", "file-1"),))
    identified = replace(run, id="logical", immutable_id="immutable")
    assert run.id is None
    assert identified.id == "logical"
    assert content_id(identified) == content_id(run)
    projected = Run(**project_storage_record(Run, identified))
    assert projected.id == "logical"
    assert projected.immutable_id == "immutable"
