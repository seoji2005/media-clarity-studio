# ARCHITECTURE.md — 아키텍처

모듈 경계와 인터페이스 계약. **구현이 아니라 계약의 정의입니다.**

마지막 갱신: 2026-08-22 (TASK-025 — U-31 한국어 대상 언어 계약 반영)
상태: **제안됨 (Proposed)** — 경계 원칙과 구체 기술 모두 아직 승인 전

> 이 문서의 코드 블록은 전부 **계약 스케치(pseudo-contract)** 입니다.
> 실행 가능한 코드가 아니며 특정 언어를 강제하지 않습니다.
> 필드 이름은 제안이며, 구현 시 조정될 수 있습니다.
>
> **상태 표기:** 각 절 제목 옆의 라벨은 [`DECISIONS.md`](DECISIONS.md)의 상태와 일치합니다.
> 라벨이 없는 절은 **제안됨**으로 간주합니다.

---

## 1. 설계 원칙

| # | 원칙 | 상태 | 구체적 의미 |
|---|---|---|---|
| A1 | **도메인 산출물 독립, 공통 기반 공유** | 제안됨 (ADR-0025) | 자막 도메인 산출물과 시각 도메인 산출물은 서로를 입력으로 쓰지 않는다. 반면 **횡단 기반(cross-cutting infrastructure)은 공유한다** |
| A2 | **계약 우선** | 제안됨 | 모듈은 데이터 계약으로만 만난다. 내부 구현을 서로 모른다 |
| A3 | **모델 교체 가능** | 제안됨 | 어떤 ASR·재구성 모델도 어댑터 뒤에 있다. 코어가 모델 API에 의존하지 않는다 |
| A4 | **단계별 산출물 보존** | 제안됨 | 중간 결과를 디스크에 남긴다. 재실행·디버깅·평가의 전제 |
| A5 | **재현성 등급 명시** | 제안됨 | 비트 단위 결정성 / 허용오차 내 반복성 / 출처 재현성을 **구분**한다 (§6) |
| A6 | **평가는 일급 시민** | 제안됨 | `eval`은 부가 도구가 아니라 모듈이다 |
| A7 | **UI는 껍데기** | 제안됨 | 모든 기능은 UI 없이 실행 가능해야 한다 |
| A8 | **안전 게이트 우선** | 제안됨 (ADR-0022) | 재구성은 `ReconstructionPolicy` 통과 후에만 수행된다 (§5) |

### A1의 정확한 의미 (오해 방지)

**독립인 것 — 도메인 산출물과 도메인 로직**

- 자막 파이프라인은 `ReconstructionResult`를 읽지 않습니다.
- 시각 파이프라인은 `SubtitleDocument`나 `Transcript`를 읽지 않습니다.
- 한쪽이 실패해도 다른 쪽은 끝까지 진행됩니다.

**공유하는 것 — 횡단 기반 (공유가 정상이며, 중복 구현이 오히려 결함)**

| 공유 자산 | 내용 |
|---|---|
| `ingest` | 미디어 조사·디코딩·해시 |
| `storage` | 프로젝트/작업/산출물 배치, manifest |
| `orchestrator` | 작업 그래프, 캐시, 재개, 자원 |
| 공통 계약 | `ArtifactRef`, `Timebase`, `TimeMapping`, `RegionMask` (§2) |
| `ReferenceBundle` | 두 도메인의 정답을 담는 단일 컨테이너 (§3) |
| `eval` 하네스 | 실행·리포트·통계 처리 골격 (지표 계산기는 도메인별) |

> **A1은 "따로 만들어라"가 아니라 "도메인 산출물이 서로를 오염시키지 않게 하라"입니다.**
> 기반을 중복 구현하면 timebase가 갈라지고 평가가 비교 불가능해집니다.

### A3이 중요한 이유

지금 우리는 어떤 모델이 최선인지 모릅니다 (U-22).
모델을 어댑터 뒤에 두면 나중에 측정 결과로 교체할 수 있습니다.
코어에 특정 모델 API를 박아 넣으면 그 선택이 영구적 부채가 됩니다.

---

## 2. 공통 계약 (Cross-cutting Contracts) — **버전 관리 대상**

두 도메인이 함께 쓰는 기본 자료형입니다. **모든 공통 계약은 `schema_version`을 가집니다.**

**기계 검증 형태는 저장소의 실제 JSON Schema 파일입니다** (TASK-006). 아래 의사코드와
schema 파일이 다르면 **schema 파일이 정답**입니다.

| 계약 | schema 파일 |
|---|---|
| `ArtifactRef/v1` · `Timebase/v1` · `TimeMapping/v1` · `MetricResult/v1` | [`schemas/common-v1.schema.json`](../schemas/common-v1.schema.json) |
| `ReferenceBundle/v1` | [`schemas/reference-bundle-v1.schema.json`](../schemas/reference-bundle-v1.schema.json) |
| `EvalRunManifest/v1` | [`schemas/eval-run-manifest-v1.schema.json`](../schemas/eval-run-manifest-v1.schema.json) |
| `EvalReport/v1` | [`schemas/eval-report-v1.schema.json`](../schemas/eval-report-v1.schema.json) |
| `EvalEvent/v1` (`events.jsonl`) | [`schemas/eval-event-v1.schema.json`](../schemas/eval-event-v1.schema.json) |
| `PerSourceMetricRecord/v1` (`per_source.jsonl`) | [`schemas/per-source-metric-record-v1.schema.json`](../schemas/per-source-metric-record-v1.schema.json) |
| `HumanReviewRecord/v1` (`human_review.jsonl`) | [`schemas/human-review-record-v1.schema.json`](../schemas/human-review-record-v1.schema.json) |
| `Job/v1` (`jobs/<job_id>/manifest.json`, attempt record) | [`schemas/job-v1.schema.json`](../schemas/job-v1.schema.json) |

> `RegionMask/v1`(§2.4)은 Phase 2 시각 도메인 계약이며 TASK-006 범위에 포함되지 않았습니다.
> schema 파일은 아직 없습니다.

> schema 부분집합 검사기는 `src/media_clarity/schema_core.py` 하나입니다 (TASK-028).
> `eval_contracts`와 `job_runtime`이 같은 구현을 쓰며, keyword 해석을 복제하지 않습니다.
> Draft 2020-12 전체 구현이 아니라 `SUPPORTED_KEYWORDS` 부분집합만 검사합니다.

### 2.1 `ArtifactRef/v1` — 산출물 참조

파일 경로를 직접 주고받지 않습니다. 모든 산출물은 `ArtifactRef`로 참조됩니다.

```
ArtifactRef/v1:
  schema_version   : "1.0.0"
  artifact_id      : 문자열                 # 프로젝트 내 고유
  kind             : "audio" | "video" | "frames" | "text" | "mask"
                     | "subtitle" | "report" | "reference_bundle" | "blob"
  uri              : 문자열                 # storage 상대 경로
  content_hash     : 문자열                 # 무결성·캐시 키
  byte_size        : 정수
  media_type       : 문자열                 # 예: "audio/wav", "application/json"
  timebase_ref?    : Timebase 참조          # 시간축이 있는 산출물만
  produced_by      : { stage_id, job_id, adapter_id?, adapter_version? }
  created_at       : 타임스탬프
  parent_refs[]    : artifact_id            # 계보(lineage) 추적
  is_estimate      : 불리언                 # 재구성 계열은 항상 true (§5)
```

**규칙**

- `content_hash`가 같으면 같은 산출물로 취급합니다 (캐시 적중).
- `parent_refs`로 **계보 추적**이 가능해야 합니다. 어떤 입력에서 나왔는지 역추적할 수 없는 산출물은 평가에 쓰지 않습니다.
- 형식이 바뀌면 `schema_version`의 major를 올립니다. **하위 호환이 깨진 산출물끼리 비교하지 않습니다.**

### 2.2 `Timebase/v1` — 정준 시간축 (Canonical Timeline)

시간 관련 버그의 대부분은 "누구의 시간인가"가 정의되지 않아서 생깁니다.

```
Timebase/v1:
  schema_version   : "1.0.0"
  timebase_id      : 문자열
  domain           : "source" | "degraded" | "output"
  origin_artifact  : artifact_id            # 이 시간축의 기준 산출물
  unit             : "seconds"              # 정준 단위는 항상 초
  rate_num         : 정수                   # 프레임/샘플 격자 (예: 30000)
  rate_den         : 정수                   #                 (예: 1001)
  start_offset_seconds : 실수               # 컨테이너 시작 오프셋
  is_variable_rate : 불리언                 # VFR 여부
  frame_index_base : 0 | 1
```

**정준 규칙**

1. **모든 시간 값은 초(seconds) 실수로 표현합니다.** 프레임 번호·샘플 인덱스는 보조 정보입니다.
2. 시간이 붙은 모든 계약은 **어떤 `timebase_id`를 쓰는지 명시**합니다.
3. `domain`이 다른 시간 값을 **직접 비교하지 않습니다.** 반드시 `TimeMapping`을 거칩니다.
4. 가변 프레임레이트(VFR) 입력은 `is_variable_rate: true`로 표시하고, 프레임 번호 기반 연산을 금지합니다.

### 2.3 `TimeMapping/v1` — 시간축 변환

**무음 삽입, 프레임 드롭/중복 같은 시간 변경 열화는 원본과 열화본의 시간축을 어긋나게 합니다.**
이 경우 열화 산출물은 **반드시** `TimeMapping`을 함께 반환합니다.

