"""DecimalVector: exact CIF decimals as written (value, standard uncertainty, spelling, gaps)."""

import decimal
import json
import pickle
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import cast

import pytest

from httk.core import DecimalGap, DecimalScalar, DecimalVector, FracVector, decimal_precision
from httk.core.storage import StorageInfo, canonical_form, content_id

# Exponents near 1e9 need 64-bit Decimal limits (decimal.MAX_EMAX is 425000000 on 32-bit builds).
_EMAX64 = pytest.mark.skipif(decimal.MAX_EMAX < 999999999, reason="needs 64-bit decimal exponent limits")

# token -> (value, su, spelling)
_FORMS = {
    "0.50": (Decimal("0.50"), None, None),
    "0.5": (Decimal("0.5"), None, None),
    "1.2345(6)": (Decimal("1.2345"), Decimal("0.0006"), None),
    "12(1)": (Decimal(12), Decimal(1), None),
    "1.5e-3": (Decimal("0.0015"), None, "1.5e-3"),
    "1.5(2)E-3": (Decimal("0.0015"), Decimal("0.0002"), "1.5(2)E-3"),
    "1.5E-3(2)": (Decimal("0.0015"), Decimal("0.0002"), "1.5E-3(2)"),
    "1.23(06)": (Decimal("1.23"), Decimal("0.06"), "1.23(06)"),
    "007": (Decimal(7), None, "007"),
    "+1.0": (Decimal("1.0"), None, "+1.0"),
    "1.": (Decimal(1), None, "1."),
    ".5": (Decimal("0.5"), None, ".5"),
    "-0.0": (Decimal("-0.0"), None, None),
    "0.00000000": (Decimal("0E-8"), None, None),
    "1.2e3": (Decimal("1.2E+3"), None, "1.2e3"),
    "12E+2": (Decimal("1.2E+3"), None, None),
}

_HUGE = ["1e-999999999", "1234567890123456789012345678901234567890.5", "1(2)e999999999"]


@pytest.mark.parametrize("token", list(_FORMS))
def test_number_forms_parse_and_render_back(token: str) -> None:
    value, su, spelling = _FORMS[token]
    scalar = DecimalScalar(token)
    assert scalar.token == token and scalar.tokens == token and scalar.dim == ()
    assert scalar.value == value and cast(Decimal, scalar.value).as_tuple() == value.as_tuple()
    assert scalar.uncertainty == su
    if su is not None:
        assert scalar.uncertainty is not None
        assert scalar.uncertainty.as_tuple().exponent == cast(Decimal, scalar.value).as_tuple().exponent
    assert scalar.spelling == spelling
    assert eval(repr(scalar)) == scalar


@pytest.mark.parametrize("token", ["?", "."])
def test_gaps_keep_their_kind(token: str) -> None:
    gap = DecimalScalar(token)
    assert gap.value is DecimalGap(token) and gap.token == token
    assert gap.uncertainty is None and gap.spelling is None and gap.precision is None
    assert DecimalScalar(DecimalGap(token)) == gap
    assert eval(repr(DecimalGap(token))) is DecimalGap(token)
    with pytest.raises(ValueError, match=r"entry \(\) is"):
        gap.to_fractions()
    with pytest.raises(ValueError, match="has no value"):
        gap.to_floats()


def _hostile() -> decimal.Context:
    traps = [decimal.Inexact, decimal.Rounded, decimal.Clamped, decimal.Overflow, decimal.Underflow]
    return decimal.Context(prec=1, Emax=1, Emin=-1, capitals=0, traps=traps)


@_EMAX64
@pytest.mark.parametrize("token", _HUGE)
def test_bounds_construct_render_and_compare_without_expansion(token: str) -> None:
    with decimal.localcontext(_hostile()):
        scalar = DecimalScalar(token)
        assert scalar.token == token
        assert eval(repr(scalar)) == scalar and hash(scalar) == hash(DecimalScalar(token))
        assert scalar.numerically_equal(DecimalScalar(token))
        assert pickle.loads(pickle.dumps(scalar)) == scalar
    assert cast(Decimal, DecimalScalar("1e-999999999").value).as_tuple().exponent == -999999999
    assert DecimalScalar("1(2)e999999999").uncertainty == Decimal("2E+999999999")


@_EMAX64
def test_size_bound_applies_only_in_conversions() -> None:
    tiny = DecimalScalar("1e-999999999")
    for convert in (tiny.to_fractions, tiny.to_floats, lambda: tiny.precisions):
        with pytest.raises(ValueError, match="exceeds"):
            convert()
    long = DecimalScalar(_HUGE[1])
    assert long.to_fractions() == Fraction(_HUGE[1]) and long.precision == Fraction(1, 10)
    assert content_id(_Plain(tiny)) != content_id(_Plain(DecimalScalar("1e-999999998")))


