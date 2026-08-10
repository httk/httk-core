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
Private helpers for mapping, reducing, slicing and building nested tuples/lists.

These functions are package-internal helpers for
:mod:`httk.core.vectors.fracvector` and
:mod:`httk.core.vectors.mutablefracvector`; they are not part of the public API.

Since the nested nominator structures are recursive and heterogeneous during
construction, these helpers are honestly typed with :data:`~typing.Any`.
"""

import random
from collections.abc import Callable
from functools import reduce
from typing import Any

from .vector_api import VectorAPI


def nested_map_tuple(op: Callable[..., Any], *ls: Any) -> Any:
    """
    Map an operator over a nested tuple (like the built-in :func:`map`, but recursive).

    Returns nested tuples.
    """
    if isinstance(ls[0], (tuple, list)):
        if len(ls[0]) == 0 or not isinstance(ls[0][0], (tuple, list)):
            return tuple(map(op, *ls))
        return tuple(map(lambda *items: nested_map_tuple(op, *items), *ls))
    return op(*ls)


def nested_map_list(op: Callable[..., Any], *ls: Any) -> Any:
    """
    Map an operator over a nested list (like the built-in :func:`map`, but recursive).

    Returns nested lists.
    """
    if isinstance(ls[0], (tuple, list)):
        if len(ls[0]) == 0 or not isinstance(ls[0][0], (tuple, list)):
            return list(map(op, *ls))
        return list(map(lambda *items: nested_map_list(op, *items), *ls))
    return op(*ls)


def nested_map_fractions_tuple(op: Callable[..., Any], *ls: Any) -> Any:
    """
    Map an operator over a nested tuple, but check every element for a ``to_fractions()``
    method and use it to further convert objects into tuples of Fraction.
    """
    items = list(ls)
    if isinstance(items[0], VectorAPI):
        if not items[0].fractions_exact:
            raise TypeError(
                "cannot build an exact FracVector from an inexact member; "
                "use to_fractions_approx(prec) or to_floats explicitly"
            )
        items[0] = items[0].fractions
    elif hasattr(items[0], 'to_fractions'):
        items[0] = items[0].to_fractions()
    if not isinstance(items[0], str):
        try:
            dummy: Any = iter(items[0])
        except TypeError:
            dummy = None
        if dummy is not None:
            return tuple(map(lambda *xs: nested_map_fractions_tuple(op, *xs), *items))
    return op(*items)


def nested_map_fractions_list(op: Callable[..., Any], *ls: Any) -> Any:
    """
    Map an operator over a nested list, but check every element for a ``to_fractions()``
    method and use it to further convert objects into lists of Fraction.
    """
    items = list(ls)
    if isinstance(items[0], VectorAPI):
        if not items[0].fractions_exact:
            raise TypeError(
                "cannot build an exact FracVector from an inexact member; "
                "use to_fractions_approx(prec) or to_floats explicitly"
            )
        items[0] = items[0].fractions
    elif hasattr(items[0], 'to_fractions'):
        items[0] = items[0].to_fractions()
    if not isinstance(items[0], str):
        try:
            iter(items[0])
            return list(map(lambda *xs: nested_map_fractions_list(op, *xs), *items))
        except TypeError:
            pass
    return op(*items)


def nested_inmap_list(op: Callable[..., Any], *ls: Any) -> None:
    """
    Like :func:`inmap`, but works for nested lists, replacing elements in place.
    """
    if isinstance(ls[0], (list, tuple)):
        if len(ls[0]) == 0 or not isinstance(ls[0][0], list):
            inmap(op, *ls)
            return
        inmap(lambda *items: nested_map_list(op, *items), *ls)
        return
    raise Exception(
        "nested_inmap_list: called with non-list, not possible to do inmap replacement on scalars:"
        + str(op)
        + ":"
        + str(ls)
    )


def nested_reduce(op: Callable[[Any, Any], Any], seq: Any, initializer: Any = None) -> Any:
    """
    Same as the built-in :func:`functools.reduce`, but operates on a nested tuple/list/sequence.
    """
    if isinstance(seq, (tuple, list)):
        return reduce(lambda x, y: nested_reduce(op, y, initializer=x), seq, initializer)
    else:
        return op(initializer, seq)


def nested_reduce_levels(op: Callable[[Any, Any], Any], seq: Any, level: int = 1, initializer: Any = None) -> Any:
    """
    Same as the built-in :func:`functools.reduce`, but operates on a nested tuple/list/sequence
    only down to the given number of ``level`` s.
    """
    if level == 1:
        return reduce(op, seq, initializer)
    if isinstance(seq, (tuple, list)):
        return reduce(lambda x, y: nested_reduce_levels(op, y, level - 1, initializer=x), seq, initializer)
    else:
        return op(initializer, seq)


def nested_reduce_fractions(op: Callable[[Any, Any], Any], seq: Any, initializer: Any = None) -> Any:
    """
    Same as the built-in :func:`functools.reduce`, but operates on a nested tuple/list/sequence.
    Also checks every element for a ``to_fractions()`` method and uses it to further convert
    such elements to lists of fractions.
    """
    if hasattr(seq, 'to_fractions'):
        seq = seq.to_fractions()
    if not isinstance(seq, str):
        try:
            iter(seq)
            return reduce(lambda x, y: nested_reduce_fractions(op, y, initializer=x), seq, initializer)
        except TypeError:
            pass
    return op(initializer, seq)


def tuple_slice(seq: Any, key: tuple[Any, ...]) -> Any:
    """
    Given a Python slice (i.e., what :meth:`__getitem__` receives when you write ``A[3:2]``),
    cut out the relevant nested tuple.
    """
    if isinstance(key[0], (int, slice)):
        slicedlist = seq[key[0]]
    else:
        slicedlist = tuple([seq[i] for i in key[0]])
    cdr = key[1:]
    if len(cdr) > 0:
        if isinstance(key[0], slice):
            return tuple(tuple_slice(slicedlist[i], cdr) for i in range(len(slicedlist)))
        else:
            return tuple_slice(slicedlist, cdr)
    return slicedlist


def tuple_index(dims: tuple[int, ...], uppidx: tuple[int, ...] = ()) -> Any:
    """
    Create a nested tuple where every element is a tuple indicating the position of that element.
    """
    if dims == ():
        if len(uppidx) == 1:
            return uppidx[0]
        else:
            return uppidx
    else:
        neweye = []
        lastdim = dims[0]
        lowerdims = dims[1:]
        for i in range(lastdim):
            neweye += [tuple_index(lowerdims, uppidx + (i,))]
    return neweye


def tuple_zeros(dims: tuple[int, ...]) -> Any:
    """
    Create a nested tuple with the given dimensions filled with zeroes.
    """
    if dims == ():
        return 0
    else:
        neweye = []
        lastdim = dims[0]
        lowerdims = dims[1:]
        for _ in range(lastdim):
            neweye += [tuple_zeros(lowerdims)]
    return neweye


def tuple_random(dims: tuple[int, ...], minval: int, maxval: int) -> Any:
    """
    Create a nested tuple with the given dimensions filled with random numbers between minval and maxval.
    """
    if dims == ():
        return random.randint(minval, maxval)
    else:
        neweye = []
        lastdim = dims[0]
        lowerdims = dims[1:]
        for _ in range(lastdim):
            neweye += [tuple_random(lowerdims, minval, maxval)]
    return neweye


def tuple_eye(dims: tuple[int, ...], onepos: int = 0) -> Any:
    """
    Create a matrix with the given dimensions and 1 on the diagonal.
    """
    if dims == ():
        return 1

    if len(dims) == 1:
        neweye = [0] * dims[0]
        neweye[onepos] = 1

    else:
        neweye = []
        lastdim = dims[-1]
        nextdim = dims[-2]
        lowerdims = dims[:-1]
        for i in range(lastdim):
            neweye += [tuple_eye(lowerdims, onepos=(i * nextdim // lastdim))]
    return neweye


def list_slice(seq: Any, key: tuple[Any, ...]) -> Any:
    """
    Given a Python slice (i.e., what :meth:`__getitem__` receives when you write ``A[3:2]``),
    cut out the relevant nested list.
    """
    if isinstance(key[0], (int, slice)):
        slicedlist = seq[key[0]]
    else:
        slicedlist = tuple([seq[i] for i in key[0]])
    cdr = key[1:]
    if len(cdr) > 0:
        if isinstance(key[0], slice):
            return tuple(list_slice(slicedlist[i], cdr) for i in range(len(slicedlist)))
        else:
            return list_slice(slicedlist, cdr)
    return slicedlist


def list_set_slice(seq: Any, key: tuple[Any, ...], values: Any) -> None:
    """
    Given a list ``seq``, a Python slice ``key`` (i.e., what :meth:`__setitem__` receives when
    you write ``A[3:2] = [2, 5]``), and a list of ``values``, change the elements specified by
    the slice in ``key`` to those given by ``values``.
    """
    if len(key) == 1:
        if isinstance(key[0], slice):
            seq[key[0]] = list(values)
        else:
            seq[key[0]] = values
        return

    if isinstance(key[0], int):
        list_set_slice(seq[key[0]], key[1:], values)
    elif isinstance(key[0], slice):
        idxs = key[0].indices(len(seq))
        for i, idx in enumerate(range(*idxs)):
            list_set_slice(seq[idx], key[1:], values[i])
    else:
        for i, idx in enumerate(key[0]):
            list_set_slice(seq[idx], key[1:], values[i])


def inmap(f: Callable[[Any], Any], x: Any) -> None:
    """
    Like the built-in :func:`map`, but work on a list and *replace* the elements in the list
    with the result of the mapping.
    """
    for i, v in enumerate(x):
        x[i] = f(v)
