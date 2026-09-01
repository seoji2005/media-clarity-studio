# TASK-029 — 자막 spine 실행 계약 정본화

| 항목 | 값 |
|---|---|
| **ID** | TASK-029 |
| **Owner** | Claude Code 구현 세션 |
| **Reviewer** | Lean Root Orchestrator — 구현 세션과 분리된 고정 HEAD Gate H 검토 |
| **Phase** | Phase 1a / subtitle data spine |
| **Status** | `In review` |
| **구현 상태** | **`Implemented — awaiting fixed HEAD review`** — 구현 세션 자기 승인 없음 |
| **구현 기준 main** | `5264f6bec469ae741e8c99d8d5d150cf78e2b76f` |
| **구현 브랜치** | `claude/task-029-subtitle-spine-contracts` |
| **위험 등급** | **Gate H** — 데이터 구조·파일 형식·교차 문서 참조·원본 증거 계보 |
| **계약 기준 main** | `6c71867b4c920c8550edc4eadc1f3b7f4ab5a3a9` |
| **선행** | TASK-006 Done, TASK-022 Done, TASK-028 Done |
| **차단 질문** | 없음. U-18·U-19·U-22와 의존성·모델 반입 gate는 이 TASK의 비범위로 유지 |

## 0. 제품 오너가 이 계약 PR 승인으로 받아들이는 기술 결정

이 다섯 항목은 기존 pseudo-contract에 정답이 없었다. 계약 PR의 고정 HEAD 승인은 다음 선택을
명시적으로 받아들이는 것이며, 실제 모델·품질 수치·외부 비용을 승인하는 것은 아니다.

1. `SpeechSegment/v1` schema root는 단일 segment이고 교차 참조는 ordered document set validator가 검사한다.
2. raw `Transcript/v1`은 immutable ASR evidence이며 forced alignment는 후속 별도 artifact다.
3. text offset은 exact stored text의 Unicode scalar 반개구간이다. language gap과 explicit `und`
   span은 모두 unknown+review로 남기며, 둘 중 어느 표현도 검수 의무를 우회하지 않는다.
4. confidence는 의미·출처를 결박하고 calibrated probability만 `[0,1]`로 해석한다.
5. translation split/merge와 subtitle cue는 fragment-level upstream lineage를 항상 보존한다.

이 선택 중 하나라도 제품 오너가 수용하지 않으면 구현을 시작하지 않고 TASK를 `Blocked`로 둔다.

## 1. 목표와 판정

현재 `SpeechSegment/v1`, `Transcript/v1`, `AdapterCapabilityReport/v1`,
`TranslatedTranscript/v1`, `TranslationCapabilityReport`, `SubtitleDocument/v1`은
`docs/ARCHITECTURE.md`의 제안형 pseudo-contract뿐이다. 저장소는 schema 파일이 문서와 다르면
schema가 정답이라고 규정하지만, 이 계약에는 정답 파일이 없다.

이 TASK는 실제 모델보다 먼저 자막 경로의 기계 정본을 만든다.

완료 시 다음이 존재해야 한다.

1. ASR 입력 구간, 원문 ASR 증거, 번역 결과와 표시 cue를 분리한 JSON Schema
2. schema만으로 표현할 수 없는 참조·시간·문자축·capability 불변식의 표준 라이브러리 validator
3. 정상·위반 fixture와 필수 mutation을 직접 잡는 테스트
4. 단일 검증 진입점 `make verify-task-029`
5. schema와 기존 pseudo-contract의 차이를 숨기지 않는 migration note

이 TASK는 WER·번역 품질·RTF·VRAM·사람 수정시간을 개선하거나 측정하지 않는다.
계약 검증을 제품 성능 개선으로 보고하지 않는다.

## 2. 지켜야 할 계층과 불변식

다음 계층은 유지한다.

```
원본 SpeechSegment
  → immutable ASR evidence Transcript
  → canonical utterance (후속 TASK)
  → TranslatedTranscript
  → SubtitleDocument display cue
  → QC (후속 TASK)
  → export
```

- `Transcript/v1`은 **ASR이 직접 낸 원문 증거**다. 번역·사람 교정·forced alignment가
  이 문서를 덮어쓰지 않는다.
- forced alignment 결과는 후속 별도 artifact다. TASK-029에서 그 schema나 producer를 만들지 않는다.
- `TranslatedTranscript/v1`은 입력 원문을 참조·보존하며 원문을 대체하지 않는다.
- `SubtitleDocument/v1`은 표시 단위로 재분할할 수 있지만 upstream lineage를 잃지 않는다.
- source/target 축이 바뀌거나 비-`ko` target이 성공 산출물로 승격되면 계약 실패다.
- 없는 timing·confidence·LID·alignment를 기본값으로 채우지 않는다.
- 다른 `stream_id`끼리의 동시 cue는 정상이다. 같은 stream 안의 시간 겹침만 구조 오류다.

## 3. 기계 정본 파일

다음 다섯 파일을 추가한다.

- `schemas/speech-segment-v1.schema.json`
- `schemas/transcript-v1.schema.json`
- `schemas/adapter-capability-report-v1.schema.json`
- `schemas/translated-transcript-v1.schema.json`
- `schemas/subtitle-document-v1.schema.json`

`TranslationCapabilityReport`는
`translated-transcript-v1.schema.json#/$defs/TranslationCapabilityReport`에 **한 번만** 정의한다.
다른 schema나 Python 상수에 enum·필드 집합을 복제하지 않는다.

모든 root schema는 다음을 지킨다.

- JSON Schema Draft 2020-12 선언과 파일명에 맞는 안정 `$id`
- `schema_version: "1.0.0"`
- production 객체의 `additionalProperties: false`
- 공통 식별자·시간·`ArtifactRef`는 `common-v1.schema.json` 상대 `$ref` 재사용
- `schema_core.py`의 현재 `SUPPORTED_KEYWORDS` 안에서만 작성

`oneOf`, `anyOf`, `allOf`, `if/then/else`, `contains`, custom format 추가가 필요해 보이면
schema_core를 확장하지 말고 §8의 domain validator로 옮긴다.

## 4. 계약별 필수 의미

### 4.1 `SpeechSegment/v1`

최소 다음 의미를 고정한다.

schema root의 직렬화 단위는 **SpeechSegment 단일 객체**다. concurrent 참조와 ID 유일성은
domain validator가 같은 실행의 ordered segment 집합을 받아 검사한다. 별도 collection envelope나
비공식 aggregate 형식을 이 TASK에서 만들지 않는다.

- `segment_id`, `timebase_ref`, `[start_seconds, end_seconds)`, `audio_ref`
- `stream_id`, `concurrent_stream_ids`, `overlap_kind`, `separation_method`
- 원본 오디오의 `source_track_index`와 선택 `source_channel_index`
- `channel_semantics: independent | mixed | unknown`
- 선택 `speaker_label`, 처리 chain과 provenance

규칙:

1. 시간은 `timebase_ref`가 가리키는 **원본 source 시간축**이다. clip-local offset을 가장하지 않는다.
   `audio_ref`는 실제 ASR에 공급할 sample data를 가리키며, segment clip이면 추출 chain을 provenance에 남긴다.
2. `end_seconds > start_seconds >= 0`이고 모든 값은 finite다.
3. `separation_method="channel"`은 `source_channel_index`가 있고
   `channel_semantics="independent"`일 때만 허용한다. 일반 stereo mix를 두 화자로 간주하지 않는다.
4. `separation_method="none"`이면 source channel만으로 별도 화자를 주장하지 않는다.
5. concurrent 참조는 존재하는 다른 stream이고 실제 시간이 겹쳐야 하며 자기 자신을 참조할 수 없다.
   겹침을 선언한 두 stream의 참조는 상호 대칭이어야 한다.
6. `speech_confidence`와 `speaker_confidence`는 선택이다. 있으면 각각
   `speech_confidence_semantics`, `speaker_confidence_semantics`에
   `calibrated_probability | model_score | provider_opaque`를 함께 기록한다.
   지원되지 않는 값을 1.0으로 채우지 않는다.
7. `calibrated_probability`만 `[0,1]`을 강제한다. `model_score`와 `provider_opaque`는 finite
   provider-native 값이며 확률처럼 정규화하거나 서로 비교하지 않는다.

### 4.2 `Transcript/v1` — immutable ASR evidence

최소 다음 의미를 고정한다.

- `timebase_ref`, stream과 segment의 안정 ID
- 각 ASR segment의 `source_speech_segment_ids` — 존재하는 입력 구간 참조
- 각 ASR segment의 `[start_seconds, end_seconds)` — source timebase의 원문 증거 경계
- ASR이 직접 낸 exact `text`
- 선택 token text·ASR timing·confidence
- 선택 n-best `alternatives[]`와 각 대안의 provider-native score
- 선택 `language_spans`, 선택 파생 `dominant_language`
- 실행별 `feature_status`:
  `produced | not_requested | no_result | unsupported`
- `capability_report_ref`가 아니라 **실행 당시 report의 immutable snapshot**
- adapter·params·seed provenance

규칙:

1. token timing은 ASR이 직접 보고한 값만 담는다. forced alignment 값을 raw Transcript에 합치지 않는다.
   Transcript `segment_id`는 ASR hypothesis ID이며 SpeechSegment ID와 같다고 가정하지 않는다.
   split/merge lineage는 `source_speech_segment_ids`로만 표현한다.
2. ASR segment 시간은 참조한 입력 SpeechSegment 시간 범위의 합집합 안에 있어야 한다.
   다른 stream의 입력을 한 segment lineage로 섞지 않는다.
3. token의 start/end는 둘 다 있거나 둘 다 없어야 한다. 있으면 segment 시간 범위 안에서
   시간순·비역전이어야 한다.
4. 문자 offset 단위는 exact stored `text`의 **Unicode scalar value index**다.
   UTF-8 byte, UTF-16 code unit, grapheme cluster offset과 섞지 않는다.
5. lone surrogate가 있는 text는 안정적인 scalar offset을 만들 수 없으므로 계약 실패다.
6. `language_spans`는 `char_start` 오름차순, 비중첩이다. gap은 허용하되 평가에서 `unknown`으로
   투영하고 segment의 `needs_review=true`, `review_reasons[]`에 `language_unknown`을 남긴다.
   producer는 모르는 범위를 `language="und"` span으로 명시할 수 있지만 이 경우에도 동일한
   review 상태가 필수다. gap을 `und`로 바꿔 검수를 우회할 수 없다.
7. `switch_kind`는 **그 span의 `char_start`로 들어오는 경계**를 설명한다. 첫 span에는 생략하고,
   이후 span에는 `inter_sentential | intra_sentential | unknown` 중 하나가 필수다.
8. `supports_language_id=false`이면 `language_spans`와 `dominant_language`를 만들지 않는다.
   지원하지만 이번 실행에서 결과를 얻지 못하면 §4.3의 `feature_status="no_result"`로 구분한다.
9. `supports_intra_sentential_lid=false`이면 `switch_kind="intra_sentential"` span을 만들 수 없다.
   inter-sentential span 여러 개는 허용한다.
10. gap 또는 `und` 범위가 하나라도 있으면 `dominant_language`를 생략한다. 전 범위가 알려진 언어
   span으로 덮였을 때만 spans 길이 합이 가장 큰 언어를 기록하고, 동률은 첫 span의 언어로 결정한다.
11. segment/token/LID confidence는 capability가 지원한다고 보고하고 대응 semantics가 `none`이 아닐
   때만 존재할 수 있다.
12. `token_unit: word | subword | character | provider_token`을 기록한다. token timing이 있으면
   capability report의 지원 timing unit과 일치해야 한다.
13. ASR segment의 `speaker_label`에는 `speaker_label_source: input | adapter`가 함께 있어야 한다.
   input/channel에서 복사한 label은 diarization 결과로 세지 않는다.
14. `is_low_confidence`는 numeric confidence의 존재를 뜻하지 않는다. 다른 review signal로 true가 될 수
   있지만 그 경우 `review_reasons[]`와 provenance를 남긴다.

Transcript segment의 review 필드는 `needs_review`와 중복 없는 `review_reasons[]`이며,
core enum은 `low_confidence | language_unknown | language_switch | timing_uncertain |
speaker_uncertain | overlap | other`다. `other`이면 별도 `review_extension_id`가 `x-` 접두사의
안정 ID여야 한다. reasons가 비어 있음과 `needs_review=false`, non-empty와 `true`는 서로 동치다.

`feature_status`는 임의 key/value map이 아니라 다음 일곱 key가 모두 있는 닫힌 객체다.

| key | capability 축 | `produced`일 때 필요한 결과 |
|---|---|---|
| `token_timing` | 지원 `token_timing_units` | 하나 이상의 token에 start/end 쌍 |
| `token_confidence` | `token_confidence_semantics != "none"` | 하나 이상의 token confidence |
| `segment_confidence` | `segment_confidence_semantics != "none"` | 하나 이상의 ASR segment confidence |
| `language_id` | `supports_language_id` | 하나 이상의 `language_spans` 또는 `dominant_language` |
| `language_confidence` | `language_confidence_semantics != "none"` | 하나 이상의 language span confidence |
| `speaker_diarization` | `supports_diarization` | 하나 이상의 adapter-produced speaker label |
| `nbest` | `supports_nbest` | 하나 이상의 ASR segment에 non-empty `alternatives[]` |

각 key는 §4.3의 `produced | not_requested | no_result | unsupported` 결박을 독립적으로 지킨다.
independent channel의 `stream_id`·speaker attribution은 adapter diarization 결과가 아니므로
`speaker_diarization="produced"`의 근거로 세지 않는다.

### 4.3 `AdapterCapabilityReport/v1`

실행 결과와 독립적으로 adapter의 실제 능력을 다음 축으로 보고한다.

- adapter ID/version과 지원 언어
- 지원 token timing unit과 `supports_word_timing`, token confidence, segment confidence
- segment LID, intra-sentential LID와 LID confidence
- diarization, independent-channel input, overlap streams
- `supports_nbest`와 `nbest_score_semantics`:
  `calibrated_probability | model_score | provider_opaque | none`
- candidate language restriction과 선택 최대 후보 수
- term injection mode 목록: `prompt | phrase_list | custom_vocabulary`; 미지원이면 빈 배열
- `network_requirement: none | optional | required`
- `requires_gpu`
- `determinism_tier: T1 | T2 | T3`
- confidence 축별 semantics:
  `calibrated_probability | model_score | provider_opaque | none`

규칙:

- 지원 언어는 항상 language tag 문자열 배열이다. 문자열 단독 `"unknown"`을 허용하지 않고,
  알 수 없으면 빈 배열과 명시적 limitation을 쓴다.
- 이 TASK의 stdlib 검증 범위는 primary subtag가 소문자 ASCII 2~8자이고 후속 subtag가
  ASCII 영숫자 1~8자인 `^[a-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$` subset이다. 전체 BCP-47 ABNF나
  IANA registry 유효성을 주장하지 않으며, 제품 불변식인 target exact-`ko`와 `und` 의미는
  domain validator가 추가로 강제한다.
- `supports_word_timing`은 timing unit 목록에 `word`가 있을 때만 true다.
- Transcript의 실행 feature status는 capability snapshot에 결박한다.
- capability가 unsupported이면 실행 feature status도 `unsupported`이고 대응 결과 필드는 없어야 한다.
- capability가 supported여도 `not_requested`·`no_result`이면 대응 결과 필드를 만들지 않는다.
- `produced`이면 해당 결과 필드가 실제로 존재해야 한다.
- confidence semantics가 `none`이면 대응 confidence 필드는 없어야 한다.
- `supports_nbest=false`이면 `feature_status.nbest="unsupported"`이고 `alternatives`는 없어야 한다.
  true여도 `not_requested | no_result`이면 alternatives를 만들지 않고, `produced`이면 실제 대안이 있다.
  alternative score는 `nbest_score_semantics != "none"`일 때만 존재하며 calibrated probability만 `[0,1]`이다.
- 모든 confidence 축에서 `calibrated_probability`만 `[0,1]`을 강제한다.
  `model_score`·`provider_opaque`는 finite provider-native 값이며 adapter 간 확률처럼 비교하지 않는다.
- 지원하지 않는 기능을 fallback으로 합성했으면 adapter 능력으로 보고하지 않는다.
- `network_requirement="required"`를 표현할 수는 있지만 완전 로컬 기본 profile에 채택했다는 뜻은 아니다.
- term payload, candidate language 실제 값과 model 선택은 이 TASK에서 정하지 않는다.

### 4.4 `TranslatedTranscript/v1`

최소 다음 의미를 고정한다.

- 입력 `source_transcript` ArtifactRef와 동일 `timebase_ref`
- `target_language`는 현재 성공 계약에서 정확히 `ko`
- 원문과 동일한 stream lineage
- 번역 segment ID, exact source fragment, target text, alignment kind
- `coverage_status: complete | partial`과 partial일 때 명시적 uncovered source fragment
- 선택 confidence와 review 상태
- alignment/confidence의 실행별 `feature_status`
- `TranslationCapabilityReport` snapshot과 provenance

`TranslationCapabilityReport`는 다음 닫힌 field set을 갖는다.

- 필수: `adapter_id`, `adapter_version`, `supported_source_languages[]`,
  `supported_target_languages[]`, `supports_segment_alignment`,
  `supports_document_context`, `supports_code_switching_input`,
  `translation_confidence_semantics`, `network_requirement`, `requires_gpu`,
  `determinism_tier`, `limitations[]`
- `translation_confidence_semantics`:
  `calibrated_probability | model_score | provider_opaque | none`
- language tag는 §4.3의 구조 subset을 사용한다. 성공 결과를 낼 capability snapshot의
  `supported_target_languages`에는 exact `ko`가 있어야 한다.

