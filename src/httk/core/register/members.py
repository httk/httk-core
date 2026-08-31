"""The project-member-kind registry: which module owns which member kind."""

#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation; either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
from collections.abc import Callable
from typing import Any

from ._base import PluginRegistry, resolve_callable

#: Registered member kinds, keyed by kind name. A registered handler is a lazy
#: ``"module:callable"`` reference (or a callable) that, when called with no
#: arguments, yields an object implementing
#: :class:`httk.core.project.members.ProjectMemberHandler`.
project_member_kinds = PluginRegistry()


def register_project_member_kind(kind: str, handler: str | Callable[..., Any]) -> None:
    """Register the handler that implements one project-member *kind*.

    A *handler* is either a callable or a lazy ``"module:callable"`` reference
    that takes no arguments and returns an object implementing
    :class:`~httk.core.project.members.ProjectMemberHandler`. Registering a kind
    is how an installed module teaches the core seal, manifest, and repair verbs
    to delegate that member's internals to it. This mirrors
    :func:`~httk.core.register.entries.register_entry_provider`.

    :param kind: The member kind name to register.
    :param handler: The handler callable or lazy ``"module:callable"`` reference.
    """

    project_member_kinds.register(key=kind, handler=handler, name=kind)


def known_project_member_kinds() -> list[str]:
    """Return the registered member-kind names.

    :return: Registered member-kind names in sorted order.
    """

    return project_member_kinds.keys()


def project_member_handler(kind: str) -> Any:
    """Return the handler object for one project-member *kind*.

    The registered reference is resolved lazily and called with no arguments to
    build the handler, so a module contributes a kind without core importing it
    until a member of that kind is actually acted on.

    :param kind: The member kind whose handler to resolve.
    :return: The handler object implementing the member protocol.
    :raises LookupError: If no module has registered a handler for the kind.
    """

    spec = project_member_kinds.get(kind)
    if spec is None:
        known = ", ".join(project_member_kinds.keys()) or "(none)"
        raise LookupError(
            f"no handler is registered for project member kind {kind!r}; "
            f"install the module that provides it. Known kinds: {known}"
        )
    return resolve_callable(spec.handler)()
