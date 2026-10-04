"""Parse and convert OPTIMADE Compound Unit Expressions with exact factors.

Symbols resolve against OPTIMADE unit, prefix and constant definition documents;
:func:`default_registry` uses the upstream documents vendored with *httk-core*.
Every relation-less unit is a base dimension named by its symbol (upstream ``kg``
is a base unit; there is no ``g``). Relations are read only when a symbol is
resolved, so a malformed upstream relation fails only for the symbols using it.
"""

import functools
import importlib.resources
import json
import numbers
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Literal

__all__ = ["Conversion", "UnitDefinition", "UnitRegistry", "default_registry"]

_FACTOR = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)(?:\^(-?[1-9][0-9]*))?")
_KINDS = ("unit", "prefix", "constant")

type _Terms = tuple[tuple[str | None, str, int], ...]
type _Measure = tuple[Fraction, Mapping[str, int], bool]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _number(fields: Mapping[str, Any], key: str, default: int) -> int:
    value = fields.get(key)
    return default if value is None else value


def _scale(scale: Mapping[str, Any] | None) -> tuple[Fraction, bool]:
    if scale is None:
        return Fraction(1), False
    approximate = bool(scale.get("standard_uncertainty"))
    if "value" in scale:
        # Float scales (approximate relations) become the float's exact binary value.
        return Fraction(scale["value"]), True
    ratio = Fraction(_number(scale, "numerator", 1), _number(scale, "denominator", 1))
    return ratio * Fraction(_number(scale, "base", 10)) ** _number(scale, "exponent", 0), approximate


def _format(dimension: Mapping[str, int]) -> str:
    return (
        "*".join(f"{key}^{power}" if power != 1 else key for key, power in sorted(dimension.items())) or "dimensionless"
    )


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    """One OPTIMADE unit, prefix or constant definition known to a registry.

    :param symbol: Symbol used in Compound Unit Expressions.
    :param kind: Definition kind from ``x-optimade-definition``.
    :param definition_id: The document's ``$id``.
    :param document: Read-only view of the definition document.
    """

    symbol: str
    kind: Literal["unit", "prefix", "constant"]
    definition_id: str
    document: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Conversion:
    """An exact scale factor between two unit expressions.

    :param factor: Exact rational factor; a value in the source unit times it is the value in the target unit.
    :param approximate: Whether upstream metadata marks any relation used as approximate; informational only.
    """

    factor: Fraction
    approximate: bool

    def apply(self, value: Any) -> Any:
        """Convert a number or nested lists/tuples of numbers.

        :param value: Number or nested sequence of numbers in the source unit.
        :return: Float, or nested lists of floats, in the target unit.
        :raises TypeError: If a leaf is not a number or is a boolean.
        """

        if isinstance(value, list | tuple):
            return [self.apply(item) for item in value]
        if isinstance(value, bool) or not isinstance(value, numbers.Real):  # also numpy bool_, str, complex
            raise TypeError(f"cannot convert non-numeric value {value!r}")
        number = value if isinstance(value, numbers.Rational) else float(value)
        try:
            return float(Fraction(number) * self.factor)  # one rounding for finite values
        except (ValueError, OverflowError):  # nan/inf
            return float(number) * float(self.factor)


