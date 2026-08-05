#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Import-tracked citation credits for scientific dependencies.

Modules register :class:`~httk.core.Reference` records for what they scientifically rely
on. ``print(httk.core.credits)`` shows what the running program ought to cite
and why.
"""

import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import replace
from threading import Lock
from typing import Any

from .entry_types import Reference

_citations: dict[str, list[Reference]] = {}
_citations_lock = Lock()


def register_citation(
    *,
    applies_to: str,
    references: Reference | Mapping[str, Any] | Sequence[Reference | Mapping[str, Any]],
) -> None:
    """Register one or more references under a human-readable explanation."""
    if not isinstance(applies_to, str) or not applies_to.strip() or applies_to != applies_to.strip():
        raise ValueError("applies_to must be a nonempty string without surrounding whitespace")
    items: Sequence[Reference | Mapping[str, Any]]
    if isinstance(references, (Reference, Mapping)):
        items = (references,)
    elif isinstance(references, str):
        raise TypeError("references must be a Reference, mapping, or sequence of references")
    elif isinstance(references, Sequence):
        items = references
    else:
        raise TypeError("references must be a Reference, mapping, or sequence of references")

    normalized: list[Reference] = []
    for item in items:
        reference = Reference.create(item)
        if reference.authors is not None or reference.editors is not None:
            reference = replace(
                reference,
                authors=tuple(dict(author) for author in reference.authors) if reference.authors is not None else None,
                editors=tuple(dict(editor) for editor in reference.editors) if reference.editors is not None else None,
            )
        normalized.append(reference)
    if not normalized:
        raise ValueError("references must not be empty")

    with _citations_lock:
        registered = _citations.setdefault(applies_to, [])
        for reference in normalized:
            if reference not in registered:
                registered.append(reference)


def _format_reference(ref: Reference) -> str:
    parts: list[str] = []
    if ref.authors:
        parts.append(", ".join(author["name"] for author in ref.authors))
    if ref.title:
        parts.append(f'"{ref.title}"')
    if ref.journal:
        parts.append(ref.journal)
    elif ref.booktitle:
        booktitle = f"in {ref.booktitle}"
        if ref.editors:
            booktitle += ", eds. " + ", ".join(editor["name"] for editor in ref.editors)
        parts.append(booktitle)
    if ref.series:
        parts.append(ref.series)
    if ref.volume:
        parts.append(f"vol. {ref.volume}")
    if ref.number:
        parts.append(f"no. {ref.number}")
    if ref.pages:
        parts.append(f"pp. {ref.pages}")
    if ref.publisher:
        parts.append(ref.publisher)
    if ref.year:
        parts.append(f"({ref.year})")
    if ref.note:
        parts.append(ref.note)

    citation = ", ".join(parts)
    if ref.doi:
        citation += (". " if citation else "") + f"https://doi.org/{ref.doi}"
    elif ref.url:
        citation += (". " if citation else "") + ref.url
    return citation or ref.note or ""


class Credits:
    """The presentation object for registered citation credits."""

    def entries(self) -> dict[str, tuple[Reference, ...]]:
        """Return a snapshot of the registered citation entries."""
        with _citations_lock:
            return {heading: tuple(references) for heading, references in _citations.items()}

    def __str__(self) -> str:
        lines = ["This program used the high-throughput toolkit (httk). The authors ask you to cite:"]
        for heading, references in self.entries().items():
            lines.extend(("", f"{heading}:"))
            lines.extend(
                textwrap.fill(
                    _format_reference(reference),
                    width=78,
                    initial_indent="  ",
                    subsequent_indent="    ",
                )
                for reference in references
            )
        return "\n".join(lines)

    __repr__ = __str__


credits = Credits()

HTTK_REFERENCE: Reference = Reference.create(
    {
        "authors": ({"name": "Rickard Armiento", "firstname": "Rickard", "lastname": "Armiento"},),
        "title": "Database-driven High-Throughput Calculations and Machine Learning Models for Materials Design",
        "booktitle": "Machine Learning Meets Quantum Physics",
        "editors": (
            {"name": "Kristof T. Schütt"},
            {"name": "Stefan Chmiela"},
            {"name": "O. Anatole von Lilienfeld"},
            {"name": "Alexandre Tkatchenko"},
            {"name": "Koji Tsuda"},
            {"name": "Klaus-Robert Müller"},
        ),
        "series": "Lecture Notes in Physics",
        "volume": "968",
        "publisher": "Springer, Cham",
        "year": "2020",
        "doi": "10.1007/978-3-030-40245-7_17",
        "bib_type": "inbook",
    }
)

register_citation(applies_to="httk, the high-throughput toolkit", references=HTTK_REFERENCE)
