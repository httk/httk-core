"""Identifiers of the httk core property definitions vendored with *httk-core*."""

__all__ = [
    "ATOMIC_FORCE",
    "AVERAGE_TOTAL_ENERGY",
    "ENTHALPY",
    "KINETIC_ENERGY",
    "POTENTIAL_ENERGY",
    "PRESSURE",
    "STRESS_TENSOR",
    "TEMPERATURE",
    "TOTAL_ENERGY",
    "VOLUME",
]

#: Definition IRI of the total energy (eV).
TOTAL_ENERGY = "https://schemas.httk.org/defs/v0.1/properties/core/total_energy"

#: Definition IRI of the average total energy (eV).
AVERAGE_TOTAL_ENERGY = "https://schemas.httk.org/defs/v0.1/properties/core/average_total_energy"

#: Definition IRI of the potential energy (eV).
POTENTIAL_ENERGY = "https://schemas.httk.org/defs/v0.1/properties/core/potential_energy"

#: Definition IRI of the kinetic energy (eV).
KINETIC_ENERGY = "https://schemas.httk.org/defs/v0.1/properties/core/kinetic_energy"

#: Definition IRI of the enthalpy (eV).
ENTHALPY = "https://schemas.httk.org/defs/v0.1/properties/core/enthalpy"

#: Definition IRI of the temperature (K).
TEMPERATURE = "https://schemas.httk.org/defs/v0.1/properties/core/temperature"

#: Definition IRI of the volume (angstrom^3).
VOLUME = "https://schemas.httk.org/defs/v0.1/properties/core/volume"

#: Definition IRI of the pressure (GPa).
PRESSURE = "https://schemas.httk.org/defs/v0.1/properties/core/pressure"

#: Definition IRI of the stress tensor in Voigt order (GPa).
STRESS_TENSOR = "https://schemas.httk.org/defs/v0.1/properties/core/stress_tensor"

#: Definition IRI of the per-atom force vectors (eV/angstrom).
ATOMIC_FORCE = "https://schemas.httk.org/defs/v0.1/properties/core/atomic_force"
