"""General best-effort coercion into registered view or value classes."""

from collections.abc import Callable, Sequence
from typing import Any, cast

from .view import View

type Coercer = Callable[[Any, type], Any | None]

_coercers: list[tuple[tuple[type, ...], Coercer]] = []


def register_coercer(coercer: Coercer, target: Any) -> None:
    """Append ``coercer`` to the registry, preserving registration order.

    ``target`` declares what the coercer can coerce *into*: a class, a tuple of classes, or
    ``typing.Any`` for a fully general coercer. During :func:`coerce`, a registered coercer is
    only tried when the requested target class is a subclass of (one of) its declared targets;
    ``Any`` matches every target. Invalid declarations raise ``TypeError`` eagerly.
    """
    if target is Any:
        targets: tuple[type, ...] = (object,)
    elif isinstance(target, tuple):
        targets = target
    else:
        targets = (target,)
    if not targets or not all(isinstance(entry, type) for entry in targets):
        raise TypeError(f"register_coercer target must be a class, tuple of classes, or typing.Any, got {target!r}")
    _coercers.append((targets, coercer))


def _try_view(view_cls: type, value: Any) -> Any | None:
    """Construct ``view_cls(value)`` and materialize it, or ``None`` if it cannot represent it.

    A ``TypeError``, ``ValueError``, or ``OverflowError`` from construction means the view cannot
    represent the value. If the candidate exposes ``_ensure_materialized()``, explicit coercion
    calls it so lazy views are materialized and deferred data errors follow the same
    fall-through contract.
    """
    try:
        candidate = cast(Any, view_cls)(value)
        ensure_materialized = getattr(candidate, "_ensure_materialized", None)
        if ensure_materialized is not None:
            ensure_materialized()
        return candidate
    except (TypeError, ValueError, OverflowError):
        return None


def view_class_coercer(view_classes: Sequence[type]) -> Coercer:
    """Return a coercer that tries matching view classes in ``view_classes`` order."""

    def coerce_view(value: Any, target: type) -> Any | None:
        for cls in view_classes:
            if issubclass(cls, target):
                candidate = _try_view(cls, value)
                if candidate is not None:
                    return candidate
        return None

    return coerce_view


def coerce(value: Any, target: Any) -> Any:
    """
    Coerce ``value`` to a target class or prototype instance.

    The exact string ``"natural"`` is a documented sentinel that returns ``value`` unchanged.
    Otherwise, a class target is used directly and an instance target is treated as a prototype,
    using its type. Values already matching the target are returned unchanged. A target that is a
    :class:`~httk.core.views.view.View` subclass is then tried directly as a view conversion of
    ``value``, so any view family works without a registered coercer. Failing that, registered
    coercers whose declared targets match are tried in registration order, and the first
    non-``None`` result wins. If none succeeds, ``TypeError`` is raised naming the value type and
    target. Coercion is best effort and favors lossless view wrapping; individual coercers
    document any deliberately lossy conversion.
    """
    if isinstance(target, str) and target == "natural":
        return value
    tcls = target if isinstance(target, type) else type(target)
    if isinstance(value, tcls):
        return value
    if issubclass(tcls, View):
        candidate = _try_view(tcls, value)
        if candidate is not None:
            return candidate
    for targets, coercer in _coercers:
        if not issubclass(tcls, targets):
            continue
        result = coercer(value, tcls)
        if result is not None:
            return result
    raise TypeError(f"Cannot coerce {type(value)} to {target!r}")
