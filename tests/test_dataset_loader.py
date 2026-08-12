import gzip
import json
import pickle
import sqlite3
import threading
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from httk.core import DatasetLoader, DatasetMeta, DatasetRecord
from httk.core.dataset_loader import _MAX_MEMBER_BYTES, _SqlarStore, write_dataset_sqlar


def _structured_doc() -> dict[str, Any]:
    return {
        "@context": {
            "@vocab": "https://example.org/vocab#",
            "data": {
                "@id": "https://example.org/symmetry_basics",
                "@context": {
                    "spacegroups": {
                        "@id": "https://example.org/spacegroups",
                        "@context": {
                            "number": "https://example.org/number",
                            "hall": "https://example.org/hall",
                        },
                    },
                },
            },
        },
        "@id": "https://example.org/symmetry_basics",
        "@type": "Dataset",
        "title": "Symmetry basics",
        "creator": "httk AUTHORS",
        "license": "CC0",
        "data": {
            "spacegroups": [
                {"number": 1, "symbol": "P1", "hall": {"symbol": "P 1"}},
                {"number": 2, "symbol": "P-1", "hall": {"symbol": "-P 1"}},
            ]
        },
        "indicies": {"by_number": {"1": 0, "2": 1}},
    }


def _write_json(tmp_path: Path, name: str, obj: Any) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


def test_plain_json_dict_is_raw_value(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "plain.json", {"a": 1, "b": [2, 3]})
    loader = DatasetLoader("plain_dict", p)
    assert loader.data == {"a": 1, "b": [2, 3]}
    assert not isinstance(loader.data, DatasetRecord)
    assert loader.meta is None
    assert loader.index is None


def test_plain_json_bare_list(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "list.json", [1, 2, 3])
    loader = DatasetLoader("plain_list", p)
    assert loader.data == [1, 2, 3]
    assert loader.meta is None
    assert loader.index is None


def test_plain_json_number(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "number.json", 42)
    loader = DatasetLoader("plain_number", p)
    assert loader.data == 42
    assert loader.meta is None
    assert loader.index is None


def test_structured_meta_and_records(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "structured.json", _structured_doc())
    loader = DatasetLoader("structured_meta", p)

    meta = loader.meta
    assert isinstance(meta, DatasetMeta)
    assert meta.id == "https://example.org/symmetry_basics"
    assert meta.type_ == "Dataset"
    assert meta.context["@vocab"] == "https://example.org/vocab#"
    assert meta.header == {"title": "Symmetry basics", "creator": "httk AUTHORS", "license": "CC0"}
    assert meta.dataset_ids == {"spacegroups": "https://example.org/spacegroups"}
    assert meta.fields == {
        "spacegroups": {
            "number": "https://example.org/number",
            "hall": "https://example.org/hall",
        }
    }

    data = loader.data
    assert isinstance(data, DatasetRecord)
    assert data.spacegroups == data["spacegroups"]
    assert data.spacegroups[0]["symbol"] == "P1"

    index = loader.index
    assert isinstance(index, DatasetRecord)
    assert index.by_number == index["by_number"]
    assert index["by_number"]["2"] == 1


def test_dataset_record_mapping_protocol(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "record.json", _structured_doc())
    data = DatasetLoader("record_protocol", p).data
    assert len(data) == 1
    assert "spacegroups" in data
    assert list(iter(data)) == ["spacegroups"]
    assert list(data.keys()) == ["spacegroups"]
    assert "spacegroups" in repr(data)
    with pytest.raises(AttributeError):
        _ = data.missing


def test_laziness_defers_io_until_access() -> None:
    loader = DatasetLoader("lazy_missing", "/no/such/file/really.json")
    with pytest.raises(OSError):
        _ = loader.data


def test_dedup_same_identifier_reuses_first_load(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "dedup.json", _structured_doc())
    first = DatasetLoader("dedup_shared", p)
    _ = first.data  # trigger the load

    second = DatasetLoader("dedup_shared", "/bogus/nonexistent.json")
    assert second.data is first.data
    assert second.meta is first.meta
    assert second.index is first.index


