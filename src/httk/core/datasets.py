"""Neutral dataset identity and publication metadata contract."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import urlsplit

_FIELD_NAMES = frozenset({"id", "title", "description", "publisher_id", "publisher_name"})
_FORBIDDEN_IRI_ASCII = frozenset(' <>"{}|\\^`')
_HEXDIGITS = frozenset("0123456789abcdefABCDEF")


def _is_absolute_iri(value: str) -> bool:
    """Return whether *value* is a minimally well-formed absolute IRI."""

    for index, character in enumerate(value):
        codepoint = ord(character)
        if (
            character.isspace()
            or codepoint < 32
            or 0x7F <= codepoint <= 0x9F
            or 0xD800 <= codepoint <= 0xDFFF
            or (codepoint < 128 and character in _FORBIDDEN_IRI_ASCII)
        ):
            return False
        if character == "%" and (
            index + 2 >= len(value) or value[index + 1] not in _HEXDIGITS or value[index + 2] not in _HEXDIGITS
        ):
            return False
    try:
        return bool(urlsplit(value).scheme)
    except ValueError:
        return False


@dataclass(frozen=True)
class Dataset:
    """Describe one published dataset independently of a transport or provider.

    ``id`` and ``publisher_id`` are absolute IRIs.  The remaining fields are
    human-readable metadata and retain their supplied text exactly.

    :param id: The dataset's absolute IRI.
    :param title: The dataset's human-readable title.
    :param description: A non-empty description of the dataset.
    :param publisher_id: The publisher's absolute IRI.
    :param publisher_name: The publisher's human-readable name.
    """

    id: str
    title: str
    description: str
    publisher_id: str
    publisher_name: str

    def __post_init__(self) -> None:
        for field_name in _FIELD_NAMES:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Field '{field_name}' must be a string containing non-whitespace text.")
        for field_name in ("id", "publisher_id"):
            if not _is_absolute_iri(getattr(self, field_name)):
                raise ValueError(f"Field '{field_name}' must be a well-formed absolute IRI.")

    @classmethod
    def create(cls, obj: "Dataset | Mapping[str, Any]") -> Self:
        """Coerce a mapping or existing dataset into a :class:`Dataset`.

        :param obj: A dataset instance or a mapping with exactly the dataset fields.
        :return: The existing or newly constructed dataset.
        :raises TypeError: If ``obj`` is neither a dataset nor a mapping.
        :raises ValueError: If the mapping has missing, unknown, or invalid fields.
        """

        if isinstance(obj, cls):
            return obj
        if not isinstance(obj, Mapping):
            raise TypeError(f"Expected a {cls.__name__} or a mapping, got {type(obj).__name__}.")
        missing = _FIELD_NAMES.difference(obj)
        if missing:
            raise ValueError(f"Missing required field(s) for {cls.__name__}: {', '.join(sorted(missing))}.")
        unknown = [key for key in obj if key not in _FIELD_NAMES]
        if unknown:
            raise ValueError(f"Unknown field(s) for {cls.__name__}: {', '.join(sorted(repr(key) for key in unknown))}.")
        return cls(**dict(obj))


__all__ = ["Dataset"]