각 translation segment는 `alignment_evidence_source: adapter | orchestrator`를 필수로 기록한다.
`adapter`는 모델이 직접 보고한 semantic alignment, `orchestrator`는 실제 요청 fragment 계보만
뜻한다. 번역 문서의 `feature_status`도 임의 map이 아니라 `segment_alignment`,
`translation_confidence` 두 key가 모두 있는 닫힌 객체다. `segment_alignment="produced"`이면
하나 이상의 segment가 `alignment_evidence_source="adapter"`여야 한다. 다만 값이
`unsupported | not_requested | no_result`여도 orchestrator의 실제 입력 source fragment lineage는
항상 남긴다. `translation_confidence`는 semantics가 `none`이면 `unsupported`이고 confidence가
없어야 하며, `produced`이면 confidence가 실제로 있어야 한다. calibrated probability만 `[0,1]`이다.

각 source fragment는 최소 다음을 담는다.

- `source_segment_id`
- `char_start`, `char_end` — 원문 segment exact text의 Unicode scalar offset
- `source_text` — 위 범위의 exact substring

규칙:

1. 모든 source fragment는 존재하는 Transcript segment를 참조하고 `text`가 exact substring과 같아야 한다.
2. `alignment_kind="one_to_one"`은 한 source segment 전체를 참조한다.
3. `merged`는 원문 순서의 서로 다른 source segment를 2개 이상 참조한다.
4. `split`은 한 source segment의 non-empty strict subrange를 참조한다. 같은 source를 나눈 sibling은
   범위가 겹치지 않고 원문 순서여야 한다.
5. `dropped`도 source fragment를 보존하고 `target_text`는 빈 문자열이며
   `review_reasons[]`에 `untranslated_span`을 남긴다.
6. `unknown`은 알려진 실행 입력 fragment를 보존하되 더 강한 alignment 주장을 하지 않는다.
7. source fragment 없이 성공 번역 segment를 만들 수 없다. adapter가 정렬을 보고하지 못해도
   orchestrator가 실제로 공급한 입력 범위는 lineage로 남긴다.
   `TranslationCapabilityReport.supports_segment_alignment`는 model이 semantic alignment를 직접
   보고하는 능력이며 이 lineage 보존 의무를 끄지 않는다.
8. `translated/dropped source fragments + uncovered_source_fragments`는 `complete`와 `partial` 모두에서
   모든 non-empty source scalar range를 원문 순서대로 정확히 한 번 partition해야 한다. covered와
   uncovered 사이에도 gap·중복·겹침이 있을 수 없다. `complete`는 uncovered가 비어 있을 때와 동치고,
   `partial`은 uncovered가 하나 이상일 때와 동치다. uncovered도 source segment ID, scalar start/end,
   exact substring, 안정 reason과 `needs_review=true`를 반드시 남긴다.
9. confidence 미지원이면 값을 생략하며 1.0을 채우지 않는다.
10. source/target text를 하나의 필드로 덮어쓰거나 source text를 target으로 복사해 성공처럼 보고하지 않는다.

번역 segment와 uncovered fragment의 review 필드는 `needs_review`와 중복 없는
`review_reasons[]`이다. core enum은 `low_confidence | untranslated_span | alignment_uncertain |
source_ambiguous | other`이며 `other` 확장 규칙과 boolean/array 동치는 Transcript와 같다.

### 4.5 `SubtitleDocument/v1`

최소 다음 의미를 고정한다.

- `text_axis: source | target`
- target 문서의 `target_language` — 현재 성공 계약에서 정확히 `ko`
- 직접 입력 문서 ArtifactRef와 target일 때 원본 Transcript ArtifactRef
- cue ID, stream ID, 시간, lines, lineage
- concurrent cue, overlap, needs-review와 이유
- `style_profile_id`, `style_profile_version`, 실행 당시 resolved style 값 snapshot
- cue ID와 reason을 포함한 구조화된 cue별 `unsupported_features`
- provenance

lineage 규칙:

- 각 cue의 `lineage_fragments[]` 항목은 `line_index`, `input_segment_id`, Unicode scalar
  `char_start`, `char_end`, `text`를 필수로 가진다. 같은 line의 항목을 순서대로 결합한 문자열은
  `lines[line_index]`와 exact scalar sequence로 같아야 한다.
- 원문의 whitespace를 실제 줄 경계로 대체한 경우 `line_break_whitespace[]`가
  `after_line_index`, `input_segment_id`, `char_start`, `char_end`, exact `text`를 기록한다.
  허용 whitespace scalar 집합은 U+0009–000D, U+0020, U+0085, U+00A0, U+1680,
  U+2000–U+200A, U+2028, U+2029, U+202F, U+205F, U+3000으로 고정한다.
- source cue의 범위와 exact substring은 Transcript segment `text` 기준이다.
- target cue의 범위와 exact substring은 TranslatedTranscript segment `target_text` 기준이며,
  해당 translation segment의 source fragments를 통해 원문까지 추적 가능해야 한다.
- 한 입력 segment가 여러 cue로 split되거나 여러 입력 segment가 한 cue로 merge될 때도 같은 입력
  segment의 visible/line-break fragment는 원문 순서·비중첩이고 범위와 `text`가 exact substring이어야 한다.
- cue 경계와 line 경계를 통틀어 direct input의 모든 scalar range는 visible fragment 또는 explicit
  `line_break_whitespace`로 정확히 한 번 덮여야 한다. line break는 0개 이상의 위 고정 whitespace만
  layout 경계로 옮길 수 있으며, 모든 non-whitespace scalar는 `lines[]`에 원문 순서로 정확히 한 번
  보존한다. 공백 없는 일본어 줄 분할도 인접 visible range로 정상 표현한다.
- 평가용 `raw_cue_text=lines.join(U+0020 SPACE)`와 `canonical_cue_text=norm-v1(raw_cue_text)`는
  원본 lineage text와 별도 표현이다. U-19가 미정인 이 TASK의 validator가 정규화 규칙을 새로 만들거나
  인공 U+0020 구분자를 upstream 원문 증거라고 주장하지 않는다.
- 존재하지 않는 segment/cue 참조는 계약 실패다.

시간·순서 규칙:

1. 모든 cue는 positive duration이고 배열 canonical order는
   `(start_seconds, end_seconds, stream_id, cue_id)` 오름차순이다.
2. 같은 `stream_id`의 cue는 겹치지 않는다.
3. 다른 stream의 cue는 정상적으로 겹칠 수 있다.
4. `concurrent_cue_ids`는 존재하는 다른 cue이고 실제 시간이 겹치며 상호 대칭이어야 한다.
5. `overlap_kind="none"`인 cue는 concurrent cue를 선언하지 않는다.

축 규칙:

- `text_axis="target"`이면 직접 입력은 TranslatedTranscript이고 source Transcript ref가 필수다.
- `text_axis="target"`이면 `target_language="ko"`가 필수다.
- `text_axis="source"`이면 번역 segment lineage를 가장할 수 없다.
- U-18이 미정이므로 CPS·줄 길이·최소/최대 표시시간 숫자는 schema에 박지 않는다.
  `resolved_style`은 다음 필드가 모두 있는 닫힌 snapshot이며 기본 숫자를 정하지 않는다:
  `max_chars_per_line`(integer ≥ 1), `max_lines`(integer ≥ 1), `max_cps`(number > 0),
  `min_duration_seconds`(number ≥ 0), `max_duration_seconds`(number > 0),
  `min_gap_seconds`(number ≥ 0), `line_break_policy`(`semantic | balanced | source_preserving`),
  `language_overrides`(language-tag key별 동일 수치 필드의 닫힌 partial override).
  domain validator는 `max_duration_seconds > min_duration_seconds`를 강제한다.
- `unsupported_features[]` record는 `cue_id`,
  `feature_kind`(`ruby | positioning | font_style | speaker_placement | karaoke |
  bidirectional_layout | vertical_text | other`), `feature_identifier`,
  `reason_code`(`not_representable | profile_disallowed | exporter_unsupported |
  source_ambiguous | other`), `action`(`dropped | flattened | approximated | review_required`)을 필수로 가진다.
  `feature_kind` 또는 `reason_code`가 `other`이면 `feature_identifier`는 `x-` 접두사의 안정 확장 ID다.
  새 core 어휘는 schema version 변경으로 추가하며 자유문자 reason으로 core 의미를 바꾸지 않는다.
- cue의 review 필드는 `needs_review`와 중복 없는 `review_reasons[]`이며 core enum은
  `low_confidence | overlap | language_switch | timing_uncertain | format_violation |
  silence_adjacent | unsupported_feature | other`다. `other` 확장 규칙과 boolean/array 동치는 같다.
- `unsupported_features`와 `review_reasons`는 조용한 정보 유실을 막는 기록이다. 실제 QC 정책은 후속 TASK다.

## 5. 기존 문서와의 명시적 migration

`docs/ARCHITECTURE.md`의 해당 pseudo-contract를 schema 정본 링크와 일치시킨다.
기존 산문을 조용히 삭제하지 않고 최소 다음 차이를 migration note로 기록한다.

| 기존 pseudo-contract | TASK-029 정본 |
|---|---|
| SpeechSegment confidence가 사실상 필수 | 미지원값 조작 금지를 위해 선택 + semantics 결박 |
| channel 선택의 출처·독립성 불명확 | track/channel index와 independent/mixed/unknown 분리 |
| Transcript token timing의 출처 불명확 | raw ASR timing만 허용, forced alignment 별도 artifact |
| Transcript segment 경계가 명시되지 않음 | source timebase의 start/end와 입력 SpeechSegment lineage 필수 |
| 문자 offset 단위 불명확 | exact text의 Unicode scalar value index |
| language span gap·switch boundary 의미 불명확 | gap과 `und`는 모두 unknown+review; 둘이 있으면 dominant 생략; switch는 다음 span 진입 경계 |
| LID 미지원 fallback이 configured dominant language를 결과처럼 기록 | capability false이면 spans·dominant 모두 부재; 후보 언어는 실행 options/provenance의 후속 계약 |
| ASR n-best/alternative score 의미가 불명확 | `supports_nbest`, score semantics, 실행 status로 결박 |
| capability에 channel·term·candidate·network 축 누락 | capability report에 명시 |
| 번역 document context·code-switching capability | 기존 두 boolean을 닫힌 report에 그대로 보존 |
| 번역 `source_segment_ids` 생략 fallback | 실제 입력 fragment lineage는 항상 보존 |
| `source_language_authority` literal 경로가 stream 계층을 누락하고 ASR 가설을 정답처럼 표현 | literal 제거; source Transcript ref와 segment lineage가 authority |
| merged/split에서 source text 범위 불명확 | exact source fragment + scalar offset |
| Subtitle cue upstream lineage 불명확 | axis별 exact scalar fragment lineage와 canonical cue text 동치 필수 |
| target Subtitle에 언어가 없음 | target 문서는 `target_language="ko"` 필수 |
| document-level unsupported feature로 cue 비율 계산 불가 | cue ID와 reason이 있는 구조형 record |
| inline style 숫자가 U-18과 충돌 가능 | profile ID/version+resolved snapshot, schema default 숫자는 없음 |

`docs/EVALS.md`의 offset 규정도 좁게 정합화한다. **두 text space를 하나로 취급하지 않는다** —
raw Transcript의 offset은 exact segment `text` 기준이고, SubtitleDocument의 offset은 `lines[]`를
결합한 `canonical_cue_text` 기준이다.

> **문자 offset을 시간으로 옮기는 규칙은 이 TASK에 없다 (§17.7, REVIEW-026 D-04).**
> 이 절의 초판은 "raw Transcript는 ASR segment/token timing을 기준으로 **투영**한다"고 썼는데,
> `tokens[]`는 선택 필드이고 문자 offset이 없으며 token 문자열이 segment `text`를 정확히 한 번
> 분할한다는 계약도 없다. 위 문장은 offset이 **어느 text space에 속하는가**를 정하는 규칙일
> 뿐, 시간 투영을 승인하는 규칙이 아니다.
> **§19 이후:** EVALS §4.5(a)의 공식 LID 정확도 채점 자체가 미지원이다 (ADR-0029).
> segment 단위 귀속도 채점 규칙으로 승인하지 않는다.

schema와 문서가 다르면 schema가 정답이다. 단, 구현자는 모순을 임의 선택해 schema에 숨기지 않는다.
이 표로 해결되지 않는 교차 계약 모순을 발견하면 구현을 중단하고 제품 오너에게 올린다.

## 6. 산출물과 허용 파일

코드 구현 PR은 다음 파일만 생성·수정할 수 있다.

- §3의 신규 schema 5개
- 신규 `src/media_clarity/subtitle_contracts.py`
- 신규 `tests/test_subtitle_contracts.py`
- 신규 `tests/fixtures/subtitle_contracts/` 아래 JSON fixture
- 신규 `scripts/verify_task_029.py` 또는 같은 목적의 단일 fixture runner
- `Makefile`의 TASK-029 target 추가
- `docs/ARCHITECTURE.md`의 해당 계약 링크·정합화·migration note
- `docs/EVALS.md`의 Transcript raw-text offset과 Subtitle canonical-cue-text 구분 문구
- 이 TASK 파일의 구현 기록·Status
- `STATUS.md`의 TASK-029 행과 마지막 갱신 날짜 (§6.1)

기존 `common-v1.schema.json`, job/eval schema, `schema_core.py`, runtime/cache 구현은 수정하지 않는다.
공통 타입 결함 때문에 수정이 필요해 보이면 범위를 넓히지 말고 중단해 보고한다.

## 7. 범위 밖

- 실제 ASR·번역·VAD·diarization·source separation·forced alignment adapter
- 모델 선정, 가중치, 외부 corpus, 다운로드, network access
- `requirements*`, `pyproject.toml`, `package.json` 등 신규 외부 의존성
- CorrectionLedger, canonical replay, TermBundle, WorkUnitManifest
- subtitle QC 규칙 구현과 U-18 실제 수치
- `norm-v1`과 U-19 확정
- OCR/VLM, RegionMask, 시각 재구성, UI
- publish profile과 실제 SRT/MKV/MP4 producer 변경
- `CACHE_KEY_FIELDS`, `StageSpec`, job fingerprint, artifact store 변경
- schema_core의 범용 재설계나 Draft 2020-12 전체 지원 주장

## 8. domain validator와 안정 오류

JSON Schema로 표현하기 어려운 조건은 `subtitle_contracts.py`에 둔다. 일반 schema 해석을 복제하지 않고
`SchemaSet`·`SchemaValidator`·`Finding`·strict JSON loader를 재사용한다.

최소 공개 검증 경계:

- SpeechSegment 집합 검증
- Transcript + 입력 SpeechSegment 집합 검증
- TranslatedTranscript + source Transcript 검증
- SubtitleDocument + source/translated document 검증
- capability snapshot과 결과 필드의 일치 검증

finding은 기존처럼 결정적 `(location, code, message)` 정렬을 사용한다. location은 실제 입력에서
해석 가능한 **선행 `/` 없는** JSON Pointer 형식이며, message만으로 판정하지 않는다.

최소 안정 error code:

| code | 의미 |
|---|---|
| `E_SCHEMA` | root schema·필수 필드·enum·닫힌 객체 위반 |
| `E_TIME_RANGE` | 음수·0 duration·역전·부모 범위 밖 timestamp |
| `E_TIME_ORDER` | token/cue/source fragment 순서 위반 |
| `E_CHANNEL_SEMANTICS` | channel method와 channel 출처·독립성 모순 |
| `E_STREAM_REF` | 없는/self/non-overlap/asymmetric concurrent stream 참조 |
| `E_OFFSET_RANGE` | scalar 범위 밖·빈 범위 offset |
| `E_OFFSET_ORDER` | language/source fragment offset 순서 역전·겹침 |
| `E_UNICODE_SCALAR` | lone surrogate로 scalar offset 정의 불가 |
| `E_LANGUAGE_GAP_REVIEW` | language span gap이 있는데 unknown review 상태 누락 |
| `E_CAPABILITY_MISMATCH` | capability false/none인데 대응 결과 필드 존재 |
| `E_CONFIDENCE` | confidence와 semantics 모순 |
| `E_SOURCE_REF` | 없는 SpeechSegment/Transcript/Translation segment 참조 |
| `E_SOURCE_TEXT` | source fragment text가 exact substring과 다름 |
| `E_SOURCE_COVERAGE` | complete/partial translation partition의 미신고 gap·중복·겹침·상태 모순 |
| `E_ALIGNMENT` | alignment kind와 source fragment 모양 불일치 |
| `E_TEXT_AXIS` | source/target document·lineage 축 교환 |
| `E_TARGET_LANGUAGE` | target 성공 산출물의 누락·비-`ko` 언어 |
| `E_CUE_ORDER` | cue canonical order 위반 |
| `E_CUE_OVERLAP` | 같은 stream cue 시간 겹침 |
| `E_CUE_REF` | 없는/self/non-overlap/asymmetric concurrent cue 참조 |
| `E_LINEAGE` | cue의 upstream fragment ID·범위·exact text·canonical text 동치 위반 |
| `E_REVIEW_STATE` | `needs_review`와 review reasons의 존재가 모순 |

같은 입력은 실행마다 같은 code·location 순서를 반환해야 한다.
finding message에는 source/target text, 절대 경로와 민감한 실제 값을 넣지 않는다.

### 8.1 세 축을 섞지 않는다 — 입력 오류 / schema 위반 / domain 불변식

REVIEW-026 R-02가 지적한 대로, "왜 거부됐는가"는 서로 다른 세 축이다. 하나로 뭉치면
소비자가 고칠 곳을 찾을 수 없다.

