"""
Tests for the Vector backend/view family: dispatch, kind overrides, view round-trips, unwrap,
and behavior when numpy is absent.
"""

import copy
import fractions
import pathlib
import pickle
import subprocess
import sys
from typing import Any, cast

import pytest

from httk.core.vectors import (
    FracVector,
    SurdVector,
    VectorBackend,
    VectorFrac,
    VectorFracView,
    VectorNative,
    VectorNativeView,
    VectorSurd,
    VectorSurdView,
)
from httk.core.views import unwrap

F = fractions.Fraction

try:
    import numpy

    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    HAS_NUMPY = False

requires_numpy = pytest.mark.skipif(not HAS_NUMPY, reason="numpy is not installed")


# ------------------------------------------------------------------ dispatch


def test_dispatch_list_to_native() -> None:
    backend = VectorBackend.create([[1, 2], [3, 4]])
    assert isinstance(backend, VectorNative)


def test_dispatch_fracvector_to_frac() -> None:
    backend = VectorBackend.create(FracVector([[1, 2], [3, 4]]))
    assert isinstance(backend, VectorFrac)


@requires_numpy
def test_dispatch_ndarray_to_numpy() -> None:
    from httk.core.vectors import VectorNumpy

    backend = VectorBackend.create(numpy.array([[1.0, 2.0], [3.0, 4.0]]))
    assert isinstance(backend, VectorNumpy)


def test_kind_override_forces_native() -> None:
    backend = VectorBackend.create([[1, 2], [3, 4]], kind="native")
    assert isinstance(backend, VectorNative)


def test_kind_mismatch_is_rejected() -> None:
    # A FracVector cannot be interpreted as kind="native".
    with pytest.raises(TypeError):
        VectorBackend.create(FracVector([1, 2, 3]), kind="native")


def test_unrepresentable_raises() -> None:
    with pytest.raises(TypeError):
        VectorBackend.create(object())


# ------------------------------------------------------------------ fractions interchange


def test_backend_fractions_are_exact() -> None:
    backend = VectorBackend.create([["1/3", "2/5"]])
    assert backend.fractions == ((F(1, 3), F(2, 5)),)
    assert backend.dim == (1, 2)


def test_native_string_uncertainty_parsing() -> None:
    # Conversion goes through FracVector, so uncertainty strings parse here too.
    backend = VectorBackend.create(["0.33342(10)"])
    assert backend.fractions == (F(1, 3),)


# ------------------------------------------------------------------ views


def test_frac_view_is_a_fracvector_with_algebra() -> None:
    v = VectorFracView([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    assert isinstance(v, FracVector)
    assert v.det() == -3
    assert v.inv().simplify() == FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]]).inv().simplify()


def test_native_view_preserves_native_leaves_verbatim() -> None:
    # The default native view of natively-held data presents the original leaves verbatim
    # (containers tuple-ized, leaves untouched) — no silent conversion.
    nv = VectorNativeView([[1, 2], [3, 4]])
    assert nv == ((1, 2), (3, 4))
    assert all(isinstance(x, int) for row in nv for x in row)
    # String leaves are presented as-is (NOT Fraction-ized); ask for a codec to convert them.
    string_nv = VectorNativeView([["1/3", "2/3"]])
    assert string_nv == (("1/3", "2/3"),)
    frac_nv = VectorNativeView([["1/3", "2/3"]], leaf="fraction")
    assert frac_nv == ((F(1, 3), F(2, 3)),)
    assert all(isinstance(x, fractions.Fraction) for row in frac_nv for x in row)


def test_native_view_cross_representation_default_is_exact() -> None:
    # Crossing from a frac backend (no native leaves to preserve) uses the exact codec, as before:
    # int when integral, else Fraction, never a float.
    nv = VectorNativeView(FracVector([["1/3", "2/3"], [1, 2]]))
    assert nv == ((F(1, 3), F(2, 3)), (1, 2))
    assert isinstance(nv[0][0], fractions.Fraction)
    assert all(isinstance(x, int) for x in nv[1])


