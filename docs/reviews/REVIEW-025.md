# REVIEW-025 — TASK-029 third fixed-HEAD Gate H review

- 대상 PR: #45
- 대상 브랜치: `claude/task-029-subtitle-spine-contracts`
- 고정 HEAD: `27fc2cd6d3c9969f5b7c3bc58e89bcdf9668c87f`
- tree: `d8a2bd5d04e5d14ace330f2ba7c8b4dfd6d8113c`
- 직접 부모: `7b627e9755f786793b1ae898cf76053d238f0bf5`
- 기준 main: `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`
- 검토일: 2026-08-30
- 판정: **변경 요청**
- 병합/Ready 전환: 승인하지 않음

## 1. 고정 상태와 직접 재현

PR #45는 검토 시점에 open, draft, unmerged, mergeable=true이며 main 대비 ahead 3 / behind 0이었다. commit, tree, parent는 제출 보고와 일치했다.

| 명령 | 독립 결과 |
|---|---|
| `make verify-task-029` | exit 0; fixture 132/132, subtitle tests 60, 전체 415 |
| `make audit-task-029` | exit 0; 보고된 9개 분모 100%, SKIP 0 |
| `make verify-task-028` | exit 0; J 16/16, artifact-store 36, job-runtime 149 |
| `make verify-task-006` | exit 0; H 14/14, 계약 162 |
| `make verify` | exit 0; 전체 415, FFmpeg smoke PASS |
| `make verify-task-029 PYTHON=python3.12` | exit 0 |
| `git diff --check`, `git status --short` | exit 0, 무출력 |

리뷰 환경의 기본 `python3`도 Python 3.12.13이므로 Python 3.11 결과는 별도 재현하지 못했다. 현재 blocker 판정에는 영향을 주지 않는다.

REVIEW-024의 IM-90, IM-122~136, IM-172~198 및 Unicode·NaN/Inf·음수 회귀는 새 HEAD에서 기대한 exact code/location으로 차단됐다. depth probe 결박, sentinel exit 자기검증, capability의 기본 implication, speaker exact-value 기본 사례도 개선됐다. 그러나 아래 인접 반례와 audit 자기맹점 때문에 Gate H는 승인할 수 없다.

## 2. Blocking findings

### R-01 — ArtifactRef 검증 context가 fail-open이며 자체 일관성도 약하다

`document_refs`가 없거나 필요한 항목이 빠지면 identity 검사를 조용히 건너뛰고 최종 결과는 `VALID`이다. 실제로 context를 제거하고 SubtitleDocument.`input_document_ref`를 다른 artifact ID/hash로 바꾸면 finding이 없다.

이 선택 경계는 “직접 입력 ref가 실제 제공 문서를 가리킨다”는 REVIEW-024 H-01의 보장을 호출자가 실수로 생략할 수 있게 한다. 검증 결과에도 “identity 미검증” 상태가 표현되지 않는다.

또한 다음 context가 모두 `VALID`이다.

- Transcript와 TranslatedTranscript에 동일 artifact ID/hash 사용
- 동일 artifact ID에 서로 다른 content hash 사용
- context ref에 `kind=video`, `media_type=video/mp4`, 절대경로 URI, 임의 필드 사용
- 사용되지 않는 document role 추가
- embedded ref에서 동일 ID/hash인데 `byte_size`가 서로 다름

ARCHITECTURE §2.1의 프로젝트 내 artifact ID 유일성과 immutable ArtifactRef metadata 일관성을 위반한다.

필수 수정:

1. lineage identity를 검증하는 문서 조합에서는 필요한 context entry를 필수화하거나, context 부재를 명시적인 invalid/partial-validation 결과로 만든다. 조용한 skip+VALID은 금지한다.
2. `document_refs` 값을 공통 ArtifactRef 계약 또는 별도 기계 정본으로 검증한다.
3. document role별 필요한 key와 추가 key 금지를 고정한다.
4. artifact ID uniqueness와 같은 ID→동일 hash/metadata를 검사한다.
5. ref equality가 identity 두 필드만 의미하는지 전체 immutable metadata까지 의미하는지 문서에 명시하고, 최소한 동일 hash와 모순되는 byte size를 거부한다.
6. context missing/partial, role collapse, duplicate ID/different hash, wrong kind/media type, metadata mismatch를 fixture와 mutant로 고정한다.

### R-02 — 비겹치는 SpeechSegment가 ASR lineage와 input speaker 증거를 오염시킨다

다음 문서가 `VALID`이다.