| 축 | 언제 | 어떻게 끝나는가 | 위 표의 code를 쓰나 |
|---|---|---|---|
| **입력 오류** | raw JSON 본문이 문서가 되기 **전에** 계약을 어겼다 — 구문 오류, 중복 key, `NaN`/`Infinity`, §18의 숫자 profile 위반 | `JsonInputError`. CLI는 `E_JSON <사유>`를 stderr로 내고 **exit 2**로 끝난다. traceback을 내지 않는다 | **아니다.** finding이 아니다 |
| **schema 위반** | 문서가 되었지만 정본 schema를 어겼다 | `E_SCHEMA` finding. 그 문서는 **의미 검사를 건너뛴다** (깨진 구조 위에 파생 오류를 쌓지 않는다) | `E_SCHEMA` |
| **domain 불변식** | schema는 통과했지만 계약이 금지한 조합이다 | `E_TIME_RANGE`·`E_OFFSET_RANGE`·`E_CONFIDENCE` 등 위 표의 code | 그 밖의 21개 |

그래서 **같은 field라도 schema가 먼저 잡으면 `E_SCHEMA`이고, schema를 통과한 뒤 domain이
잡으면 범위 code**다. 예: `start_seconds: -1`은 schema의 `minimum: 0`이 먼저 잡아 `E_SCHEMA`이고,
`start_seconds: 10**400`은 schema 범위를 통과하므로(상한이 없다) domain의 `E_TIME_RANGE`가 잡는다.
이 순서는 우연이 아니라 §8이 정한 것이며 fixture와 mutation이 그대로 고정한다.

문서 집합 root 자체가 객체가 아니면(`[]`·`null`·정수) `E_SCHEMA @ ""`다. 호출자 신뢰로 두지
않는다 (REVIEW-026 R-02c).

### 8.2 finding location의 비식별화 계약

location은 **정본이 그 자리에서 선언한 고정 field 이름과 배열 index만** 담는다.

- 허용 판정은 **경로별**이다. 어떤 이름이 *다른* 위치의 정본 field라는 사실은 이 위치에서
  그 이름을 노출해도 된다는 근거가 아니다. 최상위 `uri`·`text`·`artifact_id`,
  `document_refs["speaker_label"]`은 각각 `""`와 `document_refs`로 접힌다.
- `patternProperties`가 여는 자리(`resolved_style.language_overrides`)의 key는 **전부** 부모로
  접는다. BCP-47·private-use 모양(`en-John-Doe`·`en-x-secret`)에도 임의 문자열을 넣을 수 있으므로
  **모양은 비식별화 근거가 아니다** (REVIEW-026 R-01).
- 이 계약은 schema finding, domain finding, container 조기 반환, **공개 `check_*` 진입점**에
  모두 같게 적용된다. `validate_documents()`만 접으면 공개 함수를 직접 부른 소비자에게는
  raw key가 그대로 간다.
- 감사의 누출 스캔은 production 접기 함수를 재사용하지 않고 **독립 oracle**(정본에서 펼친 경로
  패턴 집합 + 입력 해석 가능성)로 판정하며, 동적 mapping key도 민감 후보로 수집한다.

## 9. fixture와 mutation 요구

`tests/fixtures/subtitle_contracts/k-01.json`부터 독립 synthetic 문서 묶음을 둔다.
fixture expected는 message가 아니라 exact `code + location` pair를 고정한다.

정상 fixture는 최소 다음 경로를 각각 포함한다.

1. JA/EN 문장 내 전환, explicit `und`, gap→unknown+review를 각각 포함하고 gap/`und`에서
   `dominant_language`를 생략한 raw Transcript
2. timing/confidence/LID를 전부 지원하지 않아 필드가 정직하게 생략된 Transcript
3. 실제 independent channel과 서로 다른 stream의 동시 segment/cue
4. one-to-one, merged, split, dropped, unknown 번역 lineage
5. emoji·combining mark가 있는 source-axis·target-axis SubtitleDocument와 정확한 scalar offset
6. 다른 stream cue overlap은 통과하고 같은 stream overlap은 실패하는 쌍
7. 공백 없는 일본어 `日本語 → ["日", "本語"]` line split과 source 공백을 explicit
   `line_break_whitespace`로 옮긴 영어 split

최소 다음 mutation은 관련 검사를 하나씩 무력화했을 때 반드시 잡혀야 한다.

- source/target axis 교환
- `target_language`를 비-`ko`로 변경
- scalar 범위를 벗어나거나 겹치는 language span, gap review 누락
- explicit `und`의 unknown review 누락, gap/`und`가 있는데 `dominant_language` 추가
- emoji 앞뒤 offset을 UTF-16 code unit 기준으로 바꾸는 mutation
- lone surrogate text 허용
- 음수·0 duration·역전 timestamp
- segment 밖 token timestamp와 token 순서 역전
- 미지원 confidence를 1.0으로 추가
- capability false인데 timing/confidence/LID/diarization 관련 결과 필드 추가
- copied input/channel speaker label을 adapter-produced diarization으로 가장
- orchestrator source lineage를 adapter-produced semantic alignment로 가장
- `supports_nbest=false`인데 alternatives 추가 또는 score semantics가 `none`인데 score 추가
- 존재하지 않는 SpeechSegment/source segment/translation segment 참조
- source fragment text 한 글자 변경
- complete translation의 source coverage gap·duplicate coverage
- partial translation의 미신고 gap, duplicate uncovered, covered/uncovered overlap,
  empty/non-empty uncovered와 coverage status 불일치
- one-to-one/merged/split/dropped의 fragment cardinality·범위 위반
- channel method인데 mixed/unknown channel로 변경
- concurrent stream/cue의 self·dangling·non-overlap·비대칭 참조
- cue canonical order 위반
- cue lineage fragment의 line index·범위·exact text 변경, split/merge fragment 순서·겹침 위반,
  line text와 visible fragments 불일치, non-whitespace 누락·중복, 허용 집합 밖 문자를
  `line_break_whitespace`로 이동
- 같은 stream cue overlap 허용
- 다른 stream cue overlap을 잘못 거부
- style profile 기본 숫자를 schema에 하드코딩하거나 resolved snapshot을 누락
- review reason이 있는데 `needs_review=false`로 변경

mutation 감사는 다음 세 분모를 섞지 않고 각각 manifest와 결과를 기록한다.

1. **input mutants**: 위 목록의 각 단일 필드·관계 변형. 총수·기대 code/location·탐지수를 기록한다.
2. **schema mutants**: production schema의 `required`·`enum`·범위·닫힌 객체 방어를 임시 사본에서
   하나씩 약화. 총수·해당 sentinel fixture·탐지수를 기록한다.
3. **validator code mutants**: domain validator의 각 핵심 분기·비교를 저장소 밖 임시 사본에서
   하나씩 무력화. 총수·해당 sentinel test·탐지수를 기록한다.

각 mutant는 대응하는 **valid-case sentinel**도 함께 통과해야 한다. mutant가 결함 fixture를 잡더라도
정상 case를 잘못 거부하면 kill로 세지 않는다. 각 분모에서 `detected / total`, `SKIP` 수와 이유를
별도로 보고하며 필수 목록의 `SKIP`은 허용하지 않는다. schema 검사가 상위에서 같은 결함을 잡아
semantic 검사가 가려지면 보완 mutant/fixture로 domain 방어의 실제 의미를 증명한다.

## 10. 완료 조건과 측정 지표

1. 신규 정상 fixture와 위반 fixture가 기대한 code·location으로 100% 통과한다.
2. §9의 input/schema/validator-code 세 mutation 분류가 각각 `detected / total = 100%`,
   valid-case sentinel 통과 100%, 필수 `SKIP=0`이다. 미탐지·감사 불가는 병합 차단이다.
3. `make verify-task-029`가 신규 fixture, unit/mutation test와 기존 전체 `verify`를 포함해 exit 0이다.
4. 기존 355 tests와 TASK-006·022·028 smoke가 감소 없이 유지된다.
5. 신규 dependency/model/network access가 0이다.
6. 기존 schema와 `CACHE_KEY_FIELDS` canonical bytes가 변하지 않는다.
7. `schema_core.py`, artifact store, job runtime diff가 0이다.
8. pseudo-contract와 schema의 필드·enum 차이가 §5 migration note에 남는다.
9. unresolved cross-contract contradiction이 0이거나 명시적 blocker로 중단된다.

측정 지표:

- schema/semantic fixture pass rate: 100%
- input mutation kill rate: 100%, 필수 `SKIP=0`
- schema mutation kill rate + valid-case sentinel pass rate: 각각 100%, 필수 `SKIP=0`
- validator-code mutation kill rate + valid-case sentinel pass rate: 각각 100%, 필수 `SKIP=0`
- 기존 회귀: 355/355 이상, 감소 0
- 신규 dependency/model/network: 0
- 기존 job/artifact schema byte changes: 0
- unresolved contradiction: 0 또는 `Blocked`

기준선 rollback guard:

- `common-v1.schema.json` raw SHA-256:
  `0d00e20511e0585547b1e0be6211270d600bff7f6196e849aa258fde0f392f33`
- `common-v1.schema.json` canonical SHA-256:
  `e498654fa1d4a6eb0c2bb3d09b7d50e48a1e26b0b999598d1651884881681292`
- `job-v1.schema.json` raw SHA-256:
  `47a570efdb058dddb94228cba645d1432d675c910e5640f59e3dec5d0e395dab`
- `job-v1.schema.json` canonical SHA-256:
  `92f17a2284520b2523205ad685bfa4d23df087bcd7ee0d5f0cd4df4da3ba2e9e`

## 11. 검증 명령

Claude Code 구현 PR은 최소 다음을 직접 실행하고 실제 숫자를 기록한다.

```bash
make verify-task-029
make verify-task-028
make verify-task-006
make verify
git diff --check
git status --short
```

validator의 mutation 감사는 저장소 밖 임시 사본에서 수행한다. fixture·production schema·기존 테스트를
감사 편의를 위해 조용히 바꾸지 않는다.

## 12. rollback 조건

- schema가 source/target 축, 원본 불변, optional capability 규칙과 충돌하면 병합하지 않는다.
- schema_core 범용 재작성, cache key 변경, 외부 의존성 또는 실제 모델이 필요해지면 범위 초과로 중단한다.
- 고정 HEAD 검토에서 필수 mutation 미탐지나 silent source text loss가 재현되면 변경 요청이다.
- 병합 전 rollback은 PR을 병합하지 않는 것이다.
- 병합 뒤 결함은 신규 schema·domain validator·fixture·Makefile target·문서 정합화·TASK-029 상태·
  `STATUS.md` 상태 행을 한 묶음으로 일반 revert한다. 별도 revert가 불가피하면 같은 운영 변경에서
  TASK-029를 `Blocked`로, STATUS를 실제 미적용 상태로 즉시 정합화한다. 실제 producer가 없으므로
  데이터 migration을 만들지 않는다.

## 13. 인계 메모

- 구현 세션은 최신 `main`에서 `claude/task-029-subtitle-spine-contracts` 브랜치를 만든다.
- 첫 커밋 전에 이 파일과 `AGENTS.md`를 다시 읽고 파일 소유 범위를 확인한다.
- 구조 검증은 `schema_core.py`를 **수정하지 않고** 재사용한다.
- 시간·문자·lineage·capability 조건은 신규 domain validator가 담당한다.
- 실제 모델·의존성·network gate를 열지 않는다.
- 구현 완료 보고는 승인 요청이 아니다. Lean Root가 원격 고정 HEAD·diff·fixture·mutation·전체 회귀를
  독립 검증한 뒤 별도 판정을 낸다.

### Claude Code 실행 프롬프트

> `seoji2005/media-clarity-studio`의 최신 `main`에서 시작하세요. 먼저 `AGENTS.md`를 처음부터 끝까지
> 읽고, 이어서 `STATUS.md`, `docs/tasks/TASK-029.md`, `docs/PRODUCT_SPEC.md`,
> `docs/ARCHITECTURE.md`, `docs/EVALS.md`, `PLAN.md`, `docs/DECISIONS.md` 순서로 읽으세요.
> TASK-029의 Owner는 이 Claude Code 구현 세션 하나이며, 코드는 이 세션이 작성하고 Lean Root가
> 별도 고정 HEAD에서 검토합니다. `claude/task-029-subtitle-spine-contracts` 브랜치와 Draft PR을
> 만들고 TASK-029 §6의 파일만 수정하세요. §3~§5의 schema 정본, §8 domain validator,
> §9 fixture·mutation, §10 완료 조건을 그대로 구현하세요. `schema_core.py`, 기존 schema,
> artifact store, job runtime, cache key, 의존성·모델·network는 수정하지 마세요.
> 모순이나 범위 확장이 필요하면 임의로 선택하지 말고 구현을 중단해 `Blocked`로 보고하세요.
> 완료 전 §11 명령을 직접 실행하고 실제 test 수·fixture 수·mutation 결과·미검증 환경을 PR 본문과
> TASK 구현 기록에 남기세요. Ready 전환·병합·자기 승인은 하지 마세요.

---

## 14. 구현 기록 (Claude Code 구현 세션)

**상태: `Implemented — awaiting fixed HEAD review`.** 아래는 구현 세션의 주장이며 검증이 아니다.
판정은 Lean Root가 고정 HEAD에서 직접 재현한다 (`AGENTS.md` R10 / §3.5).
구현 세션은 자기 변경을 승인하지 않았고 병합·Ready 전환을 하지 않았다.

### 14.1 산출물

| 파일 | 내용 |
|---|---|
| `schemas/speech-segment-v1.schema.json` | root 직렬화 단위는 SpeechSegment **단일 객체**. track/channel index와 `channel_semantics`, `separation_method`, concurrent stream, 선택 confidence + semantics |
| `schemas/transcript-v1.schema.json` | immutable ASR evidence. segment lineage·exact text·선택 token/LID/n-best·닫힌 7-key `feature_status`·capability **snapshot** |
| `schemas/adapter-capability-report-v1.schema.json` | adapter 능력 축. `language_tag`·`token_unit`·`confidence_semantics`·`feature_status_value`·`network_requirement`·`determinism_tier`의 **단일 정의처** |
| `schemas/translated-transcript-v1.schema.json` | 번역 산출물과 `$defs/TranslationCapabilityReport` (**유일 정의**). exact source fragment, `coverage_status`, `uncovered_source_fragments[]` |
| `schemas/subtitle-document-v1.schema.json` | 표시 cue, line별 exact scalar lineage, `line_break_whitespace[]`, `resolved_style` snapshot, 구조형 `unsupported_features[]` |
| `src/media_clarity/subtitle_contracts.py` | domain validator + fixture runner CLI. `schema_core`의 `SchemaSet`·`SchemaValidator`·`Finding`·strict loader를 **재사용**하고 재구현하지 않는다 |
| `tests/test_subtitle_contracts.py` | schema 정본 계약, fixture, input mutation manifest, validator 경계 test 32건 |
| `tests/fixtures/subtitle_contracts/k-01.json` … `k-57.json` | 정상 3건 + 위반 54건. expected는 message가 아니라 exact `code + location` 쌍 |
| `scripts/verify_task_029.py` | 단일 검증 진입점. fixture · input mutants · schema mutants · validator code mutants를 **분모를 섞지 않고** 각각 보고 |
| `Makefile` | `fixtures-task-029` · `test-task-029` · `audit-task-029` · `verify-task-029` |

### 14.2 §0의 다섯 기술 결정을 그대로 구현했다

1. `SpeechSegment/v1` root는 단일 객체이고, ID 유일성·concurrent 대칭성은 `check_speech_segments()`가
   ordered 집합을 받아 검사한다. 별도 collection envelope를 만들지 않았다.
2. `Transcript/v1`은 immutable ASR evidence다. forced alignment schema·producer를 만들지 않았다.
3. offset은 exact stored text의 Unicode scalar 반개구간이고, gap과 explicit `und`는 **둘 다**
   `needs_review=true` + `language_unknown`을 요구한다. `und`로 바꿔 검수를 우회할 수 없다.
4. confidence는 semantics와 결박하며 `calibrated_probability`만 `[0,1]`을 강제한다.
5. translation split/merge와 subtitle cue는 fragment-level upstream lineage를 항상 보존한다.

### 14.3 확정한 안정 오류 코드

§8 표의 22개 코드를 **그대로** 쓴다. 새 코드를 만들지 않았다. 표에 이름이 하나뿐인 규칙 묶음은
다음처럼 그 코드 하나로 모으고 module docstring에 같은 내용을 적었다.

- `E_SCHEMA` — schema 위반에 더해, schema로 표현할 수 없는 **문서 집합 수준의 구조 위반**
  (ID 중복, 조건부 동반 필수 필드, `x-` 확장 ID 규칙, language tag 자리의 `"unknown"` 문자열).
- `E_LANGUAGE_GAP_REVIEW` — §4.2 R6·R10의 language unknown 정직성 묶음 세 가지:
  gap·`und`인데 review 상태 없음 / gap·`und`인데 `dominant_language` 있음 /
  전 범위 커버인데 `dominant_language`가 파생 규칙과 다름.
- `E_LINEAGE` — cue upstream fragment의 ID·exact text·line 결합 동치·입력 범위 partition 위반.
  범위 자체가 비었거나 밖이면 `E_OFFSET_RANGE`, 순서가 역전되면 `E_OFFSET_ORDER`가 먼저다.

finding 위치는 **선행 `/` 없는** JSON Pointer이며, 57개 fixture 전부에 대해 실제 입력에서
해석되는지 test로 고정했다 (`test_locations_are_resolvable_json_pointers`).
`resolved_style.language_overrides` 위반은 override에 없는 필드를 가리키지 않고 실제 존재하는
필드나 override 객체 자체로 좁힌다.

### 14.4 schema 경계를 지킨 방법

- `schema_core.py` diff **0**. `SUPPORTED_KEYWORDS`를 넓히지 않았고 새 `x-mcs-semantic`도 없다.
- `oneOf`/`anyOf`/`allOf`/`if-then-else`/`contains`/custom format을 쓰지 않는다. 그 표현이 필요한
  조건(축·capability·coverage·lineage)은 전부 domain validator로 옮겼다. test가 이를 고정한다.
