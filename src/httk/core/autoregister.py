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

import importlib
import importlib.util
import pkgutil

_DONE = False


def autoregister() -> None:
    global _DONE
    if _DONE:
        return
    _DONE = True

    import httk  # ensures httk.__path__ is set

    prefix = httk.__name__ + "."
    for m in pkgutil.iter_modules(httk.__path__, prefix):
        if not m.ispkg:
            continue
        reg_name = m.name + "._register"  # e.g. httk.io._register
        if importlib.util.find_spec(reg_name) is None:
            continue
        importlib.import_module(reg_name)
