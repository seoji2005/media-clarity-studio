# REVIEW-017 — TASK-006 Gate H 네 번째 고정 HEAD 재검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #28 `feat: add TASK-006 evaluation contract schemas and validator` |
| Gate | H |
| 기준 `main` | `5a6b25d870514433c579be6858de8c23fbd33dfc` |
| 고정 HEAD | `1e94cf8aa7ede86974e1553754b960f57941da83` |
| tree | `35e2cd6321e4911f4ba9d82b7b55bdd6d10bf504` |
| 직접 부모 | `c35bd2b56272b505749d407986f16f4513a0e81d` |
| 직전 리뷰 | REVIEW-016 / PR #31 / review commit `9b2406da12825447e3dbde3c44f77397777ae262` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-28 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch의 push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**승인 — Gate H. 기술 지적 0건. 비차단 절차 일탈 1건.**

REVIEW-016의 M-01-R2·M-04-R2·R-03-R2는 구현과 독립 반례에서 모두 해소됐다.
정의 역할·ID 무결성, hypothesis graph 유일성, required 필드 누락 위치가 계약대로
기계적으로 거부된다. 기존 REVIEW-015 회귀와 전체 TASK-006·TASK-022 검증도 통과했다.

알려진 중복 방어는 관측 동작을 오염시키지 않고 문서에 범위가 공개되어 있어 제거를
요구하지 않는다.

이 판정은 병합이 아니다. PR #28의 Ready 전환과 병합에는 사람 제품 오너가
`PR #28@1e94cf8…`을 별도로 명시적으로 승인해야 한다.

## 3. 원격 경계와 범위

### 3.1 Git·PR

- PR #28은 Open / Draft / 미병합이다.
- base는 `main@5a6b25d…`, head는
  `claude/task-006-eval-contracts@1e94cf8…`이다.
- PR 전체는 `main`보다 4커밋 앞, 0커밋 뒤다.
- PR 전체 변경은 27파일 · +10,572 / -15다.
- 이번 커밋은 `c35bd2b…`보다 1커밋 앞, 0커밋 뒤이며 merge base가 정확히
  `c35bd2b…`다.
- 이번 커밋의 변경은 다음 4파일뿐이다.

| 파일 | 추가 | 삭제 |
|---|---:|---:|
| `STATUS.md` | 6 | 6 |
| `docs/tasks/TASK-006.md` | 44 | 0 |
| `src/media_clarity/eval_contracts.py` | 147 | 6 |
| `tests/test_eval_contracts.py` | 335 | 0 |

schema 7개, H-01~H-14 fixture 14개, `Makefile`, `docs/ARCHITECTURE.md`,
TASK-022 코드·테스트·smoke는 이번 커밋에서 변경되지 않았다.

### 3.2 원격 blob 고정

격리 검증 트리의 네 변경 파일은 원격 고정 SHA의 blob과 일치했다.

| 파일 | blob SHA |
|---|---|
| `STATUS.md` | `7e2a46c7934c3f4a1ab07c0685042cf4f5c93d78` |
| `docs/tasks/TASK-006.md` | `03943df45bd925bffc4f108297fd8fa254007c11` |
| `src/media_clarity/eval_contracts.py` | `f85036390a35566df5cde25612d79e386bb6085b` |
| `tests/test_eval_contracts.py` | `7d3832816f6cdf083e3c230ba949ebeb0a17a85c` |

GitHub Actions workflow run은 없었다. 아래 실행 결과는 외부 CI가 아니라 Lean Root가
원격 blob과 일치시킨 격리 트리에서 직접 얻은 증거다.

## 4. 직접 실행 결과

| 명령 | 결과 |
|---|---|
| `make verify-task-006` | exit 0 — H fixture 14/14, 계약 157, 전체 165, 실제 FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 165, 실제 FFmpeg smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — H fixture 14/14, 계약 157, 전체 165, 실제 FFmpeg smoke PASS |
| whitespace 검사 | 변경 4파일 후행 공백 0, 최종 newline 존재 |
| skip 검사 | `unittest.skip`, `skipTest`, `expectedFailure` 추가 0 |

