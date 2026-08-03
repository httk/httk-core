"""Exact, immutable source documents received from an OPTIMADE service.

``OptimadeDocument`` deliberately stores the original response text. Use
``OptimadeDocument.create`` when a document may be persisted: it removes
credentials specifically from the top-level pagination ``links.next`` value
without parsing and reserializing the whole response, so semantic URL values,
JSON number spelling, and unrelated whitespace remain authoritative. Direct
dataclass construction is also available when the caller controls the values.
"""

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from types import MappingProxyType
from urllib.parse import unquote_plus, urlsplit, urlunsplit
from weakref import WeakKeyDictionary

from .datastream import TextstreamFileView
from .storage_markers import stored_property

_SENSITIVE_QUERY_KEYS = frozenset({"access_token", "api_key", "apikey", "token", "key"})
_NON_ENTRY_ENDPOINTS = frozenset({"info", "links", "versions", "extensions"})
_VERSION_SEGMENT = re.compile(r"v1(?:\.\d+){0,2}")


def redact_optimade_url(url: str) -> str:
    """Return *url* without userinfo, recognized sensitive query parameters, or its fragment.

    Non-URL strings are returned unchanged except for fragment removal.
    Non-sensitive URL spelling is retained byte-for-byte; decoding is used
    only to recognize query keys. Fragments are not semantically load-bearing
    for OPTIMADE URLs or file fetches and are never retained in diagnostics.
    """

    if not isinstance(url, str):
        raise TypeError(f"URL must be a str, got {type(url)!r}")
    try:
        split = urlsplit(url)
    except ValueError:
        # ``urlsplit`` rejects a few malformed URL authorities (notably bad
        # IPv6 brackets). Still remove recognizable credentials when retaining
        # the malformed source is necessary for a later diagnostic.
        before_fragment = url.partition("#")[0]
        before_query, query_separator, query = before_fragment.partition("?")
        scheme_end = before_query.find("://")
        if scheme_end < 0:
            return url
        authority_and_path = before_query[scheme_end + 3 :]
        authority, path_separator, path = authority_and_path.partition("/")
        authority = authority.rpartition("@")[2]
        kept_query = [
            item
            for item in query.split("&")
            if unquote_plus(item.partition("=")[0]).casefold() not in _SENSITIVE_QUERY_KEYS
        ]
        return (
            before_query[: scheme_end + 3]
            + authority
            + path_separator
            + path
            + (query_separator + "&".join(kept_query) if query_separator else "")
        )
    is_relative_url = split.path.startswith(("/", "./", "../")) or url.startswith("?")
    if not split.scheme and not split.netloc and not is_relative_url:
        return url.partition("#")[0]

    before_fragment = url.partition("#")[0]
    before_query, query_separator, query = before_fragment.partition("?")
    sanitized_base = before_query
    if split.netloc:
        if "://" in before_query:
            authority_start = before_query.index("://") + 3
        elif before_query.startswith("//"):
            authority_start = 2
        else:
            authority_start = 0
        slash_index = before_query.find("/", authority_start)
        authority_end = len(before_query) if slash_index < 0 else slash_index
        authority = before_query[authority_start:authority_end]
        sanitized_base = before_query[:authority_start] + authority.rpartition("@")[2] + before_query[authority_end:]

    kept_query = [
        item
        for item in query.split("&")
        if unquote_plus(item.partition("=")[0]).casefold() not in _SENSITIVE_QUERY_KEYS
    ]
    sanitized_query = "&".join(kept_query)
    return sanitized_base + (query_separator + sanitized_query if query_separator and sanitized_query else "")


def _json_string_end(text: str, start: int) -> int:
    """Return the exclusive end of the JSON string token at *start*."""

    index = start + 1
    escaped = False
    while index < len(text):
        character = text[index]
        index += 1
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return index
    raise ValueError("unterminated JSON string")


def _redacted_json_string_token(token: str, redacted: str) -> str:
    """Remove decoded URL characters while retaining kept JSON escapes."""

    units: list[tuple[str, str]] = []
    index = 1
    end = len(token) - 1
    while index < end:
        start = index
        if token[index] != "\\":
            index += 1
        elif index + 1 < end and token[index + 1] == "u":
            index += 6
            first = int(token[start + 2 : start + 6], 16)
            if (
                0xD800 <= first <= 0xDBFF
                and index + 5 < end
                and token[index : index + 2] == "\\u"
                and 0xDC00 <= int(token[index + 2 : index + 6], 16) <= 0xDFFF
            ):
                index += 6
        else:
            index += 2
        raw_unit = token[start:index]
        units.append((json.loads(f'"{raw_unit}"'), raw_unit))

    kept: list[str] = []
    wanted = 0
    for character, raw_unit in units:
        if wanted < len(redacted) and character == redacted[wanted]:
            kept.append(raw_unit)
            wanted += 1
    if wanted != len(redacted):
        # ``redact_optimade_url`` is deletion-only, but retain a safe fallback
        # if a future URL policy introduces replacement characters.
        return json.dumps(redacted, ensure_ascii=False)
    return '"' + "".join(kept) + '"'


