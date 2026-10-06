"""Generate typed result record modules from registered OPTIMADE property definitions.

The generator reads each definition (so the registry must be loaded) and emits one frozen
:class:`~httk.core.typed_records.TypedRecord` dataclass per definition. Packages regenerate and verify
their committed module through :func:`main`, e.g. from a ``tools/generate_records.py`` script.
"""

import argparse
import difflib
import re
import sys
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .register.schemas import load_property_definition
from .typed_records import MemberLayout, TypedRecordSpec, _lower_first

_LICENSE = """#
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
"""

_ANNOTATIONS = {"float": "float", "integer": "int", "string": "str", "boolean": "bool"}
_NO_UNIT = {None, "dimensionless", "inapplicable"}

# A single-backtick markdown code span that is not part of an RST ``literal`` or a :role:`target`.
_CODE_SPAN = re.compile(r"(?<![`:])`([^`\n]+)`(?!`)")

_STANDARD_PARAMS = (
    ":param product_of: The entries this value is a product of, as labeled edges.",
    ":param id: The human-readable entry id shared by all revisions; minted by the store when None.",
    ":param immutable_id: The per-revision immutable id; minted by the store when None.",
    ":param last_modified: The optional timezone-aware metadata timestamp.",
)

_STANDARD_FIELDS = (
    '    product_of: Annotated[tuple[RunEdge, ...], StrongLink("product_of", reverse="has_product", role="subject")] = ()',
    "    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)",
    "    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)",
    "    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)",
)


def _doc_lines(text: str) -> list[str]:
    """Return a schema description as docstring lines: escaped, dedented, markdown code spans as RST literals.

    :param text: The description.
    :return: Its lines.
    """
    quoted = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    quoted = _CODE_SPAN.sub(r"``\1``", quoted)
    return [line.rstrip() for line in textwrap.dedent(quoted).strip().splitlines()]


def _unit(level: Mapping[str, Any]) -> str | None:
    """Return the first physical unit declared along a member's list levels and leaf.

    :param level: The member's definition level.
    :return: The unit, or ``None`` when every level is dimensionless or inapplicable.
    """
    while True:
        unit = level.get("x-optimade-unit")
        if unit not in _NO_UNIT:
            return str(unit)
        if level.get("x-optimade-type") != "list":
            return None
        level = level.get("items", {})


def _module_doc_lines(text: str) -> list[str]:
    lines = _doc_lines(text)
    return ['"""' + lines[0] + '"""'] if len(lines) == 1 else ['"""' + lines[0], *lines[1:], '"""']


def _annotation(item: MemberLayout) -> str:
    leaf = _ANNOTATIONS[item.leaf]
    if item.dimensions:
        annotation = f"tuple[{leaf} | None, ...]" if item.element_nullable else f"tuple[{leaf}, ...]"
    else:
        annotation = leaf
    if not item.path:
        return annotation  # A typed record always holds its definition's value.
    if item.nullable or not item.required:
        annotation += " | None"
    return annotation if item.required else annotation + " = None"


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part) + "Record"