def test_conversions_are_exact_under_a_hostile_context() -> None:
    vector = DecimalVector([["0.1", "1.2345(6)"], ["-2.50", "1.5e-3"]])
    with decimal.localcontext(_hostile()):
        assert vector.to_fractions() == (
            (Fraction(1, 10), Fraction(12345, 10000)),
            (Fraction(-5, 2), Fraction(3, 2000)),
        )
        assert vector.to_floats() == ((0.1, 1.2345), (-2.5, 0.0015))
        assert FracVector(vector) == FracVector([["1/10", "12345/10000"], ["-5/2", "3/2000"]])


def test_out_of_range_exponent_and_non_numbers_are_rejected() -> None:
    with decimal.localcontext(decimal.Context(traps=[])), pytest.raises(ValueError, match="out of range"):
        DecimalScalar("1e99999999999999999999")
    # The su is built in the same trapped context as the value: no raw InvalidOperation or NaN su.
    for context in (decimal.Context(), decimal.Context(traps=[])):
        with decimal.localcontext(context), pytest.raises(ValueError, match="out of range"):
            DecimalScalar("1(12345)e999999999999999999")
    with pytest.raises(ValueError, match="too many digits"):
        DecimalScalar(10**5000)
    for token in ["NaN", "Infinity", "1_000", " 1", "1 ", "", "1.5(2", "١", "1e", "e3", "0x10", "1/3", "'1.5'"]:
        with pytest.raises(ValueError, match="not a CIF number"):
            DecimalScalar(token)
    for leaf in [1.5, Fraction(1, 2), True, None, b"1"]:
        with pytest.raises(TypeError):
            DecimalScalar(leaf)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            DecimalVector([leaf])
    for bad in [Decimal("NaN"), Decimal("Infinity"), Decimal("-sNaN")]:
        with pytest.raises(ValueError, match="finite"):
            DecimalScalar(bad)
    with pytest.raises(ValueError, match="rectangular"):
        DecimalVector([["1", "2"], ["3"]])
    with pytest.raises(ValueError, match="rectangular"):
        DecimalVector(["1", ["2"]])
    with pytest.raises(TypeError, match="bare leaf"):
        DecimalVector("1")
    with pytest.raises(TypeError, match="single leaf"):
        DecimalScalar(["1"])  # type: ignore[arg-type]


def test_accepted_leaves_and_containers() -> None:
    vector = DecimalVector([7, Decimal("0.50"), Decimal("1.2E+3"), DecimalGap.UNKNOWN, DecimalScalar("1.5(2)")])
    assert vector.tokens == ("7", "0.50", "12E+2", "?", "1.5(2)")
    assert vector.spellings == {} and vector.uncertainties == {(4,): Decimal("0.2")}
    nested = DecimalVector([DecimalVector(["1.0(1)", "007"]), ("2", ".")])
    assert nested.dim == (2, 2)
    assert nested.uncertainties == {(0, 0): Decimal("0.1")} and nested.spellings == {(0, 1): "007"}
    assert DecimalVector([]).dim == (0,) and DecimalVector([[], []]).dim == (2, 0)
    assert DecimalVector(nested) == nested
    with pytest.raises(TypeError):
        nested.uncertainties[(0, 0)] = Decimal(1)  # type: ignore[index]


def test_equality_is_token_exact_and_numerical_comparison_is_separate() -> None:
    a, b = DecimalVector(["0.50", "007", "?"]), DecimalVector(["0.5", "7", "?"])
    assert a != b and hash(a) != hash(b)
    assert a.numerically_equal(b)
    assert DecimalScalar("?") != DecimalScalar(".")
    assert not DecimalVector(["?"]).numerically_equal(DecimalVector(["."]))
    assert not DecimalVector(["?"]).numerically_equal(DecimalVector(["0"]))
    assert not DecimalVector(["1"]).numerically_equal(DecimalVector([["1"]]))
    assert DecimalVector(["1.0(1)"]).numerically_equal(DecimalVector(["+1.00(2)"]))
    assert DecimalVector(["0.50"]) == DecimalVector(("0.50",)) and len({a, DecimalVector(a)}) == 1
    assert DecimalVector(["1"]) != DecimalScalar("1") and DecimalVector([[]]) != DecimalVector([])
    assert DecimalScalar("1") != "1"


