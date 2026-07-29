# Vendored OPTIMADE filter grammar

This directory holds the OPTIMADE filter language support of *httk-core*: the
parser (`parser.py`, built on the vendored LR(1) parser generator in
`_miniparser.py`) and the grammar file `optimade_filter_grammar.ebnf` it loads
at runtime (packaged through `pyproject.toml`'s `package-data` entry
`"httk.core" = [..., "optimade_filter/*.ebnf", "optimade_filter/README.md"]`).

## Provenance

`optimade_filter_grammar.ebnf` is a transcription of the filter-language
grammar given in the appendix of the OPTIMADE specification. The upstream
machine-readable grammar lives in the Materials-Consortia OPTIMADE repository
under `grammar/` (e.g. `grammar/v1.2.0.g`):
<https://github.com/Materials-Consortia/OPTIMADE/tree/master/grammar>

TODO: pin exact tag/URL when refreshing.

The supported version is OPTIMADE v1.x — a single grammar file covers the
v1 series (the v1.2 addition of boolean values is included).

## Refreshing

The grammar is refreshed manually: the upstream machine-readable grammar and
this file use different EBNF dialects/formats, so there is no automated fetch
target (unlike `make optimade-defs` for the sibling `registry/schemas/core/`
directory). When the specification grammar changes, update this transcription
by hand, review the diff against the spec appendix, and update the provenance
notes above.