TASK-006 test method 수는 136개에서 157개로 21개 늘었고 삭제·skip·완화는 발견되지 않았다.

실제 FFmpeg smoke는 다음 복구 경계를 계속 확인했다.

- source byte 불변
- canonical/raw 동일성
- 기존 output·staging 보존
- unset guard의 filesystem 무변경
- raw 위반과 FFmpeg 실패의 export 전 기록

## 5. REVIEW-016 지적별 판정

### M-01-R2 — 승인

`_check_definition_identity()`가 정의 슬롯과 참조 슬롯을 분리해 다음을 검사한다.

1. `source_timebase.domain == "source"`
2. `degraded_timebase.domain == "degraded"`
3. source/degraded timebase 정의의 ID 비동일성
4. 서로 다른 media 정의가 같은 artifact ID를 쓰는 충돌

독립 mutation 결과:

| 반례 | 실제 판정 |
|---|---|
| source/degraded domain swap | `E_REFERENCE_ID` 2건, 실제 domain 노드 |
| 두 timebase를 `tb-shared`로 collapse | `E_REFERENCE_ID` @ degraded timebase ID |
| 서로 다른 media를 `artifact-shared`로 collapse | `E_REFERENCE_ID` @ degraded media artifact ID |
| TimeMapping from/to swap 회귀 | `E_TIME_MAPPING` 2건, 실제 from/to 노드 |

정상 정의 ID를 `ArtifactRef.timebase_ref`와 `Timebase.origin_artifact`가 참조하는
구성은 중복 정의로 오판하지 않는다. 동일한 artifact 정의를 alias로 재사용하는 positive와
degraded counterpart가 없는 positive도 유지된다. `clean_video`에는 계약 밖 역할 규칙을
추가하지 않았다.

정의 검사 전체를 런타임에서 무력화한 독립 실패 주입에서는 domain 위반 입력이 통과했다.
따라서 새 회귀 테스트는 실제 load-bearing 검사를 대상으로 한다.

### M-04-R2 — 승인

`_check_hypothesis_id_uniqueness()`가 paired graph 해석 전에 manifest 전체의
`hypothesis_id`를 검사한다. 뒤 중복 index마다 `E_DOCUMENT_LINK`를 내고,
모호해진 ID는 paired 객체로 해석하지 않는다.

독립 mutation 결과:

| 반례 | 실제 판정 |
|---|---|
| 내용이 다른 baseline ID 중복 | `E_DOCUMENT_LINK` @ `hypotheses/4/hypothesis_id` |
| candidate ID 중복 | `E_DOCUMENT_LINK` @ `hypotheses/4/hypothesis_id` |
| 중복 정의 순서 반전 | `E_DOCUMENT_LINK` @ 실제 뒤 중복 index |
| 같은 ID 세 번 정의 | 두 뒤 index 모두 `E_DOCUMENT_LINK` |

유일성 검사를 런타임에서 무력화하면 내용이 다른 duplicate baseline이 finding 없이
통과했다. 따라서 유일성 회귀도 실제 load-bearing이다.

lookup 구성 루프와 role 해석 루프의 모호 ID 방어 중 하나는 현재 관측 결과에 중복이다.
그러나 첫 정의를 조용히 채택하지 않도록 lookup 자체를 안전하게 유지하는 방어이고,
TASK-006 §11.7과 PR 본문에 중복성이 공개되어 있다. 기능 회귀나 유지보수 차단으로 보지 않는다.

### R-03-R2 — 승인

`SchemaValidator._check_object()`는 required 필드가 없을 때 존재하지 않는 leaf 대신
실제 부모 객체를 location으로 사용하고 누락 필드 이름을 메시지에 기록한다.

독립 반례에서 H-11의
`resume.previous_metric_versions[0].implementation_version`을 제거한 결과:

- 코드: `E_SCHEMA`
- location: `eval_run_manifest/resume/previous_metric_versions/0`
- location 해석값: 실제 entry 객체
- 메시지: `implementation_version` 포함

값 불일치의 실제 배열 index, normalization 필드 부재의 부모 위치, 결정적 정렬도 유지된다.

## 6. REVIEW-015 직접 회귀

다음 기존 반례는 새 HEAD에서도 계속 거부됐다.

