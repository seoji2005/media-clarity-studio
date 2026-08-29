# REVIEW-022 — TASK-028 Gate H 최종 고정 HEAD 재검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #36 `feat: add TASK-028 artifact store and resumable stage runtime` |
| Gate | H |
| 기준 `main` | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| 이전 검토 HEAD | `f0c5e86c3a23f8b358464f7117d63c46149b9403` |
| 고정 재검토 HEAD | `9cfaf4dad35b313ae2a2357f5257c2897a7b01a3` |
| 구현 보고 tree | `0770fa074544b4bfefa3b374789fccbc32316f05` |
| 직접 부모 | `f0c5e86c3a23f8b358464f7117d63c46149b9403` |
| 직전 리뷰 | REVIEW-021 / PR #40 / review commit `c35f5b7201697469508fa49264d76a5542cc0d2b` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-29 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**승인 — Gate H 고정 HEAD. 병합 승인은 별도 제품 오너 결정이다.**

REVIEW-021의 completed-prefix 결함은 기대한 안정 코드·실제 위치·무변경 결과로 해소됐다.
REVIEW-018~020의 이전 11개 직접 반례도 계속 차단됐고, J-01~J-16, H-01~H-14,
전체 355 tests, TASK-028 smoke와 실제 FFmpeg smoke가 원격 고정 blob 기반 독립 실행에서
통과했다.

새 구현은 manifest stage state와 실제 record의 status 일치를 먼저 검사하고, 실제 record가
`completed`인지 별도로 검사한다. 따라서 state만 `completed`라고 위조하거나 state와 record를
함께 non-completed로 만드는 두 경로가 각각 독립적으로 차단된다. state에 별도 completed 검사를
중복 추가하지 않은 판단은 계약을 약화하지 않으면서 mutation shadowing을 줄이므로 승인한다.

추가 hard-gate 결함이나 범위 이탈은 발견되지 않았다.

## 3. 원격 경계와 범위

- PR #36은 Open / Draft / 미병합, mergeable이다.
- base는 `main`, head는 `claude/task-028-resumable-runtime`이다.
- 고정 HEAD 직전 재확인에서 branch와 `9cfaf4da…`는 ahead 0 / behind 0 / identical이었다.
- 기준 main보다 5커밋 앞, 0커밋 뒤다.
- PR 전체 변경은 30파일 · +8,281 / -471이다.
- REVIEW-021 반영 커밋은 이전 HEAD보다 1커밋 앞이고 4파일 · +453 / -14다.
- 원격 commit status는 없고 구성된 CI도 없다.
- 새 4파일의 격리 트리 blob SHA는 원격 고정 SHA와 일치했다.

| 파일 | blob SHA |
|---|---|
| `STATUS.md` | `34332e5c5fa67bfae5ddff4b268070c2faf77484` |
| `docs/tasks/TASK-028.md` | `422b73a23616711404df89057a8a4e31ae8206f8` |
| `src/media_clarity/job_runtime.py` | `80845479874ba847fbcd42f91b358d336a4e3584` |
| `tests/test_job_runtime.py` | `1f4fa0dfbf2c057e97f9b581560b47fe6edd1f5c` |

구현 branch, 구현 코드, schema, fixture와 PR 상태는 이 리뷰에서 수정하지 않았다.

## 4. 직접 실행 결과

| 명령 | 결과 |
|---|---|
| `make verify-task-028` | exit 0 — J 16/16, store 36, runtime 149, 전체 355, TASK-028 smoke PASS, FFmpeg smoke PASS |
| `make verify-task-006` | exit 0 — H 14/14, 계약 162, 전체 355, FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 355, FFmpeg smoke PASS |
| `make verify-task-028 PYTHON=python3.12` | exit 0 — J 16/16, 전체 355, smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — H 14/14, 계약 162, 전체 355, smoke PASS |

격리 트리는 Git metadata를 포함하지 않으므로 자체 `git diff --check`는 실행 대상이 아니었다.
대신 원격 네 blob과 local hash의 일치, 후행 공백 없음과 최종 newline을 직접 확인했다.