- Draft 2020-12 **전체 구현을 주장하지 않는다.** 부분집합만 검사한다는 기존 경계를 그대로 쓴다.
- `common-v1.schema.json`과 job/eval schema는 **byte 무변경**이다. §10의 raw·canonical SHA-256
  네 개를 test가 매 실행 확인한다.

### 14.5 정본에서 뺀 pseudo-contract 필드 (숨기지 않는다)

`docs/ARCHITECTURE.md` §7.12 표에 전부 적었다. 요약하면 cue의 `language_spans[]`·
`dominant_language?`·`confidence?`·`speaker_label?` 넷을 정본에 넣지 않았다. **가설 쪽** LID의
단일 출처는 `Transcript.language_spans` 하나이고(`ARCHITECTURE.md` §3.0.2 L-1), `SubtitleDocument`는
독립 LID 가설을 갖지 않는다(L-2). 자막 계층에는 confidence·speaker label을 결박할
capability 축이 없어 근거 없는 값이 되기 때문이다. 산문은 지우지 않고 보존했다.

> **§3.0과 §3.0.2를 섞어 읽지 않는다** (REVIEW-023 D-01). §3.0은 **정답(`ReferenceBundle`)**
> 안에서 `language_spans[]`가 정답이라는 규정이고, §3.0.2는 **가설 산출물** 쪽 authority다.
> cue는 `lineage_fragments[]`로 입력 segment까지, 번역이면 그 segment의 `source_fragments[]`로
> 원문 segment까지 **segment 수준으로 추적**된다. cue 문자 범위 LID는 현재 계약으로 계산할 수
> 없어 **미지원**이다 (§16.6, REVIEW-024 D-02, `EVALS.md` §4.5(a)).

### 14.6 fixture (57건 — 첫 구현 시점)

> 현재 저장소의 fixture·mutation·test 숫자는 **§15**에 있다. 아래는 첫 구현 세션의 기록이며
> REVIEW-023 반영으로 늘어났다. 이 절의 숫자를 현재 상태로 읽지 않는다.

정상 3건이 §9가 요구한 일곱 경로를 모두 담는다.

| fixture | 담은 경로 |
|---|---|
| `k-01` | JA/EN 문장 내 전환 · explicit `und` · gap→unknown+review와 `dominant_language` 생략 · 실제 independent channel과 다른 stream의 동시 segment/cue · one_to_one/merged/split/dropped/unknown 번역 lineage · target axis emoji(U+1F44D)+combining(U+0301) cue lineage · 다른 stream cue overlap 허용 |
| `k-02` | timing·confidence·LID를 **전부 미지원**해 필드가 정직하게 생략된 Transcript · source axis 자막 · emoji/combining scalar offset · 공백 없는 일본어 `日本語 → ["日","本語"]` 분할 · 영어 공백을 explicit `line_break_whitespace`로 옮긴 분할 |
| `k-03` | partial 번역 — uncovered fragment가 남은 원문 범위를 정확히 한 번 채우고 `needs_review`와 안정 reason을 남김 |

위반 54건은 §9 mutation 목록에 1:1 대응하며 각 fixture의 `mutation_id`가 그 대응을 기록한다.

### 14.7 mutation 감사 — 세 분모를 섞지 않았다 (첫 구현 시점)

> 현재 분모와 판정 규칙은 **§15.4**에 있다. REVIEW-023 B-03이 지적한 대로 multi-kill 판정과
> 실제 sentinel 계산이 바뀌었고, 방어면 coverage guard와 depth probe 분모가 추가됐다.

`make audit-task-029` (= `scripts/verify_task_029.py`) 한 번으로 재현된다.

| 분모 | total | detected | kill rate | valid-case sentinel | SKIP |
|---|---|---|---|---|---|
| fixture | 57 | 57 | **100%** | 57/57 | 0 |
| **input mutants** | 121 | 121 | **100%** | 121/121 | 0 |
| **schema mutants** | 17 | 17 | **100%** | 17/17 | 0 |
| **validator code mutants** | 78 | 78 | **100%** | 78/78 | 0 |

- input mutant는 정상 fixture 문서를 **메모리에서** 한 필드·한 관계씩 변형하고 선언한
  `(code, location)`이 그대로 나오는지 본다. 기대값은 관측 복사가 아니라 손으로 선언했다.
- schema mutant는 production schema의 `required`·`enum`·범위·닫힌 객체 방어를, validator code
  mutant는 domain validator의 핵심 분기를 **저장소 밖 임시 사본에서** 하나씩 약화한다.
  각 mutant는 (a) 지정한 defect case가 실제로 탐지되지 않게 되는지와 (b) valid-case sentinel이
  여전히 통과하는지를 **함께** 판정한다. 저장소 파일은 바꾸지 않는다.

**중복 방어를 숨기지 않고 mutant를 합쳤다.** concurrent stream의 존재·겹침·대칭 세 분기와
concurrent cue의 겹침·대칭 두 분기는 하나를 지우면 나머지가 **같은 code·location으로** 잡아
개별 mutant가 공허해진다. 그래서 개별 mutant 대신 **한 번에 무력화하는 mutant** 하나로
감사하고, 그 사실을 mutant 제목과 코드 주석에 적었다.

**감사 과정에서 스스로 만든 공백 두 가지를 그대로 두지 않았다.**
① 처음 만든 `uncovered fragment의 needs_review=true` 검사는 schema의 `review_reasons` minItems 1과
동치 검사에 완전히 흡수돼 같은 위치를 두 번 보고했다. 중복 검사를 없애고 대신 minItems를 약화하는
schema mutant(`SM-17`)와 그 defect case(`IM-110`)를 추가해 실제 방어를 실증했다.
② 임시 사본에서 같은 초에 크기가 같은 파일을 다시 쓰면 스테일 `.pyc`가 재사용돼 mutant가 가짜로
미탐지되는 것을 관측했다. 감사 driver에 `PYTHONDONTWRITEBYTECODE=1`을 넣어 제거했다.

### 14.8 실행한 검증 (첫 구현 시점)

> REVIEW-023 반영 뒤 다시 실행한 결과는 **§15.6**에 있다.

```bash
make verify-task-029      # K-01~K-57 fixture + 계약 test + 3분류 mutation 감사 + 기존 전체 verify
make verify-task-028      # J-01~J-16 + store/runtime test + smoke + 전체 verify
make verify-task-006      # H-01~H-14 + 계약 test + 전체 verify
make verify               # static + 전체 unit + 실제 FFmpeg smoke
git diff --check
git status --short
```

전체 test는 355 → **387** (신규 32, 전부 `test_subtitle_contracts.py`). 기존 test 삭제·skip·완화 0건.
`ffmpeg`는 이 실행 환경에 처음부터 없어 컨테이너에 설치한 뒤 실행했다. 저장소에는 의존성·CI·
외부 데이터·모델을 추가하지 않았고 network access도 쓰지 않는다.

### 14.9 명시적 한계 (과장하지 않는다)

- **Draft 2020-12 전체 구현이 아니다.** `schema_core`의 부분집합만 검사한다.
- **BCP-47 전체 ABNF·IANA registry 유효성을 주장하지 않는다.** §4.3의 구조 subset만 본다.
- **번역문이 원문을 그대로 복사했는지 구조적으로 판정하지 않는다.** 정당하게 동일한 번역
  (고유명사 등)과 구분할 방법이 없어 잘못된 거부를 만든다. 계약이 강제할 수 있는 절반 —
  source/target을 한 필드로 합치지 않는 것, `dropped`는 빈 `target_text` + `untranslated_span` —
  만 강제하고 나머지는 검수 신호로 남긴다.
- **실제 ASR·번역·VAD·diarization·forced alignment adapter를 만들지 않았다.** 이 TASK는 계약과
  검증만 만들며 WER·번역 품질·RTF·VRAM·사람 수정시간을 개선하거나 측정하지 않는다.
- **미정값을 채우지 않았다.** U-07·U-12·U-13·U-15·U-16·U-18·U-19·U-22·U-26·U-27은 그대로다.
  U-18이 미정이므로 style 수치를, U-19가 미정이므로 `norm-v1` 규칙을 만들지 않았다.
- **Windows 11/NTFS에서 실행하지 않았다.** Linux·Python 3.11/3.12에서만 확인했다.

### 14.10 미해결 교차 계약 모순 (첫 구현 시점 — §16·§17이 갱신한다)

> 이 절의 "발견하지 못했다"는 첫 구현 세션의 기록이다. REVIEW-024 D-02와 REVIEW-025 D-03이
> 실제 모순을 지적했고 §16.6·**§17.7**이 그것을 해소했다. 현재 상태는 §17을 본다.

**발견하지 못했다.** §5 표로 해결되지 않는 모순은 없었고, 따라서 `Blocked`로 중단하지 않았다.
`docs/EVALS.md` §4.5(a)가 raw `Transcript`의 `language_spans`에도 `canonical_cue_text` 기준
offset을 쓰라고 읽히던 부분은 §5가 지시한 대로 좁혀 정합화했다 (raw Transcript는 exact segment
`text`와 ASR segment/token timing, SubtitleDocument만 `canonical_cue_text`).

### 14.11 범위 밖에서 발견했지만 수정하지 않은 것

1. **`common-v1.schema.json`의 `identifier`·`timestamp` pattern은 Python `re.search`로 해석되므로
   끝의 개행 하나를 통과시킨다** (`re`의 `$`는 trailing newline 앞에서도 맞는다). TASK-029에서
   `common-v1`과 `schema_core`는 수정 금지이므로 손대지 않았고, 신규 정본의 제품 불변식
   (target exact `ko`)은 domain validator가 **정확한 문자열 동등성**으로 따로 강제한다.
2. **`schema_core.SchemaValidator`는 `patternProperties` 중 처음 일치하는 하나만 적용한다.**
   신규 schema는 패턴이 하나뿐이라 영향이 없지만, 후속 계약이 패턴을 둘 이상 쓰면 재검토가 필요하다.

---

## 15. REVIEW-023 변경 요청 반영 기록 (같은 브랜치의 후속 커밋)

[`docs/reviews/REVIEW-023.md`](../reviews/REVIEW-023.md)의 **변경 요청** 판정을 PR #45의 같은
브랜치에 후속 커밋으로 반영했다. §14는 첫 구현 세션의 기록이며 **지우지 않았다.** 아래 숫자가
현재 저장소 상태이고, §14.6~§14.8의 숫자는 그 시점의 기록이다.

`schema_core.py`·`CACHE_KEY_FIELDS`·기존 job/artifact schema의 canonical bytes는 그대로다.
신규 dependency·model·network access는 0이고, §8의 안정 오류 코드 22개 밖의 코드를 만들지 않았다.

### 15.1 B-01 — 시간·stream·계보 결박 (거짓 음성 제거)

| # | 무엇이 통과하던 것을 막았나 | code / location |
|---|---|---|
| 1 | ASR segment가 입력 SpeechSegment **사이의 빈틈**을 가로질러도 양 끝점만 보면 통과했다. 이제 `start`를 포함하는 **하나의 연속 구간**이 `end`까지 덮는지 본다 | `E_TIME_RANGE` @ `…/end_seconds` |
| 2 | SpeechSegment → Transcript → TranslatedTranscript → SubtitleDocument의 `timebase_ref`가 갈라져도 통과했다 | `E_SOURCE_REF` @ `<문서>/timebase_ref` |
| 3 | Transcript segment·번역 fragment·cue fragment가 **다른 stream**의 상류를 참조해도 통과했다 | `E_STREAM_REF` @ 참조 필드 |
| 4 | Transcript stream/segment·번역 stream/segment·cue의 **ID 중복**이 dict last-write-wins에 먹혀 보이지 않았다. 이제 index를 만들기 **전에** 검사하고, 모든 index는 first-wins다 | `E_SCHEMA` @ 중복 ID |
| 5 | merged 번역의 source fragment가 **원문 Transcript 순서를 뒤집어도** 통과했다 | `E_OFFSET_ORDER` @ `…/char_start` |
| 6 | cue lineage가 배열 순서만 봐서, 줄을 뒤집고 `line_index`를 맞바꾸면 통과했다. 이제 `(cue_index, 2*line_index, position)`·줄바꿈 공백 `(cue_index, 2*after_line_index+1, position)`의 **렌더 순서 키**로 본다 | `E_OFFSET_ORDER` @ `…/char_start` |

### 15.2 B-02 — capability 정직성과 필드 부재

- `tokens`·`alternatives`·`language_spans`에 `minItems: 1`을 넣어 **빈 배열을 부재로 위장**할 수 없게 했다.
- `language_spans`가 없는데 `dominant_language`만 있으면 `E_LANGUAGE_GAP_REVIEW`.
- capability snapshot의 `adapter_id`/`adapter_version`을 문서 `provenance`에 결박했다 (`E_CAPABILITY_MISMATCH`).
- stream 수준 `speaker_label_source="adapter"`는 `supports_diarization`에, `"input"`은 실제 입력 label에 결박했다.
- `overlap_kind="none"`인데 `concurrent_stream_ids`가 비어 있지 않으면 계약 위반이다.

### 15.3 B-02 — 민감 값 비노출 (`schema_core.py` 무변경)

`schema_core`의 schema finding message는 위반한 **실제 값**을 담는다(`enum 밖의 값: 'SECRET…'`).
`schema_core`를 고치지 않고 **TASK-029 검증 경계에서** message를 결정적 고정 문구로 바꾼다
(`redact_schema_message` / `redact_schema_findings`). `error_code`와 `error_location`은 그대로다.

- 어떤 instance 파생 조각도 남기지 않는다. 필드 이름과 값을 구분해 남기려면 `schema_core`의
  문자열 포맷을 파싱해야 하고, 파싱은 갈라지기 쉽다. 위치가 이미 필드를 가리킨다.
- `run_leak_scan`이 **모든 fixture와 모든 input mutant**의 finding message를 훑어, 문서의
  `text`·`target_text`·`source_text`·`lines`·`speaker_label`·확장 ID와 절대 경로가
  들어갔는지 본다. 이 스캔이 실패하면 검증 전체가 실패한다.

### 15.4 B-03 — mutation 감사의 완전성

- **multi-kill 판정**: 여러 kill case를 선언한 mutant는 **선언한 전부**가 미탐지가 될 때만 killed다.
- **실제 sentinel**: fixture·input·leak 분모도 row 수가 아니라 **실제 valid-case 실행 결과**를 센다.
- **방어면 coverage guard**: `sys.settrace`로 domain validator의 `_finding(...)` 발화 **문장 전수**를
  AST에서 뽑아, fixture + input mutant를 돌리는 동안 한 번도 발화하지 않는 방어면이 있으면 실패한다.
  mutant 목록은 사람이 고른 표본이므로, 표본에 없는 방어면이 죽어 있어도 100% kill로 보인다.
  이 guard가 그 착시를 없앤다.
- **depth probe**: 비-finite·음수처럼 **schema가 먼저 거르는** 심층 방어는 문서 경로로 도달하지
  않는다. 면제 목록으로 두지 않고, (a) 내부 검사 함수를 직접 호출해 실제로 발화시키고
  (b) 같은 값이 문서 경로에서는 상류 schema에 잡힌다는 것을 **함께** 요구한다.
- **약한 mutant를 지우지 않았다.** REVIEW-023이 지적한 무효 mutant(VM-24·VM-25·VM-76·VM-98)는
  삭제가 아니라 **실제로 방어를 무력화하도록 고쳐** 다시 감사한다.

### 15.5 D-01 — 언어 authority 문서 정합화

cue에 독립 `language_spans`를 **다시 넣지 않았다.** 대신 세 자리를 나눠 적었다.

| 자리 | 지위 |
|---|---|
| `ReferenceBundle.language_spans[]` | 평가 정답 (ground truth) — `ARCHITECTURE.md` §3.0 |
| `Transcript…language_spans[]` | 가설 쪽 LID의 단일 출처 — `ARCHITECTURE.md` §3.0.2 L-1 |
| `SubtitleDocument` | 독립 LID 가설 없음 — L-2. (이 절이 처음 쓴 "결정적 투영"은 **§16.6에서 철회**했다) |

- `ARCHITECTURE.md` §3.0.2를 **추가**했다 (기존 산문은 지우지 않았다). §7.12 표의 근거를
  §3.0에서 §3.0.2로 고쳤다.
- `EVALS.md` C0 규칙 7·8과 §4.5(a)의 두 text space 표를 위 정의에 맞췄고, cue 언어 구간의
  투영식 L1–L3을 명시했다. **이 투영식은 §16.6에서 철회했다** — 현재 계약으로 성립하지 않는다.
- **미해결 모순 0건**이라고 적었으나, REVIEW-024 D-02가 이 절의 "결정적 투영" 주장 자체가
  현재 계약으로 성립하지 않는 모순임을 지적했다. **§16.6**에서 철회하고 정합화했다.

**원문과 번역문이 문자열상 같다는 사실만으로 구조 오류를 만들지 않았다.** validator에 그런 검사는
없다(`grep`으로 확인). 동일 문자열은 QC 신호 후보이지 계약 무효 조건이 아니다.

### 15.6 반영 뒤 감사 결과 (`make audit-task-029`)

| 분모 | total | detected | kill rate | 실제 valid-case sentinel | SKIP |
|---|---|---|---|---|---|
| fixture | 104 | 104 | **100%** | 3/3 | 0 |
| **input mutants** | 171 | 171 | **100%** | 171/171 | 0 |
| leak scan (민감 값 비노출) | 275 | 275 | **100%** | 3/3 | 0 |
| depth probes | 4 | 4 | **100%** | — | 0 |
| validator 방어면 coverage | 122 | 122 | **100%** | — | 0 |
| **schema mutants** | 22 | 22 | **100%** | 22/22 | 0 |
| **validator code mutants** | 100 | 100 | **100%** | 100/100 | 0 |

