# Parsing OPTIMADE filter strings into an abstract syntax tree

An OPTIMADE query arrives as a string — `elements HAS ALL "Ga","Ti" AND
nelements=3`. Before anything can be done with it, it has to become structure.
`httk.core.optimade.parse_optimade_filter` does exactly that and nothing more: it runs
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

```{literalinclude} ../../examples/optimade_filter.py
:language: python
:lines: 48-
```
