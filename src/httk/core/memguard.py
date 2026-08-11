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

"""Run a command inside a Linux memory-guarded process group.

The child command starts in its own session (and therefore its own process
group), every process it forks inherits an optional per-process virtual
address-space rlimit, and a watchdog sums the resident memory of the whole
group at a fixed interval. When the group's total RSS exceeds the budget the
entire group receives ``SIGKILL`` — sacrificing the run, never the machine.

This is the userland fallback for environments without a delegatable cgroup v2
subtree (where ``memory.max`` on a dedicated cgroup would do the same job in
the kernel). It guards against the failure mode that motivated it: a parallel
test or benchmark run whose workers independently grow until the system-wide
OOM killer takes down unrelated processes.

The process-group sampler requires Linux and a visible ``/proc`` filesystem.
On other platforms, or when ``/proc`` is unavailable, the command exits with a
clear error instead of running without its memory guard.

Usage::

    python -m httk.core.memguard [--max-rss-gb N] [--as-gb N] [--interval SECONDS] -- command args...

The exit status is the child's status, or 137 when the watchdog killed the
group.
"""

import argparse
import os
import signal
import subprocess
import sys
from collections.abc import Sequence

from .cli import CLIContext

try:
    _PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
except (AttributeError, OSError, ValueError):
    _PAGE_SIZE = 0


def _child_peak_bytes() -> int:
    """Return the direct child's peak RSS as a sampler fallback.

    Some sandbox runners place the child in a PID namespace whose processes
    are not visible through the guard's ``/proc`` mount. The process-group
    sampler remains the enforcement mechanism where that visibility exists;
    ``RUSAGE_CHILDREN`` merely prevents a successful serial run from reporting
    a misleading zero peak in that constrained environment.

    :return: Peak resident set size of waited-for child processes, in bytes.
    """
    import resource

    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024


def _group_rss_bytes(pgid: int) -> int:
    """Return the total resident set size of every live process in a group.

    :param pgid: Process-group identifier to sample.
    :return: Total RSS in bytes.
    """
    total = 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as handle:
                fields = handle.read().rsplit(b")", 1)[1].split()
            # After the comm field: field 0 is state, 2 is pgrp, 21 is rss (pages).
            if int(fields[2]) != pgid:
                with open(f"/proc/{entry}/status", encoding="utf-8") as handle:
                    namespace_group = next(
                        (line.split()[1:] for line in handle if line.startswith("NSpgid:")),
                        (),
                    )
                # A host-mounted /proc can show host pgrps in stat while the
                # child reports the local pgrp created by setsid().
                if not namespace_group or int(namespace_group[-1]) != pgid:
                    continue
            total += int(fields[21]) * _PAGE_SIZE
        except (OSError, ValueError, IndexError):
            continue
    return total


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    return argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested command under the process-group memory guard.

    :param argv: Command-line arguments, excluding the program name. When
        omitted, arguments are read from ``sys.argv``.
    :return: The child exit status, 137 for a budget breach, or 2 when the
        platform cannot provide the Linux process-group sampler.
    """
    parser = _parser()
    parser.add_argument("--max-rss-gb", type=float, default=24.0, help="group-total RSS budget (default 24)")
    parser.add_argument(
        "--as-gb",
        type=float,
        default=None,
        help="optional per-process RLIMIT_AS, inherited by every child (off by default: "
        "address-space reservations of mmap-heavy tools can exceed real memory use)",
    )
    parser.add_argument("--interval", type=float, default=2.0, help="watchdog poll interval in seconds (default 2)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- command args...")
    arguments = parser.parse_args(argv)
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("no command given (use: python -m httk.core.memguard [options] -- command args...)")

    if sys.platform != "linux" or not os.path.isdir("/proc"):
        sys.stderr.write("memguard: requires Linux with a visible /proc filesystem\n")
        return 2

    def prepare() -> None:
        import resource

        os.setsid()
        if arguments.as_gb is not None:
            limit = int(arguments.as_gb * (1 << 30))
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    child = subprocess.Popen(command, preexec_fn=prepare)  # noqa: PLW1509 - setsid and RLIMIT_AS must run pre-exec
    pgid = child.pid  # setsid makes the child the leader of a new group with pgid == its pid.
    budget = int(arguments.max_rss_gb * (1 << 30))

    def forward(signum: int, _frame: object) -> None:
        try:
            os.killpg(pgid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGTERM, forward)

    peak = 0
    while True:
        try:
            return_code = child.wait(timeout=arguments.interval)
            break
        except subprocess.TimeoutExpired:
            pass
        rss = _group_rss_bytes(pgid)
        peak = max(peak, rss)
        if rss > budget:
            sys.stderr.write(
                f"memguard: process-group RSS {rss / (1 << 30):.1f} GiB exceeded the "
                f"{arguments.max_rss_gb:.1f} GiB budget - killing the group\n"
            )
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            return 137
    peak = max(peak, _child_peak_bytes())
    sys.stderr.write(f"memguard: peak group RSS {peak / (1 << 30):.2f} GiB (budget {arguments.max_rss_gb:.1f} GiB)\n")
    return return_code


def command(argv: Sequence[str], _context: CLIContext) -> int:
    """Adapt the memory guard to the top-level ``httk`` command contract."""
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
