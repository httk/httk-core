"""Predicates for minimally validating IRI and URL syntax.

These predicates check only surface syntax; they neither resolve references nor
verify that a target exists.  Callers raise their own domain-specific errors
based on the boolean result.
"""

from urllib.parse import urlsplit

_FORBIDDEN_IRI_ASCII = frozenset(' <>"{}|\\^`')
_HEXDIGITS = frozenset("0123456789abcdefABCDEF")


def has_valid_percent_escapes(value: str) -> bool:
    """Return whether every ``%`` in *value* introduces a valid percent-escape.

    Each ``%`` must be followed by exactly two hexadecimal digits, including
    when the ``%`` sits at the end of the string, where the missing followers
    make the escape invalid.

    :param value: The candidate string.
    :return: ``True`` if every ``%`` in *value* is followed by two hex digits.
    """

    for index, character in enumerate(value):
        if character == "%" and (
            index + 2 >= len(value) or value[index + 1] not in _HEXDIGITS or value[index + 2] not in _HEXDIGITS
        ):
            return False
    return True


def is_absolute_iri(value: str) -> bool:
    """Return whether *value* is a minimally well-formed absolute IRI.

    The check rejects whitespace, control characters, the C1 range, lone
    surrogates, the ASCII set ``<>"{}|\\^```, and malformed percent-escapes,
    then requires a non-empty URL scheme.

    :param value: The candidate IRI string.
    :return: ``True`` if *value* is a minimally well-formed absolute IRI.
    """

    for character in value:
        codepoint = ord(character)
        if (
            character.isspace()
            or codepoint < 32
            or 0x7F <= codepoint <= 0x9F
            or 0xD800 <= codepoint <= 0xDFFF
            or (codepoint < 128 and character in _FORBIDDEN_IRI_ASCII)
        ):
            return False
    if not has_valid_percent_escapes(value):
        return False
    try:
        return bool(urlsplit(value).scheme)
    except ValueError:
        return False


def is_root_relative_url(value: str) -> bool:
    """Return whether *value* is a minimally well-formed root-relative URL.

    A root-relative URL begins with a single ``/``, carries no scheme, network
    location, or fragment, and its path component is valid IRI syntax.

    :param value: The candidate URL string.
    :return: ``True`` if *value* is a minimally well-formed root-relative URL.
    """

    if not value.startswith("/") or value.startswith("//"):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        not parsed.scheme
        and not parsed.netloc
        and not parsed.fragment
        and is_absolute_iri(f"https://example.invalid{value}")
    )


def is_https_url(value: str, *, allow_query: bool = False) -> bool:
    """Return whether *value* is a minimally well-formed absolute HTTPS URL.

    The value must be a well-formed absolute IRI whose scheme is exactly
    ``https``, with a non-empty host, no userinfo, and no fragment; any explicit
    port must lie in ``1..65535``.  A non-empty query is rejected unless
    *allow_query* is ``True``.

    :param value: The candidate URL string.
    :param allow_query: Whether a non-empty query component is permitted.
    :return: ``True`` if *value* is a minimally well-formed absolute HTTPS URL.
    """

    if not is_absolute_iri(value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and (allow_query or not parsed.query)
        and (port is None or 1 <= port <= 65_535)
    )
