# REVIEW-024 — TASK-029 second fixed-HEAD Gate H review

- 대상 PR: #45
- 대상 브랜치: `claude/task-029-subtitle-spine-contracts`
- 고정 HEAD: `7b627e9755f786793b1ae898cf76053d238f0bf5`
- tree: `7072a1b2c73cb7a8f9f7ad9c14dfa9cb169198b9`
- 직접 부모: `66141c2c838a3c8adf67356d643d2415877a807e`
- 기준 main: `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`
- 검토일: 2026-08-30
- 판정: **변경 요청**
- 병합/Ready 전환: 승인하지 않음

## 1. 고정 상태와 직접 재현

PR #45는 검토 시점에 open, draft, unmerged, mergeable clean이며 main 대비 ahead 2 / behind 0이었다. 커밋·tree·부모는 제출 보고와 일치했다.

원격 저장소의 해당 commit을 직접 고정한 환경에서 다음 결과를 재현했다.

| 명령 | 결과 |
|---|---|
| `make verify-task-029` | exit 0; fixture 104/104, subtitle tests 43, 전체 398 |
| `make audit-task-029` | exit 0; 보고된 7개 분모 전부 100%, SKIP 0 |
| `make verify-task-028` | exit 0; J 16/16, artifact-store 36, job-runtime 149 |
| `make verify-task-006` | exit 0; H 14/14, 계약 162 |
| `make verify` | exit 0; 전체 398, FFmpeg smoke PASS |
| `make verify-task-029 PYTHON=python3.12` | exit 0 |
| `git diff --check`, `git status --short` | exit 0, 무출력 |

독립 재현 환경의 기본 `python3`도 Python 3.12.13이므로 제출자가 보고한 Python 3.11 실행은 이번 리뷰 환경에서 별도로 재현하지 못했다. 이는 현재 판정의 blocker는 아니다.

## 2. REVIEW-023 해소 확인

다음 기존 blocker는 새 HEAD에서 정상적으로 거부됨을 직접 확인했다.

- SpeechSegment 합집합 내부 gap을 가로지르는 ASR interval
- Speech → Transcript → Translation → Subtitle timebase·stream 불일치
- translated stream/segment 및 cue ID 중복
- merged source fragment와 실제 cue rendering 순서 역전
- unsupported field의 빈 배열 위장
- capability snapshot과 provenance adapter identity/version 불일치
- `overlap_kind="none"`과 concurrent stream 참조 모순
- schema enum 위반의 민감 actual value message 노출

multi-kill은 선언된 kill case 전부를 요구하도록 수정됐고, 현재 input sentinel과 message redaction의 정상 동작도 확인했다. 그러나 아래 인접 계약과 감사 gate가 여전히 조용히 통과하므로 Gate H는 승인할 수 없다.

## 3. Blocking findings

### H-01 — ArtifactRef 계보가 실제 문서 관계에 결박되지 않는다

다음 입력이 finding 없이 `VALID`이다.

1. target SubtitleDocument의 `source_transcript_ref`를 TranslatedTranscript의 `source_transcript`와 다른 artifact ID/hash로 변경
2. SubtitleDocument의 `input_document_ref`를 `kind=video, media_type=video/mp4`로 변경
3. TranslatedTranscript의 `source_transcript`를 video ref로 변경
4. translation과 subtitle의 source refs를 함께 별도 detached chain으로 변경

이는 TASK §4.4/§4.5의 “입력 Transcript”, “직접 입력 TranslatedTranscript”, 원본 증거 계보 의미를 검증하지 못한다. 최소한 현재 문서 집합 안에서 확인 가능한 다음 동일성은 강제해야 한다.

- target SubtitleDocument.`source_transcript_ref` == TranslatedTranscript.`source_transcript`
- 각 ArtifactRef가 기대하는 document kind/media type과 일치
- 직접 입력 ref와 실제 제공 document 사이의 identity

현재 validator API에 실제 document self ArtifactRef가 없어 마지막 항목을 검증할 수 없다면, 구현자가 임의 값을 가정하지 말고 계약/API blocker로 올려야 한다. “필드가 존재한다”만 검사하는 것은 수용할 수 없다.

### H-02 — `speaker_label_source="input"`이 실제 입력 label 값과 결박되지 않는다

다음 입력이 `VALID`이다.

- SpeechSegment label이 `SPK-A`인데 Transcript segment가 `SPK-B/source=input`
- stream-level `speaker_label_source=input`인데 해당 입력 SpeechSegment에 label이 하나도 없음
- segment label이 임의 값이고 diarization status가 `no_result`인 경우

