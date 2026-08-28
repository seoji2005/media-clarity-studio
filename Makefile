PYTHON ?= python3
export PYTHONPATH := src

.PHONY: static test smoke verify verify-task-022 fixtures-task-006 test-task-006 verify-task-006

static:
	$(PYTHON) -m compileall -q src tests scripts

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

smoke:
	$(PYTHON) scripts/smoke_task_022.py

verify: static test smoke

verify-task-022: verify

# TASK-006 — H-01~H-14 fixture runner (읽기 전용)
fixtures-task-006:
	$(PYTHON) -m media_clarity.eval_contracts --fixtures tests/fixtures/eval_contracts

# TASK-006 — 계약 unit·mutation test
test-task-006:
	$(PYTHON) -m unittest discover -s tests -p 'test_eval_contracts.py'

# TASK-006 단일 검증 진입점: fixture runner + 계약 test + 기존 전체 verify
verify-task-006: fixtures-task-006 test-task-006 verify
