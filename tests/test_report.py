import asyncio
import json
import logging
import warnings
from collections.abc import Iterator
from typing import Any, cast

import pytest

from httk.core import report


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    httk = logging.getLogger("httk")
    py_warnings = logging.getLogger("py.warnings")
    state = [(logger, logger.level, logger.propagate) for logger in (httk, py_warnings)]
    filters = list(warnings.filters)
    showwarning = warnings.showwarning
    capture_scopes = report._capture_scopes
    capture_permanent = report._capture_permanent
    yield
    report.reset_reporting()
    for logger, level, propagate in state:
        logger.setLevel(level)
        logger.propagate = propagate
    cast(Any, warnings.filters)[:] = filters
    logging.captureWarnings(False)
    warnings.showwarning = showwarning
    report._capture_scopes = capture_scopes
    report._capture_permanent = capture_permanent


def test_zero_config_import_installs_no_report_handler() -> None:
    logger = logging.getLogger("httk")
    level = logger.level

    assert not [handler for handler in logger.handlers if getattr(handler, "_httk_report_handler", False)]
    assert logger.level == level


def test_collection_basics() -> None:
    logger = logging.getLogger("httk.tests.collection")
    with report.collect_reports() as collection:
        logger.info("quiet")
        logger.warning("kept")
    logger.warning("outside")

    assert [record.getMessage() for record in collection.records] == ["kept"]


def test_context_two_level_policy() -> None:
    logger = logging.getLogger("httk.tests.context")
    with report.collect_reports(level="warning", context_levels={"optimade": "info"}) as collection:
        logger.info("plain")
        logger.warning("warning")
        logger.info("optimade", extra={"context": "optimade"})
        logger.info("both", extra={"context": ["web", "optimade"]})
        logger.info("web", extra={"context": "web"})
    with report.collect_reports(context_levels={"noisy": "error"}) as demoted:
        logger.warning("noisy", extra={"context": "noisy"})

    assert [record.getMessage() for record in collection.records] == ["warning", "optimade", "both"]
    assert demoted.records == []


def test_collectors_are_isolated_between_asyncio_tasks() -> None:
    logger = logging.getLogger("httk.tests.asyncio")

    async def collect(message: str) -> list[str]:
        with report.collect_reports(level="info", rearm=False) as collection:
            logger.info(message)
            await asyncio.sleep(0)
            logger.info(f"{message}-again")
        return [record.getMessage() for record in collection.records]

    async def run() -> tuple[list[str], list[str]]:
        return await asyncio.gather(collect("left"), collect("right"))

    left, right = asyncio.run(run())

    assert left == ["left", "left-again"]
    assert right == ["right", "right-again"]


def test_nested_collectors_filter_independently() -> None:
    logger = logging.getLogger("httk.tests.nested")
    with report.collect_reports(level="warning") as outer, report.collect_reports(level="info") as inner:
        logger.info("info")
        logger.warning("warning")

    assert [record.getMessage() for record in outer.records] == ["warning"]
    assert [record.getMessage() for record in inner.records] == ["info", "warning"]


def test_collection_lowers_admission_monotonically() -> None:
    logger = logging.getLogger("httk.tests.admission")
    root = logging.getLogger()
    httk = logging.getLogger("httk")
    root_level, httk_level = root.level, httk.level
    root.setLevel(logging.WARNING)
    httk.setLevel(logging.NOTSET)

    with report.collect_reports(level="info") as collection:
        logger.info("info")
    lowered = httk.level
    with report.collect_reports(level="warning"):
        pass

    assert [record.getMessage() for record in collection.records] == ["info"]
    assert lowered == logging.INFO
    assert httk.level == logging.INFO
    root.setLevel(root_level)
    httk.setLevel(httk_level)


def test_warnings_capture_rearm_and_opt_out() -> None:
    original = warnings.showwarning

    def warn_once() -> None:
        warnings.warn("repeat me", UserWarning, stacklevel=1)

    with report.collect_reports() as first:
        warn_once()
        warn_once()
    with report.collect_reports() as second:
        warn_once()
    with report.collect_reports(rearm=False) as third:
        warn_once()

    assert len(first.records) == 1
    assert len(second.records) == 1
    assert third.records == []
    assert warnings.showwarning is original


def test_capture_is_scoped_and_restores_normal_display() -> None:
    original = warnings.showwarning
    displayed: list[str] = []

    def showwarning(message, category, filename, lineno, file=None, line=None) -> None:
        displayed.append(str(message))

    warnings.showwarning = showwarning
    try:
        with report.collect_reports() as collection:
            warnings.warn("collected", UserWarning, stacklevel=1)
        assert len(collection.records) == 1
        assert warnings.showwarning is showwarning

        warnings.warn("displayed", UserWarning, stacklevel=1)
        assert displayed == ["displayed"]
    finally:
        warnings.showwarning = original


def test_capture_reasserted_after_external_showwarning_restoration() -> None:
    original = warnings.showwarning
    report.configure_reporting(capture_warnings=True)
    warnings.showwarning = original  # what a catch_warnings exit does behind logging's back
    with report.collect_reports() as collection:
        warnings.warn("re-captured", UserWarning, stacklevel=1)

    assert len(collection.records) == 1
    assert "re-captured" in collection.records[0].getMessage()
    assert warnings.showwarning is not original


def test_catch_warnings_recorder_resumes_after_collection() -> None:
    with warnings.catch_warnings(record=True) as recorded:
        recorder_showwarning = warnings.showwarning
        with report.collect_reports() as collection:
            warnings.warn("collected", UserWarning, stacklevel=1)
        assert len(collection.records) == 1
        assert warnings.showwarning is recorder_showwarning

        warnings.warn("recorded", UserWarning, stacklevel=1)

    assert [str(item.message) for item in recorded] == ["recorded"]


