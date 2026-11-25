"""Tests for the import records."""

import datetime
import logging
import warnings
from dataclasses import dataclass, fields, replace
from typing import Any, ClassVar, cast

import pytest

from httk.core import (
    STANDARD_LINKS,
    FileRecord,
    ImportEntry,
    ImportRecord,
    ImportReport,
    load_entry_type_definition,
    standard_links,
)
from httk.core.import_records import IMPORT_STATUSES, IMPORTS_DEFINITION_ID
from httk.core.register import entry_record_info, known_entry_records, resolve_entry_family, resolve_entry_record
from httk.core.report import collect_reports, context_logger
from httk.core.storage import StorageInfo, content_id

_DATE = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=datetime.UTC)
_METADATA: dict[str, Any] = {
    "id": "logical",
    "immutable_id": "immutable",
    "last_modified": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
    "imported_at": _DATE,
}
_REPORTS = (
    ImportReport("warning", "Dropped an auxiliary loop.", "cif", "httk.atomistic.io.cif"),
    ImportReport("info", "Inferred symbols from labels."),
)
_FILE = FileRecord("https://example.org/1000000.cif", "1000000.cif", sha256="0" * 64)


@dataclass(frozen=True)
class _Payload:
    value: int


@dataclass(frozen=True)
class _PayloadImportRecord(ImportRecord):
    # A typed subclass: one record-valued field, present exactly when imported.
    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="test_payload_import", identity_name="test_payload_import"
    )

    payload: _Payload | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if (self.payload is not None) != (self.status == "imported"):
            raise ValueError("Field 'payload' must be set exactly when status is 'imported'.")


def _imported(**changes: Any) -> _PayloadImportRecord:
    record = _PayloadImportRecord(
        "cif/1/00/00/1000000.cif",
        "build-cod 1.0",
        "imported",
        source_file=_FILE,
        reports=_REPORTS,
        repaired=True,
        payload=_Payload(1),
    )
    return replace(record, **changes)


def _failed() -> ImportRecord:
    return ImportRecord("cif/1/00/00/1000001.cif", "build-cod 1.0", "failed", error="ValueError: no cell")


def test_records_construct() -> None:
    record = _imported()
    assert (record.type, record.status, record.repaired, record.error) == ("imports", "imported", True, None)
    assert record.reports == _REPORTS
    assert ImportRecord("x", "i", "excluded", error="duplicate").source_file is None
    listed = ImportRecord("x", "i", "failed", reports=cast(Any, list(_REPORTS)), error="e")
    assert type(listed.reports) is tuple
    assert listed.reports == _REPORTS
    assert IMPORT_STATUSES == ("imported", "failed", "excluded")


