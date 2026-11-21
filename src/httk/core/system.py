"""Per-user httk state reset, driven by ``httk setup --reset``."""

import shutil
import sys
from pathlib import Path

from httk.core.userdirs import config_home, data_home


def _reset_user_state(*, yes: bool) -> int:
    """Remove the per-user httk configuration and data homes after confirmation.

    The homes are listed with a warning first; without *yes* the removal waits
    for a terminal confirmation and is refused when stdin is not a terminal.

    :param yes: Whether ``--yes`` pre-confirmed the prompt.
    :return: Command exit status: ``0`` on success, ``1`` when declined, ``2`` when refused or failed.
    """

    program = "httk setup"
    targets = [config_home(), data_home()]
    home = Path.home().resolve()
    for target in targets:
        if target.parent == target or target == home:
            print(f"{program}: refusing to remove {target}", file=sys.stderr)
            return 2

    print("WARNING! This will remove all httk per-user configuration and data:")
    for target in targets:
        print(f"  - {target}")

    if not yes:
        if not sys.stdin.isatty():
            print(
                f"{program}: refusing to reset without --yes when stdin is not a terminal",
                file=sys.stderr,
            )
            return 2
        try:
            answer = input("Are you sure you want to continue? [y/N] ")
        except EOFError:
            return 1
        if answer.strip().lower() not in {"y", "yes"}:
            return 1

    for target in targets:
        try:
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                continue
        except OSError as exc:
            print(f"{program}: cannot remove {target}: {exc}", file=sys.stderr)
            return 2
        print(f"removed {target}")
    return 0