def test_permanent_capture_survives_collection_exit() -> None:
    report.configure_reporting(capture_warnings=True)
    captured_showwarning = warnings.showwarning

    with report.collect_reports() as collection:
        warnings.warn("permanent", UserWarning, stacklevel=1)

    assert len(collection.records) == 1
    assert warnings.showwarning is captured_showwarning


def test_externally_enabled_capture_survives_collection_exit() -> None:
    logging.captureWarnings(True)
    captured = warnings.showwarning
    with report.collect_reports():
        pass

    assert warnings.showwarning is captured


def test_reconfiguring_during_collection_keeps_admission() -> None:
    logger = logging.getLogger("httk.tests.reconfig")
    with report.collect_reports(level="info") as collection:
        logger.info("before")
        report.configure_reporting(level="warning")
        logger.info("after")

    assert [record.getMessage() for record in collection.records] == ["before", "after"]


def test_lastresort_fallback_defers_to_descendant_handlers(capsys: pytest.CaptureFixture[str]) -> None:
    child = logging.getLogger("httk.tests.descendant")
    with report.collect_reports():
        pass
    child.addHandler(logging.NullHandler())
    try:
        child.warning("handled elsewhere")
        assert "handled elsewhere" not in capsys.readouterr().err
    finally:
        child.handlers.clear()


def test_console_configuration_and_reset_preserve_collector() -> None:
    logger = logging.getLogger("httk")
    isolated_name = "httk.tests.reset"
    report.configure_reporting(logger=isolated_name)
    report.reset_reporting(isolated_name)
    isolated = logging.getLogger(isolated_name)
    assert isolated.level == logging.NOTSET
    assert isolated.propagate

    with report.collect_reports():
        pass
    collector = next(handler for handler in logger.handlers if not getattr(handler, "_httk_report_handler", False))

    report.configure_reporting(level="warning", context_levels={"optimade": "info"})
    marked = [handler for handler in logger.handlers if getattr(handler, "_httk_report_handler", False)]
    assert len(marked) == 1
    assert marked[0].level == logging.INFO
    assert isinstance(marked[0].filters[0], report.ReportFilter)
    report.configure_reporting(level="error")
    assert len([handler for handler in logger.handlers if getattr(handler, "_httk_report_handler", False)]) == 1

    report.reset_reporting()
    assert collector in logger.handlers
    assert not [handler for handler in logger.handlers if getattr(handler, "_httk_report_handler", False)]
    assert logger.propagate


def test_collecting_handler_preserves_last_resort(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    root_handlers = list(root.handlers)
    for handler in root_handlers:
        root.removeHandler(handler)
    try:
        with report.collect_reports():
            pass
        logger = logging.getLogger("httk.tests.lastresort")
        logger.warning("last-resort warning")
        logger.info("last-resort info")
        assert capsys.readouterr().err == "last-resort warning\n"

        report.configure_reporting()
        logger.warning("console warning")
        assert capsys.readouterr().err.count("console warning") == 1
    finally:
        report.reset_reporting()
        for handler in root_handlers:
            root.addHandler(handler)


def test_configured_logger_keeps_its_requested_admission() -> None:
    root = logging.getLogger()
    target = logging.getLogger("httk.tests.c3")
    root_level = root.level
    records: list[logging.LogRecord] = []

    class RecordHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    report.configure_reporting(logger=target.name, level="warning")
    observer = RecordHandler()
    target.addHandler(observer)
    try:
        root.setLevel(logging.ERROR)
        target.warning("still admitted")
        assert [record.getMessage() for record in records] == ["still admitted"]
    finally:
        root.setLevel(root_level)
        target.removeHandler(observer)
        report.reset_reporting(target.name)
        target.setLevel(logging.NOTSET)
        target.propagate = True


def test_report_file_writes_json_with_extra(tmp_path) -> None:
    path = report.add_report_file(tmp_path / "reports.jsonl", json_logs=True)
    logging.getLogger("httk.tests.file").info("saved", extra={"request_id": "abc"})
    report.reset_reporting()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["message"] == "saved"
    assert payload["request_id"] == "abc"


def test_context_logger_merges_contexts_and_extra() -> None:
    logger = logging.getLogger("httk.tests.adapter")
    adapter = report.context_logger(logger, "web", "optimade")
    cast(dict[str, object], adapter.extra)["request_id"] = "adapter"
    with report.collect_reports(level="info") as collection:
        adapter.info("contextual", extra={"context": ["optimade", "user"], "request_id": "call"})

    record = cast(Any, collection.records[0])
    assert record.context == ("web", "optimade", "user")
    assert record.request_id == "call"


def test_context_logger_flattens_foreign_adapter() -> None:
    logger = logging.getLogger("httk.tests.foreign-adapter")
    foreign = logging.LoggerAdapter(logger, {"request_id": "r", "context": "web"})
    adapter = report.context_logger(foreign, "optimade")
    with report.collect_reports(context_levels={"optimade": "info"}) as collection:
        adapter.info("contextual")

    record = cast(Any, collection.records[0])
    assert record.context == ("web", "optimade")
    assert record.request_id == "r"


def test_active_collections_exposes_innermost_last() -> None:
    assert report.active_collections() == ()
    with report.collect_reports() as outer:
        with report.collect_reports() as inner:
            assert report.active_collections() == (outer, inner)
        assert report.active_collections() == (outer,)
    assert report.active_collections() == ()


def test_resolve_level() -> None:
    assert report.resolve_level("InFo") == logging.INFO
    assert report.resolve_level(logging.ERROR) == logging.ERROR
    with pytest.raises(ValueError, match="unknown log level"):
        report.resolve_level("verbose")
