from abc import ABC
from typing import Any, ClassVar, Self, cast


class Backend[BackendT: Backend](ABC):
    r"""
    Abstract base class to be subclassed into classes that keep track of alternative
    representations of certain types of data, all adhering to a common API interface.

    The class variable backend_classes is a list of all classes that can carry the kind of data the subclass represents.

    A system of "hints" are used primarily to disambiguate between multiple valid interpretations of the same input object.
    Unless otherwise documented for a specific backend, extra hints that do not affect this interpretation are ignored.

    A set of backends are meant to be combined with a set of Views.

    Concrete backends implement ``_backend_adopt`` to accept an object and return an initialized
    backend instance, or ``None`` to decline it. The ``kind`` hint convention is used to
    disambiguate between multiple valid interpretations.

    :param backend: Source value or backend being adopted by the concrete backend.
    :param \**hints: Backend-specific initialization hints.
    """

    # Subclasses must implement this class variable, which only appear as a type annotation here
    backend_classes: ClassVar[list[type["Backend[Any]"]]]

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Try to adopt an object as an instance of this backend.

        :param obj: Source object to represent.
        :param \**hints: Backend-selection and disambiguation hints.
        :return: An initialized backend, or ``None`` when this backend declines ``obj``.
        """
        return None

    @classmethod
    def create(cls: type[Self], obj: Any, **hints: Any) -> Self:
        r"""
        Given a source data (obj) and a set of hints, create a backend from one of the alternatives in the class variable `backend_classes`.

        By design this creation depends heavily on order of the classes in `backend_classes`.
        Each class is tried in the order they appear until one of them is successful, in the sense that their `_backend_adopt` returns an initialized instance.
        Sometimes multiple backend classes can handle the same input type. In that case, dispatch is guided by keyword arguments ``**hints``,
        with the convention that:

        * if a hint named `kind` is given, a backend class should accept the object only if it matches that `kind`;
        * when `kind` matches, additional unrecognized hints may be ignored.

        :param obj: Source object to represent with a registered backend.
        :param \**hints: Backend-selection and disambiguation hints.
        :return: A backend that represents ``obj``.
        :raises TypeError: If no registered backend accepts ``obj`` and the hints.
        """
        for t in cls.backend_classes:
            instance = t._backend_adopt(obj, **hints)
            if instance is not None:
                return cast(Self, instance)
        raise TypeError(f"Cannot represent {type(obj)} as {cls.__name__}")

    def __init__(self, backend: Any, **hints: Any) -> None:
        pass

    def unwrap(self) -> Any:
        """
        Return the most raw representation possible of this backend, i.e., if it uses a backend with an internal representaion -
        or if it can (possibly lossly) convert itself into a more raw representation that still would be recognized as a <Something>Like type,
        that representation will be returned. If this is not possible, the instance itself is returned.

        :return: The backend's most raw available representation.
        """
        return self
