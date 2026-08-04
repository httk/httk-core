"""Tests for registry discovery and lazy core record pointers."""

import subprocess
import sys
from pathlib import Path

import pytest

import httk.core.entry_types
import httk.registry
from httk.core._discover import discover_and_register
from httk.core.register import (
    _entry_records,
    _entry_type_definitions,
    _property_definitions,
    entry_record_info,
    known_cli_commands,
    known_entry_records,
    known_entry_type_definitions,
    load_entry_type_definition,
    register_entry_record,
    register_entry_type_definition,
    register_property_definition,
    resolve_entry_record,
)


def test_discovery_registers_cli_and_core_records() -> None:
    assert {"project", "docs"} <= set(known_cli_commands())
    definition_ids = {
        "core-reference": "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
        "core-file": "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
        "core-calculation": "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    }
    # Subset, not equality: other installed modules legitimately register
    # their own records into the same registry.
    assert set(definition_ids) <= set(known_entry_records())
    assert {name: entry_record_info(name)[2] for name in definition_ids} == definition_ids
    assert entry_record_info("core-reference") == (
        "httk.core.entry_types:Reference",
        None,
        definition_ids["core-reference"],
    )
    assert resolve_entry_record("core-reference") is httk.core.entry_types.Reference
    assert {
        "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
        "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
        "https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    } <= set(known_entry_type_definitions())


def test_discovery_walks_io_and_not_flat_registry_tiers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    io_package = tmp_path / "io" / "test_discovery_io"
    io_package.mkdir(parents=True)
    io_package.joinpath("__init__.py").write_text(
        "from httk.core.register import register_entry_record\n"
        "register_entry_record(name='test-discovery-io', record='test_module:Record')\n",
        encoding="utf-8",
    )
    flat_package = tmp_path / "test_discovery_flat"
    flat_package.mkdir()
    flat_package.joinpath("__init__.py").write_text(
        "raise AssertionError('flat registry tier was imported')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(httk.registry, "__path__", [str(tmp_path), *httk.registry.__path__])
    try:
        discover_and_register()
        assert "test-discovery-io" in known_entry_records()
        assert "httk.registry.test_discovery_flat" not in sys.modules
    finally:
        _entry_records.pop("test-discovery-io", None)


def test_entry_record_registration_is_strict_and_lazy() -> None:
    name = "test-lazy-entry-record"
    record = "module_that_does_not_exist_for_httk_tests:Record"
    register_entry_record(name=name, record=record)
    try:
        assert entry_record_info(name) == (record, None, None)
        with pytest.raises(ValueError, match="already registered"):
            register_entry_record(name=name, record=record)
        with pytest.raises(ModuleNotFoundError):
            resolve_entry_record(name)
    finally:
        _entry_records.pop(name, None)


def test_unknown_entry_record_resolution_errors() -> None:
    with pytest.raises(ValueError, match="No entry record registered"):
        resolve_entry_record("does-not-exist")


def test_schema_registration_is_strict() -> None:
    definition_id = "https://schemas.example.test/entrytypes/duplicate"
    resource = "httk.registry.schemas.core:files.json"
    register_entry_type_definition(definition_id=definition_id, resource=resource)
    try:
        with pytest.raises(ValueError, match="already registered"):
            register_entry_type_definition(definition_id=definition_id, resource=resource)
    finally:
        _entry_type_definitions.pop(definition_id, None)


def test_property_registration_is_strict() -> None:
    definition_id = "https://schemas.example.test/properties/duplicate"
    resource = "httk.registry.schemas.core:files.json"
    register_property_definition(definition_id=definition_id, resource=resource)
    try:
        with pytest.raises(ValueError, match="already registered"):
            register_property_definition(definition_id=definition_id, resource=resource)
    finally:
        _property_definitions.pop(definition_id, None)


def test_schema_loader_rejects_definition_id_mismatch() -> None:
    registration_id = "https://schemas.example.test/entrytypes/wrong"
    document_id = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"
    register_entry_type_definition(
        definition_id=registration_id,
        resource="httk.registry.schemas.core:files.json",
    )
    try:
        with pytest.raises(ValueError, match=f"{registration_id}.*{document_id}"):
            load_entry_type_definition(registration_id)
    finally:
        _entry_type_definitions.pop(registration_id, None)


def test_discovery_does_not_import_domain_modules() -> None:
    # The real import-weight property: importing httk.core runs discovery over
    # every installed registration shim, and none of that may pull a domain
    # module. Registration is lazy strings; domains load only on resolution.
    code = """
import sys
import httk.core
heavy = [name for name in sys.modules
         if name.startswith(('httk.atomistic', 'httk.data', 'httk.io', 'httk.serve', 'httk.workflow'))]
assert not heavy, f'discovery imported domain modules: {heavy}'
"""
    subprocess.run([sys.executable, "-c", code], check=True)
