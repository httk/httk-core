"""Private helpers for minimally validating absolute IRIs."""

from urllib.parse import urlsplit

_FORBIDDEN_IRI_ASCII = frozenset(' <>"{}|\\^`')
_HEXDIGITS = frozenset("0123456789abcdefABCDEF")


def is_absolute_iri(value: str) -> bool:
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