def test_indexing_values_and_precisions() -> None:
    vector = DecimalVector([["0.50", "?"], ["1.2345(6)", "1.5E-3"], ["007", "1."]])
    assert len(vector) == 3 and vector[1] == DecimalVector(["1.2345(6)", "1.5E-3"])
    assert vector[1][0] == DecimalScalar("1.2345(6)") and vector[-1][0].spellings == {(): "007"}
    assert next(iter(vector))[1] == DecimalScalar("?")
    assert vector.values == (
        (Decimal("0.50"), DecimalGap.UNKNOWN),
        (Decimal("1.2345"), Decimal("0.0015")),
        (Decimal(7), Decimal(1)),
    )
    assert vector.precisions == ((Fraction(1, 100), None), (Fraction(1, 10000), Fraction(1, 10000)), (None, None))
    for token in ["0.50", "1.5E-3", "007", "1.", "1.2e3"]:
        assert DecimalScalar(token).precision == decimal_precision(token)
    with pytest.raises(ValueError, match=r"entry \(0, 1\) is unknown"):
        FracVector(vector)
    with pytest.raises(TypeError):
        len(DecimalScalar("1"))
    with pytest.raises(TypeError):
        DecimalScalar("1")[0]
    with pytest.raises(TypeError):
        vector[0:1]  # type: ignore[index]


@dataclass(frozen=True)
class _Plain:
    value: object


def test_content_identity_is_the_token_text() -> None:
    def node(value: object) -> object:
        return dict(json.loads(canonical_form(_Plain(value)))["fields"])["value"]

    assert node(DecimalScalar("1.2345(6)")) == {"type": "decimal_scalar", "value": "1.2345(6)"}
    assert node(DecimalVector([["0.50", "?"]])) == {"type": "decimal_vector", "value": [["0.50", "?"]]}
    assert node(Decimal("0.50")) == {"type": "rational", "value": "1/2"}
    vector = DecimalVector([["0.50", "1.2(3)"], [".", "007"]])
    assert content_id(_Plain(vector)) == content_id(_Plain(eval(repr(vector))))
    assert content_id(_Plain(DecimalScalar("0.50"))) != content_id(_Plain(DecimalScalar("0.5")))
    assert content_id(_Plain(DecimalScalar("1"))) != content_id(_Plain(DecimalVector(["1"])))

    class Sub(DecimalVector):
        __slots__ = ()

    with pytest.raises(TypeError, match="unsupported value type"):
        content_id(_Plain(Sub(["1"])))


def test_long_non_numbers_are_rejected_in_linear_time() -> None:
    for token in ["1" * 200_000 + "x", "1" * 100_000 + "." + "1" * 100_000 + "x", "1" * 200_000 + "(1"]:
        start = time.perf_counter()
        with pytest.raises(ValueError, match="not a CIF number"):
            DecimalScalar(token)
        assert time.perf_counter() - start < 1


def test_precision_imports_in_a_fresh_interpreter() -> None:
    code = "import httk.core.precision\nfrom httk.core import decimal_precision\nassert str(decimal_precision('0.50')) == '1/100'"
    subprocess.run([sys.executable, "-c", code], check=True)
    subprocess.run([sys.executable, "-c", "from httk.core import decimal_precision"], check=True)


def test_subclass_leaves_are_normalized_and_errors_are_deliberate() -> None:
    class Text(str):
        def __str__(self) -> str:
            return "9"

        def __eq__(self, other: object) -> bool:
            return True

        __hash__ = str.__hash__

    class Integer(int):
        def __repr__(self) -> str:
            return "9"

        __str__ = __repr__

    scalar = DecimalScalar(Text("0.50"))
    assert type(scalar.token) is str and scalar.token == "0.50" and scalar != DecimalScalar("9")
    assert DecimalScalar(Integer(5)).token == "5"
    with pytest.raises(TypeError, match="no truth value"):
        bool(DecimalScalar("0"))
    assert DecimalVector(["0"]) and not DecimalVector([])
    with pytest.raises(TypeError, match="cannot compare"):
        DecimalVector(["1"]).numerically_equal(["1"])  # type: ignore[arg-type]
    with pytest.raises(OverflowError):
        DecimalScalar("1e400").to_floats()
    with pytest.raises(ValueError, match=r"entry \(1,\): .*exceeds"):
        _ = DecimalVector(["1", "1.5e5000"]).precisions


@dataclass(frozen=True)
class _DecimalGolden:
    __httk_storage__ = StorageInfo(identity_name="golden.decimal")
    value: object


def test_decimal_content_id_golden_pins() -> None:
    scalar = _DecimalGolden(DecimalScalar("1.2345(6)"))
    vector = _DecimalGolden(DecimalVector([["0.50", "?"], [".", "007"]]))
    assert canonical_form(scalar) == (
        '{"fields":[["value",{"type":"decimal_scalar","value":"1.2345(6)"}]],'
        '"identity_name":"golden.decimal","type":"record","version":2}'
    )
    assert content_id(scalar) == "c9b1e901919d28fcdb9be64706591ee8be4273599a49ed0c44fe02be50c799cd"
    assert content_id(vector) == "2c6ce3ad99ea90bd62085ed28f3e96a56791461fcc984676af15e1a6ed3380f3"