- fixture·leak scan의 sentinel은 **정상 fixture 3건의 실제 실행 결과**다. row 수를 sentinel
  통과 수로 출력하던 이전 판(REVIEW-023 B-03)을 고쳤다.
- depth probe·coverage guard는 mutant 분모가 아니라 **완전성 분모**라 valid-case sentinel 개념이
  없다. 대신 depth probe 자체가 상류 schema 방어를 함께 확인한다.
- schema mutant 22건은 다섯 정본의 **root `additionalProperties: false` 제거**(SM-18~SM-22),
  `required` 필드 제거, `enum` 확장, 범위·닫힌 객체·`pattern`·`uniqueItems`·`minItems` 방어를 덮는다.

### 15.7 실행한 검증 (반영 뒤)

```bash
make verify-task-029                  # fixture 104건 + 계약 test + 감사 + 기존 전체 verify
make audit-task-029
make verify-task-028
make verify-task-006
make verify
make verify-task-029 PYTHON=python3.12
git diff --check
git status --short
```

### 15.8 남은 한계 (확인하지 않은 것)

- **실제 ASR·번역·diarization·정렬 adapter는 없다.** 이 반영도 계약과 검증만 만든다.
- **Windows 11/NTFS에서 실행하지 않았다.** WER·RTF·VRAM·사람 수정시간도 측정하지 않았다.
- `CorrectionLedger`·`TermBundle`·`WorkUnitManifest`는 여전히 범위 밖이다.
- `STATUS.md`·`PLAN.md`·`DECISIONS.md`의 일반 상태 정합화는 Lean Root의 몫이며 여기서 하지 않았다.
- 이 세션은 **작성자**다. 리뷰도 승인도 하지 않는다 (`AGENTS.md` R8).

---

## 16. REVIEW-024 변경 요청 반영 기록 (같은 브랜치의 두 번째 후속 커밋)

[`docs/reviews/REVIEW-024.md`](../reviews/REVIEW-024.md)의 **변경 요청**(H-01~H-06, D-02)을
PR #45의 같은 브랜치에 반영했다. §14는 첫 구현, §15는 REVIEW-023 반영 기록이며 **지우지 않았다.**
현재 저장소 상태의 숫자는 이 절에 있다.

`schema_core.py`·`CACHE_KEY_FIELDS`·artifact store·job runtime·기존 job/artifact schema의
canonical bytes는 그대로다. 신규 dependency·model·network access는 0이고, §8의 안정 오류 코드
22개 밖의 코드를 만들지 않았다.

### 16.1 H-01 — ArtifactRef 계보 결박

세 층으로 나눠 강제한다.

| 층 | 무엇을 검사하나 | code / location |
|---|---|---|
| 문서 집합 안 | target 축 자막의 `source_transcript_ref` == 번역 문서의 `source_transcript` | `E_SOURCE_REF` @ `subtitle_document/source_transcript_ref` |
| ref 자체 | 상류 문서 ref가 실제 **문서 artifact**인가 (`kind="text"`, `media_type="application/json"`) | `E_SOURCE_REF` @ `…/kind`, `…/media_type` |
| 검증 컨텍스트 | 직접 입력 ref가 **실제로 제공된 문서**인가 | `E_SOURCE_REF` @ `translated_transcript/source_transcript`, `subtitle_document/input_document_ref`, `subtitle_document/source_transcript_ref` |

**API 확장은 최소 한 곳이다.** 검증 입력 집합에 `document_refs`라는 **검증 컨텍스트** key를
받는다. 문서가 아니라 "지금 검증하는 이 문서가 어떤 artifact인가"를 담는다.

- **문서 안에 self ArtifactRef를 둘 수 없다.** `content_hash`는 그 문서 바이트의 해시라서
  문서 안에 적으면 순환이 된다. 그래서 schema에 self-ref 필드를 추가하는 선택지는 성립하지
  않는다. identity는 store가 아는 사실이고, validator는 그것을 **컨텍스트로 받아야** 한다.
- 컨텍스트를 주지 않으면 identity 검사만 건너뛴다. **임의 ID를 지어내지 않는다** (R5).
- `validate_documents`의 시그니처는 바뀌지 않았다. 입력 집합의 선택 key 하나가 늘었을 뿐이라
  기존 호출자와 fixture는 그대로 동작한다.
- TASK 범위 판단: 변경 파일은 `subtitle_contracts.py`와 TASK-029 fixture뿐이다. §6이 허용한
  파일 밖을 건드리지 않으므로 **범위 안**으로 판단했고 blocker로 올리지 않았다.

`kind="text"`·`media_type="application/json"` 요구는 새 계약이 아니라 §4.4·§4.5가 말하는
"입력 Transcript / 직접 입력 TranslatedTranscript"가 JSON 문서라는 사실의 기계화다.

### 16.2 H-02 — `speaker_label_source="input"`의 값 결박

- segment 수준 `input` label은 참조한 SpeechSegment의 **실제 label 값**과 같아야 한다.
- stream 수준 `input` label은 그 `stream_id`를 가진 입력 SpeechSegment의 label과 같아야 한다.
- 입력에 label이 하나도 없으면 `input`을 주장할 수 없다.
- 입력 label이 **여러 개**면 어느 것을 복사했는지 계약이 정하지 않았으므로 조용히 고르지 않고
  계약 위반으로 보고한다. 임의 선택은 근거 없는 값을 만든다.
- `adapter`는 기존 diarization capability 결박을 그대로 유지한다.
- 정상 fixture(K-19/IM-35)도 upstream과 **동일한 실제 label**을 쓰도록 고쳤다.

### 16.3 H-03 — capability 내부 논리와 실제 evidence

| 규칙 | code |
|---|---|
| `supports_intra_sentential_lid=true` → `supports_language_id=true` | `E_CAPABILITY_MISMATCH` |
| `language_confidence_semantics != "none"` → `supports_language_id=true` | `E_CAPABILITY_MISMATCH` |
| `supports_nbest=false` → `nbest_score_semantics="none"` | `E_CAPABILITY_MISMATCH` |
| 실제 산출 언어 ⊆ 선언한 지원 언어 (`und` 제외) | `E_CAPABILITY_MISMATCH` |
| 번역한 원문 언어 ⊆ `supported_source_languages` | `E_CAPABILITY_MISMATCH` |

**빈 지원 언어 목록의 의미를 계약대로 고정했다.** §4.3은 "알 수 없으면 빈 배열과 명시적
limitation"이라고 정했다. 따라서 빈 배열은 **미상**이고, `limitations`가 비어 있으면 계약
위반이다. "모든 언어 지원"이나 "미지원"으로 읽는 것을 허용하지 않는다.

### 16.4 H-04 — schema 방어 분모의 완전성

수동 표본 22개를 유지하되, 그와 **별개로** 기계 수집 inventory를 새 분모로 만들었다.

- 다섯 정본에서 `required`·`enum`·범위·닫힌 객체·`pattern`·`uniqueItems`를 **전수 수집**한다
  (사람이 고른 목록이 아니다). 새 `required` 필드가 생기면 이 목록이 저절로 늘고, 대응
  mutation이 없으면 감사가 실패한다.
- 각 방어마다 세 가지를 함께 요구한다. ① 위반 입력이 production schema에서 실제로 거부된다,
  ② **그 방어만** 약화하면 더 이상 거부되지 않는다(다른 방어에 가려지지 않았다),
  ③ 약화한 schema에서도 정상 fixture는 통과한다(valid-case sentinel).
- 위반 입력과 약화 patch는 schema 좌표에서 **기계적으로 생성**한다. 저장소 밖 임시 schema
  디렉터리에서만 수행하며 저장소 파일은 바꾸지 않는다.
- 방어가 적용되는 instance를 정상 fixture에서 찾는다. base 세 건에 없는 선택 필드를 위해
  **네 번째 정상 fixture K-105(coverage)** 를 추가했다. 선택 필드를 모두 켠 정직한 문서다.
- 같은 노드의 다른 keyword가 그 방어를 **수학적으로 함의**하는 경우(예: `^[a-z]{2,8}…$`
  pattern이 `minLength: 2`를 이미 보장)는 어떤 입력으로도 분리할 수 없다. 감사 공백이 아니라
  중복 선언이므로 `subsumed`로 분류해 그 수를 함께 보고한다.

### 16.5 H-05 — sentinel을 exit gate에 연결

`_all_passed()`가 `passed`뿐 아니라 `sentinel_ok`도 본다. `--check-only`와 전체 audit가 같은
predicate를 쓰고, source mutant 실행도 관측된 input sentinel 실패를 그 mutant의 sentinel 실패로
센다. **감사 자체를 감사하는 자기검증**을 새 분모로 추가했다 — 임시 사본에서 sentinel만
실패시키고 `--check-only`가 exit 1인지 확인한다 (fixture·input·leak 각각).

### 16.6 H-06 / D-02 — location 안전성과 LID 주장 축소

**H-06.** schema finding의 location에 사용자 제어 dynamic key가 그대로 실리던 문제를
`schema_core`를 고치지 않고 TASK-029 경계에서 해결했다. location을 두 단계로 자른다.
① 구간 모양(ASCII snake_case/숫자가 아니면 중단), ② **실제 입력에서의 해석 가능성**
(`"a/b"`처럼 join 뒤 두 구간처럼 보이는 key를 거른다). 남은 위치는 언제나 입력에서 해석되는
부모를 가리키고 입력 값을 담지 않는다. 안전한 짧은 ASCII key는 진단 좌표로 남긴다.
누출 스캔이 message와 **location을 모두** 검사하도록 넓혔고, 길이와 무관하게 구간 모양을
전수로 본다.

**D-02.** cue 문자 범위 LID의 "결정적 투영" 주장을 **철회**했다. 현재 계약에는 target 문자와
source 문자 사이 정렬이 없고, `Transcript` token에 문자 오프셋이 없으며, `norm-v1`(U-19)도
미정이다. 없는 대응을 있다고 쓰지 않는다.

- LID authority 3축(§3.0.2 L-1/L-2/L-3/L-4)은 **유지**한다.
- cue에 독립 `language_spans`를 **다시 넣지 않았다.**
- `SubtitleDocument` 가설의 cue 문자 범위 LID는 **미지원**이며, 지금 보장하는 것은
  **segment 수준 추적 가능성**이다.
- U-19를 이 TASK에서 임의로 확정하지 않았다.
- `ARCHITECTURE.md` §3.0.2·§7.12, `EVALS.md` §4.5(a)와 C0 규칙 7·8, 그리고 §14.10·§15.5의
  "결정적 투영 / 미해결 모순 0" 표현을 실제 계약 수준으로 낮췄다.
  (§16.6이 놓친 EVALS의 잔존 문구는 REVIEW-025 D-03이 지적했고 **§17.7**이 마무리했다.)

### 16.7 오너 결정이 필요한 항목 (이 TASK에서 정하지 않았다)

REVIEW-024 §5와 같다. 후속 producer가 **숨은 정렬 규약**을 만들기 전에 오너가 정해야 한다.

1. 같은 stream 안 Transcript segment의 canonical 시간 순서
2. 서로 다른 source segment를 참조하는 translation segment의 순서
3. ASR `source_speech_segment_ids` 배열의 canonical order
4. U-19 `norm-v1` 정규화 규칙
5. `loads_strict()` duplicate-key 오류 message의 전체 CLI 비식별화 정책

이 다섯은 계약이 아직 규정하지 않았고, 임의로 정하면 producer가 그 선택에 묶인다.
**추측으로 채우지 않고 미해결로 남긴다** (`AGENTS.md` R5).

### 16.8 남은 한계 (확인하지 않은 것)

- **실제 ASR·번역·diarization·정렬 adapter는 없다.** 이 반영도 계약과 검증만 만든다.
- **Windows 11/NTFS에서 실행하지 않았다.** WER·RTF·VRAM·사람 수정시간도 측정하지 않았다.
- `document_refs` 컨텍스트를 **주지 않으면** identity 검사는 수행되지 않는다. 실제 producer가
  store에서 그 값을 넘기도록 만드는 것은 후속 실행 TASK의 몫이다.
- 누출 스캔의 message 판정은 3 scalar 이상 저장 텍스트를 대상으로 한다. location은 길이와
  무관하게 구간 모양을 전수로 검사한다.
- `CorrectionLedger`·`TermBundle`·`WorkUnitManifest`는 여전히 범위 밖이다.
- `STATUS.md`·`PLAN.md`·`DECISIONS.md`의 일반 상태 정합화는 Lean Root의 몫이며 여기서 하지 않았다.
- 이 세션은 **작성자**다. 리뷰도 승인도 하지 않는다 (`AGENTS.md` R8).

---

## 17. REVIEW-025 변경 요청 반영 기록 (같은 브랜치의 세 번째 후속 커밋)

[`docs/reviews/REVIEW-025.md`](../reviews/REVIEW-025.md)의 **변경 요청**(R-01~R-06, D-03)을
PR #45의 같은 브랜치에 반영했다. §14는 첫 구현, §15는 REVIEW-023, §16은 REVIEW-024 기록이며
**지우지 않았다.** 현재 저장소 상태의 숫자는 이 절에 있다.

`schema_core.py`·`CACHE_KEY_FIELDS`·`artifact_store.py`·`job_runtime.py`·기존 job/artifact
schema의 canonical bytes는 그대로다. 신규 dependency·model·network access는 0이고, §8의 안정
오류 코드 22개 밖의 코드를 만들지 않았다. REVIEW-023/024에서 해소한 방어는 회귀 없이 유지된다.

### 17.1 R-01 — 검증 컨텍스트 fail-open과 ArtifactRef 일관성

**컨텍스트는 더 이상 선택이 아니다.** 계보 identity를 검사해야 하는 문서 조합(번역·자막)에서
`document_refs`가 없거나 필요한 role이 빠지면 조용히 건너뛰지 않고 `E_SOURCE_REF`로 거부한다.
"확인하지 못했다"를 `VALID`로 돌려주지 않는다.

| 규칙 | code @ location |
|---|---|
| 번역 문서를 검증하려면 `transcript` role이 필요하다 | `E_SOURCE_REF` @ `translated_transcript/source_transcript` |
| 자막 문서를 검증하려면 직접 입력 role이 필요하다 (target이면 `translated_transcript`) | `E_SOURCE_REF` @ `subtitle_document/input_document_ref` |
| target 축 자막의 원본 ref를 검증하려면 `transcript` role이 필요하다 | `E_SOURCE_REF` @ `subtitle_document/source_transcript_ref` |
| Transcript와 TranslatedTranscript가 같은 identity로 붕괴 | `E_SOURCE_REF` @ `document_refs/translated_transcript` |
| 컨텍스트 ref는 `common-v1.schema.json#/$defs/ArtifactRef`로 검증한다 (느슨한 사본 없음) | `E_SCHEMA` @ `document_refs/<role>` |
| role은 `transcript`·`translated_transcript` 둘로 닫는다 | `E_SCHEMA` @ `document_refs/<role>` |
| 같은 `artifact_id`를 가리키는 모든 ref의 immutable metadata가 일치해야 한다 | `E_SOURCE_REF` @ `<ref 위치>/<field>` |

**ArtifactRef equality가 비교하는 정확한 field set** (`subtitle_contracts.py` 상수로 고정).

| 구분 | field | 근거 |
|---|---|---|
| **identity** | `artifact_id`, `content_hash` | ARCHITECTURE §2.1 — `artifact_id`는 프로젝트 내 고유, `content_hash`가 같으면 같은 산출물 |
| **immutable metadata (일치 필수)** | `schema_version`, `content_hash`, `kind`, `media_type`, `byte_size`, `is_estimate` | 바이트가 정해지면 함께 정해지는 값. 같은 ID인데 다르면 둘 중 하나가 거짓이다 |
| **비교하지 않음 (오너 결정)** | `uri`, `produced_by`, `created_at`, `parent_refs`, `timebase_ref` | 캐시 재사용·외부 입력에서 같은 artifact가 다른 값을 가질 수 있는지 정한 계약이 **없다**. 임의로 정하지 않는다 (§17.8) |

> `uri`의 절대 경로 허용 여부도 같은 이유로 정하지 않았다. `common-v1`은 `uri`를
> "외부 입력 URI도 표현할 수 있는 불투명 문자열"로 규정하고, TASK-028의 store는 산출물에
> project-relative 경로를 쓴다. 어느 쪽이 `document_refs`에 적용되는지는 계약에 없다.

### 17.2 R-02 — 비겹치는 SpeechSegment lineage와 화자 근거

- `source_speech_segment_ids`의 각 항목이 그 ASR segment 구간과 **양의 길이로 겹치는지**
  검사한다. 겹치지 않으면 `E_TIME_RANGE` @ `…/source_speech_segment_ids/<i>`.
- 화자 근거는 **실제로 구간을 덮는 입력에서만** 모은다. 겹치지 않는 과거·미래 segment의
  label을 빌려 올 수 없다.
- 덮는 입력 중 **label이 없는 것이 있으면** 단일 input label을 주장할 수 없다
  (`E_CAPABILITY_MISMATCH` @ `…/speaker_label`). stream 수준도 같다 — 한 입력만 label을
  갖고 나머지는 없으면 stream 전체의 화자를 그 하나로 정당화하지 않는다.
- **비겹치는 참조를 다른 의미로 허용할지는 정하지 않았다.** 지금 계약에서
  `source_speech_segment_ids`는 "이 인식 결과가 나온 입력"이므로 겹치지 않는 참조는 오류다.
  context 참조가 필요하다면 별도 field가 필요하며 §17.8 오너 결정 항목이다.

### 17.3 R-03 — translation code-switch capability

한 번역 입력 단위의 언어를 **실제 `source_fragments` 범위와 `Transcript.language_spans`의
교차**로 계산한다. 전체 Transcript가 아니라 그 단위가 실제로 받은 범위만 본다.

