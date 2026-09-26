"""Parse and check minimum-version requirements on installed distributions.

Manifests declare ``requires = ["httk-workflow>=2.2.0", ...]``. Only the
``>=`` operator is supported, with a plain release ``N(.N)*`` on the right.
Installed versions are compared in PEP 440 order without a ``packaging``
dependency: a pre or dev release of the required release does not satisfy
it, while a post release or local label does.
"""

import importlib.metadata
import re
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["Requirement", "RequirementError", "check_requirements", "parse_requirements", "unmet_requirements"]

_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
_RELEASE_RE = re.compile(r"[0-9]+(?:\.[0-9]+)*")
_INSTALLED_RE = re.compile(
    r"""v?(?:(?P<epoch>[0-9]+)!)?(?P<release>[0-9]+(?:\.[0-9]+)*)
    (?P<pre>[-_.]?(?:a|b|c|rc|alpha|beta|pre|preview)[-_.]?[0-9]*)?
    (?P<post>-[0-9]+|[-_.]?(?:post|rev|r)[-_.]?[0-9]*)?
    (?P<dev>[-_.]?dev[-_.]?[0-9]*)?
    (?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?""",
    re.IGNORECASE | re.VERBOSE,
)


class RequirementError(ValueError):
    """Report that installed distributions do not meet declared requirements."""


@dataclass(frozen=True)
class Requirement:
    """Describe one minimum-version requirement.

    :param name: Name the distribution, normalized per PEP 503.
    :param minimum: Give the minimum release segments.
    :param text: Give the requirement as declared, without whitespace.
    """

    name: str
    minimum: tuple[int, ...]
    text: str


def parse_requirements(values: object, where: str) -> tuple[Requirement, ...]:
    """Parse a ``requires`` list of ``NAME>=VERSION`` strings.

    :param values: Supply the raw manifest value.
    :param where: Name the manifest key in error messages.
    :return: The parsed requirements in declaration order.
    :raises ValueError: If the value is not a list of valid, distinct requirement strings.
    """

    if not isinstance(values, list):
        raise ValueError(f"{where} must be an array of strings")
    result: list[Requirement] = []
    for index, value in enumerate(values):
        entry = f"{where}[{index}]"
        if not isinstance(value, str):
            raise ValueError(f"{entry} must be a string")
        name, operator, version = value.partition(">=")
        name, version = name.strip(), version.strip()
        if not operator or any(character in name for character in "<>=!~;[@ "):
            raise ValueError(
                f"{entry} {value!r} must have the form NAME>=VERSION (only minimum versions are supported)"
            )
        if _NAME_RE.fullmatch(name) is None:
            raise ValueError(f"{entry} {value!r} has an invalid distribution name {name!r}")
        if _RELEASE_RE.fullmatch(version) is None:
            raise ValueError(f"{entry} {value!r} version {version!r} must be a plain release N(.N)*")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if any(requirement.name == normalized for requirement in result):
            raise ValueError(f"{entry} {value!r} repeats distribution {normalized!r}")
        result.append(Requirement(normalized, tuple(int(part) for part in version.split(".")), f"{name}>={version}"))
    return tuple(result)


def _satisfies(installed: str, minimum: tuple[int, ...]) -> bool | None:
    """Return whether *installed* is at least *minimum*, or ``None`` when unparseable."""

    match = _INSTALLED_RE.fullmatch(installed.strip())
    if match is None:
        return None
    if int(match["epoch"] or 0) > 0:
        return True
    release = tuple(int(part) for part in match["release"].split("."))
    width = max(len(release), len(minimum))
    padded, required = release + (0,) * (width - len(release)), minimum + (0,) * (width - len(minimum))
    if padded != required:
        return padded > required
    return match["pre"] is None and (match["dev"] is None or match["post"] is not None)


def unmet_requirements(requirements: Iterable[Requirement]) -> tuple[str, ...]:
    """Describe the requirements the running interpreter does not meet.

    :param requirements: Check these requirements.
    :return: One message per unmet requirement, e.g. ``"httk-workflow>=2.2.0 (installed: 2.1.1)"``.
    """

    unmet: list[str] = []
    for requirement in requirements:
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            unmet.append(f"{requirement.text} (not installed)")
            continue
        satisfied = None if installed is None else _satisfies(installed, requirement.minimum)
        if satisfied is None:
            unmet.append(f"{requirement.text} (installed version {installed!r} is not a valid version)")
        elif not satisfied:
            unmet.append(f"{requirement.text} (installed: {installed})")
    return tuple(unmet)


def check_requirements(requirements: Iterable[Requirement], what: str) -> None:
    """Require every requirement to be met by the running interpreter.

    :param requirements: Check these requirements.
    :param what: Name the requiring manifest in the error message.
    :raises RequirementError: If any requirement is unmet; the message lists every one.
    """

    unmet = unmet_requirements(requirements)
    if unmet:
        raise RequirementError(f"{what} has unmet requirements: {'; '.join(unmet)}")
