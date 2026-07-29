"""Parsing OPTIMADE filter strings into an abstract syntax tree

An OPTIMADE query arrives as a string — `elements HAS ALL "Ga","Ti" AND
nelements=3`. Before anything can be done with it, it has to become structure.
`httk.core.parse_optimade_filter` does exactly that and nothing more: it runs
the filter string against the OPTIMADE grammar (transcribed from the
specification's appendix and vendored inside *httk-core*) and returns the query
as a tree of plain Python tuples. It does not evaluate, optimize, or translate
the query — a database backend does that, by walking the tree this function
returns.

The tree contains only tuples and strings. Every node is
`(operator, *operands)`:

- **Leaves** are two-element tuples tagging a token with its kind:
  `('Identifier', 'nelements')`, `('Number', '3')`, `('String', 'Ga')`,
  `('Boolean', 'TRUE')`. Values stay as *text*; interpreting `'3'` as an
  integer is the backend's business, since the right numeric type depends on
  the property being compared.
- A **nested identifier** simply grows more elements:
  `cartesian_site_positions.x` becomes
  `('Identifier', 'cartesian_site_positions', 'x')`.
- **Comparisons** are `(op, left, right)` where `op` is one of `=`, `!=`, `<`,
  `<=`, `>`, `>=`, or one of the string operators `CONTAINS`, `STARTS`, `ENDS`.
  Either side may be the constant — `"Ga" = chemical_formula_descriptive`
  parses with the string on the left, exactly as written.
- **Boolean structure** is `('AND', left, right)`, `('OR', left, right)` and
  `('NOT', operand)`. `AND` binds tighter than `OR`, so `a AND b OR c` comes
  back as `('OR', ('AND', a, b), c)`.
- **List operators** carry an extra tuple of per-value operators, because
  OPTIMADE allows a comparison operator per value: `elements HAS ALL "Ga","Ti"`
  becomes `('HAS_ALL', ('=', '='), identifier, (value, value))` — one `'='` per
  value. `HAS ANY`, `HAS ONLY` and the operator form `elements HAS < 3` follow
  the same shape.
- **Presence and length** get their own nodes: `('IS_KNOWN', identifier)`,
  `('IS_UNKNOWN', identifier)`, and `('LENGTH', identifier, op, value)`.

Because the shape is uniform, walking it is a short recursive function — the
`describe` function below renders any tree as an indented outline, and it needs
no knowledge of the individual operators.

A filter the grammar rejects raises `ParserSyntaxError`, a subclass of
`ParserError`. The failures are all genuine grammar violations, not
type errors: `nelements == 3` (OPTIMADE spells equality with one `=`),
`Elements = "Ga"` (property names are lower-case), `LENGTH elements = 2`
(`LENGTH` is a postfix operator on the identifier).
"""

from httk.core import FilterAst, ParserSyntaxError, parse_optimade_filter

FILTERS = [
    'nelements=3',
    'nelements>=2 AND nelements<=5',
    'elements HAS ALL "Ga","Ti" AND (nelements=3 OR nelements=2)',
    'nelements = 3 AND nelements = 2 OR nelements = 1',
    'NOT (nelements=3 AND nelements=4)',
    'elements HAS ONLY "Si","O"',
    'elements HAS < 3',
    'elements LENGTH >= 2',
    'chemical_formula_descriptive STARTS WITH "Ga"',
    'cartesian_site_positions.x = 1.5',
    '_httk_total_energy IS KNOWN',
    '_httk_stable = TRUE',
    '"Ga" = chemical_formula_descriptive',
]

BAD_FILTERS = [
    'nelements = ',
    'nelements == 3',
    '(nelements=1',
    'Elements = "Ga"',
    'LENGTH elements = 2',
    'elements HAS FOO "x"',
]

#: Node kinds whose payload is a token value rather than a subtree.
LEAF_KINDS = ("Identifier", "Number", "String", "Boolean")


def describe(node: FilterAst, indent: int = 0) -> None:
    """Print any filter AST as an indented outline.

    The traversal is generic: a node is `(head, *rest)`, so it is enough to
    print the head and recurse into whichever elements are themselves tuples.
    """
    pad = "  " * indent
    head = node[0]
    if head in LEAF_KINDS:
        # A leaf: ('Identifier', 'cartesian_site_positions', 'x') -> the dotted name.
        print(f"{pad}{head}: {'.'.join(str(part) for part in node[1:])}")
        return
    print(f"{pad}{head}")
    for operand in node[1:]:
        if isinstance(operand, tuple) and operand and operand[0] in LEAF_KINDS:
            describe(operand, indent + 1)
        elif isinstance(operand, tuple) and operand and isinstance(operand[0], tuple):
            # A tuple of values, as carried by HAS ALL / HAS ANY / HAS ONLY.
            for value in operand:
                describe(value, indent + 1)
        elif isinstance(operand, tuple):
            # Either a nested expression, or the per-value operator tuple.
            if all(isinstance(part, str) and part in ("=", "!=", "<", "<=", ">", ">=") for part in operand):
                print(f"{pad}  per-value operators: {operand}")
            else:
                describe(operand, indent + 1)
        else:
            print(f"{pad}  {operand!r}")


def show_parses() -> None:
    print("== Filters and the trees they parse to ==")
    for filter_string in FILTERS:
        print(f"\n{filter_string}")
        ast = parse_optimade_filter(filter_string)
        print(f"  raw: {ast}")
        describe(ast, indent=1)
    print()


def show_precedence() -> None:
    print("== AND binds tighter than OR ==")
    ast = parse_optimade_filter('nelements = 3 AND nelements = 2 OR nelements = 1')
    assert ast[0] == 'OR' and ast[1][0] == 'AND'
    print("  'a AND b OR c' parses as ('OR', ('AND', a, b), c) -- top node is", ast[0])
    print()


def show_syntax_errors() -> None:
    print("== Filters the grammar rejects ==")
    for filter_string in BAD_FILTERS:
        try:
            parse_optimade_filter(filter_string)
        except ParserSyntaxError as exc:
            first_line = str(exc).strip().splitlines()[0]
            print(f"  {filter_string!r:32} -> ParserSyntaxError: {first_line}")
        else:
            raise AssertionError(f"expected {filter_string!r} to be rejected")


def main() -> None:
    show_parses()
    show_precedence()
    show_syntax_errors()


if __name__ == "__main__":
    main()
