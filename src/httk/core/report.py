"""Unified reporting for the ``httk`` logger hierarchy.

Library code reports diagnostics with :func:`logging.getLogger` under
``httk.*``. Console/file handlers and per-task collections are consumers of
that same record stream. Context is supplied at emission sites with
``extra={"context": ...}``, as one string or a list of strings. A general
level and optional per-context levels control each consumer; a context level
can also demote a context by being higher than the general level.

:func:`rearm` lets a new task collect warnings already seen by an earlier
task. With no configuration or collection, importing this module changes no
logging or warnings state. Installing any handler on ``"httk"``, including
the collecting handler, suppresses ``logging.lastResort`` for this hierarchy,
so server processes using :func:`collect_reports` should also call
:func:`configure_reporting` for console output.
"""

import json
import logging
import threading
import warnings
from collections.abc import Mapping, MutableMapping
from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, cast

__all__ = [
    "DEFAULT_BACKUP_COUNT",
    "DEFAULT_LOGGER",
    "DEFAULT_MAXIMUM_BYTES",
    "LOG_LEVELS",
    "JsonFormatter",
    "ReportCollection",
    "ReportFilter",
    "active_collections",
    "add_report_file",
    "collect_reports",
    "configure_reporting",
    "context_logger",
    "rearm",
    "reset_reporting",
    "resolve_level",
]

DEFAULT_LOGGER = "httk"
LOG_LEVELS = ("debug", "info", "warning", "error", "critical")
DEFAULT_MAXIMUM_BYTES = 4 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3

_TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_MARK = "_httk_report_handler"
_STANDARD_MEMBERS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _contexts(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _minimum_level(level: int, context_levels: Mapping[str, int]) -> int:
    return min((level, *context_levels.values()))


class JsonFormatter(logging.Formatter):
    """Render one record as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_MEMBERS or key.startswith("_") or key in payload:
                continue
            payload[key] = value
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def resolve_level(level: str | int) -> int:
    """Return the numeric level for a protocol log-level name."""

    if isinstance(level, int):
        return level
    try:
        return logging.getLevelNamesMapping()[level.upper()]
    except KeyError:
        raise ValueError(f"unknown log level: {level!r}") from None


class ReportFilter(logging.Filter):
    """Accept records at a general or context-specific threshold.

    A context threshold replaces the general threshold for records carrying
    that context, so it can deliberately demote a noisy context by using a
    higher level.
    """

    def __init__(
        self,
        level: str | int = "warning",
        context_levels: Mapping[str, str | int] | None = None,
    ) -> None:
        super().__init__()
        self.level = resolve_level(level)
        self.context_levels = {name: resolve_level(value) for name, value in (context_levels or {}).items()}
        self.minimum_level = _minimum_level(self.level, self.context_levels)

    def filter(self, record: logging.LogRecord) -> bool:
        applicable = [
            self.context_levels[name]
            for name in _contexts(getattr(record, "context", None))
            if name in self.context_levels
        ]
        return record.levelno >= (min(applicable) if applicable else self.level)


class _ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        adapter_extra = self.extra or {}
        extra = dict(adapter_extra)
        call_extra = kwargs.get("extra") or {}
        extra.update(call_extra)
        extra["context"] = tuple(
            dict.fromkeys((*_contexts(adapter_extra.get("context")), *_contexts(call_extra.get("context"))))
        )
        kwargs["extra"] = extra
        return msg, kwargs


def context_logger(logger: logging.Logger | logging.LoggerAdapter, *contexts: str) -> logging.LoggerAdapter:
    """Return an adapter which attaches ``contexts`` to every record.

    Passed adapters are flattened so their ``extra`` values survive logging's
    default adapter processing. Custom adapter :meth:`~logging.LoggerAdapter.process` logic is
    deliberately bypassed.
    """

    extra: dict[str, object] = {"context": contexts}
    while isinstance(logger, logging.LoggerAdapter):
        adapter_extra = logger.extra or {}
        inherited = dict(adapter_extra)
        inherited.update(extra)
        inherited["context"] = tuple(
            dict.fromkeys((*_contexts(adapter_extra.get("context")), *_contexts(extra.get("context"))))
        )
        extra = inherited
        logger = logger.logger
    return _ContextLoggerAdapter(logger, extra)


def _formatter(*, json_logs: bool) -> logging.Formatter:
    return JsonFormatter() if json_logs else logging.Formatter(_TEXT_FORMAT)


def _lower_admission(logger: logging.Logger, level: int) -> None:
    if level < logger.getEffectiveLevel():
        logger.setLevel(level)


def _install(handler: logging.Handler, level: int, logger: str) -> None:
    target = logging.getLogger(logger)
    handler.setLevel(level)
    setattr(handler, _MARK, True)
    target.addHandler(handler)
    target.propagate = False
    if target.level == logging.NOTSET or level < target.level:
        target.setLevel(level)


_capture_scopes = 0
_capture_permanent = False
# True while collection scopes are open if the host had already enabled
# logging.captureWarnings itself; the outermost exit then leaves capture on.
_capture_external = False


def _capture_warnings_cycle() -> None:
    """Enable warning capture after restoring the previously saved display hook."""

    logging.captureWarnings(False)
    logging.captureWarnings(True)


def _enable_warnings_capture() -> None:
    """Keep warning capture enabled for the lifetime of this process.

    This replaces :func:`warnings.showwarning`, so warning display follows the
    logging pipeline; that is intentional for server and CLI processes. The
    off/on cycle repairs warning capture after a :class:`warnings.catch_warnings`
    exit restores ``warnings.showwarning`` behind logging's back.
    """

    global _capture_permanent
    _capture_warnings_cycle()
    _capture_permanent = True


def configure_reporting(
    *,
    level: str | int = "warning",
    json_logs: bool = False,
    context_levels: Mapping[str, str | int] | None = None,
    capture_warnings: bool = False,
    logger: str = DEFAULT_LOGGER,
) -> None:
    """Install one console handler for a reporting logger hierarchy."""

    reset_reporting(logger)
    report_filter = ReportFilter(level, context_levels)
    handler = logging.StreamHandler()
    handler.setFormatter(_formatter(json_logs=json_logs))
    handler.addFilter(report_filter)
    _install(handler, report_filter.minimum_level, logger)
    if capture_warnings:
        _enable_warnings_capture()


def add_report_file(
    path: Path,
    *,
    level: str | int = "info",
    json_logs: bool = False,
    context_levels: Mapping[str, str | int] | None = None,
    maximum_bytes: int = DEFAULT_MAXIMUM_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    logger: str = DEFAULT_LOGGER,
) -> Path:
    """Add one rotating report file handler and return the path it writes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    report_filter = ReportFilter(level, context_levels)
    handler = RotatingFileHandler(path, maxBytes=maximum_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setFormatter(_formatter(json_logs=json_logs))
    handler.addFilter(report_filter)
    _install(handler, report_filter.minimum_level, logger)
    return path


def reset_reporting(logger: str = DEFAULT_LOGGER) -> None:
    """Remove the reporting handlers installed for ``logger``."""

    target = logging.getLogger(logger)
    for handler in list(target.handlers):
        if not getattr(handler, _MARK, False):
            continue
        target.removeHandler(handler)
        handler.close()
    if not target.handlers:
        target.setLevel(logging.NOTSET)
        target.propagate = True
    elif not [handler for handler in target.handlers if handler is not _collecting_handler]:
        # Keep the monotonically lowered level: an active collection may still
        # depend on it for admission.
        target.propagate = True


class ReportCollection:
    """Append-only records accepted by one :func:`collect_reports` block."""

    def __init__(self, report_filter: ReportFilter) -> None:
        self.records: list[logging.LogRecord] = []
        self.filter = report_filter


_collections: ContextVar[tuple[ReportCollection, ...]] = ContextVar("httk_report_collections", default=())


class _CollectingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Only append to lists already stored in the ContextVar: worker paths
        # must never call .set(), so copied task contexts stay isolated.
        collections = _collections.get()
        if not collections:
            # Emulate the callHandlers walk: fall back to lastResort only when
            # this handler is the sole one on the record's propagation chain,
            # preserving zero-config stderr behavior otherwise suppressed by
            # installing this permanent handler.
            chain: logging.Logger | None = logging.getLogger(record.name)
            only_self = True
            while chain is not None:
                if any(handler is not self for handler in chain.handlers):
                    only_self = False
                    break
                chain = chain.parent if chain.propagate else None
            if only_self and logging.lastResort is not None and record.levelno >= logging.lastResort.level:
                logging.lastResort.handle(record)
            return
        for collection in collections:
            if collection.filter.filter(record):
                collection.records.append(record)


_collecting_handler: _CollectingHandler | None = None
_collecting_handler_lock = threading.Lock()


def _install_collecting_handler() -> None:
    global _collecting_handler
    with _collecting_handler_lock:
        if _collecting_handler is not None:
            return
        _collecting_handler = _CollectingHandler(level=logging.NOTSET)
        logging.getLogger(DEFAULT_LOGGER).addHandler(_collecting_handler)
        logging.getLogger("py.warnings").addHandler(_collecting_handler)


class _CollectionContext(AbstractContextManager[ReportCollection]):
    def __init__(self, collection: ReportCollection, rearm_warnings: bool) -> None:
        self.collection = collection
        self.rearm_warnings = rearm_warnings
        self.token: Token[tuple[ReportCollection, ...]] | None = None

    def __enter__(self) -> ReportCollection:
        global _capture_scopes, _capture_external
        # Everything that can fail runs before the capture refcount moves, so a
        # failed __enter__ (whose __exit__ is never called) leaks no state.
        _install_collecting_handler()
        if self.rearm_warnings:
            rearm()
        _lower_admission(logging.getLogger(DEFAULT_LOGGER), self.collection.filter.minimum_level)
        if _capture_scopes == 0:
            _capture_external = getattr(logging, "_warnings_showwarning", None) is not None
            _capture_warnings_cycle()
        _capture_scopes += 1
        self.token = _collections.set(_collections.get() + (self.collection,))
        return self.collection

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        global _capture_scopes
        try:
            if self.token is not None:
                _collections.reset(self.token)
        finally:
            _capture_scopes -= 1
            if _capture_scopes == 0 and not _capture_permanent and not _capture_external:
                logging.captureWarnings(False)


def collect_reports(
    level: str | int = "warning",
    *,
    context_levels: Mapping[str, str | int] | None = None,
    rearm: bool = True,
) -> AbstractContextManager[ReportCollection]:
    """Collect records for the current context until the ``with`` block exits.

    Warning-registry invalidation is process-global. Concurrent collection
    scopes can double-collect or zero-collect repeated warnings, so callers
    should avoid task switches inside the block or pass ``rearm=False``.
    """

    return _CollectionContext(ReportCollection(ReportFilter(level, context_levels)), rearm)


def active_collections() -> tuple[ReportCollection, ...]:
    """Return the :func:`collect_reports` collections active in this context.

    Outermost first; the last entry is the innermost enclosing block. Code that
    presents collected records (for example a server building a response) reads
    them from here instead of threading a collection through call signatures.
    """

    return _collections.get()


class _RearmWarning(Warning):
    pass


def rearm() -> None:
    """Invalidate warning deduplication caches without changing warning policy.

    CPython's ``warnings._filters_mutated`` is the primary mechanism used by
    :class:`warnings.catch_warnings`. Other implementations get an identical
    temporary public filter entry, whose version bump is retained after it is
    removed. This is process-global: overlapping collection scopes in tasks can
    double-collect or zero-collect repeated warnings; avoid task switches in a
    collection block or use ``rearm=False``.
    """

    mutated = getattr(warnings, "_filters_mutated", None)
    if mutated is not None:
        mutated()
        return
    warnings.filterwarnings("ignore", category=_RearmWarning, append=True)
    filters = cast(list[object], warnings.filters)
    filters.remove(filters[-1])
