# Allow httk.* subpackages to be provided by other distributions.
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

from .core._discovery import _discover_register_modules as _discover_register_modules
subpackages = _discover_register_modules()

# Core API
from .core import *
