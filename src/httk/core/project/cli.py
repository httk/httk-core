"""The core-owned ``httk project`` command.

``httk project`` owns the anchor: ``init`` creates one (like ``git init``),
``show`` describes it, ``export`` creates a signed redistribution,
``verify-export`` checks one, and ``import-v1`` migrates a legacy project.
"""

import argparse
import json
import logging
import shutil
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from httk.core.cli import CLIContext
from httk.core.identity import identity_key_paths
from httk.core.register.cli import cli_extensions
from httk.core.register.members import project_member_handler

from .anchor import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
    import_v1_project,
    initialize_project,
    key_fingerprint,
    pin_project_key,
    pinned_project_key,
    project_public_key_path,
    read_project,
    read_public_key_file,
    require_project,
    trusted_project_keys,
)
from .export import export_project, verify_export
from .manifests import (
    VALID_TRUSTED,
    VALID_UNKNOWN_KEY,
    create_manifest,
    resolve_trusted_keys,
    verify_manifest,
)
from .members import project_members
from .sealing import (
    SealKeys,
    default_project_keys,
    project_seal_path,
    read_seal,
    seal_project,
    unseal_project,
    verify_project,
)
from .templates import available_templates, check_parameters, instantiate_template, resolve_template

_LOGGER = logging.getLogger(__name__)

#: Everything a handler may raise that is an operator's problem rather than a
#: defect. Anything here is reported as ``PROGRAM: message`` and exits ``2``.
_ERRORS = (OSError, ValueError, RuntimeError)

#: The handler contract every project subcommand honors, the same one the root
#: :command:`httk` commands use.
Handler = Callable[[argparse.Namespace, CLIContext], int]


def _key_record(value: str) -> dict[str, object]:
    return {"public_key": value, "fingerprint": key_fingerprint(value)}


def _field(name: str, value: object) -> str:
    """Render one name/value line of a human-readable description."""

    return f"{name:<22}{value}"


def describe_project(root: str | Path | None = None) -> dict[str, object]:
    """Describe one project's anchor.

    :param root: Project root, or None to discover the nearest project.
    :return: JSON-ready description of project metadata and trust keys.
    :raises ValueError: If no project exists or its metadata is invalid.
    """

    project = require_project(root)
    metadata = read_project(project)
    own = pinned_project_key(metadata)
    trusted = trusted_project_keys(metadata)
    seed = project / PROJECT_DIRECTORY / "keys" / "project.seed"
    description: dict[str, object] = {
        "format": "httk-project-description",
        "format_version": 2,
        "root": str(project),
        "project": {
            "project_id": metadata.get("project_id"),
            "name": metadata.get("name"),
            "description": metadata.get("description"),
            "imported_from": metadata.get("imported_from"),
            "manifest_exclusions": metadata.get("manifest_exclusions", []),
        },
        "keys": {
            "pinned": own is not None,
            "public_key": None if own is None else _key_record(own),
            "seed_present": seed.is_file(),
            "trusted_keys": [_key_record(key) for key in trusted],
        },
    }
    return description


