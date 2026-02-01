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

import importlib, importlib.util, pkgutil

_DONE = False

def _discover_register_modules() -> None:
    global _DONE, subpackages
    if _DONE:
        return
    _DONE = True

    import httk  # safe: we're inside httk import, but httk.__path__ is already extended above

    found: list[str] = []
    prefix = "httk."

    for m in pkgutil.iter_modules(httk.__path__, prefix):
        if not m.ispkg:
            continue

        found.append(m.name)

        reg_name = m.name + "._register"  # e.g. httk.io._register
        if importlib.util.find_spec(reg_name) is not None:
            importlib.import_module(reg_name)

    return tuple(sorted(set(found)))