## 5. REVIEW-021 직접 지적 재검증

이전 HEAD에서 schema·semantic finding 없이 통과하던 동일 production script를 새 HEAD에
그대로 실행했다.

| 반례 | 새 HEAD 실제 판정 |
|---|---|
| failed attempt를 failed manifest stage로 기록 | `E_CHECKPOINT_INVALID @ .../stages/0/attempt_status`; callable 0회 |
| interrupted attempt를 stage로 기록 | 같은 코드·위치; callable 0회 |
| running attempt를 stage로 기록 | 같은 코드·위치; callable 0회 |
| state만 completed라고 주장하고 실제 record는 failed | state↔record 불일치와 record completed 규칙으로 거부 |

failed 반례의 schema finding은 0건이지만 semantic finding이 정확히 발생했다. 거부 뒤 manifest와
attempt는 byte 불변이고 새 attempt가 생성되지 않으며 failure evidence도 그대로 보존됐다.

정상 `failed + stages=[]`, `failed + [alpha completed]`, `running + completed prefix`,
`completed + full completed order`는 semantic finding 없이 유지됐고, 정상 prefix 재개에서
alpha는 hit, beta만 실행됐다.

## 6. 이전 리뷰 회귀

독립 production script에서 다음을 다시 확인했다.

- REVIEW-018: 완료 evidence 모순, stale running, source identity path, failure evidence,
  seed artifact 누락 차단
- REVIEW-019: record identity, manifest 완결성, failed error evidence, non-string seed key 차단
- REVIEW-020: relocated attempt path와 downstream-only manifest 차단
- REVIEW-021: failed·interrupted·running stage state 차단

총 14개 변형이 모두 기대한 안정 코드와 실제 위치로 차단됐다. 전체 fixture·unit·smoke 회귀도
약화되지 않았다.

## 7. 설계 판단

다음 판단을 승인한다.

1. **completed 판정을 실제 record에 결박한다.** 기존 state↔record 일치 검사와 조합되어
   state와 record 모두 completed가 강제된다.
2. **completed manifest 전용 검사를 일반 규칙으로 교체한다.** 더 넓은 모든 manifest status에
   적용되므로 제거된 좁은 검사는 기능 약화가 아니다.
3. **`StageState.attempt_status` enum을 유지한다.** format을 좁히지 않고 현재 synchronous
   runtime의 completed-prefix 제약을 semantic validator에서 강제한다.
4. **진실한 중간 진행 기록은 보존한다.** 앞 stage가 실제 완료된 뒤 뒤 stage에서 거부되면
   manifest에 기록된 앞 stage 진행이 남는 것은 손상 evidence 덮어쓰기가 아니다. REVIEW-021
   반례처럼 실행 시작 전에 거부되는 경우의 byte 불변 계약과 구분한다.

## 8. 남은 미검증 경계와 비차단 위험

- Windows 11/NTFS 실제 실행
- hard-link 미지원 filesystem의 실제 동작
- 실제 프로세스 강제 종료와 OS crash durability
- 멀티프로세스/TOCTOU 경합
- JSON Schema Draft 2020-12 전체 구현과 외부 meta-validator

이 경계는 TASK-028 범위와 문서에 명시돼 있으며 Linux 단일 프로세스 Gate H 승인을 막지 않는다.
Windows 검증과 실제 crash durability는 후속 확장 전 별도 TASK에서 다뤄야 한다.

## 9. 롤백과 다음 허용 행동

- PR #36은 아직 Draft·미병합이므로 현재 롤백은 branch/PR을 병합하지 않는 것으로 충분하다.
- 이 승인은 고정 HEAD `9cfaf4dad35b313ae2a2357f5257c2897a7b01a3`에만 유효하다.
- 구현 branch HEAD가 바뀌면 승인도 무효이며 다시 검토한다.
- 다음 허용 행동은 사람 제품 오너의 PR #36 고정 HEAD 병합 승인이다.
- 제품 오너 승인 전 Ready 전환·병합·branch 삭제를 하지 않는다.

이 판정은 코드 리뷰 승인이지 PR 병합이나 TASK-028 `Done` 전이가 아니다.