```
TimeMapping/v1:
  schema_version   : "1.0.0"
  from_timebase    : timebase_id            # 보통 source
  to_timebase      : timebase_id            # 보통 degraded
  method           : "identity" | "piecewise_linear" | "step" | "explicit_pairs"
  is_monotonic     : 불리언
  is_invertible    : 불리언
  segments[]       : { from_start, from_end, to_start, to_end, scale }
  inserted_spans[] : { to_start, to_end, kind: "silence"|"duplicate"|"other" }
                     # 원본에 대응이 없는 구간
  dropped_spans[]  : { from_start, from_end }
                     # 열화본에 대응이 없는 구간
```

**필수 규칙**

- `method: "identity"`가 아닌 열화는 **`TimeMapping` 없이 평가에 투입할 수 없습니다.**
  매핑이 없으면 타임스탬프 지표가 조용히 틀립니다.
- `inserted_spans`는 **정답이 존재하지 않는 구간**입니다. 지표 계산에서 어떻게 다룰지는
  [`EVALS.md`](EVALS.md) §4에서 지표별로 정의합니다.
- `inserted_spans[].to_start`/`to_end`는 **`to_timebase`의 반개구간 `[to_start, to_end)`**입니다.
  `from_timebase`(source) 쪽에는 애초에 대응이 없으므로, 이 구간에 속하는지 판정은
  **`to_timebase`에서 먼저** 합니다 ([`EVALS.md`](EVALS.md) §4.0.1 알고리즘 A, REVIEW-003 §3.1).
- 역변환이 불가능하면(`is_invertible: false`) 그 열화 조건에서 계산할 수 없는 지표를
  **"미지원"으로 명시 보고**합니다. 근사값으로 채우지 않습니다.

### 2.4 `RegionMask/v1` — 공간 영역 (이동 지원)

열화 영역은 정지해 있지 않습니다. 인물이 움직이면 모자이크도 따라 움직입니다.

```
RegionMask/v1:
  schema_version   : "1.0.0"
  timebase_ref     : timebase_id
  representation   : "rle" | "polygon" | "bitmap_ref" | "bbox"
  is_static        : 불리언
  keyframes[]      :
    time_seconds   : 실수
    shape          : 표현 형식에 따른 데이터
    confidence?    : 0..1
  interpolation    : "none" | "nearest" | "linear"   # keyframe 사이 처리
  coverage_ratio   : 0..1                            # 프레임 면적 대비 평균 비율
```

**규칙**

- `is_static: false`면 `keyframes`가 2개 이상이어야 합니다.
- `interpolation: "none"`이면 keyframe이 없는 시각의 마스크는 **정의되지 않음**입니다.
  정의되지 않은 구간을 "영역 없음"으로 간주하지 않습니다.
- 마스크 면적(`coverage_ratio`)은 지표 정규화에 필요합니다 ([`EVALS.md`](EVALS.md) §5).

---

## 3. `ReferenceBundle/v1` — 정답 계약 *(제안됨)*

**평가에 필요한 모든 정답을 담는 단일 컨테이너입니다.**
지금까지 "정답"이 문서마다 다른 뜻으로 쓰였고, 그래서 어떤 지표는 계산 가능 여부조차 불명확했습니다.
`ReferenceBundle`은 그 모호함을 없애기 위한 계약입니다.

```
ReferenceBundle/v1:
  schema_version     : "1.0.0"
  bundle_id          : 문자열
  source_media       : ArtifactRef            # 깨끗한 원본 미디어
  source_timebase    : Timebase               # 이 번들의 정준 시간축 (domain: "source")
  provenance         : { origin, license_id, consent_status, curated_by, curated_at }
  completeness       : { 아래 각 절의 제공 여부 플래그 }

  # ── 음성/자막 도메인 ─────────────────────────────
  # 정답 축이 둘입니다 (§3.0.1). 두 축을 같은 것으로 취급하지 않습니다.
  speaker_streams[]  :                        # [원문 축] 화자별 독립 스트림 (겹침 표현의 핵심)
    speaker_id       : 문자열
    utterances[]     : { start_seconds, end_seconds, text, language,
                         tokens[]? : { text, start_seconds, end_seconds } }
    is_complete      : 불리언                 # 이 화자 전사가 완전한가

  reference_cues[]   :                        # 자막 형태의 정답 (스타일 규칙 포함)
    cue_id, start_seconds, end_seconds, lines[], language, speaker_id?,
    reference_axis   : "source" | "target"    # ★ 어느 정답 축인가 (§3.0.1). 생략 불가

  target_language?   : BCP-47                 # 번역 축(`reference_axis: "target"`)의 대상 언어.
                                              # 현재 제품 프로필은 **한국어 `ko`** (U-31 해소).
                                              # target-axis 정답이 있으면 `ko`가 필수입니다

  speech_mask        :                        # 발화/무음 구간 (환각 지표의 전제)
    segments[]       : { start_seconds, end_seconds,
                         kind: "speech"|"silence"|"non_speech_audio"|"unknown" }
    overlap_spans[]  : { start_seconds, end_seconds, speaker_ids[] }

  language_spans[]   :                        # 시간축 언어 구간 (문장 내 전환 포함)
    start_seconds, end_seconds, language, speaker_id?,
    switch_kind      : "inter_sentential" | "intra_sentential" | "unknown"

  # ── 시각 도메인 ──────────────────────────────────
  clean_video        : ArtifactRef?           # 깨끗한 영상 (full-reference 지표용)
  degradation_masks[]:                        # 어디를 망가뜨렸는지 (합성 열화 시)
    recipe_id        : 문자열                 # 예: "D-V3"
    degradation_kind : "blur" | "mosaic" | "low_resolution" | "compression"
                       | "sensor_noise" | "unknown"
                       # 정답 종류. DegradedRegion/v1.degradation_kind (§7.5)와
                       # 의미·허용값이 동일하다. §3.3 참조
    mask             : RegionMask
    severity         : 0..5

  # ── 시간축 대응 ──────────────────────────────────
  degraded_media     : ArtifactRef?           # 열화본 (합성 열화 시)
  degraded_timebase  : Timebase?              # domain: "degraded"
  time_mapping       : TimeMapping?           # source ↔ degraded (§2.3)

  known_limitations[]: 문자열                 # 이 번들이 보증하지 못하는 것
```

### 3.0 언어의 정답은 `language_spans[]` 하나뿐입니다

`ReferenceBundle` 안에서 언어는 세 곳에 나타납니다. **정답은 하나입니다.**

| 필드 | 지위 |
|---|---|
| **`language_spans[]`** | **정답(authoritative).** 시간축 구간 기반이며 문장 내 전환(intra-sentential)을 표현할 수 있는 유일한 필드 |
| `utterances[].language` | **파생 편의 필드(derived convenience).** 그 발화의 대표 언어일 뿐 정답이 아니다 |
| `reference_cues[].language` | **파생 편의 필드.** 그 cue의 대표 언어일 뿐 정답이 아니다 |

> **충돌 시 `language_spans[]`가 우선합니다.** 두 단수 필드는 표시·정렬 편의를 위한 값이며,
> 언어 지표(EVALS §4.5)는 **`language_spans[]`만** 정답으로 씁니다.
> 이는 가설 쪽 `Transcript.dominant_language`가 "편의용 파생값일 뿐 정답이 아니다"(§7.3)로
> 규정된 것과 같은 취급입니다 (REVIEW-002 R-13).
>
> code-switching 발화에서 단수 필드에 무엇을 넣을지 애매하면 **비워 둡니다.**
> 추측한 대표 언어를 넣고 그것을 정답처럼 쓰는 것이 더 나쁩니다.

### 3.0.1 정답 축이 둘입니다 — 원문(ASR)과 번역(자막)

