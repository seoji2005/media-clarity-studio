# REVIEW-014 — TASK-006 Gate H 고정 HEAD 검토

## 1. 대상과 판정

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 대상 PR | #28 `claude/task-006-eval-contracts` → `main` |
| 기준 base | `5a6b25d870514433c579be6858de8c23fbd33dfc` |
| 고정 HEAD | `d72325737d1088104a11d05228b84bd47616fee0` |
| 대상 tree | `195b745ed04c7dd62c92bca8d1aed7b55fa31c9c` |
| 위험 등급 | Gate H |
| Reviewer | Lean Root Orchestrator — 구현 세션과 분리 |
| **판정** | **변경 요청** |
| 차단/중대/경미 | **차단 0 · 중대 4 · 경미 1** |

이 판정은 병합이 아니다. 사람 제품 오너가 승인하더라도 아래 중대 지적을 새 HEAD에서 제한 재검토하기 전에는 통합하지 않는다.

## 2. 직접 확인한 것

작성자의 완료 보고를 증거로 사용하지 않았다. GitHub의 고정 SHA에서 27개 변경 파일을 직접 가져와 격리된 검증 트리에서 실행했다.

| 검사 | 직접 결과 |
|---|---|
| base/head | 1커밋, behind 0, 고정 HEAD 일치 |
| 실제 diff | 27파일 · +8,453 / −14 |
| 허용 범위 | 7 schema, validator, test, fixture 14, Makefile, ARCHITECTURE, TASK-006, STATUS — 범위 안 |
| `make verify-task-006` | exit 0 — fixture 14/14, TASK test 69, 전체 77, FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 77, FFmpeg smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — 동일 |
| 변경 파일 후행 공백 | 0 |
| CI status | 없음 |
| 기존 TASK-022 직접 회귀 | 실제 FFmpeg smoke PASS, source 및 기존 output/staging 보존 확인 |

통과 결과는 유효하지만 아래 반례를 잡지 못한다.

## 3. 변경 요청

### M-01 — ReferenceBundle의 시간축·artifact 참조 무결성이 빠져 있다

**계약:** TASK-006 §3.3 불변식 4는 cue·utterance·language span·mask가 존재하는 timebase ID만 참조해야 한다. `Timebase.origin_artifact`도 실제 bundle artifact를 가리켜야 한다.

**관측:** H-01에 다음 mutation을 각각 넣어도 `valid=True, codes=()`다.

- `reference_cues[0].timebase_ref = "tb-ghost"`
- `speaker_streams[0].utterances[0].timebase_ref = "tb-ghost"`
- `speech_mask.timebase_ref = "tb-ghost"`
- `source_timebase.origin_artifact = "artifact-ghost"`

`check_reference_bundle()`은 speaker ID만 교차 확인하고 timebase/artifact ID는 확인하지 않는다.

**요구:** source/degraded media와 timebase의 ID 집합을 만든 뒤 모든 참조를 검증하라. mapping의 from/to도 실제 timebase를 가리키게 하고 각 반례의 회귀 테스트를 추가하라.

### M-02 — completed/final 상태와 required metric 완료 조건이 양방향으로 강제되지 않는다

**계약:** EVAL_HARNESS §4에서 completed는 모든 required metric이 computed 또는 명시적으로 허용된 insufficient_n일 때뿐이다. TASK-006 §3.5에서 completed만 final이고 그 외는 partial이다.

**관측:** H-01에서 다음 세 경우가 전부 `valid=True, codes=()`다.

1. required source CER 결과를 report에서 삭제
2. required source CER를 `failed`로 바꾸고 report를 completed/final 유지
3. run_status는 completed인데 document_kind를 partial로 변경

현재 `check_report()`은 final + non-completed 한 방향만 거부하고, metric plan의 required entry가 report에 모두 존재하는지와 terminal status를 검사하지 않는다.

**요구:**

