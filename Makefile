PYTHON ?= python3
export PYTHONPATH := src

.PHONY: static test smoke verify verify-task-022 \
	fixtures-task-006 test-task-006 verify-task-006 \
	fixtures-task-028 test-task-028 smoke-task-028 verify-task-028 \
	fixtures-task-029 test-task-029 audit-task-029 verify-task-029 \
	preflight-task-031 test-task-031-preflight verify-task-031-preflight \
	test-task-031-evidence verify-task-031-evidence \
	test-task-031-manifest-report verify-task-031-manifest-report \
	test-task-031-matrix verify-task-031-matrix \
	preflight-task-032 probe-task-032-work-cpu fixtures-task-032 \
	test-task-032-preflight verify-task-032-preflight

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

# TASK-029 — K-* fixture runner (읽기 전용)
fixtures-task-029:
	$(PYTHON) -m media_clarity.subtitle_contracts --fixtures tests/fixtures/subtitle_contracts --require-all-cases

# TASK-029 — 자막 spine 계약 unit·mutation test
test-task-029:
	$(PYTHON) -m unittest discover -s tests -p 'test_subtitle_contracts.py'

# TASK-029 — fixture + input/schema/validator-code mutation 감사
# (schema·validator mutation은 저장소 밖 임시 사본에서만 수행한다)
audit-task-029:
	$(PYTHON) scripts/verify_task_029.py

# TASK-029 단일 검증 진입점: fixture runner + 계약 test + 3분류 mutation 감사 + 기존 전체 verify
verify-task-029: fixtures-task-029 test-task-029 audit-task-029 verify

# TASK-031 첫 구현 slice — 고정 dependency/model 준비 manifest (network/model 실행 없음)
preflight-task-031:
	$(PYTHON) -m media_clarity.calibration validate

test-task-031-preflight:
	$(PYTHON) -m unittest discover -s tests -p 'test_calibration_preflight.py'

# 준비 manifest 자체는 통과해야 하지만 Windows lock/model readiness는 아직 별도 hard gate다.
verify-task-031-preflight: preflight-task-031 test-task-031-preflight static

# TASK-031 offline evidence core — 실제 TASK-028 attempt/CAS 기반 identity mutation test
test-task-031-evidence:
	$(PYTHON) -m unittest discover -s tests -p 'test_calibration_evidence.py'

# Windows/model/GPU 없이 실행 가능한 evidence core + 기존 preflight 회귀
verify-task-031-evidence: test-task-031-evidence test-task-031-preflight static

# TASK-031 manifest/report evidence spine — 닫힌 문서와 CAS cross-reference 검증
test-task-031-manifest-report:
	$(PYTHON) -m unittest discover -s tests -p 'test_calibration_manifest_report.py'

# timing/NVML/Windows 없이 정직한 incomplete spine과 기존 evidence/preflight 회귀
verify-task-031-manifest-report: test-task-031-manifest-report test-task-031-evidence test-task-031-preflight static

# TASK-031 exact synthetic matrix — 8 logical cells, 12 unique measured stages
test-task-031-matrix:
	$(PYTHON) -m unittest discover -s tests -p 'test_calibration_exact_matrix.py'

# Exact coverage/mutation matrix + previously merged TASK-031 evidence ladders
verify-task-031-matrix: test-task-031-matrix verify-task-031-manifest-report

# TASK-032 first implementation slice — closed preparation contract, no model/network use
preflight-task-032:
	$(PYTHON) -m media_clarity.asr_screen validate

# Honest current Work CPU receipt; explicitly makes no Windows/GPU compatibility claim
probe-task-032-work-cpu:
	$(PYTHON) -m media_clarity.asr_screen probe-work-cpu

# Tiny synthetic CAS and controlled interruption/resume fixtures (no evaluation media)
fixtures-task-032:
	$(PYTHON) scripts/task_032_fixture.py

test-task-032-preflight:
	$(PYTHON) -m unittest discover -s tests -p 'test_task032_preflight.py'

verify-task-032-preflight: preflight-task-032 probe-task-032-work-cpu \
	fixtures-task-032 test-task-032-preflight static
