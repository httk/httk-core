from typing import Any


def unwrap(obj: Any) -> Any:
    """
    Given a Backend or a View, return the most raw representation possible, i.e., if the backend has an internal representaion -
    or if it can (possibly lossly) convert itself into a more raw representation that still would be recognized as a <Something>Like type,
    that representation will be returned. If this is not possible, the instance itself is returned.

    :param obj: Value, backend, or view to unwrap.
    :return: The most raw available representation.
    """
    if hasattr(obj, "unwrap"):
        return obj.unwrap()
    return obj
