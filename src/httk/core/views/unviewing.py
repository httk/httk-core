from typing import Any

from .view import View


def unview(obj: Any) -> Any:
    """
    Shed the httk View wrapper from ``obj``, returning a plain instance of the presented type.

    Unlike :func:`~httk.core.views.unwrapping.unwrap`, which goes *down* to the backend's raw
    source representation, ``unview`` goes *sideways*: it removes the httk wrapper while keeping
    the presentation the view exposes. The result is not promised to be a copy — it may alias
    the view's (or the original input's) storage; use the target representation's normal copy
    operation when independent mutation is required. A non-View input is returned unchanged.
    Views that only adapt an interface and have no faithful standalone value raise ``TypeError``.
    """
    if isinstance(obj, View):
        return obj.unview()
    return obj
