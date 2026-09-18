"""Complete an OPTIMADE schema snapshot with standard-namespace name identities.

Real OPTIMADE providers almost never publish a property-definition ``$id`` in
their ``/info/<entry_type>`` documents, yet the specification reserves the
unprefixed property namespace on a standard endpoint for the standard property
of that name as of the specification version the service declares. This module
applies that namespace rule: it fills in the definition IRI of an advertised
unprefixed property name whose meaning the declared specification version fixes,
without ever overriding a declared ``$id`` and without guessing about
provider-prefixed names.

The pure core is :func:`infer_standard_names`; :func:`complete_standard_schema`
is the registry-driven wrapper that every code path building an
:class:`~httk.core.optimade.resources.OptimadeSchemaSnapshot` can consult.
"""

import dataclasses
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType
from typing import cast
from weakref import WeakKeyDictionary

from ..property_definitions import EntryTypeDefinition
from ..register.entries import OptimadeEntryBinding, known_optimade_entry_bindings, optimade_entry_binding
from ..register.schemas import load_entry_type_definition
from .entries import _is_definition_iri
from .resources import OptimadeDocument, OptimadeSchemaSnapshot, optimade_document_root

STANDARD_NAME_EVIDENCE = "standard-name"
"""Evidence tag recorded for a name inferred from the standard namespace rule."""

_VERSION = re.compile(r"^(\d+)\.(\d+)(?:\.\d+)?(?:[-+].*)?$")


def parse_optimade_api_version(value: object) -> tuple[int, int] | None:
    """Return the ``(major, minor)`` of a major-1 OPTIMADE version, or ``None``.

    ``MAJOR.MINOR`` and ``MAJOR.MINOR.PATCH`` are accepted with optional trailing
    pre-release or build text ignored. Only the ``(major, minor)`` pair is
    compared. A value whose major version is not 1, or which does not parse,
    yields ``None`` (the client supports major version 1 only).

    :param value: Candidate version value.
    :return: The ``(major, minor)`` pair, or ``None`` when unusable.
    """

    if not isinstance(value, str):
        return None
    match = _VERSION.match(value)
    if match is None:
        return None
    major = int(match.group(1))
    if major != 1:
        return None
    return (major, int(match.group(2)))


@dataclass(frozen=True)
class StandardSchemaCompletion:
    """Identities inferred for standard-namespace property names.

    :param entry_type: Entry type of the info document these names belong to.
    :param api_version: Specification version the service declared, if any.
    :param entry_type_definition_id: Definition IRI of the matched standard
        entry type, set only when standard-name inference is possible for this
        snapshot (a usable declared version and an owner-declared version
        table); ``None`` otherwise.
    :param definitions_by_name: Remote property name mapped to the property
        definition IRI inferred for it.
    :param evidence_by_name: Remote property name mapped to the evidence tag
        that justified its inference.
    """

    entry_type: str
    api_version: str | None
    entry_type_definition_id: str | None
    definitions_by_name: Mapping[str, str]
    evidence_by_name: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "definitions_by_name", MappingProxyType(dict(self.definitions_by_name)))
        object.__setattr__(self, "evidence_by_name", MappingProxyType(dict(self.evidence_by_name)))


def infer_standard_names(
    *,
    entry_type: str,
    api_version: str | None,
    advertised: Mapping[str, object],
    definition_ids_by_name: Mapping[str, str],
    introduced_in: Mapping[str, str],
) -> StandardSchemaCompletion:
    """Infer definition IRIs for advertised standard-namespace property names.

    Pure and registry-free. For each advertised name the standard namespace
    rule is applied: an unprefixed name that the declared specification version
    already defines is completed to that standard property's definition IRI. A
    declared ``$id`` always wins, provider-prefixed names carry no standard
    semantics, and a name introduced only in a later version stays unknown. An
    absent or non-major-1 declared version disables inference entirely.

    :param entry_type: Entry type being completed.
    :param api_version: Specification version the service declared.
    :param advertised: The info document's ``data.properties`` mapping.
    :param definition_ids_by_name: Standard property name to definition IRI.
    :param introduced_in: Standard property name to its earliest spec version.
    :return: The names inferred for this schema, possibly empty.
    """

    declared = parse_optimade_api_version(api_version)
    if declared is None:
        return StandardSchemaCompletion(entry_type, api_version, None, {}, {})

    declared_iris = {
        cast(str, doc.get("$id"))
        for doc in advertised.values()
        if isinstance(doc, Mapping) and _is_definition_iri(doc.get("$id"))
    }

    inferred: dict[str, str] = {}
    for name, document in advertised.items():
        if not isinstance(name, str):
            continue
        if isinstance(document, Mapping) and _is_definition_iri(document.get("$id")):
            # A declared identity is authoritative; never infer over it.
            continue
        if name.startswith("_"):
            # Provider-prefixed names, and any other underscore-led name outside
            # the well-formed prefix shape, are outside the standard namespace.
            continue
        iri = definition_ids_by_name.get(name)
        if iri is None:
            continue
        introduced = parse_optimade_api_version(introduced_in.get(name))
        if introduced is None or introduced > declared:
            continue
        inferred[name] = iri

    # Declared identities win, and one IRI must never be claimed by two names.
    inferred = {name: iri for name, iri in inferred.items() if iri not in declared_iris}
    iri_counts = Counter(inferred.values())
    inferred = {name: iri for name, iri in inferred.items() if iri_counts[iri] == 1}

    evidence = {name: STANDARD_NAME_EVIDENCE for name in inferred}
    return StandardSchemaCompletion(entry_type, api_version, None, inferred, evidence)


