# REVIEW-020 — TASK-028 Gate H 고정 HEAD 재검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #36 `feat: add TASK-028 artifact store and resumable stage runtime` |
| Gate | H |
| 기준 `main` | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| 이전 검토 HEAD | `26139810bb4f3d8c1033d7802254c4144c370eac` |
| 고정 재검토 HEAD | `45459b0331113ea18319cdf6072e24e64b6c3da4` |
| 구현 보고 tree | `eabcacddf15d523bdcee467dd5057612108145d6` |
| 직접 부모 | `26139810bb4f3d8c1033d7802254c4144c370eac` |
| 직전 리뷰 | REVIEW-019 / PR #38 / review commit `c57e22b507a97d1b7f63bc8ab530bb7935efaa2c` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-28 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**변경 요청 — Gate H. REVIEW-018·019 직접 반례는 해소, 추가 필수 수정 2건.**

REVIEW-019의 attempt identity, manifest identity, failed evidence, mixed seed key 반례는 모두
기대한 안정 코드·실제 위치·filesystem 결과로 차단됐다. REVIEW-018의 다섯 반례도 계속
차단됐고, J-01~J-16, H-01~H-14, 전체 328 tests, TASK-028 smoke와 실제 FFmpeg smoke가
독립 실행에서 통과했다.

그러나 기존 manifest가 가리키는 attempt path의 **canonical 정체성**과 비완료 manifest의
**deterministic completed prefix**가 아직 검증되지 않는다. 독립 반례에서 다음이 재현됐다.

1. 유효한 attempt record를 canonical 디렉터리 밖의 다른 project-relative 경로로 옮긴 뒤
   manifest가 그 복사본을 가리키게 해도 semantic finding 없이 수용한다. 재실행은 stage를
   다시 수행하고 새 canonical record를 만들며 기존 manifest를 조용히 덮어쓴다.
2. `alpha -> beta` DAG에서 failed manifest의 stage 집합을 downstream `beta` 하나만 남겨도
   semantic finding 없이 수용한다. 재실행은 cache hit로 성공하고 모순 manifest를 조용히
   completed로 덮어쓴다.

두 항목 모두 schema-valid checkpoint가 실제 runtime이 생성할 수 없는 그래프를 표현하도록
허용한다. 손상 evidence를 오류로 보존하지 않고 재실행 또는 덮어쓰기로 정상화하므로
TASK-028의 content-addressed resume·복구 hard gate를 충족하지 않는다.

## 3. 원격 경계와 범위

- PR #36은 Open / Draft / 미병합, mergeable이다.
- base는 `main`, head는 `claude/task-028-resumable-runtime`이다.
- 고정 HEAD 직전 재확인에서 branch와 `45459b03…`는 ahead 0 / behind 0 / identical이었다.
- 기준 main보다 3커밋 앞, 0커밋 뒤다.
- PR 전체 변경은 30파일 · +7,320 / -471이다.
- REVIEW-019 반영 커밋은 이전 HEAD보다 1커밋 앞이고 4파일 · +1,019 / -31이다.
- 원격 commit status와 GitHub Actions workflow run은 없다.
- 새 4파일의 격리 트리 blob SHA는 원격 고정 SHA와 일치했다.

| 파일 | blob SHA |
|---|---|
| `STATUS.md` | `f18dd33fa57ddffea0d178d8e15023afcae6c655` |
| `docs/tasks/TASK-028.md` | `ec6f0d925ec03b6b711336a7c3b2dbbe9c03ef39` |
| `src/media_clarity/job_runtime.py` | `124d5019d3b6bf9214c1cf9a945fbe74f216c742` |
| `tests/test_job_runtime.py` | `67427151e1bde5db05c19f9df7a09819424762a1` |

구현 branch, 구현 코드, schema, fixture와 PR 상태는 이 리뷰에서 수정하지 않았다.

## 4. 직접 실행 결과

