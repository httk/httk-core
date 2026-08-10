"""Focused checks that exact vector views defer backend conversion."""

from typing import Any

import pytest

from httk.core import coerce, coerce_view
from httk.core.vectors import (
    FracVector,
    SurdVector,
    VectorFracBackend,
    VectorFracView,
    VectorNativeBackend,
    VectorSurdBackend,
    VectorSurdView,
)
from httk.core.views import unwrap


class CountingVectorFrac(VectorFracBackend):
    def __init__(self, obj: FracVector, **hints: Any) -> None:
        super().__init__(obj, **hints)
        self.fractions_calls = 0
        self.unwrap_calls = 0

    @property
    def fractions(self):
        self.fractions_calls += 1
        return super().fractions

    def unwrap(self) -> Any:
        self.unwrap_calls += 1
        return super().unwrap()


class CountingVectorNative(VectorNativeBackend):
    def __init__(self, obj: Any, **hints: Any) -> None:
        super().__init__(obj, **hints)
        self.fractions_calls = 0

    @property
    def fractions(self):
        self.fractions_calls += 1
        return super().fractions


class CountingVectorSurd(VectorSurdBackend):
    def __init__(self, obj: SurdVector, **hints: Any) -> None:
        super().__init__(obj, **hints)
        self.unwrap_calls = 0

    def unwrap(self) -> Any:
        self.unwrap_calls += 1
        return super().unwrap()


def test_frac_view_construction_is_lazy_and_unwrap_does_not_materialize() -> None:
    raw = FracVector([[1, 2], [3, 4]])
    backend = CountingVectorFrac(raw)
    view = VectorFracView(backend)

    assert backend.fractions_calls == 0
    assert "noms" not in view.__dict__
    assert unwrap(view) is raw
    assert backend.fractions_calls == 0


def test_frac_view_presentation_state_is_filled_once() -> None:
    backend = CountingVectorNative([1, 2, 3])
    view = VectorFracView(backend)

    _ = view.noms
    _ = view.denom
    _ = view[0]
    _ = view.dim

    assert backend.fractions_calls == 1


def test_frac_view_adopts_frac_backend_without_fractions_roundtrip() -> None:
    raw = FracVector([[1, "2/3"], [3, 4]])
    backend = CountingVectorFrac(raw)
    view = VectorFracView(backend)

    assert backend.unwrap_calls == 0
    _ = view.noms
    _ = view.denom
    assert backend.fractions_calls == 0
    assert backend.unwrap_calls == 1
    assert view == raw


def test_frac_view_hash_and_equality_materialize_correctly() -> None:
    raw = [[1, "2/3", 3]]
    expected = FracVector(raw)

    hashed = VectorFracView(CountingVectorFrac(expected))
    assert hash(hashed) == hash(FracVector(raw))

    equal = VectorFracView(CountingVectorFrac(expected))
    assert equal == expected


def test_surd_view_construction_and_materialization_are_lazy() -> None:
    backend = CountingVectorFrac(FracVector([1, 2, 3]))
    view = VectorSurdView(backend)

    assert backend.fractions_calls == 0
    assert "_components" not in view.__dict__
    assert unwrap(view) is backend.unwrap()
    assert backend.fractions_calls == 0

    _ = view._components
    _ = view._dim
    _ = view.dim
    assert backend.fractions_calls == 1


def test_surd_view_adopts_surd_backend_lazily() -> None:
    raw = SurdVector.sqrt_of(2)
    backend = CountingVectorSurd(raw)
    view = VectorSurdView(backend)

    assert backend.unwrap_calls == 0
    assert "_components" not in view.__dict__
    assert unwrap(view) is raw
    assert backend.unwrap_calls == 1


def test_frac_view_low_level_results_remain_backendless() -> None:
    view = VectorFracView.from_noms_and_denom((1, 2), 2)
    result = view + view

    assert result == FracVector.from_noms_and_denom((1, 2), 1)
    assert unwrap(result) is result


def test_fracvector_create_accepts_frac_view() -> None:
    raw = [[1, "2/3"], [3, 4]]

    assert FracVector(VectorFracView(raw)) == FracVector(raw)


def test_coerce_falls_through_deferred_view_data_errors() -> None:
    with pytest.raises(TypeError):
        coerce_view(["not-a-number"], FracVector)
    with pytest.raises(TypeError):
        coerce(["not-a-number"], FracVector)


def test_coerce_view_materializes_successful_lazy_view() -> None:
    result = coerce_view(["1/3"], FracVector)

    assert isinstance(result, VectorFracView)
    assert {"noms", "denom", "_dim"} <= result.__dict__.keys()

    # The strict verb sheds the materialized view to a plain FracVector.
    plain = coerce(["1/3"], FracVector)
    assert type(plain) is FracVector