채점 정답은 **번역 자막**입니다 ([`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) §2.0, U-08).
그러나 원문 인식 오류와 번역 오류를 구분하려면 **정답도 두 축**이 필요합니다 (T-2·T-3).

| 축 | 무엇의 정답인가 | 번들 안의 위치 |
|---|---|---|
| **원문 축 (`source`)** | `asr`이 낸 **원문 transcript**의 정답 | `speaker_streams[].utterances[].text` (항상 원문 축) · `reference_cues[]` 중 `reference_axis: "source"` |
| **번역 축 (`target`)** | `translate`가 낸 **번역 subtitle**(채점 대상)의 정답 | `reference_cues[]` 중 `reference_axis: "target"` |

**규칙**

| # | 규칙 |
|---|---|
| **X-1** | `reference_cues[]`의 **`reference_axis`는 생략할 수 없습니다.** 축이 없는 cue는 계약 검증 실패이며 그 번들은 평가에 투입하지 않습니다 |
| **X-2** | `speaker_streams[]`는 **언제나 원문 축**입니다. 번역 정답을 이 필드에 넣지 않습니다 |
| **X-3** | **한 축의 정답을 다른 축의 가설과 비교하지 않습니다.** 원문 가설 ↔ 원문 축, 번역 가설 ↔ 번역 축입니다 |
| **X-4** | 두 축의 지표를 **하나의 숫자로 합치지 않습니다** (ADR-0015, T-3) |
| **X-5** | 현재 제품 프로필의 `target_language`는 **`ko`** 입니다 (U-31 해소). target-axis cue가 있는데 값이 누락·`undetermined`·비-`ko`이면 계약 검증 실패이며 그 번들을 한국어 번역 축 평가에 투입하지 않습니다 |

> **번역 모델·API·공급자·프레임워크는 이 계약이 고르지 않습니다** (U-22).
> 이 절은 **정답을 어디에 담고 무엇과 비교하는가**만 규정합니다.
> 두 축의 지표 정의는 [`EVALS.md`](EVALS.md) §4.1(원문 축)·§4.7(번역 축)에 있습니다.

### 3.0.2 언어 authority는 **정답 쪽**과 **가설 쪽**을 나눠 읽습니다 (TASK-029)

§3.0은 **정답(`ReferenceBundle`) 안에서** 무엇이 언어의 정답인지를 정합니다.
가설 산출물 쪽에도 같은 표현을 그대로 옮겨 쓰면 "cue에도 `language_spans`가 있어야 한다"는
잘못된 읽기가 생깁니다 (REVIEW-023 D-01). 세 자리를 구분합니다.

| 자리 | 지위 | 어디에 있나 |
|---|---|---|
| `ReferenceBundle.language_spans[]` | **평가 정답(ground truth).** 언어 지표가 채점 기준으로 쓰는 유일한 값 (§3.0) | `ReferenceBundle` |
| `Transcript.streams[].segments[].language_spans[]` | **가설 쪽 LID의 단일 출처(single source).** ASR/LID가 낸 언어 가설은 여기에만 있습니다 | `transcript-v1.schema.json` |
| `SubtitleDocument` | **독립 LID 가설을 갖지 않습니다.** cue에 `language_spans`·`dominant_language`를 두지 않습니다 | `subtitle-document-v1.schema.json` |

**규칙**

| # | 규칙 |
|---|---|
| **L-1** | 가설 쪽 언어 판단의 정본은 `Transcript.language_spans[]` 하나입니다. `dominant_language`는 그 파생 편의 필드이며 정답으로 쓰지 않습니다 (§7.3) |
| **L-2** | `SubtitleDocument`는 **자체 LID를 주장하지 않습니다.** cue 수준 **문자 범위** 언어는 현재 계약으로 계산할 수 없으므로 **미지원**입니다(REVIEW-024 D-02). cue는 `lineage_fragments[]`로 입력 segment까지, 번역이면 그 segment의 `source_fragments[]`로 원문 segment까지 **segment 수준으로 추적**됩니다. 그 이상은 후속 TASK가 source↔target 문자 정렬과 문자↔시간 매핑을 정의한 뒤의 일입니다 |
| **L-3** | cue의 `review_reasons`에 남는 `language_switch`는 **검토 신호**이지 언어 정답이 아닙니다 |
| **L-4** | `supports_language_id=false`이면 `language_spans`도 `dominant_language`도 **부재**여야 합니다. 설정에서 받은 후보 언어를 결과처럼 기록하지 않습니다 |

> 원문 축 `Transcript` 가설의 언어 시간 귀속 범위는 [`EVALS.md`](EVALS.md) §4.5(a)에 있습니다.
> **segment 단위까지만 지원**하며, segment 안쪽 문자→시간 투영은 token에 문자 오프셋이 없어
> 미지원입니다 (REVIEW-025 D-03).
> 저장 위치를 늘리지 않는 쪽을 택한 이유는, 같은 사실을 두 곳에 적으면 둘이 갈라졌을 때
> 어느 쪽이 정답인지 정할 방법이 없기 때문입니다.
>
> **cue 문자 범위 LID를 "결정적으로 투영한다"고 쓰지 않습니다.** 현재 계약에는 번역
> target 문자와 원문 문자 사이의 정렬이 없고, `Transcript` token에는 문자 오프셋이 없으며,
> `norm-v1`(U-19)도 미정입니다. 없는 대응을 있다고 쓰는 것이 저장 중복보다 나쁩니다.

### 3.1 부분 번들 (Partial Bundle)

**모든 필드가 항상 채워지지는 않습니다.** 실제 입력에는 `clean_video`가 없습니다.

- `completeness` 플래그가 **어떤 지표를 계산할 수 있는지 결정**합니다.
- 필요한 정답이 없으면 해당 지표는 **"미지원(unsupported)"으로 보고**합니다.
  0점이나 결측 평균으로 처리하지 않습니다.
- 지표별 필요 조건은 [`EVALS.md`](EVALS.md) §4–§5의 각 지표 정의에 명시합니다.

**두 정답 축의 계산 가능 조건 (§3.0.1)**

| 상태 | 원문 축 지표 | 번역 축 지표 |
|---|---|---|
| `reference_axis: "source"` cue 또는 `speaker_streams[]`만 있음 | 계산 가능 | **미지원** |
| `reference_axis: "target"` cue가 있고 `target_language: "ko"` | 원문 축 정답이 있으면 계산 가능 | 계산 가능 |
| `reference_axis: "target"` cue는 있으나 `target_language`가 누락·`undetermined`·비-`ko` | 영향 없음 | **계약 검증 실패** — 한국어 번역 축 평가에 투입하지 않음 |

> **한 축이 미지원이라고 다른 축을 대신 보고하지 않습니다.** 원문 축 CER을 번역 품질처럼
> 쓰는 것이 REVIEW-005 M-01이 지적한 실패 시나리오입니다.

### 3.2 버전 규칙

- 필드 추가(하위 호환) → minor 증가
- 의미 변경·필드 제거 → major 증가
- **major가 다른 번들 사이의 점수를 비교하지 않습니다.**

### 3.3 `degradation_kind` — 정답 축과 계약 검증

[`EVALS.md`](EVALS.md) §5.1의 **종류 정확도(`degradation_kind` 혼동 행렬)** 는 정답 축을 필요로 합니다.
그 정답이 `degradation_masks[].degradation_kind`입니다.

| 규칙 | 내용 |
|---|---|
| **같은 의미·같은 허용값** | `degradation_masks[].degradation_kind`의 허용값은 `DegradedRegion/v1.degradation_kind`(§7.5)와 **문자 그대로 동일한 집합**입니다: `blur` · `mosaic` · `low_resolution` · `compression` · `sensor_noise` · `unknown`. **새 종류를 추가하지 않습니다.** 한쪽에 값을 추가하려면 **양쪽을 함께** 바꾸고 major를 올립니다 |
| **생성 시 함께 기록** | 합성 열화를 생성할 때 `recipe_id`와 `degradation_kind`를 **함께** 기록합니다. 레시피를 적용했는데 종류를 비워 두는 경로는 없습니다 ([`EVALS.md`](EVALS.md) §3.2) |
| **불일치는 계약 검증 실패** | 같은 항목의 `recipe_id`가 가리키는 종류와 `degradation_kind`가 **다르면 계약 검증 실패**입니다. 그 번들은 평가에 투입하지 않습니다. 한쪽을 추측으로 고쳐 통과시키지 않습니다 |
| **`unknown`의 취급** | 정답이 `unknown`인 항목은 **종류 정확도의 분모에서 제외**합니다 (탐지 지표에는 그대로 포함). "모른다"를 정답으로 채점하지 않습니다 |

> `recipe_id → degradation_kind` 대응표는 [`EVALS.md`](EVALS.md) §3.2의 레시피 목록에 있습니다.
> 실제 입력(합성이 아닌 경우)에는 `degradation_masks[]` 자체가 없으므로,
> §3.1에 따라 종류 정확도는 **"미지원"으로 보고**합니다 (REVIEW-002 M-05).

---

## 4. 모듈 지도

```
                        ┌──────────────┐
                        │      ui      │  (Phase 3, 선택적 껍데기)
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │ orchestrator │  작업 그래프 · 스케줄 · 캐시 · 자원
                        └──┬────────┬──┘
                           │        │
          ┌────────────────┘        └────────────────┐
   ══ 자막 도메인 ══                        ══ 시각 도메인 ══
          │                                          │
   ┌──────▼──────┐                            ┌──────▼───────┐
   │    audio    │ VAD·잡음·분리·분절          │  reconstruct  │ 탐지·재구성·일관성
   └──────┬──────┘                            └──────┬───────┘
   ┌──────▼──────┐                                   │
   │     asr     │ 전사·언어식별 → 원문 transcript     │
   └──────┬──────┘                                   │
   ┌──────▼──────┐                                   │
   │  translate  │ 원문 → 번역 (공급자 중립)           │
   └──────┬──────┘                                   │
   ┌──────▼──────┐                                   │
   │  subtitle   │ 정렬·분할·형식화·출력              │
   └──────┬──────┘                                   │
          │                                          │
          └──────────────┐          ┌────────────────┘
                         │          │
   ══ 횡단 기반 (양쪽이 공유) ══
                         │          │
              ┌──────────▼──────────▼──────────┐
              │  ingest · storage · 공통 계약   │
              └──────────────┬─────────────────┘
                             │
                  ┌──────────▼──────────┐        ┌──────────┐
                  │        eval         │        │  export  │ (Phase 4, 선택)
                  └─────────────────────┘        └──────────┘
```

**모듈 ID 목록 (전 문서 공통):**
`ingest` · `audio` · `asr` · `translate` · `subtitle` · `reconstruct` · `eval` · `orchestrator` · `storage` · `ui` · `export`

> **명칭 주의:** 시각 도메인 모듈 이름은 `reconstruct`입니다. `restore`는 사용하지 않습니다
> (`AGENTS.md` §1 용어 정책). 어댑터 이름도 `ReconstructionAdapter`입니다.
>
> **`translate`는 별도 모듈입니다** (U-08 답변 반영 — [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) §2.0 T-1).
> `asr`이 번역하지 않고, `subtitle`이 번역하지 않습니다. 책임 경계는 §7.11에 있습니다.
> **모듈 경계만 정의하며 번역 모델·API·공급자는 고르지 않습니다** (U-22). 대상 언어는 사람 제품 오너가 한국어(`ko`)로 확정했습니다 (U-31).

---

## 5. `ReconstructionPolicy/v1` — 안전 게이트 *(제안됨 — 정책·세부 모두)*

> **상태 정정 (2026-08-09, REVIEW-002 M-01):** 이전 판은 "정책 승인됨"이었습니다.
> **사람 제품 오너가 ADR-0022를 이전에 승인한 적이 없다고 확인했으므로 제안됨으로 정정**했습니다.
> 게이트의 필요성 자체가 철회된 것은 아니며, **승인 라벨만** 내려간 것입니다.
> 기본 정책 수준은 여전히 **U-28** 미해결입니다.

**모든 재구성은 이 게이트를 통과한 뒤에만 실행됩니다.** 기본값은 "하지 않음"입니다.

일부 흐림·모자이크는 **의도적 비식별 처리(intentional redaction)** 입니다.
그것을 자동으로 되돌리려 시도하는 것은 제품 범위 밖이며 (`PRODUCT_SPEC.md` N2–N3),
윤리적·법적 위험이 큽니다.

```
ReconstructionPolicy/v1:
  schema_version        : "1.0.0"
  policy_id             : 문자열
  default_action        : "skip"              # 기본값은 항상 skip
  region_rules[]        :
    region_class        : "face" | "identity_document" | "license_plate"
                          | "text_protected" | "intentional_redaction"
                          | "generic_degradation" | "unknown"
    action              : "skip" | "require_confirmation" | "allow"
    rationale           : 문자열
  require_user_confirmation_for[] : region_class
  audit_log_ref         : ArtifactRef         # 어떤 결정이 내려졌는지 기록
```

### 5.1 강제 규칙

| # | 규칙 |
|---|---|
| P1 | `face`, `identity_document`, `license_plate`, `text_protected`, `intentional_redaction`은 **기본 `skip`** |
| P2 | 위 분류를 `allow`로 바꾸려면 **사용자의 명시적 확인**이 필요하다. 기본 설정으로는 불가능하다 |
| P3 | 분류가 `unknown`이면 `require_confirmation`으로 처리한다. **모르면 진행하지 않는다** |
| P4 | 의도적 비식별 처리로 판정된 영역은 사용자가 확인해도 **신원 식별 목적으로는 지원하지 않는다** (N2–N3) |
| P5 | 모든 게이트 판정은 `audit_log_ref`에 기록한다. 조용히 통과시키지 않는다 |

### 5.2 정직한 한계

`intentional_redaction`과 `generic_degradation`을 **자동으로 정확히 구분할 수 없습니다.**
분류기는 틀립니다. 그래서 P3(모르면 확인 요구)이 존재합니다.
분류 임계값과 기본 정책 수준은 미해결 **U-28**입니다.

---

## 6. 재현성 등급 (Reproducibility Tiers) *(제안됨)*

**"재현 가능하다"는 한 가지 뜻이 아닙니다.** 세 등급을 구분해 사용합니다.
manifest만으로 동일 출력이 보장된다고 주장하지 않습니다.

| 등급 | 이름 | 보증 내용 | 확인 방법 |
|---|---|---|---|
| **T1** | 비트 단위 결정성 (bitwise determinism) | 동일 입력·설정·환경에서 **바이트 단위로 동일한** 출력 | 산출물 해시 일치 |
| **T2** | 허용오차 내 반복성 (repeatability within tolerance) | 동일 입력·설정에서 **정의된 허용오차 내** 동일 결과 | 지표 차이가 tolerance 이하 |
| **T3** | 출처 재현성 (provenance reproducibility) | **무엇으로 어떻게 만들었는지 완전히 기록**됨. 출력 동일성은 보증하지 않음 | manifest 완전성 검사 |

**적용 방침**

- `manifest`는 **T3만 보증합니다.** T1·T2는 별도 확인이 필요합니다.
- GPU 비결정 커널, 비결정적 스레드 축약, 라이브러리 버전 차이가 있는 경로는 **T1을 주장하지 않습니다.**
- 각 파이프라인 단계는 자신이 어느 등급인지 manifest에 기록합니다.

```
ReproducibilityClaim:
  tier              : "T1" | "T2" | "T3"
  scope             : "stage" | "pipeline"
  tolerance?        : { metric_name -> 허용 차이 }    # T2에만 존재
  nondeterminism_sources[] : 문자열
                      # 예: "gpu_atomics", "cudnn_autotune", "thread_reduction_order"
  verified_by       : "hash_match" | "tolerance_check" | "not_verified"
```

- 평가 비교에서 T2를 쓸 때는 **허용오차를 리포트에 명시**합니다.
- `verified_by: "not_verified"`인 주장을 근거로 개선을 선언하지 않습니다.

**허용오차 수치는 미정입니다 (U-29).** 기준선 측정 후 정합니다.

---

## 7. 모듈별 책임과 경계

> **절 번호는 문서 순서이며 파이프라인 순서가 아닙니다.**
> 자막 도메인의 실행 순서는 `ingest → audio → asr → translate → subtitle`이며
> **§4 모듈 지도와 §8 데이터 흐름**이 정답입니다.
> `translate`는 나중에 추가되었으므로 기존 절 번호(§7.5·§7.8 등 다른 문서가 참조 중)를
> 흔들지 않기 위해 **§7.11**에 두었습니다. 번호가 뒤라는 것이 단계가 뒤라는 뜻이 아닙니다.

### 7.1 `ingest` — 미디어 입력 *(횡단 기반, 공유)*

| 항목 | 내용 |
|---|---|
| 책임 | 미디어 조사, 트랙 정보 추출, 오디오/프레임 접근 제공, 해시 계산, `Timebase` 확정 |
| 하지 않는 것 | 품질 판단, 잡음 제거, 전사, 화면 수정 |

```
MediaProfile/v1:
  schema_version     : "1.0.0"
  source_ref         : ArtifactRef
  content_hash       : 문자열
  duration_seconds   : 실수
  container          : 문자열
  timebase           : Timebase                # domain: "source"
  audio_tracks[]     : { index, codec, sample_rate, channels, language_hint? }
  video_tracks[]     : { index, codec, width, height, fps_num, fps_den,
                         is_variable_rate, bit_depth? }
  has_video          : 불리언
  probe_warnings[]   : 문자열                  # 깨진 인덱스, VFR, 불일치 등
```

> `language_hint`는 **힌트일 뿐** 신뢰하지 않습니다. 컨테이너 메타데이터는 자주 틀립니다.

---

### 7.2 `audio` — 오디오 프론트엔드

| 항목 | 내용 |
|---|---|
| 책임 | 정규화, 발화 구간 탐지(VAD), 잡음 처리, 화자/음원 분리 검토, 분절 |
| 하지 않는 것 | 전사, 언어 판정, 자막 형식 |

**겹치는 발화를 표현할 수 있어야 합니다.** 단일 선형 구간 목록으로는 불가능합니다.

```
SpeechSegment/v1:
  schema_version     : "1.0.0"
  segment_id         : 문자열
  timebase_ref       : timebase_id
  start_seconds      : 실수
  end_seconds        : 실수
  audio_ref          : ArtifactRef
  speech_confidence  : 0..1

  # ── 겹침 표현 ──────────────────────────────
  stream_id          : 문자열       # 동일 시각에 복수 스트림이 존재할 수 있음
  concurrent_stream_ids[] : 문자열  # 이 구간과 시간이 겹치는 다른 스트림
  overlap_kind       : "none" | "partial" | "full" | "unknown"
  separation_method  : "none" | "diarization" | "source_separation" | "channel"
  speaker_label?     : 문자열       # diarization 채택 시에만 (U-15)
  speaker_confidence?: 0..1

  snr_estimate?      : 실수
  processing_chain[] : { step, params_hash }   # 어떤 처리를 거쳤는지
  provenance         : { adapter_id?, adapter_version?, config_hash }
```

**핵심 설계**

- `stream_id`가 있어 **같은 시각에 여러 SpeechSegment가 공존**할 수 있습니다.
  이것이 겹치는 발화를 표현하는 유일한 방법입니다.
- `overlap_kind: "unknown"`은 정상 상태입니다. 겹침 탐지에 실패했음을 정직하게 표시합니다.
- `separation_method: "none"`이면 하나의 스트림만 존재하며, 겹침 구간의 두 번째 화자는
  **표현되지 않습니다.** 이 경우 평가는 해당 지표를 "미지원"으로 보고합니다.

**이 모듈이 어려운 입력의 1차 방어선입니다.**
긴 무음을 여기서 걸러야 `asr`이 환각을 만들 기회가 줄어듭니다.
다만 과도한 잡음 제거·과도한 VAD는 실제 발화를 버립니다.
**강도는 평가로 결정할 항목입니다 (U-12).**

> **기계 정본: [`schemas/speech-segment-v1.schema.json`](../schemas/speech-segment-v1.schema.json)** (TASK-029).
> 위 블록은 설계 의도를 읽기 위한 pseudo-contract이며, 필드·enum이 다르면 **schema가 정답**입니다.
> ID 유일성과 concurrent 참조 대칭성은 하나의 segment 객체로 표현할 수 없어
> [`src/media_clarity/subtitle_contracts.py`](../src/media_clarity/subtitle_contracts.py)의
> ordered 집합 validator가 검사합니다. 차이 목록은 §7.12를 보십시오.

---

### 7.3 `asr` — 음성 인식

| 항목 | 내용 |
|---|---|
| 책임 | 구간별 전사, 언어 식별, 토큰 타이밍, 신뢰도 산출 |
| 하지 않는 것 | **번역** (→ `translate`, §7.11), 자막 줄 나누기, 형식 규칙, 파일 출력 |
| 산출물의 지위 | `Transcript/v1`은 **원문 transcript**이며 **채점 대상이 아닙니다.** 그러나 원문 축 평가와 오류 출처 구분을 위해 **반드시 산출·보존**합니다 ([`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) §2.0 T-2) |

