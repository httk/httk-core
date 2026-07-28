"""Public exactmath coercion, vector, and exact-surd trigonometry tests."""

import decimal
import fractions

import pytest

from httk.core import (
    FracScalar,
    FracVector,
    ScalarLike,
    SurdScalar,
    SurdVector,
    VectorBackend,
    VectorFrac,
    VectorFracView,
    VectorNativeView,
    VectorSurd,
    VectorSurdView,
    exactmath,
    unwrap,
)

F = fractions.Fraction
D = decimal.Decimal


def test_scalar_like_is_runtime_resolvable() -> None:
    value = ScalarLike.__value__
    assert int in value.__args__
    assert FracScalar in value.__args__


def test_scalar_like_coercions_share_the_same_fraction_hub() -> None:
    expected = exactmath.cos(F(1, 2))
    assert exactmath.cos("1/2") == expected
    assert exactmath.cos(0.5) == float(expected)
    assert exactmath.cos(FracScalar.create(F(1, 2))) == expected
    assert exactmath.cos(SurdVector.create(F(1, 2))) == expected


def test_vector_inputs_are_mapped_and_constructed_in_the_output_domain() -> None:
    assert exactmath.cos([[0, 60]], degrees=True) == [[1, F(1, 2)]]
    assert exactmath.sqrt(FracVector.create([1, 4])) == FracVector.create([1, 2])
    assert exactmath.sqrt(VectorNativeView([1, 4])) == (1, 2)
    assert isinstance(exactmath.log([[1, 2]]), list)

    decimal_result = exactmath.sqrt([D("1"), D("4")])
    assert decimal_result == [D("1"), D("2")]
    assert all(isinstance(value, D) for value in decimal_result)


def test_decimal_promotes_a_mixed_vector_as_a_whole() -> None:
    result = exactmath.sqrt([D("1"), F(4)])
    assert result == [D("1"), D("2")]
    assert all(isinstance(value, D) for value in result)


def test_exact_surd_trigonometry_and_inverse_tables() -> None:
    sqrt2 = exactmath.sqrt(2, exact=True)
    sqrt3 = exactmath.sqrt(3, exact=True)
    sqrt5 = exactmath.sqrt(5, exact=True)
    sqrt6 = exactmath.sqrt(6, exact=True)
    assert exactmath.cos(15, degrees=True, exact=True) == (sqrt6 + sqrt2) / 4
    assert exactmath.cos(30, degrees=True, exact=True) == sqrt3 / 2
    assert exactmath.cos(45, degrees=True, exact=True) == sqrt2 / 2
    assert exactmath.cos(60, degrees=True, exact=True) == F(1, 2)
    assert exactmath.cos(75, degrees=True, exact=True) == (sqrt6 - sqrt2) / 4
    assert exactmath.sin(15, degrees=True, exact=True) == (sqrt6 - sqrt2) / 4
    assert exactmath.sin(30, degrees=True, exact=True) == F(1, 2)
    assert exactmath.sin(45, degrees=True, exact=True) == sqrt2 / 2
    assert exactmath.sin(60, degrees=True, exact=True) == sqrt3 / 2
    assert exactmath.sin(75, degrees=True, exact=True) == (sqrt6 + sqrt2) / 4
    assert exactmath.tan(15, degrees=True, exact=True) == 2 - sqrt3
    assert exactmath.tan(30, degrees=True, exact=True) == sqrt3 / 3
    assert exactmath.tan(45, degrees=True, exact=True) == F(1)
    assert exactmath.tan(60, degrees=True, exact=True) == sqrt3
    assert exactmath.tan(75, degrees=True, exact=True) == 2 + sqrt3
    assert exactmath.cos(36, degrees=True, exact=True) == (1 + sqrt5) / 4
    assert exactmath.cos(72, degrees=True, exact=True) == (sqrt5 - 1) / 4
    assert exactmath.acos((1 + sqrt5) / 4, degrees=True, exact=True) == F(36)
    assert exactmath.asin(F(1, 2), degrees=True, exact=True) == F(30)
    assert exactmath.atan(sqrt3 / 3, degrees=True, exact=True) == F(30)
    assert exactmath.atan2(-1, -1, degrees=True, exact=True) == F(-135)

    vector_result = exactmath.cos([0, 60], degrees=True, exact=True)
    assert vector_result._element((0,)) == F(1)
    assert vector_result._element((1,)) * vector_result._element((1,)) == F(1, 4)


