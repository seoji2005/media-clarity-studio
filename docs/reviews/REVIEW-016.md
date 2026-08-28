# REVIEW-016 — TASK-006 Gate H 세 번째 고정 HEAD 재검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #28 `feat: add TASK-006 evaluation contract schemas and validator` |
| Gate | H |
| 기준 `main` | `5a6b25d870514433c579be6858de8c23fbd33dfc` |
| 고정 HEAD | `c35bd2b56272b505749d407986f16f4513a0e81d` |
| tree | `5968b00c2527c47b54c49482df7abbcc1d82db32` |
| 직접 부모 | `cd94abf0c23c9e9023abbfed1c3999eda9c7efa0` |
| 직전 리뷰 | REVIEW-015 / PR #30 / 고정 HEAD `cd94abf0c23c9e9023abbfed1c3999eda9c7efa0` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-28 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch의 push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**변경 요청 — 차단 0 · 중대 2 · 경미 1.**

REVIEW-015가 요구한 역할별 `timebase_ref` 연결, paired 다섯 집합 동일성,
resume finding 배열 index는 구현되어 직접 반례가 모두 거부됐다. 그러나 같은 계약 경계에
역할 도메인과 ID 정의의 유일성, hypothesis ID 유일성이 아직 빠져 있다. 이 상태에서는
서로 다른 시간축이나 가설 정의가 같은 ID로 합쳐져도 validator가 통과하므로 Gate H의
데이터 무결성 hard gate를 만족하지 않는다.

`c35bd2b…`는 Ready 또는 병합 승인 대상이 아니다.

## 3. 직접 확인한 사실

### 3.1 Git·PR 경계

- PR #28은 Open / Draft / 미병합이다.
- base는 `main@5a6b25d…`, head는
  `claude/task-006-eval-contracts@c35bd2b…`이다.
- `main` 대비 3커밋 앞, 0커밋 뒤이며 merge base는 현재 `main`이다.
- REVIEW-015 반영 커밋은 직접 부모 `cd94abf…` 위의 단일 fast-forward 커밋이다.
- 이번 검토에서 구현 branch, `main`, PR #28, 이전 REVIEW 문서는 수정하지 않았다.

### 3.2 독립 실행

고정 SHA의 격리된 검증 트리에서 다음을 직접 실행했다.

| 명령 | 결과 |
|---|---|
| `make verify-task-006` | exit 0 — fixture 14/14, 계약 136, 전체 144, 실제 FFmpeg smoke PASS |
| `make verify` | exit 0 — 144 tests, 실제 FFmpeg smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — 동일 |
| `git diff --check` | 출력 없음 |

GitHub status check와 workflow run 증거는 구성되어 있지 않았다. 위 결과는 외부 CI가 아니라
Lean Root의 고정 HEAD 독립 실행 결과다.

### 3.3 REVIEW-015 회귀

다음 반례는 새 HEAD에서 기대 코드와 실제 입력에 해석되는 JSON Pointer로 거부됐다.

- source/degraded `timebase_ref` swap
- dataset의 진부분집합인 paired 다섯 집합
- 참조된 baseline hypothesis의 `sample_ids` 누락
- normalization version만 바뀐 resume

기존 H-01~H-14 의미, TASK-022 테스트, 실제 FFmpeg smoke도 유지됐다.

## 4. 발견 사항

### M-01-R2 — timebase 역할과 ID 정의의 유일성이 완결되지 않음

**심각도: 중대**

#### 재현 A — 역할 domain swap

유효한 H-06 계열 bundle에서 media의 `timebase_ref`는 올바른 역할 ID를 유지한 채

- `source_timebase.domain = "degraded"`
- `degraded_timebase.domain = "source"`

로 바꾸면 finding 없이 통과한다.

현재 역할 연결 검사는 media의 참조 ID와 명명된 timebase의 ID가 같은지만 확인한다.
`source_timebase`가 실제 source domain인지, `degraded_timebase`가 실제 degraded
domain인지는 확인하지 않는다.

#### 재현 B — source/degraded timebase ID collapse

