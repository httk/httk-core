#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import urllib.parse
import zlib
from collections.abc import Callable, Iterator, KeysView, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

from .datastream import TextstreamFileView, TextstreamLike
from .datastream.compression import split_compression_suffix

_MAX_MEMBER_BYTES = 256 * 1024 * 1024

type DecodeObjectCallback = Callable[[dict[str, Any], str], Any]
"""Callback invoked as ``(dict_obj, jsonld_url)`` that returns the value to use in place of
``dict_obj`` (return the input unchanged to decline)."""


class DatasetLoaderRecord(Mapping[str, Any]):
    """Read-only attribute and mapping view over a ``Mapping[str, Any]``.

    Top-level keys are reachable both as attributes (``record.name``) and as items
    (``record["name"]``); the wrapped values are the plain parsed JSON and are not
    themselves wrapped. Supports iteration over keys, ``len()``, ``in``, and ``keys()``.

    :param data: The parsed top-level object exposed by this view.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        # Underscored names are never data keys; failing fast here also avoids recursing
        # into self._data lookups when _data itself is not yet set (copy/unpickling).
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __reduce__(self) -> tuple[type["DatasetLoaderRecord"], tuple[dict[str, Any]]]:
        return DatasetLoaderRecord, (dict(self._data),)

    def keys(self) -> KeysView[str]:
        """Return a dynamic view of the record's top-level keys.

        :return: The wrapped mapping's keys view.
        """
        return self._data.keys()

    def __repr__(self) -> str:
        return f"DatasetLoaderRecord({self._data!r})"


@dataclass(frozen=True)
class DatasetMeta:
    """Describe header metadata extracted from a structured JSON-LD document.

    :param context: The raw document context.
    :param id: The document identifier, if present.
    :param type_: The document type, if present.
    :param header: Remaining top-level header fields.
    :param dataset_ids: Dataset names mapped to their identifiers.
    :param fields: Dataset names mapped to their field property URLs.
    """

    context: dict[str, Any]
    """The raw ``@context`` object."""

    id: str | None
    """The document ``@id``, or ``None`` if absent."""

    type_: str | None
    """The document ``@type``, or ``None`` if absent (trailing underscore avoids the builtin ``type``)."""

    header: dict[str, Any]
    """All remaining top-level keys except ``data``, ``indicies``, and ``@``-keys (titles, creator, license, provenance, ...)."""

    dataset_ids: dict[str, str]
    """Mapping of dataset name to its ``@id``."""

    fields: dict[str, dict[str, str]]
    """Mapping of dataset name to a mapping of field name to its property URL."""


@dataclass(frozen=True)
class _LoadedData:
    data: Any
    meta: DatasetMeta | None
    index: DatasetLoaderRecord | None


class _SqlarStore:
    def __init__(self, connection: sqlite3.Connection, names: list[str]) -> None:
        self.connection = connection
        self.lock = threading.Lock()
        self.names = set(names)
        self.dataset_names: list[str] = []
        self.specs: dict[str, dict[str, Any]] = {}
        self.cache: dict[str, Any] = {}
        self.sequences: dict[str, Any] = {}

        for name in names:
            if name in ("header.json", "indicies.json"):
                continue
            if not name.startswith("data/") or not name.endswith(".json"):
                raise ValueError(f"invalid sqlar member name: {name!r}")
            parts = name[5:].split("/")
            dataset_name = parts[0][:-5] if len(parts) == 1 else parts[0]
            if dataset_name not in self.specs:
                self.dataset_names.append(dataset_name)
                self.specs[dataset_name] = {"scalar": None, "records": {}}
            spec = self.specs[dataset_name]
            if len(parts) == 1:
                if spec["scalar"] is not None or spec["records"]:
                    raise ValueError(f"conflicting sqlar members for dataset {dataset_name!r}")
                spec["scalar"] = name
            elif len(parts) == 2:
                index_name = parts[1][:-5]
                index = _sqlar_index(index_name)
                if index is None:
                    raise ValueError(f"invalid sqlar record member name: {name!r}")
                if spec["scalar"] is not None:
                    raise ValueError(f"conflicting sqlar members for dataset {dataset_name!r}")
                record = spec["records"].setdefault(index, {"value": None, "fields": {}})
                if record["value"] is not None or record["fields"]:
                    raise ValueError(f"conflicting sqlar members for record {name!r}")
                record["value"] = name
            elif len(parts) == 3:
                index_name = parts[1]
                field_name = parts[2][:-5]
                index = _sqlar_index(index_name)
                if index is None:
                    raise ValueError(f"invalid sqlar record member name: {name!r}")
                if spec["scalar"] is not None:
                    raise ValueError(f"conflicting sqlar members for dataset {dataset_name!r}")
                record = spec["records"].setdefault(index, {"value": None, "fields": {}})
                if record["value"] is not None or field_name in record["fields"]:
                    raise ValueError(f"conflicting sqlar members for record {name!r}")
                record["fields"][field_name] = name
            else:
                raise ValueError(f"invalid sqlar member name: {name!r}")

        for dataset_name, spec in self.specs.items():
            records = spec["records"]
            if records and sorted(records) != list(range(len(records))):
                raise ValueError(f"non-contiguous sqlar records for dataset {dataset_name!r}")

    def read(self, name: str) -> Any:
        with self.lock:
            return self._read_locked(name)

    def _read_locked(self, name: str) -> Any:
        if name not in self.cache:
            size_row = self.connection.execute("SELECT sz FROM sqlar WHERE name=?", (name,)).fetchone()
            if size_row is None:
                raise ValueError(f"missing sqlar member: {name!r}")
            size = size_row[0]
            if size > _MAX_MEMBER_BYTES:
                raise ValueError(f"sqlar member {name!r} exceeds {_MAX_MEMBER_BYTES} byte limit")
            data_row = self.connection.execute("SELECT data FROM sqlar WHERE name=?", (name,)).fetchone()
            if data_row is None:
                raise ValueError(f"missing sqlar member: {name!r}")
            raw = data_row[0]
            if len(raw) < size:
                try:
                    decompressor = zlib.decompressobj()
                    content = decompressor.decompress(raw, size)
                    if decompressor.unconsumed_tail or not decompressor.eof or decompressor.unused_data:
                        raise ValueError(f"invalid compressed sqlar member: {name!r}")
                    flushed = decompressor.flush()
                except zlib.error as error:
                    raise ValueError(f"invalid compressed sqlar member: {name!r}") from error
                if flushed or len(content) != size:
                    raise ValueError(f"invalid compressed sqlar member: {name!r}")
            else:
                if len(raw) != size:
                    raise ValueError(f"invalid raw sqlar member: {name!r}")
                content = raw
            self.cache[name] = json.loads(content)
        return self.cache[name]

    def sequence(self, dataset_name: str) -> "_SqlarSequence":
        with self.lock:
            if dataset_name not in self.sequences:
                self.sequences[dataset_name] = _SqlarSequence(self, self.specs[dataset_name]["records"])
            return self.sequences[dataset_name]


def _sqlar_index(segment: str) -> int | None:
    if not segment.isdigit():
        return None
    index = int(segment)
    return index if segment == f"{index:05d}" else None


class _SqlarRecordMapping(Mapping[str, Any]):
    def __init__(self, store: _SqlarStore, fields: dict[str, str]) -> None:
        self._store = store
        self._fields = fields

    def __getitem__(self, key: str) -> Any:
        return self._store.read(self._fields[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __reduce__(self) -> tuple[type[dict[str, Any]], tuple[dict[str, Any]]]:
        return dict, (dict(self),)


class _SqlarSequence(Sequence[Any]):
    def __init__(self, store: _SqlarStore, records: dict[int, dict[str, Any]]) -> None:
        self._store = store
        self._records = records
        self._cache: list[Any] = [None] * len(records)
        self._loaded = [False] * len(records)

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            return [self[position] for position in range(*index.indices(len(self)))]
        with self._store.lock:
            if index < 0:
                index += len(self)
            if index < 0 or index >= len(self):
                raise IndexError(index)
            if not self._loaded[index]:
                record = self._records[index]
                if record["fields"]:
                    self._cache[index] = DatasetLoaderRecord(_SqlarRecordMapping(self._store, record["fields"]))
                else:
                    self._cache[index] = self._store._read_locked(record["value"])
                self._loaded[index] = True
            return self._cache[index]

    def __len__(self) -> int:
        return len(self._records)

    def __reduce__(self) -> tuple[type[list[Any]], tuple[list[Any]]]:
        return list, (list(self),)


class _SqlarDataMapping(Mapping[str, Any]):
    def __init__(self, store: _SqlarStore) -> None:
        self._store = store

    def __getitem__(self, key: str) -> Any:
        try:
            spec = self._store.specs[key]
        except KeyError:
            raise KeyError(key) from None
        scalar = spec["scalar"]
        return self._store.read(scalar) if scalar is not None else self._store.sequence(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._store.dataset_names)

    def __len__(self) -> int:
        return len(self._store.dataset_names)

    def __reduce__(self) -> tuple[type[dict[str, Any]], tuple[dict[str, Any]]]:
        return dict, ({name: self[name] for name in self},)


def _sqlar_content(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sqlar_members(document: dict[str, Any]) -> list[tuple[str, bytes]]:
    data = document.get("data")
    if not isinstance(data, dict):
        raise ValueError("sqlar dataset document data must be a dict")

    members: list[tuple[str, bytes]] = []
    header = {key: value for key, value in document.items() if key not in ("data", "indicies")}
    members.append(("header.json", _sqlar_content(header)))
    if "indicies" in document:
        members.append(("indicies.json", _sqlar_content(document["indicies"])))
    for dataset_name, entries in data.items():
        if "/" in dataset_name:
            raise ValueError(f"sqlar dataset name contains '/': {dataset_name!r}")
        if isinstance(entries, list):
            if not entries:
                raise ValueError(f"sqlar dataset {dataset_name!r} cannot be an empty list")
            for index, entry in enumerate(entries):
                prefix = f"data/{dataset_name}/{index:05d}"
                if isinstance(entry, dict):
                    if not entry:
                        raise ValueError(f"sqlar dataset {dataset_name!r} record {index} cannot be empty")
                    for field_name, value in entry.items():
                        if "/" in field_name:
                            raise ValueError(f"sqlar record field name contains '/': {field_name!r}")
                        members.append((f"{prefix}/{field_name}.json", _sqlar_content(value)))
                else:
                    members.append((f"{prefix}.json", _sqlar_content(entry)))
        else:
            members.append((f"data/{dataset_name}.json", _sqlar_content(entries)))
    return members


def write_dataset_sqlar(document: dict[str, Any], destination: str | Path) -> None:
    """Write a structured JSON-LD dataset document as a deterministic sqlar archive.

    Empty list datasets and empty dictionary records are unsupported because the sqlar member
    grammar has no representation for them; this function raises instead of losing data.

    :param document: Structured JSON-LD dataset document to archive.
    :param destination: Destination filename ending in ``.sqlar``.
    :raises ValueError: If the destination or document cannot be represented by the sqlar format.
    """
    destination_path = Path(destination)
    if not str(destination_path).endswith(".sqlar"):
        raise ValueError("sqlar destination must end with .sqlar")
    members = _sqlar_members(document)
    temporary_directory = Path(tempfile.mkdtemp(dir=destination_path.parent, prefix=f".{destination_path.name}."))
    temporary_path = temporary_directory / "archive.sqlar"
    try:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE TABLE sqlar(name TEXT PRIMARY KEY, mode INT, mtime INT, sz INT, data BLOB)")
            for name, content in members:
                compressed = zlib.compress(content, 9)
                stored = compressed if len(compressed) < len(content) else content
                connection.execute(
                    "INSERT INTO sqlar VALUES (?, ?, ?, ?, ?)",
                    (name, 33188, 0, len(content), stored),
                )
            connection.commit()
            connection.execute("VACUUM INTO ?", (str(temporary_path),))
        os.replace(temporary_path, destination_path)
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


def _build_meta(doc: dict[str, Any]) -> DatasetMeta:
    context = doc.get("@context", {})
    if not isinstance(context, dict):
        context = {}

    header = {key: value for key, value in doc.items() if key not in ("data", "indicies") and not key.startswith("@")}

    dataset_ids: dict[str, str] = {}
    fields: dict[str, dict[str, str]] = {}

    data_context = context.get("data", {})
    nested = data_context.get("@context", {}) if isinstance(data_context, dict) else {}
    if isinstance(nested, dict):
        for dataset_name, spec in nested.items():
            if not isinstance(spec, dict):
                continue
            dataset_id = spec.get("@id")
            if isinstance(dataset_id, str):
                dataset_ids[dataset_name] = dataset_id
            field_context = spec.get("@context")
            if isinstance(field_context, dict):
                field_urls = {field: url for field, url in field_context.items() if isinstance(url, str)}
                if field_urls:
                    fields[dataset_name] = field_urls

    return DatasetMeta(
        context=context,
        id=doc.get("@id"),
        type_=doc.get("@type"),
        header=header,
        dataset_ids=dataset_ids,
        fields=fields,
    )


def _decode_entry(
    entry: dict[str, Any],
    field_urls: dict[str, str],
    dataset_id: str | None,
    decode: DecodeObjectCallback,
) -> Any:
    for field_name, url in field_urls.items():
        value = entry.get(field_name)
        if isinstance(value, dict):
            entry[field_name] = decode(value, url)
    if dataset_id is None:
        return entry
    return decode(entry, dataset_id)


def _apply_decode(data: dict[str, Any], meta: DatasetMeta, decode: DecodeObjectCallback) -> None:
    for dataset_name, entries in data.items():
        dataset_id = meta.dataset_ids.get(dataset_name)
        field_urls = meta.fields.get(dataset_name, {})
        if dataset_id is None and not field_urls:
            continue
        if isinstance(entries, dict):
            data[dataset_name] = _decode_entry(entries, field_urls, dataset_id, decode)
        elif isinstance(entries, list):
            data[dataset_name] = [
                _decode_entry(entry, field_urls, dataset_id, decode) if isinstance(entry, dict) else entry
                for entry in entries
            ]


class DatasetLoader:
    r"""Lazy loader for httk dataset files, resolved only when data is first accessed.

    A ``DatasetLoader`` is a declare-time placeholder: constructing it records its arguments
    and performs no I/O. The source is read the first time ``data``, ``meta``, or ``index``
    is accessed. Files are either plain JSON (any JSON value is exposed as ``data`` with
    ``meta``/``index`` set to ``None``) or a structured JSON-LD document (with ``@context``,
    header fields, ``data``, and optional ``indicies``) whose header is exposed via ``meta``,
    datasets via ``data.<name>``, and lookup indices via ``index.<name>``.

    Loaders that share an ``identifier`` deduplicate through a class-level registry: the
    first load wins, and later loaders reusing that identifier return the same result while
    their ``source`` and ``decode_object`` arguments are ignored. Keeping identifiers unique
    is the caller's responsibility. Not thread-safe.

    Format is resolved from the source name after stripping any compression suffix: a ``.json``
    name (e.g. ``data.json`` or ``data.json.gz``) is parsed as JSON; any other recognizable
    suffix raises ``ValueError``; a source with no determinable name is treated as JSON.
    Compression is handled transparently by the stream layer, so ``.json.gz`` and similar load
    directly. A plain ``.sqlar`` file is an alternative structured JSON-LD representation. It
    contains ``header.json``, optional ``indicies.json``, scalar ``data/{D}.json`` members, and
    list members at ``data/{D}/{i:05d}.json`` or ``data/{D}/{i:05d}/{field}.json``. Sqlar sources
    require a real filename because their immutable SQLite connection is retained for the
    lifetime of the cached load; they cannot be compressed, streamed, or loaded from content.
    Empty list datasets and empty dictionary records cannot be represented and are rejected by
    the writer; individual members are limited to 256 MiB. Sqlar-backed record/sequence/data
    views (and ``DatasetLoaderRecord``) pickle by
    materializing to plain containers; live iterators over them are not picklable.
    A ``str``/``Path`` source is interpreted as a filename unless its scheme marks it
    as a URL (``http``, ``https``, ``ftp``, ``file``); bare network URLs are refused at read time,
    so pass ``kind="url"`` or a ``urllib.request.Request``. Pass ``kind="content"`` for literal
    content or ``kind="filename"`` to force a filename interpretation.

    Example:
        symmetry_basics = DatasetLoader("symmetry_basics", "data/spacegroup_symbols.json")
        spacegroups = symmetry_basics.data.spacegroups  # first access triggers the load

    :param identifier: The deduplication key for this load.
    :param source: The filename, URL-like stream, request, or literal content to read.
    :param decode_object: An optional callback for JSON-LD objects identified by context URLs.
    :param \**hints: Stream interpretation hints such as ``kind``.
    """

    _loaded: ClassVar[dict[str, _LoadedData]] = {}

    def __init__(
        self,
        identifier: str,
        source: TextstreamLike,
        decode_object: DecodeObjectCallback | None = None,
        **hints: Any,
    ) -> None:
        self._identifier = identifier
        self._source = source
        self._decode_object = decode_object
        self._hints = hints

    def _resolve_name(self) -> str | None:
        source = self._source
        if isinstance(source, (str, Path)):
            # With kind="content" the string is the data itself, not a name.
            if self._hints.get("kind") == "content":
                return None
            return str(source)
        url = getattr(source, "url", None)
        if isinstance(url, str):
            return url
        name = getattr(source, "name", None)
        if isinstance(name, str):
            return name
        return None

    def _load_sqlar(self) -> _LoadedData:
        if self._decode_object is not None:
            raise ValueError("decode_object is not supported for sqlar sources")
        source = self._source
        kind = self._hints.get("kind")
        if kind in ("content", "url") or not isinstance(source, (str, Path)):
            raise ValueError("sqlar sources require a plain filename; content, URLs, and streams are unsupported")
        if (
            isinstance(source, str)
            and kind != "filename"
            and urllib.parse.urlsplit(source).scheme
            in (
                "http",
                "https",
                "ftp",
                "file",
            )
        ):
            raise ValueError("sqlar sources require a plain filename; URLs are unsupported")

        path = Path(source).resolve()
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, check_same_thread=False)
        try:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlar")]
            if len(names) != len(set(names)):
                raise ValueError("sqlar source contains duplicate member names")
            if "header.json" not in names:
                raise ValueError("sqlar source is missing required header.json")
            store = _SqlarStore(connection, names)
            header = store.read("header.json")
            if not isinstance(header, dict):
                raise ValueError("sqlar header.json must contain an object")
            meta = _build_meta(header)
            index = None
            if "indicies.json" in store.names:
                index_value = store.read("indicies.json")
                if isinstance(index_value, dict):
                    index = DatasetLoaderRecord(index_value)
            data = DatasetLoaderRecord(_SqlarDataMapping(store))
        except BaseException:
            connection.close()
            raise
        return _LoadedData(data=data, meta=meta, index=index)

    def _load(self) -> _LoadedData:
        if self._identifier in DatasetLoader._loaded:
            return DatasetLoader._loaded[self._identifier]

        name = self._resolve_name()
        dispatch_name = name
        if dispatch_name is None and isinstance(self._source, (str, Path)):
            candidate = str(self._source)
            candidate_base, _candidate_codec = split_compression_suffix(candidate)
            if Path(candidate_base).suffix.lower() == ".sqlar":
                dispatch_name = candidate
        if dispatch_name is not None:
            base, codec = split_compression_suffix(dispatch_name)
            suffix = Path(base).suffix.lower()
            if suffix == ".sqlar":
                if codec is not None:
                    raise ValueError("sqlar sources must not be compressed")
                loaded = self._load_sqlar()
                DatasetLoader._loaded[self._identifier] = loaded
                return loaded
            if suffix not in ("", ".json"):
                raise ValueError(f"unsupported data format: {suffix}")

        doc = json.load(TextstreamFileView(self._source, **self._hints))

        if isinstance(doc, dict) and "@context" in doc:
            meta = _build_meta(doc)
            data_section = doc.get("data")
            if self._decode_object is not None and isinstance(data_section, dict):
                _apply_decode(data_section, meta, self._decode_object)
            data: Any = DatasetLoaderRecord(data_section) if isinstance(data_section, dict) else data_section
            index_section = doc.get("indicies")
            index = DatasetLoaderRecord(index_section) if isinstance(index_section, dict) else None
            loaded = _LoadedData(data=data, meta=meta, index=index)
        else:
            loaded = _LoadedData(data=doc, meta=None, index=None)

        DatasetLoader._loaded[self._identifier] = loaded
        return loaded

    @cached_property
    def data(self) -> Any:
        """Return the lazily loaded dataset value."""
        return self._load().data

    @cached_property
    def meta(self) -> DatasetMeta | None:
        """Return structured-document metadata, or ``None`` for plain JSON."""
        return self._load().meta

    @cached_property
    def index(self) -> DatasetLoaderRecord | None:
        """Return structured-document lookup indices, or ``None`` when absent."""
        return self._load().index