def test_exact_inverse_trigonometry_maps_rational_vector_leaves() -> None:
    asin_result = exactmath.asin([-1, 0, 1], degrees=True, exact=True)
    acos_result = exactmath.acos([-1, 0, 1], degrees=True, exact=True)
    atan_result = exactmath.atan([-1, 0, 1], degrees=True, exact=True)
    assert [asin_result._element((i,)) for i in range(3)] == [F(-90), F(0), F(90)]
    assert [acos_result._element((i,)) for i in range(3)] == [F(180), F(90), F(0)]
    assert [atan_result._element((i,)) for i in range(3)] == [F(-45), F(0), F(45)]


def test_atan2_vectors_broadcast_and_resolve_quadrants() -> None:
    result = exactmath.atan2([1, -1, 1, -1], [1, 1, -1, -1], degrees=True, exact=True)
    assert [result._element((i,)) for i in range(4)] == [F(45), F(-45), F(135), F(-135)]
    broadcast = exactmath.atan2([1, -1, 0], 1, degrees=True, exact=True)
    assert [broadcast._element((i,)) for i in range(3)] == [F(45), F(-45), F(0)]
    with pytest.raises(ValueError, match="shapes"):
        exactmath.atan2([1, 0], [1, 0, -1], degrees=True)


def test_scalar_vector_backends_and_zero_dimensional_numpy_are_scalar_inputs() -> None:
    rational_backend = VectorFrac(FracVector.create(4))
    assert exactmath.sqrt(rational_backend, exact=True) == F(2)
    genuine = VectorSurd(SurdVector.sqrt_of(2))
    with pytest.raises(ValueError, match="rational value"):
        exactmath.sqrt(genuine, exact=True)
    genuine_view = VectorSurdView(SurdVector.sqrt_of(2))
    with pytest.raises(ValueError, match="rational value"):
        exactmath.sqrt(genuine_view, exact=True)

    numpy = pytest.importorskip("numpy")
    zero_dimensional = numpy.array(4)
    assert exactmath.sqrt(zero_dimensional) == F(2)
    assert exactmath.sqrt(zero_dimensional, exact=True) == F(2)


def test_exact_vector_mode_ignores_decimal_parameter_validation() -> None:
    result = exactmath.sqrt([2, 3], exact=True, digits=0)
    assert result._element((0,)) * result._element((0,)) == F(2)
    assert result._element((1,)) * result._element((1,)) == F(3)


def test_log10_honors_max_refinements() -> None:
    assert isinstance(exactmath.log10(D(2), digits=5, max_refinements=0), D)
    with pytest.raises(ValueError, match="max_refinements"):
        exactmath.log10(D(2), digits=5, max_refinements=-1)


def test_view_neutral_default_presentation_matrix() -> None:
    assert exactmath.sqrt([4, 9]) == [2, 3]
    assert isinstance(exactmath.sqrt((4, 9)), tuple)
    assert isinstance(exactmath.sqrt(4), int)
    assert isinstance(exactmath.sqrt(2), F)
    assert isinstance(exactmath.sqrt(2.0), float)
    assert isinstance(exactmath.sqrt(F(2)), F)
    assert isinstance(exactmath.sqrt(D(2)), D)
    assert isinstance(exactmath.sqrt(SurdVector.create(4)), SurdVector)

    numpy = pytest.importorskip("numpy")
    array_result = exactmath.sqrt(numpy.array([4, 9]))
    assert isinstance(array_result, numpy.ndarray)