def test_decode_object_applied_bottom_up_at_both_levels(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "decode.json", _structured_doc())
    calls: list[tuple[str, str]] = []

    def decode(obj: dict[str, Any], url: str) -> Any:
        kind = "field" if "symbol" in obj and "number" not in obj else "entry"
        calls.append((kind, url))
        if kind == "field":
            return obj["symbol"]  # replace {"symbol": ...} with the plain string
        return {**obj, "decoded": True}

    loader = DatasetLoader("decode_both", p, decode_object=decode)
    spacegroups = loader.data.spacegroups

    # For each entry the field URL is visited before the dataset @id (bottom-up).
    assert calls == [
        ("field", "https://example.org/hall"),
        ("entry", "https://example.org/spacegroups"),
        ("field", "https://example.org/hall"),
        ("entry", "https://example.org/spacegroups"),
    ]
    # URL-less fields (number, symbol) never trigger the callback.
    assert all(url in ("https://example.org/hall", "https://example.org/spacegroups") for _, url in calls)

    assert spacegroups[0]["hall"] == "P 1"
    assert spacegroups[0]["decoded"] is True


def test_decode_object_not_called_for_plain_json(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "plain_decode.json", {"a": 1})
    calls: list[Any] = []

    def decode(obj: dict[str, Any], url: str) -> Any:
        calls.append((obj, url))
        return obj

    loader = DatasetLoader("plain_no_decode", p, decode_object=decode)
    assert loader.data == {"a": 1}
    assert calls == []


def test_unsupported_suffix_raises(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "data.yaml", {"a": 1})
    loader = DatasetLoader("unsupported_yaml", p)
    with pytest.raises(ValueError):
        _ = loader.data


def test_dataset_record_underscore_attributes_raise_and_pickle_roundtrips() -> None:
    record = DatasetRecord({"a": 1})
    with pytest.raises(AttributeError):
        _ = record._missing
    restored = pickle.loads(pickle.dumps(record))
    assert restored["a"] == 1
    assert restored.a == 1


def test_content_string_source_is_not_treated_as_filename() -> None:
    loader = DatasetLoader("content_number", "3.5", kind="content")
    assert loader.data == 3.5


def test_field_urls_decoded_even_without_dataset_id(tmp_path: Path) -> None:
    doc = _structured_doc()
    del doc["@context"]["data"]["@context"]["spacegroups"]["@id"]
    p = _write_json(tmp_path, "no_dataset_id.json", doc)
    calls: list[str] = []

    def decode(obj: dict[str, Any], url: str) -> Any:
        calls.append(url)
        return obj

    loader = DatasetLoader("fields_without_dataset_id", p, decode_object=decode)
    assert loader.data.spacegroups[0]["number"] == 1
    # Field-level URLs still fire; no entry-level calls without a dataset @id.
    assert calls == ["https://example.org/hall", "https://example.org/hall"]


def test_structured_doc_tolerates_missing_data_key(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "headers_only.json", {"@context": {}, "@id": "urn:x", "title": "t"})
    loader = DatasetLoader("headers_only", p)
    assert loader.data is None
    assert loader.meta is not None
    assert loader.meta.id == "urn:x"
    assert loader.index is None


def test_load_from_file_url_source(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "via_url.json", _structured_doc())
    # A bare file:// URL string is auto-recognized as a URL (no kind="url" needed).
    loader = DatasetLoader("file_url_source", p.as_uri())
    assert loader.data.spacegroups[1]["symbol"] == "P-1"
    assert loader.meta is not None
    assert loader.meta.id == "https://example.org/symmetry_basics"


def test_load_from_gzipped_json(tmp_path: Path) -> None:
    p = tmp_path / "symmetry.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(_structured_doc(), f)

    loader = DatasetLoader("gzip_structured", p)
    assert loader.data.spacegroups[0]["symbol"] == "P1"
    assert loader.meta is not None
    assert loader.meta.id == "https://example.org/symmetry_basics"