- ASR segment `[4,5)`
- 실제 시간을 덮는 SpeechSegment `[4,6)`는 speaker label 없음
- 추가 source ref `[0,2)`에는 `CH-L` label
- ASR은 두 source ID를 모두 참조하고 `speaker_label=CH-L/source=input`

validator는 ASR interval이 source interval 합집합 중 하나에 들어가는지만 확인하고, speaker label은 모든 source ref에서 시간 겹침 없이 수집한다. unlabeled source는 집합에서 버리므로 비겹치는 과거·미래 segment의 label을 빌릴 수 있다. stream-level input label도 같은 방식으로 미래 segment 하나만으로 정당화된다.

필수 수정:

- 모든 `source_speech_segment_ids`가 해당 ASR segment와 실제로 겹치는지, 또는 참조의 명시적 역할을 검사
- speaker evidence는 실제 ASR 구간을 덮는 source에서만 수집
- 구간 일부를 덮는 source가 unlabeled이면 단일 input label을 조용히 주장하지 않음
- labelled non-overlap + unlabeled covering source 반례를 segment/stream 양쪽에 추가
- 불필요한 비겹침 source ref 자체를 허용할지 오너 계약으로 명시

### R-03 — translation code-switch capability가 실제 입력과 결박되지 않는다

JA/EN 문장 내부 전환이 있는 `今日はsunnyですね` 전체를 하나의 translation unit으로 번역하면서 `supports_code_switching_input=false`로 바꿔도 `VALID`이다.

필수 수정:

- 실제 번역 source fragment와 Transcript.language_spans의 교차로 해당 translation unit의 입력 언어 집합·switch kind를 계산
- 한 번의 translation 입력 단위가 복수 known language 또는 intra-sentential switch를 포함하면 `supports_code_switching_input=true`를 요구
- 전체 Transcript가 아니라 실제 번역 fragment 범위를 사용
- orchestrator가 언어별 분할 호출 후 합성한 경우를 허용하려면 이를 표현하는 provenance/processing 계약을 먼저 정하고 임의 추론하지 않음

`supports_independent_channel_input`과 `supports_overlap_streams`의 producer evidence 결박은 adapter가 전처리 전/후 어느 입력을 의미하는지 모호하므로 오너 결정으로 분리한다.

### R-04 — JSON-valid arbitrary-precision integer가 validator를 crash시킨다

다음 값은 finding을 반환하지 않고 `OverflowError: int too large to convert to float`로 validator를 중단시킨다.

- Transcript segment `start_seconds=10**400`
- token `confidence=10**400`

Python strict JSON loader도 401자리 정수를 정상 int로 수용하므로 direct-object 전용 인공 입력이 아니다. `_finite()`와 시간 검사에서 무조건 `float(value)`로 바꾸는 경로가 원인이다.

필수 수정:

- 임의 크기 JSON integer/decimal에서 예외 없이 안정적인 finding을 반환
- finite/range 비교를 overflow-safe하게 구현
- segment/token/confidence/style/time 등 모든 number 경로를 같은 원칙으로 감사
- huge positive/negative integer와 경계 decimal을 fixture, depth probe, validator mutant에 포함
- invalid input이 traceback이나 process crash로 빠지지 않는 CLI 회귀 추가

### R-05 — dynamic-key location 정규화가 slash aliasing으로 우회된다

현재 구현은 raw dynamic key를 `/`로 이어붙인 뒤 split/resolve한다. 이 시점에는 동적 key 경계가 소실된다.

직접 반례:

- top-level key `transcript/streams` → `E_SCHEMA@transcript/streams`
- `document_refs["transcript/artifact_id"]` → `document_refs/transcript/artifact_id`
- `language_overrides["a/b"]`와 실제 nested `a.b`가 함께 있으면 둘 다 `.../a/b`
- `patient_name`, `John_Doe` 같은 ASCII dynamic key가 그대로 location에 남음
- 일부 container 조기 반환 경로는 root-aware 정규화 자체를 건너뜀

finding이 공격자 key를 다른 실제 노드의 위치로 오인하고 leak scan도 정상 경로가 존재한다는 이유로 놓친다.

필수 수정:

- raw concatenated string의 사후 split만으로 dynamic key를 판별하지 않음
- schema/source-aware tokenized location 또는 알려진 dynamic parent별 parent folding 사용
- invalid top-level key는 root, invalid document_refs key는 `document_refs`, unsafe language override key는 override 부모로 접음
- safe-looking ASCII도 사용자 제어 key라면 raw 보존하지 않거나 명시적 allowlist만 보존
- slash alias, real-path collision, ASCII 민감 key, container early-return을 message+location leak 분모와 mutant에 추가

### R-06 — schema defense inventory가 production 방어 삭제를 탐지하지 못한다

