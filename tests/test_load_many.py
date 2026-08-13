"""Tests for :func:`httk.core.load_many`."""

import multiprocessing
import os
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any

import pytest

from httk.core import load_many
from httk.core import loading as loading_module
from httk.core.register import known_extensions, readers

_LOAD_COUNT = 0
_REUSED_ERROR = RuntimeError("reused failure")


def _many_loader(filename: str, **kwargs: Any) -> dict[str, Any]:
    global _LOAD_COUNT
    _LOAD_COUNT += 1
    if filename == "bad.many":
        raise RuntimeError("dummy failure")
    return {"filename": filename, "kwargs": kwargs}


def _reused_loader(_filename: str, **_kwargs: Any) -> Any:
    raise _REUSED_ERROR


def _crashing_loader(filename: str, **_kwargs: Any) -> dict[str, str]:
    if filename == "crash.crash":
        os._exit(23)
    return {"filename": filename}


@pytest.fixture
def _register_many_reader() -> Iterator[None]:
    global _LOAD_COUNT
    _LOAD_COUNT = 0
    _REUSED_ERROR.__notes__ = []
    readers.register(key=".many", handler=_many_loader, name="load-many-test")
    readers.register(key=".reuse", handler=_reused_loader, name="load-many-reused-test")
    readers.register(key=".crash", handler=_crashing_loader, name="load-many-crash-test")
    try:
        yield
    finally:
        for key in (".many", ".reuse", ".crash"):
            readers._by_key.pop(key, None)


def test_serial_load_many_preserves_order_and_forwards_kwargs(_register_many_reader: None) -> None:
    assert list(load_many(["first.many", "second.many"], processes=1, marker=7)) == [
        ("first.many", {"filename": "first.many", "kwargs": {"marker": 7}}),
        ("second.many", {"filename": "second.many", "kwargs": {"marker": 7}}),
    ]


def test_serial_load_many_error_policies_name_source(_register_many_reader: None) -> None:
    with pytest.raises(RuntimeError, match="dummy failure") as excinfo:
        list(load_many(["bad.many"], processes=1))
    assert "bad.many" in excinfo.value.__notes__[0]

    results = list(load_many(["ok.many", "bad.many"], processes=1, errors="return"))
    assert results[0][0] == "ok.many"
    assert results[1][0] == "bad.many"
    assert isinstance(results[1][1], RuntimeError)


def test_serial_load_many_is_lazy(_register_many_reader: None) -> None:
    results = load_many(["first.many", "second.many"], processes=1)
    assert _LOAD_COUNT == 0
    assert next(results)[0] == "first.many"
    assert _LOAD_COUNT == 1


def test_reused_exception_gets_only_the_first_source_note(_register_many_reader: None) -> None:
    results = list(load_many(["first.reuse", "second.reuse"], processes=1, errors="return"))

    assert results[0][1] is _REUSED_ERROR
    assert results[1][1] is _REUSED_ERROR
    assert _REUSED_ERROR.__notes__ == ["load_many source: 'first.reuse'"]


@pytest.mark.skipif(
    multiprocessing.get_all_start_methods()[0] != "fork",
    reason="runtime reader registration is not inherited by spawn workers",
)
def test_parallel_broken_pool_falls_back_to_serial(_register_many_reader: None) -> None:
    sources = ["crash.crash", "pending.crash", "after.crash"]
    results = list(load_many(sources, processes=2, errors="return"))

    assert [source for source, _result in results] == sources
    assert isinstance(results[0][1], BrokenProcessPool)
    assert results[2] == ("after.crash", {"filename": "after.crash"})


def test_parallel_load_many_close_shuts_down_executor(
    _register_many_reader: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class TrackingExecutor(ProcessPoolExecutor):
        exited = False

        def __exit__(self, *args: object) -> None:
            type(self).exited = True
            super().__exit__(*args)

    monkeypatch.setattr(loading_module, "ProcessPoolExecutor", TrackingExecutor)
    results = load_many(["first.many", "second.many"], processes=2)
    next(results)
    results.close()
    assert TrackingExecutor.exited


@pytest.mark.skipif(not known_extensions(), reason="httk-core has no discoverable reader")
def test_parallel_load_many_smoke_uses_discovered_reader(tmp_path: Any) -> None:
    extension = known_extensions()[0]
    source = tmp_path / f"missing{extension}"
    result = next(load_many([str(source)], processes=2, errors="return"))
    assert result[0] == str(source)
    assert isinstance(result[1], Exception)