| 명령 | 결과 |
|---|---|
| `make verify-task-028` | exit 0 — J 16/16, store 36, runtime 122, 전체 328, TASK-028 smoke PASS, FFmpeg smoke PASS |
| `make verify-task-006` | exit 0 — H 14/14, 계약 162, 전체 328, FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 328, FFmpeg smoke PASS |
| `make verify-task-028 PYTHON=python3.12` | exit 0 — J 16/16, 전체 328, smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — H 14/14, 계약 162, 전체 328, smoke PASS |

구현자가 보고한 mutation 74종 중 72종 탐지와 2개 상위 중복 방어 설명은 수용 가능하다.
이번 변경 요청의 원인은 mutation 비율이 아니라 아래 production API 반례다.

## 5. 이전 직접 지적 재검증

### REVIEW-019

| 반례 | 새 HEAD 실제 판정 |
|---|---|
| attempt ID/job/stage/number 단일 조작 | 각 `E_CHECKPOINT_INVALID`; callable 0회; attempt·manifest byte 불변 |
| manifest identity + `completed`/`stages=[]` | `E_CHECKPOINT_INVALID @ .../manifest.json/job_id`; callable 0회; byte 불변 |
| failed의 error evidence 삭제 | `E_CHECKPOINT_INVALID` 2건; 선언되지 않은 error code도 거부 |
| mixed seed key | `E_SCHEMA @ seed_inputs`; raw 예외 없음; root entry 0; key 값 미노출 |

### REVIEW-018

빈 completed outputs, stale running, absolute source identity, artifact 입력 변경, malformed seed의
다섯 반례도 모두 REVIEW-019에 기록한 코드·위치·filesystem 결과로 계속 차단됐다.

따라서 REVIEW-018·019의 **직접 반례**는 해소됐다. fingerprint를 semantic 검사보다 먼저
처리해 J-11의 `E_RESUME_FINGERPRINT`를 유지하는 판단과, 새 evidence가 없는 거부에서 기존
manifest를 수정하지 않는 판단도 유지 승인한다.

## 6. 추가 필수 수정

### M-01-R2-R1 — manifest의 attempt path가 canonical record 경로에 결박되지 않는다

정상 one-stage completed run 뒤 다음과 같이 변형했다.

1. 실제 `jobs/job-a/stages/extract/attempts/a0001.json`을
   `jobs/job-a/relocated/a0001.json`으로 복사한다.
2. canonical 원본을 삭제한다.
3. manifest의 `attempt_path`를 존재하는 relocated copy로 바꾼다.

record 내부 `job_id`, `stage_id`, `attempt_id`, `attempt_number`, cache key와 outputs는 모두
그대로다. 현재 `_check_stage_state()`는 portable path, 존재, schema, manifest-record 필드만
검사하므로 결과는 다음과 같았다.

```json
{
  "semantic_findings": [],
  "run_status": "completed",
  "calls": 1,
  "manifest_unchanged": false,
  "canonical_attempt_created": true
}
```

즉 파일 stem 대조가 있어도 parent path가 다른 record를 유효한 checkpoint로 받아들인다.
그 뒤 cache discovery는 canonical 디렉터리만 읽으므로 miss가 되고, 비용이 큰 stage를 다시
실행한 다음 손상 manifest를 덮어쓴다.

필수 수정:

- 각 stage state의 `attempt_path`가 현재 `job_id`, `stage_id`, `attempt_id`로 계산한
  canonical relative path와 문자열 수준에서 정확히 일치하는지 검사한다.
- 단순히 존재하고 내부 record가 일치하는 relocated/aliased path는 허용하지 않는다.
- manifest 검사에서도 가리킨 record에 `check_attempt_identity()`와 필요한 attempt semantic
  검사를 실제 path·spec·stage와 함께 적용한다.
- 불일치는 `E_CHECKPOINT_INVALID @ .../attempt_path`, callable 0회, 기존 manifest와 attempt
  evidence byte 불변으로 거부한다.
- relocated existing copy, 잘못된 job/stage parent, canonical valid path를 각각 회귀로 고정한다.