- 한 단위가 **복수 known language** 또는 **fragment 안쪽의 intra-sentential 전환 경계**를
  담고 있으면 `supports_code_switching_input=true`를 요구한다
  (`E_CAPABILITY_MISMATCH` @ `translated_transcript/capability_report/supports_code_switching_input`).
- 언어 경계에 맞춰 나눈 단일언어 단위는 미지원 adapter로도 유효하다 (정상 회귀로 고정).
- **언어별 분할 호출 후 합성**은 추론하지 않는다. 그 사실을 표현할 provenance/processing
  계약이 없으므로 §17.8 오너 결정 항목으로 올린다.
- `supports_independent_channel_input`·`supports_overlap_streams`는 adapter가 전처리 전
  원본을 받는지 분리된 work unit을 받는지에 따라 의미가 달라지므로 결박하지 않았다 (§17.8).

### 17.4 R-04 — 임의 정밀도 JSON 숫자

`_finite()`가 더 이상 `float()`로 강제 변환하지 않는다. Python `int`는 언제나 finite이므로
변환 없이 판정하고, 모든 시간·confidence·offset 비교가 원래 타입 그대로 이루어진다.
strict JSON loader가 받는 401자리 정수도 **crash 대신 안정 finding**을 낸다.

감사한 number 경로: SpeechSegment 시간, Transcript segment·token 시간, token/segment
confidence, language span offset, 번역 fragment offset, cue 시간, resolved style 숫자.
CLI fixture 경로가 traceback 없이 끝나는 것도 회귀로 고정했다.

### 17.5 R-05 — dynamic key location의 slash aliasing

**이어붙인 문자열을 사후 split하지 않는다.** 실제 입력을 따라가며 구간을 확정한다.

- 각 단계에서 그 노드의 **실제 key 중 앞부분과 맞는 것**을 찾는다. 둘 이상 맞으면
  (alias 충돌) 거기서 접는다.
- 맞는 key가 **정본이 선언한 고정 field**가 아니면 접는다. 모양이 ASCII snake_case라는
  이유만으로 남기지 않는다 — `patient_name`·`John_Doe`도 같은 모양이다.
- 유일한 예외는 정본이 선언한 dynamic 어휘, 즉 `language_overrides`의 language tag subset이다.
  이것은 계약이 정한 vocabulary이지 자유 입력이 아니다.
- 알 수 없는 최상위 key는 **root**(빈 pointer), 잘못된 `document_refs` key는 `document_refs`,
  허용되지 않은 language override key는 그 부모로 접힌다.
- **container 조기 반환 경로도 같은 정규화를 지난다** — 모든 반환이 `_finalize`를 통과한다.
- leak scan은 message와 location을 **모두** 보며, location은 접힘 결과와의 동일성·선언
  어휘 여부·입력 해석 가능성을 독립적으로 확인한다.

### 17.6 R-06 — 고정 defense manifest와 killable/equivalent 분리

분모를 production schema에서 다시 만들면 방어를 지웠을 때 분모도 함께 줄어 감사가 조용히
통과한다. 그래서 현재 방어 ID 집합을 **schema 밖 파일**에 고정했다.

- `tests/fixtures/subtitle_contracts/defense-manifest.json` — killable 목록, equivalent
  allowlist(근거 포함), 그리고 둘에 대한 digest.
- 방어가 **삭제되면** `MF-01`, **추가되면** `MF-02`, 목록과 digest가 어긋나면 `MF-03`이
  실패한다. 갱신은 `--write-manifest`가 만드는 **명시적 diff**로만 한다.
- `--manifest-check`는 drift와 transformation 고유성만 빠르게 확인하는 모드다.
  전체 audit의 성공 조건에도 manifest·drift·고유성 검사가 **직접** 걸려 있다.
- **자기 mutation**: REVIEW-024가 지목한 다섯 root required(`source_track_index`,
  `transcript_id`, `network_requirement`, `source_transcript`, `input_document_ref`)를
  임시 사본에서 하나씩 지우고 gate가 실제로 exit 1인지 확인한다 (SD-01~SD-05).
- **killable / equivalent 분리**: pattern이 minLength를 논리적으로 함의하는 2건은 단독 kill이
  원리적으로 불가능하다. killable 분모에 섞지 않고 근거가 적힌 frozen allowlist로 관리하며,
  allowlist가 조용히 늘거나 줄면 그 자체가 실패다. 보고는 `291/291 killable + equivalent 2/2`다.

### 17.7 D-03 — EVALS 잔존 모순과 불가능한 char→time 주장

- C0의 잔존 cue-LID 투영 문구(411~413·432~433·464~465)를 제거했다.
- `SubtitleDocument` cue LID 미지원 결론은 유지한다.
- **raw `Transcript`의 intra-segment 문자→시간 투영도 미지원으로 낮췄다.** token에는 문자
  오프셋이 없고 segment `text`를 정확히 한 번 분할한다는 계약도 없다. §4.5(b)·(c)의 전환
  지점 지표도 같은 이유로 미지원이며, 정의는 후속 계약을 위해 보존했다.
- **지원 범위와 불가능 범위를 나눴다.** segment의 text 전체가 gap·`und` 없이 단일 known
  language로 덮이면 그 segment 구간 전체를 그 언어로 귀속할 수 있다(S1–S3). 그 밖은 분모에서
  제외하고 그 사실을 보고한다.
- U-19(`norm-v1`)와 균등 시간 배분, token text partition을 이 TASK에서 확정하지 않았다.
- ARCHITECTURE·EVALS·TASK의 "결정적 투영 / 미해결 모순 0" 표현을 실제 상태에 맞췄다.

### 17.8 오너 결정이 필요한 항목 (이 TASK에서 정하지 않았다)

§16.7 목록에 REVIEW-025가 남긴 항목을 더한다.

1. 같은 stream 안 Transcript segment의 canonical 시간 순서
2. 서로 다른 source segment를 참조하는 translation segment의 순서
3. ASR `source_speech_segment_ids` 배열의 canonical order
   (각 참조의 **시간 관련성** 검증은 §17.2로 이번에 넣었다)
4. U-19 `norm-v1` 정규화 규칙과 문자↔시간 mapping 계약
5. `loads_strict()` duplicate-key 오류 message의 전체 CLI 비식별화 정책
6. **ArtifactRef의 `uri`·`produced_by`·`created_at`·`parent_refs`·`timebase_ref` 동일성 의미**
   — 캐시 재사용에서 같은 artifact가 다른 값을 가질 수 있는가. `uri`의 절대 경로 허용 여부 포함
7. **비겹치는 SpeechSegment를 context로 참조할 필요가 있는가** — 필요하다면
   `source_speech_segment_ids`가 아닌 별도 field가 필요하다
8. **언어별 분할 호출 후 합성한 번역**을 표현할 provenance/processing 계약
9. `supports_independent_channel_input`·`supports_overlap_streams`가 전처리 **전** 원본을
   뜻하는지 분리된 work unit을 뜻하는지

**추측으로 채우지 않고 미해결로 남긴다** (`AGENTS.md` R5).

### 17.9 남은 한계 (확인하지 않은 것)

- **실제 ASR·번역·diarization·정렬 adapter는 없다.** 이 반영도 계약과 검증만 만든다.
- **Windows 11/NTFS에서 실행하지 않았다.** WER·RTF·VRAM·사람 수정시간도 측정하지 않았다.
- `CorrectionLedger`·`TermBundle`·`WorkUnitManifest`는 여전히 범위 밖이다.
- `STATUS.md`·`PLAN.md`·`DECISIONS.md`의 일반 상태 정합화와 REVIEW-023~025 문서의 통합
  순서는 Lean Root의 몫이며 여기서 하지 않았다 (REVIEW-025 §4).
- 이 세션은 **작성자**다. 리뷰도 승인도 하지 않는다 (`AGENTS.md` R8).

---

## 18. REVIEW-026 변경 요청 반영 기록 (같은 브랜치의 네 번째 후속 커밋)

> 대상 고정 HEAD `67060e39ef6c4b9b004c77e2c57446804173be3a`,
> tree `da6d68a45642fbc3d253a4e67bcf9ffcc265b077`, 기준 main
> `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`.
> REVIEW-026의 **R-01~R-03과 D-04만** 제한 반영했다. §14~§17의 기록은 각 고정 HEAD의
> 역사이며 다시 쓰지 않는다.

### 18.1 R-01 — location 비식별화를 **경로별**로 바꿨다

전역 `declared_segments()` 집합을 제거했다. 이제 허용 어휘는 정본 schema를 **입력과 나란히
따라가며** 그 자리에서 얻는다 (`_document_set_schema()` → `_declared_children()` →
`_child_position()`/`_item_position()`).

| 입력 | 이전 location | 지금 location |
|---|---|---|
| 최상위 `uri` / `text` / `artifact_id` | 그 이름 그대로 | `""` (root) |
| `document_refs["uri"]` / `["speaker_label"]` / `["artifact_id"]` | `document_refs/<raw key>` | `document_refs` |
| `language_overrides["patient"]` / `["password"]` | raw key 포함 | `.../language_overrides` |
| `language_overrides["en-John-Doe"]` / `["en-x-secret"]` | raw key 포함 (BCP-47 모양이라 허용됐다) | `.../language_overrides` |
| `language_overrides["speaker_label"]` | raw key 포함 | `.../language_overrides` |
| 정상 `ko` override의 결함 | `.../language_overrides/ko/max_duration_seconds` | `.../language_overrides` |

마지막 줄은 **의도한 축소**다. 정본이 선언한 것은 `language_overrides`까지이고 그 아래 key는
입력이 정한다. 진단성보다 비노출을 앞세운다 (REVIEW-026 R-01 2번).

- **`patternProperties`는 어휘가 아니다.** language tag 모양은 임의 문자열을 담을 수 있다.
- **공개 경계도 같은 계약을 지난다.** `_public_boundary()` 데코레이터가 여덟 개 공개
  `check_*` 함수의 결과를 각자 받은 문서로 접는다. `PB-01`~`PB-08`이 이를 고정한다.
- **감사 oracle을 분리했다.** `declared_path_patterns()`는 정본을 **먼저 전부 펼쳐**
  `transcript/streams/*/segments/*/text` 같은 패턴 집합을 만들고,
  `oracle_location_problem()`이 location을 (a) 입력에서 구간별로 해석되는가,
  (b) 다른 key와 alias되지 않는가, (c) 그 패턴 집합에 있는가로 판정한다.
  production `safe_location()`·`declared_segments()`를 부르지 않는다.
- **동적 mapping key도 민감 후보다.** `oracle_dynamic_keys()`가 정본이 그 자리에서 선언하지
  않은 key를 전수로 모아 message 누출 판정에 넣는다.
- 반례는 input mutant `IM-226`~`IM-235`와 fixture `K-160`~`K-169`, source mutant
  `VM-109`(경로별 어휘를 전역 집합으로 되돌린다)·`VM-142`(language tag 모양을 다시 근거로 삼는다)로
  고정했다.

### 18.2 R-02 — raw JSON 숫자 profile과 문서 root

**`schema_core.py`는 바꾸지 않았다.** 전부 TASK-029 경계(`subtitle_contracts.py`)에서 해결했다.

#### `num-profile-v1` — 허용 숫자 어휘·정밀도 profile

| 리터럴 종류 | 규칙 | 근거 |
|---|---|---|
| 정수 | 유효 자릿수 ≤ **4,300** (`NUMBER_MAX_INTEGER_DIGITS`). 넘으면 거부 | `int()`를 부르기 **전에** 판정하므로 환경의 `ValueError`가 새지 않는다 |
| decimal (`.` 또는 `e` 포함) | `float(리터럴)`이 유한하고, `Decimal(repr(float(리터럴))) == Decimal(리터럴)` | 리터럴이 그 binary64 값의 **최단 왕복 표기와 수치적으로 같을 것**을 요구한다 |

`parse_int`/`parse_float` hook이 리터럴 **문자열**을 그대로 주므로 tokenizer를 새로 쓰지 않는다.

| 반례 | 결과 |
|---|---|
| 4,301자리 · 10,000자리 양/음 정수 | `E_JSON num-profile-v1: 정수 리터럴 유효 자릿수 …` · exit 2. **traceback 없음** |
| 4,300자리 정수 | 통과 (경계가 정확하다) |
| confidence `1.0000000000000001` | `E_JSON num-profile-v1: … binary64 반올림으로 값이 바뀐다` |
| `-1e-400` (timestamp·`min_gap_seconds`) | 같은 profile 오류. `-0.0`으로 조용히 통과하지 않는다 |
| `1e-400` (`max_cps`) | 같은 profile 오류. `0.0`으로 잘못 거부되지 않는다 |
| `1e400` | `… binary64 범위를 넘어 유한하지 않다` |
| `0.1` · `0.30000000000000004` | 통과 — 생산자가 실제로 쓰는 표기를 막지 않는다 |

profile 거부는 **schema 범위 위반과 다른 축**이다 (§8.1). `NumberProfileError`는
`JsonInputError`의 하위 타입이라 CLI 계약(`E_JSON` + exit 2)이 그대로 유지된다.

#### 문서 집합 root

`documents`가 `[]`·`null`·정수·문자열이면 `E_SCHEMA @ ""`다. 이전 판은
`AttributeError`/`TypeError` traceback으로 끝났다.

#### 새 회귀 분모

`RJ-01`~`RJ-17`(raw JSON probe)을 `--check-only` payload에 넣었다. in-memory mutation은 이미
파싱된 객체를 넣으므로 이 축을 **원리적으로** 재현하지 못한다. `validate_documents`의 root
가드는 방어면 coverage guard에서도 실제로 발화시킨다.

### 18.3 R-03 — manifest가 방어의 **의미**와 자기 갱신을 고정한다

- `SchemaDefense.fingerprint` 추가. 좌표(`파일#/pointer|keyword`)와 함께 **canonical 의미값**을
  고정한다.

  | kind | fingerprint |
  |---|---|
  | `enum` | `enum=["a","b",…]` (canonical JSON, 정렬) |
  | `pattern` | `pattern="<정규식>"` |
  | `range:<kw>` | `<kw>=<값>` |
  | `closed` | `closed=[properties:a,…,patternProperties:^…$]` — **허용되는 이름 집합** |
  | `required:<f>` | `required=<f>` |
  | `uniqueItems` | `uniqueItems=true` |

- `--write-manifest`는 **실제로 기록하는 entry**에서 digest를 계산하고, 쓴 직후 같은 파일로
  `run_manifest_check()`를 돌려 **실패하면 exit 1**로 끝난다. 갱신 도구가 스스로 불일치 파일을
  만들 수 없다.
- manifest 검사 8건이 standalone 성공 조건이다.

  | check | 무엇을 막나 |
  |---|---|
  | MF-01 / MF-02 | 방어 삭제 / 미등록 신규 방어 |
  | MF-03 | digest 불일치 |
  | MF-04 | 근거 없는 equivalent |
  | MF-05 | 중복 transformation |
  | **MF-06** | **의미값 drift** — enum 확장, 범위 완화, pattern 변경, closed 객체 확장 |
  | **MF-07** | killable/equivalent 각 절의 중복과 두 절의 교집합 |
  | **MF-08** | `defense_declared == defense_unique`, schema·validator mutant의 declared==unique, manifest 선언 수 == 고유 수 |

- 자기검증 `SD-01`~`SD-13`을 저장소 밖 임시 사본에서 돌린다. 각각 `--manifest-check` exit 1이다.

  | id | 훼손 |
  |---|---|
  | SD-01~05 | 다섯 정본의 root required 삭제 (REVIEW-024가 지목한 필드) |
  | **SD-06** | `line_break_policy` enum에 `x_new_policy` 추가 |
  | **SD-07** | `source_track_index`의 `minimum` 완화 |
  | **SD-08** | `extension_id` pattern을 `^.*$`로 변경 |
  | **SD-09** | root `required` 배열에 같은 이름 중복 |
  | **SD-10 / SD-11** | manifest killable / equivalent 절 안의 ID 중복 |
  | **SD-12** | killable과 equivalent의 교집합 |
  | **SD-13** | equivalent 방어(`minLength`) 삭제 → `--manifest-check` **1**, `--write-manifest` **0**, 직후 `--manifest-check` **0** (stale digest 없음) |

- 감사 자기검증에 **AS-04**를 더했다. 갱신 도구가 목록과 다른 digest를 쓰도록 훼손하면
  `--write-manifest` 자체가 exit 1이어야 한다.

### 18.4 D-04 — 공개 문서 정합화

1. **EVALS §4.5(a)의 1차 분모를 "정답이 알려진 언어를 가진 발화 격자 전부"로 고정했다.**
   투영 불가·gap·`und` 가설은 분모에서 빼지 않고 `unknown`(오답)으로 센다. 어려운 구간을
   `und`로 내보내 정확도를 올리는 회피 경로를 닫는다.
   `hypothesis_coverage`·`unknown_ratio`·`supported_segment_ratio`·`excluded_reference_ratio`를
   함께 보고하지 않으면 정확도만 보고할 수 없다.
2. **분모 0은 측정 불가**다. `MetricResult.status = "insufficient_n"`이고 `value`가 없다.
   0%도 100%도 쓰지 않는다.
3. intra-segment 문자→시간 투영은 명시적 mapping 계약이 생기기 전까지 **미지원**으로 유지한다.
4. **ARCHITECTURE §7.3.1의 LID 미지원 fallback을 철회했다.** capability가 거짓이면
   `language_spans`와 `dominant_language`가 **둘 다 부재**다. 설정 언어를 어댑터 가설처럼 적지
   않는다.
5. **TASK §5의 timing projection 문장을 §17.7과 맞췄다.** 그 문장은 offset이 어느 text space에
   속하는지를 정할 뿐, 시간 투영을 승인하지 않는다.