def test_load_from_gzipped_json_via_file_url(tmp_path: Path) -> None:
    p = tmp_path / "sym_url.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump({"a": 1, "b": [2, 3]}, f)

    # Extension is taken from the URL path; the stream layer decompresses transparently.
    loader = DatasetLoader("gzip_via_url", p.as_uri())
    assert loader.data == {"a": 1, "b": [2, 3]}


def _sqlar_doc() -> dict[str, Any]:
    return {
        "@context": {
            "data": {
                "@context": {
                    "records": {
                        "@id": "https://example.org/records",
                        "@context": {
                            "nested": "https://example.org/nested",
                            "label": "https://example.org/label",
                        },
                    },
                    "words": {"@id": "https://example.org/words"},
                }
            }
        },
        "@id": "https://example.org/dataset",
        "@type": "Dataset",
        "title": "sqlar test",
        "data": {
            "records": [
                {"nested": [1, {"value": "2/3"}], "label": "first", "count": 1},
                {"nested": {"value": "3/5"}, "label": "second", "count": 2},
            ],
            "words": ["alpha", "beta"],
            "summary": {"total": 2, "fraction": "5/7"},
        },
        "indicies": {"by_label": {"first": 0, "second": 1}},
    }


def _materialize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _materialize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_materialize(item) for item in value]
    return value


def test_sqlar_round_trip_matches_json(tmp_path: Path) -> None:
    document = _sqlar_doc()
    sqlar_path = tmp_path / "dataset.sqlar"
    json_path = _write_json(tmp_path, "dataset.json", document)
    write_dataset_sqlar(document, sqlar_path)

    sqlar = DatasetLoader("sqlar_round_trip", sqlar_path)
    plain = DatasetLoader("json_round_trip", json_path)
    assert sqlar.meta == plain.meta
    assert _materialize(sqlar.index) == _materialize(plain.index)
    assert _materialize(sqlar.data) == _materialize(plain.data)


def test_sqlar_storage_rule(tmp_path: Path) -> None:
    document = _sqlar_doc()
    document["data"]["repetitive"] = "a" * 10000
    path = tmp_path / "storage.sqlar"
    write_dataset_sqlar(document, path)

    with sqlite3.connect(path) as connection:
        raw_size, raw_data = connection.execute(
            "SELECT sz, data FROM sqlar WHERE name = 'data/words/00000.json'"
        ).fetchone()
        compressed_size, compressed_data = connection.execute(
            "SELECT sz, data FROM sqlar WHERE name = 'data/repetitive.json'"
        ).fetchone()
    assert len(raw_data) == raw_size
    assert len(compressed_data) < compressed_size


def test_sqlar_output_is_deterministic(tmp_path: Path) -> None:
    document = _sqlar_doc()
    first = tmp_path / "first.sqlar"
    second = tmp_path / "second.sqlar"
    write_dataset_sqlar(document, first)
    write_dataset_sqlar(document, second)
    assert first.read_bytes() == second.read_bytes()


def test_sqlar_views_are_lazy_and_memoized(tmp_path: Path) -> None:
    path = tmp_path / "lazy.sqlar"
    write_dataset_sqlar(_sqlar_doc(), path)
    records = DatasetLoader("sqlar_lazy", path).data.records
    assert isinstance(records, Sequence)
    record = records[0]
    assert isinstance(record, Mapping)
    assert set(record) == {"nested", "label", "count"}
    assert record["nested"] is record["nested"]