def test_frac_to_native_to_frac_is_exact_identity() -> None:
    src = FracVector([["1/3", "2/5"], ["3/7", "4/9"]])
    roundtrip = VectorFracView(VectorNativeView(VectorFracView(src)))
    assert roundtrip == src


def test_rewrap_identity() -> None:
    fv = VectorFracView([[1, 2], [3, 4]])
    assert VectorFracView(fv) is fv
    nv = VectorNativeView([[1, 2], [3, 4]])
    assert VectorNativeView(nv) is nv


def test_unwrap_returns_raw_objects() -> None:
    raw = [[1, 2], [3, 4]]
    assert unwrap(VectorNative(raw)) is raw
    fv = FracVector([[1, 2], [3, 4]])
    assert unwrap(VectorFrac(fv)) is fv


# ------------------------------------------------------------------ leaf codecs on the native view


def test_native_view_preserves_decimal_object_identity() -> None:
    import decimal

    d = decimal.Decimal("1.5")
    nv = VectorNativeView([[d, 2]])
    assert nv == ((d, 2),)
    assert nv[0][0] is d  # the identical Decimal object, not a copy or conversion
    assert isinstance(nv[0][1], int)


def test_native_view_preserves_mixed_leaves() -> None:
    import decimal

    raw = [[decimal.Decimal("0.5"), F(1, 4), 3, 2.5, "1/3"]]
    nv = VectorNativeView(raw)
    assert nv == ((decimal.Decimal("0.5"), F(1, 4), 3, 2.5, "1/3"),)
    assert [type(x) for x in nv[0]] == [decimal.Decimal, fractions.Fraction, int, float, str]


def test_native_view_leaf_int_rounding_modes() -> None:
    src = FracVector([["5/2", "7/2", "-5/2", "-7/2"]])
    assert VectorNativeView(src, leaf="int") == ((2, 4, -2, -4),)  # nearest, ties to even
    assert VectorNativeView(src, leaf="int", rounding="floor") == ((2, 3, -3, -4),)
    assert VectorNativeView(src, leaf="int", rounding="ceil") == ((3, 4, -2, -3),)
    assert VectorNativeView(src, leaf="int", rounding="trunc") == ((2, 3, -2, -3),)


def test_native_view_leaf_decimal_exact_and_quantized() -> None:
    import decimal

    exact = VectorNativeView(FracVector([["1/8"]]), leaf="decimal")
    assert exact == ((decimal.Decimal("0.125"),),)
    assert isinstance(exact[0][0], decimal.Decimal)
    # 1/3 has no finite decimal expansion: quantized to `digits` significant digits, half-even.
    assert VectorNativeView(FracVector([["1/3"]]), leaf="decimal", digits=6) == ((decimal.Decimal("0.333333"),),)
    assert VectorNativeView(FracVector([["2/3"]]), leaf="decimal", digits=6) == ((decimal.Decimal("0.666667"),),)


def test_native_view_leaf_float_is_lossy() -> None:
    fv = VectorNativeView(FracVector([["1/3"]]), leaf="float")
    assert fv == ((1.0 / 3.0,),)
    assert isinstance(fv[0][0], float)


def test_native_view_unknown_codec_and_bad_options_raise() -> None:
    with pytest.raises(ValueError, match="unknown leaf codec"):
        VectorNativeView([[1]], leaf="nope")
    with pytest.raises(ValueError, match="unknown rounding"):
        VectorNativeView([[1]], leaf="int", rounding="bogus")
    with pytest.raises(ValueError, match="takes no options"):
        VectorNativeView([[1]], leaf="float", digits=3)
    with pytest.raises(ValueError, match="only 'digits' is accepted"):
        VectorNativeView([[1]], leaf="decimal", rounding="floor")


