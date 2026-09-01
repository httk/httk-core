"""Tests for human-readable httk entry identifiers."""

import logging

import pytest

from httk.core import (
    ALTERNATIVE_ID_PATTERN,
    ALTERNATIVE_KIND_PATTERN,
    ENTRY_ID_PATTERN,
    IMMUTABLE_ID_PATTERN,
    check_entry_id,
    check_immutable_id,
    format_alternative_id,
    format_entry_id,
    format_immutable_id,
    is_url_safe_id,
    parse_alternative_id,
    parse_entry_id,
    parse_immutable_id,
)


def test_entry_id_round_trip() -> None:
    value = format_entry_id("httk.mydb.structures", "1", 42)
    assert value == "httk.mydb.structures-1-42"
    assert parse_entry_id(value) == ("httk.mydb.structures", "1", 42)


def test_immutable_id_round_trip() -> None:
    entry_id = format_entry_id("httk.mydb.structures", "1", 42)
    value = format_immutable_id(entry_id, 3)
    assert value == "httk.mydb.structures-1-42~3"
    assert parse_immutable_id(value) == (entry_id, 3)


@pytest.mark.parametrize(
    ("base", "series", "number"),
    [
        ("", "1", 1),
        ("httk.", "1", 1),
        ("httk..mydb", "1", 1),
        ("httk", "", 1),
        ("httk", "1.2", 1),
        ("httk", "1~2", 1),
        ("httk", "1:2", 1),
        ("httk", "1", 0),
        ("httk", "1", -1),
    ],
)
def test_format_entry_id_rejects_invalid_parts(base: str, series: str, number: int) -> None:
    with pytest.raises(ValueError):
        format_entry_id(base, series, number)


@pytest.mark.parametrize("number", [1.5, True, "1"])
def test_format_entry_id_requires_non_boolean_int(number: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        format_entry_id("httk.mydb", "1", number)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        "httk.mydb-1-042",
        "httk.mydb-1-0",
        "httk.mydb-1-1~01",
        "httk.mydb-1-1~0",
        "httk.mydb-1-1~0x",
        "httk.mydb-1-1~3~4",
        "httk.mydb-1.2-1",
        "httk..mydb-1-1~3",
    ],
)
def test_parse_rejects_invalid_ids(value: str) -> None:
    assert parse_entry_id(value) is None
    assert parse_immutable_id(value) is None
    assert parse_alternative_id(value) is None


def test_parse_entry_id_returns_none_for_non_entry_id() -> None:
    assert parse_entry_id("not-an-entry-id") is None


def test_parse_immutable_id_returns_none_for_non_immutable_id() -> None:
    assert parse_immutable_id("anyt:am-1-12~3") is None


@pytest.mark.parametrize("value", ["", "a/b", "a\nb", "é-1-1"])
def test_url_safety_rejects_empty_slash_control_and_non_ascii(value: str) -> None:
    assert not is_url_safe_id(value)


def test_format_immutable_id_accepts_url_safe_nonconforming_entry_id() -> None:
    assert format_immutable_id("anyt:am-1-12", 3) == "anyt:am-1-12~3"
    with pytest.raises(ValueError):
        format_immutable_id("a/b", 1)
    with pytest.raises(ValueError):
        format_immutable_id("a-1-1", 0)


