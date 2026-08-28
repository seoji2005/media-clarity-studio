# REVIEW-019 — TASK-028 Gate H 고정 HEAD 재검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #36 `feat: add TASK-028 artifact store and resumable stage runtime` |
| Gate | H |
| 기준 `main` | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| 이전 검토 HEAD | `9c60ccb67d5475ce1c794852ccadfd82594383a3` |
| 고정 재검토 HEAD | `26139810bb4f3d8c1033d7802254c4144c370eac` |
| 구현 보고 tree | `f624324eaf79274bdc0f2e3c5cdd0e3dea230b67` |
| 직접 부모 | `9c60ccb67d5475ce1c794852ccadfd82594383a3` |
| 직전 리뷰 | REVIEW-018 / PR #37 / review commit `a08981795739901b9fa14733ff3e0a9afc614e8a` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-28 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**변경 요청 — Gate H. REVIEW-018 직접 지적 5건은 해소, 추가 필수 수정 4건.**

REVIEW-018의 다섯 원래 반례는 모두 기대한 안정 코드·위치·filesystem 결과로 차단됐다.
J-01~J-16, H-01~H-14, 전체 294 tests, TASK-028 smoke와 실제 FFmpeg smoke도
독립 실행에서 통과했다.

그러나 새 semantic validator는 attempt의 일부 상태 필드만 검사하고 저장소 그래프의
정체성·연결을 검사하지 않는다. 독립 반례에서 다음이 재현됐다.

1. attempt record 내부 ID를 실제 파일·job·stage와 다르게 바꿔도 cache hit가 되고,
   completed manifest가 존재하지 않는 attempt 파일을 가리킨다.
2. schema-valid이지만 job identity·pipeline·completed stage 집합이 모순인 manifest를
   semantic 오류로 거부하지 않고 조용히 덮어쓴다.
3. failed record에서 안정 error code/location을 삭제해도 semantic validator가 유효하다고 판정한다.
4. mixed-type seed key가 안정 `E_SCHEMA`가 아니라 raw `TypeError`를 낸다.

첫 두 항목은 완료 checkpoint와 manifest 연결을 깨뜨려 거짓 완료·복구 실패를 만들 수 있다.
TASK-028 §3.4~§3.6의 Job/Attempt semantic invariant와 content-addressed resume hard gate를
충족하지 않으므로 승인할 수 없다.

## 3. 원격 경계와 범위

- PR #36은 Open / Draft / 미병합, mergeable이다.
- base는 `main`, head는 `claude/task-028-resumable-runtime`이다.
- 고정 HEAD 직전 재확인에서 branch와 `26139810…`는 ahead 0 / behind 0 / identical이었다.
- 기준 main보다 2커밋 앞, 0커밋 뒤다.
- PR 전체 변경은 30파일 · +6,332 / -471이다.
- REVIEW-018 반영 커밋은 이전 HEAD보다 1커밋 앞이고 7파일 · +1,072 / -59다.
- 원격 commit status와 GitHub Actions workflow run은 없다.
- 새 7파일의 격리 트리 blob SHA는 원격 고정 SHA와 모두 일치했다.

| 파일 | blob SHA |
|---|---|
| `STATUS.md` | `90cb3ade4efc01e46063e89deb6dffc04fb59cb3` |
| `docs/tasks/TASK-028.md` | `4c1a57dfac079283c643f479b795557f26841eb4` |
| `schemas/job-v1.schema.json` | `09d072eac828d5c785a672c0f120e056bee28c93` |
| `src/media_clarity/artifact_store.py` | `0f80d7318068a2593041408aafc59cee0aef203d` |
| `src/media_clarity/job_runtime.py` | `302d931d9d691bfc1d348e82736d9112fb254dd4` |
| `tests/test_artifact_store.py` | `9684c5e9388d19fe60534ad0d1237b57fa0f32cf` |
| `tests/test_job_runtime.py` | `fef205eb4130f9bbeb26ab3b4d735b349d98714e` |

구현 branch, 구현 코드, schema, fixture와 PR 상태는 이 리뷰에서 수정하지 않았다.

## 4. 직접 실행 결과

| 명령 | 결과 |
|---|---|
| `make verify-task-028` | exit 0 — J 16/16, store 36, runtime 88, 전체 294, TASK-028 smoke PASS, FFmpeg smoke PASS |
| `make verify-task-006` | exit 0 — H 14/14, 계약 162, 전체 294, FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 294, FFmpeg smoke PASS |
| `make verify-task-028 PYTHON=python3.12` | exit 0 — J 16/16, 전체 294, smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — H 14/14, 계약 162, 전체 294, smoke PASS |