def test_lossy_view_leaves_backend_untouched() -> None:
    # After ANY lossy view, unwrap() returns the identical original and a fresh exact view
    # reproduces the exact values.
    import decimal

    raw = [["1/3", decimal.Decimal("2.5"), 4]]
    backend = VectorNative(raw)
    lossy = VectorNativeView(backend, leaf="int")  # deliberately lossy
    assert lossy == ((0, 2, 4),)  # 1/3 -> 0, 2.5 -> 2 (half-even)
    # The backend's original object is untouched (same identity).
    assert unwrap(backend) is raw
    # A fresh exact view reproduces the exact rational values.
    assert VectorNativeView(backend, leaf="exact") == ((F(1, 3), F(5, 2), 4),)


def test_native_view_leaf_applies_across_backends() -> None:
    # An explicit codec converts from the exact fractions hub regardless of the source backend.
    from_native = VectorNativeView([["1/2"]], leaf="int")
    from_frac = VectorNativeView(FracVector([["1/2"]]), leaf="int")
    assert from_native == ((0,),) == from_frac  # 1/2 -> 0 by half-even


# ------------------------------------------------------------------ surd backend/view


def test_dispatch_surdvector_to_surd() -> None:
    backend = VectorBackend.create(SurdVector.sqrt_of(2))
    assert isinstance(backend, VectorSurd)


def test_surd_unwrap_is_exact() -> None:
    s = SurdVector.sqrt_of(2)
    assert unwrap(VectorSurd(s)) is s


def test_native_to_surd_view_exact_round_trip() -> None:
    # Rationals embed exactly at radicand 1, so native -> surd -> native is exact.
    v = VectorSurdView([["1/3", "2/5"], ["3/7", "4/9"]])
    assert isinstance(v, SurdVector)
    assert v == SurdVector([["1/3", "2/5"], ["3/7", "4/9"]])
    assert v.is_rational


def test_surd_view_of_surd_backend_keeps_exact_value() -> None:
    s = SurdVector.sqrt_of(2)
    backend = VectorSurd(s)
    view = VectorSurdView(backend)
    assert view == s
    assert unwrap(view) is s  # the exact original SurdVector


def test_surd_backend_fractions_hub_rational_is_exact() -> None:
    backend = VectorBackend.create(SurdVector([["1/3", "2/3"]]))
    assert backend.fractions == ((F(1, 3), F(2, 3)),)


def test_surd_backend_fractions_hub_irrational_is_deterministic() -> None:
    # An irrational surd is reduced to a deterministic (lossy) rational approximation.
    backend = VectorBackend.create(SurdVector.from_radicand_map({2: [[1, 2]]}))
    assert backend.fractions == backend.fractions  # same every call
    assert backend.dim == (1, 2)


def test_surd_view_rewrap_identity() -> None:
    v = VectorSurdView([[1, 2], [3, 4]])
    assert VectorSurdView(v) is v


# ------------------------------------------------------------------ numpy views (skipped if absent)


@requires_numpy
def test_numpy_view_is_float64_ndarray() -> None:
    from httk.core.vectors import VectorNumpyView

    arr = VectorNumpyView([[1, 2], [3, 4]])
    assert isinstance(arr, numpy.ndarray)
    assert arr.dtype == numpy.float64
    assert arr.tolist() == [[1.0, 2.0], [3.0, 4.0]]


@requires_numpy
def test_rewrap_numpy_view_identity() -> None:
    from httk.core.vectors import VectorNumpyView

    arr = VectorNumpyView([[1, 2], [3, 4]])
    assert VectorNumpyView(arr) is arr


@requires_numpy
def test_frac_to_numpy_to_frac_is_binary_rational() -> None:
    from httk.core.vectors import VectorNumpyView

    one_third = FracVector([["1/3"]])
    # A detached raw float64 array (as one truly has when handed a numpy array).
    detached = numpy.asarray(VectorNumpyView(one_third))
    lossy = VectorFracView(detached)
    # 1/3 does NOT come back exactly: it is the float64 binary rational.
    assert lossy.simplify() != one_third
    assert lossy.to_fractions() == [[fractions.Fraction(1.0 / 3.0)]]
    # limit_denominator recovers the intended small rational.
    assert lossy.limit_denominator(100).simplify() == one_third


