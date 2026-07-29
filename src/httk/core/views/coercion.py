"""General best-effort coercion into registered view or value classes."""

from collections.abc import Callable, Sequence
from typing import Any, cast

type Coercer = Callable[[Any, type], Any | None]

_coercers: list[Coercer] = []


def register_coercer(coercer: Coercer) -> None:
    """Append ``coercer`` to the registry, preserving registration order."""
    _coercers.append(coercer)


def view_class_coercer(view_classes: Sequence[type]) -> Coercer:
    """Return a coercer that tries matching view classes in ``view_classes`` order.

    A ``TypeError``, ``ValueError``, or ``OverflowError`` from a view constructor means that view
    cannot represent the value, so construction continues with the next matching class. If a
    candidate exposes ``_ensure_materialized()``, explicit coercion calls it so lazy views are
    materialized and deferred data errors follow the same fall-through contract.
    """

    def coerce_view(value: Any, target: type) -> Any | None:
        for cls in view_classes:
            if issubclass(cls, target):
                try:
                    candidate = cast(Any, cls)(value)
                    ensure_materialized = getattr(candidate, "_ensure_materialized", None)
                    if ensure_materialized is not None:
                        ensure_materialized()
                    return candidate
                except (TypeError, ValueError, OverflowError):
                    pass
        return None

    return coerce_view


def coerce(value: Any, target: Any) -> Any:
    """
    Coerce ``value`` to a target class or prototype instance.

    The exact string ``"natural"`` is a documented sentinel that returns ``value`` unchanged.
    Otherwise, a class target is used directly and an instance target is treated as a prototype,
    using its type. Values already matching the target are returned unchanged. Registered coercers
    are then tried in registration order, and the first non-``None`` result wins. If none succeeds,
    ``TypeError`` is raised naming the value type and target. Coercion is best effort and favors
    lossless view wrapping; individual coercers document any deliberately lossy conversion.
    """
    if isinstance(target, str) and target == "natural":
        return value
    tcls = target if isinstance(target, type) else type(target)
    if isinstance(value, tcls):
        return value
    for coercer in _coercers:
        result = coercer(value, tcls)
        if result is not None:
            return result
    raise TypeError(f"Cannot coerce {type(value)} to {target!r}")
