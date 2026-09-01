"""Format, parse, and validate human-readable httk entry identifiers."""

import logging
import re

__all__ = [
    "ALTERNATIVE_ID_PATTERN",
    "ALTERNATIVE_KIND_PATTERN",
    "ENTRY_ID_PATTERN",
    "IMMUTABLE_ID_PATTERN",
    "check_entry_id",
    "check_immutable_id",
    "format_alternative_id",
    "format_entry_id",
    "format_immutable_id",
    "is_url_safe_id",
    "parse_alternative_id",
    "parse_entry_id",
    "parse_immutable_id",
]

ENTRY_ID_PATTERN = re.compile(r"^([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)-([A-Za-z0-9_]+)-([1-9][0-9]*)$")
_ENTRY_ID_BODY = re.sub(r"\((?!\?)", "(?:", ENTRY_ID_PATTERN.pattern[1:-1])
IMMUTABLE_ID_PATTERN = re.compile(rf"^({_ENTRY_ID_BODY})~([1-9][0-9]*)$")
ALTERNATIVE_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ALTERNATIVE_ID_PATTERN = re.compile(rf"^({_ENTRY_ID_BODY})~([a-z][a-z0-9_]*)(?:~([1-9][0-9]*))?$")

_ENTRY_ID_SYNTAX = "<base>-<series>-<number>"
_IMMUTABLE_ID_SYNTAX = "<base>-<series>-<number>~<revision>"
_ALTERNATIVE_ID_SYNTAX = "<base>-<series>-<number>~<kind>[~<revision>]"


def format_entry_id(base: str, series: str, number: int) -> str:
    """Format a recommended entry identifier.

    :param base: Dot-separated identifier namespace.
    :param series: Identifier series token.
    :param number: Positive entry number.
    :return: The formatted entry identifier.
    :raises TypeError: If ``number`` is not a non-boolean integer.
    :raises ValueError: If the formatted identifier does not match the recommended syntax.
    """
    _validate_positive_int(number, "number")
    value = f"{base}-{series}-{number}"
    if ENTRY_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Invalid entry id {value!r}; expected {_ENTRY_ID_SYNTAX}.")
    return value


def format_immutable_id(entry_id: str, revision: int) -> str:
    """Format an immutable identifier for an entry revision.

    :param entry_id: URL-safe entry identifier, including non-conforming user identifiers.
    :param revision: Positive revision number.
    :return: The formatted immutable identifier.
    :raises TypeError: If ``revision`` is not a non-boolean integer.
    :raises ValueError: If ``entry_id`` is not URL-safe or ``revision`` is less than one.
    """
    _validate_positive_int(revision, "revision")
    if not is_url_safe_id(entry_id):
        raise ValueError(f"Invalid entry id {entry_id!r}; it must be URL-safe (non-empty printable ASCII without '/').")
    return f"{entry_id}~{revision}"


def format_alternative_id(entry_id: str, kind: str, revision: int | None = None) -> str:
    """Format an alternative identifier for a named alternative representation of an entry.

    :param entry_id: URL-safe entry identifier, including non-conforming user identifiers.
    :param kind: Alternative-kind token matching ``[a-z][a-z0-9_]*``.
    :param revision: Optional positive revision number of the alternative.
    :return: The formatted alternative identifier.
    :raises TypeError: If ``revision`` is given and is not a non-boolean integer.
    :raises ValueError: If ``kind`` is malformed, ``entry_id`` is not URL-safe, or ``revision`` is less than one.
    """
    if ALTERNATIVE_KIND_PATTERN.fullmatch(kind) is None:
        raise ValueError(f"Invalid alternative kind {kind!r}; expected {ALTERNATIVE_KIND_PATTERN.pattern}.")
    if not is_url_safe_id(entry_id):
        raise ValueError(f"Invalid entry id {entry_id!r}; it must be URL-safe (non-empty printable ASCII without '/').")
    if revision is None:
        return f"{entry_id}~{kind}"
    _validate_positive_int(revision, "revision")
    return f"{entry_id}~{kind}~{revision}"


def parse_entry_id(value: str) -> tuple[str, str, int] | None:
    """Parse a recommended entry identifier.

    :param value: Entry identifier to parse.
    :return: The ``(base, series, number)`` parts, or ``None`` if invalid.
    """
    match = ENTRY_ID_PATTERN.fullmatch(value)
    if match is None:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def parse_immutable_id(value: str) -> tuple[str, int] | None:
    """Parse an immutable identifier with a recommended embedded entry id.

    :param value: Immutable identifier to parse.
    :return: The ``(entry_id, revision)`` parts, or ``None`` if invalid.
    """
    match = IMMUTABLE_ID_PATTERN.fullmatch(value)
    if match is None or ENTRY_ID_PATTERN.fullmatch(match.group(1)) is None:
        return None
    return match.group(1), int(match.group(2))


def parse_alternative_id(value: str) -> tuple[str, str, int | None] | None:
    """Parse an alternative identifier with a recommended embedded entry id.

    :param value: Alternative identifier to parse.
    :return: The ``(entry_id, kind, revision)`` parts (``revision`` ``None`` when absent), or ``None`` if invalid.
    """
    match = ALTERNATIVE_ID_PATTERN.fullmatch(value)
    if match is None or ENTRY_ID_PATTERN.fullmatch(match.group(1)) is None:
        return None
    revision = match.group(3)
    return match.group(1), match.group(2), None if revision is None else int(revision)


def is_url_safe_id(value: str) -> bool:
    """Return whether an identifier is safe for use in a URL path segment.

    :param value: Identifier to inspect.
    :return: ``True`` if the value is non-empty printable ASCII without ``/``.
    """
    return bool(value) and "/" not in value and all(33 <= ord(character) <= 126 for character in value)


def check_entry_id(value: str) -> str:
    """Check an entry identifier, warning for recommended-syntax deviations.

    :param value: Entry identifier to check.
    :return: The unchanged identifier.
    :raises ValueError: If the identifier is not URL-safe.
    """
    _check_url_safety(value, "entry")
    if parse_entry_id(value) is None:
        logging.getLogger(__name__).warning(
            "Entry id %r does not match the recommended syntax %s.",
            value,
            _ENTRY_ID_SYNTAX,
            extra={"context": "store"},
        )
    return value


def check_immutable_id(value: str) -> str:
    """Check an immutable identifier, warning for recommended-syntax deviations.

    :param value: Immutable identifier to check.
    :return: The unchanged identifier.
    :raises ValueError: If the identifier is not URL-safe.
    """
    _check_url_safety(value, "immutable")
    if parse_immutable_id(value) is None and parse_alternative_id(value) is None:
        logging.getLogger(__name__).warning(
            "Immutable id %r does not match the recommended syntax %s or %s.",
            value,
            _IMMUTABLE_ID_SYNTAX,
            _ALTERNATIVE_ID_SYNTAX,
            extra={"context": "store"},
        )
    return value


def _check_url_safety(value: str, kind: str) -> None:
    if not is_url_safe_id(value):
        raise ValueError(f"Invalid {kind} id {value!r}; it must be URL-safe (non-empty printable ASCII without '/').")


def _validate_positive_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be a non-boolean int; got {value!r}.")
    if value < 1:
        raise ValueError(f"Invalid {name} {value!r}; it must be a positive integer.")