def test_exactmath_explicit_presentation_and_natural_mode() -> None:
    result = exactmath.sqrt([4, 9], coerce=FracVector)
    assert isinstance(result, FracVector)
    assert result == FracVector.create([2, 3])
    prototype = FracVector.create([0])
    assert isinstance(exactmath.cos((0, 1), coerce=prototype), FracVector)
    assert isinstance(exactmath.sqrt(4, coerce=float), float)
    assert isinstance(exactmath.sqrt(2, exact=True), SurdScalar)
    assert isinstance(exactmath.sqrt(2, exact=True, coerce=float), float)
    assert isinstance(exactmath.sqrt(2, coerce="natural"), F)
    with pytest.raises(TypeError):
        exactmath.sqrt(2, coerce=dict)


def test_view_neutral_two_argument_functions_use_the_first_argument() -> None:
    assert isinstance(exactmath.atan2(1, 1.0), F)
    assert isinstance(exactmath.atan2(1.0, 1), float)
    assert isinstance(exactmath.log(4, base=2.0), int)
    assert isinstance(exactmath.log(4.0, base=2), float)


def test_view_neutral_decimal_list_preserves_decimal_leaves() -> None:
    result = exactmath.sqrt([D("1"), D("4")])
    assert result == [D("1"), D("2")]
    assert all(isinstance(value, D) for value in result)


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (exactmath.sqrt, (F(1, 2),)),
        (exactmath.cos, (F(1, 2),)),
        (exactmath.sin, (F(1, 2),)),
        (exactmath.tan, (F(1, 2),)),
        (exactmath.exp, (F(1, 2),)),
        (exactmath.log, (F(1, 2), F(2))),
        (exactmath.log10, (F(1, 2),)),
        (exactmath.asin, (F(1, 2),)),
        (exactmath.acos, (F(1, 2),)),
        (exactmath.atan, (F(1, 2),)),
        (exactmath.atan2, (F(1, 2), F(2))),
    ],
)
def test_all_exactmath_functions_honor_explicit_presentation(function, args) -> None:
    natural = function(*args, coerce="natural")
    assert isinstance(natural, F)
    assert isinstance(function(*args, coerce=float), float)
    with pytest.raises(TypeError):
        function(*args, coerce=dict)


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (exactmath.cos, (60,)),
        (exactmath.sin, (30,)),
        (exactmath.tan, (45,)),
        (exactmath.asin, (F(1, 2),)),
        (exactmath.acos, (F(1, 2),)),
        (exactmath.atan, (1,)),
        (exactmath.atan2, (1, 1)),
    ],
)
def test_exact_trigonometry_honors_explicit_float_presentation(function, args) -> None:
    assert isinstance(function(*args, degrees=True, exact=True, coerce=float), float)


def test_default_presentation_special_input_rows() -> None:
    assert isinstance(exactmath.sqrt("4"), F)
    assert exactmath.sqrt(True) == F(1)
    assert isinstance(exactmath.sqrt(True), F)

    backend = VectorFrac(FracVector.create(4))
    assert isinstance(backend, VectorBackend)
    assert exactmath.sqrt(backend) == F(2)
    assert isinstance(exactmath.sqrt(backend), F)

    view = VectorFracView([4, 9])
    result = exactmath.sqrt(view)
    assert isinstance(result, VectorFracView)
    assert unwrap(result) == FracVector.create([2, 3])


def test_default_numpy_presentation_is_float64_and_lossless_backend() -> None:
    numpy = pytest.importorskip("numpy")
    source = numpy.array([4, 9])
    exact = exactmath.sqrt(source, coerce="natural")
    result = exactmath.sqrt(source)
    assert result.dtype == numpy.dtype(numpy.float64)
    assert numpy.array_equal(result, numpy.asarray(exact.to_floats(), dtype=numpy.float64))
    assert unwrap(result) == exact


def test_exact_trigonometry_and_surd_sqrt_reject_inexact_cases() -> None:
    with pytest.raises(ValueError, match="degrees=True"):
        exactmath.cos(30, exact=True)
    with pytest.raises(ValueError, match="15° and 36°"):
        exactmath.cos(7, degrees=True, exact=True)
    with pytest.raises(ValueError, match="rational value"):
        exactmath.sqrt(SurdVector.sqrt_of(2), exact=True)
    with pytest.raises(ValueError, match="15° and 36°"):
        exactmath.sin(36, degrees=True, exact=True)