def _pagination_string_spans(text: str) -> tuple[tuple[int, int, str], ...]:
    """Locate top-level ``links.next`` URL string tokens in valid JSON."""

    length = len(text)
    replacements: list[tuple[int, int, str]] = []

    def whitespace(index: int) -> int:
        while index < length and text[index] in " \t\r\n":
            index += 1
        return index

    def value(index: int, path: tuple[str | int, ...]) -> int:
        index = whitespace(index)
        if text[index] == '"':
            end = _json_string_end(text, index)
            if path in (("links", "next"), ("links", "next", "href")):
                decoded = json.loads(text[index:end])
                redacted = redact_optimade_url(decoded)
                if redacted != decoded:
                    replacements.append((index, end, _redacted_json_string_token(text[index:end], redacted)))
            return end
        if text[index] == "{":
            return object_value(index, path)
        if text[index] == "[":
            return array_value(index, path)
        while index < length and text[index] not in ",]} \t\r\n":
            index += 1
        return index

    def object_value(index: int, path: tuple[str | int, ...]) -> int:
        index = whitespace(index + 1)
        if text[index] == "}":
            return index + 1
        while True:
            key_start = index
            key_end = _json_string_end(text, key_start)
            key = json.loads(text[key_start:key_end])
            index = whitespace(key_end)
            if text[index] != ":":
                raise ValueError("missing JSON object colon")
            index = value(index + 1, path + (key,))
            index = whitespace(index)
            if text[index] == "}":
                return index + 1
            if text[index] != ",":
                raise ValueError("missing JSON object separator")
            index = whitespace(index + 1)

    def array_value(index: int, path: tuple[str | int, ...]) -> int:
        index = whitespace(index + 1)
        if text[index] == "]":
            return index + 1
        item_index = 0
        while True:
            index = value(index, path + (item_index,))
            item_index += 1
            index = whitespace(index)
            if text[index] == "]":
                return index + 1
            if text[index] != ",":
                raise ValueError("missing JSON array separator")
            index = whitespace(index + 1)

    end = whitespace(value(0, ()))
    if end != length:
        raise ValueError("trailing JSON content")
    return tuple(replacements)


def redact_optimade_document_text(text: str) -> str:
    """Sanitize only top-level pagination URLs, preserving source authority.

    A direct string ``links.next`` or its JSON:API link-object ``href`` has
    recognized URL credentials removed. Every other byte remains untouched:
    in particular URL-like object keys, resource attributes, relationships,
    extension values, whitespace, and number spelling are semantic source
    data. Malformed JSON is returned unchanged because its envelope path cannot
    be identified safely without guessing.
    """

    if not isinstance(text, str):
        raise TypeError(f"document text must be a str, got {type(text)!r}")
    try:
        # Validate first: the span scanner is intentionally small and must
        # never guess envelope paths in malformed content.
        json.loads(text)
        replacements = _pagination_string_spans(text)
    except (IndexError, json.JSONDecodeError, RecursionError, TypeError, ValueError):
        return text
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


@dataclass(frozen=True)
class OptimadeDocument:
    """Original OPTIMADE response text and the URL from which it was obtained.

    Direct construction performs no sanitization. Use :meth:`create` before
    storing an externally sourced document or URL.
    """

    text: str
    source_url: str

    @classmethod
    def create(cls, text: str, source_url: str) -> "OptimadeDocument":
        """Construct a source-exact document with safe pagination provenance."""

        return cls(redact_optimade_document_text(text), redact_optimade_url(source_url))


@dataclass(frozen=True)
class OptimadeSchemaSnapshot:
    """The ``/info/<entry_type>`` document applicable to a resource response."""

    entry_type: str
    info_document: OptimadeDocument


def optimade_entry_url_info(url: str) -> tuple[str, str] | None:
    """Return an OPTIMADE entry type and its derived info URL, if *url* has that shape."""

    split = urlsplit(url)
    path = split.path.rstrip("/")
    try:
        base, entry_type, entry_id = path.rsplit("/", 2)
    except ValueError:
        return None
    if (
        not entry_id
        or _VERSION_SEGMENT.fullmatch(entry_type)
        or entry_type in _NON_ENTRY_ENDPOINTS
        or re.fullmatch(r"[a-z_][a-z_0-9-]*", entry_type) is None
    ):
        return None
    return entry_type, urlunsplit((split.scheme, split.netloc, f"{base}/info/{entry_type}", "", ""))


def is_optimade_entry_url(url: str) -> bool:
    """Return whether *url* has the shape of an OPTIMADE single-entry URL."""

    return optimade_entry_url_info(url) is not None


def _read_optimade_url(url: str, *, timeout: float | None, label: str) -> str:
    try:
        with TextstreamFileView(url, kind="url", timeout=timeout) as source:
            return source.read()
    except Exception as exc:
        raise ValueError(f"Could not fetch OPTIMADE {label} URL {redact_optimade_url(url)!r}") from exc