현재 293개 inventory의 개별 약화와 sentinel은 재현됐다. 그러나 분모를 현재 schema에서 다시 생성하므로 production defense가 삭제되면 분모도 함께 줄어든다.

저장소 밖 임시 사본에서 SpeechSegment root required의 `source_track_index`를 삭제한 결과:

- inventory 293 → 292
- 해당 필드 없는 실제 입력도 findings 없음
- `--check-only` exit 0
- AuditGateTests 5/5
- `make audit-task-029` exit 0
- `make verify-task-029` exit 0, 415 tests와 smoke PASS

이는 REVIEW-024가 지목한 바로 그 required 회귀를 최종 gate가 놓치는 것이다.

또한 “중복 선언 2”는 duplicate mutant가 아니라 pattern이 minLength를 논리적으로 함의하는 equivalent defense다. 단일 방어 약화로 위반이 통과하지 않는데 293/293 detected로 포함하므로 kill-rate 표현이 부정확하다.

필수 수정:

1. 현재 defense ID의 schema 외부 고정 manifest/digest 또는 동등한 독립 기준을 둔다.
2. 방어 추가·삭제는 명시적 manifest 갱신과 검토 없이는 audit가 실패해야 한다.
3. equivalent defense 2건은 killable 분모와 분리해 근거가 있는 frozen allowlist로 관리한다.
4. 보고는 예를 들어 `291/291 killable + equivalent 2/2`처럼 실제 의미를 구분한다.
5. standalone audit의 성공 predicate에도 manifest drift와 transformation uniqueness를 직접 연결한다.
6. required 삭제 시 전체 verify가 exit 1이 되는 자기 mutation을 추가한다.

Depth-probe mutant 결박과 AS-01~03 sentinel exit 자기검증은 이번 HEAD에서 정상임을 확인했다.

## 3. Documentation finding

### D-03 — D-02 철회가 EVALS 전체에 반영되지 않았다

EVALS §4.5(a)는 SubtitleDocument cue LID를 미지원으로 축소했지만 다음 기존 문구는 여전히 canonical cue text와 알고리즘 C를 언어 투영에 사용한다고 규정한다.

- EVALS 411~413
- EVALS 432~433
- EVALS 464~465

이는 같은 문서 663 및 684~698의 Transcript exact-text 전용·Subtitle unsupported 규칙과 직접 충돌한다.

또한 EVALS 672~675는 segment/token timing으로 “각 문자”의 시각을 부여한다고 하지만 token에는 char offsets가 없고 segment text의 exact partition 계약도 없다. intra-segment language span/switch point의 일반적인 char→time 투영은 아직 실행할 수 없다.

필수 수정:

- C0의 잔존 cue-LID 투영 문구 제거
- 명시적 char↔time mapping이 생기기 전까지 raw Transcript의 intra-segment 시간 지표도 unsupported 또는 후속 owner decision으로 표시
- U-19나 균등 시간 배분을 이번 TASK에서 임의 확정하지 않음
- “미해결 모순 0”은 실제로 모든 잔존 문구를 정합화한 뒤에만 사용

## 4. 통합·상태 정합성

PR #45 tree에는 REVIEW-023/024가 없어서 STATUS와 TASK의 상대 링크가 깨져 있다. 리뷰 기록은 PR #46에 있다. PR #46을 먼저 병합하거나 영속 GitHub 링크/명시적 통합 순서로 해소해야 한다.

다음은 기능 수정과 분리해 Lean Root 상태 PR에서 처리한다.

- STATUS의 merged #44, open #45/#46 및 TASK-029 잔존 제안 문구
- PLAN의 TASK-029 미확정 candidate 문구
- DECISIONS에 TASK-029 기술 결정과 §16.7 owner decisions 등록

## 5. 재검토 조건

PR #45는 Draft로 유지한다. 같은 브랜치에 수정 commit을 추가하고 새 fixed HEAD를 보고한다.

1. R-01~R-05 반례가 crash/fail-open 없이 안정 code/location으로 거부됨
2. R-06 required 삭제가 실제 전체 audit/verify exit 1을 만듦
3. schema inventory의 killable/equivalent 분모가 정직하게 분리됨
4. D-03 문서 모순과 불가능한 char→time 주장이 해소됨
5. REVIEW-023/024에서 이미 해소한 방어와 전체 회귀 유지
6. `schema_core.py`, cache key, artifact/job canonical bytes 변경 0
7. 신규 dependency/model/network 0
8. TASK-029/028/006, 전체 verify, Python 3.12 검증 통과
9. Ready 전환·merge·자기 승인은 제품 오너의 별도 승인 전 수행하지 않음
