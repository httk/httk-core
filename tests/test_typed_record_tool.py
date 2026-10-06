"""Tests for the typed-record generator's docstring conversion."""

import pytest

from httk.core._typed_record_tool import _doc_lines


@pytest.mark.parametrize(
    ("description", "expected"),
    (
        ("a vector over `dim_spatial` here", "a vector over ``dim_spatial`` here"),
        ("already ``literal`` stays", "already ``literal`` stays"),
        ("a :func:`role` stays", "a :func:`role` stays"),
        ("`a` and `b`", "``a`` and ``b``"),
        ("an unbalanced ` backtick", "an unbalanced ` backtick"),
        ("**bold** is valid RST", "**bold** is valid RST"),
    ),
)
def test_doc_lines_converts_markdown_code_spans(description: str, expected: str) -> None:
    assert _doc_lines(description) == [expected]


def test_doc_lines_spans_do_not_cross_lines() -> None:
    assert _doc_lines("open `here\nclosed` there") == ["open `here", "closed` there"]