@pytest.mark.parametrize("revision", [1.5, True, "1"])
def test_format_immutable_id_requires_non_boolean_int(revision: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        format_immutable_id("httk.mydb-1-1", revision)  # type: ignore[arg-type]


def test_immutable_pattern_rejects_nonconforming_entry_id() -> None:
    assert IMMUTABLE_ID_PATTERN.fullmatch("anyt:am-1-12~3") is None
    assert IMMUTABLE_ID_PATTERN.fullmatch("httk.mydb-1-12~3")


def test_check_entry_id_rejects_url_unsafe() -> None:
    with pytest.raises(ValueError, match="a/b.*URL-safe"):
        check_entry_id("a/b")


def test_check_immutable_id_rejects_url_unsafe() -> None:
    with pytest.raises(ValueError, match="a/b~1.*URL-safe"):
        check_immutable_id("a/b~1")


def test_check_entry_id_warns_for_url_safe_nonconforming_id(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="httk.core.entry_ids")
    value = "anyt:am-1-12"

    assert check_entry_id(value) == value
    assert len(caplog.records) == 1
    assert caplog.records[0].context == "store"
    assert "anyt:am-1-12" in caplog.records[0].message
    assert "<base>-<series>-<number>" in caplog.records[0].message


def test_check_immutable_id_warns_for_url_safe_nonconforming_id(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="httk.core.entry_ids")
    value = "anyt:am-1-12~3"

    assert check_immutable_id(value) == value
    assert len(caplog.records) == 1
    assert caplog.records[0].context == "store"


def test_checks_do_not_warn_for_conforming_ids(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="httk.core.entry_ids")
    entry_id = "httk.mydb-1-12"
    immutable_id = "httk.mydb-1-12~3"

    assert check_entry_id(entry_id) == entry_id
    assert check_immutable_id(immutable_id) == immutable_id
    assert caplog.records == []


def test_alternative_id_round_trip() -> None:
    entry_id = format_entry_id("httk.mydb.structures", "1", 42)
    assert format_alternative_id(entry_id, "conventional") == "httk.mydb.structures-1-42~conventional"
    assert parse_alternative_id("httk.mydb.structures-1-42~conventional") == (entry_id, "conventional", None)
    assert format_alternative_id(entry_id, "conventional", 2) == "httk.mydb.structures-1-42~conventional~2"
    assert parse_alternative_id("httk.mydb.structures-1-42~conventional~2") == (entry_id, "conventional", 2)


@pytest.mark.parametrize(
    "value",
    [
        "httk.mydb-1-1~conventional",
        "httk.mydb-1-1~conventional~2",
        "httk.mydb-1-1~p_2",
    ],
)
def test_parse_alternative_id_accepts_well_formed(value: str) -> None:
    assert parse_alternative_id(value) is not None
    assert ALTERNATIVE_ID_PATTERN.fullmatch(value)


@pytest.mark.parametrize(
    "value",
    [
        "httk.mydb-1-1~Conventional",
        "httk.mydb-1-1~1conv",
        "httk.mydb-1-1~conventional~0",
        "httk.mydb-1-1~conventional~07",
        "httk.mydb-1-1~3~4",
        "httk..mydb-1-1~conventional",
    ],
)
def test_parse_alternative_id_rejects_malformed(value: str) -> None:
    assert parse_alternative_id(value) is None


def test_format_alternative_id_rejects_bad_kind_and_revision() -> None:
    with pytest.raises(ValueError, match="alternative kind"):
        format_alternative_id("httk.mydb-1-1", "Conventional")
    with pytest.raises(ValueError, match="alternative kind"):
        format_alternative_id("httk.mydb-1-1", "1conv")
    with pytest.raises(ValueError, match="URL-safe"):
        format_alternative_id("a/b", "conventional")
    with pytest.raises(ValueError):
        format_alternative_id("httk.mydb-1-1", "conventional", 0)


def test_format_alternative_id_accepts_url_safe_nonconforming_entry_id() -> None:
    assert format_alternative_id("anyt:am-1-12", "conventional") == "anyt:am-1-12~conventional"


def test_alternative_kind_pattern_is_exported() -> None:
    assert ALTERNATIVE_KIND_PATTERN.fullmatch("conventional")
    assert ALTERNATIVE_KIND_PATTERN.fullmatch("Conventional") is None


def test_check_immutable_id_does_not_warn_for_alternative_ids(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="httk.core.entry_ids")

    assert check_immutable_id("httk.mydb-1-12~conventional") == "httk.mydb-1-12~conventional"
    assert check_immutable_id("httk.mydb-1-12~conventional~2") == "httk.mydb-1-12~conventional~2"
    assert caplog.records == []


def test_patterns_are_exported() -> None:
    assert ENTRY_ID_PATTERN.fullmatch("httk.mydb-1-12")
    assert IMMUTABLE_ID_PATTERN.fullmatch("httk.mydb-1-12~3")
    assert ALTERNATIVE_ID_PATTERN.fullmatch("httk.mydb-1-12~conventional~3")
