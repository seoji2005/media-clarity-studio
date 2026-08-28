# REVIEW-021 — TASK-028 Gate H 고정 HEAD 재검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #36 `feat: add TASK-028 artifact store and resumable stage runtime` |
| Gate | H |
| 기준 `main` | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| 이전 검토 HEAD | `45459b0331113ea18319cdf6072e24e64b6c3da4` |
| 고정 재검토 HEAD | `f0c5e86c3a23f8b358464f7117d63c46149b9403` |
| 구현 보고 tree | `c247c973ef98a9260d2605a5c374ccf3458cffa7` |
| 직접 부모 | `45459b0331113ea18319cdf6072e24e64b6c3da4` |
| 직전 리뷰 | REVIEW-020 / PR #39 / review commit `801a804b467ea61378203f96f4680fc3d78996ff` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-29 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**변경 요청 — Gate H. REVIEW-020 직접 지적 2건은 해소, 추가 필수 수정 1건.**

canonical attempt path와 deterministic execution prefix 반례는 기대한 안정 코드·실제 위치·
무변경 결과로 차단됐다. REVIEW-018·019의 아홉 반례도 계속 차단됐고, J-01~J-16,
H-01~H-14, 전체 343 tests, TASK-028 smoke와 실제 FFmpeg smoke가 독립 실행에서 통과했다.

그러나 execution prefix 검사는 stage ID 순서만 확인하고 각 stage state가 **completed
attempt**를 가리키는지 비완료 manifest에서 확인하지 않는다. 실제 failed attempt를
failed manifest의 첫 stage state로 넣은 독립 반례가 schema·semantic finding 없이 수용됐고,
재실행은 stage callable을 실행해 새 attempt를 만든 뒤 기존 manifest를 completed로 덮어썼다.

TASK-028과 REVIEW-020이 정의한 stage list는 단순 stage prefix가 아니라 **completed prefix**다.
runtime이 생성할 수 없는 checkpoint를 조용히 정상화하므로 복구 hard gate를 충족하지 않는다.

## 3. 원격 경계와 범위

- PR #36은 Open / Draft / 미병합, mergeable이다.
- base는 `main`, head는 `claude/task-028-resumable-runtime`이다.
- 고정 HEAD 직전 재확인에서 branch와 `f0c5e86c…`는 ahead 0 / behind 0 / identical이었다.
- 기준 main보다 4커밋 앞, 0커밋 뒤다.
- PR 전체 변경은 30파일 · +7,842 / -471이다.
- REVIEW-020 반영 커밋은 이전 HEAD보다 1커밋 앞이고 4파일 · +536 / -14다.
- 원격 commit status는 없고 구성된 CI도 없다.
- 새 4파일의 격리 트리 blob SHA는 원격 고정 SHA와 일치했다.

| 파일 | blob SHA |
|---|---|
| `STATUS.md` | `56ad42cf7f64059f63c2c34aece26ae5183d0575` |
| `docs/tasks/TASK-028.md` | `b8c508117bcb13f643794f3c7d07f0ad81235ebc` |
| `src/media_clarity/job_runtime.py` | `edfd0b1f34fc73a3f8e9a3638d2aac4a4172d80b` |
| `tests/test_job_runtime.py` | `6be28a57f174f9d01c33fdd52aa226fbc5b2a54a` |

구현 branch, 구현 코드, schema, fixture와 PR 상태는 이 리뷰에서 수정하지 않았다.

## 4. 직접 실행 결과

| 명령 | 결과 |
|---|---|
| `make verify-task-028` | exit 0 — J 16/16, store 36, runtime 137, 전체 343, TASK-028 smoke PASS, FFmpeg smoke PASS |
| `make verify-task-006` | exit 0 — H 14/14, 계약 162, 전체 343, FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 343, FFmpeg smoke PASS |
| `make verify-task-028 PYTHON=python3.12` | exit 0 — J 16/16, 전체 343, smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — H 14/14, 계약 162, 전체 343, smoke PASS |

격리 트리는 Git metadata를 포함하지 않으므로 자체 `git diff --check`는 실행 대상이 아니었다.
대신 원격 네 blob과 local hash의 일치, 후행 공백 없음, 최종 newline을 직접 확인했다.

## 5. REVIEW-020 직접 지적 재검증

| 반례 | 새 HEAD 실제 판정 |
|---|---|
| relocated existing attempt record | `E_CHECKPOINT_INVALID @ .../manifest.json/stages/0/attempt_path`; callable 0회; manifest 불변; canonical 미재생성 |
| `alpha -> beta`에서 downstream `beta`만 남긴 failed manifest | `E_CHECKPOINT_INVALID @ .../stages/0/stage_id`; callable 0회; manifest 불변 |

