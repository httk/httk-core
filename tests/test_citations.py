"""Tests for import-tracked citation credits."""

import pytest

import httk.core
from httk.core.citations import _citations


@pytest.fixture(autouse=True)
def restore_citations():
    original = {heading: list(references) for heading, references in _citations.items()}
    yield
    _citations.clear()
    _citations.update({heading: list(references) for heading, references in original.items()})


def test_httk_reference_is_registered() -> None:
    entries = httk.core.credits.entries()
    reference = entries["httk, the high-throughput toolkit"][0]
    assert reference.doi == "10.1007/978-3-030-40245-7_17"


def test_credits_render_the_httk_reference() -> None:
    rendered = str(httk.core.credits)
    assert "httk, the high-throughput toolkit:" in rendered
    assert "Rickard Armiento" in rendered
    assert "https://doi.org/10.1007/978-3-030-40245-7_17" in rendered


def test_registration_merges_idempotently_and_appends_new_references() -> None:
    heading = "citation test"
    reference = {"title": "First"}
    httk.core.register_citation(applies_to=heading, references=reference)
    httk.core.register_citation(applies_to=heading, references=reference)
    assert len(httk.core.credits.entries()[heading]) == 1

    httk.core.register_citation(applies_to=heading, references={"title": "Second"})
    assert [ref.title for ref in httk.core.credits.entries()[heading]] == ["First", "Second"]


def test_authors_are_canonicalized_for_idempotence() -> None:
    heading = "author canonicalization"
    httk.core.register_citation(applies_to=heading, references={"authors": [{"name": "Author"}]})
    httk.core.register_citation(applies_to=heading, references={"authors": ({"name": "Author"},)})
    assert len(httk.core.credits.entries()[heading]) == 1


def test_author_mappings_are_copied_during_registration() -> None:
    author = {"name": "Original"}
    httk.core.register_citation(applies_to="author copy", references={"authors": [author]})
    author["name"] = "Changed"
    assert httk.core.credits.entries()["author copy"][0].authors[0]["name"] == "Original"


def test_number_and_note_are_rendered() -> None:
    httk.core.register_citation(
        applies_to="number and note",
        references={"title": "Title", "volume": "3", "number": "3", "note": "Version 0.1.0, CC BY 4.0"},
    )
    rendered = str(httk.core.credits)
    assert "no. 3" in rendered
    assert "Version 0.1.0, CC BY 4.0" in rendered


def test_empty_references_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        httk.core.register_citation(applies_to="empty references", references=[])


def test_registration_delegates_mapping_validation_to_reference() -> None:
    with pytest.raises(ValueError, match="Unknown field"):
        httk.core.register_citation(applies_to="citation test", references={"unknown": "value"})


def test_registration_validates_references_and_heading() -> None:
    with pytest.raises(TypeError):
        httk.core.register_citation(applies_to="citation test", references="a string")
    with pytest.raises(ValueError):
        httk.core.register_citation(applies_to="", references={"title": "Title"})
    with pytest.raises(ValueError):
        httk.core.register_citation(applies_to=" padded ", references={"title": "Title"})


def test_entries_is_a_snapshot() -> None:
    entries = httk.core.credits.entries()
    entries.clear()
    assert "httk, the high-throughput toolkit" in httk.core.credits.entries()