def _record_lines(spec: TypedRecordSpec, storage_prefix: str) -> tuple[str, list[str]]:
    """Return the class name and source lines of one typed record class.

    :param spec: The record's spec.
    :param storage_prefix: The storage-name prefix.
    :return: The class name and its lines.
    """
    definition = spec._stored_definition
    document = definition.as_optimade()
    layout = spec.layout
    ordered = [item for item in layout if item.required] + [item for item in layout if not item.required]
    class_name = _class_name(definition.name)
    title = definition.title or definition.name.replace("_", " ").capitalize()
    doc = [f"{title} as a typed record.", "", *_doc_lines(definition.description), ""]
    for item in ordered:
        if item.path:
            level = document["properties"][item.path[0]]
            first = (_doc_lines(level.get("description", "")) or [f"The ``{item.field}`` member."])[0]
        else:  # The class docstring already carries the definition's description.
            level, first = document, f"The {_lower_first(title)} value."
        unit = _unit(level)
        doc.append(f":param {item.field}: {first}" + ("" if unit is None else f" Unit: {unit}."))
    doc.extend(_STANDARD_PARAMS)
    storage_name = f"{storage_prefix}_{definition.name}"
    lines = [
        "@dataclass(frozen=True)",
        f"class {class_name}(TypedRecord):",
        '    """' + doc[0],
        *("    " + line if line else "" for line in doc[1:]),
        '    """',
        "",
        "    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(",
        f'        storage_name="{storage_name}",',
        f'        identity_name="{storage_name}",',
        "    )",
        "    __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(",
        f'        "{spec.definition_id}",',
        f'        "{spec.served_name}",',
        *([f'        "{spec.derivation}",', f'        "{spec.derivation_label}",'] if spec.derivation else []),
        "    )",
        "    __httk_property_definitions__: ClassVar[Mapping[str, PropertyDefinition]] = __httk_typed_record__.definitions()",
        "    __httk_stored_properties__: ClassVar[Mapping[str, StoredPropertyProjection]] = __httk_typed_record__.projections()",
        "",
        *(f"    {item.field}: {_annotation(item)}" for item in ordered),
        *_STANDARD_FIELDS,
    ]
    return class_name, lines


def _spec(definition_id: str, derivation: str | None = None, label: str | None = None) -> TypedRecordSpec:
    """Return the spec of a plain or derived kind, with the served name its definition gives.

    :param definition_id: The (base) property definition IRI.
    :param derivation: The derivation-term IRI of a derived kind.
    :param label: The derivation label of a derived kind.
    :return: The spec.
    """
    if derivation is None:
        return TypedRecordSpec(definition_id, load_property_definition(definition_id).served_form().name)
    probe = TypedRecordSpec(definition_id, "_", derivation, label)
    return TypedRecordSpec(definition_id, probe._stored_definition.served_form().name, derivation, label)


def _kinds_lines(comment: str, declaration: str, entries: list[str]) -> list[str]:
    if not entries:
        return ["", "", comment, declaration + "({})"]
    return ["", "", comment, declaration + "(", "    {", *entries, "    }", ")"]


def generate_typed_records(
    definition_ids: Sequence[str],
    *,
    derived: Sequence[tuple[str, str, str]] = (),
    module_doc: str,
    storage_prefix: str,
    command: str,
) -> str:
    """Return the source of a typed record module for *definition_ids* and *derived* kinds.

    :param definition_ids: The property definition IRIs, one record class each, in output order.
    :param derived: ``(base IRI, derivation-term IRI, derivation label)`` of each statistic kind, one record
        class each, after the plain kinds; listed in ``DERIVED_RECORD_KINDS``.
    :param module_doc: The generated module's docstring.
    :param storage_prefix: The storage-name prefix: a class stores as ``<prefix>_<definition name>``.
    :param command: The regeneration command named in the generated-file banner.
    :return: The module source.
    """
    specs = [_spec(iri) for iri in definition_ids] + [_spec(*item) for item in derived]
    classes: list[tuple[TypedRecordSpec, str]] = []
    body: list[str] = []
    for spec in specs:
        class_name, lines = _record_lines(spec, storage_prefix)
        classes.append((spec, class_name))
        body.extend(["", "", *lines])
    plain = [f'        "{spec.definition_id}": {name},' for spec, name in classes if spec.derivation is None]
    derived_entries = [
        f'        (\n            "{spec.definition_id}",\n            "{spec.derivation}",\n        ): {name},'
        for spec, name in classes
        if spec.derivation is not None
    ]
    tail = _kinds_lines(
        "#: The generated record class of each property definition IRI.",
        "RECORD_KINDS: Mapping[str, type[TypedRecord]] = MappingProxyType",
        plain,
    )
    if derived_entries:
        tail += _kinds_lines(
            "#: The generated record class of each (base definition IRI, derivation-term IRI) statistic.",
            "DERIVED_RECORD_KINDS: Mapping[tuple[str, str], type[TypedRecord]] = MappingProxyType",
            derived_entries,
        )
    lines = [
        _LICENSE.rstrip("\n"),
        f"# Generated by '{command}'. Do not edit directly; edit the definitions and regenerate.",
        "",
        *_module_doc_lines(module_doc),
        "",
        "import datetime",
        "from collections.abc import Mapping",
        "from dataclasses import dataclass, field",
        "from types import MappingProxyType",
        "from typing import Annotated, ClassVar",
        "",
        "from httk.core import (",
        "    IdentitySkip,",
        "    Indexed,",
        "    PropertyDefinition,",
        "    RunEdge,",
        "    StorageInfo,",
        "    StrongLink,",
        "    TypedRecord,",
        "    TypedRecordSpec,",
        "    Unique,",
        ")",
        "from httk.core.storage import StoredPropertyProjection",
        "",
        "__all__ = [",
        *(['    "DERIVED_RECORD_KINDS",'] if derived_entries else []),
        '    "RECORD_KINDS",',
        *sorted(f'    "{class_name}",' for _, class_name in classes),
        "]",
        *body,
        *tail,
        "",
    ]
    return "\n".join(lines)


