# REVIEW-023 — TASK-029 fixed-HEAD Gate H review

- 대상 PR: #45
- 대상 브랜치: `claude/task-029-subtitle-spine-contracts`
- 고정 HEAD: `66141c2c838a3c8adf67356d643d2415877a807e`
- tree: `fc061ceea1a925c0ff7e88a5aa8f3ab9426524f3`
- 기준 main: `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`
- 검토일: 2026-08-30
- 판정: **변경 요청**
- 병합/Ready 전환: 승인하지 않음

## 1. 고정 상태와 직접 검증

PR #45는 검토 시점에 open, draft, unmerged, mergeable clean이며 기준 main 대비 ahead 1 / behind 0이었다. 변경 파일은 TASK-029 범위의 schema, domain validator, fixture/test/audit, 문서에 한정되어 있었다.

다음을 고정 HEAD에서 직접 실행해 모두 통과함을 확인했다.

| 명령 | 결과 |
|---|---|
| `make verify-task-029` | exit 0; fixture 57/57, input mutants 121/121, schema mutants 17/17, validator mutants 78/78 |
| `make verify-task-028` | exit 0; runtime fixture 16/16, artifact-store 36, job-runtime 149 |
| `make verify-task-006` | exit 0; H 14/14, 계약 162 |
| `make verify` | exit 0; 전체 387, FFmpeg smoke PASS |
| `make verify-task-029 PYTHON=python3.12` | exit 0 |

기존 cache key/canonical bytes guard와 `schema_core.py` 비변경도 확인했다. 그러나 아래 반례는 선언된 테스트·mutation 분모 밖에 있으며, 정상 실행 경로에서 계약 위반 문서를 조용히 유효 처리한다. 따라서 전체 테스트 통과만으로 Gate H를 승인할 수 없다.

## 2. Blocking findings

### B-01 — 시간·stream·lineage의 교차 문서 결박이 불완전하다

다음 변형이 모두 finding 없이 유효 처리된다.

1. Transcript segment의 구간 양 끝점은 SpeechSegment 합집합 안에 있지만 중간 gap을 가로지르는 경우
2. Transcript/TranslatedTranscript/SubtitleDocument timebase를 SpeechSegment와 무관한 동일 값으로 바꾼 경우
3. Transcript segment, translated fragment 또는 cue의 stream을 참조 원본과 다른 stream으로 바꾼 경우
4. merged translation의 source fragment ID 순서를 뒤집은 경우
5. cue의 렌더링 line 순서를 뒤집고 fragment의 `line_index`만 함께 바꾼 경우
6. translated stream/segment ID 또는 cue ID가 중복된 경우

이는 TASK-029의 원본 시간축, source fragment 원순서, cue text 보존, 유일한 참조 해석 요구를 위반한다. 일부 경로에서는 dict 구축의 last-write-wins로 lineage가 모호해진다.

필수 수정:

- segment 전체 interval이 참조 SpeechSegment interval 합집합에 빈틈 없이 포함되는지 검사
- Speech → Transcript → Translation → Subtitle의 timebase/stream/ref 결박
- Transcript/translation/subtitle 각 계층의 요구되는 ID 유일성
- merged source fragment의 원문 순서
- 실제 렌더링 line 순서와 `line_break`를 포함한 source text 보존
- 위 반례 각각의 안정적인 error_code/error_location과 정상 sentinel

### B-02 — capability/field-absence 진실성과 민감 값 비노출이 불완전하다

다음이 유효 처리된다.

- 지원하지 않거나 결과가 없는 LID/nbest 필드를 빈 배열로 채우는 경우
- stream-level `speaker_label_source="adapter"`인데 diarization/channel capability 근거가 없는 경우
- capability snapshot의 adapter identity/version이 산출물 provenance와 맞지 않는 경우
- `overlap_kind="none"`과 concurrent stream 참조가 함께 있는 경우

또한 schema enum 위반의 실제 값이 finding message에 포함된다. 예를 들어 review reason에 민감 문자열을 넣으면 그 문자열이 그대로 `E_SCHEMA` message에 노출된다. TASK-029 §8의 민감 actual value 비노출 요구 위반이다.

필수 수정:

- capability가 false/not_requested/no_result인 대응 필드는 빈 값이 아니라 **부재**하도록 검사
- capability snapshot과 provenance adapter identity/version 결박
- stream/segment speaker evidence와 diarization/channel capability 결박
- overlap 의미의 모순 차단
- `schema_core.py`를 바꾸지 않고 TASK-029 domain boundary에서 schema finding을 안정적으로 정규화·비식별화
- 민감 문자열이 message에 나타나지 않는 직접 회귀 테스트

### B-03 — mutation 감사의 분모와 sentinel 보고가 수용 기준을 증명하지 못한다