## 5. REVIEW-018 직접 지적 재검증

| REVIEW-018 반례 | 새 HEAD 실제 판정 |
|---|---|
| 빈 `completed` outputs | `E_CHECKPOINT_INVALID` @ 실제 `a0001.json/outputs`; callable 0회; record 불변 |
| completed + 최신 running | completed hit 유지, 최신 running은 `E_STATE_TRANSITION`·location·`interrupted_at`과 함께 interrupted |
| absolute `source_identity` | `E_UNSAFE_PATH @ source_identity`; 경로 미노출; root entry 0 |
| artifact 입력 변경 실패 | `E_INPUT_CHANGED @ stage_output`; record temp_paths와 실제 incoming 파일 정확 일치 |
| malformed seed `[{}]` | `E_SCHEMA @ seed_inputs/extract/0`; raw 예외 없음; root entry 0 |

따라서 REVIEW-018 M-01~M-05의 **직접 반례**는 해소됐다. `interrupted_at`은 죽은 시각이
아니라 재시작이 전이를 관측한 시각으로 사용되며, `ended_at`을 추정하지 않는 판단도 승인한다.

## 6. 추가 필수 수정

### M-01-R1 — attempt record 정체성이 파일·job·stage와 연결되지 않는다

실제 `jobs/job-a/stages/extract/attempts/a0001.json`에서 schema-valid하게 다음 값만 바꿨다.

- `attempt_id = "a9999"`
- `job_id = "job-other"`
- `stage_id = "stage-other"`

출력 artifact와 cache key는 그대로 두었다. 재실행 결과:

- cache status: `hit`
- 반환 attempt ID: `a9999`
- job status: `completed`
- manifest attempt path: `jobs/job-a/stages/extract/attempts/a9999.json`
- 위 manifest 경로의 실제 파일: **없음**
- 원래 `a0001.json`: 그대로 존재

`_read_attempts()`가 record 내부 상태만 검사하고 경로·호출 spec과의 identity를 검사하지 않으며,
`_lookup_cache()`가 record만 반환해 실제 path를 잃기 때문에 dangling completed manifest가
생긴다.

필수 수정:

- attempt의 `job_id`, `stage_id`, `attempt_id`를 현재 spec·stage·파일 stem과 정확히 비교한다.
- `attempt_number`와 계약된 `aNNNN` ID의 수치가 일치하는지 검사한다.
- 같은 stage 디렉터리에서 attempt ID와 attempt number 중복을 거부한다.
- cache 후보는 실제 `(path, record)` 연결을 유지하고 manifest는 검증한 실제 path만 기록한다.
- 불일치는 기존 record를 수정하지 않고 `E_CHECKPOINT_INVALID`와 실제 필드/path 위치로 거부한다.
- job ID, stage ID, attempt ID, attempt number를 각각 하나씩 바꾼 반례를 추가한다.

### M-01-R2 — Job manifest semantic invariant가 없다

기존 valid completed manifest에서 다음을 schema-valid하게 바꿨다.

- `job_id = "job-other"`
- `pipeline_id = "pipe-other"`
- `status = "completed"`
- `stages = []`
- 기존 `job_fingerprint`는 유지

schema finding은 0건이었다. 재실행은 cache hit·completed로 성공하고 손상 manifest를
현재 값으로 조용히 덮어썼다.

REVIEW-018은 Job/Attempt semantic validator를 요구했고 TASK-028 §3.6도 schema와 semantic
invariant를 모두 요구한다. 현재 구현은 Attempt 일부만 검사한다.

필수 수정:

- 기존 manifest를 사용하거나 덮어쓰기 전에 Job semantic validator를 실행한다.
- schema/runtime version, job ID, pipeline ID, source identity, DAG와 job fingerprint가 현재
  spec 및 canonical 계산값과 일치하는지 검사한다.
- stage ID의 유일성·DAG membership을 검사한다.
- completed manifest는 DAG의 모든 stage를 정확히 한 번 포함하고 모든 stage state가
  실제 존재하는 completed attempt record를 가리켜야 한다.
