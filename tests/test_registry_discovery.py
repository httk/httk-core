"""Tests for registry discovery and lazy core record pointers."""

import subprocess
import sys

import pytest

import httk.core.entry_types
from httk.core import (
    entry_record_info,
    known_cli_commands,
    known_entry_records,
    register_entry_record,
    resolve_entry_record,
)
from httk.core.register import _entry_records


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
    assert {name: entry_record_info(name)[1] for name in definition_ids} == definition_ids
    assert entry_record_info("core-reference") == (
        "httk.core.entry_types:Reference",
        definition_ids["core-reference"],
    )
    assert resolve_entry_record("core-reference") is httk.core.entry_types.Reference


def test_entry_record_registration_is_strict_and_lazy() -> None:
    name = "test-lazy-entry-record"
    record = "module_that_does_not_exist_for_httk_tests:Record"
    register_entry_record(name=name, record=record)
    try:
        assert entry_record_info(name) == (record, None)
        with pytest.raises(ValueError, match="already registered"):
            register_entry_record(name=name, record=record)
        with pytest.raises(ModuleNotFoundError):
            resolve_entry_record(name)
    finally:
        _entry_records.pop(name, None)


def test_unknown_entry_record_resolution_errors() -> None:
    with pytest.raises(ValueError, match="No entry record registered"):
        resolve_entry_record("does-not-exist")


def test_discovery_does_not_import_domain_modules() -> None:
    # The real import-weight property: importing httk.core runs discovery over
    # every installed registration shim, and none of that may pull a domain
    # module. Registration is lazy strings; domains load only on resolution.
    code = """
import sys
import httk.core
heavy = [name for name in sys.modules
         if name.startswith(('httk.atomistic', 'httk.data', 'httk.io', 'httk.optimade', 'httk.workflow'))]
assert not heavy, f'discovery imported domain modules: {heavy}'
"""
    subprocess.run([sys.executable, "-c", code], check=True)
