import pytest

from httk.core.optimade.filter import ParserSyntaxError, parse_optimade_filter

# Expected syntax trees below were captured from the httk v1 implementation
# to guarantee port parity.


def test_simple_comparison() -> None:
    assert parse_optimade_filter('nelements=3') == ('=', ('Identifier', 'nelements'), ('Number', '3'))


def test_comparison_operators() -> None:
    assert parse_optimade_filter('nelements>=2 AND nelements<=5') == (
        'AND',
        ('>=', ('Identifier', 'nelements'), ('Number', '2')),
        ('<=', ('Identifier', 'nelements'), ('Number', '5')),
    )
    assert parse_optimade_filter('nelements != 3 OR nelements > 10') == (
        'OR',
        ('!=', ('Identifier', 'nelements'), ('Number', '3')),
        ('>', ('Identifier', 'nelements'), ('Number', '10')),
    )


def test_and_or_grouping() -> None:
    assert parse_optimade_filter('elements HAS ALL "Ga","Ti" AND (nelements=3 OR nelements=2)') == (
        'AND',
        ('HAS_ALL', ('=', '='), ('Identifier', 'elements'), (('String', 'Ga'), ('String', 'Ti'))),
        (
            'OR',
            ('=', ('Identifier', 'nelements'), ('Number', '3')),
            ('=', ('Identifier', 'nelements'), ('Number', '2')),
        ),
    )


def test_and_binds_tighter_than_or() -> None:
    assert parse_optimade_filter('nelements = 3 AND nelements = 2 OR nelements = 1') == (
        'OR',
        (
            'AND',
            ('=', ('Identifier', 'nelements'), ('Number', '3')),
            ('=', ('Identifier', 'nelements'), ('Number', '2')),
        ),
        ('=', ('Identifier', 'nelements'), ('Number', '1')),
    )


def test_not() -> None:
    assert parse_optimade_filter('NOT nelements = 3') == ('NOT', ('=', ('Identifier', 'nelements'), ('Number', '3')))
    assert parse_optimade_filter('NOT (nelements=3 AND nelements=4)') == (
        'NOT',
        (
            'AND',
            ('=', ('Identifier', 'nelements'), ('Number', '3')),
            ('=', ('Identifier', 'nelements'), ('Number', '4')),
        ),
    )


def test_fuzzy_string_operations() -> None:
    ident = ('Identifier', 'chemical_formula_descriptive')
    assert parse_optimade_filter('chemical_formula_descriptive CONTAINS "Ga"') == ('CONTAINS', ident, ('String', 'Ga'))
    assert parse_optimade_filter('chemical_formula_descriptive STARTS WITH "Ga"') == ('STARTS', ident, ('String', 'Ga'))
    assert parse_optimade_filter('chemical_formula_descriptive ENDS WITH "Ga"') == ('ENDS', ident, ('String', 'Ga'))


def test_is_known_unknown() -> None:
    assert parse_optimade_filter('_httk_total_energy IS KNOWN') == ('IS_KNOWN', ('Identifier', '_httk_total_energy'))
    assert parse_optimade_filter('_httk_total_energy IS UNKNOWN') == (
        'IS_UNKNOWN',
        ('Identifier', '_httk_total_energy'),
    )


def test_has_operations() -> None:
    assert parse_optimade_filter('elements HAS "Si"') == (
        'HAS_ALL',
        ('=',),
        ('Identifier', 'elements'),
        (('String', 'Si'),),
    )
    assert parse_optimade_filter('elements HAS ONLY "Si","O"') == (
        'HAS_ONLY',
        ('=', '='),
        ('Identifier', 'elements'),
        (('String', 'Si'), ('String', 'O')),
    )
    assert parse_optimade_filter('elements HAS ANY "Si","O"') == (
        'HAS_ANY',
        ('=', '='),
        ('Identifier', 'elements'),
        (('String', 'Si'), ('String', 'O')),
    )


def test_has_with_operator() -> None:
    assert parse_optimade_filter('elements HAS < 3') == ('HAS', ('<',), ('Identifier', 'elements'), (('Number', '3'),))


def test_length_operations() -> None:
    assert parse_optimade_filter('elements LENGTH 2') == (
        'LENGTH',
        ('Identifier', 'elements'),
        '=',
        ('Number', '2'),
    )
    assert parse_optimade_filter('elements LENGTH >= 2') == (
        'LENGTH',
        ('Identifier', 'elements'),
        '>=',
        ('Number', '2'),
    )


def test_nested_identifier() -> None:
    assert parse_optimade_filter('cartesian_site_positions.x = 1.5') == (
        '=',
        ('Identifier', 'cartesian_site_positions', 'x'),
        ('Number', '1.5'),
    )


