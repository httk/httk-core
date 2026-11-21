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
# Core registers the per-user setup, identity, plugin, project and convert
# commands, grouped into root-help sections, plus hidden maintenance commands
# (docs, registry, memguard). Handlers are lazy "module:callable" references, so
# root help resolves nothing and a command imports argparse only when it runs.
from httk.core import register_cli_command

register_cli_command(
    "setup",
    "httk.core.identity_cli:setup_command",
    "set up httk for this user (establishes the default operator identity)",
    section="Setup",
)
register_cli_command(
    "identity",
    "httk.core.identity_cli:identity_command",
    "manage named operator identities",
    section="Setup",
)
register_cli_command("plugin", "httk.core.plugins.cli:command", "install and manage httk plugins", section="Setup")
register_cli_command(
    "project",
    "httk.core.project.cli:command",
    "initialize and inspect httk projects",
    section="Organize",
)
register_cli_command(
    "convert",
    "httk.core.converting:command",
    "convert a loadable file into a saveable format",
    section="Data",
)
register_cli_command(
    "docs",
    "httk.core.docs.cli:command",
    "maintain versioned httk documentation sites",
    hidden=True,
)
register_cli_command(
    "registry",
    "httk.core._registry_tool:command",
    "generate and verify entry record classes from schemas",
    hidden=True,
)
register_cli_command("memguard", "httk.core.memguard:command", "run a command under a memory guard", hidden=True)