**문장 내 언어 전환(intra-sentential code-switching)을 표현할 수 있어야 합니다.**
구간에 언어 하나를 붙이는 구조로는 불가능합니다.

```
Transcript/v1:
  schema_version     : "1.0.0"
  timebase_ref       : timebase_id
  streams[]          :
    stream_id        : 문자열
    speaker_label?   : 문자열
    segments[]       :
      segment_id     : 문자열
      text           : 문자열
      tokens[]?      : { text, start_seconds?, end_seconds?, confidence? }
      language_spans[]:                        # 문장 내 전환 표현
        char_start   : 정수                    # text 내 문자 오프셋
        char_end     : 정수
        language     : BCP-47
        confidence?  : 0..1
        switch_kind  : "inter_sentential" | "intra_sentential" | "unknown"
      dominant_language? : BCP-47              # 편의 필드 (파생값)
      segment_confidence?: 0..1
      is_low_confidence  : 불리언
      alternatives[]?    : { text, score }     # n-best
  capability_report  : AdapterCapabilityReport # 아래 §7.3.1
  provenance         : { adapter_id, adapter_version, params_hash, seed? }
```

**설계 근거**

- `language_spans`가 **문자 오프셋 기반**이라 한 문장 안의 전환을 표현합니다.
  `dominant_language`는 편의용 파생값일 뿐 정답이 아닙니다.
