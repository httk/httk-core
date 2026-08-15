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
        (r'label="\x"', 'x'),
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


def test_unsupported_zip_construct_raises_syntax_error_not_assertionerror() -> None:
    # A grammatical-but-unsupported zipped correlated list ("Ag":1) fires a bare
    # assert during ojf conversion; it must surface as a ParserSyntaxError (HTTP
    # 400), not a raw AssertionError (a 500).
    with pytest.raises(ParserSyntaxError) as excinfo:
        parse_optimade_filter('elements:elements_ratios HAS "Ag":1')
    assert "unsupported or invalid construct" in str(excinfo.value)


def test_unsupported_construct_via_public_two_step_api() -> None:
    # The documented two-step path must also convert the bare assert.
    from httk.core.optimade.filter import optimade_parse_tree_to_ojf, parse_optimade_filter_raw

    tree = parse_optimade_filter_raw('elements:elements_ratios HAS "Ag":1')
    with pytest.raises(ParserSyntaxError) as excinfo:
        optimade_parse_tree_to_ojf(tree)
    assert "unsupported or invalid construct" in str(excinfo.value)


def test_too_deep_and_unsupported_messages_stay_distinct() -> None:
    # Step 3 must not collapse the two error kinds into one message.
    with pytest.raises(ParserSyntaxError) as deep:
        parse_optimade_filter("(" * 500 + "a=1" + ")" * 500)
    with pytest.raises(ParserSyntaxError) as unsupported:
        parse_optimade_filter('elements:elements_ratios HAS "Ag":1')
    assert "too deeply nested" in str(deep.value)
    assert "unsupported or invalid construct" in str(unsupported.value)
    assert str(deep.value) != str(unsupported.value)


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