현재 segment 검사는 참조 SpeechSegment 중 label이 하나라도 존재하는지만 보고 실제 label equality를 검사하지 않는다. stream-level input 분기는 입력 근거를 검사하지 않는다. 기존 정상 fixture K-19 자체도 upstream label과 Transcript label이 다르므로 exact-copy 의미를 고정하지 못한다.

필수 수정:

- segment input label은 참조 SpeechSegment label과 정확히 일치
- stream input label은 해당 stream의 입력 label 근거와 일치
- 여러 입력 label이 있어 단일 값으로 결정할 수 없으면 조용히 임의 선택하지 않고 review/error 경계를 명시
- 정상 sentinel도 실제 동일 label을 사용

### H-03 — capability 내부 논리와 산출 evidence 결박이 불완전하다

다음 모순이 모두 `VALID`이다.

- `supported_languages=[]`이면서 `limitations=[]`
- 출력에 JA span이 있지만 ASR `supported_languages=["en"]`
- `supports_language_id=false`인데 `supports_intra_sentential_lid=true`
- LID 미지원인데 `language_confidence_semantics!="none"`
- `supports_nbest=false`인데 `nbest_score_semantics!="none"`
- JA/EN 원문을 번역했는데 translation capability의 `supported_source_languages=["ko"]`

필수 수정:

- capability 내부 implication을 명시적으로 검사
- 실제 산출 evidence의 언어가 capability의 지원/제한 표현과 모순되지 않도록 결박
- 빈 supported list를 “모든 언어/미상/미지원” 중 무엇으로 해석하는지 계약대로 고정하고, 현재 TASK §4.3 요구처럼 비어 있다면 명시적 limitation을 요구
- corresponding fixtures/input mutants/validator mutants와 정상 sentinel 추가

### H-04 — mutation 감사가 필수 schema/depth 방어를 분모에 포함하지 않는다

공식 100%는 재현됐지만 다음 추가 mutant가 모두 `detected=false, sentinel_ok=true`였다.

Schema required 방어 제거:

- SpeechSegment.`source_track_index`
- Transcript.`transcript_id`
- AdapterCapabilityReport.`network_requirement`
- TranslatedTranscript.`source_transcript`
- SubtitleDocument.`input_document_ref`

Validator depth 방어 제거:

- confidence finite 검사
- half-open interval 음수 start 검사
- token finite 검사

원인은 다음과 같다.

- schema mutants는 22개 수동 표본뿐이고 production schema defense inventory가 없다.
- source mutant 실행은 fixture/input/leak만 실행하며 depth probes를 mutant 실행에 결박하지 않는다.
- depth probes는 변경되지 않은 production validator에 한 번만 실행된다.
- `VM-25`와 `VM-83`은 동일 target/old/new transformation이라 보고된 100개는 고유 transform 기준 99개다.

TASK §9의 production required/enum/range/closed-object 방어 약화 요구와 §10의 미탐지 병합 차단을 만족하려면 다음이 필요하다.

- schema defense inventory와 각 필수 방어의 mutation 추적
- depth 방어를 제거한 source mutant 실행에도 depth probes 포함
- 동일 transform 중복 금지 또는 하나의 multi-kill mutant로 통합
- H-01~H-03 신규 방어에 대한 fixture/input/source/schema mutant와 실제 sentinel

### H-05 — sentinel 실패가 audit 프로세스의 exit failure가 아니다

`scripts/verify_task_029.py`의 `_all_passed()`는 row의 `passed`만 검사하고 `sentinel_ok`를 보지 않는다. `--check-only`와 최종 gate도 fixture/input/leak sentinel 실패를 별도 차단하지 않는다.

임시 사본에서 input mutant IM-161의 sentinel만 실패하도록 만들면 JSON은 `bad_sentinels=["IM-161"]`을 보고하지만 producer exit는 0이었다. 따라서 “실제 sentinel 100%”가 출력상 깨져도 검증 명령이 성공할 수 있다.

필수 수정:

- fixture/input/leak의 모든 sentinel 실패를 exit 1로 결박
- source-mutant 실행에서도 observed input-mutant sentinel 상태를 반영
- sentinel 실패 전용 자기검증 또는 mutant 추가
- 출력 수치와 프로세스 성공 조건이 정확히 같은 predicate를 사용

### H-06 — 동적 객체 key가 error location에 raw 노출되고 해석 불가능하다

message redaction은 정상 동작하지만 schema finding의 `location`은 사용자 제어 object key를 그대로 포함한다.

예:

```text
resolved_style.language_overrides["/home/patient/secret.mp4"] = {}
→ subtitle_document/resolved_style/language_overrides//home/patient/secret.mp4
```

이 location은:

