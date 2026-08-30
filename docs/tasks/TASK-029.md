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

`docs/EVALS.md`의 Transcript offset 투영도 좁게 정합화한다. raw Transcript는 exact segment `text`와
ASR segment/token timing을 기준으로 투영하고, SubtitleDocument만 `lines[]`를 결합한
`canonical_cue_text`를 쓴다. 두 text space를 하나로 취급하지 않는다.

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
`dominant_language?`·`confidence?`·`speaker_label?` 넷을 정본에 넣지 않았다. 언어의 authority는
`Transcript.language_spans` 하나여야 하고(§3.0), 자막 계층에는 confidence·speaker label을 결박할
capability 축이 없어 근거 없는 값이 되기 때문이다. 산문은 지우지 않고 보존했다.

### 14.6 fixture (57건)

정상 3건이 §9가 요구한 일곱 경로를 모두 담는다.

| fixture | 담은 경로 |
|---|---|
| `k-01` | JA/EN 문장 내 전환 · explicit `und` · gap→unknown+review와 `dominant_language` 생략 · 실제 independent channel과 다른 stream의 동시 segment/cue · one_to_one/merged/split/dropped/unknown 번역 lineage · target axis emoji(U+1F44D)+combining(U+0301) cue lineage · 다른 stream cue overlap 허용 |
| `k-02` | timing·confidence·LID를 **전부 미지원**해 필드가 정직하게 생략된 Transcript · source axis 자막 · emoji/combining scalar offset · 공백 없는 일본어 `日本語 → ["日","本語"]` 분할 · 영어 공백을 explicit `line_break_whitespace`로 옮긴 분할 |
| `k-03` | partial 번역 — uncovered fragment가 남은 원문 범위를 정확히 한 번 채우고 `needs_review`와 안정 reason을 남김 |

위반 54건은 §9 mutation 목록에 1:1 대응하며 각 fixture의 `mutation_id`가 그 대응을 기록한다.

### 14.7 mutation 감사 — 세 분모를 섞지 않았다

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

### 14.8 실행한 검증

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

### 14.10 미해결 교차 계약 모순

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
