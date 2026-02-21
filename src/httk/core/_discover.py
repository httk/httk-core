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

def discover_and_register():
    import httk.handlers

    prefix = "httk.handlers."
    for m in pkgutil.iter_modules(httk.handlers.__path__, prefix):
        if not m.ispkg:
            continue

        spec = importlib.util.find_spec(m.name)
        if spec is None:
            continue

        mod = importlib.import_module(m.name)  # imports only that handler package chain
