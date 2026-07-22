import gzip
import json
import pickle
from pathlib import Path
from typing import Any

import pytest

from httk.core import DataLoader, DataRecord, DatasetMeta


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
    loader = DataLoader("plain_dict", p)
    assert loader.data == {"a": 1, "b": [2, 3]}
    assert not isinstance(loader.data, DataRecord)
    assert loader.meta is None
    assert loader.index is None


def test_plain_json_bare_list(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "list.json", [1, 2, 3])
    loader = DataLoader("plain_list", p)
    assert loader.data == [1, 2, 3]
    assert loader.meta is None
    assert loader.index is None


def test_plain_json_number(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "number.json", 42)
    loader = DataLoader("plain_number", p)
    assert loader.data == 42
    assert loader.meta is None
    assert loader.index is None


def test_structured_meta_and_records(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "structured.json", _structured_doc())
    loader = DataLoader("structured_meta", p)

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
    assert isinstance(data, DataRecord)
    assert data.spacegroups == data["spacegroups"]
    assert data.spacegroups[0]["symbol"] == "P1"

    index = loader.index
    assert isinstance(index, DataRecord)
    assert index.by_number == index["by_number"]
    assert index["by_number"]["2"] == 1


def test_datarecord_mapping_protocol(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "record.json", _structured_doc())
    data = DataLoader("record_protocol", p).data
    assert len(data) == 1
    assert "spacegroups" in data
    assert list(iter(data)) == ["spacegroups"]
    assert list(data.keys()) == ["spacegroups"]
    assert "spacegroups" in repr(data)
    with pytest.raises(AttributeError):
        _ = data.missing


def test_laziness_defers_io_until_access() -> None:
    loader = DataLoader("lazy_missing", "/no/such/file/really.json")
    with pytest.raises(OSError):
        _ = loader.data


def test_dedup_same_identifier_reuses_first_load(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "dedup.json", _structured_doc())
    first = DataLoader("dedup_shared", p)
    _ = first.data  # trigger the load

    second = DataLoader("dedup_shared", "/bogus/nonexistent.json")
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

    loader = DataLoader("decode_both", p, decode_object=decode)
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

    loader = DataLoader("plain_no_decode", p, decode_object=decode)
    assert loader.data == {"a": 1}
    assert calls == []


def test_unsupported_suffix_raises(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "data.yaml", {"a": 1})
    loader = DataLoader("unsupported_yaml", p)
    with pytest.raises(ValueError):
        _ = loader.data


def test_datarecord_underscore_attributes_raise_and_pickle_roundtrips() -> None:
    record = DataRecord({"a": 1})
    with pytest.raises(AttributeError):
        _ = record._missing
    restored = pickle.loads(pickle.dumps(record))
    assert restored["a"] == 1
    assert restored.a == 1


def test_content_string_source_is_not_treated_as_filename() -> None:
    loader = DataLoader("content_number", "3.5", kind="content")
    assert loader.data == 3.5


def test_field_urls_decoded_even_without_dataset_id(tmp_path: Path) -> None:
    doc = _structured_doc()
    del doc["@context"]["data"]["@context"]["spacegroups"]["@id"]
    p = _write_json(tmp_path, "no_dataset_id.json", doc)
    calls: list[str] = []

    def decode(obj: dict[str, Any], url: str) -> Any:
        calls.append(url)
        return obj

    loader = DataLoader("fields_without_dataset_id", p, decode_object=decode)
    assert loader.data.spacegroups[0]["number"] == 1
    # Field-level URLs still fire; no entry-level calls without a dataset @id.
    assert calls == ["https://example.org/hall", "https://example.org/hall"]


def test_structured_doc_tolerates_missing_data_key(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "headers_only.json", {"@context": {}, "@id": "urn:x", "title": "t"})
    loader = DataLoader("headers_only", p)
    assert loader.data is None
    assert loader.meta is not None
    assert loader.meta.id == "urn:x"
    assert loader.index is None


def test_load_from_file_url_source(tmp_path: Path) -> None:
    p = _write_json(tmp_path, "via_url.json", _structured_doc())
    # A bare file:// URL string is auto-recognized as a URL (no kind="url" needed).
    loader = DataLoader("file_url_source", p.as_uri())
    assert loader.data.spacegroups[1]["symbol"] == "P-1"
    assert loader.meta is not None
    assert loader.meta.id == "https://example.org/symmetry_basics"


def test_load_from_gzipped_json(tmp_path: Path) -> None:
    p = tmp_path / "symmetry.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(_structured_doc(), f)

    loader = DataLoader("gzip_structured", p)
    assert loader.data.spacegroups[0]["symbol"] == "P1"
    assert loader.meta is not None
    assert loader.meta.id == "https://example.org/symmetry_basics"


def test_load_from_gzipped_json_via_file_url(tmp_path: Path) -> None:
    p = tmp_path / "sym_url.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump({"a": 1, "b": [2, 3]}, f)

    # Extension is taken from the URL path; the stream layer decompresses transparently.
    loader = DataLoader("gzip_via_url", p.as_uri())
    assert loader.data == {"a": 1, "b": [2, 3]}
