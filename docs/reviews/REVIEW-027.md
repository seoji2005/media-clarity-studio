# REVIEW-027 — TASK-029 final fixed-HEAD Gate H review

- 대상 PR: #45
- 대상 브랜치: `claude/task-029-subtitle-spine-contracts`
- 최종 고정 HEAD: `4b0d2cd041d7a133640355dd0b96874ef4329074`
- tree: `edd2d799c194d1a4775d4d734b9d63b13f989a68`
- 직접 부모: `0fcb22b8689eb4ac7f0174348af6de9a4ed0ef7c`
- reviewed base / 기준 main: `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`
- 검토일: 2026-08-31
- Author / Reviewer: Claude Code / fresh Lean Root fixed-HEAD Reviewer
- 판정: **승인 — 기술 차단 0건**
- 병합/Ready 전환: **승인하지 않음** — 사람 제품 오너의 exact PR/HEAD/base 승인이 별도로 필요

## 1. 검토 수명주기

REVIEW-026의 고정 HEAD와 판정은 그대로 보존한다. 이후 제한 재검토에서 사용한 고정 HEAD와
그 시점의 판정은 다음과 같다.

| 고정 HEAD | tree | 판정 | 당시 미해결 |
|---|---|---|---|
| `cb3bcbc0d26a340f41e619398e4293c2c9dda069` | `0e7b78e15298cbf945ce824a38358930d640b9c0` | 변경 요청 | R-01 non-vacuous public-boundary evidence, R-02 public raw-JSON boundary, R-03 manifest 재분류, D-04 LID·`document_refs` 문서 계약 |
| `2dc0716820f827d8023e48f0f63652e816f8faf9` | `fd26bb638ab4d5c093ddf7e3bab0ae1ff0c17628` | 중간 작성자 checkpoint | 오너 결정 option 3과 공개 문서 반영; R-01~R-03 최종 재검토 전 |
| `c0dec2e45e29e44abc5f8332a3a46ab05d1c2ef3` | `2fc06f707d1810db7447976380f0b7a66b150f6f` | 변경 요청 | R-02C 프로세스 전역 정수 정책, R-03C 첫 candidate 조기 성공·manifest 원자성 |
| `0fcb22b8689eb4ac7f0174348af6de9a4ed0ef7c` | `55ebaf1a137444b6b479ee3f70ddc6580bbd6e5a` | 변경 요청 | R-01C 공개 callable의 표준 `__wrapped__` / `inspect.unwrap()` 우회 |
| `4b0d2cd041d7a133640355dd0b96874ef4329074` | `edd2d799c194d1a4775d4d734b9d63b13f989a68` | **승인** | 기술 차단 0건 |

각 판정은 해당 고정 HEAD의 역사 기록이다. 뒤의 승인으로 앞선 변경 요청을 삭제하거나
그 당시의 결함이 없었다고 다시 쓰지 않는다.

## 2. 최종 고정 상태와 범위

최종 확인에서 PR #45는 open, draft, unmerged였고 base와 head가 위 값에 일치했다.
`main`은 reviewed base와 동일했으며 PR #45는 ahead 9 / behind 0이었다.

직접 부모 `0fcb22b…` 대비 변경은 다음 5개 파일, +273/-6뿐이다.

- `src/media_clarity/subtitle_contracts.py`
- `scripts/verify_task_029.py`
- `tests/test_subtitle_contracts.py`
- `docs/tasks/TASK-029.md`
- `STATUS.md`

`defense-manifest.json`과 다음 금지 경로는 직접 부모 대비 diff 0이다.

- `AGENTS.md`, `PLAN.md`, `docs/DECISIONS.md`
- `docs/EVALS.md`, `docs/ARCHITECTURE.md`
- `schemas/`, `tests/fixtures/`
- `src/media_clarity/schema_core.py`
- `src/media_clarity/artifact_store.py`
- `src/media_clarity/job_runtime.py`

`schema_core.py`, artifact/job runtime, common/job schema는 reviewed base 대비도 diff 0이다.
신규 dependency, model, network egress, CI, error code는 없고 기존 test 삭제·skip·완화도
발견하지 못했다. `git diff --check`와 detached review worktree는 clean이었다.

## 3. R-01C 직접 재현과 해소

이전 고정 HEAD `0fcb22b…`에서 공개 validator는 정상 호출 시 location을 접었지만,
`check_transcript.__wrapped__`와 `inspect.unwrap(check_transcript)`가 비식별화 전 구현을
표준 attribute로 노출했다.

`PATIENT_SECRET`을 location으로 준 시간 범위 반례에서:

- 정상 공개 호출: `E_TIME_RANGE @ ""`
- `__wrapped__` / `inspect.unwrap()` 우회:
  `E_TIME_RANGE @ PATIENT_SECRET/streams/0/segments/0/end_seconds`

최종 HEAD의 `_public_boundary()`는 `update_wrapper()`로 이름·docstring·annotation을
보존한 뒤 `wrapper.__wrapped__`를 제거하고 `__signature__`를 명시적으로 보존한다.
8개 공개 `check_*` 함수를 독립 확인한 결과:

- `hasattr(fn, "__wrapped__") == false`
- `inspect.unwrap(fn) is fn`
- `__name__`, `__doc__`, `inspect.signature(fn)` 보존
- 민감 반례의 code/location은 `E_TIME_RANGE @ ""`
- location과 message에 sentinel 없음

`run_boundary_probes()`는 호출 결과를 보기 전에 공개 함수 객체의 callable
`__wrapped__`와 `inspect.unwrap()`을 검사한다. PB-01~PB-08은 각각 실제 finding을
한 건 이상 만들고 exact `(code, location)`과 일치했다.

