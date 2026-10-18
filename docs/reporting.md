# Reporting and diagnostics

*httk₂* sends all library diagnostics through one standard-library `logging`
hierarchy rooted at `"httk"`. Library code only calls
`logging.getLogger(__name__)` and never installs handlers. Python's warnings
are routed into the same stream when capture is enabled. Console output, log
files and per-task collection are separate consumers of that one stream.

With no configuration, Python's `lastResort` handler prints `WARNING` and
above to standard error, and info and debug records are silent. Applications
opt in to more:

```python
from pathlib import Path

from httk.core.report import add_report_file, configure_reporting

configure_reporting(level="warning", context_levels={"optimade": "info"}, capture_warnings=True)
add_report_file(Path("httk.log"), level="info", json_logs=True)
```

The report names are not exported from the `httk.core` root `__all__`; import
them from `httk.core.report`.

## Context tags

A record may carry a *context*, one string or a list of strings, that names the
subsystem it concerns. Untagged records are "general":

```python
import logging

from httk.core.report import context_logger

logger = logging.getLogger(__name__)
logger.warning("slow query", extra={"context": "optimade"})

optimade_logger = context_logger(logger, "optimade")
optimade_logger.warning("slow query")
```

## Two-level policy

Every consumer has a general level plus optional per-context levels, held in a
{class}`httk.core.report.ReportFilter`. A record that lists contexts with a
configured level is judged against the lowest of those levels; any other record
uses the general level. A context level higher than the general level
deliberately demotes a noisy context.

## Console and files

{func}`httk.core.report.configure_reporting` installs one console handler
(`level`, `json_logs`, `context_levels`, `capture_warnings`, and `logger`,
default `"httk"`). It replaces the handler from an earlier call, and
`capture_warnings=True` also routes `warnings.warn` through logging.
{func}`httk.core.report.add_report_file` adds a rotating file handler
(default level `"info"`) and returns its path.
{func}`httk.core.report.reset_reporting` removes the handlers installed this way.
Installing a handler turns off the zero-configuration `lastResort` printing for
that logger, which is why an application calls `configure_reporting` itself.

## Collection per task

{func}`httk.core.report.collect_reports` gathers the records of one task, with
the same two-level policy, without printing them:

```python
from httk.core.report import collect_reports

with collect_reports("warning", context_levels={"optimade": "info"}) as collection:
    run_task()

for record in collection.records:
    print(record.levelname, record.getMessage())
```

Collections are scoped with a `ContextVar`, so they nest and stay isolated
between asyncio tasks and threads. Python warnings raised inside the block are
captured as well, and by default previously seen warnings are re-armed so that
each new task sees repeats afresh (`rearm=False` turns that off; re-arming is
process-global, so avoid task switches inside the block when it matters).
{func}`httk.core.report.active_collections` returns the ambient collections,
outermost first, so code that presents results can read them without threading
a collection through call signatures.

*httk-serve* runs every OPTIMADE request inside a collection and merges the
innermost one into the response `meta.warnings`, so library warnings reach the
client without any code in the library depending on the server.
