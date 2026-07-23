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

An :class:`EntryProvider` supplies queryable *entry types* — named tables of
records with described columns — to consumers that expose them, for example an
OPTIMADE server. The contract is deliberately domain-neutral: nothing here is
specific to materials science (or to OPTIMADE). A materials module such as
``httk.atomistic`` implements a provider that serves its ``structures`` from
this contract, and a serving module such as ``httk.optimade`` consumes any
provider without depending on the domain module.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any


class EntryProvider(ABC):
    """Supplies described, queryable entry types as plain JSON-able records.

    A provider serves one or more *entry types*, each identified by a name (e.g.
    ``"structures"``). For every entry type it describes the entry type and its
    properties, states how each served property maps to a record column, and
    yields the records themselves.

    Three notions define the contract:

    - **Descriptions** (:meth:`entry_types`) are plain dictionaries in the
      OPTIMADE property-definition dialect — the schema language shared across
      httk₂ modules. Each entry type maps to a dictionary with a ``description``
      string and a ``properties`` mapping of property name to a property-info
      dictionary (carrying at least ``description`` and a ``fulltype`` such as
      ``"string"``, ``"integer"``, ``"float"``, or ``"list of string"``).
      Producing these needs no imports: the dictionaries are structurally
      compatible with a consumer's typed schema but are stated in neutral terms.
    - **Columns** (:meth:`columns`) map each served property name to the key
      under which that property's value is found in a record. Every entry type's
      column map MUST cover at least ``id`` and ``type``.
    - **Records** (:meth:`records`) are plain JSON-able mappings keyed by the
      column keys named in :meth:`columns` (values are strings, numbers,
      booleans, ``None``, or nested lists/dicts of the same).

    A consumer combines the three: the descriptions become the served schema,
    the columns drive both response-field extraction and filter handling, and
    the records are loaded into a store the consumer queries.
    """

    @abstractmethod
    def entry_types(self) -> Mapping[str, dict[str, Any]]:
        """Return the served entry types keyed by name.

        Each value is a description dictionary in the OPTIMADE
        property-definition dialect: ``{"description": <str>, "properties":
        {<property name>: <property-info dict>}}``. The property-info dictionary
        for each property carries at least a ``description`` and a ``fulltype``.
        """
        raise NotImplementedError

    @abstractmethod
    def columns(self, entry_type: str) -> Mapping[str, str]:
        """Return the served-property-name to record-column-key map for ``entry_type``.

        The mapping MUST include entries for at least ``id`` and ``type``. Every
        key names a property described by :meth:`entry_types`; every value names
        the key under which that property's value is found in a record from
        :meth:`records`.
        """
        raise NotImplementedError

    @abstractmethod
    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        """Yield the records for ``entry_type`` as plain JSON-able mappings.

        Each record is a mapping keyed by the record-column keys named in
        :meth:`columns`; values are JSON-able (strings, numbers, booleans,
        ``None``, or nested lists/dicts of the same).
        """
        raise NotImplementedError
