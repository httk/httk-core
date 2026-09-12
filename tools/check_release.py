"""Verify a committed httk module in disposable release and wheel environments.

Run with Python 3.12+, Git, make, and (for JavaScript projects) Node/npm.
This standalone repository tool does not require an installed httk package.
"""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path


def _environment(work: Path) -> dict[str, str]:
    """Remove workspace Python, package-index, and test-selection overrides."""
    excluded = {
        "VIRTUAL_ENV",
        "MAKEFLAGS",
        "MFLAGS",
        "MAKELEVEL",
        "MAKEFILES",
        "GNUMAKEFLAGS",
        "MYPYPATH",
        "NODE_OPTIONS",
        "PYTHON",
        "NODE",
        "NPM",
        "DIST_DIR",
        "DOCS_BASE_URL",
        "MEMGUARD",
        "TEST_TIMEOUT_SECONDS",
        "EXTENDED_TEST_TIMEOUT_SECONDS",
    }
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in excluded and not key.startswith(("PYTHON", "PYTEST", "PIP_", "HTTK_", "CONDA_"))
    }
    paths = []
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        path = Path(entry)
        if path.is_absolute() and not (path.resolve().parent / "pyvenv.cfg").is_file():
            paths.append(entry)
    env.update(
        PATH=os.pathsep.join([str(work / ".venv/bin"), *paths]),
        PYTHONNOUSERSITE="1",
        PIP_CONFIG_FILE=os.devnull,
        PIP_INDEX_URL="https://pypi.org/simple",
        PIP_CACHE_DIR=str(work / "cache/pip"),
        npm_config_cache=str(work / "cache/npm"),
        TMPDIR=str(work / "tmp"),
    )
    return env


def _snapshot(repo: Path, work: Path) -> tuple[Path, str]:
    """Export exactly one clean commit, preserving executable bits and symlinks."""
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none"],
        cwd=repo,
        text=True,
    )
    if dirty:
        raise ValueError(f"Commit or remove uncommitted changes before checking:\n{dirty}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    tree = subprocess.check_output(["git", "ls-tree", "-r", commit], cwd=repo, text=True)
    if any(line.startswith("160000 ") for line in tree.splitlines()):
        raise ValueError("Check individual module repositories; gitlink/submodule archives are unsupported")
    source = work / "source"
    source.mkdir()
    archive = work / "source.tar"
    with archive.open("wb") as output:
        subprocess.run(["git", "archive", commit], cwd=repo, stdout=output, check=True)
    with tarfile.open(archive) as exported:
        exported.extractall(source, filter="data")
    archive.unlink()
    return source, commit


def _run(command: list[str], cwd: Path, env: dict[str, str], log: Path) -> None:
    """Run a gate, retaining its complete output and propagating failure."""
    print(f"Running {shlex.join(command)}\n  log: {log}", flush=True)
    with log.open("w") as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        print("\n".join(log.read_text(errors="replace").splitlines()[-30:]), file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, command)


def main() -> int:
    """Run the release gates and write a commit-specific verification report.

    :return: Zero when every gate passes, otherwise one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--tag", help="Expected release tag; defaults to v<project.version>.")
    parser.add_argument("--output-dir", type=Path, help="New directory for retained logs, environments, and artifacts.")
    args = parser.parse_args()
    repo = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=args.repository,
            text=True,
        ).strip()
    )
    if args.output_dir:
        work = args.output_dir.resolve()
        work.mkdir(parents=True, exist_ok=False)
    else:
        work = Path(tempfile.mkdtemp(prefix="httk-release-check-")).resolve()
    print(f"Verification output: {work}", flush=True)
    report: dict[str, object] = {
        "repository": str(repo),
        "status": "failed",
        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Declared CI/release targets, locked docs, and configured bare-wheel imports; "
        "does not add browser or live-database gates, or reproduce the GitHub OS image.",
    }
    passed: list[str] = []
    report["passed"] = passed
    try:
        source, commit = _snapshot(repo, work)
        project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
        tag = args.tag or f"v{project['version']}"
        if tag != f"v{project['version']}":
            raise ValueError(f"Tag {tag!r} does not match project.version {project['version']!r}")
        report.update(commit=commit, tag=tag, python=sys.version)
        print(f"Checking {project['name']} {tag}, commit {commit}", flush=True)
        (work / "tmp").mkdir()
        env = _environment(work)
        env["HTTK_DOCS_VERSION"] = tag
        python = str(work / ".venv/bin/python")

        def gate(name: str, command: list[str], cwd: Path = source) -> None:
            _run(command, cwd, env, work / f"{name}.log")
            passed.append(name)

        gate("create-environment", [sys.executable, "-I", "-m", "venv", str(work / ".venv")])
        gate("install-dev", [python, "-I", "-m", "pip", "install", "-e", ".[dev]"])
        # The Makefiles invoke this Python tool directly, rather than via -m.
        # Require the fresh environment's executable, not a user PATH fallback.
        gate("dev-cli", [str(work / ".venv/bin/pydoclint"), "--version"])
        gate("dev-dependencies", [python, "-I", "-m", "pip", "check"])
        gate("dev-environment", [python, "-I", "-m", "pip", "freeze"])
        if (source / "package-lock.json").exists():
            gate("npm", ["npm", "ci"])
        gate("ci", ["make", "ci"])
        gate("install-release", [python, "-I", "-m", "pip", "install", "-e", ".[dev,docs,release]"])
        gate("dependencies", [python, "-I", "-m", "pip", "check"])
        gate("environment", [python, "-I", "-m", "pip", "freeze"])
        gate("preflight", [python, "-I", "-m", "httk.core.docs", "check-release", "--tag", tag])
        gate("release-check", ["make", "release-check"])
        gate("docs-lock-check", ["make", "docs-lock-check"])
        wheels = list((source / "dist").glob("*.whl"))
        if len(wheels) != 1:
            raise ValueError(f"Expected one built wheel, found {len(wheels)}")
        report["artifacts_sha256"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source / "dist").iterdir())
            if path.is_file()
        }
        wheel_env = work / "wheel-env"
        gate("create-wheel-environment", [python, "-I", "-m", "venv", str(wheel_env)])
        wheel_python = str(wheel_env / "bin/python")
        gate("install-wheel", [wheel_python, "-I", "-m", "pip", "install", str(wheels[0])], work)
        gate("wheel-dependencies", [wheel_python, "-I", "-m", "pip", "check"], work)
        config = tomllib.loads((source / "docs/versioning.toml").read_text())
        roots = config["site"]["import-roots"]
        if not roots:
            raise ValueError("docs/versioning.toml must declare public import-roots")
        gate(
            "wheel-imports",
            [
                wheel_python,
                "-I",
                "-c",
                (
                    "import importlib, importlib.metadata, sys; "
                    "assert importlib.metadata.version(sys.argv[1]) == sys.argv[2]; "
                    "[importlib.import_module(name) for name in sys.argv[3:]]"
                ),
                project["name"],
                project["version"],
                project["name"].replace("-", "."),
                *(root.replace("/", ".") for root in roots),
            ],
            work,
        )
        report["status"] = "passed"
        print(f"PASS: {commit}\nArtifacts: {source / 'dist'}", flush=True)
        return 0
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        report["error"] = str(error)
        print(f"FAILED: {error}\nSee logs in {work}", file=sys.stderr)
        return 1
    finally:
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
