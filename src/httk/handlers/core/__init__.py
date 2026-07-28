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

# httk-core ships no concrete EntryProvider: it defines the neutral contract and
# its registry, plus the stdlib-only record models, and domain modules (e.g.
# httk-data, httk-atomistic) provide their own httk.handlers.* package that
# self-registers providers during httk.core discovery.
#
# The one command core registers itself is the umbrella `httk project`: the
# project anchor lives in httk.core.project, so its command line is a built-in of a
# core installation. The handler is a lazy "module:callable" reference, so root
# help resolves nothing and `httk project` imports argparse only when it runs.
from httk.core import register_cli_command

register_cli_command(
    "project",
    "httk.core.project.cli:command",
    "initialize and inspect httk projects",
)
