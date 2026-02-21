# httk-core

This is the central lightweight "stub" dependency of all httk2 modules.
It:

* Sets up the `httk` package prefix
* Provides a few convinience functions under `httk.core`, including some aggregate handlers such as `load`, which allows "loading anything" to which httk2 modules can register handlers.

Other modules, e.g., `httk-io` installs under the httk package prefix and can be used as, e.g. `import httk.io`.
