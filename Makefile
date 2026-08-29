PYTHON ?= python3
export PYTHONPATH := src

.PHONY: static test smoke verify verify-task-022 \
	fixtures-task-006 test-task-006 verify-task-006 \
	fixtures-task-028 test-task-028 smoke-task-028 verify-task-028

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

# TASK-028 — J-01~J-16 fixture runner (실제 production API를 임시 project root에서 호출)
fixtures-task-028:
	$(PYTHON) -m media_clarity.job_runtime --fixtures tests/fixtures/job_runtime

# TASK-028 — artifact store·job runtime 계약 unit·mutation test
test-task-028:
	$(PYTHON) -m unittest discover -s tests -p 'test_artifact_store.py'
	$(PYTHON) -m unittest discover -s tests -p 'test_job_runtime.py'

# TASK-028 — 임시 project root에서 store·runtime end-to-end (FFmpeg·네트워크 없음)
smoke-task-028:
	$(PYTHON) scripts/smoke_task_028.py

# TASK-028 단일 검증 진입점: fixture runner + 계약 test + smoke + 기존 전체 verify
verify-task-028: fixtures-task-028 test-task-028 smoke-task-028 verify
