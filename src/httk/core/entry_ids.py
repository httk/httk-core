"""Format, parse, and validate human-readable httk entry identifiers."""

import logging
import re

__all__ = [
    "ENTRY_ID_PATTERN",
    "IMMUTABLE_ID_PATTERN",
    "check_entry_id",
    "check_immutable_id",
    "format_entry_id",
    "format_immutable_id",
    "is_url_safe_id",
    "parse_entry_id",
    "parse_immutable_id",
]

ENTRY_ID_PATTERN = re.compile(r"^([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)-([A-Za-z0-9_]+)-([1-9][0-9]*)$")
_ENTRY_ID_BODY = re.sub(r"\((?!\?)", "(?:", ENTRY_ID_PATTERN.pattern[1:-1])
IMMUTABLE_ID_PATTERN = re.compile(rf"^({_ENTRY_ID_BODY})~([1-9][0-9]*)$")

_ENTRY_ID_SYNTAX = "<base>-<series>-<number>"
_IMMUTABLE_ID_SYNTAX = "<base>-<series>-<number>~<revision>"


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
    if parse_immutable_id(value) is None:
        logging.getLogger(__name__).warning(
            "Immutable id %r does not match the recommended syntax %s.",
            value,
            _IMMUTABLE_ID_SYNTAX,
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
