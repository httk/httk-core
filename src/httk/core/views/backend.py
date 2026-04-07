from typing import Any, ClassVar, Self, cast


class Backend:
    """
    Abstract base class to be subclassed into classes that keep track of alternative
    representations of certain types of data, all adhering to a common API interface.

    The class variable backend_classes is a list of all classes that can carry the kind of data the subclass represents.

    A system of "hints" are used primarily to disambiguate between multiple valid interpretations of the same input object.
    Unless otherwise documented for a specific backend, extra hints that do not affect this interpretation are ignored.

    A set of backends are meant to be combined with a set of Views.
    """

    backend_classes: ClassVar[list[type["Backend"]]] = []

    @classmethod
    def create(cls: type[Self], obj: Any, **hints: Any) -> Self:
        """
        Given a source data (obj) and a set of hints, create a backend from one of the alternatives in the class variable `backend_classes`.

        By design this creation depends heavily on order of the classes in `backend_classes`.
        Each class is tried in the order they appear until one of them is successful, in the sense that their `__new__` does not return None.
        Sometimes multiple backend classes can handle the same input type. In that case, dispatch is guided by keyword arguments `**hints`,
        with the convention that:

        * if a hint named `kind` is given, a backend class should accept the object only if it matches that `kind`;
        * when `kind` matches, additional unrecognized hints may be ignored.
        """
        for t in cls.backend_classes:
            instance = t(obj, **hints)
            if instance is not None:
                return cast(Self, instance)
        raise TypeError(f"Cannot represent {type(obj)} as {cls.__name__}")

    def unwrap(self) -> Any:
        """
        Return the most raw representation possible of this backend, i.e., if it uses a backend with an internal representaion -
        or if it can (possibly lossly) convert itself into a more raw representation that still would be recognized as a <Something>Like type,
        that representation will be returned. If this is not possible, the instance itself is returned.
        """
        return self