@requires_numpy
def test_numpy_view_default_dtype_unchanged() -> None:
    from httk.core.vectors import VectorNumpyView

    arr = VectorNumpyView([[1, 2], [3, 4]], dtype=None)
    assert arr.dtype == numpy.float64
    assert arr.tolist() == [[1.0, 2.0], [3.0, 4.0]]


@requires_numpy
def test_numpy_view_integer_dtype_exact_and_rounded() -> None:
    from httk.core.vectors import VectorNumpyView

    integral = VectorNumpyView([[1, 2], [3, 4]], dtype=numpy.int64)
    assert integral.dtype == numpy.int64
    assert integral.tolist() == [[1, 2], [3, 4]]
    # Fractional values are rounded through the int codec (nearest, half-even) BEFORE array
    # construction — never silently truncated by numpy. 1/2 -> 0, 3/2 -> 2, 5/2 -> 2, 7/2 -> 4.
    rounded = VectorNumpyView(FracVector([["1/2", "3/2", "5/2", "7/2"]]), dtype=numpy.int64)
    assert rounded.dtype == numpy.int64
    assert rounded.tolist() == [[0, 2, 2, 4]]


@requires_numpy
def test_numpy_view_float32_dtype() -> None:
    from httk.core.vectors import VectorNumpyView

    arr = VectorNumpyView([[1, 2], [3, 4]], dtype=numpy.float32)
    assert arr.dtype == numpy.float32


# --------------------------------------------------------- numpy view adoption and shedding


@requires_numpy
def test_numpy_view_adopts_raw_ndarray_zero_copy() -> None:
    from httk.core import coerce, unview, unwrap
    from httk.core.vectors import VectorNumpyView

    for dtype in (numpy.int64, numpy.float32, numpy.float64, numpy.complex128):
        raw = numpy.arange(6).astype(dtype).reshape(2, 3)
        view = VectorNumpyView(raw)
        assert view.dtype == dtype  # input dtype preserved
        assert numpy.shares_memory(view, raw)
        assert unwrap(view) is raw
        assert unview(view) is raw
        assert coerce(raw, numpy.ndarray) is raw


@requires_numpy
def test_numpy_view_adoption_does_not_scan_elements() -> None:
    from httk.core.vectors import VectorNumpyView

    # Non-rationalizable values (non-finite, complex) adopt fine; only an actual exact-hub
    # conversion fails, and only when requested.
    raw = numpy.array([numpy.nan, numpy.inf, 1.0])
    view = VectorNumpyView(raw)
    assert numpy.shares_memory(view, raw)
    with pytest.raises((ValueError, OverflowError)):
        _ = view._backend.fractions

    complex_raw = numpy.array([1 + 2j])
    complex_view = VectorNumpyView(complex_raw)
    assert numpy.shares_memory(complex_view, complex_raw)
    with pytest.raises((TypeError, ValueError)):
        _ = complex_view._backend.fractions


@requires_numpy
def test_numpy_view_explicit_dtype_change_converts() -> None:
    from httk.core import unwrap
    from httk.core.vectors import VectorNumpyView

    raw = numpy.array([[1.5, 2.5]])
    converted = VectorNumpyView(raw, dtype=numpy.int64)
    assert converted.dtype == numpy.int64
    assert not numpy.shares_memory(converted, raw)
    assert converted.tolist() == [[2, 2]]  # half-even through the int codec
    assert unwrap(converted) is raw  # the original backend is retained

    # A matching explicit dtype still adopts.
    same = VectorNumpyView(raw, dtype=numpy.float64)
    assert numpy.shares_memory(same, raw)


