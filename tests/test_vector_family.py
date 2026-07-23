"""
Tests for the Vector backend/view family: dispatch, kind overrides, view round-trips, unwrap,
and behavior when numpy is absent.
"""

import fractions
import pathlib
import subprocess
import sys

import pytest

from httk.core.vectors import (
    FracVector,
    VectorBackend,
    VectorFrac,
    VectorFracView,
    VectorNative,
    VectorNativeView,
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
    backend = VectorBackend.create(FracVector.create([[1, 2], [3, 4]]))
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
        VectorBackend.create(FracVector.create([1, 2, 3]), kind="native")


def test_unrepresentable_raises() -> None:
    with pytest.raises(TypeError):
        VectorBackend.create(object())


# ------------------------------------------------------------------ fractions interchange


def test_backend_fractions_are_exact() -> None:
    backend = VectorBackend.create([["1/3", "2/5"]])
    assert backend.fractions == ((F(1, 3), F(2, 5)),)
    assert backend.dim == (1, 2)


def test_native_string_uncertainty_parsing() -> None:
    # Conversion goes through FracVector.create, so uncertainty strings parse here too.
    backend = VectorBackend.create(["0.33342(10)"])
    assert backend.fractions == (F(1, 3),)


# ------------------------------------------------------------------ views


def test_frac_view_is_a_fracvector_with_algebra() -> None:
    v = VectorFracView([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
    assert isinstance(v, FracVector)
    assert v.det() == -3
    assert v.inv().simplify() == FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]]).inv().simplify()


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
    nv = VectorNativeView(FracVector.create([["1/3", "2/3"], [1, 2]]))
    assert nv == ((F(1, 3), F(2, 3)), (1, 2))
    assert isinstance(nv[0][0], fractions.Fraction)
    assert all(isinstance(x, int) for x in nv[1])


def test_frac_to_native_to_frac_is_exact_identity() -> None:
    src = FracVector.create([["1/3", "2/5"], ["3/7", "4/9"]])
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
    fv = FracVector.create([[1, 2], [3, 4]])
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
    src = FracVector.create([["5/2", "7/2", "-5/2", "-7/2"]])
    assert VectorNativeView(src, leaf="int") == ((2, 4, -2, -4),)  # nearest, ties to even
    assert VectorNativeView(src, leaf="int", rounding="floor") == ((2, 3, -3, -4),)
    assert VectorNativeView(src, leaf="int", rounding="ceil") == ((3, 4, -2, -3),)
    assert VectorNativeView(src, leaf="int", rounding="trunc") == ((2, 3, -2, -3),)


def test_native_view_leaf_decimal_exact_and_quantized() -> None:
    import decimal

    exact = VectorNativeView(FracVector.create([["1/8"]]), leaf="decimal")
    assert exact == ((decimal.Decimal("0.125"),),)
    assert isinstance(exact[0][0], decimal.Decimal)
    # 1/3 has no finite decimal expansion: quantized to `digits` significant digits, half-even.
    assert VectorNativeView(FracVector.create([["1/3"]]), leaf="decimal", digits=6) == ((decimal.Decimal("0.333333"),),)
    assert VectorNativeView(FracVector.create([["2/3"]]), leaf="decimal", digits=6) == ((decimal.Decimal("0.666667"),),)


def test_native_view_leaf_float_is_lossy() -> None:
    fv = VectorNativeView(FracVector.create([["1/3"]]), leaf="float")
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
    from_frac = VectorNativeView(FracVector.create([["1/2"]]), leaf="int")
    assert from_native == ((0,),) == from_frac  # 1/2 -> 0 by half-even


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

    one_third = FracVector.create([["1/3"]])
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
    rounded = VectorNumpyView(FracVector.create([["1/2", "3/2", "5/2", "7/2"]]), dtype=numpy.int64)
    assert rounded.dtype == numpy.int64
    assert rounded.tolist() == [[0, 2, 2, 4]]


@requires_numpy
def test_numpy_view_float32_dtype() -> None:
    from httk.core.vectors import VectorNumpyView

    arr = VectorNumpyView([[1, 2], [3, 4]], dtype=numpy.float32)
    assert arr.dtype == numpy.float32


# ------------------------------------------------------------------ numpy-absent simulation


def test_dispatch_and_import_work_without_numpy() -> None:
    src_dir = str(pathlib.Path(__file__).resolve().parent.parent / "src")
    script = (
        "import sys\n"
        "sys.modules['numpy'] = None\n"
        f"sys.path.insert(0, {src_dir!r})\n"
        "import httk.core as c\n"
        "from httk.core.vectors import VectorBackend, VectorNative\n"
        "assert c._vectors_numpy_available is False\n"
        "assert not hasattr(c, 'VectorNumpy')\n"
        "names = [b.__name__ for b in VectorBackend.backend_classes]\n"
        "assert names == ['VectorFrac', 'VectorNative'], names\n"
        "b = VectorBackend.create([[1, 2], [3, 4]])\n"
        "assert isinstance(b, VectorNative)\n"
        "import fractions as fr\n"
        "assert b.fractions == ((fr.Fraction(1), fr.Fraction(2)), (fr.Fraction(3), fr.Fraction(4)))\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
