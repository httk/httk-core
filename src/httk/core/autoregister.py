from __future__ import annotations

import importlib
import importlib.util
import pkgutil

_DONE = False


def autoregister() -> None:
    global _DONE
    if _DONE:
        return
    _DONE = True

    import httk  # ensures httk.__path__ is set

    prefix = httk.__name__ + "."
    for m in pkgutil.iter_modules(httk.__path__, prefix):
        if not m.ispkg:
            continue
        reg_name = m.name + "._register"  # e.g. httk.io._register
        if importlib.util.find_spec(reg_name) is None:
            continue
        importlib.import_module(reg_name)