6. **`document_refs` 검증 컨텍스트 envelope을 ARCHITECTURE §2.1.1에 공개 계약으로 적었다** —
   role 두 개, ArtifactRef 모양, 필수 조건, identity 비교 field.
7. **generic ArtifactRef URI와 TASK-028 store 출력 URI를 분리했다** (ARCHITECTURE §2.1).
   전자는 불투명 문자열이고 후자는 store가 자기 출력에 대해 지키는 생산 규칙이다.
   `uri`·`produced_by`·`created_at`·`parent_refs`·`timebase_ref`의 동일성 의미는 **오너 결정**으로
   남긴다 (§17.8-6).

### 18.5 이 반영에서 정하지 않은 것

§17.8의 오너 결정 항목 아홉 개는 그대로 열려 있다. 이번 반영은 그중 어느 것도 임의로 정하지
않았다. `schema_core.py`·`artifact_store.py`·`job_runtime.py`·`CACHE_KEY_FIELDS`·
`common-v1`·`job-v1`은 diff 0이고, 새 dependency·model·network는 0이며 §8의 안정 error code
22개만 쓴다. **새 error code 0개.**


## 19. 오너 결정 option 3 반영 기록 (같은 브랜치의 다섯 번째 후속 커밋)

REVIEW-026 **D-04**에 대한 사람 제품 오너의 결정은 **option 3**이다.

> 공식 LID 정확도 채점을 TASK-029에서 **미지원**으로 표시한다. 동시 다국어 발화의 채점
> 의미를 정의하는 후속 화자/정렬 평가 TASK가 생기기 전까지 단일 label 채점 규칙을
> **만들지도, 조용히 고르지도 않는다.** 다만 후속 구현이 서로 다른 격자를 만들지 못하도록
> 결정적 정규화·경계는 지금 고정한다.

정본은 [`docs/DECISIONS.md`](../DECISIONS.md) **ADR-0029**다.

### 19.1 §18.4의 무엇을 대체하는가

§18.4의 1·2번은 §4.5(a)의 **1차 분모와 S1–S4 채점 규칙**을 고정했다. 그 규정은 동시 발화
격자에서 정답 label을 **암묵적으로 하나로 골랐다** — 두 stream이 같은 시각을 다른 언어로
덮을 때 무엇이 정답인지 그 규정에는 없고, 그럼에도 일치율을 계산했다.

**그래서 §18.4-1의 1차 분모·S1–S4·네 비율 규정을 철회한다.** §18.4의 나머지(3·4·5·6·7)는
그대로 유지되며, §18의 기록 자체는 지우지 않는다 (일어난 일이다).

### 19.2 지금 고정한 다섯 경계

| 항목 | 규정 | 기계 정본 |
|---|---|---|
| timeline origin·interval | 격자 0번은 정준 `Timebase`의 **0.0초**에서 시작하고 간격은 **100ms**, 구간은 **반개구간** `[start, end)`다 | `LID_GRID_ORIGIN_SECONDS`·`LID_GRID_INTERVAL_SECONDS`·`lid_frame_bounds()` |
| 꼬리 프레임 | 격자는 **중점이 구간 안에 들 때만** 덮인 것으로 센다. 부분 가중치도 경계 반올림도 없다. 경계 판정은 binary64가 아니라 **최단 왕복 십진 표기**로 한다 (`num-profile-v1`과 같은 축) | `lid_frame_range()`·`lid_frame_midpoint()` |
| 인접 동일 언어 정규화 | 맞닿은 두 `language_span`의 언어가 같으면 **하나로 합친 것이 정규형**이다. 문서가 정규형인지는 validator가 `E_OFFSET_ORDER`로 거부한다. 맞닿지 **않은** 같은 언어 span은 합치지 않는다 (사이 gap은 별도 계약) | `normalize_language_spans()` · `_check_language_spans()` |
| 동시 다른 언어 stream | 한 격자를 덮는 언어를 **집합으로** 돌려주고 하나로 접지 않는다. 크기 2 이상이면 단일 정답이 없다는 뜻이고, 그 상태는 **미지원**으로만 표현한다. 격자를 분모에서 몰래 빼지 않는다 | `lid_frame_languages()`·`lid_has_simultaneous_conflict()` |
| 분모 0 | `status: "insufficient_n"`·`reason: "reference_denominator_empty"`·`n: 0`이고 `value`가 **없다.** 0%도 100%도 쓰지 않는다 | `zero_denominator_result()` |

LID 지표 자체의 고정 결과는 `lid_scoring_result()`다 — `status: "unsupported"`,
`reason: "simultaneous_multilingual_speech_semantics_undefined"`, `value` 없음. **데이터에
의존하지 않는다.**

### 19.3 새 계약 방어와 fixture

| 항목 | 값 |
|---|---|
| 새 validator 방어면 | **1개** — 맞닿은 동일 언어 span (`E_OFFSET_ORDER`) |
| 새 error code | **0개** (§8의 22개만 사용) |
| 새 fixture | **K-170** (알려진 언어) · **K-171** (`und`) |
| 새 input mutant | **IM-236** · **IM-237** |
| 새 validator code mutant | **VM-144** (정규형 검사 제거 → IM-236·IM-237을 놓친다) |
| 새 계약 unit test | **13건** (격자 origin/interval, 반개구간, 꼬리 프레임 중점 규칙, binary64 drift 비의존, 빈·역전 구간, 비유한 시각의 안정 오류와 **값 비노출**, 동시 언어 집합, 미지원 고정, 분모 0, `common-v1` `metric_status` 어휘 일치, 정규형과 고정점, gap 비병합, 문서 거부) |

### 19.4 공개 `document_refs` 계약 보강

[`ARCHITECTURE.md`](../ARCHITECTURE.md) §2.1.1은 envelope의 존재와 role·모양·identity 비교
field는 적었지만, **어느 문서 조합에서 무엇이 필수인지**, `kind`·`media_type`이 정확히 어떤
값인지, finding이 어디에 붙는지는 code와 §8에만 있었다. 그 셋을 공개 계약에 적었다.

- 조합별 필요 role 표 (`speech_segments`/`transcript`만 → 없음, `translated_transcript` →
  `transcript`, 자막 `text_axis="source"` → `transcript`, `text_axis="target"` → 둘 다)
- `kind="text"` 고정, `media_type` essence `application/json` (parameter 허용, 대소문자 무시).
  종류 결박과 identity 비교는 **다른 축**이다 — 후자는 같은 artifact의 모든 ref에서
  `media_type` 문자열이 정확히 일치할 것을 요구하므로 한 곳만 표기를 바꾸면 `E_SOURCE_REF`다
- 두 role이 같은 `(artifact_id, content_hash)`로 붕괴하면 `E_SOURCE_REF`
- 컨텍스트 부재 finding은 `document_refs/...`가 아니라 **그 검사가 붙는 실제 문서 field**에
  붙는다. 붕괴만 `document_refs/translated_transcript`다
- 계약 밖 key는 `E_SCHEMA` @ `document_refs`이고 **key 이름은 location에 남지 않는다**

### 19.5 R-01·R-02·R-03에 대해 이 커밋이 한 일

이 세 finding은 이전 고정 HEAD `cb3bcbc`에서 이미 반영됐다 (§18.1~18.3). 이번 커밋은 그
방어를 **약화하지 않고**, 새로 늘어난 면에 같은 계약을 적용했다.

| finding | 이번 커밋의 처리 |
|---|---|
| **R-01** (경로별 비식별화) | 새 방어면의 location `transcript/streams/*/segments/*/language_spans/*/language`는 전부 정본 선언 어휘다. 독립 oracle의 leak scan 분모가 404 → **408**로 늘었고 전부 통과한다. 새 helper의 비유한 입력 오류 message에도 입력값을 넣지 않으며 unit test가 그것을 직접 검사한다 |
| **R-02** (raw JSON 숫자·문서 root) | 새 격자 helper는 비유한 시각·비수치 입력을 **고정 message의 `ValueError`**로 끝낸다. 격자 소속 판정도 binary64 나눗셈이 아니라 `num-profile-v1`과 같은 최단 왕복 십진 표기로 한다 — `0.25 / 0.1 = 2.4999…`가 격자를 흔들지 못한다. raw JSON probe 17건은 그대로 통과한다 |
| **R-03** (방어 manifest) | schema 방어는 diff 0이므로 manifest도 diff 0이다. validator 방어면 inventory는 자동 파생이라 144 → **145**로 늘었고 새 면도 실제로 발화한다. MF-01~08·SD-01~13·AS-01~04는 그대로 통과한다 |

### 19.6 이 반영에서 정하지 않은 것

- §17.8의 오너 결정 항목 아홉 개는 그대로 열려 있다.
- 동시 다국어 발화의 **채점 의미**는 정하지 않았다. 그것이 이 결정의 요지다.
- `schema_core.py`·`artifact_store.py`·`job_runtime.py`·`CACHE_KEY_FIELDS`·`common-v1`·
  `job-v1`은 계속 diff 0이고, 다섯 신규 정본 schema도 이전 고정 HEAD 대비 **diff 0**이다.
- 새 dependency·model·network **0**, 새 error code **0**, 기존 test 삭제·skip·완화 **0건**.


## 20. REVIEW-027 변경 요청 반영 기록 (같은 브랜치의 여섯 번째 후속 커밋)

REVIEW-027이 지목한 차단 결함은 **R-01·R-02·R-03 셋뿐**이다. D-04(option 3 / ADR-0029),
EVALS의 LID 미지원 계약, ARCHITECTURE의 `document_refs` 공개 계약, 다섯 정본 schema는
그대로 보존한다.

### 20.1 R-01 — 공개 경계 probe가 vacuous했다

이전 고정 HEAD의 `PB-01`~`PB-08`은 **정상 문서를 그대로** 넣었다. 여덟 probe 모두 finding이 0건이라
비노출 판정(`_unsafe_public_location`)이 한 번도 실행되지 않았고, `not bad`가 자동으로 참이었다.
그래서 `_public_boundary`를 통째로 identity decorator로 바꿔도 probe가 통과했다.

이제 각 probe는 **실제 결함**을 담고 네 가지를 함께 검증한다.

1. finding이 `min_findings` 이상 — vacuous probe 자체를 금지한다
2. 접힌 뒤의 `(code, location)` 집합이 정확히 계약대로다
3. 남은 location이 정본 경로 패턴 안이다
4. 민감 문자열이 location에도 message에도 없다

| probe | 넣은 결함 | 접힌 location | wrapper가 없을 때의 raw location |
|---|---|---|---|
| `PB-01` `check_subtitle_document` | `language_overrides`의 동적 key가 표시시간 불변식을 깬다 | `subtitle_document/resolved_style/language_overrides` | `…/language_overrides/en-x-<민감값>/max_duration_seconds` |
| `PB-02` `check_transcript` | segment duration이 0 · 호출자가 준 `location` | `""` | `<민감값>/streams/0/segments/0/end_seconds` |
| `PB-03` `check_speech_segments` | `segment_id` 중복 · 호출자가 준 `location` | `""` | `<민감값>/1/segment_id` |
| `PB-04` `check_translated_transcript` | `target_language="en"` · 호출자가 준 `location` | `""` | `<민감값>/target_language` |
| `PB-05` `check_asr_capability_binding` | `feature_status.nbest`가 capability와 모순 · 호출자가 준 `location` | `""` | `<민감값>/feature_status/nbest` |
| `PB-06` `check_translation_capability_binding` | `feature_status.translation_confidence` 모순 · 호출자가 준 `location` | `""` | `<민감값>/feature_status/translation_confidence` |
| `PB-07` `check_document_ref_identity` | 컨텍스트 없음 + 문서에 그 leaf가 없다 | `translated_transcript` | `translated_transcript/source_transcript` |
| `PB-08` `check_artifact_consistency` | 사용자 제어 최상위 key 아래 충돌 `ArtifactRef` | `""` | `<민감값>/byte_size` |

세 유출 축을 함께 덮는다.

- **문서 안의 동적 key** — `language_overrides`의 사용자 제어 tag (PB-01).
- **호출자가 준 `location` 인자** — 호출자가 넘긴 문자열도 사용자 제어 값이며, 정본 어휘가
  아니면 root로 접힌다 (PB-02~PB-06).
- **문서 집합의 최상위 key** — `check_artifact_consistency`는 입력 mapping을 그대로 훑으므로
  사용자 key가 location에 그대로 실릴 수 있다 (PB-08).

PB-07은 여기에 더해 **실제로 존재하지 않는 leaf**를 가리키지 않는다는 §8 계약을 고정한다.

- 새 source mutant **`VM-145`** — `_public_boundary`를 identity decorator로 만든다.
  `PB-01`~`PB-08` **여덟 개 전부**를 kill 조건으로 선언했고, 임시 사본에서 여덟 개가 모두 실패해
  `--check-only`가 nonzero로 끝난다.
- `run_source_mutants()`의 `caught`에 **raw JSON probe와 공개 경계 probe 실패를 더했다.**
  이 둘이 빠져 있으면 그 축만 깨는 mutant를 "잡히지 않음"으로 세게 된다.

### 20.2 R-02 — 공개 입력 경계와 런타임 전역 설정

**공개 API에서 strict loader를 뺐다.** `load_strict`/`loads_strict`는 `num-profile-v1`을 지나지
않으므로 TASK-029의 입력 경계가 아니다. 이제 내부 alias(`_load_strict`/`_loads_strict`)로만 쓰고,
공개하는 것은 `load_documents`·`loads_documents`·`assert_number_profile`·`NumberProfileError`·
`NUMBER_PROFILE_ID`·`NUMBER_MAX_INTEGER_DIGITS`다. `schema_core`는 여전히 **무변경**이며 재구현도
하지 않는다.

**계약 상한을 런타임 전역 설정에서 떼어냈다.** CPython의 `int(str)` 자릿수 상한은
`PYTHONINTMAXSTRDIGITS`와 `sys.set_int_max_str_digits()`로 낮출 수 있는 프로세스 전역 설정이다.
그 값이 계약을 바꾸면 같은 입력이 환경에 따라 다르게 판정된다.

| 입력 | 이전 고정 HEAD (`PYTHONINTMAXSTRDIGITS=640`) | 새 고정 HEAD (같은 환경) |
|---|---|---|
| 639자리 정수 | 통과 | 통과 |
| **641자리 정수** | **`NumberProfileError`(잘못된 거부)** | **통과** |
| **4,300자리 정수** | **`NumberProfileError`(잘못된 거부)** | **통과 — 계약 경계가 정확하다** |
| 4,301자리 정수 | `NumberProfileError` | `NumberProfileError` · traceback 0건 |
| 10,000자리 정수 | `NumberProfileError` | `NumberProfileError` · traceback 0건 |

`_contract_integer_limit()`는 **파싱하는 동안만** 전역 상한을 계약값(4,300)까지 올리고
`finally`에서 원래 값을 되돌린다. 상한을 없애지 않으므로 4,301자리 이상은 그대로 profile 거부다.
이미 계약값 이상이거나 무제한(0)인 환경에서는 아무것도 바꾸지 않는다.

- 새 raw JSON probe **`RJ-18`~`RJ-21`** — 전역 상한을 640으로 낮춘 채 production을 그대로 부른다
  (639 대조군 / 641 / 4,300 / 4,301). 분모 17 → **21**.
- 새 source mutant **`VM-146`** — 상한을 다시 전역 설정에 종속시킨다. `RJ-19`·`RJ-20`이 kill한다.
- **완화 없음**: 중복 key·`NaN`/`Infinity`·lossy decimal 거부는 낮춘 상한 아래에서도 그대로다.
  계약 test가 그 넷을 직접 확인한다.

### 20.3 R-03 — 갱신 도구가 분류를 **다시 관측**한다

이전 판의 `--write-manifest`는 이전 파일의 `defense_id`만 보고 equivalent 여부와 사유를 그대로
옮겼다. 그래서 `extension_id`의 pattern을 `^.*$`로 약화해 `minLength`가 독립 방어가 된 뒤에도
갱신 도구가 stale equivalent를 보존한 채 **exit 0**으로 끝났고 직후 `--manifest-check`도 통과했다.
분류 오류는 전체 감사에서만 드러났다.

| 단계 | 이전 고정 HEAD | 새 고정 HEAD |
|---|---|---|
| `--manifest-check` (약화 직후) | 1 | 1 |
| `--write-manifest` | **0 · stale equivalent 보존** | **1 · 파일을 쓰지 않는다** (`MF-09`) |
| `--write-manifest --reclassify` | — | **1** — `minLength`는 killable로 옳게 재분류되지만 pattern 방어가 죽어 분류 inventory가 통과하지 못한다 (`MF-10`) |
| `--manifest-check` (write 뒤) | 0 (거짓 통과) | 1 |
| `--classification-check` | — | 1 |

바꾼 것:

1. **분류의 정본은 관측이다.** `classify_schema_defenses()`가 manifest를 읽지 않고 현재
   schema에서 각 방어의 `subsumed`를 다시 관측한다. manifest는 그 관측을 **고정**할 뿐이다.
2. 관측이 이전 파일의 분류와 다르면 — 새 방어가 처음부터 equivalent인 경우 포함 —
   `--reclassify` 없이는 **쓰지 않고** exit 1이다 (`MF-09`). 사라진 방어는 drift가 아니다.
3. 쓴 직후 자기검증이 `--manifest-check`뿐 아니라 **분류 inventory까지** 돌린다 (`MF-10`).
   둘 다 통과할 때만 exit 0이다. drift 검사만으로는 방어가 아예 죽은 경우를 잡지 못한다.
4. 재분류로 새로 equivalent가 된 방어의 사유는 이전 사유를 물려받지 않고 **재분류 표식**을
   붙여 사람이 diff에서 바로 알아보게 한다.
5. 새 CLI `--classification-check` — 관측과 manifest 분류의 일치만 따로 확인한다.

