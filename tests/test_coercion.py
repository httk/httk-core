"""Tests for the general view/value coercion registry: coerce_view (backend-aware) and coerce (strict)."""

import decimal
import fractions

import pytest

from httk.core import (
    FracScalar,
    FracVector,
    SurdScalar,
    SurdVector,
    View,
    coerce,
    coerce_view,
    unwrap,
)
from httk.core.vectors.vector_native_view import VectorNativeView
from httk.core.views.coercion import _coercers, register_coercer

F = fractions.Fraction
D = decimal.Decimal


def test_identity_prototype_and_natural() -> None:
    value = [1, 2]
    for verb in (coerce_view, coerce):
        assert verb(value, list) is value
        assert verb(value, []) is value
        assert verb(value, "natural") is value


def test_coerce_view_results_are_lossless_views() -> None:
    source = FracVector.create([[1, 2], [3, 4]])
    for target in (FracVector, SurdVector, tuple):
        result = coerce_view(source, target)
        assert isinstance(result, target)
        assert unwrap(result) is source

    numpy = pytest.importorskip("numpy")
    result = coerce_view(source, numpy.ndarray)
    assert isinstance(result, numpy.ndarray)
    assert unwrap(result) is source


def test_strict_coerce_returns_plain_instances() -> None:
    source = FracVector.create([[1, 2], [3, 4]])
    for target in (FracVector, SurdVector, tuple):
        result = coerce(source, target)
        assert isinstance(result, target)
        assert not isinstance(result, View)

    numpy = pytest.importorskip("numpy")
    result = coerce(source, numpy.ndarray)
    assert type(result) is numpy.ndarray


def test_strict_coerce_sheds_a_view_input() -> None:
    source = FracVector.create([[1, 2], [3, 4]])
    view = coerce_view(source, tuple)
    assert isinstance(view, View)
    shed = coerce(view, tuple)
    assert type(shed) is tuple
    # A View target keeps the view result; strict coercion sheds only for non-View targets.
    view_result = coerce(source, VectorNativeView)
    assert isinstance(view_result, VectorNativeView)


def test_natural_returns_even_a_view_unchanged() -> None:
    source = FracVector.create([1, 2])
    view = coerce_view(source, tuple)
    assert coerce(view, "natural") is view


def test_scalar_targets_use_exact_leaf_policies() -> None:
    for verb in (coerce_view, coerce):
        assert verb(F(2), int) == 2
        assert verb(F(1, 3), float) == float(F(1, 3))
        assert verb(F(1, 3), F) == F(1, 3)
        assert verb(F(1, 8), D) == D("0.125")
        assert verb(F(1, 3), D) == D("0.3333333333333333333333333333")
        assert isinstance(verb(F(1, 3), FracScalar), FracScalar)
        assert isinstance(verb(F(1, 3), SurdScalar), SurdScalar)


def test_lossless_fallback_splits_the_verbs() -> None:
    # coerce_view keeps the exact non-integral Fraction rather than rounding; strict coerce
    # refuses to return a non-int for an int target.
    assert coerce_view(F(1, 2), int) == F(1, 2)
    with pytest.raises(TypeError):
        coerce(F(1, 2), int)


def test_surd_scalar_targets() -> None:
    rational = SurdVector.create(F(3, 2))._as_scalar()
    irrational = SurdVector.sqrt_of(2)
    for verb in (coerce_view, coerce):
        assert verb(rational, FracScalar) == FracScalar.create(F(3, 2))
        assert verb(irrational, SurdScalar) is irrational
        with pytest.raises(TypeError):
            verb(irrational, int)


def test_lists_are_mutable_copies_and_preserve_native_decimal_leaves() -> None:
    value = (D("1.25"), D("2.5"))
    for verb in (coerce_view, coerce):
        result = verb(value, list)
        assert result == [D("1.25"), D("2.5")]
        assert result is not value
        assert all(isinstance(item, D) for item in result)
        assert verb(FracScalar.create(4), list) == [4]


def test_uncoercible_pair_and_custom_registration() -> None:
    for verb in (coerce_view, coerce):
        with pytest.raises(TypeError, match="dict"):
            verb(FracVector.create([1, 2]), dict)

    def custom(value, target):
        return "custom" if target is str and value == 1 else None

    original = list(_coercers)
    try:
        register_coercer(custom, str)
        assert coerce_view(1, str) == "custom"
        assert coerce(1, str) == "custom"
    finally:
        _coercers[:] = original


def test_strict_coerce_validates_custom_coercer_results() -> None:
    def wrong_type(value, target):
        return F(1, 2)  # not an int

    original = list(_coercers)
    try:
        register_coercer(wrong_type, int)
        assert coerce_view(object(), int) == F(1, 2)
        with pytest.raises(TypeError):
            coerce(object(), int)
    finally:
        _coercers[:] = original


def test_registered_target_filters_calls() -> None:
    calls = []

    def custom(value, target):
        calls.append(target)
        return "custom"

    original = list(_coercers)
    try:
        register_coercer(custom, str)
        assert coerce_view(1, str) == "custom"
        with pytest.raises(TypeError):
            coerce_view(object(), int)
    finally:
        _coercers[:] = original
    assert calls == [str]


def test_register_coercer_rejects_non_class_targets() -> None:
    for bad in ("str", (str, "int"), ()):
        with pytest.raises(TypeError, match="register_coercer target"):
            register_coercer(lambda value, target: None, bad)


def test_view_targets_convert_without_registered_coercers() -> None:
    original = list(_coercers)
    try:
        _coercers.clear()
        for verb in (coerce_view, coerce):
            result = verb([1, 2], VectorNativeView)
            assert isinstance(result, VectorNativeView)
            assert result == (1, 2)
            with pytest.raises(TypeError):
                verb(object(), VectorNativeView)
    finally:
        _coercers[:] = original


def test_unrepresentable_numpy_values_raise_type_error() -> None:
    numpy = pytest.importorskip("numpy")
    for special in (numpy.nan, numpy.inf):
        value = numpy.array([special])
        for target in (list, tuple):
            for verb in (coerce_view, coerce):
                with pytest.raises(TypeError):
                    verb(value, target)


def test_native_view_scalar_shape_is_a_tuple() -> None:
    view = VectorNativeView(FracScalar.create(4))
    assert view == (4,)