def optimade_resource_from_url(url: str, *, timeout: float | None = None) -> "OptimadeResource":
    """Fetch one OPTIMADE entry and its schema snapshot from *url*.

    Redirects follow ``urllib`` defaults. Both requests use the datastream
    layer and honor ``timeout`` (or its configured default when it is ``None``).
    """

    shape = optimade_entry_url_info(url)
    if shape is None:
        raise ValueError(f"Not an OPTIMADE single-entry URL: {redact_optimade_url(url)!r}")
    entry_type, info_url = shape
    document = OptimadeDocument.create(_read_optimade_url(url, timeout=timeout, label="entry"), url)
    try:
        entry_root = optimade_document_root(document)
    except ValueError as exc:
        raise ValueError(f"OPTIMADE entry response at {redact_optimade_url(url)!r} is not valid JSON") from exc
    if not isinstance(entry_root.get("data"), Mapping):
        raise ValueError(
            f"OPTIMADE entry response at {redact_optimade_url(url)!r} must contain one object in 'data', not a list"
        )

    info_document = OptimadeDocument.create(_read_optimade_url(info_url, timeout=timeout, label="info"), info_url)
    try:
        info_root = optimade_document_root(info_document)
    except ValueError as exc:
        raise ValueError(f"OPTIMADE info response at {redact_optimade_url(info_url)!r} is not valid JSON") from exc
    if not isinstance(info_root.get("data"), Mapping):
        raise ValueError(
            f"OPTIMADE info response at {redact_optimade_url(info_url)!r} must contain an object in 'data'"
        )
    return OptimadeResource(document, 0, OptimadeSchemaSnapshot(entry_type, info_document))


type FrozenJson = None | bool | int | Decimal | str | tuple["FrozenJson", ...] | Mapping[str, "FrozenJson"]


def _freeze_json(value: object) -> FrozenJson:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, bool | int | Decimal | str):
        return value
    raise ValueError(f"Unexpected JSON value {value!r}")


_document_cache: WeakKeyDictionary[OptimadeDocument, Mapping[str, FrozenJson]] = WeakKeyDictionary()
_document_cache_lock = Lock()


def _parsed_root(document: OptimadeDocument) -> Mapping[str, FrozenJson]:
    with _document_cache_lock:
        cached = _document_cache.get(document)
        if cached is not None:
            return cached
        try:
            parsed = json.loads(document.text, parse_float=Decimal, parse_int=int)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OPTIMADE document is not valid JSON: {exc.msg}") from exc
        frozen = _freeze_json(parsed)
        if not isinstance(frozen, Mapping):
            raise ValueError("OPTIMADE document root must be a JSON object")
        _document_cache[document] = frozen
        return frozen


def optimade_document_root(document: OptimadeDocument) -> Mapping[str, FrozenJson]:
    """Return the immutable, Decimal-preserving root of *document* lazily.

    This is intentionally a small public seam for source-model consumers that
    need to interpret an OPTIMADE envelope or an ``/info`` document without
    duplicating JSON parsing.  The returned mapping is cached per equal
    :class:`OptimadeDocument` and must be treated as immutable.
    """

    return _parsed_root(document)


@dataclass(frozen=True)
class OptimadeResource(Mapping[str, FrozenJson]):
    """An immutable, lazily decoded OPTIMADE resource from an array or single-entry envelope."""

    document: OptimadeDocument
    data_index: int
    schema: OptimadeSchemaSnapshot

    def unwrap(self) -> Mapping[str, FrozenJson]:
        """Return the immutable resource object at this response's data index."""

        root = _parsed_root(self.document)
        data = root.get("data")
        if not isinstance(self.data_index, int) or isinstance(self.data_index, bool):
            raise TypeError("OPTIMADE resource data_index must be an int")
        if self.data_index < 0:
            raise IndexError(f"OPTIMADE resource data index out of range: {self.data_index}")
        if isinstance(data, Mapping):
            if self.data_index != 0:
                raise IndexError(f"OPTIMADE resource data index out of range: {self.data_index}")
            resource = data
        elif isinstance(data, tuple):
            try:
                resource = data[self.data_index]
            except IndexError as exc:
                raise IndexError(f"OPTIMADE resource data index out of range: {self.data_index}") from exc
        else:
            raise ValueError("OPTIMADE document root member 'data' must be a JSON array or object")
        if not isinstance(resource, Mapping):
            raise ValueError(f"OPTIMADE document data[{self.data_index}] must be a JSON object")
        return resource

    @stored_property
    def id(self) -> str:
        """The protocol-mandated JSON API resource identifier.

        This intentionally reads the JSON API envelope directly.  It is a
        generic source-resource capability, not semantic recognition of a
        transport property name.
        """

        value = self.unwrap().get("id")
        if not isinstance(value, str) or not value:
            raise ValueError("OPTIMADE resource top-level 'id' must be a nonempty string")
        return value

    @stored_property
    def type(self) -> str:
        """The protocol-mandated JSON API resource type identifier."""

        value = self.unwrap().get("type")
        if not isinstance(value, str) or not value:
            raise ValueError("OPTIMADE resource top-level 'type' must be a nonempty string")
        return value

    def __getitem__(self, key: str) -> FrozenJson:
        return self.unwrap()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.unwrap())

    def __len__(self) -> int:
        return len(self.unwrap())
