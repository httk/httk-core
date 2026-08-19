"""Generate the stdlib-only core entry record models from registered schemas."""

import difflib
import sys
import textwrap
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .cli import CLIContext
from .property_definitions import EntryTypeDefinition, PropertyDefinition
from .register.schemas import load_entry_type_definition

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

_SCHEMAS = (
    (
        "Reference",
        "references",
        "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
    ),
    (
        "File",
        "files",
        "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
    ),
    (
        "Calculation",
        "calculations",
        "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    ),
)


def _fulltype(document: Mapping[str, Any]) -> str:
    kind = document["x-optimade-type"]
    if kind == "list":
        return "list of " + _fulltype(document["items"])
    if kind == "dictionary":
        return "dict"
    return str(kind)


def type_annotation_for_fulltype(fulltype: str) -> str:
    """Return the generated Python annotation for a schema fulltype."""
    if fulltype == "string":
        return "str"
    if fulltype == "integer":
        return "int"
    if fulltype == "boolean":
        return "bool"
    if fulltype == "float":
        return "float"
    if fulltype == "timestamp":
        return "datetime.datetime"
    if fulltype == "dict":
        return "Mapping[str, Any]"
    if fulltype.startswith("list of "):
        return f"tuple[{type_annotation_for_fulltype(fulltype[8:])}, ...]"
    raise ValueError(f"Unsupported schema fulltype: {fulltype!r}")


def _type_annotation(property_definition: PropertyDefinition) -> str:
    document = property_definition.as_optimade()
    fulltype = _fulltype(document)
    if fulltype == "dict":
        properties = document.get("properties")
        if (
            isinstance(properties, Mapping)
            and properties
            and all(isinstance(value, Mapping) for value in properties.values())
        ):
            value_types = {_fulltype(value) for value in properties.values()}
            if len(value_types) == 1:
                return f"Mapping[str, {type_annotation_for_fulltype(value_types.pop())}]"
    return type_annotation_for_fulltype(fulltype)


def _source_entry_types_path() -> Path:
    core = Path(__file__).resolve().parent
    if core.name != "core" or core.parent.name != "httk" or core.parent.parent.name != "src":
        raise RuntimeError(
            "httk registry gen/check core requires httk.core to be loaded from a source checkout under src/httk/core"
        )
    repo_root = core.parents[2]
    pyproject = repo_root / "pyproject.toml"
    try:
        with pyproject.open("rb") as stream:
            project = tomllib.load(stream).get("project")
            project_name = project.get("name") if isinstance(project, Mapping) else None
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError("httk registry gen/check core requires a valid httk-core pyproject.toml") from exc
    if project_name != "httk-core":
        raise RuntimeError("httk registry gen/check core requires the httk-core source checkout")
    target = (core / "entry_types.py").resolve()
    try:
        target.relative_to(repo_root)
    except ValueError as exc:
        raise RuntimeError(
            "httk registry gen/check core refuses an entry_types.py target outside the source checkout"
        ) from exc
    return target


def _quote_doc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _class_doc(definition: EntryTypeDefinition) -> str:
    lines = [
        f"The ``{definition.name}`` entry type.",
        "",
        *textwrap.dedent(_quote_doc(definition.description)).strip().splitlines(),
        "",
        "Schema properties:",
        "",
    ]
    for name, prop in definition.properties.items():
        if name in {"id", "type"}:
            continue
        # Schema descriptions stay verbatim; only source indentation is normalized for RST.
        description = textwrap.dedent(_quote_doc(prop.description)).strip().splitlines() or [""]
        lines.append(f":ivar {name}: {description[0]}")
        lines.extend("    " + line if line else "" for line in description[1:])
        lines.append("")
    return "\n".join(lines)


def _field_lines(definition: EntryTypeDefinition) -> tuple[list[str], tuple[str, ...]]:
    properties = list(definition.properties.items())
    properties = [item for item in properties if item[0] not in {"id", "type"}]
    fields = [item for item in properties if not item[1].nullable] + [item for item in properties if item[1].nullable]
    timestamp_fields = tuple(name for name, prop in fields if prop.optimade_type == "timestamp")
    lines = []
    for name, prop in fields:
        annotation = _type_annotation(prop)
        default = "" if not prop.nullable else " | None = None"
        lines.append(f"    {name}: {annotation}{default}")
    return lines, timestamp_fields


def _record_lines(class_name: str, definition: EntryTypeDefinition) -> tuple[list[str], tuple[str, ...]]:
    fields, timestamp_fields = _field_lines(definition)
    doc_lines = _class_doc(definition).splitlines()
    doc = ["    " + line if line else "" for line in doc_lines[1:]]
    lines = [
        "@dataclass(frozen=True)",
        f"class {class_name}:",
        '    """' + doc_lines[0],
        *doc,
        '    """',
        "",
        *fields,
        "",
    ]
    lines.extend(
        [
            "    def __post_init__(self) -> None:",
            f"        _validate_timestamps(self, _{class_name.upper()}_TIMESTAMP_FIELDS)",
            "",
            "    @classmethod",
            f'    def from_obj(cls, obj: "{class_name} | Mapping[str, Any]") -> Self:',
            "        return _create(cls, obj)",
            "",
        ]
    )
    return lines, timestamp_fields


def generate_core_records() -> str:
    """Return the complete generated ``entry_types.py`` source."""
    records = [(class_name, load_entry_type_definition(iri)) for class_name, _, iri in _SCHEMAS]
    lines = [
        _LICENSE.rstrip("\n"),
        "# Generated by 'httk registry gen core'. Do not edit directly; edit the schemas and regenerate.",
        "",
        '"""Generated data models for httk-core standard OPTIMADE entry types.',
        "",
        "The record classes below are generated from the registered ``references``,",
        "``files``, and ``calculations`` entry-type schemas.",
        '"""',
        "",
        "import datetime",
        "from collections.abc import Mapping",
        "from dataclasses import dataclass, fields",
        "from typing import Any, Self",
        "",
        "",
    ]
    timestamp_sets: list[tuple[str, ...]] = []
    for index, (class_name, definition) in enumerate(records):
        record, timestamp_fields = _record_lines(class_name, definition)
        lines.extend(record)
        timestamp_sets.append(timestamp_fields)
        if index != len(records) - 1:
            lines.append("")

    all_timestamp_fields = tuple(dict.fromkeys(field for fields_ in timestamp_sets for field in fields_))
    lines.extend([""])
    for (class_name, _), timestamp_fields in zip(records, timestamp_sets):
        values = ", ".join(f'"{field}"' for field in timestamp_fields)
        if len(timestamp_fields) == 1:
            values += ","
        lines.append(f"_{class_name.upper()}_TIMESTAMP_FIELDS = ({values})")
    all_values = ", ".join(f'"{field}"' for field in all_timestamp_fields)
    lines.extend(
        [
            "_TIMESTAMP_FIELDS = frozenset(",
            f"    {{{all_values}}}",
            ")",
            "",
            "",
            "def _validate_timestamp(value: Any, field: str) -> None:",
            "    if value is not None and (not isinstance(value, datetime.datetime) or value.utcoffset() is None):",
            '        raise ValueError(f"Field \'{field}\' must be a timezone-aware datetime with an explicit offset.")',
            "",
            "",
            "def _validate_timestamps(obj: Any, timestamp_fields: tuple[str, ...]) -> None:",
            "    for field in timestamp_fields:",
            "        _validate_timestamp(getattr(obj, field), field)",
            "",
            "",
            "def _create(cls: type[Any], obj: Any) -> Any:",
            '    """Coerce ``obj`` (an instance or a plain mapping) into ``cls``."""',
            "    if isinstance(obj, cls):",
            "        return obj",
            "    if isinstance(obj, Mapping):",
            "        known = {f.name for f in fields(cls)}",
            "        unknown = [key for key in obj if key not in known]",
            "        if unknown:",
            '            raise ValueError("Unknown field(s) for " + cls.__name__ + ": " + ", ".join(sorted(unknown)) + ".")',
            "        values = dict(obj)",
            "        for field in _TIMESTAMP_FIELDS & known:",
            "            value = values.get(field)",
            "            if isinstance(value, str):",
            "                try:",
            "                    parsed = datetime.datetime.fromisoformat(value)",
            "                except ValueError as exc:",
            '                    raise ValueError(f"Invalid ISO-8601 value for field \'{field}\': {value!r}.") from exc',
            "                _validate_timestamp(parsed, field)",
            "                values[field] = parsed",
            "            elif value is not None:",
            "                _validate_timestamp(value, field)",
            "        return cls(**values)",
            '    raise TypeError("Expected a " + cls.__name__ + " or a mapping, got " + type(obj).__name__ + ".")',
            "",
        ]
    )
    return "\n".join(lines)


def check_core_records() -> bool:
    """Return whether the committed core record module is up to date."""
    return _source_entry_types_path().read_text(encoding="utf-8") == generate_core_records()


def _run(action: str, context: CLIContext) -> int:
    try:
        target = _source_entry_types_path()
        if action == "gen":
            target.write_text(generate_core_records(), encoding="utf-8")
            return 0
        if check_core_records():
            return 0
        current = target.read_text(encoding="utf-8")
        generated = generate_core_records()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"{context.program} registry: {exc}", file=sys.stderr)
        return 1

    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=str(target),
        tofile="generated entry_types.py",
    )
    print("".join(diff), file=sys.stderr, end="")
    print(f"Regenerate with: {context.program} registry gen core", file=sys.stderr)
    return 1


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle ``httk registry gen/check core``."""
    import argparse

    parser = argparse.ArgumentParser(
        prog=f"{context.program} registry", description="Generate and verify registry code"
    )
    parser.add_argument("action", choices=("gen", "check"))
    parser.add_argument("record", choices=("core",))
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    return _run(arguments.action, context)