`source_timebase.timebase_id`와 `degraded_timebase.timebase_id`를 모두
`"tb-shared"`로 바꾸고 bundle 내부 참조와 mapping의 from/to도 같은 값으로 맞추면
finding 없이 통과한다.

이 입력은 source와 degraded 시간축을 구분할 수 없지만 단순 membership과 equality를
모두 만족한다.

#### 재현 C — 충돌하는 artifact ID 정의

서로 다른 URI·hash 등 정의를 가진 `source_media`와 `degraded_media`의
`artifact_id`를 모두 `"artifact-shared"`로 바꾸고 두 timebase의
`origin_artifact`도 같은 ID로 맞추면 finding 없이 통과한다.

ID lookup 관점에서는 한 ID에 충돌하는 두 정의가 생긴다. 현재 집합 기반 검사는 이를
유일한 정의로 오인한다.

#### 위험

- source/degraded 시간축이 조용히 합쳐질 수 있다.
- 동일 artifact ID가 서로 다른 content 정의를 가리킬 수 있다.
- 후속 metric, resume, provenance가 어떤 정의를 사용했는지 재현할 수 없다.

이는 스키마 취향 문제가 아니라 M-01의 참조 무결성과 데이터 손상 방지 hard gate다.

#### 요구 수정

1. `source_timebase.domain`은 정확히 `"source"`,
   `degraded_timebase.domain`은 정확히 `"degraded"`여야 한다.
2. source/degraded timebase 정의의 ID는 서로 달라야 한다.
3. bundle 안에서 같은 timebase ID 또는 artifact ID가 여러 정의에 쓰이면 충돌을
   검출한다. 최소한 같은 ID인데 정의가 다른 경우는 반드시 거부한다.
4. finding은 안정 오류 코드와 실제 입력의 ID/domain 노드 또는 존재하는 부모를 가리킨다.
5. degraded counterpart가 없는 유효 positive, 선택적 `timebase_ref` 부재,
   REVIEW-015 swap 거부를 유지한다.
6. 계약이 역할을 정하지 않은 `clean_video.timebase_ref`에는 새 역할 추측을 넣지 않는다.

기존 `E_REFERENCE_ID`를 재사용해도 되지만 오류 의미와 위치가 결정적이어야 한다.

### M-04-R2 — 중복 hypothesis_id가 paired 연결에서 조용히 선택됨

**심각도: 중대**

#### 재현

유효한 paired manifest에 baseline hypothesis와 같은
`hypothesis_id = "hyp-baseline"`을 가진 두 번째 hypothesis를 추가하되
`content_hash`와 `sample_ids`를 다르게 만들면 finding 없이 통과한다.

`_check_paired_comparison()`은 hypothesis 목록을 dict로 만들 때 `setdefault`를
사용한다. 따라서 같은 ID의 뒤 정의는 조용히 무시되고 paired reference는 어느 객체를
가리키는지 모호해진다.

#### 위험

- baseline/candidate 결과가 같은 ID의 다른 hypothesis 정의와 연결될 수 있다.
- paired sample 검사가 임의의 첫 객체만 검사한다.
- manifest 순서 변경만으로 검증 대상이 바뀔 수 있어 재현성과 결정성이 깨진다.

#### 요구 수정

1. manifest의 `hypothesis_id`는 전체 목록에서 유일해야 한다.
2. uniqueness를 확인한 뒤에만 paired baseline/candidate ID를 객체로 해석한다.
3. 충돌하는 뒤 entry는
   `eval_run_manifest/hypotheses/<index>/hypothesis_id`처럼 실제 노드에
   결정적으로 보고한다.
4. `setdefault`로 중복을 조용히 선택하는 경로를 제거한다.
5. 서로 다른 유일 ID를 가진 정상 baseline/candidate positive와 기존 다섯 집합
   동일성 회귀를 유지한다.

기존 `E_DOCUMENT_LINK`를 재사용해도 된다. 새 오류 코드를 만들면 TASK·event contract·
테스트를 함께 맞춰야 한다.

### R-03-R2 — 누락된 required version의 finding이 실제 노드/부모를 가리키지 않음

**심각도: 경미**

#### 재현

