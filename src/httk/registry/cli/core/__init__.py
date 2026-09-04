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
# httk-store, httk-atomistic) provide their own httk.registry.* package that
# self-registers providers during httk.core discovery.
#
# The two commands core registers are the umbrella `httk project` and versioned
# documentation maintenance. The project anchor lives in httk.core.project, so
# its command line is a built-in of a
# core installation. The handler is a lazy "module:callable" reference, so root
# help resolves nothing and `httk project` imports argparse only when it runs.
from httk.core import register_cli_command

register_cli_command(
    "project",
    "httk.core.project.cli:command",
    "initialize and inspect httk projects",
)
register_cli_command("plugin", "httk.core.plugins.cli:command", "install and manage httk plugins")
register_cli_command(
    "docs",
    "httk.core.docs.cli:command",
    "maintain versioned httk documentation sites",
)
register_cli_command(
    "registry",
    "httk.core._registry_tool:command",
    "generate and verify entry record classes from schemas",
)
register_cli_command("memguard", "httk.core.memguard:command", "run a command under a memory guard")
register_cli_command("convert", "httk.core.converting:command", "convert a loadable file into a saveable format")
register_cli_command("system", "httk.core.system:command", "reset per-user httk state")
register_cli_command(
    "init",
    "httk.core.identity_cli:init_command",
    "set up httk for this user (establishes the default operator identity)",
)
register_cli_command(
    "identity",
    "httk.core.identity_cli:identity_command",
    "manage named operator identities",
)