def test_constant_first_comparison() -> None:
    assert parse_optimade_filter('"Ga" = chemical_formula_descriptive') == (
        '=',
        ('String', 'Ga'),
        ('Identifier', 'chemical_formula_descriptive'),
    )


@pytest.mark.parametrize(
    ("filter_string", "expected"),
    [
        ('0.5 < _httk_e.rmse', ('<', ('Number', '0.5'), ('Identifier', '_httk_e', 'rmse'))),
        ('"x" = a.b.c', ('=', ('String', 'x'), ('Identifier', 'a', 'b', 'c'))),
        ('a = b.c', ('=', ('Identifier', 'a'), ('Identifier', 'b', 'c'))),
        ('a CONTAINS b.c', ('CONTAINS', ('Identifier', 'a'), ('Identifier', 'b', 'c'))),
        ('a HAS b.c', ('HAS_ALL', ('=',), ('Identifier', 'a'), (('Identifier', 'b', 'c'),))),
    ],
)
def test_dotted_identifier_operands_keep_every_segment(filter_string: str, expected: object) -> None:
    assert parse_optimade_filter(filter_string) == expected


@pytest.mark.parametrize(
    "bad_filter",
    [
        'nelements = ',
        'elements HAS FOO "x"',
        'nelements == 3',
        '(nelements=1',
        'Elements = "Ga"',
        'LENGTH elements = 2',
    ],
)
def test_syntax_errors(bad_filter: str) -> None:
    with pytest.raises(ParserSyntaxError):
        parse_optimade_filter(bad_filter)


def test_grammar_loads_from_package_data() -> None:
    from httk.core.optimade.filter.parser import _optimade_parser_ls

    _optimade_parser_ls.cache_clear()
    assert parse_optimade_filter('nelements=1') == ('=', ('Identifier', 'nelements'), ('Number', '1'))


def test_boolean_values() -> None:
    # Boolean values were added to the filter language in OPTIMADE v1.2.
    assert parse_optimade_filter('_httk_stable = TRUE') == (
        '=',
        ('Identifier', '_httk_stable'),
        ('Boolean', 'TRUE'),
    )
    assert parse_optimade_filter('_httk_stable != FALSE') == (
        '!=',
        ('Identifier', '_httk_stable'),
        ('Boolean', 'FALSE'),
    )


def test_boolean_constant_first() -> None:
    assert parse_optimade_filter('TRUE = _httk_stable') == (
        '=',
        ('Boolean', 'TRUE'),
        ('Identifier', '_httk_stable'),
    )


@pytest.mark.parametrize(
    "filter_string,expected",
    [
        (r'label="ab\"c"', 'ab"c'),
        (r'label="a\\b"', 'a\\b'),
        (r'label="\\\""', '\\"'),
        ('label="plain"', 'plain'),
    ],
)
def test_string_escapes_are_unescaped(filter_string: str, expected: str) -> None:
    # OPTIMADE requires the \" and \\ escapes inside string literals to be
    # reversed after quote stripping (values with " or \ must be filterable).
    ast = parse_optimade_filter(filter_string)
    assert ast == ('=', ('Identifier', 'label'), ('String', expected))


def test_deep_nesting_raises_syntax_error_not_recursionerror() -> None:
    # Pathological nesting must surface as a ParserSyntaxError (mapped to HTTP
    # 400 by consumers), not a raw RecursionError (a 500).
    n = 500
    with pytest.raises(ParserSyntaxError):
        parse_optimade_filter("(" * n + "a=1" + ")" * n)


def test_long_and_chain_raises_syntax_error_not_recursionerror() -> None:
    # A long flat AND chain recurses per term during ojf conversion and would
    # otherwise raise RecursionError; it must be a ParserSyntaxError too.
    with pytest.raises(ParserSyntaxError):
        parse_optimade_filter(" AND ".join(["a=1"] * 1000))


A, B, C = ('Identifier', 'a'), ('Identifier', 'b'), ('Identifier', 'c')
N1, N2, N3 = ('Number', '1'), ('Number', '2'), ('Number', '3')
EQ2 = ('=', '=')


