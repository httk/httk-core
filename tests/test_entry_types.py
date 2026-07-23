"""Tests for the standard-entry-type record dataclasses.

The entry *providers* that serve these dataclasses through the
:class:`~httk.core.EntryProvider` contract now live in the *httk-data* module;
their tests live there. httk-core keeps only the stdlib-only record models.
"""

import pytest

from httk.core import Calculation, File, Reference, known_entry_providers

# --- dataclass create/validation ----------------------------------------------


def test_reference_create_from_dict_and_instance() -> None:
    ref = Reference.create({"title": "T", "doi": "10.1/x", "authors": ({"name": "Ada"},)})
    assert ref.title == "T"
    assert ref.authors == ({"name": "Ada"},)
    assert Reference.create(ref) is ref


def test_create_unknown_key_error_names_it() -> None:
    with pytest.raises(ValueError) as excinfo:
        File.create({"url": "http://x", "bogus": 1})
    assert "bogus" in str(excinfo.value)


def test_calculation_minimal_fields() -> None:
    calc = Calculation.create({"last_modified": "2024-01-01T00:00:00Z"})
    assert calc.immutable_id is None
    assert calc.last_modified == "2024-01-01T00:00:00Z"


# --- registry -----------------------------------------------------------------


def test_core_registers_no_entry_providers() -> None:
    # httk-core defines the registry but ships no concrete providers of its own
    # (the standard-entry-type providers register from httk-data). Assert on
    # core's own contribution only, so this holds regardless of which other
    # httk modules happen to be importable in the test environment.
    from httk.core.register import entry_providers

    for name in known_entry_providers():
        spec = entry_providers.require(name)
        factory = spec.handler if isinstance(spec.handler, str) else getattr(spec.handler, "__module__", "")
        assert not factory.startswith("httk.core"), (
            f"httk-core itself registered entry provider {name!r} ({factory}); core must ship none"
        )