- `tokens`, `confidence`, `language_spans`는 **전부 선택 필드(optional)** 입니다.
  모든 ASR 모델이 이를 제공하지는 않기 때문입니다.

> **기계 정본: [`schemas/transcript-v1.schema.json`](../schemas/transcript-v1.schema.json)** (TASK-029).
> `Transcript/v1`은 **immutable ASR evidence**입니다. 번역·사람 교정·forced alignment가 이 문서를
> 덮어쓰지 않으며, forced alignment 결과는 **후속 별도 artifact**입니다 (TASK-029에서 만들지 않음).
> 모든 문자 offset은 exact stored `text`의 **Unicode scalar value index** 반개구간입니다.

#### 7.3.1 어댑터 능력 보고와 대체 동작 (Fallback)

**능력이 없는 것과 값이 0인 것은 다릅니다.** 이를 혼동하면 평가가 조용히 틀립니다.

```
AsrAdapter (인터페이스):
  capabilities() -> AdapterCapabilityReport
  transcribe(segments, options) -> Transcript

AdapterCapabilityReport:
  adapter_id, adapter_version
  languages[]                 : BCP-47 목록 또는 "unknown"
  supports_word_timing        : 불리언
  supports_token_confidence   : 불리언
  supports_language_id        : 불리언
  supports_intra_sentential_lid : 불리언
  supports_overlap_streams    : 불리언
  supports_nbest              : 불리언
  requires_gpu                : 불리언
  determinism_tier            : "T1" | "T2" | "T3"
```

| 없는 능력 | 대체 동작 | 평가에 미치는 영향 |
|---|---|---|
| 단어 타이밍 없음 | `tokens` 생략. 세그먼트 경계만 사용. 강제 정렬(forced alignment)을 **별도 단계로** 시도할 수 있으나, 그 사실을 `provenance`에 기록 | 토큰 단위 타임스탬프 지표는 **미지원** |
| 신뢰도 없음 | `confidence` 필드 **생략**. 1.0으로 채우지 않는다 | 신뢰도 기반 지표는 **미지원**. `needs_review` 판정은 다른 신호로 대체 |
| 언어 식별 없음 | `language_spans` 생략. `dominant_language`를 설정에서 받은 값으로 기록하되 `switch_kind: "unknown"` | 언어 식별 정확도 지표는 **미지원** |
| 문장 내 LID 없음 | 세그먼트 전체를 하나의 span으로 기록 | 문장 내 전환 지표는 **미지원** |
| 겹침 스트림 없음 | 단일 스트림만 생성 | cpWER은 **미지원**, 완화 지표로 대체 ([`EVALS.md`](EVALS.md) §4.2) |

> **금지:** 없는 값을 기본값으로 채우는 것. `confidence = 1.0`, `language = "en"` 같은
> 조용한 채움은 지표를 오염시키고 오염 사실을 숨깁니다.

**다국어 전략은 아직 미정입니다 (U-13).** (a) 구간별 LID 후 언어별 모델, (b) 다국어 통합 모델.

> **기계 정본: [`schemas/adapter-capability-report-v1.schema.json`](../schemas/adapter-capability-report-v1.schema.json)** (TASK-029).
> 정본은 위 목록에 없는 축(token timing unit, confidence semantics, channel 입력, term injection,
> candidate language, network 요구)을 추가로 고정하고, 실행 결과와의 결박을 Transcript의
> `feature_status` 일곱 key로 표현합니다 (`produced | not_requested | no_result | unsupported`).

---

### 7.4 `subtitle` — 자막 구성

| 항목 | 내용 |
|---|---|
| 책임 | **시간 정렬 다듬기 · 자막 단위 분할 · 줄바꿈 · 형식 규칙 적용 · 파일 출력, 이것뿐입니다** |
| 하지 않는 것 | **번역** (→ `translate`, §7.11), 전사 내용 변경, **번역문 내용 변경**, 오디오 접근 |
| 입력 | **`TranslatedTranscript/v1`** (번역 경로 — 채점 대상 산출) 또는 `Transcript/v1` (원문 자막을 따로 뽑을 때) |

> **`subtitle`은 언어를 바꾸지 않습니다.** 입력이 원문이면 출력도 원문이고,
> 입력이 번역문이면 출력도 번역문입니다. 채점 대상인 **번역 자막**을 만들려면
> **반드시 `translate`를 거친 입력**이 들어와야 합니다 (T-1).
> `SubtitleDocument`가 어느 축인지는 아래 `text_axis`가 밝힙니다.

```
SubtitleDocument/v1:
  schema_version     : "1.0.0"
  timebase_ref       : timebase_id
  text_axis          : "source" | "target"   # ★ 이 문서의 텍스트가 원문인가 번역인가.
                                             # 생략 불가. ReferenceBundle.reference_axis(§3.0.1)와
                                             # 같은 축끼리만 비교한다 (규칙 X-3)
  source_document_ref? : ArtifactRef         # text_axis="target"일 때 대응하는 원문 산출물
  cues[]             :
    cue_id           : 문자열
    start_seconds    : 실수
    end_seconds      : 실수
    lines[]          : 문자열
    language_spans[] : { line_index, char_start, char_end, language }
                       # 한 cue 안에서 언어가 바뀔 수 있음
    dominant_language?: BCP-47
    speaker_label?   : 문자열
    stream_id?       : 문자열
    concurrent_cue_ids[] : 문자열      # 동시 표시되는 다른 화자의 cue
    overlap_kind     : "none" | "partial" | "full" | "unknown"
    confidence?      : 0..1            # 없으면 생략 (채우지 않음)
    needs_review     : 불리언
    review_reason[]  : "low_confidence" | "overlap" | "language_switch"
                       | "timing_uncertain" | "format_violation" | "silence_adjacent"
  style_profile      : { max_chars_per_line, max_lines, max_cps,
                         min_duration, max_duration, min_gap, language_overrides{} }
  unsupported_features[] : 문자열      # 출력 형식이 표현하지 못한 것
  provenance         : { input_hash, config_hash, pipeline_version,
                         adapter_versions{}, seed?, reproducibility_claim }
```

**설계 근거**

- `concurrent_cue_ids`로 **동시 발화를 표현**합니다. 겹침을 하나의 cue로 뭉개지 않습니다.
- `unsupported_features`가 중요합니다. 출력 형식(U-09)에 따라 화자 표기·위치 지정·동시 자막이
  표현되지 않을 수 있습니다. **표현하지 못한 것을 조용히 버리지 않고 기록**합니다.
- `review_reason`은 사람이 어디를 봐야 하는지 알려줍니다.
  자동 결과는 초안이며, **어디가 불확실한지 말해주는 것이 "다 맞다"보다 유용**합니다.

> **기계 정본: [`schemas/subtitle-document-v1.schema.json`](../schemas/subtitle-document-v1.schema.json)** (TASK-029).
> 정본은 cue마다 **line별 exact scalar fragment lineage**(`lineage_fragments[]`)와, 원문 whitespace를
> 줄 경계로 옮긴 기록(`line_break_whitespace[]`)을 필수로 둡니다. 직접 입력 문서의 모든 scalar 범위는
> 둘 중 하나로 **정확히 한 번** 덮여야 하며, 공백 없는 일본어 줄 분할도 인접 visible range로 표현합니다.
> U-18이 미정이므로 CPS·줄 길이·표시시간 숫자는 schema 기본값이 아니라
> `style_profile_id`/`style_profile_version`과 실행 시점 `resolved_style` snapshot으로 남깁니다.