@pytest.mark.parametrize(
    ("filter_string", "expected"),
    [
        # A plain zip HAS is HAS_ZIP_ALL with one tuple (as plain HAS is HAS_ALL).
        ('a:b HAS 1:2', ('HAS_ZIP_ALL', (EQ2,), (A, B), ((N1, N2),))),
        ('a:b:c HAS 1:2:3', ('HAS_ZIP_ALL', (('=', '=', '='),), (A, B, C), ((N1, N2, N3),))),
        ('a:b HAS ALL 1:2, 2:3', ('HAS_ZIP_ALL', (EQ2, EQ2), (A, B), ((N1, N2), (N2, N3)))),
        ('a:b HAS ANY 1:2, 2:3', ('HAS_ZIP_ANY', (EQ2, EQ2), (A, B), ((N1, N2), (N2, N3)))),
        ('a:b HAS ONLY 1:2, 2:3, 3:1', ('HAS_ZIP_ONLY', (EQ2,) * 3, (A, B), ((N1, N2), (N2, N3), (N3, N1)))),
        # Per-slot operators; '=' where none is given.
        ('a:b HAS >1:<2', ('HAS_ZIP_ALL', (('>', '<'),), (A, B), ((N1, N2),))),
        ('a:b HAS ANY 1:!=2, <=3:>=1', ('HAS_ZIP_ANY', (('=', '!='), ('<=', '>=')), (A, B), ((N1, N2), (N3, N1)))),
        # Strings are unquoted, booleans normalized.
        ('a:b HAS "x":TRUE', ('HAS_ZIP_ALL', (EQ2,), (A, B), ((('String', 'x'), ('Boolean', 'TRUE')),))),
        # Dotted properties keep every segment.
        (
            'x.m:x.n HAS "a":1',
            ('HAS_ZIP_ALL', (EQ2,), (('Identifier', 'x', 'm'), ('Identifier', 'x', 'n')), ((('String', 'a'), N1),)),
        ),
        # A property-valued slot becomes an Identifier with every segment.
        ('a:b HAS c.d:1', ('HAS_ZIP_ALL', (EQ2,), (A, B), ((('Identifier', 'c', 'd'), N1),))),
        ('NOT a:b HAS 1:2', ('NOT', ('HAS_ZIP_ALL', (EQ2,), (A, B), ((N1, N2),)))),
        (
            'c=3 AND (a:b HAS 1:2 OR c HAS 1)',
            (
                'AND',
                ('=', C, N3),
                ('OR', ('HAS_ZIP_ALL', (EQ2,), (A, B), ((N1, N2),)), ('HAS_ALL', ('=',), C, (N1,))),
            ),
        ),
    ],
)
def test_zip_ast(filter_string: str, expected: tuple[object, ...]) -> None:
    assert parse_optimade_filter(filter_string) == expected


@pytest.mark.parametrize(
    ("filter_string", "expected"),
    [
        ('a HAS > "x"', ('HAS', ('>',), A, (('String', 'x'),))),
        ('a HAS != c.d', ('HAS', ('!=',), A, (('Identifier', 'c', 'd'),))),
    ],
)
def test_has_operator_value_is_normalized(filter_string: str, expected: tuple[object, ...]) -> None:
    assert parse_optimade_filter(filter_string) == expected


@pytest.mark.parametrize("filter_string", ['a:b HAS 1:2:3', 'a:b:c HAS 1:2', 'a:b HAS ALL 1:2, 1:2:3'])
def test_zip_width_mismatch_raises_syntax_error(filter_string: str) -> None:
    with pytest.raises(ParserSyntaxError, match="zip value tuple has"):
        parse_optimade_filter(filter_string)


def test_zip_via_public_two_step_api() -> None:
    from httk.core.optimade.filter import optimade_parse_tree_to_ojf, parse_optimade_filter_raw

    tree = parse_optimade_filter_raw('elements:elements_ratios HAS "Ag":1')
    assert optimade_parse_tree_to_ojf(tree) == (
        'HAS_ZIP_ALL',
        (EQ2,),
        (('Identifier', 'elements'), ('Identifier', 'elements_ratios')),
        ((('String', 'Ag'), N1),),
    )


def test_miniparser_toy_grammar() -> None:
    # Direct test of the vendored LR(1) miniparser: build_ls + parser over the
    # small toy grammar from the module docstring's usage example.
    from httk.core.optimade.filter import _miniparser

    ls = _miniparser.build_ls(
        ebnf_grammar="""
            S = E ;
            E = T, '+', E ;
            E = T ;
            T = id ;
        """,
        tokens={'id': '[a-zA-Z][a-zA-Z0-9_]*'},
    )
    result = _miniparser.parser(ls, "Test + Test")
    assert result == ('S', ('E', ('T', ('id', 'Test')), ('+', '+'), ('E', ('T', ('id', 'Test')))))


def test_miniparser_toy_grammar_syntax_error() -> None:
    from httk.core.optimade.filter import _miniparser

    ls = _miniparser.build_ls(
        ebnf_grammar="""
            S = E ;
            E = T, '+', E ;
            E = T ;
            T = id ;
        """,
        tokens={'id': '[a-zA-Z][a-zA-Z0-9_]*'},
    )
    with pytest.raises(_miniparser.ParserSyntaxError):
        _miniparser.parser(ls, "Test + +")
