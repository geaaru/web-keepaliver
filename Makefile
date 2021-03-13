# Web Keepaliver
PYTHON ?= python3
PYTEST_ARG ?=
PYTHON_DIRS = web_keepaliver tests

.PHONY: flake8 pylint pytest coverage tarball test all

all:
	@echo "flake8         run flake8 on code"
	@echo "pylint         run pylint on code"
	@echo "pytest         run pytest on code"
	@echo "coverage       run coverage on code"
	@echo "test           run flake8, pylint, pytest"
	@echo "tarball        create package tarball"

test: flake8 pylint pytest

flake8:
	$(PYTHON) -m flake8 $(PYTHON_DIRS)

pylint:
	$(PYTHON) -m pylint $(PYTHON_DIRS)

pytest:
	$(PYTHON) -m pytest -vv tests/

tarball:
	$(PYTHON) setup.py sdist

coverage: $(generated)
	$(PYTHON) -m coverage run --source web_keepaliver -m pytest $(PYTEST_ARG) tests/
	$(PYTHON) -m coverage report --show-missing