- `completed ↔ final`을 양방향으로 강제하라.
- metric plan의 모든 required `(axis, metric_id)`가 올바른 bucket에 정확히 한 번 존재하도록 하라.
- required metric의 failed·예상 밖 unsupported는 completed를 거부하도록 하라.
- insufficient_n을 completed에서 허용하려면 metric plan에 사전 허용 여부를 명시적으로 모델링하고 그 값만 사용하라.
- 삭제·failed·completed-as-partial mutation 회귀 테스트를 추가하라.

### M-03 — resume이 normalization version과 축별 metric version을 고정하지 않는다

**계약:** TASK-005 §4와 TASK-006 §3.4는 resume에 fingerprint뿐 아니라 metric·normalizer version과 완료 shard hash의 동일성을 요구한다.

**관측:** H-11에서 source CER의 `normalization_version`만 변경하고 기존 fingerprint 문자열을 그대로 두어도 `valid=True, codes=()`다. 또한 `_check_resume()`은 version을 `metric_id` 하나로 `setdefault`하여 같은 metric이 source/target에 다른 version을 갖는 경우 뒤 축을 잃는다.

**요구:** 이전 metric plan version 계약을 `(axis, metric_id)` 단위로 표현하고 implementation/normalization version의 존재·부재와 값을 모두 비교하라. 기존 다섯 fingerprint 비교는 그대로 유지한다. normalizer 변경 및 source/target version 차이 회귀 테스트를 추가하라.

### M-04 — manifest/report 문서 그래프의 핵심 연결이 자기 일관되지 않아도 통과한다

**계약:** split evidence와 paired comparison은 실제 dataset·hypothesis sample을 증명해야 하며 MetricResult의 ID는 저장 위치와 일치해야 한다. 제공된 문서의 구조 오류를 조용히 건너뛰면 안 된다.

**관측:** 다음 mutation이 각각 `valid=True, codes=()`다.

- split evidence를 dataset과 무관한 source/speaker ID로 교체
- H-14의 baseline/candidate ID를 서로 같은 임의 sample로 바꾸되 dataset·두 hypothesis sample은 그대로 둠
- `metrics_by_axis.source.cer.metric_id = "wer"`
- `reference_bundles = {}` 또는 `event_records = {}`처럼 LIST_DOCUMENTS를 잘못된 객체로 변경

**요구:**

- 현재 split의 dataset source/speaker 집합이 해당 split evidence에 포함되고 반대 split에는 없음을 검사하라.
- paired baseline/candidate hypothesis ID가 실제 role과 일치하고, paired sample 집합이 각 hypothesis 및 dataset sample 집합과 일치하게 하라.
- metric map key와 내부 `metric_id`를 일치시켜라.
- 알려진 document key가 잘못된 container type이면 `E_SCHEMA`로 거부하고 조용히 skip하지 마라.
- 각 반례의 회귀 테스트를 추가하라.

### R-01 — RFC 3339 UTC라고 선언한 timestamp가 달력·시각 유효성을 검사하지 않는다

`2026-99-99T99:99:99Z`가 pattern을 통과해 valid가 된다. 외부 meta-validator를 추가하라는 뜻이 아니다. stdlib로 실제 UTC timestamp 유효성을 확인하고 회귀 테스트를 추가하라.

## 4. 제한 재검토 범위

새 HEAD에서는 다음만 본다.

1. M-01~M-04와 R-01의 직접 수정
2. 위 반례를 고정한 회귀 테스트
3. 기존 H-01~H-14·69개 계약 테스트·전체 verify·FFmpeg smoke 직접 회귀
4. schema/validator/fixture/문서의 직접 정합성
5. 범위 이탈·테스트 약화·새 dependency 없음

이미 통과한 다른 TASK-006 영역을 이유 없이 전면 재검토하지 않는다. 추가 독립 결함은 수정이 현재 merge를 실제로 위험하게 만드는 직접 회귀일 때만 보고한다.

## 5. 복구 경계

이 리뷰는 코드 branch를 수정하지 않는다. Claude Code가 PR #28에 별도 후속 커밋으로 반영한다. 실패 시 후속 커밋만 일반 revert할 수 있어야 하며 기존 TASK-022 media slice와 artifact를 수정하지 않는다.