REVIEW-018·019의 기존 아홉 반례도 동일 production script에서 모두 차단됐다. 따라서
REVIEW-020 M-01-R2-R1·R2의 **직접 반례**는 해소됐다. canonical path 문자열 동일성과
현재 synchronous runtime의 deterministic prefix 결박은 현재 계약에 맞으므로 승인한다.

## 6. 추가 필수 수정

### M-01-R2-R3 — stage 목록이 completed prefix인지 확인하지 않는다

정상 production API로 one-stage job의 callable을 실패시켜 다음 evidence를 만들었다.

- `jobs/job-a/stages/extract/attempts/a0001.json`: schema·semantic이 유효한 `failed` attempt
- `jobs/job-a/manifest.json`: `status=failed`, `stages=[]`

그 뒤 manifest에 schema-valid한 stage state 하나를 추가했다.

- `stage_id=extract`
- `attempt_id=a0001`
- canonical `attempt_path`
- 실제 record와 동일한 cache key/status/reason
- `attempt_status=failed`

현재 `_check_execution_prefix()`는 stage ID `[extract]`만 deterministic order의 prefix와
비교하고, `check_manifest_semantics()`는 `attempt_status=completed`를 completed manifest에서만
요구한다. 실제 결과:

```json
{
  "schema_findings": [],
  "semantic_findings": [],
  "outcome": {
    "calls": 1,
    "new_attempt_id": "a0002",
    "run_status": "completed",
    "manifest_unchanged": false
  }
}
```

failed attempt evidence 자체는 유효하지만 manifest의 `stages`는 `_write_manifest()`가
`outcomes`에서 만드는 **완료된 stage 목록**이다. 실패한 현재 stage는 attempt record에만
남고 manifest stage prefix에는 들어가지 않는다.

필수 수정:

- manifest status와 무관하게 `stages`의 모든 state는 `attempt_status=completed`여야 한다.
- 각 state가 가리키는 실제 record도 `status=completed`여야 한다. 기존 state-record status
  일치 검사는 유지한다.
- failed·interrupted·running attempt를 stage state로 넣은 manifest를
  `E_CHECKPOINT_INVALID @ .../attempt_status`로 거부한다.
- production `run_job()`은 callable 0회, 기존 manifest·attempt byte 불변으로 거부해야 한다.
- 정상 `failed + stages=[]`, `failed + [alpha completed]`, `running + completed prefix`,
  `completed + full completed order`는 계속 허용한다.
- failure evidence는 기존 attempt record에 그대로 보존하며 삭제·정상화하지 않는다.

schema의 `StageState.attempt_status` enum을 좁힐 필요는 없다. 현재 format이 향후 상태 표현을
위해 넓게 유지된다면 semantic validator에서 현재 runtime의 completed-prefix 계약을 강제하면 된다.

## 7. 회귀 보존 요구

- REVIEW-018 다섯, REVIEW-019 네, REVIEW-020 두 직접 반례
- J-01~J-16 정확히 16건
- H-01~H-14 정확히 14건과 TASK-006 계약 162
- 전체 343 tests와 실제 FFmpeg smoke
- canonical attempt path와 deterministic execution prefix
- CAS streaming hash, no-overwrite, dedupe, 손상 거부
- stale running의 선행 interrupted 전이
- failure temp·error code·location 연결
- source identity·seed input·J-11 fingerprint 계약
- downstream invalidation과 독립 branch cache 재사용

재작업은 M-01-R2-R3과 직접 회귀에 한정한다. worker supervision, 멀티프로세스, GC,
실제 ASR·번역 stage, 외부 dependency, CI를 추가하지 않는다.

## 8. 남은 미검증 경계

- Windows 11/NTFS 실제 실행
- hard-link 미지원 filesystem의 실제 동작
- 실제 프로세스 강제 종료와 OS crash durability
- 멀티프로세스/TOCTOU 경합
- JSON Schema Draft 2020-12 전체 구현과 외부 meta-validator

이번 결함은 Linux 단일 프로세스 기본 경로에서 직접 재현되므로 위 환경 한계로 설명되지 않는다.

## 9. 다음 허용 행동

1. Claude Code가 기존 `claude/task-028-resumable-runtime` branch에 M-01-R2-R3과 직접 회귀만
   새 focused commit으로 반영한다.
2. amend, rebase, force-push, merge, Ready 전환, branch 삭제를 하지 않는다.
3. 기존 테스트를 삭제·skip·완화하지 않는다.
4. REVIEW-018~020의 기존 반례와 REVIEW-021의 새 반례를 모두 재실행한다.
5. J-01~J-16·H-01~H-14·전체 verify·Python 3.12를 다시 실행한다.
6. 새 HEAD를 보고하면 Lean Root가 새 고정 HEAD에서 Gate H 재검토한다.

이 변경 요청은 구현 PR의 병합이나 종료가 아니다. PR #36은 Draft 상태로 유지한다.