- 절대 경로 또는 민감 key를 `Finding.as_line()`에 그대로 노출
- `/`와 `~`를 escape하지 않아 입력에서 안정적으로 resolve 불가
- unknown top-level key가 `/`로 시작하면 TASK §8의 “선행 / 없는 location”도 위반

현재 leak scan은 message와 3 scalar 이상 text value만 검사하여 이 경로를 놓친다. `schema_core.py`를 수정하지 않고 TASK-029 boundary에서 동적 key를 안전한 parent location으로 정규화하거나, five-schema 전용으로 해석 가능한 location을 만들어야 한다. location의 절대경로·민감 key 누출과 1~2 scalar key도 감사 분모에 포함한다.

## 4. 문서 finding

### D-02 — cue LID의 “결정적 투영”은 현재 schema로 계산할 수 없다

LID authority 세 축의 분리는 올바르게 수정됐다.

- ReferenceBundle.language_spans: 평가 ground truth
- Transcript.language_spans: ASR/LID hypothesis의 단일 출처
- SubtitleDocument: 독립 LID hypothesis 없음

하지만 EVALS §4.5(a)의 L1–L3은 현재 계약이 제공하지 않는 대응을 결정적이라고 주장한다.

- target cue lineage는 TranslatedTranscript.`target_text` offset만 가리킨다.
- translation의 `source_fragments`는 segment 전체의 원문 offset만 제공한다.
- target 문자 범위와 source fragment 사이의 char alignment가 없다.
- merged/split/어순 변경 번역에서 특정 한국어 cue fragment를 특정 원문 language span에 배정할 수 없다.
- Transcript token은 선택이며 char offsets가 없어 raw character LID를 시간으로 옮길 일반 규칙도 없다.
- source cue도 U-19 `norm-v1` 미정 상태에서 Unicode 정규화 전후 offset mapping이 확정되지 않았다.

따라서 현재 TASK에서 target-axis cue의 LID projection을 결정적이라고 규정하지 않는다. 명시적 source↔target character alignment와 char↔time mapping이 생기는 후속 TASK로 넘기고, 현재는 추적 가능한 segment 수준 또는 unsupported로 제한한다. U-19를 이번 TASK에서 임의로 확정하지 않는다. ARCHITECTURE, EVALS, TASK 구현 기록의 “결정적 투영/미해결 모순 0” 표현을 이에 맞게 고친다.

## 5. 비차단·오너 결정 사항

다음 배열의 canonical order는 현재 TASK 문구가 명확하지 않아 이번 blocker로 확정하지 않는다.

- same-stream Transcript segment 시간순서
- 서로 다른 source segment에 대응하는 translation segment 순서
- ASR `source_speech_segment_ids` 순서

후속 producer가 숨은 정렬 규약을 만들기 전에 canonical order 필요 여부를 오너가 결정해야 한다.

`loads_strict()` duplicate-key 오류가 실제 key를 message에 넣는 문제는 Finding.message 계약 밖이므로 이번 Gate H blocker에는 포함하지 않는다. 다만 전체 CLI 로그 비노출 정책을 확장할 때 별도 hardening이 필요하다.

## 6. 재검토 조건

PR #45는 Draft로 유지한다. 같은 브랜치에 수정 commit을 추가하고 새 fixed HEAD를 보고한다.

1. H-01~H-03 반례가 안정적인 기존 error code/location으로 거부됨
2. H-04의 schema/depth mutation이 실제 kill되고 고유 transform 분모가 정확함
3. H-05의 모든 sentinel 실패가 exit 1로 연결됨
4. H-06의 location이 해석 가능하고 민감 key/path를 노출하지 않음
5. D-02의 불가능한 결정적 투영 주장이 제거되거나 실제 계약 필드로 증명됨
6. REVIEW-023에서 이미 해소한 방어와 전체 회귀가 유지됨
7. `schema_core.py`, cache key, 기존 job/artifact canonical bytes 변경 0
8. 신규 dependency/model/network 0
9. TASK-029/028/006, 전체 verify, Python 3.12 검증이 모두 통과
10. Ready 전환·merge·자기 승인은 제품 오너의 별도 승인 전 수행하지 않음

## 7. 별도 상태 정합성

기능 수정과 섞지 않고 Lean Root가 별도 변경으로 다룬다.

- STATUS의 병합 #44, open Draft #45/#46 및 TASK-029 잔존 제안 문구 정리
- PLAN의 TASK-029 미확정 candidate 문구 정리
- DECISIONS에 승인된 TASK-029 architecture 결정 기록
- REVIEW-023/024 증거 PR의 통합 순서와 깨진 상대 링크 해소

이 정합성 작업은 H-01~H-06과 D-02를 대신하지 않는다.
