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
from collections.abc import Callable, Iterator, KeysView
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

from .datastream import TextstreamFileView, TextstreamLike
from .datastream.compression import split_compression_suffix

type DecodeObjectCallback = Callable[[dict[str, Any], str], Any]
"""Callback invoked as ``(dict_obj, jsonld_url)`` that returns the value to use in place of
``dict_obj`` (return the input unchanged to decline)."""


class DatasetRecord:
    """Read-only attribute and mapping view over a ``dict[str, Any]``.

    Top-level keys are reachable both as attributes (``record.name``) and as items
    (``record["name"]``); the wrapped values are the plain parsed JSON and are not
    themselves wrapped. Supports iteration over keys, ``len()``, ``in``, and ``keys()``.

    :param data: The parsed top-level object exposed by this view.
    """

    def __init__(self, data: dict[str, Any]) -> None:
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

    def keys(self) -> KeysView[str]:
        """Return a dynamic view of the record's top-level keys.

        :return: The wrapped mapping's keys view.
        """
        return self._data.keys()

    def __repr__(self) -> str:
        return f"DatasetRecord({self._data!r})"


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
    index: DatasetRecord | None


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
    directly. A ``str``/``Path`` source is interpreted as a filename unless its scheme marks it
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

    def _load(self) -> _LoadedData:
        if self._identifier in DatasetLoader._loaded:
            return DatasetLoader._loaded[self._identifier]

        name = self._resolve_name()
        if name is not None:
            base, _ = split_compression_suffix(name)
            suffix = Path(base).suffix.lower()
            if suffix not in ("", ".json"):
                raise ValueError(f"unsupported data format: {suffix}")

        doc = json.load(TextstreamFileView(self._source, **self._hints))

        if isinstance(doc, dict) and "@context" in doc:
            meta = _build_meta(doc)
            data_section = doc.get("data")
            if self._decode_object is not None and isinstance(data_section, dict):
                _apply_decode(data_section, meta, self._decode_object)
            data: Any = DatasetRecord(data_section) if isinstance(data_section, dict) else data_section
            index_section = doc.get("indicies")
            index = DatasetRecord(index_section) if isinstance(index_section, dict) else None
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
    def index(self) -> DatasetRecord | None:
        """Return structured-document lookup indices, or ``None`` when absent."""
        return self._load().index
