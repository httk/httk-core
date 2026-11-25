"""Stdlib-only import records: what happened while importing one thing into a store.

An :class:`ImportRecord` is the canonical record of one import: where the thing
came from, which importer imported it, the outcome, and every warning, notice
and exception reported on the way, as :class:`ImportReport` children in
emission order. A source holding several things gives one import record per
thing, each with the reports that apply to it.

``ImportRecord`` itself records failures and exclusions only, which embed no
entry, e.g. a failure before the kind of the imported thing is known. A
successful import is recorded by a typed subclass that adds one record-valued
field holding the imported entry and extends ``__post_init__`` to require it
exactly when ``status == "imported"``; it gives its own
:class:`~httk.core.storage.StorageInfo` and registers in the ``imports`` family.

The record carries the internal, unprefixed entry-type name ``imports``; the
provider prefix is applied at the serving edge.
"""

import datetime
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Self

from .curation import _check_text, _check_timestamp
from .files import FileRecord
from .report import _contexts
from .storage import IdentitySkip, Indexed, KeepStored, StorageInfo, Unique

IMPORTS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/imports"
IMPORT_STATUSES = ("imported", "failed", "excluded")


@dataclass(frozen=True)
class ImportReport:
    """One diagnostic reported while importing a thing.

    :param level: The lowercase logging level name, e.g. ``"warning"``.
    :param message: The report message.
    :param context: The :mod:`httk.core.report` context tag, e.g. ``"cif"``, if any.
    :param logger: The name of the logger that emitted the report, if known.
    :raises TypeError: If a field has the wrong type.
    :raises ValueError: If ``level`` is blank, not lowercase or has surrounding whitespace, or ``message`` is blank.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_import_report",
        identity_name="core_import_report",
    )

    level: str
    message: str
    context: str | None = None
    logger: str | None = None

    def __post_init__(self) -> None:
        _check_text(self.level, "level", required=True, stripped=True)
        if self.level != self.level.lower():
            raise ValueError(f"Field 'level' must be lowercase, got {self.level!r}.")
        _check_text(self.message, "message", required=True)
        _check_text(self.context, "context", required=False)
        _check_text(self.logger, "logger", required=False)

    @classmethod
    def from_log_record(cls, record: logging.LogRecord) -> Self:
        """Build a report from a log record, e.g. one collected by :func:`~httk.core.report.collect_reports`.

        The message is reduced to what identifies the diagnostic on any machine:

        - A captured Python warning (logger ``py.warnings``) becomes
          ``"<Category>: <text>"`` from the first line of its formatted text,
          without the ``path:line:`` prefix and the source line; continuation
          lines of a multi-line warning message are dropped.
        - A blank message becomes ``"(empty message)"``, so a silent record does
          not abort the import.
        - An attached exception adds one line ``"<ExceptionType>: <text>"``;
          the traceback is left out, since it holds absolute paths.

        The ``context`` extra becomes one context, several joined with ``", "``,
        or None when there is none.

        :param record: The log record.
        :return: The report.
        """
        message = record.getMessage()
        if record.name == "py.warnings":
            first = message.split("\n", 1)[0]
            match = re.match(r".*?:\d+: (.*)", first)
            message = match.group(1) if match else first
        if not message.strip():
            message = "(empty message)"
        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None:
            message = f"{message}\n{type(exc).__name__}: {exc}"
        context = ", ".join(map(str, _contexts(getattr(record, "context", None))))
        return cls(record.levelname.lower(), message, context or None, record.name)


@dataclass(frozen=True)
class ImportRecord:
    """The record of importing one thing into a store.

    This base class records failures and exclusions only; a successful import
    is recorded by a typed subclass that embeds the imported entry.

    Two imports are one record when source, importer, outcome and reports are
    equal; a new importer version gives a new record. ``imported_at`` and the
    entry metadata are outside content identity and equality. Equality also
    compares the embedded ``source_file``, whose ``url`` and ``name`` are outside
    its identity, so two records with equal content ids compare unequal when the
    file was recorded under another location.

    :param source_uri: Where the thing was imported from, as chosen by the importer:
        a stable path, URL or identifier, not a machine-specific absolute path.
    :param importer: The program that imported the thing, with its version.
    :param status: The outcome: ``"imported"``, ``"failed"`` or ``"excluded"``.
    :param source_item: The item within the source when it holds several, e.g. a CIF data block name.
    :param source_file: The source bytes, if recorded.
    :param reports: The diagnostics, in emission order; any iterable, stored as a tuple.
    :param error: The exception or exclusion text; required unless ``status`` is
        ``"imported"``, and None when it is.
    :param repaired: Whether the importer had to repair the source; only with ``status == "imported"``.
    :param imported_at: When the import was made, a timezone-aware datetime; kept from the first save.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :raises TypeError: If a field has the wrong type.
    :raises ValueError: If a required string is blank, ``source_uri``, ``importer`` or ``source_item``
        has surrounding whitespace, ``status`` is unknown, ``error`` or ``repaired`` disagrees with
        ``status``, a timestamp is naive, or a base ``ImportRecord`` has ``status == "imported"``.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_import",
        identity_name="core_import",
        indexes=(("source_uri",), ("status",), ("importer",)),
    )

    source_uri: str
    importer: str
    status: str
    source_item: str | None = None
    source_file: FileRecord | None = None
    reports: tuple[ImportReport, ...] = ()
    error: str | None = None
    repaired: bool = False
    imported_at: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(default=None, compare=False)
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "imports"

    def __post_init__(self) -> None:
        _check_text(self.source_uri, "source_uri", required=True, stripped=True)
        _check_text(self.importer, "importer", required=True, stripped=True)
        if not isinstance(self.status, str):
            raise TypeError(f"Field 'status' must be a str, got {type(self.status).__name__}.")
        if self.status not in IMPORT_STATUSES:
            raise ValueError(f"Field 'status' must be one of {IMPORT_STATUSES}, got {self.status!r}.")
        _check_text(self.source_item, "source_item", required=False, stripped=True)
        if self.source_file is not None and not isinstance(self.source_file, FileRecord):
            raise TypeError(f"Field 'source_file' must be a FileRecord or None, got {type(self.source_file).__name__}.")
        reports: Any = self.reports
        if isinstance(reports, (str, bytes)) or not isinstance(reports, Iterable):
            raise TypeError(f"Field 'reports' must be an iterable of ImportReport, got {type(reports).__name__}.")
        reports = tuple(reports)
        for report in reports:
            if not isinstance(report, ImportReport):
                raise TypeError(f"Field 'reports' must hold ImportReport values, got {type(report).__name__}.")
        object.__setattr__(self, "reports", reports)
        imported = self.status == "imported"
        _check_text(self.error, "error", required=not imported)
        if imported and self.error is not None:
            raise ValueError("Field 'error' must be None when status is 'imported'.")
        if not isinstance(self.repaired, bool):
            raise TypeError(f"Field 'repaired' must be a bool, got {type(self.repaired).__name__}.")
        if self.repaired and not imported:
            raise ValueError("Field 'repaired' can only be True when status is 'imported'.")
        _check_timestamp(self.imported_at, "imported_at", required=False)
        _check_timestamp(self.last_modified, "last_modified", required=False)
        if imported and type(self) is ImportRecord:
            raise ValueError(
                "A base ImportRecord records failures and exclusions only; record an import"
                " with a typed ImportRecord subclass that embeds the imported entry."
            )


class ImportEntry:
    """Logical entry family for served :class:`ImportRecord` records and their typed subclasses.

    This family is not itself storable; store an ``ImportRecord`` directly.
    """

    type = "imports"
    definition_id = IMPORTS_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("ImportEntry is a logical entry family; store an ImportRecord directly")


__all__ = [
    "IMPORTS_DEFINITION_ID",
    "IMPORT_STATUSES",
    "ImportEntry",
    "ImportRecord",
    "ImportReport",
]