@pytest.mark.parametrize(
    ("build", "error"),
    [
        (lambda: ImportReport(cast(Any, None), "m"), TypeError),
        (lambda: ImportReport("", "m"), ValueError),
        (lambda: ImportReport(" warning", "m"), ValueError),
        (lambda: ImportReport("warning", cast(Any, 1)), TypeError),
        (lambda: ImportReport("warning", " "), ValueError),
        (lambda: ImportReport("warning", "m", cast(Any, ("cif",))), TypeError),
        (lambda: ImportReport("warning", "m", logger=cast(Any, 1)), TypeError),
        (lambda: ImportReport("Warning", "m"), ValueError),
        (lambda: ImportRecord(cast(Any, None), "i", "failed", error="e"), TypeError),
        (lambda: ImportRecord("", "i", "failed", error="e"), ValueError),
        (lambda: ImportRecord(" x", "i", "failed", error="e"), ValueError),
        (lambda: ImportRecord("x", cast(Any, 1), "failed", error="e"), TypeError),
        (lambda: ImportRecord("x", " ", "failed", error="e"), ValueError),
        (lambda: ImportRecord("x", "i 1.0 ", "failed", error="e"), ValueError),
        (lambda: ImportRecord("x", "i", cast(Any, None)), TypeError),
        (lambda: ImportRecord("x", "i", "skipped", error="e"), ValueError),
        (lambda: ImportRecord("x", "i", "failed", source_item=cast(Any, 1), error="e"), TypeError),
        (lambda: ImportRecord("x", "i", "failed", source_item=" block", error="e"), ValueError),
        (lambda: ImportRecord("x", "i", "failed", source_file=cast(Any, "1000000.cif"), error="e"), TypeError),
        (lambda: ImportRecord("x", "i", "failed", reports=cast(Any, None), error="e"), TypeError),
        (lambda: ImportRecord("x", "i", "failed", reports=cast(Any, "warning"), error="e"), TypeError),
        (lambda: ImportRecord("x", "i", "failed", reports=cast(Any, [("warning", "m")]), error="e"), TypeError),
        (lambda: _imported(error="e"), ValueError),
        (lambda: ImportRecord("x", "i", "failed"), TypeError),
        (lambda: ImportRecord("x", "i", "excluded", error=""), ValueError),
        (lambda: ImportRecord("x", "i", "failed", error=cast(Any, 1)), TypeError),
        (lambda: _imported(repaired=cast(Any, 1)), TypeError),
        (lambda: ImportRecord("x", "i", "failed", error="e", repaired=True), ValueError),
        (lambda: ImportRecord("x", "i", "excluded", error="e", repaired=True), ValueError),
        (lambda: _imported(imported_at=_DATE.replace(tzinfo=None)), ValueError),
        (lambda: _imported(imported_at=cast(Any, "2026-11-25")), TypeError),
        (lambda: _imported(last_modified=_DATE.replace(tzinfo=None)), ValueError),
    ],
)
def test_records_reject_bad_values(build: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        build()


def test_report_from_log_record() -> None:
    logger = logging.getLogger("httk.test.import_records")
    with collect_reports("info") as collection:
        logger.warning("Dropped %d loops.", 2, extra={"context": "cif"})
        logger.info("No context.")
    with_context, without = (ImportReport.from_log_record(record) for record in collection.records)
    assert with_context == ImportReport("warning", "Dropped 2 loops.", "cif", "httk.test.import_records")
    assert without == ImportReport("info", "No context.", None, "httk.test.import_records")


def test_report_from_log_record_normalizes_messages_and_contexts() -> None:
    logger = logging.getLogger("httk.test.import_records")
    with collect_reports("info") as collection:
        context_logger(logger, "cif").warning("One context.")
        context_logger(logger, "cif", "symmetry").warning("Two contexts.")
        context_logger(logger).warning("No contexts.")
        logger.warning("")
        try:
            raise ValueError("bad cell")
        except ValueError:
            logger.exception("Import failed.")
        warnings.warn("Odd cell.", UserWarning, stacklevel=1)
    reports = [ImportReport.from_log_record(record) for record in collection.records]
    assert [(report.message, report.context) for report in reports] == [
        ("One context.", "cif"),
        ("Two contexts.", "cif, symmetry"),
        ("No contexts.", None),
        ("(empty message)", None),
        ("Import failed.\nValueError: bad cell", None),
        ("UserWarning: Odd cell.", None),
    ]
    assert reports[-1].logger == "py.warnings"
    assert reports[-1].level == "warning"


def test_base_record_refuses_imported_status() -> None:
    with pytest.raises(ValueError, match="typed ImportRecord subclass"):
        ImportRecord("x", "i", "imported")
    assert _imported().status == "imported"


def test_imported_at_keeps_first_non_null_on_resave() -> None:
    pytest.importorskip("httk.store.backend.sql")
    from httk.store import EntryIdScheme
    from httk.store.backend.sql import Backend, SqlStore

    later = _DATE + datetime.timedelta(days=1)
    with Backend.sqlite() as db:
        store = SqlStore(db, entry_records={ImportEntry: ImportRecord}, entry_ids=EntryIdScheme("httk.test", "1"))
        sids = {store.save(replace(_failed(), imported_at=stamp)) for stamp in (None, _DATE, later)}
        assert len(sids) == 1
        assert store.fetch(ImportRecord, sids.pop(), eager=True).imported_at == _DATE


def test_content_identity_golden_pins() -> None:
    # A changed value means a storage-identity break.
    pins = {
        _REPORTS[0]: "d05f0afbc6b8553b30ed023ae3d53f6f87c4d0920909ea6d5ae19789d3fdc773",
        _imported(): "1e5f82845514a4f6f697e006ab2f3be5785ba500b501e758528ce2fa3160f1a4",
        _failed(): "770a0eded60da5c3a27722131f5a1811f4813fc15da4bff729f72e5fadd432ad",
    }
    for record, pin in pins.items():
        assert content_id(record) == pin
        if isinstance(record, ImportRecord):
            with_metadata = replace(record, **_METADATA)
            assert with_metadata == record
            assert content_id(with_metadata) == pin


@pytest.mark.parametrize(
    "changes",
    [
        {"source_uri": "cif/other.cif"},
        {"importer": "build-cod 1.1"},
        {"source_item": "block"},
        {"source_file": None},
        {"source_file": replace(_FILE, sha256="1" * 64)},
        {"reports": _REPORTS[::-1]},
        {"reports": _REPORTS[:1]},
        {"repaired": False},
        {"status": "failed", "error": "e", "repaired": False, "payload": None},
    ],
)
def test_content_identity_covers_identity_fields(changes: dict[str, Any]) -> None:
    changed = _imported(**changes)
    assert changed != _imported()
    assert content_id(changed) != content_id(_imported())


def test_failed_identity_covers_error() -> None:
    assert content_id(replace(_failed(), error="other")) != content_id(_failed())


def test_subclass_extends_validation() -> None:
    typed = _PayloadImportRecord("x", "i", "imported", reports=cast(Any, list(_REPORTS)), payload=_Payload(1))
    assert typed.reports == _REPORTS
    assert typed.type == "imports"
    assert _PayloadImportRecord("x", "i", "failed", error="e").payload is None
    with pytest.raises(ValueError, match="payload"):
        _PayloadImportRecord("x", "i", "imported")
    with pytest.raises(ValueError, match="payload"):
        _PayloadImportRecord("x", "i", "failed", error="e", payload=_Payload(1))
    with pytest.raises(ValueError, match="error"):
        _PayloadImportRecord("x", "i", "failed", payload=_Payload(1), error="")
    base = ImportRecord("x", "i", "failed", error="e")
    assert content_id(_PayloadImportRecord("x", "i", "failed", error="e")) != content_id(base)
    assert content_id(typed) != content_id(replace(typed, payload=_Payload(2)))
    assert standard_links(_PayloadImportRecord) == STANDARD_LINKS


def test_standard_links() -> None:
    assert standard_links(ImportRecord) == STANDARD_LINKS
    assert standard_links(ImportReport) == ()


def test_definition_and_registration() -> None:
    with pytest.raises(TypeError, match="logical entry family"):
        ImportEntry()
    definition = load_entry_type_definition(IMPORTS_DEFINITION_ID)
    assert definition.name == ImportEntry.type == _imported().type == "imports"
    assert resolve_entry_family("imports") is ImportEntry
    assert ImportEntry.definition_id == IMPORTS_DEFINITION_ID
    assert "core-import" in known_entry_records(family="imports")
    assert resolve_entry_record("core-import") is ImportRecord
    assert entry_record_info("core-import")[1:] == ("imports", IMPORTS_DEFINITION_ID)
    # Every field is a served property except ``source_file``, a forward relationship to ``files``.
    served = {item.name for item in fields(ImportRecord)} - {"source_file"} | {"type"}
    assert set(definition.properties) == served
    assert definition.properties["status"].definition_id.endswith("/properties/imports/status")
