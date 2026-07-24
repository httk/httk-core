#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
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

"""The OPTIMADE filter language as a first-class httk citizen.

This package makes the OPTIMADE filter language a standard httk query
feature: :func:`parse_optimade_filter` parses a filter string into a nested
tuple abstract syntax tree (the "ojf" format, :data:`FilterAst`), e.g.::

    ('AND', ('HAS_ALL', ('=', '='), ('Identifier', 'elements'),
             (('String', 'Ga'), ('String', 'Ti'))),
            ('OR', ('=', ('Identifier', 'nelements'), ('Number', '3')),
                   ('=', ('Identifier', 'nelements'), ('Number', '2'))))

It is the sibling of the vendored OPTIMADE property definitions in
``httk.core.optimade_defs`` — two halves of the same standard: the property
definitions describe what can be queried, and this package parses the query
language itself. The grammar is loaded from the packaged
``optimade_filter_grammar.ebnf`` (see the adjacent ``README.md`` for
provenance) and parsed by the vendored LR(1) parser generator in
``_miniparser``.

Errors raised on bad user input are :class:`ParserSyntaxError`; grammar
problems raise :class:`ParserGrammarError`; parser bugs raise
:class:`ParserInternalError`. All are subclasses of :class:`ParserError`.
"""

from ._miniparser import (
    ParserError,
    ParserGrammarError,
    ParserInternalError,
    ParserSyntaxError,
)
from .parser import (
    FilterAst,
    optimade_parse_tree_to_ojf,
    parse_optimade_filter,
    parse_optimade_filter_raw,
)

__all__ = [
    "parse_optimade_filter",
    "parse_optimade_filter_raw",
    "optimade_parse_tree_to_ojf",
    "FilterAst",
    "ParserError",
    "ParserSyntaxError",
    "ParserGrammarError",
    "ParserInternalError",
]