def test_sqlar_views_pickle_as_materialized_containers(tmp_path: Path) -> None:
    document = _sqlar_doc()
    sqlar_path = tmp_path / "pickle.sqlar"
    json_path = _write_json(tmp_path, "pickle.json", document)
    write_dataset_sqlar(document, sqlar_path)
    sqlar = DatasetLoader("sqlar_pickle", sqlar_path)
    plain = DatasetLoader("json_pickle", json_path)

    record = sqlar.data.records[0]
    plain_record = plain.data.records[0]
    restored_record = pickle.loads(pickle.dumps(record))
    assert dict(restored_record) == plain_record
    assert isinstance(restored_record, DatasetRecord)
    assert isinstance(pickle.loads(pickle.dumps(record._data)), dict)

    restored_data = pickle.loads(pickle.dumps(sqlar.data))
    restored_sequence = pickle.loads(pickle.dumps(sqlar.data.records))
    assert _materialize(restored_data) == _materialize(plain.data)
    assert _materialize(restored_sequence) == _materialize(plain.data.records)

    assert pickle.dumps(record) == pickle.dumps(record)


def test_sqlar_errors(tmp_path: Path) -> None:
    document = _sqlar_doc()
    with pytest.raises(ValueError):
        write_dataset_sqlar(document, tmp_path / "wrong.sqlite")
    document["data"]["bad/name"] = []
    with pytest.raises(ValueError):
        write_dataset_sqlar(document, tmp_path / "bad.sqlar")
    document = _sqlar_doc()
    document["data"]["records"][0]["bad/name"] = 1
    with pytest.raises(ValueError):
        write_dataset_sqlar(document, tmp_path / "bad_field.sqlar")

    document = _sqlar_doc()
    path = tmp_path / "source.sqlar"
    write_dataset_sqlar(document, path)
    with pytest.raises(ValueError, match="must not be compressed"):
        _ = DatasetLoader("sqlar_compressed_name", f"{path}.gz").data
    with pytest.raises(ValueError, match="decode_object"):
        _ = DatasetLoader("sqlar_decode", path, decode_object=lambda obj, url: obj).data
    with pytest.raises(ValueError, match="plain filename"):
        _ = DatasetLoader("sqlar_content", str(path), kind="content").data

    missing = tmp_path / "missing_header.sqlar"
    with sqlite3.connect(missing) as connection:
        connection.execute("CREATE TABLE sqlar(name TEXT PRIMARY KEY, mode INT, mtime INT, sz INT, data BLOB)")
        connection.execute("INSERT INTO sqlar VALUES ('data/a.json', 33188, 0, 1, '1')")
    with pytest.raises(ValueError, match="header.json"):
        _ = DatasetLoader("sqlar_missing_header", missing).data


def test_sqlar_dedup_same_identifier_reuses_first_load(tmp_path: Path) -> None:
    path = tmp_path / "dedup.sqlar"
    write_dataset_sqlar(_sqlar_doc(), path)
    first = DatasetLoader("sqlar_dedup_shared", path)
    _ = first.data
    second = DatasetLoader("sqlar_dedup_shared", tmp_path / "not-there.sqlar")
    assert second.data is first.data
    assert second.meta is first.meta
    assert second.index is first.index


def test_sqlar_rejects_unrepresentable_empty_values(tmp_path: Path) -> None:
    empty_list = {"data": {"empty": []}}
    with pytest.raises(ValueError, match="dataset 'empty' cannot be an empty list"):
        write_dataset_sqlar(empty_list, tmp_path / "empty_list.sqlar")

    empty_record = {"data": {"records": [{"a": 1}, {}]}}
    with pytest.raises(ValueError, match="dataset 'records' record 1 cannot be empty"):
        write_dataset_sqlar(empty_record, tmp_path / "empty_record.sqlar")


def test_sqlar_lazy_read_is_cross_thread_safe(tmp_path: Path) -> None:
    path = tmp_path / "threaded.sqlar"
    write_dataset_sqlar(_sqlar_doc(), path)
    loader = DatasetLoader("sqlar_threaded", path)
    records = loader.data.records
    values: list[str] = []
    errors: list[BaseException] = []

    def read_field() -> None:
        try:
            values.append(records[0]["label"])
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=read_field)
    thread.start()
    thread.join()
    assert errors == []
    assert values == ["first"]