def check_typed_records(path: Path, source: str) -> bool:
    """Return whether the file at *path* holds exactly *source*.

    :param path: The committed generated module.
    :param source: The freshly generated source.
    :return: ``False`` when the file is missing or differs.
    """
    try:
        return path.read_text(encoding="utf-8") == source
    except FileNotFoundError:
        return False


def _sync(target: Path, source: str, *, check: bool, command: str) -> int:
    """Write *source* to *target*, or with *check* report whether it is current.

    :param target: The generated module path.
    :param source: The freshly generated source.
    :param check: Compare instead of writing.
    :param command: The regeneration command shown on a mismatch.
    :return: The exit status: 0 when written or current, 1 on a mismatch or a missing file.
    """
    if not check:
        target.write_text(source, encoding="utf-8")
        return 0
    if check_typed_records(target, source):
        return 0
    current = target.read_text(encoding="utf-8").splitlines(keepends=True) if target.exists() else []
    diff = difflib.unified_diff(
        current, source.splitlines(keepends=True), fromfile=str(target), tofile=f"generated {target.name}"
    )
    print("".join(diff), file=sys.stderr, end="")
    if not current:
        print(f"{target} is missing.", file=sys.stderr)
    print(f"Regenerate with: {command}", file=sys.stderr)
    return 1


def main(
    argv: Sequence[str],
    *,
    definition_ids: Sequence[str],
    derived: Sequence[tuple[str, str, str]] = (),
    module_doc: str,
    storage_prefix: str,
    target: Path,
    command: str,
) -> int:
    """Regenerate *target*, or with ``--check`` verify that it is current.

    :param argv: The command-line arguments (``[--check]``).
    :param definition_ids: The property definition IRIs to generate records for.
    :param derived: The ``(base IRI, derivation-term IRI, derivation label)`` statistic kinds to generate.
    :param module_doc: The generated module's docstring.
    :param storage_prefix: The storage-name prefix.
    :param target: The generated module path.
    :param command: The regeneration command, named in the banner and on a mismatch.
    :return: The exit status.
    """
    parser = argparse.ArgumentParser(description="Generate typed result record classes")
    parser.add_argument("--check", action="store_true", help="fail when the generated module is missing or stale")
    arguments = parser.parse_args(list(argv))
    source = generate_typed_records(
        definition_ids, derived=derived, module_doc=module_doc, storage_prefix=storage_prefix, command=command
    )
    return _sync(target, source, check=arguments.check, command=command)
