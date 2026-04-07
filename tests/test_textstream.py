from pathlib import Path

from httk.core.views import unwrap
from httk.core.datastream import TextstreamStringView, TextstreamString, TextstreamFileView

def test_textstream(tmp_path: Path) -> None:

    print("=== Textstream from filename ===")
    string_view = TextstreamStringView(__file__)
    print("Type:",type(string_view))
    print("First line:", string_view.splitlines()[0])

    print("\n=== Textstream from string ===")
    tss = TextstreamString("Hello\nWorld!\n")
    print("Type:",type(tss))
    file_view = TextstreamFileView(tss)
    print("Type:", type(file_view))
    print("Read all:", file_view.read())

    print("\n=== Re-wrapping TextstreamView ===")
    wrapped = TextstreamFileView(file_view)
    print("Is same object?", wrapped is file_view)

    tssv = TextstreamStringView(__file__)
    print("Unconverted:",type(tssv))
    print("Converted:",type(unwrap(tssv)))

if __name__ == "__main__":
    test_textstream(None)

