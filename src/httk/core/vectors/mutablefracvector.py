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
A mutable, list-backed variant of :class:`~httk.core.vectors.fracvector.FracVector`.
"""

import fractions
import operator
from collections.abc import Callable
from math import gcd as calc_gcd
from typing import Any, ClassVar, NoReturn

from httk.core.vectors._nested import (
    list_set_slice,
    list_slice,
    nested_inmap_list,
    nested_map_fractions_list,
    nested_map_list,
)
from httk.core.vectors.fracvector import FracVector, FracVectorBase


class MutableFracVector(FracVectorBase):
    """
    Same as :class:`~httk.core.vectors.fracvector.FracVector`, only this version allows
    assignment of elements, e.g.::

        mfracvec[2, 7] = 5

    and, e.g.::

        mfracvec[:, 7] = [1, 2, 3, 4]

    Other than this, the FracVector methods exist and do the same, i.e., they return *copies*
    of the fracvector, rather than modifying it.

    :param values: A rational value-like to convert, such as nested sequences or scalars.
    :param denom: An optional additional common denominator.
    :param simplify: Whether to reduce the resulting denominator.
    :param chain: Whether to flatten the outermost nested sequence.
    :param min_accuracy: Minimum accuracy for decimal values, or ``None`` for exact conversion.

    Methods with ``set_*`` prefixes perform mutating operations, e.g.::

       A.set_T()

    replaces A with its own transpose, whereas::

       A.T()

    just returns a new MutableFracVector that is the transpose of A, leaving A unmodified.
    """

    # Implementation note: REMEMBER TO CALL 'self.invalidate()' if any mutation has been done on
    # the frac vector that may have broken cached properties, e.g., self._dim

    # Overloaded methods now replaced to be list-based rather than tuple-based
    nested_map: ClassVar[Callable[..., Any]] = staticmethod(nested_map_list)
    nested_inmap: ClassVar[Callable[..., Any]] = staticmethod(nested_inmap_list)
    nested_map_fractions: ClassVar[Callable[..., Any]] = staticmethod(nested_map_fractions_list)
    _dup_noms: ClassVar[Callable[..., Any]] = staticmethod(list)

    # MutableFracVector's nominators are list-based (and freely reassigned by the set_* methods),
    # so the recursive tuple-oriented Noms type from FracVector is loosened to Any here.
    noms: Any

    def __init__(
        self,
        values: Any,
        *,
        denom: int | None = None,
        simplify: bool = False,
        chain: bool = False,
        min_accuracy: fractions.Fraction | None = fractions.Fraction(1, 10000),
    ) -> None:
        super().__init__(
            values,
            denom=denom,
            simplify=simplify,
            chain=chain,
            min_accuracy=min_accuracy,
        )

    def validate(self) -> bool:
        """Return whether the vector's stored list structure is valid."""
        # TODO: check all dimensions and make sure noms is a square tensor of only lists
        return True

    def invalidate(self) -> None:
        """
        Internal method to call when the MutableFracVector is changed in such a way that cached
        properties are invalidated (e.g., ``_dim``).

        :return: None.
        """
        self._dim = None

    #### Python special overloads

    def __hash__(self) -> NoReturn:
        """
        Always raises: a mutable value must not be hashable.

        Hashing one would let it be used as a dict key or set member and then mutated out
        from under its own hash bucket. :class:`~httk.core.FracVector` is the immutable,
        hashable counterpart — call ``FracVector(self)`` first.

        Raises :class:`TypeError` specifically, which is what Python's data model
        prescribes for an unhashable type and what callers doing ``try: hash(x)`` expect.
        """
        raise TypeError(
            "MutableFracVector is mutable and therefore unhashable; "
            "call FracVector(self) for a hashable snapshot of its current value"
        )

    def __setitem__(self, key: Any, values: Any) -> None:
        if not isinstance(key, tuple):
            key = (key,)

        other = FracVector(values)
        one, two, denom = self.set_common_denom(self, other)
        self.noms = one.noms
        self.denom = denom
        list_set_slice(self.noms, key, two.noms)
        if not self.validate():
            raise Exception(
                "MutableFracVector: assignment slice: "
                + str(key)
                + " mismatch with vector dimensions: "
                + str(self.dim)
            )

    def __getitem__(self, key: Any) -> "MutableFracVector":
        if not isinstance(key, tuple):
            key = (key,)
        noms = list_slice(self.noms, key)
        return MutableFracVector._of(noms, self.denom)

    def set_negative(self) -> None:
        """
        Change the MutableFracVector inline into its own negative: ``self -> -self``.
        """
        nested_inmap_list(operator.neg, self.noms)

    def set_T(self) -> None:
        """
        Change the MutableFracVector inline into its own transpose: ``self -> self.T``.
        """
        # TODO: Possible to optimize?
        dim = self.dim
        noms = self.noms
        if len(dim) == 0:
            return
        elif len(dim) == 1:
            self.noms = [
                [
                    noms[col],
                ]
                for col in range(dim[0])
            ]
            return
        elif len(dim) == 2:
            self.noms = [[noms[col][row] for col in range(dim[0])] for row in range(dim[1])]
            return
        raise Exception("FracVector.T(): on non 1 or 2 dimensional object not implemented")

    def set_inv(self) -> Any:
        """
        Change the MutableFracVector inline into its own inverse: ``self -> self^-1``.

        :return: The inverse scalar when ``self`` is scalar; otherwise ``None`` after mutation.
        """
        dim = self.dim
        if dim == ():
            return self.__class__._of(self.denom, self.nom)

        if dim != (3, 3):
            raise Exception("FracVector.inv: only scalar and 3x3 matrix implemented")

        # We are dividing with a determinant giving self.denom**3 in nominator, and
        # from the matrix 1/self.denom**2 falls out => one factor of self.denom in nominator

        det = self.det()
        det_nom = det.nom

        if det_nom == 0:
            raise Exception("FracVector.inverse: cannot take inverse of singular matrix.")

        # The adjugate must be scaled by the ORIGINAL denominator (one factor of self.denom
        # falls out of the 1/self.denom**2 in the cofactors, cancelling against the self.denom**3
        # in the determinant). The legacy code reassigned self.denom *before* reading it into m,
        # so it scaled by the determinant instead -- leaving self a factor det_nom/orig_denom off
        # from FracVector.inv(). Capture the original denominator first.
        orig_denom = self.denom
        if det_nom < 0:
            self.denom = -det_nom
            m = -orig_denom
        else:
            self.denom = det_nom
            m = orig_denom

        A = self.noms
        self.noms = [
            [
                m * (A[1][1] * A[2][2] - A[1][2] * A[2][1]),
                m * (A[0][2] * A[2][1] - A[0][1] * A[2][2]),
                m * (A[0][1] * A[1][2] - A[0][2] * A[1][1]),
            ],
            [
                m * (A[1][2] * A[2][0] - A[1][0] * A[2][2]),
                m * (A[0][0] * A[2][2] - A[0][2] * A[2][0]),
                m * (A[0][2] * A[1][0] - A[0][0] * A[1][2]),
            ],
            [
                m * (A[1][0] * A[2][1] - A[1][1] * A[2][0]),
                m * (A[0][1] * A[2][0] - A[0][0] * A[2][1]),
                m * (A[0][0] * A[1][1] - A[0][1] * A[1][0]),
            ],
        ]

    def set_simplify(self) -> None:
        """
        Change the MutableFracVector; reduces any common factor between the denominator and all
        nominators.
        """
        if self.denom != 1:
            gcd = self._reduce_over_noms(lambda x, y: calc_gcd(x, abs(y)), initializer=self.denom)
            if gcd != 1:
                # Integer division keeps the denominator an int, matching FracVector.simplify().
                # (The legacy code used true division here, which turned self.denom into a float.)
                self.denom = self.denom // gcd
                self._inmap_over_noms(lambda x: int(x / gcd))

    def set_set_denominator(self, resolution: int = 1000000000) -> None:
        """
        Change the MutableFracVector; reduces resolution.

        :param resolution: The new denominator; each element becomes the closest numerical
                approximation using this denominator.
        """
        denom = self.denom

        def limit_resolution_one(x: int) -> int:
            low = (x * resolution) // denom
            if x * resolution * 2 > (low * 2 + 1) * denom:
                return low + 1
            else:
                return low

        self._inmap_over_noms(limit_resolution_one)
        self.denom = resolution

    def set_normalize(self) -> None:
        """
        Add/remove an integer +/-N to each element to place it in the range [0, 1).
        """
        self._inmap_over_noms(lambda x: x - self.denom * (x // self.denom))

    def set_normalize_half(self) -> None:
        """
        Add/remove an integer +/-N to each element to place it in the range [-1/2, 1/2).

        This is useful to find the shortest vector C between two points A, B in a space with
        periodic boundary conditions [0, 1)::

           C = (A - B).normalize_half()
        """
        self._inmap_over_noms(lambda x: 2 * x - (2 * self.denom) * ((((2 * x) // self.denom) + 1) // 2))
        self.denom = 2 * self.denom

    #### Private methods

    def _inmap_over_noms(self, op: Callable[..., Any], *others: FracVector) -> None:
        """Inmap an operation over all nominators."""
        othernoms = [x.noms for x in others]
        if isinstance(self.noms, (tuple, list)):
            self.nested_inmap(op, self.noms, *othernoms)
        else:
            self.noms = op(self.noms, *othernoms)