H-11 계열 manifest의
`resume.previous_metric_versions[0].implementation_version`을 삭제하면 입력은
`E_SCHEMA`로 거부되지만 finding location은 존재하지 않는 leaf인

`eval_run_manifest/resume/previous_metric_versions/0/implementation_version`

를 가리킨다.

validator는 schema 오류가 있으면 semantic resume 검사를 건너뛰므로 REVIEW-015에서
약속한 “필드 누락은 실제 entry/부모” 규칙이 이 경로에는 적용되지 않는다.

#### 위험

기능적으로 잘못된 resume은 거부된다. 다만 사용자와 도구가 location을 그대로
JSON Pointer로 해석하면 수정 대상 노드를 찾지 못하고, PR/TASK의 진단 계약과 불일치한다.

#### 요구 수정

- 이 required version 누락은 실제 entry
  `eval_run_manifest/resume/previous_metric_versions/0` 또는 존재하는 부모를
  가리키게 한다.
- resolver 테스트가 모든 finding location을 production input에서 실제로 해석하거나,
  계약이 허용한 누락 부모임을 확인하게 한다.
- 광범위한 schema validator 리팩터링은 하지 않는다. resume version 경계에 필요한
  최소 변경으로 해결한다.
- 문서의 “모든 location” 주장이 실제 계약보다 넓다면 구현과 문서를 같은 의미로
  좁혀 정합시킨다. 단, REVIEW-015가 요구한 missing version의 부모 위치는 유지한다.

## 5. 승인된 수정 범위

Claude Code 후속 커밋은 다음만 다룬다.

- M-01-R2의 timebase domain·timebase/artifact ID 정의 유일성
- M-04-R2의 hypothesis ID 유일성 및 모호한 lookup 제거
- R-03-R2의 missing required version 위치
- 위 세 항목의 직접 positive·negative·pointer·결정성 회귀
- 사실과 달라지는 TASK-006·STATUS·PR #28 본문의 최소 정합성 갱신

다음은 범위 밖이다.

- 새 dependency, framework, CI, 외부 데이터
- Draft 2020-12 전체 구현
- 실제 metric/ASR/번역 알고리즘
- `clean_video`의 미정 역할 규칙
- unrelated schema·fixture·Makefile·TASK-022 리팩터링
- 이전 REVIEW 문서 수정 또는 구현 branch history rewrite

## 6. 재검토 수용 기준

다음 고정 HEAD 재검토에서 모두 충족해야 한다.

1. 위 세 독립 반례가 기대 코드와 실제 노드/부모 위치로 거부된다.
2. 정상 source/degraded 역할, degraded 없는 구성, optional ref positive가 통과한다.
3. 유일한 baseline/candidate hypothesis positive가 통과하고 중복 ID는 순서와 무관하게
   결정적으로 거부된다.
4. REVIEW-015의 네 핵심 반례가 계속 거부된다.
5. H-01~H-14가 14/14 실행·성공한다.
6. 기존 테스트 삭제·skip·완화 없이 `make verify-task-006`, `make verify`,
   Python 3.12 검증, 실제 FFmpeg smoke가 모두 통과한다.
7. 새 검사를 저장소 밖 임시 사본에서 무력화했을 때 해당 회귀 테스트가 탐지한다.
   논리적으로 중복인 검사는 중복 근거를 숨기지 않는다.
8. 구현은 기존 PR #28에 새 focused fast-forward 커밋으로 추가되고 Draft를 유지한다.
9. Ready 전환·병합·rebase·amend·force-push·branch 삭제를 하지 않는다.

## 7. 복구와 다음 단계

이 REVIEW 문서는 고정 HEAD `c35bd2b…`를 부모로 하는 별도 review branch에만 보존한다.
구현 branch와 이전 리뷰 기록은 변경하지 않는다.

Claude Code가 제한 수정 후 새 HEAD·tree·직접 부모·검증 결과를 보고하면 Lean Root가
그 SHA를 다시 고정하여 Gate H를 독립 검토한다. 그 판정과 별개로 Ready 전환·병합에는
제품 오너의 별도 명시적 승인이 필요하다.