- stage state의 attempt ID/path/status/cache key가 실제 record와 일치해야 한다.
- running/failed manifest도 기록된 stage 집합과 실제 attempt graph가 모순되지 않게 한다.
- 모순된 기존 manifest를 조용히 고치거나 덮어쓰지 않고 `E_CHECKPOINT_INVALID`과 실제 위치로 거부한다.
- identity mismatch, completed-empty-stages, dangling attempt path, stage/record status mismatch를
  독립 회귀로 추가한다.

### M-01-R3 — failed/running 상태의 error evidence 규칙이 불완전하다

실제 failed record에서 `error_code`와 `error_location`을 삭제했다. schema finding과
`check_attempt_semantics()` finding이 모두 0건이었고 `_read_attempts()`도 record를 받아들였다.

`_fail_attempt()`가 정상 경로에서는 두 필드를 쓰더라도, checkpoint validator가 손상 evidence를
유효하다고 판정하면 복구 계약이 완결되지 않는다.

필수 수정:

- failed 상태는 `error_code`와 `error_location`을 필수로 한다.
- running 상태는 `error_code`, `error_location`, `interrupted_at`, 종료 필드를 모두 금지한다.
- interrupted 상태의 code는 계약된 `E_STATE_TRANSITION`인지 검사한다.
- stored error code가 선언된 안정 오류 코드 집합인지 검사한다.
- 각 필드 누락·금지·잘못된 code 반례와 실제 해석 가능한 location을 고정한다.

### M-05-R1 — mixed-type seed key에서 raw TypeError가 노출된다

`seed_inputs={"extract": [], 1: []}`을 public API에 전달하면 `sorted(seed_inputs)`에서
raw `TypeError`가 발생한다. filesystem mutation은 없었지만 M-05가 요구한 안정 `E_SCHEMA`
계약과 구현 commit의 “raw KeyError/TypeError가 밖으로 나가지 않는다”는 주장에 어긋난다.

필수 수정:

- key를 정렬하기 전에 모든 seed key가 문자열인지 검사한다.
- non-string key는 값을 메시지에 복제하지 않고 `E_SCHEMA @ seed_inputs` 또는 실제 해석 가능한
  부모 위치로 거부한다.
- mixed string/integer, integer-only, empty/invalid stage ID를 각각 검사한다.
- 거부 뒤 filesystem entry 0과 raw 예외 미노출을 고정한다.

## 7. 회귀 보존 요구

다음은 새 HEAD에서 통과했으며 재작업이 약화하면 안 된다.

- REVIEW-018 다섯 직접 반례
- J-01~J-16 정확히 16건
- H-01~H-14 정확히 14건과 TASK-006 계약 162
- 전체 294 tests와 실제 FFmpeg smoke
- CAS streaming hash, no-overwrite, dedupe, 손상 거부
- stale running의 선행 interrupted 전이
- 실패 temp·error code·location 연결
- source identity 경로 차단과 비밀값 미노출
- valid seed의 artifact 검증과 cache key 참여
- downstream invalidation과 독립 branch cache 재사용

재작업은 M-01-R1~R3·M-05-R1과 직접 회귀에 한정한다. worker supervision, 멀티프로세스,
GC, 실제 ASR·번역 stage, 외부 dependency, CI를 추가하지 않는다.

## 8. 남은 미검증 경계

- Windows 11/NTFS 실제 실행
- hard-link 미지원 filesystem의 실제 동작
- 실제 프로세스 강제 종료와 OS crash durability
- 멀티프로세스/TOCTOU 경합
- JSON Schema Draft 2020-12 전체 구현과 외부 meta-validator

이번 네 결함은 Linux 단일 프로세스 기본 경로에서 직접 재현되므로 위 환경 한계로 설명되지 않는다.

## 9. 다음 허용 행동

1. Claude Code가 기존 `claude/task-028-resumable-runtime` branch에
   M-01-R1~R3·M-05-R1과 직접 회귀만 새 focused commit으로 반영한다.
2. amend, rebase, force-push, merge, Ready 전환, branch 삭제를 하지 않는다.
3. 기존 테스트를 삭제·skip·완화하지 않는다.
4. REVIEW-018의 다섯 반례와 REVIEW-019의 네 반례를 모두 재실행한다.
5. J-01~J-16·H-01~H-14·전체 verify·Python 3.12를 다시 실행한다.
6. 새 HEAD를 보고하면 Lean Root가 새 고정 HEAD에서 Gate H 재검토한다.

이 변경 요청은 구현 PR의 병합이나 종료가 아니다. PR #36은 Draft 상태로 유지한다.
