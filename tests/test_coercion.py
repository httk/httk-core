"""Tests for the general view/value coercion registry."""

import decimal
import fractions

import pytest

from httk.core import (
    FracScalar,
    FracVector,
    SurdScalar,
    SurdVector,
    coerce,
    unwrap,
)
from httk.core.vectors.vector_native_view import VectorNativeView
from httk.core.views.coercion import _coercers, register_coercer

F = fractions.Fraction
D = decimal.Decimal


def test_identity_prototype_and_natural() -> None:
    value = [1, 2]
    assert coerce(value, list) is value
    assert coerce(value, []) is value
    assert coerce(value, "natural") is value


def test_vector_views_are_lossless() -> None:
    source = FracVector.create([[1, 2], [3, 4]])
    for target in (FracVector, SurdVector, tuple):
        result = coerce(source, target)
        assert isinstance(result, target)
        assert unwrap(result) is source

    numpy = pytest.importorskip("numpy")
    result = coerce(source, numpy.ndarray)
    assert isinstance(result, numpy.ndarray)
    assert unwrap(result) is source


def test_scalar_targets_use_exact_leaf_policies() -> None:
    assert coerce(F(2), int) == 2
    assert coerce(F(1, 2), int) == F(1, 2)
    assert coerce(F(1, 3), float) == float(F(1, 3))
    assert coerce(F(1, 3), F) == F(1, 3)
    assert coerce(F(1, 8), D) == D("0.125")
    assert coerce(F(1, 3), D) == D("0.3333333333333333333333333333")
    assert isinstance(coerce(F(1, 3), FracScalar), FracScalar)
    assert isinstance(coerce(F(1, 3), SurdScalar), SurdScalar)


def test_surd_scalar_targets() -> None:
    rational = SurdVector.create(F(3, 2))._as_scalar()
    irrational = SurdVector.sqrt_of(2)
    assert coerce(rational, FracScalar) == FracScalar.create(F(3, 2))
    assert coerce(irrational, SurdScalar) is irrational
    with pytest.raises(TypeError):
        coerce(irrational, int)


def test_lists_are_mutable_copies_and_preserve_native_decimal_leaves() -> None:
    value = (D("1.25"), D("2.5"))
    result = coerce(value, list)
    assert result == [D("1.25"), D("2.5")]
    assert result is not value
    assert all(isinstance(item, D) for item in result)
    assert coerce(FracScalar.create(4), list) == [4]


def test_uncoercible_pair_and_custom_registration() -> None:
    with pytest.raises(TypeError, match="dict"):
        coerce(FracVector.create([1, 2]), dict)

    def custom(value, target):
        return "custom" if target is str and value == 1 else None

    original = list(_coercers)
    try:
        register_coercer(custom)
        assert coerce(1, str) == "custom"
    finally:
        _coercers[:] = original


def test_unrepresentable_numpy_values_raise_type_error() -> None:
    numpy = pytest.importorskip("numpy")
    for special in (numpy.nan, numpy.inf):
        value = numpy.array([special])
        for target in (list, tuple):
            with pytest.raises(TypeError):
                coerce(value, target)


def test_native_view_scalar_shape_is_a_tuple() -> None:
    view = VectorNativeView(FracScalar.create(4))
    assert view == (4,)