- `--manifest-check`의 분모는 `MF-01`~`MF-08` 그대로다. `--write-manifest`의 **자기검증**에
  `MF-09`(명시적 재분류 없이 쓰지 않는다)와 `MF-10`(쓴 직후 분류 inventory가 통과한다)이
  더해졌다.
- drift 자기검증에 **`SD-14`**(재분류 승인 없이 갱신 거부)와 **`SD-15`**(승인해도 죽은 방어는
  성공하지 못함)를 더했고, 성공 경로인 `SD-13`에 `--classification-check` 단계를 더했다.
  분모 13 → **15**.
- `AS-04`(갱신 도구가 stale digest를 쓰면 스스로 실패)는 그대로 유지된다.

### 20.4 보존 확인

- D-04 option 3와 **ADR-0029**, EVALS §4.5의 공식 LID 정확도 `unsupported` 계약, §19가 고정한
  다섯 경계는 **문구·기계 정본 모두 무변경**이다.
- ARCHITECTURE §2.1.1의 `document_refs` 공개 계약도 무변경이다.
- 다섯 신규 정본 schema는 이전 고정 HEAD 대비 **diff 0**이고, `schema_core.py`·
  `artifact_store.py`·`job_runtime.py`(`CACHE_KEY_FIELDS` 포함)·`common-v1`·`job-v1`은
  `main` 대비 **diff 0**이다.
- 신규 dependency·model·network·CI **0**, 새 error code **0**.
- **기존 test 삭제·skip·완화 0건.** `defense-manifest.json`의 변경은 `note` 한 줄뿐이며
  `killable`/`equivalent` 목록과 digest는 그대로다.

### 20.5 이 반영에서 정하지 않은 것

§17.8의 오너 결정 항목 아홉 개는 그대로 열려 있다. 그중 5번(`loads_strict()` duplicate-key
message의 전체 CLI 비식별화)은 `schema_core`의 message 정책이므로 이번 공개 API 정리로
해소되지 않는다 — 이름만 내부 alias로 바뀌었을 뿐이다.


## 21. REVIEW-027 재검토 반영 기록 (같은 브랜치의 일곱 번째 후속 커밋)

> **정정 (§22 후속 기록).** 아래 "R-02C·R-03C 둘뿐"은 **그 시점의 기록**이다. 같은 고정
> HEAD `0fcb22b`에서 이후 **R-01C**(공개 `check_*`의 `__wrapped__` 우회)가 추가로 발견됐다.
> 아래 문장을 지우지 않고 그대로 두며, 발견과 대응은 **§22**에 적는다.

이번 재검토가 지목한 차단 결함은 **R-02C·R-03C 둘뿐**이다. §19의 D-04 option 3(ADR-0029),
EVALS의 공식 LID 정확도 `unsupported` 계약, ARCHITECTURE의 `document_refs` 공개 계약,
§20의 R-01 공개 경계 probe(`PB-01`~`PB-08`)와 `VM-145`는 그대로 보존한다.

### 21.1 R-02C — 공개 loader가 프로세스 전역 정수 정책을 바꿨다

§20.2의 `_contract_integer_limit()`은 파싱하는 동안 `sys.set_int_max_str_digits()`를 올렸다가
되돌렸다. 그 값은 **프로세스 전역**이므로,

- 겹치는 두 loader 호출 중 먼저 끝난 쪽이 640으로 복원하면 나머지 호출이 계약 안 입력을
  `NumberProfileError`로 실패시킬 수 있고,
- loader가 도는 동안 **무관한 thread**의 `int("1" * 641)`이 일시적으로 성공한다.

두 번째는 이 저장소에서 직접 재현했다 — 이전 고정 HEAD `c0dec2e`에서 loader 6 thread가 도는
동안 관찰 thread의 계약 밖 정수 변환이 **8,693회** 성공했다. lock으로 감싸는 방식은 외부
thread의 정책을 여전히 바꾸므로 해결이 아니다.

**전역 대신 hook을 바꿨다.**

| 무엇 | 어떻게 |
|---|---|
| 정수 변환 | `int(str)`의 자릿수 상한만이 전역 설정이다. 640자리(`sys.int_info.str_digits_check_threshold`, 어떤 설정에서도 변환되는 하한) 이하는 `int()`를 그대로 쓰고, 그보다 긴 리터럴만 `Decimal`을 거쳐 만든다. `Decimal` → `int`는 문자열 변환이 아니라 그 상한에 걸리지 않는다 |
| 계약 상한 | `_profile_integer()`가 **변환 전에** 자릿수를 본다. 4,301자리 이상은 그대로 `NumberProfileError` → CLI `E_JSON` · exit 2 · traceback 0건 |
| 중복 key·NaN/Infinity | `schema_core.loads_strict()`가 쓰는 **바로 그 두 hook**(`_reject_duplicate_keys`·`_reject_constant`)을 그대로 합성한다 |

**왜 `loads_strict()`를 그대로 부르지 않는가.** 그 함수는 `parse_int`를 받지 않는다. 그러니
계약 상한(4,300자리)을 지키면서 그 함수를 쓰려면 전역을 건드리는 수밖에 없었다. 그래서 함수가
아니라 **그 함수의 구성요소**를 쓴다. 다시 구현하지도, 약화하지도 않는다. `schema_core.py`는
무변경이다.

이 선택이 조용히 갈라지지 않도록 `StrictLoaderCompositionTests`가 셋을 함께 고정한다.

1. 합성에 쓰는 두 callable이 `schema_core`의 것과 **같은 객체**인가 (`assertIs`)
2. `schema_core.loads_strict()`의 구성이 그대로인가 — 두 hook을 쓰고 `parse_int`/`parse_float`는
   받지 않는가 (받게 되면 합성할 이유가 사라지므로 그때 다시 판단해야 한다)
3. 정상·중복 key·`NaN`/`Infinity`·구문 오류·비객체 root 10건에서 두 경로의 **결과와 예외가
   같은가** (차등 test)

**확인한 불변식**

| 불변식 | 확인 |
|---|---|
| 공개 loader가 전역 상한을 읽지도 쓰지도 않는다 | AST에 `set_int_max_str_digits`·`get_int_max_str_digits` 호출 0건 · 실제 loader 실행 중 setter spy 호출 **0회** |
| 겹치는 실제 loader 호출이 결정적이다 | 전역 상한 640에서 6 thread × 20회 × 4,300자리 → 실패 **0건** |
| 무관한 thread의 정책이 전·중·후 동일하다 | 관찰 thread의 641자리 `int()` 성공 **0회**, 관측된 전역 상한 집합 `{640}` |
| 639·641·4,300자리 성공 | 유지 |
| 4,301자리 이상 거부 | `E_JSON num-profile-v1 …` · traceback 0건 |
| 중복 key·`NaN`/`Infinity`·lossy decimal 거부 | 유지 |
| `load_strict`/`loads_strict` 공개 금지 | `__all__`과 module attribute 양쪽에 없음 |

- 새 source mutant **`VM-146`**(정수 변환을 전역에 다시 종속시킨다) → `RJ-19`·`RJ-20`이 kill.
- 새 source mutant **`VM-147`**(합성 parse에서 중복 key hook 제거) → `RJ-16`이 kill.
- 새 source mutant **`VM-148`**(합성 parse에서 상수 거부 hook 제거) → `RJ-17`이 kill.
  뒤 둘이 strict-loader 계약이 합성 경로에서 **실제로 살아 있음**을 증명한다.

### 21.2 R-03C — 분류가 첫 candidate에서 조기 성공했다

`_probe_defense()`는 위반 후보를 순서대로 시도하다가 **처음** 탐지된 후보에서 곧바로 반환했다.
그 후보가 같은 노드의 다른 제약에 먼저 걸리면 `subsumed=True`가 되고, 뒤에 있는 진짜 witness는
검사되지 않았다.

재검토가 제시한 반례를 그대로 재현했다 — `extension_id.pattern`을
`^x-(?:[A-Za-z0-9][A-Za-z0-9._:-]*)?$`로 바꾸면 `aa`는 pattern에 걸리지만 `x-`는 길이 2라서
**`minLength: 3`만** 어긴다.

| 단계 | 이전 고정 HEAD `c0dec2e` | 새 고정 HEAD |
|---|---|---|
| `--classification-check` | **0** (stale equivalent 유지) | **1** |
| `--manifest-check` | 1 | 1 |
| `--write-manifest` | **0** (stale 분류를 그대로 씀) | **1** (쓰지 않음) |
| `--write-manifest --reclassify` | — | **0** — killable 292 / equivalent 1로 옳게 재분류 |
| 재분류 뒤 `--manifest-check` · `--classification-check` | — | **0 · 0** |

> `--check-only`는 이 반례에서 이전에도 지금도 exit 0이다. 그 명령은 fixture·input mutation·
> leak·depth·raw JSON·공개 경계 probe만 돌리며 **분류 inventory를 포함하지 않는다.**
> 분류의 gate는 `--classification-check`와 `make audit-task-029`이고, 둘 다 이 반례에서
> 실패한다. 이 사실을 숨기지 않고 여기 적는다.

바꾼 것:

1. **모든 후보를 평가한다.** 독립적으로 killable한 witness가 하나라도 있으면 그것이 정답이며
   `equivalent`로 판정하지 않는다. 탐지된 후보가 전부 가려진 경우에만 `subsumed`다.
2. **instance site 루프에도 같은 우선순위를 적용한다.** 어떤 instance에서 가려졌다고 다른
   instance에서도 가려지는 것은 아니다.
3. 정본 schema에서는 두 `minLength`가 그대로 `equivalent`다 — 과잉 재분류가 일어나지 않는다는
   것도 test로 고정했다.

### 21.3 R-03C — manifest 원자성

이전 판은 `path`에 **먼저 쓰고** 자기검증했다. 그래서 `^.*$`처럼 방어 자체가 죽은 반례에서
`--write-manifest --reclassify`가 exit 1로 끝나면서도 파일은 이미 바뀌어 있었다.

지금은 **임시 sibling(`defense-manifest.json.staging`)에 staging**하고,
`--manifest-check` 자기검증과 **분류 inventory**가 둘 다 통과한 뒤에만 `os.replace()`로
원자적으로 교체한다. 하나라도 실패하면 staging만 지우고 기존 bytes는 그대로 둔다.

| 반례 | exit | manifest bytes | staging 잔여물 |
|---|---|---|---|
| `^.*$` + `--write-manifest` | 1 (`MF-10`·`MF-11`) | **보존** | 없음 |
| `^.*$` + `--write-manifest --reclassify` | 1 (`MF-10`·`MF-11`) | **보존** | 없음 |
| alternate pattern + `--write-manifest` | 1 (`MF-09`) | **보존** | 없음 |
| alternate pattern + `--write-manifest --reclassify` | 0 | 재분류 반영 | 없음 |
| 정본 schema + `--write-manifest` | 0 | 동일 내용 | 없음 |

- 자기검증에 **`MF-11`**(자기검증을 모두 통과한 뒤에만 원자적으로 교체한다)을 더했다.
  `--manifest-check`의 분모는 여전히 `MF-01`~`MF-08`이고, `MF-09`~`MF-11`은 갱신 도구의
  자기검증이다.
- drift 자기검증에 **`SD-16`**(alternate pattern 반례 6단계)을 더했다. `SD-15`에는 재분류
  실패 뒤 `--manifest-check`가 여전히 1인지 확인하는 단계를 더했다. 분모 15 → **16**.

### 21.4 보존 확인

- §19의 D-04 option 3·ADR-0029, EVALS §4.5의 LID `unsupported` 계약,
  ARCHITECTURE §2.1.1·§3.0.2는 **diff 0**이다.
- §20의 `PB-01`~`PB-08` non-vacuous probe와 `VM-145`는 그대로다.
- `schema_core.py`·`artifact_store.py`·`job_runtime.py`(`CACHE_KEY_FIELDS` 포함)·
  `common-v1`·`job-v1`·다섯 신규 정본 schema는 무변경이다.
- 신규 dependency·model·network·CI **0**, 새 error code **0**,
  기존 test 삭제·skip·완화 **0건**.

### 21.5 이 반영에서 정하지 않은 것

§17.8의 오너 결정 항목 아홉 개는 그대로 열려 있다. `schema_core.loads_strict()`에
`parse_int`/`parse_float` hook을 추가할지는 **schema_core 소유자의 결정**이며 여기서 바꾸지
않았다. 추가된다면 이 모듈은 hook 합성을 그만두고 그 함수를 그대로 부르면 된다 —
`StrictLoaderCompositionTests`가 그 시점을 실패로 알려 준다.


## 22. REVIEW-027 R-01C 반영 기록 (같은 브랜치의 여덟 번째 후속 커밋)

§21은 그 시점의 차단 결함을 R-02C·R-03C 둘로 기록했다. 그 기록은 그대로 둔다. 같은 고정
HEAD `0fcb22b`에서 **R-01C**가 추가로 발견됐고, 이번 커밋은 **그 하나만** 반영한다.

### 22.1 무엇이 열려 있었나

§8.2는 비식별화 계약이 schema finding·domain finding·container 조기 반환·**공개 `check_*`
진입점**에 모두 같게 적용된다고 규정한다. `_public_boundary()`는 그 접기를 수행하지만
`functools.wraps(function)`을 썼고, 그 decorator는 편의를 위해 `wrapper.__wrapped__`에
**접기 전 구현을 공개 attribute로 그대로 노출**한다.

| 호출 경로 | `0fcb22b`의 결과 |
|---|---|
| `check_transcript(..., location="PATIENT_SECRET")` | `E_TIME_RANGE @ ""` — 계약대로 |
| `check_transcript.__wrapped__(...)` | `E_TIME_RANGE @ PATIENT_SECRET/streams/0/segments/0/end_seconds` |
| `inspect.unwrap(check_transcript)(...)` | 위와 동일 |

여덟 공개 함수 **전부**에서 `callable(fn.__wrapped__)`가 참이고
`inspect.unwrap(fn) is fn`이 거짓이었다. 이 경계 코드는 `c0dec2e`와 `0fcb22b` 사이에서
바뀌지 않았고, 기존 `PB-01`~`PB-08`과 `VM-145`는 **정상 wrapper 호출**과
**identity-decorator 변형**만 봤기 때문에 이 표준 introspection 우회를 잡지 못했다.

### 22.2 무엇을 바꿨나

`_public_boundary()`에서 `functools.wraps` decorator를 쓰지 않는다. 이름·docstring·annotation은
`functools.update_wrapper()`로 그대로 유지하고, 그 함수가 **마지막에 붙이는 raw 구현 참조만**
지운다. `inspect.signature()`가 계속 실제 서명을 보도록 `__signature__`를 직접 붙인다.

```
functools.update_wrapper(wrapper, function)
del wrapper.__wrapped__
wrapper.__signature__ = signature
```

**범위를 넓히지 않았다.** 이것은 Python의 임의 private introspection 전체를 보안 경계로
선언하는 것이 아니다. closure cell처럼 문서화되지 않은 내부 접근은 어떤 wrapper로도 막을 수
없고 여기서 막았다고 주장하지 않는다. 닫은 것은 **공개 callable에 표준 attribute로 노출되던
우회 하나**다.

| 확인 | 여덟 함수 전부 |
|---|---|
| `callable(fn.__wrapped__)` | **거짓** (attribute 자체가 없음) |
| `inspect.unwrap(fn) is fn` | **참** |
| `fn.__name__` · `fn.__doc__` · `inspect.signature(fn)` | 유지 |
| 민감 문자열로 호출한 finding의 location·message | sentinel 없음 |
| 접힌 location | §8.2 정본 경로와 정확히 일치 |

### 22.3 감사 증거를 함께 고쳤다

test assertion만 늘리지 않고 **audit 자체**가 이 우회를 보게 했다.

- `BoundaryProbe`에 **공개 함수 객체**(`public`)를 담고, `run_boundary_probes()`가 호출 결과를
  보기 **전에** 그 객체의 introspection 표면을 검사한다 — callable `__wrapped__`가 있거나
  `inspect.unwrap()`이 다른 callable을 돌려주면 그 probe는 즉시 실패다.
- 새 source mutant **`VM-149`** — `del wrapper.__wrapped__`와 `__signature__` 부착을 지워
  `functools.wraps`와 동등한 상태로 되돌린다. `PB-01`~`PB-08` **여덟 개 전부**를 kill 조건으로
  선언했고, 저장소 밖 임시 사본에서 여덟 probe가 모두 실패하며 `--check-only`가 exit 1이다.
- validator code mutant 분모 143 → **144**. `VM-145`(identity decorator)는 그대로 유지된다 —
  두 mutant는 서로 다른 우회를 본다.

### 22.4 보존 확인

- §21의 **R-02C** 정수 parsing과 프로세스 전역 격리, **R-03C**의 전체 candidate 분류와 원자적
  manifest 교체는 코드·자기검증 모두 무변경이다.
- §19의 D-04 option 3·ADR-0029, EVALS의 공식 LID 정확도 `unsupported` 계약,
  ARCHITECTURE §2.1.1의 `document_refs` 공개 계약은 **diff 0**이다.
- `PB-01`~`PB-08`의 기존 non-vacuous 검증(실제 finding·정확한 code/location·경로 패턴·민감
  문자열 비노출)은 그대로이고 여기에 introspection 검사가 **더해졌다**.
- §8의 안정 error code 22개, 다섯 정본 schema, `schema_core.py`·`artifact_store.py`·
  `job_runtime.py`, dependency·model·network·CI 경계 모두 무변경이다.
- 기존 test 삭제·skip·완화 **0건**. `defense-manifest.json`은 새 schema 방어가 없으므로
  갱신 대상이 아니다 (무변경).

### 22.5 이 반영에서 정하지 않은 것

§17.8의 오너 결정 항목 아홉 개는 그대로 열려 있다. closure cell을 포함한 문서화되지 않은
introspection 경로는 이 계약의 보증 대상이 아니며, 그렇게 주장하지도 않는다.
