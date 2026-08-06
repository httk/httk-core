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

"""The neutral entry-provider contract shared across httk₂ modules.

An :class:`EntryProvider` supplies queryable *entry types* — named collections
of records with described properties — to consumers that expose them, for
example an OPTIMADE server. The contract is deliberately domain-neutral: nothing here is
specific to materials science (or to OPTIMADE). A materials module such as
``httk.atomistic`` implements a provider that serves its ``structures`` from
this contract, and a serving module such as ``httk.serve.optimade`` consumes any
provider without depending on the domain module.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .property_definitions import EntryTypeDefinition


@dataclass(frozen=True, slots=True)
class RelatedEntry:
    """One related entry of a record, as reported by :meth:`EntryProvider.relationships`.

    Mirrors the OPTIMADE v1.3 relationships model: a related entry is named by
    its entry type and id, optionally carrying the per-identifier metadata the
    standard defines — ``description`` (the human-readable relationship
    description introduced in OPTIMADE v1.2 as ``meta.description``) and
    ``role`` (the machine-readable relationship role introduced in OPTIMADE
    v1.3 as ``meta.role``, e.g. ``"input"``/``"output"`` for the
    calculations↔files relationship). An absent ``role`` means exactly that —
    no role is declared and no default is assumed. ``label`` is the provenance
    edge label (the OPTIMADE relation-object ``label``); until relation-object
    serving exists, it is served on the OPTIMADE side as prefixed relationship
    metadata.
    """

    entry_type: str
    """The entry type of the related entry (e.g. ``"references"``)."""

    id: str
    """The id of the related entry."""

    description: str | None = None
    """A human-readable description of the relationship, if declared."""

    role: str | None = None
    """The machine-readable role of the relationship, if declared."""

    label: str | None = None
    """The provenance edge label, if declared."""


class EntryProvider(ABC):
    """Supplies described, queryable entry types as plain JSON-able records.

    A provider serves one or more *entry types*, each identified by a name (e.g.
    ``"structures"``). For every entry type it describes the entry type and its
    properties, states how each served property maps to a record key, and
    yields the records themselves.

    Three notions define the contract:

    - **Definitions** (:meth:`entry_types`) are first-class
      :class:`~httk.core.property_definitions.EntryTypeDefinition` objects — the
      OPTIMADE property-definition model shared across httk₂ modules. A provider
      obtains them from the vendored standards (via
      :func:`~httk.core.property_definitions.standard_entry_type` or
      :func:`~httk.core.register.load_entry_type_definition`) or
      builds them from
      :meth:`~httk.core.property_definitions.EntryTypeDefinition.from_optimade`
      and :meth:`~httk.core.property_definitions.PropertyDefinition.from_simple`.
      A standard definition typically describes more properties than a provider
      serves; the served subset is exactly the property names in
      :meth:`property_keys`.
    - **Property keys** (:meth:`property_keys`) map each served property name to
      the key under which that property's value is found in a record. Every entry
      type's property-key map MUST cover at least ``id`` and ``type``, and every
      served name MUST be described by the entry type's definition (custom
      properties must therefore live in an
      :meth:`~httk.core.property_definitions.EntryTypeDefinition.extended`
      definition).
    - **Records** (:meth:`records`) are plain JSON-able mappings keyed by the
      record keys named in :meth:`property_keys` (values are strings, numbers,
      booleans, ``None``, or nested lists/dicts of the same).

    A consumer combines the three: the definitions become the served schema, the
    property keys drive both response-field extraction and filter handling, and
    the records are loaded into a store the consumer queries.

    A provider may additionally declare **relationships**
    (:meth:`relationships`): a flat tuple of :class:`~httk.core.RelatedEntry` values per
    entry id, each naming a related entry (and optionally the relationship's
    ``description``/``role`` metadata) that the consumer serves as the entry's
    relationships block.
    """

    @abstractmethod
    def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
        """Return the served entry types keyed by name.

        Each value is an
        :class:`~httk.core.property_definitions.EntryTypeDefinition` describing
        the entry type and its properties. The subset a provider actually serves
        is named by :meth:`property_keys`; a definition may describe more
        properties than are served.
        """
        raise NotImplementedError

    @abstractmethod
    def property_keys(self, entry_type: str) -> Mapping[str, str]:
        """Return the served-property-name to record-key map for ``entry_type``.

        The mapping MUST include entries for at least ``id`` and ``type``. Every
        key names a property described by :meth:`entry_types`; every value names
        the key under which that property's value is found in a record from
        :meth:`records`.
        """
        raise NotImplementedError

    @abstractmethod
    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        """Yield the records for ``entry_type`` as plain JSON-able mappings.

        Each record is a mapping keyed by the record keys named in
        :meth:`property_keys`; values are JSON-able (strings, numbers, booleans,
        ``None``, or nested lists/dicts of the same).
        """
        raise NotImplementedError

    def relationships(self, entry_type: str) -> Mapping[str, tuple[RelatedEntry, ...]]:
        """Return the related entries for each record of ``entry_type``.

        The result maps an entry id to a flat tuple of :class:`~httk.core.RelatedEntry`
        values, e.g. ``{"struct-1": (RelatedEntry("references", "ref-1"),
        RelatedEntry("references", "ref-2", description="Cites the method"))}``.
        Grouping the related entries by related entry type is the serving
        layer's concern (JSON:API groups them at render time). This is the
        neutral source of an OPTIMADE **relationships** block: a consumer turns
        each related entry into a resource identifier under its entry type
        (carrying the ``description``/``role`` metadata when present), and an
        ``include=<type>`` request then embeds those related resources. The
        default implementation returns an empty mapping (no relationships); a
        provider overrides it to declare them. Ids referring to records this
        provider (or a sibling provider serving the related type) does not supply
        are simply not resolvable by the consumer.
        """
        return {}