다음 두 source mutant를 독립 실행했다.

| mutant | 반례 | 결과 |
|---|---|---|
| VM-145 | 공개 경계 자체를 제거 | PB-01~PB-08 전부 kill |
| VM-149 | `del wrapper.__wrapped__` 제거 | PB-01~PB-08 전부 kill |

VM-149 상태의 저장소 밖 사본은 `--check-only` exit 1이었고 여덟 probe가 모두
“`__wrapped__`로 비식별화 전 구현이 노출된다”로 실패했다. 따라서 최종 감사 증거는
R-01C에 대해 vacuous하지 않다.

closure cell 등 문서화되지 않은 private introspection을 새 보안 경계로 확대하지 않는다.
이 판정은 공개 callable에 표준 attribute로 노출되던 우회만 대상으로 한다.

## 4. R-02C·R-03C 보존

직접 부모에서 승인 전 재작업한 다음 동작은 최종 delta에서 변경되지 않았다.

- `_profile_integer`는 `Decimal` 경유로 계약 정수를 만들며 프로세스 전역
  `sys.set_int_max_str_digits()` / getter를 호출하지 않는다.
- strict loader hook 합성은 duplicate key, NaN/Infinity, lossy decimal 거부를 유지한다.
- schema defense 분류는 전체 candidate를 평가하고 독립 witness를 우선한다.
- manifest write는 staging 뒤 `os.replace()`로 원자 교체한다.
- SD-14/15/16과 MF-09/10/11을 유지한다.

`IntegerLimitIsolationTests`, `StrictLoaderCompositionTests`,
`ManifestWriterClassificationTests`의 관련 17개 test를 직접 실행해 17/17 통과했다.

## 5. 독립 검증 결과

검토 환경은 Linux, Python 3.12.13, FFmpeg 6.1.1이다.

| 검증 | 독립 결과 |
|---|---|
| R-01C introspection focused | 7/7 |
| public-boundary 관련 focused | 12/12 |
| R-02C/R-03C focused | 17/17 |
| `verify_task_029.py --check-only` | exit 0 |
| `make fixtures-task-029 PYTHON=python3.12` | 171/171 |
| `make audit-task-029 PYTHON=python3.12` | exit 0; 14개 보고 분모 전부 100%, SKIP 0 |
| `make static test PYTHON=python3.12` | compileall OK; 전체 496/496 |
| `make smoke PYTHON=python3.12` | TASK-022 FFmpeg smoke PASS |
| `git diff --check`, `git status --short` | clean |

TASK-029 감사의 최종 분모는 다음과 같다.

| 분모 | 결과 |
|---|---|
| fixture | 171/171 |
| input mutants | 237/237 |
| leak scan | 408/408 |
| depth probes | 4/4 |
| raw JSON probes | 21/21 |
| public boundary probes | 8/8 |
| validator defense sites | 145/145 |
| schema defense killable / equivalent | 291/291 · 2/2 |
| defense manifest | 8/8 |
| defense drift self-tests | 16/16 |
| audit self-tests | 4/4 |
| schema mutants | 22/22 |
| validator code mutants | 144/144 |

GitHub에는 이 HEAD의 commit status와 workflow run이 각각 0건이다. CI 통과로 해석하지 않고
미구성 상태로 기록한다.

## 6. 문서·운영 정합성과 잔여 경계

PR #45 본문은 최종 판정 전에 현재 고정 HEAD, tree, parent, 9커밋, 최신 검증 수치,
이 REVIEW-027 경로를 맨 위 정본 절로 갱신했다. 이전 `cb3bcbc…` 작성자 보고는
“역사 기록” 아래 원문 보존했고 현재 상태로 읽지 않는다는 supersession banner를 붙였다.

REVIEW-023~026 원문과 이 문서는 review-only PR #46에 보존한다. PR #46은 PR #45보다 먼저
병합하지 않는다. PR #45 병합 뒤 최신 `main`에서 review-only diff인지 다시 확인해 통합한다.

미검증/비보증 경계:

- Windows 11/NTFS 실제 실행
- 실제 ASR·번역·diarization·forced alignment adapter
- 문서화되지 않은 closure-cell 등 private introspection
- 공식 LID 정확도와 chrF2 — TASK-029에서는 계속 unsupported

이 항목은 현재 TASK 범위의 기술 차단이 아니며, 후속 platform/model/evaluation TASK의
증거 없이는 지원됐다고 주장하지 않는다.

## 7. 최종 판정과 다음 행동

최종 고정 HEAD `4b0d2cd041d7a133640355dd0b96874ef4329074`에서 REVIEW-026 이후의
R-01~R-03, D-04, `document_refs`, R-02C, R-03C, R-01C 변경 요청은 모두 해소됐다.
직접 반례, focused regression, TASK 감사, 전체 회귀, FFmpeg smoke에서 새 기술 차단을
발견하지 못했다.

따라서 Gate H 판정은 **승인**이다.

이 승인은 병합이 아니다. 다음 허용 행동은 사람 제품 오너에게 아래 exact pair의 merge
승인을 요청하는 것이다.

- PR: #45
- HEAD: `4b0d2cd041d7a133640355dd0b96874ef4329074`
- reviewed base: `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`

승인 전에는 Ready 전환·merge·rebase·amend·force-push를 하지 않는다. HEAD 또는 base가
움직이면 이 판정으로 병합하지 않고 영향을 제한 재검토한다. PR #47은 PR #45 결론 전까지
untouched Draft로 유지한다.
