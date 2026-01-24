from pathlib import Path
from typing import Any

from .plugins import PluginRegistry

_loaders = PluginRegistry()

def register_loader(*, name: str, loader: str, extensions: tuple[str, ...]) -> None:
    for ext in extensions:
        _loaders.register(key=ext.lower(), handler=loader, name=name)

def load(filename: str, **kwargs: Any) -> Any:
    ext = Path(filename).suffix.lower()
    if ext:
        return _loaders.dispatch(ext, filename, **kwargs)
    else:
        raise Exception("Could not deterine file type.")

def known_extensions() -> list[str]:
    return _loaders.keys()