현재 100% 수치는 선언된 mutant manifest 안에서는 재현되지만, 계약 방어면의 완전성은 증명하지 못한다.

- validator mutant 78개는 수동 선언된 anchor만 검사한다. duplicate ID, confidence branch, speaker evidence, token/segment containment 등 여러 의미 분기를 무력화한 추가 mutant가 모두 생존한다.
- schema mutant 17개도 root `additionalProperties`, 필수 필드, enum 확장 같은 기본 방어 변형을 놓친다.
- 여러 kill case를 선언한 mutant가 그중 하나만 잡혀도 전체 detected로 계산된다.
- fixture/input의 valid-case sentinel 출력은 실제 각 row의 sentinel 실행값이 아니라 총 row 수를 그대로 표시한다.

필수 수정:

- schema와 validator의 의미 방어면을 추적하는 명시적 coverage inventory/guard 추가
- 선언된 kill case가 여러 개인 mutant는 모두 충족되어야 killed 처리
- fixture/input/schema/validator 각 분모의 실제 valid-case sentinel을 실행·집계
- 위 B-01/B-02 반례와 최소한 duplicate Transcript stream/segment ID, token-before-segment, confidence/speaker branch, schema root closed-object/required/enum 방어 mutant 포함
- SKIP 0, 각 분모 100%, sentinel 실제 결과를 재현 가능한 출력으로 보고

## 3. 문서 정합성 finding

### D-01 — LID authority 설명이 ARCHITECTURE/EVALS와 충돌한다

구현 기록은 Transcript `language_spans`를 언어 authority라고 설명하지만 ARCHITECTURE §3.0의 평가 정답 authority는 `ReferenceBundle.language_spans`다. 또한 EVALS에는 새 SubtitleDocument schema가 허용하지 않는 cue `language_spans` 경로가 남아 있다.

cue에 독립 LID 필드를 두지 않은 설계 자체는 유지 가능하다. 문서는 다음 세 축을 분명히 구분해야 한다.

- `ReferenceBundle.language_spans`: 평가용 ground truth
- `Transcript.language_spans`: ASR/LID hypothesis의 단일 원천
- `SubtitleDocument`: 독립 LID hypothesis 없음; 필요하면 exact lineage를 통해 Transcript span을 결정론적으로 투영

EVALS의 불가능한 cue-span 경로와 구현 기록의 잘못된 authority 설명을 함께 고쳐야 한다. 번역문과 원문이 문자열상 같은 경우를 구조적으로 거부하지 않은 결정은 타당하다. 동일 문자열은 QC 신호일 수 있으나 오류의 충분조건은 아니다.

## 4. 승인된 부분과 비차단 사항

다음 설계는 유지한다.

- 다섯 schema의 기계 정본화와 TranslationCapabilityReport 단일 정의
- `schema_core.py`를 확장하지 않고 교차 필드 규칙을 domain validator에 둔 경계
- optional timestamp/confidence를 조작해 채우지 않는 원칙
- source/target 축과 dropped/untranslated 표현의 구조적 분리
- 기존 cache/checkpoint/resume/canonical bytes 불변
- cue에서 독립 confidence/speaker/LID authority를 만들지 않은 축소 설계

fixture 약 30,692줄은 유지보수 비용이지만 현재 Gate H의 correctness blocker는 아니다. Windows/NTFS, 실제 adapter, WER/RTF/VRAM/사람 수정시간은 TASK-029 비범위이며 이 검토도 해당 성능을 승인하지 않는다.

## 5. 재검토 조건

PR #45는 Draft로 유지한다. 작성자는 같은 PR에 수정 commit을 추가하고 새 고정 HEAD를 보고한다. 다음을 모두 만족하면 새 HEAD로 Gate H를 다시 수행한다.

1. B-01/B-02 반례가 안정적인 기존 error code와 location으로 거부됨
2. B-03의 분모·kill 판정·sentinel 집계가 실제 의미 방어면을 검증함
3. D-01 문서 모순이 해소되고 unresolved contradiction이 0임
4. `schema_core.py`, cache key, 기존 job/artifact canonical bytes 변경 0
5. 신규 dependency/model/network 0
6. TASK-029/028/006, 전체 verify, Python 3.12 검증이 모두 통과
7. Ready 전환·merge·자기 승인은 제품 오너의 별도 승인 전 수행하지 않음

## 6. 별도 상태 정합성 작업

기능 수정과 섞지 않고 Lean Root가 별도 변경으로 다룬다.

- STATUS의 TASK-029 “구현 시작 금지/제안” 잔존 문구 정리
- PR 목록에 병합된 #44와 open Draft #45 반영
- PLAN의 미확정 candidate 문구 정리
- 이 계약 PR로 확정되는 architecture 결정을 DECISIONS에 기록

이 상태 정합성 작업은 위 기능 blocker를 대신하지 않으며, PR #45 승인 조건과 분리한다.