def _render(description: dict[str, object]) -> str:
    """Render one anchor description as readable lines."""

    project = description.get("project", {})
    keys = description.get("keys", {})
    assert isinstance(project, dict) and isinstance(keys, dict)
    public = keys.get("public_key") or {}
    assert isinstance(public, dict)
    lines = [
        _field("root", description.get("root")),
        _field("name", project.get("name") or "-"),
        _field("project_id", project.get("project_id") or "-"),
        _field("key_pinned", "yes" if keys.get("pinned") else "no"),
        _field("key_fingerprint", public.get("fingerprint") or "-"),
        _field("trusted_keys", len(keys.get("trusted_keys", []))),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in leaves
# ---------------------------------------------------------------------------


def _init_one(path: Path, arguments: argparse.Namespace) -> None:
    """Create one project anchor at PATH, refusing an existing project."""

    if (path / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
        raise ValueError(f"{path} is already an httk project")
    if not arguments.template:
        metadata = initialize_project(
            path,
            name=arguments.name or path.name,
            description=arguments.description,
        )
        print(f"Initialized httk project {metadata['name']!r} in {path / PROJECT_DIRECTORY}")
        return

    template = resolve_template(arguments.template)
    supplied: dict[str, object] = {}
    for value in arguments.parameter or []:
        if "=" not in value:
            raise ValueError(f"invalid template parameter {value!r}; expected NAME=VALUE")
        name, raw = value.split("=", 1)
        try:
            supplied[name] = json.loads(raw)
        except json.JSONDecodeError:
            supplied[name] = raw
    parameters = check_parameters(template, supplied)
    was_fresh = not path.exists() or (path.is_dir() and not any(path.iterdir()))

    try:
        initialize_project(
            path,
            name=arguments.name or path.name,
            description=arguments.description,
        )
        project = describe_project(path)["project"]
        assert isinstance(project, dict)
        notes = instantiate_template(
            template,
            path,
            parameters,
            project_info={
                "name": project.get("name"),
                "description": project.get("description"),
                "project_id": project.get("project_id"),
            },
        )
    except _ERRORS as exc:
        if was_fresh:
            if path.is_dir():
                shutil.rmtree(path)
        else:
            raise ValueError(
                f"{exc}; partial state left in {path} (httk_project/ and any copied template files)"
            ) from exc
        raise
    print(f"Initialized httk project {project['name']!r} in {path / PROJECT_DIRECTORY}")
    for note in notes:
        print(f"note: {note}")


def _handle_init(arguments: argparse.Namespace, context: CLIContext) -> int:
    if arguments.list_templates:
        templates = available_templates()
        if not templates:
            print("no templates available")
        else:
            for plugin, template in templates:
                print(f"{plugin}:{template.id}  {template.description or ''}")
            print("templates can also be given as a directory path")
        return 0
    failed = False
    for raw_path in arguments.paths:
        label: str | Path = raw_path
        try:
            path = Path(raw_path).expanduser().resolve()
            label = path
            _init_one(path, arguments)
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {label}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_import_v1(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Import a legacy v1 project into a new v2 anchor."""

    failed = False
    for raw_path in arguments.paths:
        label: str | Path = raw_path
        try:
            path = Path(raw_path).expanduser().resolve()
            label = path
            if (path / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
                raise ValueError(f"{path} is already an httk project")
            source = Path(arguments.source or path / "ht.project").expanduser().resolve()
            import_v1_project(path, source=source, name=arguments.name)
            print(f"imported {source} -> {path / PROJECT_DIRECTORY}")
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {label}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_show(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Describe the nearest project: its metadata and keys."""

    descriptions: list[dict[str, object]] = []
    failed = False
    paths = arguments.paths or [str(context.cwd)]
    for raw_path in paths:
        label: str | Path = raw_path
        try:
            path = Path(raw_path).expanduser().resolve()
            label = path
            description = describe_project(path)
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {label}: {exc}", file=sys.stderr)
            continue
        descriptions.append(description)
        if not arguments.json:
            print(f"=== {path} ===")
            print(_render(description))
    if arguments.json:
        print(json.dumps(descriptions, indent=2, sort_keys=True))
    return 1 if failed else 0


def _handle_export(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Export the nearest project tree into a signed redistribution ZIP."""

    output = export_project(Path(arguments.out_zip).expanduser().resolve(), context.cwd)
    print(f"exported project to {output}")
    return 0


def _handle_verify_export(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Verify a signed redistribution ZIP and print its signer."""

    failed = False
    for raw_path in arguments.zip_paths:
        try:
            report = verify_export(
                raw_path,
                expect_key=arguments.expect_key,
                trusted_keys=arguments.trusted_keys,
            )
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {raw_path}: {exc}", file=sys.stderr)
            continue
        print(f"=== {raw_path} ===")
        print(report["status"])
        print(f"public_key: {report['public_key']}")
        print(f"fingerprint: {report['fingerprint']}")
    return 1 if failed else 0


def _build_init(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="directories to make projects",
    )
    parser.add_argument("--name", metavar="NAME", help="the project name (default: the directory name)")
    parser.add_argument("--description", metavar="TEXT", default="", help="a one-line description")
    parser.add_argument("--template", metavar="SELECTOR", help="instantiate a project template")
    parser.add_argument(
        "--parameter",
        action="append",
        metavar="NAME=VALUE",
        help="set a template parameter (repeatable)",
    )
    parser.add_argument("--list-templates", action="store_true", help="list available project templates")


def _build_show(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="projects to describe (default: the nearest project of the working directory)",
    )
    parser.add_argument("--json", action="store_true", help="print the description as one JSON document")


def _build_import_v1(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="+",
        help="projects to import",
    )
    parser.add_argument("--source", metavar="DIR", help="the v1 project directory (default: PATH/ht.project)")
    parser.add_argument("--name", metavar="NAME", help="the imported project name")


def _build_export(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("out_zip", metavar="OUT.ZIP", help="destination signed redistribution ZIP")


def _build_verify_export(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("zip_paths", metavar="ZIP", nargs="+", help="signed redistribution ZIPs to verify")
    parser.add_argument("--expect-key", metavar="FINGERPRINT", help="require this signer fingerprint")
    parser.add_argument(
        "--trusted-key",
        dest="trusted_keys",
        metavar="FINGERPRINT",
        action="append",
        default=[],
        help="trust this signer fingerprint",
    )


# ---------------------------------------------------------------------------
# doctor, manifest, seal, unseal, verify-seal
# ---------------------------------------------------------------------------


def _confirm(prompt: str, *, force: bool) -> bool:
    """Gate one destructive action behind a terminal confirmation.

    ``--force`` answers yes without asking; without a terminal and without
    ``--force`` the action is refused with a hint rather than blocking on an
    unanswerable prompt.

    :param prompt: The question to ask, without the ``[y/N]`` suffix.
    :param force: Whether ``--force`` was given, answering yes unconditionally.
    :return: Whether the action was confirmed.
    """

    if force:
        return True
    if not sys.stdin.isatty():
        print("this operation without a terminal requires --force", file=sys.stderr)
        return False
    if input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}:
        return True
    print("not unsealed")
    return False


def _finding(check: str, status: str, message: str, **extra: object) -> dict[str, object]:
    """Return one doctor finding in the shared mapping shape."""

    details = extra.get("details")
    return {
        "check": check,
        "status": status,
        "message": message,
        "repairable": bool(extra.get("repairable", False)),
        "repaired": bool(extra.get("repaired", False)),
        "action": extra.get("action"),
        "details": dict(details) if isinstance(details, dict) else {},
    }


def _check_key_pin(project: Path, metadata: dict[str, object], repair: bool) -> dict[str, object]:
    """Without a pin, manifest verification has no anchor but the manifest itself."""

    if pinned_project_key(metadata) is not None:
        return _finding("key_pin", "ok", "project.json pins the project's public key")
    repairable = project_public_key_path(project).is_file()
    finding = _finding(
        "key_pin",
        "warning",
        "project.json pins no public key, so every manifest verifies as an unknown key",
        repairable=repairable,
    )
    if repair and repairable:
        pinned = pin_project_key(project)
        finding["action"] = f"pinned {key_fingerprint(str(pinned['public_key']))}"
        finding["repaired"] = True
        finding["status"] = "ok"
        metadata.update(pinned)
    return finding


def _check_manifest(project: Path) -> dict[str, object]:
    """Manifest staleness is reported and never repaired behind an operator."""

    path = project / PROJECT_DIRECTORY / "manifest.jsonl.bz2"
    if not path.is_file():
        return _finding("manifest", "warning", "this project has no manifest", details={"present": False})
    try:
        verification = verify_manifest(project)
    except (OSError, ValueError) as exc:
        return _finding("manifest", "error", f"the manifest could not be verified: {exc}")
    status = {"valid_trusted": "ok", "valid_unknown_key": "warning"}.get(verification.verdict, "error")
    return _finding(
        "manifest",
        status,
        f"{verification.verdict}: {verification.reason}",
        details={"verdict": verification.verdict},
    )


def project_doctor(project_root: str | Path | None = None, *, repair: bool = False) -> dict[str, object]:
    """Check a project's anchor and every member, and optionally repair it.

    Core owns the anchor checks — the key pin and the manifest — and each member
    handler contributes its own findings, concatenated after them.

    :param project_root: Project root, or None to discover the nearest project.
    :param repair: Whether to apply automatic repairs.
    :return: JSON-compatible doctor report.
    """

    project = require_project(project_root)
    metadata = read_project(project)
    findings: list[dict[str, object]] = [
        _check_key_pin(project, metadata, repair),
        _check_manifest(project),
    ]
    for member in project_members(project):
        try:
            handler = project_member_handler(member.kind)
            findings.extend(handler.doctor(project / member.path, repair=repair))
        except LookupError:
            findings.append(
                _finding(
                    f"member:{member.path}",
                    "error",
                    f"member kind {member.kind!r} has no registered handler; install the module that provides it",
                )
            )
    return {
        "format": "httk-project-doctor",
        "format_version": 2,
        "root": str(project),
        "project_id": metadata.get("project_id"),
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repair": repair,
        "findings": findings,
        "problems": sum(finding["status"] != "ok" for finding in findings),
        "repaired": sum(bool(finding["repaired"]) for finding in findings),
    }


def _handle_doctor(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Check, and optionally repair, one or more projects."""

    paths = arguments.paths or [str(context.cwd)]
    reports: list[dict[str, object]] = []
    failed = False
    for raw_path in paths:
        try:
            report = project_doctor(Path(raw_path).expanduser().resolve(), repair=arguments.repair)
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {raw_path}: {exc}", file=sys.stderr)
            continue
        reports.append(report)
        findings = report["findings"]
        assert isinstance(findings, list)
        if not arguments.json:
            if len(paths) > 1:
                print(f"=== {report['root']} ===")
            for finding in findings:
                repaired = " (repaired)" if finding.get("repaired") else ""
                print(f"{finding['status']}\t{finding['check']}\t{finding['message']}{repaired}")
            print(f"{report['problems']} problem(s), {report['repaired']} repaired")
        # A warning is a thing to know about, not to fail a script on; only a
        # check that is actually broken makes the command itself fail.
        if any(finding.get("status") == "error" for finding in findings):
            failed = True
    if arguments.json:
        print(json.dumps(reports if len(paths) > 1 else reports[0] if reports else {}, indent=2, sort_keys=True))
    return 1 if failed else 0


def _handle_manifest_create(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Write the signed manifest of the nearest project."""

    print(create_manifest(arguments.project or context.cwd, output=arguments.manifest))
    return 0


def _handle_manifest_verify(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Verify one project manifest against the tree and its trust anchors."""

    verification = verify_manifest(
        arguments.project or context.cwd,
        manifest=arguments.manifest,
        trusted_keys=arguments.trusted_key,
    )
    print("valid" if verification.valid else "invalid")
    print(f"{verification.verdict}: {verification.reason}")
    return verification.exit_code


def _handle_seal(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Seal a project: its loose files and every member's seal digest."""

    root = require_project(arguments.project or context.cwd)
    refs = [ref.strip() for ref in arguments.keys.split(",") if ref.strip()] if arguments.keys else None
    resolved: SealKeys | None = default_project_keys(root, refs) if refs is not None else None
    seal_project(root, keys=resolved)
    seal = read_seal(project_seal_path(root))
    roles = ",".join(str(signature.get("role")) for signature in seal.signatures)
    print(f"{root}\tsealed\t{roles}")
    return 0


def _handle_unseal(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Remove a project's seal, after confirmation."""

    root = require_project(arguments.project or context.cwd)
    if not _confirm(f"Unseal the project at {root}?", force=arguments.force):
        return 1
    unseal_project(root)
    print(f"{root}\tunsealed")
    return 0


def _default_trusted_keys(project: Path, explicit: list[str]) -> list[str]:
    """Return the trust anchors ``verify-seal`` uses by default.

    A tree sealed by its own project or its own operator identity verifies as
    trusted without the operator naming a key: the project's pinned keys, every
    explicitly supplied key, and the local identity's public key when one exists.
    """

    trusted = list(resolve_trusted_keys(project, trusted_keys=explicit))
    public_key_path = identity_key_paths()[1]
    if public_key_path.is_file():
        identity_key = read_public_key_file(public_key_path)
        if identity_key not in trusted:
            trusted.append(identity_key)
    return trusted


def _handle_verify_seal(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Verify the project seal and, unless shallow, every member seal it references."""

    root = require_project(arguments.path or context.cwd)
    trusted = _default_trusted_keys(root, list(arguments.trusted_key))
    report = verify_project(root, trusted_keys=trusted, deep=not arguments.shallow)
    verdicts = [str(entry["verdict"]) for entry in report.entries]
    if not report.ok:
        exit_code, final = 1, "FAILED"
    elif VALID_UNKNOWN_KEY in verdicts:
        exit_code, final = 3, "UNTRUSTED"
    else:
        exit_code, final = 0, "ok"
    if arguments.json:
        document = {
            "entries": list(report.entries),
            "ok": report.ok,
            "trusted": bool(report.entries) and all(verdict == VALID_TRUSTED for verdict in verdicts),
        }
        print(json.dumps(document, indent=2, sort_keys=True))
        return exit_code
    for entry in report.entries:
        print(f"{entry['level']}\t{entry['subject']}\t{entry['verdict']}\t{entry['reason'] or '-'}")
        discrepancies = entry["discrepancies"]
        assert isinstance(discrepancies, list)
        for discrepancy in discrepancies:
            print(f"  {discrepancy['kind']}\t{discrepancy['path']}")
    print(final)
    return exit_code


def _build_doctor(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="the project to check (default: the nearest project of the working directory)",
    )
    parser.add_argument("--repair", action="store_true", help="also fix every finding that can be fixed automatically")
    parser.add_argument("--json", action="store_true", help="print the report as one JSON document")


def _build_manifest_create(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project", metavar="PROJECT", nargs="?", help="the project (default: the nearest one)")
    parser.add_argument("--manifest", metavar="PATH", help="write the manifest here rather than in the project")


def _build_manifest_verify(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project", metavar="PROJECT", nargs="?", help="the project (default: the nearest one)")
    parser.add_argument("--manifest", metavar="PATH", help="verify this manifest rather than the project's")
    parser.add_argument(
        "--trusted-key",
        action="append",
        default=[],
        metavar="PATH_OR_VALUE",
        help=(
            "trust this Ed25519 public key as well: an ed25519:BASE64 value or the path of a *.pub file "
            "(repeatable). The project's pinned key is always trusted"
        ),
    )


def _build_seal(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project", metavar="PROJECT", nargs="?", help="the project to seal (default: the nearest one)")
    parser.add_argument(
        "--keys",
        metavar="REFS",
        help="comma-separated seal-key refs to sign with (default: the project's seal_keys member)",
    )


def _build_unseal(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "project", metavar="PROJECT", nargs="?", help="the project to unseal (default: the nearest one)"
    )
    parser.add_argument("--force", action="store_true", help="skip the confirmation prompt")


def _build_verify_seal(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", metavar="PATH", nargs="?", help="a project to verify (default: the nearest one)")
    parser.add_argument("--json", action="store_true", help="print the report as one JSON document")
    parser.add_argument(
        "--trusted-key",
        action="append",
        default=[],
        metavar="KEY_OR_FINGERPRINT",
        help=(
            "trust this key as well: an ed25519:BASE64 value, a sha256: fingerprint, or the path of a *.pub file "
            "(repeatable). The project's pinned keys and the local identity are always trusted"
        ),
    )
    parser.add_argument("--shallow", action="store_true", help="verify only the project seal, not the member seals")


def _add_manifest_group(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Mount the ``manifest create|verify`` group under the project command."""

    manifest = subparsers.add_parser(
        "manifest", help="create and verify the signed project manifest", description="Create and verify the manifest"
    )
    manifest.set_defaults(handler=None, help_parser=manifest)
    actions = manifest.add_subparsers(dest="manifest_action", metavar="ACTION")
    create = actions.add_parser("create", help="write the signed manifest", description="Write the signed manifest")
    create.set_defaults(handler=_handle_manifest_create, help_parser=create)
    _build_manifest_create(create)
    verify = actions.add_parser(
        "verify", help="verify the manifest against the tree", description="Verify one project manifest"
    )
    verify.set_defaults(handler=_handle_manifest_verify, help_parser=verify)
    _build_manifest_verify(verify)


# ---------------------------------------------------------------------------
# Assembly and dispatch
# ---------------------------------------------------------------------------


def _add_leaf(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
    name: str,
    *,
    summary: str,
    handler: Handler,
    build: Callable[[argparse.ArgumentParser], None],
) -> None:
    parser = subparsers.add_parser(name, help=summary, description=summary)
    parser.set_defaults(handler=handler, help_parser=parser)
    build(parser)


def build_parser(program: str) -> argparse.ArgumentParser:
    """Build the core-owned project command tree.

    :param program: Program name used by the parser in help and errors.
    :return: Configured project command parser.
    """

    parser = argparse.ArgumentParser(prog=program, description="Create and inspect httk projects")
    parser.set_defaults(handler=None, help_parser=parser)
    subparsers = parser.add_subparsers(dest="subcommand", metavar="COMMAND")
    _add_leaf(subparsers, "init", summary="create a project anchor here", handler=_handle_init, build=_build_init)
    _add_leaf(
        subparsers,
        "show",
        summary="describe the nearest project",
        handler=_handle_show,
        build=_build_show,
    )
    _add_leaf(
        subparsers,
        "import-v1",
        summary="import a legacy v1 project",
        handler=_handle_import_v1,
        build=_build_import_v1,
    )
    _add_leaf(
        subparsers,
        "export",
        summary="create a signed project redistribution",
        handler=_handle_export,
        build=_build_export,
    )
    _add_leaf(
        subparsers,
        "verify-export",
        summary="verify a signed project redistribution",
        handler=_handle_verify_export,
        build=_build_verify_export,
    )
    _add_leaf(
        subparsers,
        "doctor",
        summary="check, and optionally repair, this project",
        handler=_handle_doctor,
        build=_build_doctor,
    )
    _add_manifest_group(subparsers)
    _add_leaf(
        subparsers,
        "seal",
        summary="seal the project and every member it holds",
        handler=_handle_seal,
        build=_build_seal,
    )
    _add_leaf(
        subparsers,
        "unseal",
        summary="remove the project's seal",
        handler=_handle_unseal,
        build=_build_unseal,
    )
    _add_leaf(
        subparsers,
        "verify-seal",
        summary="verify a sealed project tree against its seals",
        handler=_handle_verify_seal,
        build=_build_verify_seal,
    )
    # Installed modules mount extra leaves under `httk project` via the
    # `register_cli_extension("project", ...)` surface. During the transition
    # while *httk-workflow* still mounts its own `doctor|manifest|seal|unseal`
    # this way, a provider leaf whose name collides with a core-owned leaf is
    # skipped rather than fatal; this disappears when that extension is removed.
    for provider in cli_extensions("project"):
        try:
            provider(subparsers)
        except argparse.ArgumentError as exc:
            _LOGGER.debug("skipping project CLI extension leaf that collides with a core leaf: %s", exc)
    return parser


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level project command.

    :param argv: Arguments following the project command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = build_parser(f"{context.program} project")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    try:
        if arguments.subcommand == "init":
            if arguments.list_templates:
                if (
                    arguments.paths
                    or arguments.name
                    or arguments.description
                    or arguments.template
                    or arguments.parameter
                ):
                    parser.error("--list-templates cannot be combined with PATH or project/template options")
            elif not arguments.paths:
                parser.error("init requires at least one PATH")
            elif arguments.name and len(arguments.paths) != 1:
                parser.error("--name requires exactly one PATH")
            elif arguments.parameter and not arguments.template:
                parser.error("--parameter requires --template")
        elif arguments.subcommand == "import-v1" and (arguments.source or arguments.name) and len(arguments.paths) != 1:
            parser.error("--source and --name require exactly one PATH")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    handler: Handler | None = getattr(arguments, "handler", None)
    if handler is None:
        getattr(arguments, "help_parser", parser).print_help()
        return 0
    try:
        return handler(arguments, context)
    except _ERRORS as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(command(sys.argv[1:], CLIContext("httk", Path.cwd())))
