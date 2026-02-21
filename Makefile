PYTHON ?= python3

.PHONY: docs docs-clean format format-check typecheck_pyright typecheck lint

docs:
	$(PYTHON) -m sphinx -b html -W --keep-going docs docs/_build/html

docs-live:
	sphinx-autobuild docs docs/_build/html

docs-clean:
	rm -rf docs/_build docs/reference/autoapi


clean: docs-clean
	find . -name "*.pyc" -print0 | xargs -0 rm -f
	find . -name "*~" -print0 | xargs -0 rm -f
	find . -name "__pycache__" -print0 | xargs -0 rm -rf

format:
	$(PYTHON) -m ruff check src examples --select F401 --fix
	$(PYTHON) -m isort src examples
	$(PYTHON) -m black src examples

format-check:
	$(PYTHON) -m ruff check src examples
	$(PYTHON) -m isort --check-only src examples
	$(PYTHON) -m black --check src examples

typecheck_pyright:
	$(PYTHON) -m pyright

typecheck:
	$(PYTHON) -m mypy

lint:
	$(PYTHON) -m ruff check src examples
