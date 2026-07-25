"""Shared command-line handler context."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CLIContext:
    """Invocation context passed to a registered top-level command."""

    program: str
    cwd: Path
