"""Datastreams quickstart

Views accept natural inputs and present them through the interface an algorithm needs.
The same file view also opens gzip-compressed text transparently from its filename.
"""

import gzip
import tempfile
from pathlib import Path

from httk.core.datastream import TextstreamFileView, TextstreamStringView

memory = TextstreamStringView("in memory\n", kind="content")
assert memory == "in memory\n"

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "message.txt.gz"
    with gzip.open(path, "wt", encoding="utf-8") as compressed:
        compressed.write("from gzip\n")

    file_view = TextstreamFileView(path)
    assert file_view.read() == "from gzip\n"
    assert file_view.name == str(path)
    file_view.close()

print(memory.strip(), "and", "gzip text read through a view")
