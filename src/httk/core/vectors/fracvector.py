#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2015 Rickard Armiento
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Exact-rational vector (tensor) algebra: :class:`FracVector` and :class:`FracScalar`.
"""

import fractions
import itertools
import math
import operator
from collections.abc import Callable
from functools import reduce
from math import gcd as calc_gcd
from typing import Any, ClassVar, Self, cast

from httk.core.vectors import exactmath
from httk.core.vectors._nested import (
    nested_map_fractions_tuple,
    nested_map_list,
    nested_map_tuple,
    nested_reduce,
    nested_reduce_fractions,
    nested_reduce_levels,
    tuple_eye,
    tuple_index,
    tuple_random,
    tuple_slice,
    tuple_zeros,
)
from httk.core.vectors.exactmath import (
    any_to_fraction,
    best_rational_in_interval,
    string_to_val_and_delta,
)

# The nested nominator structure is recursive: either a bare integer (a scalar) or a
# (possibly nested) tuple of such structures. A single shared integer denominator is
# stored separately in FracVector.denom.
type Noms = int | tuple[Noms, ...]


def _noms_equal(a: Any, b: Any) -> bool:
    """
    Structural equality of two nested nominator sequences.

    ``FracVector`` stores nominators as nested tuples while ``MutableFracVector`` stores them as
    nested lists, and a nested ``list`` never compares ``==`` to an otherwise-identical nested
    ``tuple``. This helper compares them tolerant of that difference while keeping the common
    same-type case on the fast C-level ``==`` path.
    """
    if a == b:
        return True
    a_seq = isinstance(a, (list, tuple))
    b_seq = isinstance(b, (list, tuple))
    if a_seq and b_seq and type(a) is not type(b):
        if len(a) != len(b):
            return False
        return all(_noms_equal(x, y) for x, y in zip(a, b))
    return False


class FracVector:
    """
    FracVector is a general *immutable* N-dimensional vector (tensor) class for performing
    linear algebra with fractional numbers.

    A FracVector consists of a multidimensional tuple of integer nominators, and a single
    shared integer denominator.

    Since FracVectors are immutable, every operation on a FracVector returns a new FracVector
    with the result of the operation. A created FracVector never changes. Hence, they are safe
    to use as keys in dictionaries, to use in sets, etc.

    Note: most methods return FracVector results that are not simplified (i.e., the FracVector
    returned does *not* have the smallest possible integer denominator). To return a FracVector
    with the smallest possible denominator, just call :meth:`simplify` at the last step.
    """

    #### Static methods to overload in subclasses

    # a map-type function that handles nested sequences
    nested_map: ClassVar[Callable[..., Any]] = staticmethod(nested_map_tuple)
    # a map-type function that handles nested sequences and objects that can be converted into fractions
    nested_map_fractions: ClassVar[Callable[..., Any]] = staticmethod(nested_map_fractions_tuple)
    # a method used to copy the nominator sequence
    _dup_noms: ClassVar[Callable[..., Any]] = staticmethod(tuple)

    noms: Noms
    denom: int
    _dim: tuple[int, ...] | None
    # Class-level default so subclasses that build instances through __new__ without
    # running FracVector.__init__ (the view classes do) still have a defined cache slot.
    _hash_cache: int | None = None

    #### Creation

    def __init__(self, noms: Noms, denom: int = 1) -> None:
        """
        Low overhead constructor.

        Args:
            noms: nested *tuples* (may not be lists!) of nominator integers.
            denom: the integer denominator.

        Represents the tensor ``(1/denom)*(noms)``.

        If you want to create a FracVector from something else than tuples, use the
        :meth:`create` method.
        """
        self.noms = noms
        self.denom = denom
        self._dim = None
        self._hash_cache = None

    @classmethod
    def use(cls, old: Any) -> "FracVector":
        """
        Make sure the variable is a FracVector, and if not, convert it.
        """
        # Live fast path: anything exposing to_FracVector() (e.g. a MutableFracVector) is
        # converted through it into a plain FracVector. (The legacy code called cls.__init__
        # on the result, which returned None, so this path never actually took effect.)
        to_fracvector = getattr(old, "to_FracVector", None)
        if to_fracvector is not None:
            fracvec = to_fracvector()
            return cls(fracvec.noms, fracvec.denom)
        # A plain FracVector (no conversion of its own) is returned unchanged; anything else is
        # built from scratch.
        if isinstance(old, FracVector):
            return old
        return cls.create(old)

    @classmethod
    def create(
        cls,
        noms: Any,
        denom: int | None = None,
        simplify: bool = True,
        chain: bool = False,
        min_accuracy: fractions.Fraction | None = fractions.Fraction(1, 10000),
    ) -> Self:
        """
        Create a FracVector from various types of sequences.

        Simplest use::

          FracVector.create(some_kind_of_sequence)

        where 'some_kind_of_sequence' can be any nested list or tuple of objects that can be
        used in the constructor of the Python Fraction class (also works with strings!). If any
        object found while traveling the items has a ``.to_fractions()`` method, it will be called
        and is expected to return a fraction or list or tuple of fractions.

        Args:
            noms: any nested sequence of Fraction-constructible objects.
            denom: an optional common denominator to divide all nominators with.
            simplify: if True, return a FracVector with the smallest possible denominator.
            chain: if True, remove the outermost dimension and chain the sub-sequences. I.e.,
                if ``input=[[1, 2, 3], [4, 5, 6]]`` then ``FracVector.create(input)`` gives
                ``[1, 2, 3, 4, 5, 6]``.
            min_accuracy: the minimum accuracy assumed in string input. The default is
                ``1/10000``, i.e. ``0.33 = 0.3300 = 33/100``, whereas ``0.3333 = 1/3``. Set it
                to None to assume infinite accuracy, i.e. convert exactly whatever string is
                given (unless a standard deviation is given as a parenthesis after the string).

        Note: FracVector itself implements ``.to_fractions()``, and hence the same constructor
        allows stacking several FracVector objects like this::

            vertical_fracvector = FracVector.create([[fracvector1], [fracvector2]])
            horizontal_fracvector = FracVector.create([fracvector1, fracvector2], chain=True)
        """

        def getlcd(a: Any, y: Any) -> Any:
            b = abs(y).denominator
            return a * b // calc_gcd(a, b)

        def getnumerators(x: Any) -> Any:
            return (x * lcd).numerator

        fracnoms = cls.nested_map_fractions(lambda x: any_to_fraction(x, min_accuracy=min_accuracy), noms)

        lcd = nested_reduce_fractions(lambda x, y: getlcd(x, y), fracnoms, initializer=1)
        v_noms = cls.nested_map_fractions(lambda x: getnumerators(x), fracnoms)

        if chain:
            v_noms = cls._dup_noms(itertools.chain(*v_noms))

        if denom is None:
            v = cls(v_noms, lcd)
        else:
            v = cls(v_noms, lcd * denom)

        if simplify and v.denom != 1:
            v = v.simplify()

        return v

    # TODO: Integrate improvements in create_fast in create
    @classmethod
    def create_fast(
        cls,
        noms: Any,
        common_denom: int = 1,
        max_denom: int | None = None,
        denom: int | None = None,
        simplify: bool = True,
        chain: bool = False,
    ) -> Self:
        """
        Optimized version of :meth:`create` that takes advantage of the fact that the type of
        ``noms`` is a nested list of ints (of depth 2 or 3) over a single ``common_denom``.
        """

        def getlcd(a: Any, y: Any) -> Any:
            b = abs(y).denominator
            return a * b // calc_gcd(a, b)

        depth: int | None = None
        try:
            tmp = noms[0]
        except Exception:
            depth = 0

        if depth is None:
            depth = 1
            tmp = noms[0]
            while True:
                try:
                    tmp = tmp[0]
                    depth += 1
                except Exception:
                    break

        # Creates a tuple of tuples of Fraction
        if max_denom is not None:
            if max_denom <= common_denom:
                # Round nominators to correspond to the desired max_denom.
                ratio = max_denom / common_denom
                if depth == 2:
                    noms = tuple(
                        map(lambda sub_ls: tuple(map(lambda integer: int(round(integer * ratio, 0)), sub_ls)), noms)
                    )
                elif depth == 3:
                    noms = tuple(
                        map(
                            lambda sub_ls: tuple(
                                map(
                                    lambda sub_sub_ls: tuple(
                                        map(lambda integer: int(round(integer * ratio, 0)), sub_sub_ls)
                                    ),
                                    sub_ls,
                                )
                            ),
                            noms,
                        )
                    )
                common_denom = max_denom

        # noms is list of lists
        fracnoms: Any
        lcd: Any
        v_noms: Any
        if depth == 2:
            fracnoms = tuple(
                map(lambda sub_ls: tuple(map(lambda integer: fractions.Fraction(integer, common_denom), sub_ls)), noms)
            )
            lcd = reduce(
                lambda sub_ls1, sub_ls2: reduce(lambda frac1, frac2: getlcd(frac1, frac2), sub_ls2, sub_ls1),
                fracnoms,
                1,
            )
            v_noms = tuple(map(lambda sub_ls: tuple(map(lambda frac: (frac * lcd).numerator, sub_ls)), fracnoms))

        elif depth == 3:
            fracnoms = tuple(
                map(
                    lambda sub_ls: tuple(
                        map(
                            lambda sub_sub_ls: tuple(
                                map(lambda integer: fractions.Fraction(integer, common_denom), sub_sub_ls)
                            ),
                            sub_ls,
                        )
                    ),
                    noms,
                )
            )
            lcd = reduce(
                lambda sub_ls1, sub_ls2: reduce(
                    lambda sub_sub_ls1, sub_sub_ls2: reduce(
                        lambda frac1, frac2: getlcd(frac1, frac2), sub_sub_ls2, sub_sub_ls1
                    ),
                    sub_ls2,
                    sub_ls1,
                ),
                fracnoms,
                1,
            )
            v_noms = tuple(
                map(
                    lambda sub_ls: tuple(
                        map(lambda sub_sub_ls: tuple(map(lambda frac: (frac * lcd).numerator, sub_sub_ls)), sub_ls)
                    ),
                    fracnoms,
                )
            )

        else:
            raise Exception(
                "FracVector.create_fast: only depth 2 or 3 nested lists of ints are supported, got depth " + str(depth)
            )

        if chain:
            v_noms = cls._dup_noms(itertools.chain(*v_noms))

        if denom is None:
            v = cls(v_noms, lcd)
        else:
            v = cls(v_noms, lcd * denom)

        if simplify and v.denom != 1:
            v = v.simplify_fast(depth)

        return v

    # Note, these are different, and thus named different (get_ prefix), than the corresponding
    # methods in a list, since they do not modify the vector itself.

    def get_append(self, other: Any) -> Self:
        return self.__class__.create([self, [other]], chain=True)

    def get_extend(self, other: Any) -> Self:
        return self.__class__.create([self, other], chain=True)

    def get_insert(self, pos: int, other: Any) -> Self:
        return self.__class__.create([self[:pos], [other], self[pos:]], chain=True)

    def get_prepend(self, other: Any) -> Self:
        return self.__class__.create([[other], self], chain=True)

    def get_prextend(self, other: Any) -> Self:
        return self.__class__.create([other, self], chain=True)

    def get_stacked(self, other: Any) -> Self:
        """
        Return a new FracVector with ``other`` stacked after ``self`` along a new leading axis.

        ``self`` and ``other`` must have the same shape; the result gains one extra outermost
        dimension of size two (numpy ``stack``-like). E.g. stacking the row ``[1, 2, 3]`` with
        ``[4, 5, 6]`` gives ``[[1, 2, 3], [4, 5, 6]]``. (The legacy version wrapped ``other`` in a
        redundant extra list, producing a ragged, non-rectangular result.)
        """
        return self.__class__.create([self, other])

    def get_prestacked(self, other: Any) -> Self:
        """
        Return a new FracVector with ``other`` stacked before ``self`` along a new leading axis.

        The mirror of :meth:`get_stacked`: stacking ``[1, 2, 3]`` in front with ``[4, 5, 6]``
        gives ``[[4, 5, 6], [1, 2, 3]]``.
        """
        return self.__class__.create([other, self])

    def get_stackedinsert(self, pos: int, other: Any) -> Self:
        return self.__class__.create([self[:pos], [other], self[pos:]], chain=True)

    @classmethod
    def chain_vecs(cls, vecs: Any) -> Self:
        """
        Optimized chaining of FracVectors.

        Args:
            vecs: a list (or tuple) of fracvectors that all share the same denominator.

        Returns the same thing as ``FracVector.create(vecs, chain=True)``, i.e., removes the
        outermost dimension and chains the sub-sequences. If ``input=[[1, 2, 3], [4, 5, 6]]``
        then it gives ``[1, 2, 3, 4, 5, 6]``, but this method assumes all vectors share the
        same denominator (it raises an exception if this is not true).
        """
        noms: list[Any] = []
        denom = vecs[0].denom
        for vec in vecs:
            if vec.denom != denom:
                raise Exception("FracVector.merge: can only work with vectors sharing the same denom.")
            noms += vec.noms
        return cls(cls._dup_noms(noms), denom)

    @classmethod
    def stack_vecs(cls, vecs: Any) -> Self:
        """
        Optimized stacking of FracVectors.

        Args:
            vecs: a list (or tuple) of fracvectors that all share the same denominator.

        Returns the same thing as ``FracVector.create(vecs)``, but only works if all vectors
        share the same denominator (raises an exception if this is not true).
        """
        noms: list[Any] = []
        denom = vecs[0].denom
        for vec in vecs:
            if vec.denom != denom:
                raise Exception("FracVector.stack: can only work with vectors sharing the same denom.")
            noms += [vec.noms]
        return cls(cls._dup_noms(noms), denom)

    @classmethod
    def eye(cls, dims: tuple[int, ...]) -> Self:
        """
        Create a diagonal one-matrix with the given dimensions.
        """
        return cls.create(tuple_eye(dims))

    @classmethod
    def zeros(cls, dims: tuple[int, ...]) -> Self:
        """
        Create a zero matrix with the given dimensions.
        """
        return cls.create(tuple_zeros(dims))

    @classmethod
    def random(cls, dims: tuple[int, ...], minnom: int = -100, maxnom: int = 100, denom: int = 100) -> Self:
        """
        Create a matrix with the given dimensions filled with random rational numbers.
        """
        return cls.create(tuple_random(dims, minval=minnom, maxval=maxnom), denom)

    @classmethod
    def from_tuple(cls, t: tuple[int, Noms]) -> Self:
        """
        Return a FracVector created from the tuple representation ``(denom, noms)``, as returned
        by the :meth:`to_tuple` method. ``from_tuple(v.to_tuple())`` reconstructs ``v`` exactly.
        """
        return cls(t[1], t[0])

    @classmethod
    def from_floats(cls, data: Any, resolution: int = 2**32) -> Self:
        """
        Create a FracVector from a (nested) list or tuple of floats. You can convert a numpy
        array with this method if you use ``A.tolist()``.

        Args:
            l: the (nested) list or tuple of floats.
            resolution: the resolution used for interpreting the given floating point numbers.
                Default is ``2**32``.
        """

        eps = (1.0 / resolution) * 0.1

        gcd = nested_reduce(lambda x, y: calc_gcd(x, abs(int((y + eps) * resolution))), data, initializer=resolution)
        noms = cls.nested_map(lambda x: int((x + eps) * resolution) // gcd, data)
        denom = resolution // gcd

        return cls(noms, denom)

    @classmethod
    def _create_func(cls, data: Any, func: Callable[..., Any], find_best_rational: bool = True, **args: Any) -> Self:
        def apply_func(arg: Any) -> Any:
            if isinstance(arg, str):
                if find_best_rational:
                    val, delta = string_to_val_and_delta(arg)
                    low = val - delta
                    high = val + delta
                    lowval = func(low, **args)
                    highval = func(high, **args)
                    return best_rational_in_interval(lowval, highval)
                else:
                    val, delta = string_to_val_and_delta(arg)
                    if 'prec' in args:
                        low = val - fractions.Fraction(args['prec']) * 10
                        high = val + fractions.Fraction(args['prec']) * 10
                    else:
                        low = val - fractions.Fraction(1, 100000000000)
                        high = val + fractions.Fraction(1, 100000000000)
                    lowval = func(low, **args)
                    highval = func(high, **args)
                    return best_rational_in_interval(lowval, highval)
            else:
                try:
                    return func(arg.to_fraction())
                except Exception:
                    return func(fractions.Fraction(arg))

        newdata = nested_map_tuple(apply_func, data)
        return cls.create(newdata)

    @classmethod
    def create_cos(
        cls,
        data: Any,
        degrees: bool = False,
        limit: bool = False,
        find_best_rational: bool = True,
        prec: fractions.Fraction = fractions.Fraction(1, 1000000),
    ) -> Self:
        """
        Create a FracVector as the cosine of the argument ``data``. If ``data`` is composed of
        strings, the standard deviation of the numbers is taken into account, and the best
        possible fractional approximation to the cosines of the data is returned within the
        standard deviation.

        This is not the same as ``FracVector.create(data).cos()``, which creates the best
        possible fractional approximations of ``data`` and then takes cos on that.
        """
        return cls._create_func(
            data, exactmath.cos, find_best_rational=find_best_rational, degrees=degrees, limit=limit, prec=prec
        )

    @classmethod
    def create_sin(
        cls,
        data: Any,
        degrees: bool = False,
        limit: bool = False,
        prec: fractions.Fraction = fractions.Fraction(1, 1000000),
    ) -> Self:
        """
        Create a FracVector as the sine of the argument ``data``. If ``data`` is composed of
        strings, the standard deviation of the numbers is taken into account, and the best
        possible fractional approximation to the sines of the data is returned within the
        standard deviation.

        This is not the same as ``FracVector.create(data).sin()``, which creates the best
        possible fractional approximations of ``data`` and then takes sin on that.
        """
        return cls._create_func(data, exactmath.sin, degrees=degrees, limit=limit, prec=prec)

    @classmethod
    def create_exp(
        cls, data: Any, prec: fractions.Fraction = fractions.Fraction(1, 1000000), limit: bool = False
    ) -> Self:
        """
        Create a FracVector as the exponent of the argument ``data``. If ``data`` is composed of
        strings, the standard deviation of the numbers is taken into account, and the best
        possible fractional approximation to the exponents of the data is returned within the
        standard deviation.

        This is not the same as ``FracVector.create(data).exp()``, which creates the best
        possible fractional approximations of ``data`` and then takes exp on that.
        """
        return cls._create_func(data, exactmath.exp, limit=limit, prec=prec)

    @classmethod
    def pi(cls, prec: fractions.Fraction = fractions.Fraction(1, 1000000), limit: bool = False) -> Self:
        """
        Create a scalar FracVector with a rational approximation of pi to precision ``prec``.
        """
        return cls.create(exactmath.pi(prec, limit=limit))

    #### Properties

    @property
    def dim(self) -> tuple[int, ...]:
        """
        A tuple with the dimensionality of each dimension of the FracVector (the noms are
        assumed to be a nested list of rectangular shape).
        """
        if self._dim is None:
            dimchk: Any = self.noms
            dims: list[int] = []
            while True:
                try:
                    d = len(dimchk)
                except TypeError:
                    break
                if d > 0:
                    dims.append(d)
                    dimchk = dimchk[0]
                else:
                    break
            self._dim = tuple(dims)
        return self._dim

    @property
    def nom(self) -> int:
        """
        Return the integer nominator of a scalar FracVector.
        """
        if self.dim != ():
            raise Exception("FracVector.nom: attempt to access scalar nominator on non-scalar FracVector:" + str(self))
        return cast(int, self.noms)

    #### Methods

    def validate(self) -> bool:
        # TODO: check all dimensions and make sure noms is a square tensor of only tuples
        return True

    def to_tuple(self) -> tuple[int, Noms]:
        """
        Return the FracVector on tuple representation ``(denom, ...noms...)``.
        """
        return (self.denom, self.noms)

    def to_floats(self) -> Any:
        """
        Convert the FracVector to a (nested) list of floats.
        """

        def to_floats_nan_check(x: Any, denom: int) -> float:
            # A nominator is normally an exact (arbitrary-precision) int; guard the NaN
            # test with an isinstance check so math.isnan() never tries to convert a very
            # large exact integer to a float first (which would overflow).
            if isinstance(x, float):
                return x if math.isnan(x) else x / denom
            return float(fractions.Fraction(x, denom))

        return nested_map_list(lambda x: to_floats_nan_check(x, self.denom), self.noms)

    def to_float(self) -> float:
        """
        Convert a scalar FracVector to a single float.
        """
        return float(fractions.Fraction(self.nom, self.denom))

    def to_fractions(self) -> Any:
        """
        Convert the FracVector to a (nested) list of fractions.
        """
        return nested_map_list(lambda x: fractions.Fraction(x, self.denom), self.noms)

    def to_ints(self) -> Any:
        """
        Convert the FracVector to a (nested) list of integers, rounded off as best possible.
        """
        return nested_map_list(lambda x: round(fractions.Fraction(x, self.denom)), self.noms)

    def to_strings(self, accuracy: int = 8) -> Any:
        """
        Convert the FracVector to a (nested) list of strings.
        """
        return nested_map_list(lambda x: ("%." + str(accuracy) + "f") % (fractions.Fraction(x, self.denom),), self.noms)

    def to_string(self, accuracy: int = 8) -> str:
        """
        Convert a scalar FracVector to a single string.
        """
        return ("%." + str(accuracy) + "f") % (fractions.Fraction(self.nom, self.denom),)

    def to_fraction(self) -> fractions.Fraction:
        """
        Convert a scalar FracVector to a fraction.
        """
        return fractions.Fraction(self.nom, self.denom)

    def to_int(self) -> int:
        """
        Convert a scalar FracVector to an integer (truncating as necessary).
        """
        return int(self)

    def flatten(self) -> Self:
        """
        Return a FracVector that has been flattened out to a single row vector.
        """
        noms = nested_reduce(lambda x, y: x + [y], self.noms, initializer=[])
        return self.__class__(self._dup_noms(noms), self.denom)

    @classmethod
    def set_common_denom(cls, A: Any, B: Any) -> tuple[Self, Self, int]:
        """
        Used internally to combine two different FracVectors.

        Returns a tuple ``(A2, B2, denom)`` where A2 is numerically equal to A, and B2 is
        numerically equal to B, but A2 and B2 are both set on the same shared denominator
        ``denom``, which is the *product* of the denominators of A and B.
        """

        if not isinstance(A, FracVector):
            A = cls(A, 1)

        if not isinstance(B, FracVector):
            B = cls(B, 1)

        denom = A.denom * B.denom
        mA = B.denom
        mB = A.denom

        Anoms = A._map_over_noms(lambda x: x * mA)
        Bnoms = B._map_over_noms(lambda x: x * mB)

        return cls(Anoms, denom), cls(Bnoms, denom), denom

    def sign(self) -> int:
        """
        Return the sign of the scalar FracVector: -1, 0 or 1.
        """
        if self.dim != ():
            raise Exception("FracVector.sign: attempt to access scalar nominator on non-scalar FracVector.")
        if cast(int, self.noms) < 0:
            return -1
        elif cast(int, self.noms) > 0:
            return 1
        else:
            return 0

    def T(self) -> Self:
        """
        Return the transpose, ``A^T``.
        """
        dim = self.dim
        A = cast(Any, self.noms)
        if len(dim) == 0:
            return self.__class__(self.noms, self.denom)
        elif len(dim) == 1:
            noms = self._dup_noms((A[col],) for col in range(dim[0]))
            return self.__class__(noms, self.denom)
        elif len(dim) == 2:
            noms = self._dup_noms(self._dup_noms(A[col][row] for col in range(dim[0])) for row in range(dim[1]))
            return self.__class__(noms, self.denom)
        raise Exception("FracVector.T(): on non 1 or 2 dimensional object not implemented")

    def det(self) -> Self:
        """
        Return the determinant of the FracVector as a scalar FracVector.
        """
        dim = self.dim
        if dim == (3, 3):
            A = cast(Any, self.noms)
            noms = (
                A[0][0] * A[1][1] * A[2][2]
                + A[0][1] * A[1][2] * A[2][0]
                + A[0][2] * A[1][0] * A[2][1]
                - A[0][2] * A[1][1] * A[2][0]
                - A[0][1] * A[1][0] * A[2][2]
                - A[0][0] * A[1][2] * A[2][1]
            )
            return self.__class__(noms, self.denom**3)
        elif dim == (4, 4):
            A = cast(Any, self.noms)
            noms = (
                A[0][0] * A[1][1] * A[2][2] * A[3][3]
                + A[0][0] * A[2][1] * A[3][2] * A[1][3]
                + A[0][0] * A[3][1] * A[1][2] * A[2][3]
                + A[1][0] * A[0][1] * A[3][2] * A[2][3]
                + A[1][0] * A[2][1] * A[0][2] * A[3][3]
                + A[1][0] * A[3][1] * A[2][2] * A[0][3]
                + A[2][0] * A[0][1] * A[1][2] * A[3][3]
                + A[2][0] * A[1][1] * A[3][2] * A[0][3]
                + A[2][0] * A[3][1] * A[0][2] * A[1][3]
                + A[3][0] * A[0][1] * A[2][2] * A[1][3]
                + A[3][0] * A[1][1] * A[0][2] * A[2][3]
                + A[3][0] * A[2][1] * A[1][2] * A[0][3]
                - A[0][0] * A[1][1] * A[3][2] * A[2][3]
                - A[0][0] * A[2][1] * A[1][2] * A[3][3]
                - A[0][0] * A[3][1] * A[2][2] * A[1][3]
                - A[1][0] * A[0][1] * A[2][2] * A[3][3]
                - A[1][0] * A[2][1] * A[3][2] * A[0][3]
                - A[1][0] * A[3][1] * A[0][2] * A[2][3]
                - A[2][0] * A[0][1] * A[3][2] * A[1][3]
                - A[2][0] * A[1][1] * A[0][2] * A[3][3]
                - A[2][0] * A[3][1] * A[1][2] * A[0][3]
                - A[3][0] * A[0][1] * A[1][2] * A[2][3]
                - A[3][0] * A[1][1] * A[2][2] * A[0][3]
                - A[3][0] * A[2][1] * A[0][2] * A[1][3]
            )
            return self.__class__(noms, self.denom**4)

        raise Exception("FracVector.det: on non 3x3 or 4x4 matrix not implemented. Matrix was:" + str(dim))

    def inv(self) -> Self:
        """
        Return the matrix inverse, ``A^-1``.
        """
        dim = self.dim
        if dim == ():
            # For a FracScalar, just swap denominator and nominator
            return self.__class__(self.denom, self.nom)

        if dim != (3, 3):
            raise Exception("FracVector.inv: only scalar and 3x3 matrix implemented")

        # We are dividing with a determinant giving self.denom**3 in nominator, and
        # from the matrix 1/self.denom**2 falls out -> one factor of self.denom in nominator

        det = self.det()
        det_nom = det.nom

        if det_nom == 0:
            raise Exception("FracVector.inverse: cannot take inverse of singular matrix.")

        if det_nom < 0:
            denom = -det_nom
            m = -self.denom
        else:
            denom = det_nom
            m = self.denom

        A = cast(Any, self.noms)
        noms = self._dup_noms(
            (
                self._dup_noms(
                    (
                        m * (A[1][1] * A[2][2] - A[1][2] * A[2][1]),
                        m * (A[0][2] * A[2][1] - A[0][1] * A[2][2]),
                        m * (A[0][1] * A[1][2] - A[0][2] * A[1][1]),
                    ),
                ),
                self._dup_noms(
                    (
                        m * (A[1][2] * A[2][0] - A[1][0] * A[2][2]),
                        m * (A[0][0] * A[2][2] - A[0][2] * A[2][0]),
                        m * (A[0][2] * A[1][0] - A[0][0] * A[1][2]),
                    ),
                ),
                self._dup_noms(
                    (
                        m * (A[1][0] * A[2][1] - A[1][1] * A[2][0]),
                        m * (A[0][1] * A[2][0] - A[0][0] * A[2][1]),
                        m * (A[0][0] * A[1][1] - A[0][1] * A[1][0]),
                    ),
                ),
            )
        )

        return self.__class__(noms, denom)

    def simplify(self) -> Self:
        """
        Return a reduced FracVector. I.e., each element has the same numerical value but the
        new FracVector represents them using the smallest possible shared denominator.

        The result is *canonical*: two numerically equal FracVectors always simplify to the
        same ``(denom, noms)`` pair. That requires normalizing the sign as well as reducing
        by the greatest common divisor, since ``(1, 0, 0)/-2`` and ``(-1, 0, 0)/2`` are the
        same value and neither is reducible. Canonicality is what ``__hash__`` relies
        on to stay consistent with ``__eq__``.
        """
        noms = self.noms
        denom = self.denom

        if denom != 1:
            gcd = self._reduce_over_noms(lambda x, y: calc_gcd(x, abs(y)), initializer=abs(denom))
            # Dividing through by a negative divisor reduces and flips the sign in one pass,
            # which keeps this to a single traversal of the numerators. The division is
            # always exact, since the divisor divides the denominator and every numerator.
            divisor = gcd if denom > 0 else -gcd
            if divisor != 1:
                denom = denom // divisor
                noms = self._map_over_noms(lambda x: x // divisor)

        return self.__class__(noms, denom)

    # TODO: Integrate improvements in simplify_fast with simplify
    def simplify_fast(self, depth: int) -> Self:
        """
        Return a reduced FracVector, taking advantage of a known nesting ``depth``. I.e., each
        element has the same numerical value but the new FracVector represents them using the
        smallest possible shared denominator.
        """
        noms = self.noms
        denom = self.denom

        if self.denom != 1:
            if depth == 1:
                gcd = calc_gcd(cast(int, noms), denom)
            elif depth == 2:
                gcd = reduce(lambda sub_ls1, sub_ls2: reduce(lambda nom1, nom2: calc_gcd(nom1, abs(nom2)), sub_ls2, sub_ls1), noms, denom)  # type: ignore[arg-type]
            elif depth == 3:
                gcd = reduce(lambda sub_ls1, sub_ls2: reduce(lambda sub_sub_ls1, sub_sub_ls2: reduce(lambda nom1, nom2: calc_gcd(nom1, abs(nom2)), sub_sub_ls2, sub_sub_ls1), sub_ls2, sub_ls1), noms, denom)  # type: ignore[arg-type]
            else:
                raise Exception("FracVector.simplify_fast: only depth 1, 2 or 3 are supported, got depth " + str(depth))
            if gcd != 1:
                denom = denom // gcd
                noms = self._map_over_noms(lambda x: x // gcd)

        return self.__class__(noms, denom)

    def set_denominator(self, set_denom: int = 1000000000) -> Self:
        """
        Return a FracVector of reduced resolution where every element is the closest numerical
        approximation using this denominator.
        """
        denom = self.denom

        def limit_resolution_one(x: int) -> int:
            low = (x * set_denom) // denom
            if x * set_denom * 2 > (low * 2 + 1) * denom:
                return low + 1
            else:
                return low

        noms = self._map_over_noms(limit_resolution_one)
        return self.__class__(noms, set_denom)

    def limit_denominator(self, max_denom: int = 1000000000) -> Self:
        """
        Return a FracVector of reduced resolution.

        Each element in the returned FracVector is the closest numerical approximation that is
        allowed by a fraction with maximally this denominator. Note: since all elements must be
        put on a common denominator, the result may have a larger denominator than ``max_denom``.
        """
        denom = self.denom
        newvalues = self._map_over_noms(lambda x: fractions.Fraction(x, denom).limit_denominator(max_denom))
        return self.__class__.create(newvalues)

    def floor(self) -> int:
        """
        Return the integer that is equal to or just below the value stored in a scalar FracVector.
        """
        if self.dim != ():
            raise Exception("FracVector.floor: Needs scalar FracVector")
        # Python integer division really does floor, even for negative numbers
        return self.nom // self.denom

    def modf(self) -> tuple["FracVector", "FracVector"]:
        """
        Return the fractional and integer parts of each element as the pair
        ``(fractional, integer)`` of exact FracVectors sharing this vector's denominator.

        Both parts carry the sign of the element and the integer part truncates toward
        zero, matching the conventions of :func:`math.modf` (e.g. the value -5/2 splits
        into -1/2 and -2).
        """
        denom = self.denom

        def trunc_scaled(nom: int) -> int:
            return (nom // denom if nom >= 0 else -((-nom) // denom)) * denom

        integer_noms = self._map_over_noms(trunc_scaled)
        fractional_noms = self._map_over_noms(lambda nom: nom - trunc_scaled(nom))
        return (FracVector(fractional_noms, denom), FracVector(integer_noms, denom))

    def ceil(self) -> int:
        """
        Return the integer that is equal to or just above the value stored in a scalar FracVector.
        """
        if self.dim != ():
            raise Exception("FracVector.ceil: Needs scalar FracVector")
        if self.nom % self.denom == 0:
            return self.nom // self.denom
        else:
            return self.nom // self.denom + 1

    def normalize(self) -> Self:
        """
        Add/remove an integer +/-N to each element to place it in the range [0, 1).
        """
        noms = self._map_over_noms(lambda x: x - self.denom * (x // self.denom))
        return self.__class__(noms, self.denom)

    def normalize_half(self) -> Self:
        """
        Add/remove an integer +/-N to each element to place it in the range [-1/2, 1/2).

        This is useful to find the shortest vector C between two points A, B in a space with
        periodic boundary conditions [0, 1)::

           C = (A - B).normalize_half()
        """
        noms = self._map_over_noms(lambda x: 2 * x - (2 * self.denom) * ((((2 * x) // self.denom) + 1) // 2))
        return self.__class__(noms, 2 * self.denom)

    def mul(self, other: Any) -> Self:
        """
        Return the result of multiplying the vector with ``other`` using matrix multiplication.

        Note that for two 1D FracVectors, ``A.dot(B)`` is *not* the same as ``A.mul(B)``, but
        rather ``A.mul(B.T())``.
        """
        # Handle other being another object
        if not isinstance(other, FracVector):
            other = self.__class__.create(other)

        Adim = self.dim
        Bdim = other.dim
        A = cast(Any, self.noms)
        B = cast(Any, other.noms)
        denom = self.denom * other.denom

        # Other is scalar
        if Bdim == ():
            m = other.nom
            noms = self._map_over_noms(lambda x: x * m)

        # Self is scalar
        elif Adim == ():
            m = self.nom
            noms = other._map_over_noms(lambda x: x * m)

        # Vector * Vector
        elif len(Adim) == 1 and len(Bdim) == 1:
            if Adim[0] != Bdim[0]:
                raise Exception(
                    "FracVector.dot: vector multiplication dimension mismatch," + str(Adim) + " and " + str(Bdim)
                )
            noms = self._dup_noms(A[i] * B[i] for i in range(Adim[0]))

        # Matrix * vector
        elif len(Adim) == 2 and len(Bdim) == 1:
            if Adim[1] != Bdim[0]:
                raise Exception(
                    "FracVector.dot: matrix multiplication dimension mismatch," + str(Adim) + " and " + str(Bdim)
                )
            noms = self._dup_noms(sum([A[row][i] * B[i] for i in range(Adim[1])]) for row in range(Adim[0]))

        # vector * Matrix
        elif len(Adim) == 1 and len(Bdim) == 2:
            if Adim[0] != Bdim[0]:
                raise Exception(
                    "FracVector.dot: matrix multiplication dimension mismatch," + str(Adim) + " and " + str(Bdim)
                )
            noms = self._dup_noms(sum([A[i] * B[i][col] for i in range(Adim[0])]) for col in range(Bdim[1]))

        # Matrix * Matrix
        elif len(Adim) == 2 and len(Bdim) == 2:
            if Adim[1] != Bdim[0]:
                raise Exception(
                    "FracVector.dot: matrix multiplication dimension mismatch," + str(Adim) + " and " + str(Bdim)
                )
            noms = self._dup_noms(
                self._dup_noms(sum([A[row][i] * B[i][col] for i in range(Adim[1])]) for col in range(Bdim[1]))
                for row in range(Adim[0])
            )

        else:
            raise Exception(
                "FracVector.dot: cannot handle tensors of order > 2, dimensions:" + str(Adim) + " and " + str(Bdim)
            )

        return self.__class__(noms, denom)

    def dot(self, other: "FracVector") -> Self:
        """
        Return the vector dot product of the 1D vector with the 1D vector ``other``, i.e.,
        ``A . B``. The same as ``A * B.T()``.
        """
        Adim = self.dim
        Bdim = other.dim
        A = cast(Any, self.noms)
        B = cast(Any, other.noms)
        denom = self.denom * other.denom

        if len(Adim) == 1 and len(Bdim) == 1:
            if Adim[0] != Bdim[0]:
                raise Exception(
                    "FracVector.dot: vector multiplication dimension mismatch," + str(Adim) + " and " + str(Bdim)
                )
            noms = sum(A[i] * B[i] for i in range(Adim[0]))
        else:
            raise Exception("FracVector.dot: dot multiplication dimensions not = 1," + str(Adim) + " and " + str(Bdim))
        return self.__class__(noms, denom)

    def lengthsqr(self) -> Self:
        """
        Return the square of the length of the vector. The same as ``A * A.T()``.
        """
        # Other is scalar
        dim = self.dim
        noms_src = cast(Any, self.noms)

        if dim == ():
            noms = noms_src**2
        elif len(self.dim) == 1:
            noms = sum(noms_src[i] ** 2 for i in range(self.dim[0]))
        else:
            raise Exception("FracVector.lengthsqr: vector must be scalar or dimension must be = 1, is " + str(self.dim))
        return self.__class__(noms, self.denom**2)

    def cross(self, other: "FracVector") -> Self:
        """
        Return the vector cross product of the 3-element 1D vector with the 3-element 1D vector
        ``other``, i.e., ``A x B``.
        """
        # Note: multiplication is an especially simple case, there is no need to bring the two
        # vectors into a common denom with set_common_denom, since a/b * c/d = a*c/(b*d)
        Adim = self.dim
        A = cast(Any, self.noms)
        Bdim = other.dim
        B = cast(Any, other.noms)
        denom = self.denom * other.denom
        if Adim != (3,) or Bdim != (3,):
            raise Exception(
                "FracVector.cross: can only do cross products of 3-element 1D vectors. The dimensions are:"
                + str(Adim)
                + " and "
                + str(Bdim)
            )

        noms = ((A[1] * B[2] - A[2] * B[1]), (A[2] * B[0] - A[0] * B[2]), (A[0] * B[1] - A[1] * B[0]))

        return self.__class__(noms, denom)

    def reciprocal(self) -> Self:
        """
        Return the reciprocal matrix of a 3x3 matrix (the rows are the reciprocal vectors,
        without the ``2*pi`` factor).
        """
        dim = self.dim
        if dim != (3, 3):
            raise Exception(
                "FracVector.reciprocal: can only calculate reciprocal matrix for a 3,3 matrix. The dimension are:"
                + str(dim)
            )
        noms = cast(Any, self.noms)

        def det_noms(A: Any) -> Any:
            return (
                A[0][0] * A[1][1] * A[2][2]
                + A[0][1] * A[1][2] * A[2][0]
                + A[0][2] * A[1][0] * A[2][1]
                - A[0][2] * A[1][1] * A[2][0]
                - A[0][1] * A[1][0] * A[2][2]
                - A[0][0] * A[1][2] * A[2][1]
            )

        def cross_noms(A: Any, B: Any) -> Any:
            return ((A[1] * B[2] - A[2] * B[1]), (A[2] * B[0] - A[0] * B[2]), (A[0] * B[1] - A[1] * B[0]))

        detnom = det_noms(noms)
        denom = self.denom

        v1, v2, v3 = noms[0], noms[1], noms[2]
        noms = (cross_noms(v2, v3), cross_noms(v3, v1), cross_noms(v1, v2))
        noms = self.nested_map(lambda x: x * denom, noms)
        return self.__class__(noms, detnom)

    def metric_product(self, vecA: "FracVector", vecB: "FracVector") -> Self:
        """
        Return the result of the metric product using the present square FracVector as the
        metric matrix. The same as ``vecA * self * vecB.T()``.
        """

        dimM = cast(Any, self.dim)
        dimA = cast(Any, vecA.dim)
        dimB = cast(Any, vecB.dim)

        M = cast(Any, self.noms)
        A = cast(Any, vecA.noms)
        B = cast(Any, vecB.noms)

        denom = vecA.denom * vecB.denom * self.denom

        n = dimM[0]

        if dimA != dimB or dimM != (n, n) or ((len(dimA) != 1 or len(dimB) != 1) and (dimA[1] != n or dimB[1] != n)):
            raise Exception("FracVector.metric_product: vectors not in right dimensions.")

        noms: Any
        if len(dimA) == 1:
            noms = sum([A[row] * M[row][col] * B[col] for row in range(n) for col in range(n)])
        else:
            # Matrix * Matrix
            noms = [
                sum([A[i][row] * M[row][col] * B[i][col] for row in range(n) for col in range(n)])
                for i in range(dimA[0])
            ]

        return self.__class__(noms, denom)

    def cos(self, prec: fractions.Fraction | None = None, degrees: bool = False, limit: bool = False) -> Self:
        """
        Return a FracVector where every element is the cosine of the element in the source FracVector.

        Args:
            prec: the precision (should be set as a fraction).
            degrees: if True, interpret the elements in degrees.
            limit: if True, require the denominator to be smaller than or equal to the precision.
        """
        if prec is not None:
            fracs = self._map_over_noms(
                lambda nom: exactmath.cos(fractions.Fraction(nom, self.denom), prec=prec, limit=limit, degrees=degrees)
            )
        else:
            fracs = self._map_over_noms(
                lambda nom: exactmath.cos(fractions.Fraction(nom, self.denom), limit=limit, degrees=degrees)
            )
        return self.create(fracs)

    def sin(self, prec: fractions.Fraction | None = None, degrees: bool = False, limit: bool = False) -> Self:
        """
        Return a FracVector where every element is the sine of the element in the source FracVector.

        Args:
            prec: the precision (should be set as a fraction).
            degrees: if True, interpret the elements in degrees.
            limit: if True, require the denominator to be smaller than or equal to the precision.
        """
        if prec is not None:
            fracs = self._map_over_noms(
                lambda nom: exactmath.sin(fractions.Fraction(nom, self.denom), prec=prec, limit=limit, degrees=degrees)
            )
        else:
            fracs = self._map_over_noms(
                lambda nom: exactmath.sin(fractions.Fraction(nom, self.denom), limit=limit, degrees=degrees)
            )
        return self.create(fracs)

    def acos(self, prec: fractions.Fraction | None = None, degrees: bool = False, limit: bool = False) -> Self:
        """
        Return a FracVector where every element is the arccos of the element in the source FracVector.

        Args:
            prec: the precision (should be set as a fraction).
            degrees: if True, return the result in degrees.
            limit: if True, require the denominator to be smaller than or equal to the precision.
        """
        if prec is not None:
            fracs = self._map_over_noms(
                lambda nom: exactmath.acos(fractions.Fraction(nom, self.denom), prec=prec, limit=limit, degrees=degrees)
            )
        else:
            fracs = self._map_over_noms(
                lambda nom: exactmath.acos(fractions.Fraction(nom, self.denom), limit=limit, degrees=degrees)
            )
        return self.create(fracs)

    def asin(self, prec: fractions.Fraction | None = None, degrees: bool = False, limit: bool = False) -> Self:
        """
        Return a FracVector where every element is the arcsin of the element in the source FracVector.

        Args:
            prec: the precision (should be set as a fraction).
            degrees: if True, return the result in degrees.
            limit: if True, require the denominator to be smaller than or equal to the precision.
        """
        if prec is not None:
            fracs = self._map_over_noms(
                lambda nom: exactmath.asin(fractions.Fraction(nom, self.denom), prec=prec, limit=limit, degrees=degrees)
            )
        else:
            fracs = self._map_over_noms(
                lambda nom: exactmath.asin(fractions.Fraction(nom, self.denom), limit=limit, degrees=degrees)
            )
        return self.create(fracs)

    def exp(self, prec: fractions.Fraction | None = None, limit: bool = False) -> Self:
        """
        Return a FracVector where every element is the exponent of the element in the source FracVector.

        Args:
            prec: the precision (should be set as a fraction).
            limit: if True, require the denominator to be smaller than or equal to the precision.
        """
        if prec is not None:
            fracs = self._map_over_noms(
                lambda nom: exactmath.exp(fractions.Fraction(nom, self.denom), prec=prec, limit=limit)
            )
        else:
            fracs = self._map_over_noms(lambda nom: exactmath.exp(fractions.Fraction(nom, self.denom), limit=limit))
        return self.create(fracs)

    def sqrt(self, prec: fractions.Fraction | None = None, limit: bool = False) -> Self:
        """
        Return a FracVector where every element is the sqrt of the element in the source FracVector.

        Args:
            prec: the precision (should be set as a fraction).
            limit: if True, require the denominator to be smaller than or equal to the precision.
        """
        if prec is not None:
            fracs = self._map_over_noms(
                lambda nom: exactmath.sqrt(fractions.Fraction(nom, self.denom), prec=prec, limit=limit)
            )
        else:
            fracs = self._map_over_noms(lambda nom: exactmath.sqrt(fractions.Fraction(nom, self.denom), limit=limit))
        return self.create(fracs)

    #### Python special overloading

    def __getitem__(self, key: Any) -> Self:
        if not isinstance(key, tuple):
            key = (key,)
        noms = tuple_slice(self.noms, key)
        return self.__class__(noms, self.denom)

    def __setitem__(self, key: Any, values: Any) -> None:
        raise Exception("FracVector is immutable, use MutableFracVector instead.")

    def __len__(self) -> int:
        if isinstance(self.noms, (list, tuple)):
            return len(self.noms)
        else:
            return 0

    def __iter__(self) -> Any:
        try:
            if self.dim != ():
                noms = cast(Any, self.noms)
                for i in range(len(noms)):
                    yield self.__class__(noms[i], self.denom)
            else:
                yield self
        except GeneratorExit:
            pass

    def __mul__(self, other: Any) -> Self:
        return self.mul(other)

    def __rmul__(self, other: Any) -> "FracVector":
        other = FracVector.create(other)
        return other.mul(self)

    def __pow__(self, exp: int) -> Self:
        if exp == -1:
            return self.inv()
        if self.dim == ():
            if exp == 0:
                # Pass both nom and denom so this also works for FracScalar, whose constructor
                # requires two arguments (the legacy single-argument form crashed there).
                return self.__class__(1, 1)
            if exp > 0:
                return self.__class__(self.nom**exp, self.denom**exp)
            if exp < 0:
                return self.__class__(self.denom ** (-exp), self.nom ** (-exp))
        if isinstance(exp, int):
            if exp == 0:
                return self.eye(self.dim)
            if exp > 0:
                a = self
                for _ in range(exp - 1):
                    a = a.mul(self)
                return a
            if exp < 0:
                # A^(-n) = (A^-1)^n: keep multiplying by the inverse, not by self. (The legacy
                # loop multiplied by self, so e.g. A**-2 collapsed to the identity.)
                inv = self.inv()
                a = inv
                for _ in range(-exp - 1):
                    a = a.mul(inv)
                return a
            raise Exception("FracVector.__pow__: unreachable")
        else:
            raise Exception("FracVector.__pow__: I do not know how to exponate a FracVector with " + str(exp))

    def __truediv__(self, other: Any) -> Self:
        if not isinstance(other, FracVector):
            other = self.__class__.create(other)
        frac = self.__class__(other.denom, other.nom)
        return self.mul(frac)

    def __add__(self, other: Any) -> Self:
        noms, denom = self._map_binary_op_over_noms(operator.add, other)
        return self.__class__(noms, denom)

    def __radd__(self, other: Any) -> Self:
        noms, denom = self._map_binary_op_over_noms(operator.add, other)
        return self.__class__(noms, denom)

    def __sub__(self, other: Any) -> Self:
        noms, denom = self._map_binary_op_over_noms(operator.sub, other)
        return self.__class__(noms, denom)

    def __rsub__(self, other: Any) -> Self:
        minusself = -self
        noms, denom = minusself._map_binary_op_over_noms(operator.sub, -other)
        return self.__class__(noms, denom)

    def __repr__(self) -> str:
        return self.__class__.__name__ + "(" + repr(self.noms) + "," + repr(self.denom) + ")"

    def __str__(self) -> str:
        return "(1/" + str(self.denom) + ")*" + str(self.noms)

    def __hash__(self) -> int:
        """
        A hash consistent with ``__eq__``, which compares *numerically*.

        The stored ``(denom, noms)`` pair cannot be hashed directly: ``(1, 0, 0)/2`` and
        ``(2, 0, 0)/4`` are equal but represented differently, so hashing the raw pair
        would put equal vectors in different hash buckets and let a ``set`` or ``dict``
        hold what are really duplicates. Hashing the canonical form from :meth:`FracVector.simplify`
        removes the ambiguity. The result is cached, since a FracVector is immutable.
        """
        if self._hash_cache is None:
            simplified = self.simplify()
            self._hash_cache = hash((simplified.denom, simplified.noms))
        return self._hash_cache

    def __neg__(self) -> Self:
        return self.__class__(self._map_over_noms(operator.neg), self.denom)

    def __abs__(self) -> Self:
        return self.__class__(self._map_over_noms(operator.abs), self.denom)

    def __eq__(self, other: Any) -> bool:
        """
        Important: the == operator between FracVectors tests for numerical equality. (I.e.,
        numerically equal FracVectors with different denoms are still equal.)
        """
        # Note: somewhat optimized for speed
        try:
            if self.denom == other.denom:
                return _noms_equal(self.noms, other.noms)
            else:
                A, B, _ = self.set_common_denom(self, other)
                return _noms_equal(A.noms, B.noms)
        except AttributeError:
            if other is None:
                return False

            if not isinstance(other, FracVector):
                other = self.__class__.create(other)

            if other.dim != self.dim:
                return False

        if self.denom == other.denom:
            return _noms_equal(self.noms, other.noms)
        else:
            A, B, _ = self.set_common_denom(self, other)
            return _noms_equal(A.noms, B.noms)

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: Any) -> bool:
        try:
            return self.nom * other.denom < other.nom * self.denom
        except AttributeError:
            return self.nom < other * self.denom

    def __gt__(self, other: Any) -> bool:
        try:
            return self.nom * other.denom > other.nom * self.denom
        except AttributeError:
            return self.nom > other * self.denom

    def __le__(self, other: Any) -> bool:
        return not self.__gt__(other)

    def __ge__(self, other: Any) -> bool:
        return not self.__lt__(other)

    def __float__(self) -> float:
        # This way of converting avoids many possible overflow errors
        return float(fractions.Fraction(self.nom, self.denom))

    def __int__(self) -> int:
        return int(fractions.Fraction(self.nom, self.denom))

    def __index__(self) -> int:
        v = self.simplify()
        if v.denom != 1:
            raise Exception("FracVector.__index__: cannot index with non-integer value.")
        return v.nom

    def __complex__(self) -> complex:
        return complex(self.__float__())

    def max(self) -> Self:
        """
        Return the maximum element across all dimensions in the FracVector. ``max(fracvector)``
        works for a 1D vector.
        """
        return max(self.flatten())

    def nargmax(self) -> list[Any]:
        """
        Return a list of indices of all maximum elements across all dimensions in the FracVector.
        """
        idt = tuple_index(self.dim)
        maxval = self.max()
        indices = nested_reduce_levels(lambda x, y: x + [y] if self[y] == maxval else x, idt, len(self.dim), [])
        return indices

    def argmax(self) -> Any:
        """
        Return the index of the maximum element across all dimensions in the FracVector.
        """
        idt = tuple_index(self.dim)
        flat_idt = nested_reduce_levels(lambda x, y: x + [y], idt, len(self.dim), initializer=[])
        return max(flat_idt, key=lambda i: self[i])

    def min(self) -> Self:
        """
        Return the minimum element across all dimensions in the FracVector. ``min(fracvector)``
        works for a 1D vector.
        """
        return min(self.flatten())

    def nargmin(self) -> list[Any]:
        """
        Return a list of indices for all minimum elements across all dimensions in the FracVector.
        """
        idt = tuple_index(self.dim)
        minval = self.min()
        indices = nested_reduce_levels(lambda x, y: x + [y] if self[y] == minval else x, idt, len(self.dim), [])
        return indices

    def argmin(self) -> Any:
        """
        Return the index of the minimum element across all dimensions in the FracVector.
        """
        idt = tuple_index(self.dim)
        flat_idt = nested_reduce_levels(lambda x, y: x + [y], idt, len(self.dim), initializer=[])
        return min(flat_idt, key=lambda i: self[i])

    #### Private methods

    def _map_over_noms(self, op: Callable[..., Any], *others: "FracVector") -> Any:
        """
        Map an operation over all nominators.
        """
        othernoms = [x.noms for x in others]
        if isinstance(self.noms, (tuple, list)):
            return self.nested_map(op, self.noms, *othernoms)
        else:
            return op(self.noms, *othernoms)

    def _map_binary_op_over_noms(self, op: Callable[..., Any], other: Any) -> tuple[Any, int]:
        """
        Put self and other on common denominator form, and then map a binary operator over pairs
        of nominators, handling the cases where either of the operands is a scalar (thus pairing
        it with every nominator).
        """

        A, B, denom = self.set_common_denom(self, other)

        Adim = A.dim
        Bdim = B.dim

        if len(Adim) == 0:
            if len(Bdim) == 0:
                # scalar [op] scalar
                result = op(A.nom, B.nom)
            else:
                # scalar [op] (Matrix or Vector)
                result = B._map_over_noms(lambda x: op(A.nom, x))
        elif len(Bdim) == 0:
            # [Matrix or Vector] op scalar
            result = A._map_over_noms(lambda x: op(x, B.nom))
        else:
            # Matrix op Matrix
            result = A._map_over_noms(lambda x, y: op(x, y), B)

        return (result, denom)

    def _reduce_over_noms(self, op: Callable[[Any, Any], Any], initializer: Any = None) -> Any:
        """
        Run a nested reduce operation over all nominators.
        """
        return nested_reduce(op, self.noms, initializer=initializer)


class FracScalar(FracVector):
    """
    Represents the fractional number ``nom/denom``. This is a subclass of FracVector with the
    purpose of making it clear when a scalar fracvector is needed/used.
    """

    def __init__(self, nom: int, denom: int) -> None:
        """
        Low overhead constructor.

        Args:
            nom: the nominator (int).
            denom: the denominator (int).

        If you want to create a FracScalar from something else than integers, use the
        :meth:`create` method.
        """
        self.noms = nom
        self.denom = denom
        self._dim = ()

    @classmethod
    def create(
        cls,
        noms: Any,
        denom: int | None = None,
        simplify: bool = True,
        chain: bool = False,
        min_accuracy: fractions.Fraction | None = fractions.Fraction(1, 10000),
    ) -> Self:
        """
        Create a FracScalar.

        ``FracScalar.create(something)`` where ``something`` may be any object that can be used
        in the constructor of the Python Fraction class (also works with strings!).

        Note: for signature-compatibility with :meth:`FracVector.create`, this accepts ``chain``
        and ``min_accuracy``, but (as in the legacy implementation) it ignores them and converts
        strings exactly via the Fraction constructor.
        """

        def lcd_op(a: Any, y: Any) -> Any:
            try:
                b = abs(fractions.Fraction(y)).denominator
            except TypeError:
                b = abs(fractions.Fraction(str(y))).denominator
            return a * b // calc_gcd(a, b)

        def frac(x: Any) -> Any:
            return (fractions.Fraction(x) * lcd).numerator

        lcd = nested_reduce_fractions(lambda x, y: lcd_op(x, y), noms, initializer=1)
        v_noms = cls.nested_map_fractions(lambda x: frac(x), noms)

        if denom is None:
            v = cls(v_noms, lcd)
        else:
            v = cls(v_noms, lcd * denom)

        if simplify and v.denom != 1:
            v = v.simplify()

        return v
