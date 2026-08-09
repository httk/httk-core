"""
Unit tests for the leaf-codec registry (the Vector family's element-domain axis): each built-in
codec's exact path, default-conversion path, and option path; the never-raise-on-data policy;
configuration-error raising; and registry extension.
"""

import decimal
import fractions

import pytest

from httk.core.vectors import (
    FracVector,
    VectorNativeView,
    known_leaf_codecs,
    register_leaf_codec,
)
from httk.core.vectors.leaf_codecs import (
    LeafCodec,
    apply_leaf_codec,
    leaf_codec_for_name,
    validate_leaf_codec,
)

F = fractions.Fraction


# ------------------------------------------------------------------ registry


def test_builtin_codecs_registered_in_order() -> None:
    assert known_leaf_codecs() == ["exact", "fraction", "int", "float", "decimal"]


def test_unknown_codec_raises_listing_known() -> None:
    with pytest.raises(ValueError, match=r"unknown leaf codec 'nope'; known codecs: \["):
        leaf_codec_for_name("nope")


# ------------------------------------------------------------------ exact / fraction


def test_exact_codec() -> None:
    codec = leaf_codec_for_name("exact")
    assert codec.from_fraction(F(4, 2)) == 2 and isinstance(codec.from_fraction(F(4, 2)), int)
    assert codec.from_fraction(F(1, 3)) == F(1, 3) and isinstance(codec.from_fraction(F(1, 3)), fractions.Fraction)


def test_fraction_codec_always_fraction() -> None:
    codec = leaf_codec_for_name("fraction")
    out = codec.from_fraction(F(4, 2))
    assert out == F(2) and isinstance(out, fractions.Fraction)


# ------------------------------------------------------------------ int


def test_int_codec_exact_when_integral() -> None:
    codec = leaf_codec_for_name("int")
    assert codec.from_fraction(F(6, 2)) == 3


def test_int_codec_default_is_half_even() -> None:
    codec = leaf_codec_for_name("int")
    # ties go to the even neighbor, matching round(Fraction)
    assert codec.from_fraction(F(5, 2)) == 2
    assert codec.from_fraction(F(7, 2)) == 4
    assert codec.from_fraction(F(-5, 2)) == -2
    assert codec.from_fraction(F(-7, 2)) == -4
    # non-ties round to nearest
    assert codec.from_fraction(F(7, 3)) == 2
    assert codec.from_fraction(F(8, 3)) == 3


def test_int_codec_rounding_modes() -> None:
    codec = leaf_codec_for_name("int")
    assert codec.from_fraction(F(7, 2), rounding="floor") == 3
    assert codec.from_fraction(F(7, 2), rounding="ceil") == 4
    assert codec.from_fraction(F(7, 2), rounding="trunc") == 3
    assert codec.from_fraction(F(-7, 2), rounding="floor") == -4
    assert codec.from_fraction(F(-7, 2), rounding="ceil") == -3
    assert codec.from_fraction(F(-7, 2), rounding="trunc") == -3


def test_int_codec_bad_options_raise() -> None:
    with pytest.raises(ValueError, match="unknown rounding"):
        validate_leaf_codec("int", {"rounding": "sideways"})
    with pytest.raises(ValueError, match="only 'rounding' is accepted"):
        validate_leaf_codec("int", {"digits": 3})


# ------------------------------------------------------------------ float


def test_float_codec_binary_rational_roundtrip() -> None:
    codec = leaf_codec_for_name("float")
    out = codec.from_fraction(F(1, 3))
    assert out == 1.0 / 3.0 and isinstance(out, float)
    # a value that is a binary rational round-trips exactly through float
    assert codec.from_fraction(F(1, 4)) == 0.25


# ------------------------------------------------------------------ decimal


def test_decimal_codec_exact_when_finite_expansion() -> None:
    codec = leaf_codec_for_name("decimal")
    # 2^a * 5^b denominators have finite decimal expansions: exact, no rounding.
    assert codec.from_fraction(F(1, 8)) == decimal.Decimal("0.125")
    assert codec.from_fraction(F(-1, 8)) == decimal.Decimal("-0.125")
    assert codec.from_fraction(F(5, 2)) == decimal.Decimal("2.5")
    assert codec.from_fraction(F(3, 20)) == decimal.Decimal("0.15")
    assert codec.from_fraction(F(6, 2)) == decimal.Decimal(3)
    assert codec.from_fraction(F(0)) == decimal.Decimal(0)


def test_decimal_codec_exact_is_context_independent() -> None:
    codec = leaf_codec_for_name("decimal")
    # A denominator whose exact expansion is far longer than the default precision stays exact.
    with decimal.localcontext() as ctx:
        ctx.prec = 3
        value = codec.from_fraction(F(1, 2**20))  # 20-digit finite expansion
    # Exact despite the tiny precision that was active during construction.
    assert value == decimal.Decimal("0.00000095367431640625")
    assert value.as_integer_ratio() == (1, 2**20)


def test_decimal_codec_quantizes_when_no_finite_expansion() -> None:
    codec = leaf_codec_for_name("decimal")
    assert codec.from_fraction(F(1, 3), digits=6) == decimal.Decimal("0.333333")
    assert codec.from_fraction(F(2, 3), digits=6) == decimal.Decimal("0.666667")  # half-even up
    # default digits follow the active context precision
    with decimal.localcontext() as ctx:
        ctx.prec = 4
        assert codec.from_fraction(F(1, 3)) == decimal.Decimal("0.3333")


def test_decimal_codec_bad_options_raise() -> None:
    with pytest.raises(ValueError, match="expected a positive integer"):
        validate_leaf_codec("decimal", {"digits": 0})
    with pytest.raises(ValueError, match="expected a positive integer"):
        validate_leaf_codec("decimal", {"digits": 2.5})
    with pytest.raises(ValueError, match="only 'digits' is accepted"):
        validate_leaf_codec("decimal", {"rounding": "floor"})


# ------------------------------------------------------------------ never-raise-on-data invariant


def test_codecs_never_raise_on_data() -> None:
    # Every built-in produces *some* documented leaf for an awkward value; only config errors raise.
    awkward = F(22, 7)
    for name in known_leaf_codecs():
        codec = leaf_codec_for_name(name)
        assert codec.from_fraction(awkward) is not None


def test_apply_leaf_codec_maps_nested() -> None:
    codec = leaf_codec_for_name("int")
    assert apply_leaf_codec(codec, ((F(1, 2), F(3, 2)), (F(4),))) == ((0, 2), (4,))
    assert apply_leaf_codec(codec, F(5, 2)) == 2  # scalar


# ------------------------------------------------------------------ registry extension


def test_register_and_use_custom_codec() -> None:
    def _to_percent(value: fractions.Fraction) -> str:
        return f"{float(value * 100):g}%"

    def _no_options(options: dict[str, object]) -> None:
        if options:
            raise ValueError("percent codec takes no options")

    register_leaf_codec(LeafCodec("percent", _to_percent, _no_options))
    try:
        assert "percent" in known_leaf_codecs()
        assert VectorNativeView(FracVector([["1/4", "1/2"]]), leaf="percent") == (("25%", "50%"),)
    finally:
        # Keep the global registry clean for other tests.
        from httk.core.vectors import leaf_codecs

        leaf_codecs._registry.pop("percent", None)