### M-01-R2-R2 — running/failed manifest의 stage 집합이 실행 가능한 prefix인지 검사하지 않는다

정상 `alpha -> beta` completed run 뒤 manifest만 다음처럼 바꿨다.

- `status = "failed"`
- `stages = [beta state]`
- 실제 alpha·beta completed attempt record는 그대로 유지

현재 validator는 non-completed manifest에서 stage ID의 DAG membership과 각 record 연결만
검사하고, dependency closure·실행 순서를 검사하지 않는다. 결과는 다음과 같았다.

```json
{
  "semantic_findings": [],
  "run_status": "completed",
  "calls": 0,
  "manifest_unchanged": false
}
```

현재 synchronous runtime은 `deterministic_order(spec)` 순서대로 실행하며 각 성공 stage를
manifest에 누적하므로 저장된 stage list는 그 순서의 정확한 completed prefix여야 한다.
`[beta]`는 runtime이 만들 수 없고 alpha dependency evidence가 빠진 모순 graph다.

필수 수정:

- manifest의 stage ID 순서가 `deterministic_order(spec)`의 정확한 prefix인지 검사한다.
- `completed`는 전체 순서와 정확히 같고, running/failed 등 비완료 상태는 빈 prefix를 포함한
  유효 prefix만 허용한다.
- downstream-only subset, dependency gap, out-of-order state를 `E_CHECKPOINT_INVALID`와 실제
  `stages` 또는 offending stage 위치로 거부한다.
- 거부 시 callable 0회, 기존 manifest·attempt byte 불변을 고정한다.
- 기존 valid `alpha` prefix와 그 상태에서의 cache resume은 계속 허용한다.

## 7. 회귀 보존 요구

다음은 새 HEAD에서 통과했으며 재작업이 약화하면 안 된다.

- REVIEW-018 다섯 직접 반례와 REVIEW-019 네 직접 반례
- J-01~J-16 정확히 16건
- H-01~H-14 정확히 14건과 TASK-006 계약 162
- 전체 328 tests와 실제 FFmpeg smoke
- CAS streaming hash, no-overwrite, dedupe, 손상 거부
- stale running의 선행 interrupted 전이
- failure temp·error code·location 연결
- source identity 경로 차단과 비밀값 미노출
- valid seed artifact 검증과 cache key 참여
- downstream invalidation과 독립 branch cache 재사용
- J-11 fingerprint 오류 우선순위

재작업은 M-01-R2-R1·R2와 직접 회귀에 한정한다. schema 변경은 현재 계약이 이미 canonical
path와 DAG를 표현하므로 필요하지 않다. worker supervision, 멀티프로세스, GC, 실제 ASR·번역
stage, 외부 dependency, CI를 추가하지 않는다.

## 8. 남은 미검증 경계

- Windows 11/NTFS 실제 실행
- hard-link 미지원 filesystem의 실제 동작
- 실제 프로세스 강제 종료와 OS crash durability
- 멀티프로세스/TOCTOU 경합
- JSON Schema Draft 2020-12 전체 구현과 외부 meta-validator

이번 두 결함은 Linux 단일 프로세스 기본 경로에서 직접 재현되므로 위 환경 한계로 설명되지 않는다.

## 9. 다음 허용 행동

1. Claude Code가 기존 `claude/task-028-resumable-runtime` branch에 M-01-R2-R1·R2와 직접
   회귀만 새 focused commit으로 반영한다.
2. amend, rebase, force-push, merge, Ready 전환, branch 삭제를 하지 않는다.
3. 기존 테스트를 삭제·skip·완화하지 않는다.
4. REVIEW-018·019의 기존 반례와 REVIEW-020의 두 반례를 모두 재실행한다.
5. J-01~J-16·H-01~H-14·전체 verify·Python 3.12를 다시 실행한다.
6. 새 HEAD를 보고하면 Lean Root가 새 고정 HEAD에서 Gate H 재검토한다.

이 변경 요청은 구현 PR의 병합이나 종료가 아니다. PR #36은 Draft 상태로 유지한다.