@requires_numpy
def test_numpy_view_rewrap_with_conflicting_dtype_converts() -> None:
    from httk.core import unwrap
    from httk.core.vectors import VectorNumpyView

    raw = numpy.array([[1.0, 2.0]])
    view = VectorNumpyView(raw)
    assert VectorNumpyView(view) is view
    assert VectorNumpyView(view, dtype=numpy.float64) is view
    changed = VectorNumpyView(view, dtype=numpy.float32)
    assert changed is not view
    assert changed.dtype == numpy.float32
    assert unwrap(changed) is raw


@requires_numpy
def test_numpy_view_operations_return_base_arrays() -> None:
    from httk.core.vectors import VectorNumpyView

    view = VectorNumpyView(numpy.arange(4, dtype=numpy.float64).reshape(2, 2))
    assert type(view + 1) is numpy.ndarray  # operator
    assert type(numpy.sin(view)) is numpy.ndarray  # ufunc
    assert type(numpy.concatenate([view, view])) is numpy.ndarray  # dispatched function
    assert type(numpy.linalg.norm(view, axis=1)) is numpy.ndarray  # dispatched function
    assert type(view[0]) is numpy.ndarray  # slicing
    assert type(view[view > 1]) is numpy.ndarray  # boolean mask
    assert not isinstance(view.sum(), VectorNumpyView)  # reduction (numpy scalar)
    assert not isinstance(view.sum(axis=0), VectorNumpyView)
    quotient, remainder = divmod(view, 2)  # multiple outputs
    assert type(quotient) is numpy.ndarray and type(remainder) is numpy.ndarray
    out = numpy.empty_like(view.view(numpy.ndarray))
    result = numpy.add(view, 1, out=out)  # out=
    assert type(result) is numpy.ndarray and numpy.shares_memory(result, out)


@requires_numpy
def test_numpy_view_sheds_where_kwarg_views() -> None:
    from httk.core.vectors import VectorNumpyView

    view = VectorNumpyView(numpy.array([1.0, 2.0]))
    mask_view = numpy.array([True, False]).view(VectorNumpyView)
    out = numpy.zeros(2)
    result = numpy.add(view, 1, where=mask_view, out=out)
    assert type(result) is numpy.ndarray
    assert result.tolist() == [2.0, 0.0]


@requires_numpy
def test_numpy_view_sheds_tuple_subclass_args() -> None:
    from collections import namedtuple

    from httk.core.vectors import VectorNumpyView

    Point = namedtuple("Point", "x y")
    result = numpy.reshape(VectorNumpyView(numpy.arange(4)), Point(1, 4))
    assert type(result) is numpy.ndarray
    assert result.shape == (1, 4)


@requires_numpy
def test_numpy_view_retains_backend_through_copy_round_trips() -> None:
    from httk.core import FracVector, unview, unwrap
    from httk.core.vectors import VectorNumpyView

    exact = FracVector([["1/3", "2/3"]])
    view = VectorNumpyView(exact)
    round_trips = (
        (pickle.loads(pickle.dumps(view)), False),
        (copy.copy(view), True),
        (copy.deepcopy(view), False),
    )
    for result, is_shallow_copy in round_trips:
        backend = unwrap(result)
        assert isinstance(backend, FracVector)
        assert backend == exact
        assert type(unview(result)) is numpy.ndarray
        if is_shallow_copy:
            assert result._backend is view._backend

    derived = view.reshape(1, 2)
    copied_derived = copy.deepcopy(derived)
    assert unwrap(copied_derived) is copied_derived


@requires_numpy
def test_numpy_view_accepts_untagged_ndarray_state() -> None:
    from httk.core import unwrap
    from httk.core.vectors import VectorNumpyView

    source = numpy.arange(4, dtype=numpy.float64).reshape(2, 2)
    reconstruct, args, state = cast(tuple[Any, tuple[Any, ...], Any], numpy.ndarray.__reduce__(source))
    restored = reconstruct(VectorNumpyView, *args[1:])
    restored.__setstate__(state)
    assert numpy.array_equal(restored, source)
    assert unwrap(restored) is restored


