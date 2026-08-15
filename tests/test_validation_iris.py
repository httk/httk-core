"""Tests for the public IRI and URL syntax validation predicates."""

import pytest

from httk.core import _iris
from httk.core.validation.iris import (
    has_valid_percent_escapes,
    is_absolute_iri,
    is_https_url,
    is_root_relative_url,
)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/datasets/alpha",
        "urn:uuid:550e8400-e29b-41d4-a716-446655440000",
        "https://example.org/a%2Fb",
    ],
)
def test_is_absolute_iri_accepts_well_formed_values(value: str) -> None:
    assert is_absolute_iri(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/datasets/alpha",
        "not an iri",
        "https://example.org/space here",
        "https://example.org/\x01",
        "https://example.org/\x85",
        "https://example.org/\ud800",
        "https://example.org/a<b",
        "https://example.org/a>b",
        'https://example.org/a"b',
        "https://example.org/a{b",
        "https://example.org/a}b",
        "https://example.org/a|b",
        "https://example.org/a\\b",
        "https://example.org/a^b",
        "https://example.org/a`b",
        "https://example.org/%",
        "https://example.org/%A",
        "https://example.org/%ZZ",
        "https://example.org/path%",
    ],
)
def test_is_absolute_iri_rejects_malformed_values(value: str) -> None:
    assert is_absolute_iri(value) is False


@pytest.mark.parametrize(
    "value",
    [
        "/",
        "/datasets/alpha",
        "/a%2Fb",
    ],
)
def test_is_root_relative_url_accepts_root_relative_paths(value: str) -> None:
    assert is_root_relative_url(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "datasets/alpha",
        "//example.org/alpha",
        "https://example.org/alpha",
        "/path#fragment",
        "/space here",
        "/bad%ZZ",
    ],
)
def test_is_root_relative_url_rejects_other_values(value: str) -> None:
    assert is_root_relative_url(value) is False


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/path",
        "https://example.org:8443/path",
        "https://example.org",
    ],
)
def test_is_https_url_accepts_valid_urls(value: str) -> None:
    assert is_https_url(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "http://example.org/path",
        "https://user:pass@example.org/path",
        "https://user@example.org/path",
        "https://example.org/path#fragment",
        "https://example.org:0/path",
        "https://example.org:65536/path",
        "https://example.org:notaport/path",
        "https:///path",
    ],
)
def test_is_https_url_rejects_invalid_urls(value: str) -> None:
    assert is_https_url(value) is False


def test_is_https_url_query_is_gated_by_allow_query() -> None:
    assert is_https_url("https://a.example/x?y=1") is False
    assert is_https_url("https://a.example/x?y=1", allow_query=True) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "no percent here",
        "%20",
        "%2F",
        "%aB",
        "a%20b%2Fc",
    ],
)
def test_has_valid_percent_escapes_accepts_valid_escapes(value: str) -> None:
    assert has_valid_percent_escapes(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "%",
        "%A",
        "%ZZ",
        "path%",
        "path%A",
        "a%20b%",
    ],
)
def test_has_valid_percent_escapes_rejects_malformed_escapes(value: str) -> None:
    assert has_valid_percent_escapes(value) is False


def test_private_iris_alias_is_the_public_object() -> None:
    assert _iris.is_absolute_iri is is_absolute_iri
