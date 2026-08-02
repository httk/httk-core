"""The hash/equality contract for the exact vector classes.

Python requires that ``a == b`` implies ``hash(a) == hash(b)``. The vector classes compare
*numerically* — ``(1, 0, 0)/2`` equals ``(2, 0, 0)/4`` — so they must hash on a canonical
form rather than on their stored representation. Getting this wrong is not a loud failure:
a ``set`` or ``dict`` simply holds duplicates and lookups miss, which silently breaks any
algorithm that deduplicates exact coordinates.
"""

import fractions

import pytest

from httk.core import FracVector, SurdVector
from httk.core.vectors.mutablefracvector import MutableFracVector
from httk.core.vectors.vector_frac_view import VectorFracView
from httk.core.vectors.vector_surd_view import VectorSurdView

F = fractions.Fraction

#: Pairs that are numerically equal but stored differently: unreduced denominators, a
#: negative denominator, and the zero vector at two scales.
EQUAL_FRACVECTOR_PAIRS = [
    (FracVector((1, 0, 0), 2), FracVector((2, 0, 0), 4)),
    (FracVector((1, 0, 0), 2), FracVector((50, 0, 0), 100)),
    (FracVector((0, 0, 0), 1), FracVector((0, 0, 0), 4)),
    (FracVector((1, 0, 0), -2), FracVector((-1, 0, 0), 2)),
    (FracVector((-2, 4), -6), FracVector((1, -2), 3)),
    (FracVector((5,), 1), FracVector((-5,), -1)),
    (FracVector(((1, 2), (3, 4)), 2), FracVector(((3, 6), (9, 12)), 6)),
]


def _assert_hash_contract(first: object, second: object) -> None:
    """Equal values must hash alike, collapse in a set, and share a dict entry."""
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1
    assert {first: "a", second: "b"} == {first: "b"}


# --- FracVector ---


@pytest.mark.parametrize(("first", "second"), EQUAL_FRACVECTOR_PAIRS)
def test_equal_fracvectors_hash_alike(first: FracVector, second: FracVector) -> None:
    _assert_hash_contract(first, second)


def test_fracvector_created_by_different_arithmetic_paths_deduplicates() -> None:
    """The case that matters in practice: equal values reached by different routes.

    Arithmetic does not simplify as it goes, so the same value routinely arrives with
    different denominators, and a set of coordinates has to recognize them as one.
    """
    direct = FracVector.create([F(1, 3), F(1, 3), F(1, 3)])
    summed = FracVector.create([F(1, 6), F(1, 6), F(1, 6)]) + FracVector.create([F(1, 6), F(1, 6), F(1, 6)])
    scaled = FracVector.create([F(2, 3), F(2, 3), F(2, 3)]) * FracVector.create(F(1, 2))
    wrapped = FracVector.create([F(4, 3), F(7, 3), F(-2, 3)]).normalize()

    assert len({direct, summed, scaled, wrapped}) == 1


def test_fracvector_distinct_values_stay_distinct() -> None:
    """The contract is one-directional; unequal values must not be merged."""
    values = {
        FracVector.create([0, 0, 0]),
        FracVector.create([F(1, 2), 0, 0]),
        FracVector.create([0, F(1, 2), 0]),
        FracVector.create([F(-1, 2), 0, 0]),
    }
    assert len(values) == 4


def test_simplify_is_canonical() -> None:
    """Numerically equal vectors simplify to an identical stored representation."""
    for first, second in EQUAL_FRACVECTOR_PAIRS:
        assert first.simplify().denom == second.simplify().denom
        assert first.simplify().noms == second.simplify().noms
        assert first.simplify().denom > 0


def test_simplify_preserves_value_and_is_idempotent() -> None:
    for first, second in EQUAL_FRACVECTOR_PAIRS:
        for vector in (first, second):
            assert vector.simplify() == vector
            assert vector.simplify().simplify() == vector.simplify()


def test_fracvector_hash_is_stable_across_calls() -> None:
    vector = FracVector((6, 0, 0), 12)
    assert hash(vector) == hash(vector)
    assert vector == FracVector((1, 0, 0), 2)


# --- SurdVector ---


def test_equal_surdvectors_hash_alike() -> None:
    _assert_hash_contract(SurdVector.create(0), SurdVector.create(0) * SurdVector.create(5))

    root_two = SurdVector.sqrt_of(2)
    round_tripped = (root_two * FracVector.create(2)) * FracVector.create(F(1, 2))
    _assert_hash_contract(root_two, round_tripped)

    identity = SurdVector.create([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    _assert_hash_contract(identity, identity * SurdVector.create(1))


def test_surdvector_keeps_radicals_distinct() -> None:
    values = {
        SurdVector.sqrt_of(2),
        SurdVector.sqrt_of(3),
        SurdVector.create(1),
        SurdVector.create(0),
    }
    assert len(values) == 4


def test_surdvector_hash_matches_across_component_representations() -> None:
    """A surd whose rational coefficient arrives unreduced still hashes canonically.

    Built through the low-level constructor, which is where a component's stored form is
    decided, so this pins the canonicalization rather than the arithmetic that happens to
    feed it.
    """
    unreduced = SurdVector({3: FracVector(5, 10)}, ())
    reduced = SurdVector({3: FracVector(1, 2)}, ())
    _assert_hash_contract(unreduced, reduced)

    negative_denominator = SurdVector({2: FracVector(-1, -3)}, ())
    _assert_hash_contract(negative_denominator, SurdVector({2: FracVector(1, 3)}, ()))

    # And through arithmetic, where denominators routinely arrive unreduced.
    _assert_hash_contract(SurdVector.sqrt_of(3) * FracVector.create(F(1, 2)), reduced)


# --- views ---


def test_vector_views_inherit_the_hash_contract() -> None:
    """Views are genuine FracVector/SurdVector subclasses, so they must behave alike."""
    frac_view = VectorFracView(FracVector((2, 0, 0), 4))
    assert frac_view == FracVector((1, 0, 0), 2)
    assert hash(frac_view) == hash(FracVector((1, 0, 0), 2))
    assert len({frac_view, FracVector((1, 0, 0), 2)}) == 1

    surd_view = VectorSurdView(SurdVector.sqrt_of(2))
    assert surd_view == SurdVector.sqrt_of(2)
    assert hash(surd_view) == hash(SurdVector.sqrt_of(2))


# --- MutableFracVector ---


def test_mutable_fracvector_is_unhashable() -> None:
    """A mutable value must not be hashable, and must say so as a TypeError.

    Otherwise it could be stored in a set and then mutated out from under its own hash
    bucket.
    """
    mutable = MutableFracVector.create([[1, 2], [3, 4]])
    with pytest.raises(TypeError):
        hash(mutable)
    with pytest.raises(TypeError):
        {mutable}  # noqa: B018


def test_mutable_fracvector_snapshot_is_hashable_and_canonical() -> None:
    mutable = MutableFracVector.create([F(1, 2), 0, 0])
    snapshot = FracVector.create(mutable)
    assert hash(snapshot) == hash(FracVector((2, 0, 0), 4))

    mutable[0] = F(3, 4)
    # The snapshot is a value, not a live view: mutating the source must not change it.
    assert snapshot == FracVector.create([F(1, 2), 0, 0])
