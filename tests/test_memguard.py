"""Tests for the Linux process-group memory guard."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from httk.core.cli import main as cli_main

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not Path("/proc").is_dir(),
    reason="memguard requires Linux with a visible /proc filesystem",
)

_MODULE = "httk.core.memguard"


def test_cli_path_passes_through_child_exit_code() -> None:
    assert (
        cli_main(
            [
                "memguard",
                # Budget must exceed the child interpreter's own startup RSS
                # (~10 MiB on 3.12, ~12 MiB on 3.13/3.14) or memguard kills it
                # before it can exit; the breach test below uses a tight budget
                # against a deliberately memory-hungry child.
                "--max-rss-gb",
                "0.1",
                "--interval",
                "0.01",
                "--",
                sys.executable,
                "-c",
                "raise SystemExit(7)",
            ]
        )
        == 7
    )


def test_budget_pass_reports_peak() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            _MODULE,
            # Budget must exceed the child interpreter's own startup RSS
            # (~10 MiB on 3.12, ~12 MiB on 3.13/3.14); 10 MiB was on the edge
            # and killed a bare interpreter on 3.14.
            "--max-rss-gb",
            "0.1",
            "--interval",
            "0.01",
            "--",
            sys.executable,
            "-c",
            "pass",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "memguard: peak group RSS" in result.stderr


def test_budget_breach_kills_the_process_group() -> None:
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            _MODULE,
            "--max-rss-gb",
            "0.001",
            "--interval",
            "0.02",
            "--",
            sys.executable,
            "-c",
            "import time; data = bytearray(64 * 1024 * 1024); data[::4096] = b'x' * (64 * 1024 * 1024 // 4096); time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _stdout, stderr = child.communicate(timeout=5)
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                child.kill()
            child.wait()

    assert child.returncode == 137
    assert "exceeded" in stderr
    with pytest.raises(ProcessLookupError):
        os.killpg(child.pid, 0)


def test_missing_command_is_an_argument_error() -> None:
    result = subprocess.run(
        [sys.executable, "-m", _MODULE],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "no command given" in result.stderr