def test_sqlar_accepts_canonical_six_digit_indices() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        names = ["header.json"] + [f"data/large/{index:05d}.json" for index in range(100001)]
        store = _SqlarStore(connection, names)
        assert len(store.sequence("large")) == 100001
    finally:
        connection.close()

    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="invalid sqlar record member name"):
            _SqlarStore(connection, ["header.json", "data/large/00001.json", "data/large/000001.json"])
    finally:
        connection.close()


def test_sqlar_rejects_member_size_mismatches(tmp_path: Path) -> None:
    compressed_path = tmp_path / "bad_compressed.sqlar"
    compressed = zlib.compress(b"a" * 100)
    with sqlite3.connect(compressed_path) as connection:
        connection.execute("CREATE TABLE sqlar(name TEXT PRIMARY KEY, mode INT, mtime INT, sz INT, data BLOB)")
        connection.executemany(
            "INSERT INTO sqlar VALUES (?, 33188, 0, ?, ?)",
            [("header.json", 2, b"{}"), ("data/bad.json", 101, compressed)],
        )
    with pytest.raises(ValueError, match="invalid compressed sqlar member"):
        _ = DatasetLoader("sqlar_bad_compressed_size", compressed_path).data["bad"]

    raw_path = tmp_path / "bad_raw.sqlar"
    with sqlite3.connect(raw_path) as connection:
        connection.execute("CREATE TABLE sqlar(name TEXT PRIMARY KEY, mode INT, mtime INT, sz INT, data BLOB)")
        connection.executemany(
            "INSERT INTO sqlar VALUES (?, 33188, 0, ?, ?)",
            [("header.json", 2, b"{}"), ("data/bad.json", 1, b"12")],
        )
    with pytest.raises(ValueError, match="invalid raw sqlar member"):
        _ = DatasetLoader("sqlar_bad_raw_size", raw_path).data["bad"]


def test_sqlar_rejects_duplicate_member_names(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.sqlar"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sqlar(name TEXT, mode INT, mtime INT, sz INT, data BLOB)")
        connection.executemany(
            "INSERT INTO sqlar VALUES (?, 33188, 0, ?, ?)",
            [("header.json", 2, b"{}"), ("header.json", 2, b"{}")],
        )
    with pytest.raises(ValueError, match="duplicate member names"):
        _ = DatasetLoader("sqlar_duplicate_names", path).data


def test_sqlar_failed_overwrite_preserves_destination(tmp_path: Path) -> None:
    path = tmp_path / "overwrite.sqlar"
    write_dataset_sqlar(_sqlar_doc(), path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="dataset 'empty' cannot be an empty list"):
        write_dataset_sqlar({"data": {"empty": []}}, path)
    assert path.read_bytes() == original
    assert DatasetLoader("sqlar_overwrite_survives", path).data.records[0]["label"] == "first"


def test_sqlar_successful_write_preserves_old_predictable_tmp(tmp_path: Path) -> None:
    path = tmp_path / "safe.sqlar"
    old_tmp = path.with_name(path.name + ".tmp")
    old_tmp.write_bytes(b"unrelated file")
    write_dataset_sqlar(_sqlar_doc(), path)
    assert old_tmp.read_bytes() == b"unrelated file"


def test_sqlar_rejects_member_size_over_limit(tmp_path: Path) -> None:
    path = tmp_path / "oversized.sqlar"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sqlar(name TEXT PRIMARY KEY, mode INT, mtime INT, sz INT, data BLOB)")
        connection.executemany(
            "INSERT INTO sqlar VALUES (?, 33188, 0, ?, ?)",
            [("header.json", 2, b"{}"), ("data/too_large.json", _MAX_MEMBER_BYTES + 1, b"x")],
        )
    with pytest.raises(ValueError, match=f"too_large.*{_MAX_MEMBER_BYTES}"):
        _ = DatasetLoader("sqlar_oversized_member", path).data["too_large"]
