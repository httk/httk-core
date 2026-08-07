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

"""Strict, deliberately small Semantic Versioning helpers for documentation tags."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["Version", "VersionError", "highest_version", "is_release_dir_name", "parse_tag", "parse_version"]


class VersionError(ValueError):
    """Raised when text is not an exact ``X.Y.Z`` documentation version."""


@dataclass(frozen=True, order=True)
class Version:
    """Represent one non-negative three-component documentation release version.

    :param major: Major release component.
    :param minor: Minor release component.
    :param patch: Patch release component.
    :raises VersionError: If a component is negative, non-integral, or boolean.
    """

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        """Reject components that cannot be represented by this value object."""

        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (self.major, self.minor, self.patch)
        ):
            raise VersionError("version components must be non-negative integers")

    def __str__(self) -> str:
        """Return the canonical ``X.Y.Z`` spelling."""

        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag(self) -> str:
        """Return the canonical Git tag spelling, ``vX.Y.Z``."""

        return f"v{self}"


_VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_TAG_PATTERN = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


def _parse(text: str, pattern: re.Pattern[str], spelling: str) -> Version:
    if not isinstance(text, str):
        raise VersionError(f"invalid {spelling}: {text!r}")
    match = pattern.fullmatch(text)
    if match is None:
        raise VersionError(f"invalid {spelling}: {text!r}; expected {spelling}")
    return Version(*(int(component) for component in match.groups()))


def parse_version(text: str) -> Version:
    """Parse exactly ``X.Y.Z`` without prerelease or build metadata.

    :param text: Version spelling to validate.
    :return: Parsed release version.
    :raises VersionError: If *text* is not an exact ``X.Y.Z`` version.
    """

    return _parse(text, _VERSION_PATTERN, "version X.Y.Z")


def parse_tag(text: str) -> Version:
    """Parse exactly the release tag ``vX.Y.Z``.

    :param text: Git tag spelling to validate.
    :return: Parsed release version.
    :raises VersionError: If *text* is not an exact ``vX.Y.Z`` tag.
    """

    return _parse(text, _TAG_PATTERN, "tag vX.Y.Z")


def highest_version(versions: Iterable[Version]) -> Version | None:
    """Return the greatest version in *versions*, or ``None`` when empty.

    :param versions: Versions to compare.
    :return: Greatest version, or ``None`` when the iterable is empty.
    """

    return max(versions, default=None)


def is_release_dir_name(name: str) -> bool:
    """Return whether *name* is a valid release directory such as ``v2.1.0``.

    :param name: Directory name to validate.
    :return: Whether *name* is an exact release tag spelling.
    """

    try:
        parse_tag(name)
    except VersionError:
        return False
    return True
