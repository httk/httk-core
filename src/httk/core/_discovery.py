import importlib, importlib.util, pkgutil

_DONE = False

def _discover_register_modules() -> None:
    global _DONE, subpackages
    if _DONE:
        return
    _DONE = True

    import httk  # safe: we're inside httk import, but httk.__path__ is already extended above

    found: list[str] = []
    prefix = "httk."

    for m in pkgutil.iter_modules(httk.__path__, prefix):
        if not m.ispkg:
            continue

        found.append(m.name)

        reg_name = m.name + "._register"  # e.g. httk.io._register
        if importlib.util.find_spec(reg_name) is not None:
            importlib.import_module(reg_name)

    return tuple(sorted(set(found)))