- source/degraded `timebase_ref` swap
- dataset의 진부분집합인 paired 다섯 집합
- paired baseline hypothesis의 `sample_ids` 누락
- H-14 baseline/candidate sample 집합 불일치
- TimeMapping 방향 swap
- resume implementation/normalization version 불일치

H-01~H-14는 정확히 14건 발견·14건 실행·14건 성공했다. 계약 실패 fixture는 기존
안정 코드 H-03 `E_TARGET_LANGUAGE`, H-04 `E_AXIS_MISMATCH`,
H-09 `E_SPLIT_LEAKAGE`, H-12 `E_RESUME_FINGERPRINT`,
H-14 `E_PAIRED_SAMPLE_SET`을 유지했다.

## 7. 문서·PR 정합성

- PR #28의 고정 HEAD, tree, 부모, 4커밋, 전체 diff 통계가 원격과 일치한다.
- REVIEW-014·015·016의 변경 요청을 각 고정 HEAD의 역사로 보존했다.
- `TASK-006`과 `STATUS.md`는 `Done`이 아니라
  `Implemented — awaiting fixed HEAD rereview`를 유지한다.
- Draft 2020-12 부분집합, Python `re`, 윤초 거부, filesystem writer 미구현,
  기본 Python 3.11/검증 Python 3.12 경계를 과장하지 않는다.
- 검증한 location 범위를 특정 경로로 좁혀 기록해 전수 검증으로 주장하지 않는다.

## 8. 비차단 절차 일탈

구현 세션은 첫 로컬 커밋에 금지된 생성 모델 trailer가 들어가 push 전에
`git commit --amend`로 제거됐다고 보고했다.

이 pre-push 로컬 상태는 원격에서 독립 재현할 수 없으므로 **자기 보고 사실**로 구분한다.
명시된 “amend 금지”를 문자 그대로 위반했으며 다음 작업에서 반복하면 안 된다.

최종 원격 상태는 다음과 같다.

- `1e94cf8…`의 부모는 정확히 `c35bd2b…` 하나다.
- 구현 branch push는 원격 관점에서 fast-forward다.
- rebase·force-push 또는 공개 이력 rewrite 증거는 없다.
- 최종 commit message에는 생성 모델 이름·버전과 `Co-Authored-By` trailer가 없다.
- 기존 3커밋 SHA는 보존됐다.

영구 저장소 오염이나 검증 결과 변경이 없어 기술 승인을 막거나 추가 history 조작을
요구하지 않는다. 이 절에 기록하여 R7 인계 누락을 보완한다.

## 9. 롤백·남은 경계

이번 구현은 `c35bd2b…` 위의 단일 커밋이므로 필요하면 해당 커밋의 일반 revert로
되돌릴 수 있다. schema·fixture·TASK-022 artifact 형식은 변하지 않았다.

확인하지 않은 경계:

- Draft 2020-12 전체 호환성과 외부 meta-validator
- ECMA-262와 Python `re`의 일반적 동등성
- RFC 3339 윤초 `:60`
- 실제 filesystem writer의 partial/final·resume 동작
- Python 3.11.15·3.12.3 외 OS/Python patch

이는 TASK-006이 명시한 기존 범위 밖 또는 공개된 한계이며 이번 고정 HEAD 승인을 막지 않는다.

## 10. 다음 허용 행동

1. 제품 오너가 PR #28과 고정 HEAD `1e94cf8…`의 병합 여부를 판단한다.
2. 제품 오너가 명시적으로 승인한 경우에만 Lean Root가 승인 HEAD와 base를 재확인한다.
3. HEAD가 그대로일 때만 PR #28을 Ready로 전환하고 `expected_head_sha`를 고정한 일반
   merge를 수행한다.
4. 병합 뒤 최신 `main`, PR 종료 상태, 승인된 blob을 재검증한다.
5. TASK-006의 `Done`·STATUS 전이는 병합 증거와 함께 별도 비코드 정합성 단계에서 수행한다.

승인 전에 PR #28 HEAD가 바뀌면 이 REVIEW-017 승인은 효력을 잃고 새 고정 HEAD 재검토가 필요하다.