@requires_numpy
def test_numpy_view_fallback_results_never_inherit_the_backend() -> None:
    from httk.core import unview, unwrap
    from httk.core.vectors import VectorNumpyView

    raw = numpy.arange(6, dtype=numpy.float64).reshape(2, 3)
    view = VectorNumpyView(raw)
    for derived in (view.reshape(3, 2), view.T):
        if isinstance(derived, VectorNumpyView):
            # Backend-less: its own data is authoritative, it never unwraps to the source.
            assert unwrap(derived) is derived
            plain = unview(derived)
            assert type(plain) is numpy.ndarray
            assert plain.tolist() == derived.tolist()


@requires_numpy
def test_numpy_view_conversion_keeps_exact_backend_and_unviews_plain() -> None:
    from httk.core import coerce, coerce_view, unview, unwrap
    from httk.core.vectors import VectorNumpyView

    exact = FracVector([["1/3", "2/3"]])
    view = coerce_view(exact, numpy.ndarray)
    assert isinstance(view, VectorNumpyView)
    assert unwrap(view) is exact  # exact backend preserved
    plain = unview(view)
    assert type(plain) is numpy.ndarray
    assert numpy.shares_memory(plain, view)  # shed without another copy
    strict = coerce(exact, numpy.ndarray)
    assert type(strict) is numpy.ndarray


# ------------------------------------------------------------------ numpy-absent simulation


def test_dispatch_and_import_work_without_numpy() -> None:
    src_dir = str(pathlib.Path(__file__).resolve().parent.parent / "src")
    script = (
        "import sys\n"
        "sys.modules['numpy'] = None\n"
        f"sys.path.insert(0, {src_dir!r})\n"
        "import httk.core as c\n"
        "from httk.core.vectors import VectorBackend, VectorNative, _numpy_available\n"
        "assert _numpy_available is False\n"
        "assert not hasattr(c, 'VectorNumpy')\n"
        "names = [b.__name__ for b in VectorBackend.backend_classes]\n"
        "assert names == ['VectorFrac', 'VectorSurd', 'VectorNative'], names\n"
        "b = VectorBackend.create([[1, 2], [3, 4]])\n"
        "assert isinstance(b, VectorNative)\n"
        "import fractions as fr\n"
        "assert b.fractions == ((fr.Fraction(1), fr.Fraction(2)), (fr.Fraction(3), fr.Fraction(4)))\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --------------------------------------------------------------- the VectorAPI float contract


def test_every_backend_renders_to_floats() -> None:
    # to_floats()/to_float() are part of the VectorAPI contract, derived from the fractions hub,
    # so whatever backend the family dispatches to, the float rendering works (nested lists).
    frac_backend = VectorBackend.create(FracVector([["1/2", "1/4"]]))
    native_backend = VectorBackend.create([[1, 2], [3, 4]])
    assert frac_backend.to_floats() == [[0.5, 0.25]]
    assert native_backend.to_floats() == [[1.0, 2.0], [3.0, 4.0]]
    surd_backend = VectorBackend.create(SurdVector([[1, 0], [0, 2]]))
    assert surd_backend.to_floats() == [[1.0, 0.0], [0.0, 2.0]]


@requires_numpy
def test_numpy_backend_renders_to_floats() -> None:
    import numpy

    backend = VectorBackend.create(numpy.array([[0.5, 0.25]]))
    assert backend.to_floats() == [[0.5, 0.25]]


def test_backend_to_float_scalar_contract() -> None:
    scalar_backend = VectorBackend.create(FracVector("1/2"))
    assert scalar_backend.to_float() == 0.5
    with pytest.raises(TypeError, match="scalar"):
        VectorBackend.create([[1, 2]]).to_float()