class UnitRegistry:
    """Symbol table and converter over OPTIMADE unit, prefix and constant documents.

    A document listed in the ``compatibility`` of another document with the same
    symbol (for example a dated SI edition of a general unit) yields that symbol
    to it and stays reachable by ``$id`` from relations.

    :param documents: OPTIMADE definition documents (``x-optimade-definition.kind`` of unit, prefix or constant).
    :raises ValueError: If a document has an unsupported kind or two documents claim the same symbol.
    """

    def __init__(self, documents: Iterable[Mapping[str, Any]]) -> None:
        self._by_id: dict[str, UnitDefinition] = {}
        for document in documents:
            kind = document["x-optimade-definition"]["kind"]
            if kind not in _KINDS:
                raise ValueError(f"unsupported definition kind {kind!r} in {document.get('$id')!r}")
            definition = UnitDefinition(document["symbol"], kind, document["$id"], _freeze(document))
            self._by_id[definition.definition_id] = definition
        superseded = {
            iri
            for definition in self._by_id.values()
            for iri in definition.document.get("compatibility", ())
            if iri in self._by_id and self._by_id[iri].symbol == definition.symbol
        }
        self._units: dict[str, str] = {}
        self._prefixes: dict[str, str] = {}
        for definition in self._by_id.values():
            if definition.definition_id in superseded:
                continue
            table = self._prefixes if definition.kind == "prefix" else self._units
            if table.setdefault(definition.symbol, definition.definition_id) != definition.definition_id:
                raise ValueError(f"duplicate {definition.kind} symbol {definition.symbol!r}")
        self._cache: dict[str, _Measure] = {}

    def definition(self, symbol: str) -> UnitDefinition:
        """Return the unit or constant with *symbol*, else the prefix with *symbol*.

        :param symbol: Whole unit, constant or prefix symbol.
        :return: The definition.
        :raises KeyError: If no definition has the symbol.
        """

        definition_id = self._units.get(symbol) or self._prefixes.get(symbol)
        if definition_id is None:
            raise KeyError(symbol)
        return self._by_id[definition_id]

    def parse(self, expression: str) -> tuple[tuple[str | None, str, int], ...]:
        """Parse a Compound Unit Expression under the strict OPTIMADE grammar.

        :param expression: Expression with symbols in code-point order, or ``dimensionless``.
        :return: ``(prefix symbol or None, unit or constant symbol, power)`` per factor.
        :raises ValueError: If the expression is malformed, unordered, repeats a symbol, uses an unknown or
            ambiguous symbol, or is ``inapplicable``.
        """

        return self._parse(expression, self._units, ordered=True)

    def definitions(self, expression: str) -> tuple[UnitDefinition, ...]:
        """Return the distinct definitions an expression uses, each prefix before its unit.

        :param expression: Compound Unit Expression, parsed as by :meth:`parse`.
        :return: Prefix, unit and constant definitions in first-appearance order.
        :raises ValueError: As :meth:`parse`.
        """

        ids = [
            iri
            for prefix, symbol, _ in self.parse(expression)
            for iri in (self._prefixes.get(prefix or ""), self._units[symbol])
            if iri is not None
        ]
        return tuple(self._by_id[iri] for iri in dict.fromkeys(ids))

    def canonical(self, expression: str) -> str:
        """Return *expression* with symbols in code-point order and ``^1`` dropped.

        :param expression: Expression in any symbol order.
        :return: Canonical expression.
        :raises ValueError: As :meth:`parse`, except for symbol order.
        """

        terms = self._parse(expression, self._units, ordered=False)
        factors = sorted(((prefix or "") + symbol, power) for prefix, symbol, power in terms)
        return "*".join(f"{written}^{power}" if power != 1 else written for written, power in factors) or expression

    def dimension(self, expression: str) -> Mapping[str, Fraction]:
        """Return the exponents of *expression* over base-unit symbols.

        :param expression: Compound Unit Expression.
        :return: Read-only mapping from base symbol to nonzero exponent.
        :raises ValueError: As :meth:`parse`, or if a definition it uses cannot be resolved.
        """

        return MappingProxyType({key: Fraction(power) for key, power in self._measure(expression)[1].items()})

    def factor(self, source: str, target: str) -> Conversion:
        """Return the factor converting values in *source* to *target*.

        :param source: Compound Unit Expression of the values.
        :param target: Compound Unit Expression to convert to.
        :return: The exact conversion.
        :raises ValueError: If the dimensions differ, or as :meth:`dimension`.
        """

        source_scale, source_dimension, source_approximate = self._measure(source)
        target_scale, target_dimension, target_approximate = self._measure(target)
        if source_dimension != target_dimension:
            raise ValueError(
                f"cannot convert {source!r} ({_format(source_dimension)}) to {target!r} ({_format(target_dimension)})"
            )
        return Conversion(source_scale / target_scale, source_approximate or target_approximate)

    def convert(self, value: Any, source: str, target: str) -> Any:
        """Convert a number or nested sequence of numbers from *source* to *target*.

        :param value: Number or nested lists/tuples of numbers.
        :param source: Compound Unit Expression of *value*.
        :param target: Compound Unit Expression to convert to.
        :return: Float, or nested lists of floats.
        :raises ValueError: As :meth:`factor`.
        """

        return self.factor(source, target).apply(value)

    def _parse(self, expression: str, units: Mapping[str, str], *, ordered: bool) -> _Terms:
        if expression == "inapplicable":
            raise ValueError("'inapplicable' has no unit")
        if expression == "dimensionless":
            return ()
        written: list[str] = []
        terms: list[tuple[str | None, str, int]] = []
        for factor in expression.split("*"):
            match = _FACTOR.fullmatch(factor)
            if match is None:
                raise ValueError(f"malformed unit expression {expression!r} at {factor!r}")
            symbol = match[1]
            if symbol in written:
                raise ValueError(f"repeated unit symbol {symbol!r} in {expression!r}")
            if ordered and written and symbol < written[-1]:
                raise ValueError(f"unit symbols in {expression!r} are not in code-point order")
            written.append(symbol)
            terms.append((*self._split(symbol, units), int(match[2] or 1)))
        return tuple(terms)

    def _split(self, written: str, units: Mapping[str, str]) -> tuple[str | None, str]:
        if written in units:
            return None, written
        splits = [(written[:i], written[i:]) for i in range(1, len(written)) if written[:i] in self._prefixes]
        splits = [(prefix, symbol) for prefix, symbol in splits if symbol in units]
        if len(splits) > 1:
            raise ValueError(f"ambiguous unit symbol {written!r}: {splits}")
        if not splits:
            raise ValueError(f"unknown unit symbol {written!r}")
        return splits[0]

    def _measure(self, expression: str) -> _Measure:
        return self._combine(self.parse(expression), self._units, ())

    def _combine(self, terms: _Terms, units: Mapping[str, str], stack: tuple[str, ...]) -> _Measure:
        scale, dimension, approximate = Fraction(1), Counter[str](), False
        for prefix, symbol, power in terms:
            unit_scale, unit_dimension, unit_approximate = self._resolve(units[symbol], stack)
            if prefix is not None:
                prefix_scale, _, prefix_approximate = self._resolve(self._prefixes[prefix], stack)
                unit_scale *= prefix_scale
                unit_approximate |= prefix_approximate
            scale *= unit_scale**power
            approximate |= unit_approximate
            for key, exponent in unit_dimension.items():
                dimension[key] += exponent * power
        return scale, {key: power for key, power in dimension.items() if power}, approximate

    def _resolve(self, definition_id: str, stack: tuple[str, ...]) -> _Measure:
        cached = self._cache.get(definition_id)
        if cached is not None:
            return cached
        if definition_id in stack:
            raise ValueError(f"cyclic unit relations through {definition_id!r}")
        definition = self._by_id.get(definition_id)
        if definition is None:
            raise ValueError(f"unknown unit definition {definition_id!r}")
        document = definition.document
        relation = document.get("defining-relation")
        approximate = False
        if relation is None and document.get("approximate-relations"):
            relation, approximate = document["approximate-relations"][0], True
        if relation is None:
            if definition.kind == "prefix":
                raise ValueError(f"prefix {definition.symbol!r} has no relation")
            result: _Measure = (Fraction(1), {definition.symbol: 1}, False)
        else:
            if relation.get("offset") is not None:
                raise ValueError(f"unit {definition.symbol!r} is affine (has an offset); not supported")
            scale, scale_approximate = _scale(relation.get("scale"))
            declared = {base["symbol"]: base["id"] for base in relation.get("base-units") or ()}
            expression = relation.get("base-units-expression") or ""
            terms = self._parse(expression, declared or self._units, ordered=False) if expression else ()
            if declared and {symbol for _, symbol, _ in terms} != declared.keys():
                raise ValueError(
                    f"relation of {definition.symbol!r} uses {expression!r} but declares base units {sorted(declared)}"
                )
            base_scale, dimension, base_approximate = self._combine(
                terms, declared or self._units, (*stack, definition_id)
            )
            result = (scale * base_scale, dimension, approximate or scale_approximate or base_approximate)
        self._cache[definition_id] = result
        return result


@functools.cache
def default_registry() -> UnitRegistry:
    """Return the registry over the OPTIMADE documents vendored with *httk-core*, built on first use.

    :return: The shared default registry.
    """

    root = importlib.resources.files("httk.registry.schemas.core") / "units"
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    return UnitRegistry(json.loads((root / entry["path"]).read_text(encoding="utf-8")) for entry in index)