_completion_cache: WeakKeyDictionary[OptimadeSchemaSnapshot, tuple[tuple[int, ...], StandardSchemaCompletion]] = (
    WeakKeyDictionary()
)
_completion_cache_lock = Lock()


def _registry_fingerprint() -> tuple[int, ...]:
    # Identity of each currently registered binding. A binding re-registered
    # under the same IRI is a different object, so this changes and invalidates
    # a cached completion that resolved against the old table.
    return tuple(id(optimade_entry_binding(definition_id)) for definition_id in known_optimade_entry_bindings())


def _resolve_binding(entry_type: str) -> tuple[OptimadeEntryBinding, EntryTypeDefinition] | None:
    matches: list[tuple[OptimadeEntryBinding, EntryTypeDefinition]] = []
    for definition_id in known_optimade_entry_bindings():
        binding = optimade_entry_binding(definition_id)
        if binding is None:
            continue
        try:
            definition = load_entry_type_definition(binding.definition_id)
        except ValueError:
            # A binding whose entry-type definition is not vendored here simply
            # cannot be matched by name; skip it without failing the read.
            continue
        if definition.name == entry_type:
            matches.append((binding, definition))
    if len(matches) != 1:
        return None
    return matches[0]


def _info_api_version(document: OptimadeDocument) -> str | None:
    try:
        root = optimade_document_root(document)
    except ValueError:
        return None
    meta = root.get("meta")
    if not isinstance(meta, Mapping):
        return None
    version = meta.get("api_version")
    return version if isinstance(version, str) else None


def _info_properties(document: OptimadeDocument) -> Mapping[str, object]:
    try:
        root = optimade_document_root(document)
    except ValueError:
        return {}
    data = root.get("data")
    if not isinstance(data, Mapping):
        return {}
    properties = data.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    return properties


def _complete_standard_schema(snapshot: OptimadeSchemaSnapshot) -> StandardSchemaCompletion:
    api_version = _info_api_version(snapshot.info_document)
    resolved = _resolve_binding(snapshot.entry_type)
    # ``entry_type_definition_id`` is set only when name-based inference is
    # actually possible for this snapshot: a usable (major-1) declared version
    # and a non-empty owner-declared version table. Otherwise it stays None, so
    # a client never binds a typed backend that could identify nothing.
    if resolved is None or parse_optimade_api_version(api_version) is None:
        return StandardSchemaCompletion(snapshot.entry_type, api_version, None, {}, {})
    binding, definition = resolved
    versions = binding.standard_property_versions
    if not versions:
        return StandardSchemaCompletion(snapshot.entry_type, api_version, None, {}, {})
    definition_ids_by_name = {name: prop.definition_id for name, prop in definition.properties.items()}
    completion = infer_standard_names(
        entry_type=snapshot.entry_type,
        api_version=api_version,
        advertised=_info_properties(snapshot.info_document),
        definition_ids_by_name=definition_ids_by_name,
        introduced_in=versions,
    )
    return dataclasses.replace(completion, entry_type_definition_id=definition.definition_id)


def complete_standard_schema(snapshot: OptimadeSchemaSnapshot) -> StandardSchemaCompletion:
    """Return the standard-name completion for one schema snapshot.

    Registry-driven wrapper over :func:`infer_standard_names`. It reads the
    declared specification version from the info document's own
    ``meta.api_version``, resolves the standard entry type by name against the
    registered OPTIMADE entry bindings, and gates name-based inference on that
    binding's ``standard_property_versions`` table. It never raises for
    malformed or hostile remote input: the safe answer is an empty completion.
    ``entry_type_definition_id`` is set only when standard-name inference is
    possible for this snapshot (a usable declared version and an owner-declared
    version table).

    :param snapshot: Schema snapshot whose advertised names to complete.
    :return: The inferred completion, empty when unresolved or unsupported by
        the declared version.
    """

    fingerprint = _registry_fingerprint()
    with _completion_cache_lock:
        cached = _completion_cache.get(snapshot)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    result = _complete_standard_schema(snapshot)
    with _completion_cache_lock:
        _completion_cache[snapshot] = (fingerprint, result)
    return result
