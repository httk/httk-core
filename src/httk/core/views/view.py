from typing import Any, ClassVar

from .backend import Backend
from .unwrapping import unwrap


class View[BackendT: Backend]:
    """
    A set of views allow manipulating data and state of a backend through different interfaces.
    Hence, creating a View from a Backend, or from another View, allows to read and operate on the data through the interface of that view,
    even if it is not the natural representation of the underlying data.

    Important: views are always meant to reference the data and state of *the same* underlying object, hence, e.g.:

    * If a function is given an X object, and the function applies an Xvariant1View and then calls, e.g., close() via that view,
      the expectation should be that the original X object is also closed.
    * When, e.g., a TextstreamStringView is created on an already partially read stream, only the unread data will appear through that string interface.

    All backends and views of the same kind of data (X) should be combined into a type union XLike that functions use to declare they support this kind of data.
    Such functions should start with creating a View on the passed data, giving them access to the data in a single desired format.

    Views are lazy by default: construction stores only the backend, while
    ``cached_property`` shadows and group fills materialize presentation state on first access.
    Size fills to the subset served by each backend call; validate before assigning, never read a
    shadowed attribute from a fill, and document why a view must remain eager. The explicit
    ``coerce_view()``/``coerce()`` paths materialize via ``_ensure_materialized()``; laziness is
    for pass-through use.
    """

    # Python typing, and mypy in particular, have trouble with variables being assigned abstract base classes
    _backend_base_cls: ClassVar[Any]  # Subclass of Backend that defines a set of backends for similar data
    _view_base_cls: ClassVar[Any]  # Subclass of view that defines a set of views of similar data
    _backend: BackendT

    @classmethod
    def _prepare_backend(
        cls,
        obj: Any,
        hints: dict[str, Any],
    ) -> BackendT:
        """
        Normalize an arbitrary backend/view/raw object into a backend suitable for constructing a view.

        Behavior:
        - if `obj` is already one of the accepted views, unwrap its underlying backend to adopt it
          (a backend-less view instance, e.g. built by inherited value-class algebra, falls through
          to backend creation like a raw value);
        - if `obj` is a backend inheriting from the right superclass, return it unchanged.
        - if `obj` otherwise try to create a backend from that superclass via `backend_cls.create(obj, **hints)`;

        `hints` are forwarded for backend selection/disambiguation.
        """
        if isinstance(obj, cls._view_base_cls):
            backend = getattr(obj, "_backend", None)
            if backend is not None:
                return backend
        if not isinstance(obj, cls._backend_base_cls):
            return cls._backend_base_cls.create(obj, **hints)
        return obj

    def unwrap(self) -> Any:
        """
        Return the most raw representation possible of this view, i.e., if it uses a backend with an internal representaion -
        or if it can (possibly lossly) convert itself into a more raw representation that still would be recognized as a <Something>Like type,
        that representation will be returned. If this is not possible, the instance itself is returned.
        """
        return unwrap(self._backend)

    def unview(self) -> Any:
        """
        Return the view's presented representation as a plain, non-View instance.

        Concrete views that mimic a value type override this to shed the httk wrapper; the result
        may alias the view's storage (no copy is promised). The default raises ``TypeError``,
        which is the correct behavior for views that only adapt an interface and have no faithful
        standalone value.
        """
        raise TypeError(f"{type(self).__name__} is an interface-only view with no standalone plain value")
