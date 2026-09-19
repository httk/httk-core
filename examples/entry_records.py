"""Define a frozen served record with explicit scientific property metadata."""

from dataclasses import replace
from typing import Annotated

from httk.core import DataEntryRecord, Property, content_id, entry_record


@entry_record("example.measurement")
class Measurement(DataEntryRecord):
    """An energy measurement with a local sample label.

    :param energy: Energy per atom, in eV.
    :param label: A local sample label, not published as an OPTIMADE attribute.
    """

    energy: Annotated[float, Property(description="Energy per atom.", unit="eV")]
    label: str


measurement = Measurement(-1.2, "sample-1")
identified = replace(measurement, id="example-1-1", immutable_id="example-1-1~1")
assert measurement == identified
assert content_id(measurement) == content_id(identified)
assert "_httk_custom_label" not in Measurement.entry_type_definition().properties
print(Measurement.entry_type_definition().served_form().name)
print(measurement.energy, measurement.label)