---

### 7.5 `reconstruct` — 시각 재구성 (Phase 2)

| 항목 | 내용 |
|---|---|
| 책임 | 열화 영역 탐지, 재구성 **추정**, 시간적 일관성, 인공물 검사, 안전 게이트 집행 |
| 하지 않는 것 | 오디오·자막 관련 일체. 원본 복구 주장 (`AGENTS.md` §1) |

```
DegradedRegion/v1:
  schema_version     : "1.0.0"
  region_id          : 문자열
  mask               : RegionMask              # 이동 영역 지원 (§2.4)
  degradation_kind   : "blur" | "mosaic" | "low_resolution" | "compression"
                       | "sensor_noise" | "unknown"
  region_class       : ReconstructionPolicy의 region_class (§5)
  severity_estimate  : 0..1
  detector_confidence: 0..1

ReconstructionResult/v1:
  schema_version     : "1.0.0"
  timebase_ref       : timebase_id
  regions[]          : DegradedRegion
  output_ref         : ArtifactRef
  is_estimate        : 항상 true               # 상수. false가 되는 경로 없음
  policy_decisions[] : { region_id, action_taken: "skipped"|"reconstructed"
                                              |"awaiting_confirmation",
                         policy_id, reason }
  confidence_map?    : ArtifactRef             # 영역별 추정 신뢰도
  temporal_consistency : { warping_error, flicker_index, method, window_seconds }
  artifact_flags[]   : { region_id?, time_range, kind, severity, note }
  clean_region_delta : { changed_pixel_ratio, mean_abs_change }
                       # 손대지 않아야 할 영역이 얼마나 변했는가
  disclaimer         : "재구성 결과는 추정치이며 원본과 다를 수 있습니다"
  provenance         : { adapter_id, adapter_version, params_hash, seed?,
                         reproducibility_claim }
```

> **`is_estimate`가 상수 true인 것은 의도된 설계입니다.**
> 이 필드가 false가 될 수 있는 조건은 존재하지 않습니다.
> 원본을 모르는 상태에서 추정이 아닌 결과는 나올 수 없습니다.

```
ReconstructionAdapter (인터페이스):
  capabilities() -> { handles[], max_resolution, temporal_aware,
                      requires_gpu, determinism_tier }
  detect(frames) -> DegradedRegion[]
  reconstruct(frames, regions, policy, options) -> ReconstructionResult
```

- `policy`는 **선택 인자가 아닙니다.** 정책 없이 재구성을 호출할 수 없습니다 (A8).
- `clean_region_delta`는 "건드리지 말아야 할 곳을 건드렸는가"를 재는 필수 출력입니다
  ([`EVALS.md`](EVALS.md) §5.3).

---

### 7.6 `eval` — 평가 *(횡단 기반, 공유)*

| 항목 | 내용 |
|---|---|
| 책임 | 평가 세트 관리, 지표 계산, 통계 처리, 리포트 출력, 실행 간 비교 |
| 하지 않는 것 | 파이프라인 내부 수정, 모델 학습 |

```
EvalReport/v1:
  schema_version     : "1.0.0"
  run_id             : 문자열
  split              : "dev" | "test"          # frozen-test 분리 (EVALS §2)
  pipeline_version   : 문자열
  config_hash        : 문자열
  seeds[]            : 정수                    # 복수 시드
  dataset_id         : 문자열
  bundle_schema_version : 문자열
  sample_counts      : { total, per_condition{}, per_language{}, per_source{} }

  # ── 자막 도메인 지표는 정답 축별로 분리해서 담습니다 (§3.0.1 X-4) ──
  metrics_by_axis    :
    source           : { 지표명 -> { value, ci_low?, ci_high?, n, status } }
                       # 원문 ASR 축 (EVALS §4.1~§4.6)
    target           : { 지표명 -> { value, ci_low?, ci_high?, n, status } }
                       # 번역 자막 축 (EVALS §4.7). 현재 제품 target_language="ko"
  metrics            : { 지표명 -> { value, ci_low?, ci_high?, n, status } }
                       # 축이 없는 지표(시각 도메인 등)
                       # status: "computed" | "unsupported" | "insufficient_n" | "failed"
                       #   (네 값 — EVAL_HARNESS §4. "failed"는 metric 실행 자체가
                       #    실패한 경우이며, unsupported·insufficient_n과 마찬가지로
                       #    value를 쓰지 않고 reason을 남깁니다)
  per_condition[]    : { condition_id, severity, metrics }
  per_stratum[]      : { stratum_key, metrics }
  paired_comparison? : { baseline_run_id, deltas{}, ci{}, n_pairs,
                         meets_minimum_effect: 불리언 }
  unsupported_metrics[] : { metric, reason }
  notes[]            : 문자열
```

**두 축을 하나로 합치지 않습니다.** `metrics_by_axis.source`와 `metrics_by_axis.target`을
가중 평균·합계·단일 종합 점수로 만드는 필드는 **의도적으로 없습니다** (ADR-0015, T-3).
리포트를 읽는 사람이 **두 숫자를 같이** 봐야 오류의 출처를 알 수 있습니다.

**`eval`은 파이프라인을 수정할 권한이 없습니다.** 측정만 합니다.
측정자와 피측정자를 분리해야 자기충족적 결과를 피할 수 있습니다.

상세 설계는 [`EVALS.md`](EVALS.md).

---

### 7.7 `orchestrator` — 실행 조율 *(횡단 기반, 공유)*

```
Job/v1:
  job_id, project_id
  pipeline           : "subtitle" | "reconstruct" | "eval"
  input_ref          : ArtifactRef
  config, seed
  stages[]           : { stage_id, status, started_at, finished_at,
                         artifact_refs[], reproducibility_claim, error? }
  status             : "queued"|"running"|"paused"|"failed"|"completed"|"cancelled"
```

**요구사항**

- 단계 산출물은 캐시된다 → 뒷단계 실패 시 앞단계를 다시 돌리지 않는다
- 한 도메인의 실패가 다른 도메인을 중단시키지 않는다 (A1)
- 긴 작업은 중단·재개 가능하다 (사용자 PC는 껐다 켜집니다)
- 자원 정책은 **벤더 중립 추상화** 뒤에 둔다 (U-03)

**구현 경계 (TASK-028)**

기계 검증 형태는 [`schemas/job-v1.schema.json`](../schemas/job-v1.schema.json)이고, 구현은
`src/media_clarity/job_runtime.py`의 **local synchronous** runtime입니다. 위 의사코드와
schema 파일이 다르면 schema 파일이 정답입니다.

- stage cache key는 canonical JSON 바이트의 SHA-256이며 runtime/schema version, pipeline·stage
  ID, implementation version, 정렬된 입력 content hash, config·dependency·source·chunking·
  model·context fingerprint, random seed, 재현성 등급, **직접 dependency의 cache key**를 담습니다.
  선택 항목은 **부재 자체가 canonical 값**입니다.
- **job fingerprint는 stage cache key와 다릅니다.** job fingerprint에는 pipeline ID,
  runtime/schema version, source identity, DAG topology만 들어갑니다. 개별 stage의
  config/model/context/implementation 변경은 job resume을 막지 않고 해당 stage와 downstream을
  cache miss로 만듭니다. 이 구분이 없으면 "job fingerprint가 다르면 resume 거부"와
  "A만 miss이고 독립 branch는 재사용"이 동시에 성립할 수 없습니다.
- cache hit는 completed checkpoint와 **모든 출력 artifact의 존재·hash·size를 다시 확인한 뒤에만**
  성립합니다. `running` attempt는 어떤 경우에도 hit가 되지 않습니다.
- attempt는 callable 호출 **전에** `running`으로 기록하고, artifact를 승격·재검증한 **뒤에야**
  `completed`로 전이합니다. 남은 `running` record는 지우지 않고 `interrupted`로 보존하며 새
  attempt ID로 다시 실행합니다.
- worker process supervision, 비동기 scheduler, 멀티프로세스 동시 실행은 이 구현의 범위 밖입니다.
  중단 시나리오는 결정적 failure-injection hook으로만 재현하며 production 기본값에서는 비활성입니다.

---

### 7.8 `storage` — 저장과 파일 정리 *(횡단 기반, 공유)*

```
<project_root>/
├── project.json
├── inputs/                   # 원본 참조 (기본: 복사하지 않고 참조 + 해시)
├── references/               # ReferenceBundle (평가용 정답)
├── artifacts/
│   └── sha256/<prefix>/<digest>   # content-addressed store (TASK-028)
├── jobs/
│   └── <job_id>/
│       ├── manifest.json     # 설정·버전·시드·입력 해시·재현성 등급
│       ├── stages/           # 단계별 attempt record와 작업 공간 (A4)
│       │   └── <stage_id>/attempts/<attempt_id>.json
│       └── logs/
├── outputs/
│   ├── subtitles/
│   └── reconstructions/      # 항상 "추정 결과"로 라벨링
└── evals/
    ├── dev/<run_id>/
    └── test/<run_id>/        # frozen-test (EVALS §2.1)
```

**안전 규칙**

