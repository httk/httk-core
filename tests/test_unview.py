"""Tests for the unview verb: shedding httk View wrappers to plain presented values."""

import fractions

import pytest

from httk.core import (
    BytestreamFileView,
    FracVector,
    SurdVector,
    TextstreamFileView,
    View,
    unview,
    unwrap,
)
from httk.core.datastream.bytestream_bytes_view import BytestreamBytesView
from httk.core.datastream.bytestream_filename_view import BytestreamFilenameView
from httk.core.datastream.textstream_filename_view import TextstreamFilenameView
from httk.core.datastream.textstream_string_view import TextstreamStringView
from httk.core.vectors.vector_frac_view import VectorFracView
from httk.core.vectors.vector_native_view import VectorNativeView
from httk.core.vectors.vector_surd_view import VectorSurdView

F = fractions.Fraction


def test_non_view_inputs_pass_through_unchanged() -> None:
    for value in (7, "abc", [1, 2], (1, 2), FracVector.create([1, 2])):
        assert unview(value) is value


def test_frac_view_unview_reuses_a_frac_backend() -> None:
    source = FracVector.create([[1, 2], [3, 4]])
    view = VectorFracView(source)
    plain = unview(view)
    assert type(plain) is FracVector
    assert plain is source  # the backend holds exactly the presented FracVector


def test_frac_view_unview_materializes_converted_sources() -> None:
    view = VectorFracView((1, 2, 3))
    plain = unview(view)
    assert type(plain) is FracVector
    assert plain == FracVector.create((1, 2, 3))


def test_backendless_frac_view_unview() -> None:
    # Inherited FracVector algebra builds backend-less view instances.
    derived = VectorFracView(FracVector.create([2, 4])) / 2
    assert isinstance(derived, VectorFracView)
    assert unwrap(derived) is derived
    plain = unview(derived)
    assert type(plain) is FracVector
    assert plain == FracVector.create([1, 2])


def test_surd_view_unview() -> None:
    source = SurdVector.sqrt_of(2)  # a SurdScalar, the scalar subclass
    view = VectorSurdView(source)
    plain = unview(view)
    assert isinstance(plain, SurdVector)
    assert not isinstance(plain, View)
    assert plain is source

    converted = VectorSurdView(FracVector.create([1, 2]))
    plain2 = unview(converted)
    assert type(plain2) is SurdVector
    assert not isinstance(plain2, View)


def test_native_view_unview_is_a_plain_tuple() -> None:
    view = VectorNativeView((1, F(1, 2)))
    plain = unview(view)
    assert type(plain) is tuple
    assert plain == (1, F(1, 2))
    # Leaves are shared, the container is shed.
    assert plain[1] is view[1]


def test_datastream_value_views_shed() -> None:
    bytes_view = BytestreamBytesView(b"payload")
    assert type(unview(bytes_view)) is bytes
    assert unview(bytes_view) == b"payload"

    string_view = TextstreamStringView("payload", kind="content")
    assert type(unview(string_view)) is str
    assert unview(string_view) == "payload"


def test_datastream_filename_views_shed(tmp_path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("x")
    for view_cls in (BytestreamFilenameView, TextstreamFilenameView):
        view = view_cls(str(path))
        plain = unview(view)
        assert type(plain) is str
        assert plain == str(path)


def test_interface_only_views_raise(tmp_path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("x")
    for view_cls in (BytestreamFileView, TextstreamFileView):
        view = view_cls(str(path))
        with pytest.raises(TypeError, match="interface-only"):
            unview(view)
        view.close()
