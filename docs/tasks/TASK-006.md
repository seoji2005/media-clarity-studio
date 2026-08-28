# TASK-006 — ReferenceBundle/v1 및 평가 실행 계약 구체화

## 상태

- **위험 등급:** Gate H — 데이터 구조·파일 형식·재개 계약
- **상태:** **Done — PR #28 merged**
- **계약 기준선:** `main@400622760643d5216c9e86046d3e4c5a3370dcac`
- **구현 기준선:** `main@5a6b25d870514433c579be6858de8c23fbd33dfc` (PR #27 병합 후)
- **구현 브랜치:** `claude/task-006-eval-contracts`
- **1차 Gate H 검토:** `REVIEW-014` (PR #29 `lean-root-review/task-006-gate-h`) — 고정 HEAD `d72325737d1088104a11d05228b84bd47616fee0`, 판정 **변경 요청** (차단 0 · 중대 4 · 경미 1). 반영은 §11.5
- **2차 Gate H 제한 재검토:** `REVIEW-015` (PR #30, 리뷰 commit `d8d1abd82a1ead14b1ae3e0fac58006eff8fc1b8`) — 고정 HEAD `cd94abf0c23c9e9023abbfed1c3999eda9c7efa0`, 판정 **변경 요청** (차단 0 · 중대 2 · 경미 1). 반영은 §11.6
- **3차 Gate H 제한 재검토:** [`REVIEW-016`](../reviews/REVIEW-016.md) (PR #31, 리뷰 commit `9b2406da12825447e3dbde3c44f77397777ae262`) — 고정 HEAD `c35bd2b56272b505749d407986f16f4513a0e81d`, 판정 **변경 요청** (차단 0 · 중대 2 · 경미 1). 반영은 §11.7
- **4차 Gate H 제한 재검토:** [`REVIEW-017`](../reviews/REVIEW-017.md) (PR #32, 리뷰 commit `85e7a74467f26841e68d83bbfb4f6f30c6a49d09`) — 고정 HEAD `1e94cf8aa7ede86974e1553754b960f57941da83`, 판정 **승인** (기술 지적 0건 · 비차단 절차 일탈 1건). 완료 증거는 §11.8
- **병합:** 사람 제품 오너가 PR #28의 고정 HEAD를 승인했고, merge commit `bd00f604565cac09b91b07286437032486933a08`로 일반 merge
- **선행:** [TASK-005](TASK-005.md) Done
- **구현 Owner:** Claude Code 구현 세션
- **검증·리뷰:** Lean Root Orchestrator, 구현 세션과 분리된 고정 HEAD 검토
- **통합:** 사람 제품 오너의 명시적 승인 뒤에만 수행

> 구현 세션은 자기 변경을 승인하지 않았습니다 (`AGENTS.md` R8 / §3.1).
> Lean Root의 고정 HEAD Gate H 승인과 사람 제품 오너의 병합이 완료되어 이 TASK는 `Done`입니다 (§10·§11.8).

## 1. 목표

TASK-005의 평가 하네스 설계를 기계가 거부할 수 있는 버전 고정 계약으로 바꾼다.

완료 시 저장소는 다음을 갖는다.

1. `ReferenceBundle/v1`, 평가 run manifest/report 및 JSONL record용 JSON Schema
2. JSON Schema만으로 표현할 수 없는 교차 문서·시간축·재개 불변식을 검사하는 Python 표준 라이브러리 validator
3. TASK-005 H-01~H-14를 직접 표현한 고정 fixture
4. 단일 검증 진입점 `make verify-task-006`

이 작업은 실제 ASR·번역·지표 계산을 구현하지 않는다.

## 2. 현재 재현 상태

기준선에는 TASK-005의 문서 계약만 있다. `schemas/`, 평가 계약 validator, H-01~H-14 fixture, `verify-task-006`가 없으므로 잘못된 축 혼합·split 누수·resume fingerprint 변경·부분 결과의 최종 결과 위장을 자동으로 중단시킬 수 없다.

## 3. 요구 행동

### 3.1 버전과 파일

JSON Schema는 공식 Draft 2020-12를 사용하고 모든 root schema에 다음을 둔다.

- `"$schema": "https://json-schema.org/draft/2020-12/schema"`
- 안정적인 `$id`
- `schema_version: "1.0.0"`
- 닫힌 객체는 `additionalProperties: false`

다음 파일을 만든다.

- `schemas/common-v1.schema.json`
- `schemas/reference-bundle-v1.schema.json`
- `schemas/eval-run-manifest-v1.schema.json`
- `schemas/eval-report-v1.schema.json`
- `schemas/eval-event-v1.schema.json`
- `schemas/per-source-metric-record-v1.schema.json`
- `schemas/human-review-record-v1.schema.json`

공통 정의는 상대 `$ref`로 재사용한다. JSON Schema 실행 의존성을 추가하지 않는다. schema 자체의 정적 구조와 아래 의미 불변식은 표준 라이브러리 validator와 테스트가 함께 고정한다. 이를 외부 JSON Schema 구현체의 완전한 meta-validation으로 주장하지 않는다.

### 3.2 공통 타입

`common-v1.schema.json`은 최소한 다음을 고정한다.

- `ArtifactRef/v1`: `artifact_id`, `kind`, `uri`, `content_hash`, `byte_size`, `media_type`, `produced_by`, `created_at`, `parent_refs`, `is_estimate`; 선택 `timebase_ref`
- `Timebase/v1`: ID, domain(`source|degraded|output`), origin artifact, seconds 단위, 유리수 rate, 시작 offset, VFR 여부, 선택 frame index
- `TimeMapping/v1`: from/to timebase ID, method, monotonic/invertible, piecewise segment, inserted/dropped span
- `MetricResult/v1`
- 초 단위 시간 구간
- `sha256:<64 lowercase hex>` 형식의 content/fingerprint hash
- 안전한 식별자와 RFC 3339 UTC timestamp

ArtifactRef의 `uri`는 입력 매체 등 외부 URI도 표현할 수 있는 불투명 문자열이다. 단, run 산출물용 상대 경로 필드는 절대 경로와 `..` traversal을 거부한다.

### 3.3 ReferenceBundle/v1

필수 필드:

- `bundle_id`, `schema_version`
- `source_media`, `source_timebase`
- `provenance`, `completeness`, `limitations`
- `speaker_streams` 또는 명시적 빈 배열
- `utterances`, `reference_cues`, `speech_mask`, `language_spans`

선택 필드:

- 시각 reference/mask
- degraded media/timebase
- `TimeMapping`

불변식:

1. 모든 cue는 `reference_axis: source|target`을 갖는다.
2. target cue가 하나라도 있으면 `target_language`가 반드시 정확히 `ko`다.
3. source cue는 target language를 가장하지 않는다.
4. cue·utterance·language span·mask는 존재하는 source/sample/timebase ID만 참조한다.
5. 모든 시간 구간은 finite이고 `end > start >= 0`이다.
6. 비동일 시간축 사이 비교에는 명시적 `TimeMapping`이 필요하다.
7. mapping segment는 단조이며 선언된 invertibility와 모순되지 않는다.
8. 화자 중첩 reference는 표현 가능해야 한다. 단일 stream 가정을 강제하지 않는다.
9. 부분 bundle은 허용하되 누락된 정답은 이후 metric에서 `unsupported`이지 0점이 아니다.
10. `language_spans`가 언어 귀속의 authoritative source다.

### 3.4 EvalRunManifest/v1

다음을 버전 고정한다.

- run ID와 생성 시각
- dataset ID/hash, split, sample/source/speaker ID 집합
- dev/test 분할 증거
- ReferenceBundle ID/hash 집합
- hypothesis ID/hash, `reference_axis`, target일 때 `target_language=ko`
- metric plan: metric ID, axis(`source|target|axisless`), required 여부, 구현 버전, normalization 버전
- config hash
- dataset/reference/hypothesis/metric-plan/config fingerprint
- baseline/candidate의 paired sample ID
- resume 요청 시 이전 run/fingerprint와 완료 shard hash

불변식:

- dev/test 사이 source ID 또는 speaker ID 교집합은 불가하다.
- reference와 hypothesis axis가 다르면 run은 `invalid`다.
- baseline/candidate paired sample 집합이 다르면 paired comparison은 `invalid`다.
- resume 재사용은 모든 fingerprint·버전 및 완료 shard hash가 동일할 때만 허용한다.
- 불일치 resume는 기존 run에 이어 쓰지 않고 오류로 중단한다.

### 3.5 EvalReport/v1 및 record

run status는 정확히 다음이다.

- `planned|invalid|running|completed|partial|failed|aborted`

metric status는 정확히 다음이다.

- `computed|unsupported|insufficient_n|failed`

`MetricResult/v1` 조건:

- `computed`: finite numeric `value` 필수
- `unsupported`: stable `reason` 필수, `value` 금지
- `insufficient_n`: stable `reason`과 `n` 필수, `value` 금지
- `failed`: stable `reason` 필수, `value` 금지

Report는 다음 구조를 보존한다.

- `metrics_by_axis.source`
- `metrics_by_axis.target`
- 별도 `metrics`(axisless)
- 사용 sample, 누락·제외, 실패 진단, artifact reference
- baseline/candidate paired 관찰 결과

source/target를 합친 overall·aggregate score 필드는 허용하지 않는다. U-07·U-18·U-19·U-26·U-27이 미정인 동안 threshold나 promotion 결론을 만들어내지 않는다.

artifact 상태 계약:

- `run_status=completed`일 때만 final `report.json`
- 그 외 상태는 `report.partial.json`이며 final을 가장하지 않는다.
- 이미 계산된 metric과 실패 진단을 함께 보존한다.
- `manifest.json`, `report.partial.json`, `report.json`, `report.md`, `per_source.jsonl`, `events.jsonl`, `human_review.jsonl` 경로를 manifest가 명시한다.
- JSONL record는 각 줄이 독립적으로 schema version, run ID, sequence/sample key를 가진다.

### 3.6 validator와 안정 오류 코드

`src/media_clarity/eval_contracts.py`를 만든다.

- JSON을 읽고 schema가 요구하는 타입·필수 필드·enum·닫힌 객체를 검사한다.
- schema 간 참조와 이 TASK의 교차 문서·시간축 불변식을 검사한다.
- 실패 시 비정상 종료하고 안정 오류 코드를 출력한다.
- fixture runner를 제공한다: `python -m media_clarity.eval_contracts --fixtures tests/fixtures/eval_contracts`
- 입력 파일을 수정하지 않고, 실패한 결과나 진단을 삭제하지 않는다.

최소 오류 코드:

- `E_SCHEMA`
- `E_TARGET_LANGUAGE`
- `E_AXIS_MISMATCH`
- `E_SPLIT_LEAKAGE`
- `E_RESUME_FINGERPRINT`
- `E_PAIRED_SAMPLE_SET`
- `E_FINAL_STATUS`
- `E_METRIC_VALUE_FORBIDDEN`
- `E_TIME_RANGE`
- `E_TIME_MAPPING`

메시지 문구 전체가 아니라 코드와 위반 위치가 테스트 계약이다.

## 4. H-01~H-14 fixture 계약

`tests/fixtures/eval_contracts/h-01.json`부터 `h-14.json`까지 만든다. 각 fixture는 `case_id`, 최소 production document 묶음, 예상 valid/invalid, 예상 오류 코드 또는 핵심 metric status를 가진다.

| ID | 기계 판정 |
|---|---|
| H-01 | source/target 양축은 유효하고 aggregate가 없다 |
| H-02 | source-only reference는 유효하며 target metric은 `unsupported` |
| H-03 | target cue의 언어 누락 또는 non-`ko`는 `E_TARGET_LANGUAGE` |
| H-04 | reference/hypothesis axis 불일치는 `E_AXIS_MISMATCH` |
| H-05 | non-invertible mapping에서 text는 계산 가능, timing은 `unsupported` |
| H-06 | inserted silence가 source/target 양축 silence metric attribution에 나타난다 |
| H-07 | overlap reference와 single-stream hypothesis에서 cpWER는 `unsupported`, coverage는 별도 |
| H-08 | 표본 부족은 `insufficient_n`이며 value가 없다 |
| H-09 | dev/test source 또는 speaker 교집합은 `E_SPLIT_LEAKAGE` |
| H-10 | metric 예외는 report `partial`; 다른 computed metric과 진단 보존 |
| H-11 | 동일 fingerprint·version·shard hash resume은 재사용 가능하며 중복 없음 |
| H-12 | 변경 fingerprint resume은 `E_RESUME_FINGERPRINT` |
| H-13 | untranslated/source-copy target은 guardrail과 human-review sample을 남긴다 |
| H-14 | baseline/candidate sample 불일치는 `E_PAIRED_SAMPLE_SET` |

추가 mutation test는 최소한 다음 잘못된 변경을 잡아야 한다.

- report에 `overall_score` 추가
- unsupported metric에 `value: 0` 추가
- final report에 non-completed run status 사용
- 잘못된 시간 구간·mapping
- 절대 경로 또는 traversal을 run 산출물 경로에 사용

## 5. 수정 가능 범위

- 위 7개 `schemas/*.schema.json`
- `src/media_clarity/eval_contracts.py`
- `tests/test_eval_contracts.py`
- `tests/fixtures/eval_contracts/h-01.json` … `h-14.json`
- `Makefile`: `verify-task-006` 추가
- `docs/ARCHITECTURE.md`: 실제 schema 경로·metric status `failed` 정합성만 최소 수정
- 이 TASK의 상태 및 `STATUS.md` 자기 행·현재 작업·완료 증거

## 6. 범위 밖

- 기존 `synthetic_slice.py` 행동 변경
- ASR·번역·다운로더·실제 metric 알고리즘
- 모델·공급자·API 선택
- 외부 데이터 다운로드·재배포
- norm-v1 규칙, CPS, 표본수, promotion threshold의 미정값 확정
- FFmpeg 동작 변경
- Python package 의존성, 새 framework, CI
- 제안 상태 ADR의 일괄 승인
- 과거 TASK/REVIEW 원문 수정

범위 밖 결함은 현재 변경을 위험하게 만들지 않는 한 기록만 하고 구현하지 않는다.

## 7. Given / When / Then 합격 기준

1. **Given** H-01~H-14 fixture, **When** fixture runner를 실행하면, **Then** 14개 모두 계약된 판정과 오류 코드/status를 낸다.
2. **Given** source/target 양축 report, **When** validation하면, **Then** 축별 metric은 통과하고 aggregate 필드는 거부된다.
3. **Given** target cue, **When** language가 없거나 `ko`가 아니면, **Then** `E_TARGET_LANGUAGE`로 중단한다.
4. **Given** 부분 실행, **When** final artifact를 선언하면, **Then** `E_FINAL_STATUS`로 중단하고 partial 진단은 보존한다.
5. **Given** resume 요청, **When** fingerprint·version·shard hash 하나라도 다르면, **Then** 기존 run 재사용을 거부한다.
6. **Given** 기존 TASK-022 slice, **When** 전체 검증하면, **Then** 기존 unit 및 실제 FFmpeg smoke가 계속 통과한다.

## 8. 필수 검증

```bash
make verify-task-006
make verify
git diff --check
git status --short
```

`make verify-task-006`는 fixture runner, TASK-006 unit/mutation test, 기존 전체 `verify`를 포함하거나 호출해야 한다.

고정 HEAD 리뷰에서 Lean Root는 다음을 직접 확인한다.

- 기준선 대비 diff와 허용 범위
- fixture 14개가 실제 존재하고 기대 실패를 잡는지
- 테스트 삭제·완화, 의존성·비밀정보·생성물 추가가 없는지
- schema와 stdlib validator가 같은 계약을 표현하는지
- partial/final 및 resume 실패가 기존 artifact를 덮어쓰지 않는지
- 기존 FFmpeg smoke 회귀

## 9. 실패·중단·복구

- validation 실패는 입력·기존 artifact를 수정하지 않고 비정상 종료한다.
- partial과 진단은 보존하고 final artifact는 만들지 않는다.
- resume 불일치 시 기존 run 디렉터리에 이어 쓰지 않는다.
- 구현 PR은 단일 기능 branch로 제한한다.
- 롤백은 해당 PR의 일반 revert로 가능해야 하며 기존 TASK-022 산출물 형식은 변하지 않는다.

## 10. 완료 증거

완료 판정에는 다음이 모두 필요하다.

- Claude Code 구현 commit과 허용 범위 diff
- `make verify-task-006`, `make verify`, `git diff --check` 성공 출력
- H-01~H-14 및 mutation test 직접 재현
- 고정 HEAD Gate H 검토 승인
- 사람 제품 오너의 해당 고정 HEAD 명시적 승인
- 병합 뒤 `main` 재검증과 STATUS 정합성

코드를 작성했거나 테스트를 추가했다는 보고만으로 완료하지 않는다.

## 11. 구현 기록 (Claude Code 구현 세션)

**상태: `Implemented — awaiting fixed HEAD review`.** 아래는 구현 세션의 주장이며 검증이 아니다.
판정은 Lean Root가 고정 HEAD에서 직접 재현한다 (`AGENTS.md` R10 / §3.5).

### 11.1 산출물

| 파일 | 내용 |
|---|---|
| `schemas/*.schema.json` (7개) | Draft 2020-12, 안정 `$id`, `schema_version` `1.0.0` 고정, production 객체 `additionalProperties: false`. 공통 정의는 상대 `$ref`로 재사용 |
| `src/media_clarity/eval_contracts.py` | 실제 schema 파일을 읽어 검사하는 부분집합 validator + 교차 문서·시간축·재개 불변식 + fixture runner |
| `tests/test_eval_contracts.py` | 계약 unit·mutation test |
| `tests/fixtures/eval_contracts/h-01.json` … `h-14.json` | H-01~H-14 |
| `Makefile` | `fixtures-task-006` · `test-task-006` · `verify-task-006` |
| `docs/ARCHITECTURE.md` | §2에 실제 schema 경로 표 추가, §7.6 metric status에 `failed` 추가 |

### 11.2 오류 코드

TASK-006 §3.6의 10개를 모두 제공하고, 계약을 기계로 거부하기 위해 다음을 추가했다:
`E_JSON` · `E_SHARD_DUPLICATE` · `E_METRIC_VALUE_REQUIRED` · `E_METRIC_CAPABILITY` ·
`E_AGGREGATE_FORBIDDEN` · `E_ARTIFACT_PATH` · `E_REFERENCE_ID` · `E_SILENCE_ATTRIBUTION` ·
`E_DOCUMENT_LINK`. 메시지 문구가 아니라 코드와 위반 위치가 계약이다.

### 11.3 명시적 한계 (과장하지 않는다)

- **Draft 2020-12 전체 구현이 아니다.** `SUPPORTED_KEYWORDS`에 나열한 부분집합만 검사하고,
  그 밖의 keyword가 schema에 나타나면 데이터 오류가 아니라 **계약 결함**(`SchemaContractError`)으로
  중단한다. 외부 JSON Schema 구현체의 meta-validation을 수행하지 않았다.
- `pattern`은 ECMA-262가 아니라 Python `re`로 해석한다. schema에는 두 문법에서 뜻이 같은
  표현만 썼다.
- **미정값을 채우지 않았다.** U-07·U-18·U-19·U-26·U-27, norm-v1 규칙 내용, threshold,
  모델·공급자·API는 결정하지 않았다. `paired_observation`의 허용 값에 `promote`가 없는 것은
  의도적이다.
- 실제 ASR·번역·지표 계산은 구현하지 않았다 (§1).

### 11.4 실행한 검증

```bash
make verify-task-006     # fixture runner + 계약 test + 기존 전체 verify
make verify              # static + 기존 unit + 실제 FFmpeg smoke
make verify-task-006 PYTHON=python3.12
git diff --check
git status --short
```

### 11.5 REVIEW-014 변경 요청 반영 (2차 커밋)

`REVIEW-014` (PR #29 `lean-root-review/task-006-gate-h`)가 고정 HEAD `d723257…`에서 **변경 요청**으로 지목한
M-01~M-04·R-01을 제한 범위로 반영했다. 리뷰 원문과 PR #29는 수정하지 않았다.

| ID | 반영 위치 |
|---|---|
| **M-01** | `eval_contracts.py`: `_check_bundle_reference_ids()` 신설 — artifact/timebase ID 집합을 만들어 cue·utterance·speech mask·ArtifactRef의 `timebase_ref`, `Timebase.origin_artifact`, degraded media/timebase 연결을 검사. `_check_time_mapping()`에 `from_timebase`/`to_timebase` 멤버십 검사 추가. 코드 `E_REFERENCE_ID` |
| **M-02** | `check_report()`: `completed ↔ final` **양방향** 강제. `_check_required_metrics()` 신설 — completed 실행에서 metric plan의 모든 required `(axis, metric_id)`가 올바른 bucket에 존재하고 `computed`이거나 plan이 `allow_insufficient_n: true`로 사전 허용한 `insufficient_n`이어야 한다. 코드 `E_FINAL_STATUS` · `E_REQUIRED_METRIC`. schema: metric plan에 `allow_insufficient_n` 추가 |
| **M-03** | schema: `resume.previous_metric_implementation_versions`(metric_id key 객체)를 **`previous_metric_versions`(`(axis, metric_id)` entry 배열)** 로 교체. `_check_resume()`: implementation/normalization version을 존재 여부까지 정확히 비교. `check_manifest()`: metric plan의 `(axis, metric_id)` 중복 거부. 코드 `E_RESUME_FINGERPRINT` · `E_METRIC_PLAN_DUPLICATE`. 기존 다섯 fingerprint와 shard ID/hash 검사는 유지 |
| **M-04** | `_check_split_evidence_covers_dataset()`·`_check_paired_comparison()` 신설, `check_report()`에 metric map key ↔ `MetricResult.metric_id` 일치 검사, `check_document_containers()` 신설로 잘못된 container를 조용히 건너뛰지 않고 `E_SCHEMA`로 거부. 코드 `E_DOCUMENT_LINK` · `E_SPLIT_LEAKAGE` · `E_PAIRED_SAMPLE_SET` · `E_METRIC_ID_MISMATCH` · `E_SCHEMA` |
| **R-01** | `common-v1.schema.json`의 `timestamp`에 프로젝트 확장 annotation `x-mcs-semantic: "utc_timestamp"` 추가. `utc_timestamp_error()`가 stdlib `datetime`으로 실제 달력·시각을 검사한다. `Z` 전용 pattern은 유지. 코드 `E_TIMESTAMP` |

**호환 우회 경로를 만들지 않았다.** PR #28은 미병합이므로 M-03의 이전 resume 구조를 함께
지원하지 않고 새 구조로 교체했다.

**직접 영향을 받은 fixture:** H-02·H-04·H-05·H-06은 정답·능력이 없어 unsupported가 되는
지표를 `required: false`로 계획하도록 고쳤다 (EVAL_HARNESS §3.2 — preflight가 unsupported로
계획한다). H-08은 `allow_insufficient_n: true`를 명시했다. H-11·H-12는 새 resume 구조를 쓴다.
**H-01~H-14의 의미는 약화하지 않았다.**

**새 오류 코드 4종:** `E_TIMESTAMP` · `E_REQUIRED_METRIC` · `E_METRIC_PLAN_DUPLICATE` ·
`E_METRIC_ID_MISMATCH`. `events.jsonl`의 `error_code` pattern(`^E_[A-Z_]+$`)과
`_check_record_links()`의 `ERROR_CODES` 대조가 그대로 적용된다.

**추가 한계 (R-01):** RFC 3339가 허용하는 윤초(`:60`)는 stdlib `datetime`이 표현하지 못하므로
거부한다. 이 프로젝트의 timestamp는 윤초를 쓰지 않는다.

### 11.6 REVIEW-015 제한 재검토 반영 (3차 커밋)

`REVIEW-015`가 고정 HEAD `cd94abf…`에서 **변경 요청**으로 지목한 M-01-R1·M-04-R1·R-03-1을
제한 범위로 반영했다. REVIEW-014·015 원문과 PR #29·#30은 수정하지 않았다.

| ID | 반영 위치 |
|---|---|
| **M-01-R1** | `_check_bundle_reference_ids()`에 **역할별 정확 연결** 추가 — `source_media.timebase_ref`는 `source_timebase.timebase_id`와, `degraded_media.timebase_ref`는 `degraded_timebase.timebase_id`와 정확히 같아야 한다. 역할상 필요한 timebase가 없어 연결을 검증할 수 없으면 거부한다. 기존 ID 집합 membership 검사는 유지하고, 알 수 없는 ID는 membership이 이미 보고하므로 역할 검사에서 중복 보고하지 않는다. 코드 `E_REFERENCE_ID` |
| **M-04-R1** | `_check_paired_comparison()`에 **다섯 집합 정확 동일성** 추가 — dataset `sample_ids`, baseline/candidate paired 집합, baseline/candidate 가설 `sample_ids`가 모두 같아야 하며 **dataset의 진부분집합도 거부**한다. 참조된 두 가설에 `sample_ids`가 없으면 거부한다(선택적으로 빠질 수 있는 집합은 paired 비교의 증거가 아니다). 코드 `E_PAIRED_SAMPLE_SET` |
| **R-03-1** | `_check_resume()`이 `previous_metric_versions`의 **실제 배열 index를 보존**한다. 값 불일치는 `.../<index>/implementation_version` 또는 `.../<index>/normalization_version`을, 필드·entry 누락은 실제 존재하는 부모(`.../<index>` 또는 `.../previous_metric_versions`)를 가리킨다. `<axis>/<metric_id>` 합성 pointer를 만들지 않는다. 코드 `E_RESUME_FINGERPRINT`와 결정적 출력 순서는 유지 |

**중복 ID는 schema가 이미 금지한다.** `dataset.sample_ids`, paired 두 집합, 가설 `sample_ids`가
모두 `uniqueItems: true`이므로 semantic 중복 검사를 따로 두지 않았고, 테스트가 그 사실을 고정한다.

**positive를 먼저 고정했다.** M-04-R1은 이미 다른 이유로 invalid인 H-14를 positive base로 쓰지
않고, 유효한 H-01에 baseline/candidate 가설과 paired comparison을 더한 **독립 valid 문서**를
먼저 통과시킨 뒤 조건을 하나씩 mutation한다. M-01-R1도 정상 source/degraded 연결을 먼저 통과시킨다.

**schema 변경 없음.** 이번 반영은 validator와 테스트만 바꾼다. 7개 schema 파일은 blob 무변경이고
fixture도 변경하지 않았다 — H-01~H-14의 의미는 그대로다.

**알려진 중복 방어 (숨기지 않는다).** paired 표본 집합과 가설 `sample_ids`의 직접 비교는
dataset 동일성 검사와 **중복**이다. 두 집합이 모두 dataset과 같으면 서로도 같으므로, 이 줄만
제거해도 탐지는 유지된다. 다만 `.../baseline_sample_ids`에 별도 진단을 남겨 수정 지점을 좁혀
주므로 유지했다.

### 11.7 REVIEW-016 제한 재검토 반영 (4차 커밋)

`REVIEW-016` (PR #31, 리뷰 commit `9b2406da…`)이 고정 HEAD `c35bd2b…`에서 **변경 요청**으로
지목한 M-01-R2·M-04-R2·R-03-R2를 제한 범위로 반영했다. REVIEW-014·015·016 원문과
PR #29·#30·#31, `main`은 수정하지 않았다.

| ID | 반영 위치 |
|---|---|
| **M-01-R2** | `eval_contracts.py`: `_check_definition_identity()` 신설 — (1) `source_timebase.domain`은 `source`, `degraded_timebase.domain`은 `degraded`여야 한다, (2) 두 timebase **정의**의 `timebase_id`는 서로 달라야 한다, (3) 서로 **다른** media 정의가 같은 `artifact_id`를 쓰면 모호하다. `_check_bundle_reference_ids()`에서 호출한다. 코드 `E_REFERENCE_ID` |
| **M-04-R2** | `_check_hypothesis_id_uniqueness()` 신설 — `hypothesis_id` 중복을 **graph 해석 이전에** 각 중복 index마다 보고하고, 모호해진 ID 집합을 반환한다. `check_manifest()`가 이를 먼저 실행하고 `_check_paired_comparison()`에 넘긴다. `setdefault` 기반 "첫 정의 채택"을 제거해 목록 순서가 판정을 바꾸지 못하게 했다. 코드 `E_DOCUMENT_LINK` |
| **R-03-R2** | `SchemaValidator._check_object()`의 `required` 누락 finding이 **없는 leaf** `.../<name>` 대신 실제로 존재하는 **부모 객체**를 가리키고, 누락 필드 이름은 메시지에 담는다. 이로써 `resume.previous_metric_versions/0`의 `implementation_version` 누락을 포함해 모든 필수 필드 누락 위치가 입력에 JSON Pointer로 해석된다. 코드 `E_SCHEMA` |

**정의 ID와 참조 ID를 구분했다.** `ArtifactRef.timebase_ref`나 `Timebase.origin_artifact`가
정의와 같은 ID를 쓰는 것은 정상 연결이며 중복 정의가 아니다. 유일성 검사는 정의 슬롯
(`source_timebase`·`degraded_timebase`·`source_media`·`degraded_media`·`clean_video`)에만
적용한다. `clean_video`의 **역할 규칙은 추가하지 않았다** — REVIEW-016이 범위 밖으로 두었다.

**의도적으로 좁힌 범위.** 같은 `artifact_id`를 쓰는 정의가 **완전히 동일**하면 중복일 뿐
모호하지 않으므로 거부하지 않는다. 테스트가 이 경계를 고정한다.

**schema·fixture 변경 없음.** 이번 반영은 validator와 테스트만 바꾼다. 7개 schema 파일과
H-01~H-14 fixture는 blob 무변경이고 `Makefile`·`docs/ARCHITECTURE.md`·TASK-022 코드도
건드리지 않았다 — H-01~H-14의 의미는 그대로다.

**positive를 먼저 고정했다.** 세 검사 모두 정상 문서(H-06 정상 번들, degraded counterpart가
없는 H-01, 유일한 baseline/candidate paired 문서)가 finding 0으로 통과하는 것을 먼저 확인한
뒤 조건을 하나씩 mutation한다. REVIEW-015의 진부분집합·`sample_ids` 누락·H-14 반례도 다시 실행한다.

**위치 주장의 정확한 범위.** R-03-R2는 `required` 누락 finding이 부모 객체를 가리키도록
고친 것이다. 회귀 테스트는 resume·manifest·dataset·fingerprints·reference bundle·timebase의
필수 필드 누락에서 위치가 해석되는 것을 확인했다. **모든 코드 경로의 모든 finding**을 전수
확인했다는 주장은 하지 않는다 — 확인한 것은 위 경로들이다.

**mutation 감사 (저장소 밖 임시 사본).** 새 검사를 하나씩 무력화해 회귀 테스트가 탐지하는지
확인했다. 13개 mutation 중 **12개 탐지**. 탐지되지 않은 1개는 아래에 그대로 적는다.

**알려진 중복 방어 (숨기지 않는다).** 모호한 `hypothesis_id`를 객체로 해석하지 않는 방어가
두 곳에 있다 — lookup 구성 루프와 역할 루프. 감사 결과 **lookup 구성 쪽만 제거하면 관측
가능한 동작이 바뀌지 않는다**(역할 루프 방어가 먼저 걸린다). 반대로 역할 루프 쪽만 제거하면
"manifest hypotheses에 없는 가설"이라는 **틀린 메시지**가 나오므로 그쪽이 load-bearing이다.
두 방어를 모두 제거하면 회귀 테스트가 탐지한다. lookup 구성 쪽은 이후 다른 소비자가 같은
lookup을 쓰더라도 첫 정의를 조용히 채택하지 못하게 하는 방어로 유지했다.

### 11.8 REVIEW-017 승인과 PR #28 병합

[REVIEW-017](../reviews/REVIEW-017.md)은 고정 HEAD
`1e94cf8aa7ede86974e1553754b960f57941da83`에서 **승인 — Gate H, 기술 지적 0건,
비차단 절차 일탈 1건**으로 판정했다. REVIEW-014·015·016의 변경 요청은 각 이전 고정 HEAD에
대한 역사 기록이며 이 최종 승인으로 덮어쓰지 않는다.

사람 제품 오너가 PR #28과 위 고정 HEAD를 명시적으로 승인했다. Lean Root는 승인 직전에
HEAD·base·Draft 상태·mergeability를 다시 확인하고, Ready 전환 뒤 `expected_head_sha`를
고정한 일반 merge를 수행했다.

| 증거 | 값 |
|---|---|
| 승인 구현 HEAD | `1e94cf8aa7ede86974e1553754b960f57941da83` |
| 승인 구현 tree | `35e2cd6321e4911f4ba9d82b7b55bdd6d10bf504` |
| PR | #28 — merged |
| `main` merge commit | `bd00f604565cac09b91b07286437032486933a08` |
| 승인 HEAD → merge commit 비교 | ahead 1 · behind 0 · 변경 파일 0 |
| Gate H 검증 | H-01~H-14 14/14 · 계약 157 · 전체 165 · Python 3.12 · 실제 FFmpeg smoke PASS |

따라서 승인된 코드·schema·fixture tree가 `main`에 그대로 반영됐고 §10 완료 조건을 충족한다.
이 `Done`은 TASK-006 범위인 평가 계약의 완료를 뜻한다. 실제 ASR·번역·지표 알고리즘,
파일시스템 수준 run writer, 외부 JSON Schema 구현체 호환성은 구현·검증됐다고 주장하지 않는다.