- 원본 입력 파일은 **절대 수정하거나 덮어쓰지 않습니다.** (ADR-0010)
- 출력은 항상 새 파일로 씁니다. 같은 이름이 있으면 덮어쓰지 않고 알립니다.
- 삭제는 사용자의 명시적 행동으로만 일어납니다.
- 보관 정책은 미정입니다 (U-16).

**content-addressed store (TASK-028, `src/media_clarity/artifact_store.py`)**

- SHA-256을 chunked streaming으로 계산합니다. 입력 전체를 RAM에 올리지 않습니다.
- 검증된 임시 파일만 **원자적 no-overwrite**로 최종 경로에 승격합니다. 안전한 원자 승격을
  제공할 수 없는 filesystem에서는 덮어쓰는 fallback 대신 안정 오류로 실패합니다.
- 최종 경로가 이미 있으면 기존 바이트를 다시 hash·size 검증합니다. 같으면 dedupe hit,
  다르면 손상·collision으로 실패하며 기존 파일을 수정하지 않습니다.
- `ArtifactRef.uri`는 project root 기준 portable relative path이며 외부 절대 경로를 담지 않습니다.
- **자동 삭제·GC·eviction이 없습니다** (U-16 미정). 실패한 임시 파일은 증거로 남고 완료
  artifact나 cache hit로 보이지 않습니다.

---

### 7.9 `ui` — 사용자 인터페이스 (Phase 3)

**A7: UI는 껍데기입니다.** `orchestrator`가 노출하는 것만 씁니다.

필수 요구 (프레임워크와 무관):

- 진행 상황과 남은 작업을 보여준다
- 자막을 직접 고칠 수 있다 (`needs_review` 우선 표시)
- **원본과 추정 결과를 나란히 비교**할 수 있다
- 재구성 결과에 **추정임을 명시**한다 (`AGENTS.md` §1)
- **`ReconstructionPolicy` 확인 요청을 사용자에게 제시**한다 (§5 P2)
- 무엇이 왜 실패했는지 사람 말로 설명한다

프레임워크는 미정입니다 (U-02).

---

### 7.10 `export` — 내보내기 (Phase 4)

- 기본값은 **로컬**입니다. 클라우드 전송은 사용자가 켜야 합니다.
- 무엇을 보낼지 사용자가 선택합니다. 전체 미디어 자동 업로드는 없습니다.
- 대상 서비스는 미정입니다 (U-14).

---

### 7.11 `translate` — 번역 *(자막 도메인, `asr`과 `subtitle` 사이)*

**파이프라인 위치는 `asr → translate → subtitle`입니다** (§4, §8). 절 번호는 §7 머리말 참조.

| 항목 | 내용 |
|---|---|
| 책임 | 원문 `Transcript/v1`의 텍스트를 **대상 언어로 번역**, 원문 세그먼트와의 **대응 관계 유지**, 번역 신뢰도·검토 필요 표시 |
| 하지 않는 것 | 전사(오디오 접근), 자막 줄 나누기·형식 규칙·파일 출력(→ `subtitle`), **원문 삭제·덮어쓰기** |
| 입력 | `Transcript/v1` (§7.3) |
| 출력 | `TranslatedTranscript/v1` (아래) — **원문을 대체하지 않고 함께 보존**합니다 (T-2) |

**공급자 중립 (provider-neutral)**

이 절은 **경계와 계약만** 정의합니다. 아래를 **고르지 않습니다.**

| 고르지 않는 것 | 어디서 결정되나 |
|---|---|
| 번역 모델·엔진 | **U-22** — 측정 후 결정 (ADR-0012·ADR-0019) |
| 로컬 실행 / 원격 API / 규칙 기반 중 무엇인가 | **U-22** — 어댑터 뒤에 있으므로 계약은 동일 |
| 공급자·서비스 이름 | **U-22** — 측정 후 결정. 어댑터 계약은 실제 선택 이후에도 공급자 중립 유지 |
| **대상 언어** | **한국어, BCP-47 `ko`** — U-31 해소 (2026-08-22 사람 제품 오너) |
| 절대 목표 수치 (품질 임계값) | **U-07** — 기준선 측정 후 |

```
TranslatedTranscript/v1:
  schema_version     : "1.0.0"
  timebase_ref       : timebase_id            # 원문 Transcript와 동일한 시간축을 씁니다
  source_transcript  : ArtifactRef            # 입력이 된 원문 Transcript (참조 — 대체 아님)
  source_language_authority : "Transcript.segments[].language_spans[]"
                                              # 원문 언어의 정답은 원문 쪽에 있습니다 (§7.3)
  target_language    : BCP-47
                       # 현재 제품의 성공 산출물은 **`ko`**. 누락·`undetermined`·비-`ko`는 계약 위반
  streams[]          :
    stream_id        : 문자열                 # 원문 Transcript.streams[].stream_id와 동일 값
    segments[]       :
      source_segment_ids[] : 문자열           # 원문 segment_id 목록 (병합 시 2개 이상)
      segment_id     : 문자열                 # 번역 쪽 식별자
      source_text    : 문자열                 # 원문 (보존 — 나중에 대조할 수 있어야 함)
      target_text    : 문자열                 # 번역 결과
      alignment_kind : "one_to_one" | "merged" | "split" | "dropped" | "unknown"
      confidence?    : 0..1                   # 없으면 **생략** (1.0으로 채우지 않음)
      is_low_confidence  : 불리언
      needs_review   : 불리언
      review_reason[]: "low_confidence" | "alignment_uncertain" | "source_low_confidence"
                       | "language_switch" | "untranslated_span"
  capability_report  : TranslationCapabilityReport
  provenance         : { adapter_id, adapter_version, params_hash, seed? }
```

```
TranslationAdapter (인터페이스):
  capabilities() -> TranslationCapabilityReport
  translate(transcript, options) -> TranslatedTranscript

TranslationCapabilityReport:
  adapter_id, adapter_version
  source_languages[]           : BCP-47 목록 또는 "unknown"
  target_languages[]           : BCP-47 목록 또는 "unknown"
  supports_segment_alignment   : 불리언       # 원문 세그먼트 대응을 보고할 수 있는가
  supports_confidence          : 불리언
  supports_document_context    : 불리언       # 앞뒤 문맥을 함께 볼 수 있는가
  supports_code_switching_input: 불리언       # 문장 내 언어 전환 입력을 다룰 수 있는가
  determinism_tier             : "T1" | "T2" | "T3"
```

| 없는 능력 | 대체 동작 | 평가에 미치는 영향 |
|---|---|---|
| 세그먼트 대응 없음 | `source_segment_ids` 생략, `alignment_kind: "unknown"` | 세그먼트 단위 번역 지표는 **미지원**. 문서 단위만 보고 |
| 신뢰도 없음 | `confidence` **생략** | 신뢰도 기반 지표는 **미지원**. `needs_review`는 다른 신호로 |
| 대상 언어가 어댑터 지원 목록에 없음 | **번역을 시도하지 않고 실패로 보고** | 그 조건의 번역 축 지표는 **미지원** |
| 산출물의 대상 언어가 누락·`undetermined`·비-`ko` | 성공 산출물로 승격하지 않고 계약 실패로 보고 | 한국어 번역 축 평가에 투입하지 않음 |

> **금지:** 대상 언어를 추측해서 채우는 것, 번역 실패를 원문 그대로 복사해 성공처럼 보고하는 것.
> 원문을 그대로 넘긴 구간은 `review_reason: "untranslated_span"`으로 표시합니다.
>
> **`translate`의 상세 설계는 TASK-005·TASK-006의 범위입니다.**
> 이 절은 **모듈 경계·계약·미지원 처리**만 고정하며, 지표의 구체 정의는
> [`EVALS.md`](EVALS.md) §4.7에 있습니다.

> **기계 정본: [`schemas/translated-transcript-v1.schema.json`](../schemas/translated-transcript-v1.schema.json)** (TASK-029).
> `TranslationCapabilityReport`는 그 파일의 `#/$defs/TranslationCapabilityReport`에 **한 번만**
> 정의하며 다른 schema나 Python 상수가 같은 enum·field set을 복제하지 않습니다.
> 정본은 `source_segment_ids` 대신 **exact source fragment**(`source_segment_id` + scalar
> `char_start`/`char_end` + `source_text`)를 쓰고, `coverage_status`(`complete | partial`)와
> `uncovered_source_fragments[]`가 원문의 모든 non-empty scalar 범위를 **정확히 한 번 partition**합니다.

---

### 7.12 pseudo-contract → TASK-029 기계 정본 migration note

§7.2·§7.3·§7.3.1·§7.4·§7.11의 블록은 **읽기 위한 pseudo-contract로 그대로 보존**합니다.
아래는 그 산문과 [TASK-029](tasks/TASK-029.md) 정본 schema의 **실제 차이**이며, 조용히 바뀐 것이
없음을 보이기 위한 기록입니다. 충돌하면 schema가 정답입니다 (§10 문서 우선순위).

