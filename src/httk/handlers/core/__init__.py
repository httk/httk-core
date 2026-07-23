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

"""Self-registration of httk-core's standard OPTIMADE entry providers.

Imported during ``httk.core`` discovery, this package registers the providers
for the standard entry types httk-core vendors (``references``, ``files``,
``calculations``) as lazy factory references, mirroring the loader-registration
pattern used by the other ``httk.handlers.*`` packages.
"""

from httk.core.register import register_entry_provider

register_entry_provider(name="core-references", factory="httk.core.entry_types:ReferenceEntryProvider")
register_entry_provider(name="core-files", factory="httk.core.entry_types:FileEntryProvider")
register_entry_provider(name="core-calculations", factory="httk.core.entry_types:CalculationEntryProvider")
