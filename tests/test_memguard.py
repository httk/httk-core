"""Tests for the Linux process-group memory guard."""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from httk.core import memguard
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
            "--max-pss-gb",
            "0.1",
            "--interval",
            "0.01",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(0.1)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "memguard: peak sampled group PSS" in result.stderr


def test_budget_breach_kills_the_process_group() -> None:
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            _MODULE,
            "--max-pss-gb",
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


@pytest.mark.parametrize("copy_on_write", [False, True])
def test_forked_pages_are_charged_only_when_copied(copy_on_write: bool) -> None:
    # Five processes share 64 MiB: summed RSS exceeds the 128 MiB budget,
    # but their proportional total fits. Keep them alive across several polls.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            _MODULE,
            "--max-pss-gb",
            "0.125",
            "--interval",
            "0.02",
            "--",
            sys.executable,
            "-c",
            f"""import os, time
data = bytearray(64 * 1024 * 1024)
data[::4096] = b'x' * (len(data) // 4096)
for _ in range(4):
    if os.fork() == 0:
        if {copy_on_write!r}:
            data[::4096] = b'y' * (len(data) // 4096)
        time.sleep(0.5)
        os._exit(0)
for _ in range(4):
    os.wait()
""",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == (137 if copy_on_write else 0), result.stderr
    assert ("exceeded" if copy_on_write else "peak sampled group PSS") in result.stderr


def test_unreadable_pss_does_not_start_an_unguarded_command(monkeypatch, tmp_path, capsys) -> None:
    def denied(_pid):
        raise PermissionError("smaps_rollup denied")

    monkeypatch.setattr(memguard, "_process_pss_bytes", denied)
    marker = tmp_path / "started"
    assert memguard.main([sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"]) == 2
    assert not marker.exists()
    assert "cannot read PSS accounting" in capsys.readouterr().err


def test_unreadable_live_member_is_not_silently_omitted(monkeypatch) -> None:
    def denied(_pid):
        raise PermissionError("smaps_rollup denied")

    monkeypatch.setattr(memguard, "_process_pss_bytes", denied)
    with pytest.raises(PermissionError, match="smaps_rollup denied"):
        memguard._group_pss_bytes(os.getpgrp())