| 기존 pseudo-contract | TASK-029 정본 |
|---|---|
| SpeechSegment confidence가 사실상 필수 (`0..1`) | 선택이며, 있으면 `*_confidence_semantics`(`calibrated_probability \| model_score \| provider_opaque`)를 함께 기록. `calibrated_probability`만 `[0,1]`. 미지원값을 1.0으로 채우지 않음 |
| channel 선택의 출처·독립성이 불명확 | `source_track_index`·선택 `source_channel_index`와 `channel_semantics`(`independent \| mixed \| unknown`)로 분리. `separation_method="channel"`은 independent channel일 때만 허용하고, `"none"`이면 speaker label을 주장할 수 없음 |
| Transcript token timing의 출처가 불명확 | **raw ASR timing만** 허용. forced alignment는 후속 별도 artifact이며 이 문서에 합치지 않음 |
| Transcript segment 경계가 명시되지 않음 | source timebase의 `[start_seconds, end_seconds)`와 `source_speech_segment_ids[]` lineage 필수. ASR segment 시간은 참조한 입력 구간 합집합 안에 있어야 함 |
| 문자 offset 단위가 불명확 | exact stored `text`의 **Unicode scalar value index**. lone surrogate가 있는 text는 계약 실패 |
| language span gap·switch 경계 의미가 불명확 | gap과 explicit `und`는 **모두** unknown + `needs_review` + `language_unknown`. 둘 중 하나라도 있으면 `dominant_language` 생략. `switch_kind`는 그 span의 `char_start`로 **들어오는 경계**를 설명하며 첫 span에는 두지 않음 |
| LID 미지원 fallback이 설정값 `dominant_language`를 결과처럼 기록 | `supports_language_id=false`이면 `language_spans`·`dominant_language` 모두 부재. 후보 언어는 실행 options·provenance의 후속 계약 |
| ASR n-best/alternative score의 의미가 불명확 | `supports_nbest`·`nbest_score_semantics`와 실행 `feature_status.nbest`로 결박. score는 semantics가 `none`이 아닐 때만 존재 |
| capability에 channel·term·candidate·network 축이 없음 | capability report에 `supports_independent_channel_input`·`term_injection_modes[]`·`restricts_candidate_languages`·`network_requirement`를 명시 |
| Transcript `streams[].speaker_label?`의 출처가 불명확 | `speaker_label`에는 `speaker_label_source`(`input \| adapter`)가 반드시 동반. input/channel에서 복사한 label은 `feature_status.speaker_diarization="produced"`의 근거가 되지 않음 |
| 번역 capability의 `supports_confidence` boolean | `translation_confidence_semantics`(4값)로 대체. `supports_document_context`·`supports_code_switching_input`은 닫힌 report에 그대로 보존 |
| 번역 `source_segment_ids` 생략 fallback | adapter가 정렬을 보고하지 못해도 orchestrator의 실제 입력 fragment lineage는 **항상** 보존. `alignment_evidence_source`(`adapter \| orchestrator`)가 둘을 구분 |
| `source_language_authority` literal 문자열 경로 | 제거. 원문 언어의 authority는 `source_transcript` ref와 segment lineage이며, literal 경로는 stream 계층을 누락하고 ASR 가설을 정답처럼 표현했음 |
| merged/split에서 source text 범위가 불명확 | exact source fragment + scalar offset. `one_to_one`은 전체, `split`은 non-empty strict subrange, `merged`는 서로 다른 2개 이상, `dropped`는 빈 `target_text` + `untranslated_span` |
| 번역 coverage 개념 없음 | `coverage_status`와 `uncovered_source_fragments[]`가 `complete`·`partial` 모두에서 원문을 정확히 한 번 partition |
| Subtitle cue upstream lineage가 불명확 | 축별 **line별 exact scalar fragment lineage**와 `line_break_whitespace[]`. 직접 입력의 모든 scalar를 정확히 한 번 덮어야 함 |
| target Subtitle에 언어가 없음 | `text_axis="target"`이면 `target_language="ko"`와 원본 Transcript ref가 필수 |
| document-level `unsupported_features[]` 문자열 | `cue_id`·`feature_kind`·`feature_identifier`·`reason_code`·`action`을 갖는 구조형 record. cue 비율을 계산할 수 있음 |
| inline `style_profile` 숫자가 U-18과 충돌 가능 | `style_profile_id`/`style_profile_version` + `resolved_style` snapshot. schema에 기본 숫자를 두지 않음 |
| cue `language_spans[]`·`dominant_language?` | **정본에서 제외.** 가설 쪽 LID의 단일 출처는 `Transcript.language_spans`이고(§3.0.2 L-1), `SubtitleDocument`는 독립 LID 가설을 갖지 않습니다(L-2). cue 수준 **문자 범위** 언어는 현재 계약으로 계산할 수 없어 **미지원**이며(EVALS §4.5(a), REVIEW-024 D-02) cue는 segment 수준으로만 원문까지 추적됩니다. cue의 `review_reasons`에 남는 `language_switch`는 검토 신호이지 정답이 아닙니다 |
| cue `confidence?`·`speaker_label?` | **정본에서 제외.** 결박할 capability 축이 자막 계층에 없어 근거 없는 숫자·label이 되기 때문입니다. 신뢰도 신호는 upstream 문서와 `needs_review`/`review_reasons`가, 화자 표시는 `stream_id`와 lineage가 담당하며 표시 형식은 후속 export/QC TASK의 몫입니다 |

**정본 안에서 한 번만 정의하는 것과, 한 번 더 나타나는 것**

`TranslationCapabilityReport`는 `translated-transcript-v1.schema.json#/$defs`에만 있습니다.
language tag의 구조 subset(`^[a-z]{2,8}(-[A-Za-z0-9]{1,8})*$`)은 `adapter-capability-report-v1`
에만 **타입으로** 정의하고 나머지 schema가 상대 `$ref`로 재사용합니다. 다만
`resolved_style.language_overrides`의 `patternProperties` **key**는 정규식 자체이므로 `$ref`로
대신할 수 없어 그 한 곳에만 같은 문자열이 다시 나타납니다. `common-v1.schema.json`은 TASK-029에서
수정 대상이 아니므로 이 공통 타입을 공통 파일로 올리지 않았습니다.

---

## 8. 데이터 흐름 요약

**자막 도메인**

```
파일 → MediaProfile → SpeechSegment[] (다중 스트림)
                          ↓
                      Transcript            [원문 축] ── 보존. 채점 대상 아님
                          ↓
                 TranslatedTranscript       [번역 축] ── translate (§7.11)
                          ↓
                      SubtitleDocument (text_axis="target") → 자막 파일  ★ 채점 대상
                          ↓
        ReferenceBundle(reference_axis별) + eval → EvalReport(metrics_by_axis)
```

- **두 산출물을 모두 남깁니다.** `Transcript`(원문)와 `TranslatedTranscript`(번역)는
  서로를 대체하지 않습니다 ([`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) §2.0 T-2).
- 원문 자막 파일이 따로 필요하면 `SubtitleDocument(text_axis="source")`를 추가로 만듭니다.
  **번역 자막을 원문 자막으로 대신하지 않습니다.**
- 평가는 **축별로** 계산해 축별로 보고합니다 (§3.0.1, §7.6). 하나의 숫자로 합치지 않습니다.
- 대상 언어는 **한국어(`ko`)** 입니다 (U-31 해소). 어댑터가 `ko`를 지원하지 않으면 번역을
  시도하지 않고 실패로 보고하며, 원문 축 지표는 독립적으로 계속 계산할 수 있습니다.

**시각 도메인**

```
파일 → MediaProfile → DegradedRegion[] → [ReconstructionPolicy 게이트] → ReconstructionResult
                                                                          ↓
                                            ReferenceBundle + eval → EvalReport
```

두 도메인의 **산출물은 서로를 입력으로 쓰지 않습니다.**
`ingest`·`storage`·`orchestrator`·`eval` 하네스·공통 계약은 **공유합니다** (A1).

---

## 9. 횡단 관심사

### 오류 처리

| 등급 | 의미 | 동작 |
|---|---|---|
| Recoverable | 한 구간 실패 | 표시하고 계속. `needs_review` 설정 |
| Degraded | 기능 축소 | 사용자에게 알리고 가능한 만큼 진행 |
| Fatal | 진행 불가 | 중단, 원인 설명, 부분 산출물 보존 |

**부분 결과를 조용히 버리지 않습니다.** 사용자의 계산 시간은 비용입니다.

### 로깅

무엇을 왜 그렇게 했는지 남깁니다. 사용자 미디어 내용 자체는 로그에 넣지 않습니다.

---

## 10. 이 문서에서 파생된 미해결 항목

| ID | 질문 | 영향 |
|---|---|---|
| U-12 | 잡음 제거·VAD 강도의 최적점 | `audio` 설계 |
| U-13 | 다국어를 언어별 모델로 나눌 것인가, 통합 모델에 맡길 것인가 | `asr` 구조 |
| U-14 | 개인 클라우드 대상은 무엇인가 | `export` (Phase 4) |
| U-15 | diarization을 Phase 1에 넣을 것인가 | `audio`·`subtitle` 복잡도 |
| U-16 | 중간 산출물 보관 정책 | `storage` |
| U-28 | `ReconstructionPolicy` 기본 정책 수준과 분류 임계값 | §5 안전 게이트 |
| U-29 | 재현성 T2 허용오차 수치 | §6 |
| ~~U-31~~ | ~~번역 대상 언어는 무엇인가~~ → **한국어(`ko`)** | **해소 (2026-08-22)** — §3·§7.11 반영 |
| **U-22** | **번역·ASR 모델과 실행 방식(로컬/원격) 선택** | **§7.11은 어댑터 경계만 정의. 선택은 측정 후** |

전체 목록: [`DECISIONS.md`](DECISIONS.md)
