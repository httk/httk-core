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
        - if `obj` is already one of the accepted views, unwrap its underlying backend to adopt it;
        - if `obj` is a backend inheriting from the right superclass, return it unchanged.
        - if `obj` otherwise try to create a backend from that superclass via `backend_cls.create(obj, **hints)`;

        `hints` are forwarded for backend selection/disambiguation.
        """
        if isinstance(obj, cls._view_base_cls):
            return obj._backend
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
