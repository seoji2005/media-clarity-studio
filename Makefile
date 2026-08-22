PYTHON ?= python3
export PYTHONPATH := src

.PHONY: static test smoke verify verify-task-022

static:
	$(PYTHON) -m compileall -q src tests scripts

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

smoke:
	$(PYTHON) scripts/smoke_task_022.py

verify: static test smoke

verify-task-022: verify
