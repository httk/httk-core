"""A single canonical "not provided" sentinel, shared across httk.

``MISSING`` marks an argument that was not passed, as distinct from an explicit ``None``.
Its primary use is a ``__new__(cls, value=MISSING)`` default: it lets pickle and copy rebuild
an empty instance through the default protocol (``object.__new__`` with no arguments), so a class
whose real ``__new__`` requires an argument can still rely on plain ``__getstate__``/``__setstate__``
instead of a bespoke ``__reduce__``.

Unlike ``object()`` or ``dataclasses.MISSING``, ``MISSING`` pickles **by reference** —
``pickle.loads(pickle.dumps(MISSING)) is MISSING`` — so it stays a valid identity sentinel even
when carried inside pickled state.
"""

from typing import Final


class MissingType:
    """The type of the :data:`MISSING` sentinel; a singleton with a stable pickle identity."""

    _instance: "MissingType | None" = None

    def __new__(cls) -> "MissingType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False

    def __reduce__(self) -> str:
        # Pickle by reference to the module global, so the unpickled value is the same singleton.
        return "MISSING"


MISSING: Final = MissingType()
"""The shared sentinel for an unset/not-provided value."""
