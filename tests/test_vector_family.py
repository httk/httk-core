"""
Tests for the Vector backend/view family: dispatch, kind overrides, view round-trips, unwrap,
and behavior when numpy is absent.
"""

import fractions
import pathlib
import subprocess
import sys

import pytest

from httk.core.views import unwrap
from httk.core.vectors import (
    FracVector,
    VectorBackend,
    VectorFrac,
    VectorFracView,
    VectorNative,
    VectorNativeView,
)

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


def test_native_view_has_exact_leaves() -> None:
    nv = VectorNativeView([[1, 2], [3, 4]])
    assert nv == ((1, 2), (3, 4))
    assert all(isinstance(x, int) for row in nv for x in row)
    frac_nv = VectorNativeView([["1/3", "2/3"]])
    assert frac_nv == ((F(1, 3), F(2, 3)),)
    assert all(isinstance(x, fractions.Fraction) for row in frac_nv for x in row)


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
