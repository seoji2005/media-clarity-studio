# REVIEW-026 — TASK-029 fourth fixed-HEAD Gate H review

- 대상 PR: #45
- 대상 브랜치: `claude/task-029-subtitle-spine-contracts`
- 고정 HEAD: `67060e39ef6c4b9b004c77e2c57446804173be3a`
- tree: `da6d68a45642fbc3d253a4e67bcf9ffcc265b077`
- 직접 부모: `27fc2cd6d3c9969f5b7c3bc58e89bcdf9668c87f`
- 기준 main: `5264f6bec469ae741e8c99d8d5d150cf78e2b76f`
- 검토일: 2026-08-30
- 판정: **변경 요청**
- 병합/Ready 전환: 승인하지 않음

## 1. 고정 상태와 직접 재현

PR #45는 검토 시점에 open, draft, unmerged, mergeable=true이며 main 대비 ahead 4 / behind 0이었다. commit, tree, parent는 제출 보고와 일치했고 checkout은 clean이었다.

| 명령 | 독립 결과 |
|---|---|
| `make verify-task-029` | exit 0; fixture 159/159, subtitle tests 81, 전체 436 |
| `make audit-task-029` | exit 0; 제출된 12개 분모·sentinel·SKIP 수치 재현 |
| `make verify-task-028` | exit 0; J 16/16, artifact-store 36, job-runtime 149 |
| `make verify-task-006` | exit 0; H 14/14, 계약 162 |
| `make verify` | exit 0; 전체 436, FFmpeg smoke PASS |
| `make verify-task-029 PYTHON=python3.12` | exit 0; 같은 fixture/test/audit 수치 |
| `git diff --check`, `git status --short` | exit 0, 무출력 |

리뷰 환경에서는 Python 3.12.13을 직접 재현했다. Windows 11/NTFS와 실제 adapter는 TASK 범위대로 미검증이다.

REVIEW-025의 R-01~R-04 직접 반례는 해소됐다.

- 누락/부분 `document_refs`, role 붕괴, immutable metadata 불일치가 차단됨
- 비겹치는 SpeechSegment의 speaker label 차용과 실제 label 불일치가 차단됨
- JA/EN 혼용 translation unit과 `supports_code_switching_input=false` 조합이 차단됨
- in-memory 401자리 이상의 큰 정수가 validator 내부에서 더 이상 `float()` overflow를 일으키지 않음
- slash/path alias, frozen required 삭제, sentinel exit 결박도 제출된 공식 반례 범위에서는 개선됨

그러나 아래 인접 반례는 현재 audit가 모두 통과하면서도 실제 계약을 위반한다.

## 2. Blocking findings

### R-01 — location 비식별화가 parent-insensitive allowlist와 동적 language key에서 다시 열린다

`safe_location()`은 다섯 schema의 모든 property 이름을 하나의 전역 `declared_segments` 집합으로 합친다. 따라서 어떤 위치에서 정본 field인 이름이면 다른 부모 아래의 사용자 제어 key도 안전하다고 오인한다.

직접 재현:

| 입력 key | 실제 finding location | 계약상 안전 location |
|---|---|---|
| top-level `uri`, `text`, `artifact_id` | `uri`, `text`, `artifact_id` | root `""` |
| `document_refs["uri"]`, `["speaker_label"]`, `["artifact_id"]` | `document_refs/<raw-key>` | `document_refs` |
| `language_overrides["speaker_label"]` | override 아래 raw key 포함 | `.../language_overrides` |

또한 `language_overrides` key가 language-tag 정규식 모양이면 입력값을 그대로 노출한다. 다음 key가 모두 finding location에 남았다.

- `patient`
- `password`
- `en-John-Doe`
- `en-x-secret`

BCP-47 private-use 모양에도 임의 문자열을 넣을 수 있으므로 registry/정규식 모양은 비식별화 allowlist가 아니다. 공개 `check_subtitle_document()` 직접 호출도 최종 `_finalize()` 경계를 지나지 않아 같은 raw key를 노출할 수 있다.

제출된 leak scan은 이 반례를 모두 안전하다고 판정한다.

- mapping key를 민감 입력 후보로 수집하지 않음
- production과 같은 전역 `declared_segments`/language-tag 허용 가정을 oracle이 공유함

필수 수정:

1. 고정 field 허용을 schema 전체 전역 집합이 아니라 정확한 parent/path별 allowlist로 만든다.
2. `language_overrides`의 동적 key는 외부 finding에서 모두 부모로 접거나, 입력과 독립된 frozen allowlist만 노출한다.
3. schema finding, domain finding, container 조기 반환, 공개 validator 경계 모두 같은 비노출 계약을 적용한다.
4. leak scan은 동적 mapping key도 수집하고 production `safe_location()`과 독립된 위치별 oracle을 사용한다.
5. 위 표와 private-use 반례를 fixture/input/source mutant로 고정한다.

### R-02 — raw JSON 숫자와 document-set root가 안정적인 파일 계약을 우회한다

기존 401자리 `float()` overflow는 고쳐졌지만, strict loader와 fixture runner 경계에서 아직 traceback 또는 조용한 의미 변경이 발생한다.

#### R-02a — 4,301자리 정수 traceback

`schema_core.loads_strict()`에 4,301자리 JSON 정수를 주면 Python 정수 문자열 제한의 `ValueError`가 감싸지지 않는다.

| 입력 | 결과 |
|---|---|
| 4,300자리 정수 | parse 성공 |
| 4,301자리 양/음 정수 | exit 1 + traceback |
| 10,000자리 정수 | exit 1 + traceback |

무제한 정수를 허용하라는 요구가 아니다. 허용 범위를 넘는 raw JSON은 TASK-029 경계에서 안정적인 입력 오류/finding으로 거부되어야 한다.

#### R-02b — binary64 반올림으로 invalid가 VALID가 된다

기본 `json.loads()`가 decimal을 binary64로 바꾸면서 원문의 수학적 값을 조용히 바꾼다.

| JSON 원문 | 파싱 값 | 현재 판정 | 문제 |
|---|---:|---|---|
| confidence `1.0000000000000001` | `1.0` | VALID | `[0,1]` 밖 값을 허용 |
| start/min gap `-1e-400` | `-0.0` | VALID | 음수 불변식 우회 |
| `max_cps=1e-400` | `0.0` | `E_SCHEMA` | 양의 값을 잘못 거부 |

모든 decimal을 무제한 정밀도로 지원할 필요는 없다. 다음 중 하나를 기계 계약으로 정하고 테스트해야 한다.

- 원문 decimal의 계약 범위를 손실 없이 검사
- 허용 numeric lexical/정밀도 profile을 정의하고 손실되는 값을 안정적으로 거부

암묵적 반올림 뒤 VALID은 허용하지 않는다.

#### R-02c — malformed document-set root traceback

fixture의 `documents`가 `[]`, `null`, 정수이면 안정 `E_SCHEMA @ ""`가 아니라 `AttributeError`/`TypeError` traceback으로 종료된다. public `validate_documents()`의 precondition을 기계적으로 강제하거나 runner가 root type을 먼저 검사해야 한다.

필수 수정:

1. raw JSON parse/fixture root의 모든 실패가 traceback 없이 안정 code/location 또는 명시된 안정 CLI 오류로 끝난다.
2. 4,301자리 양/음 정수, decimal 반올림 경계, `documents=[]|null|integer`를 실제 raw JSON/CLI 회귀로 추가한다.
3. schema-first `E_SCHEMA`와 domain `E_TIME_RANGE`/`E_OFFSET_RANGE`/`E_CONFIDENCE`의 taxonomy를 TASK §8과 일치시키거나 문서에서 정확히 구분한다.
4. `schema_core.py` 변경이 필요하다면 TASK-029 범위를 임의 확장하지 말고 Blocked로 오너에게 올린다.

### R-03 — frozen defense manifest가 방어의 의미와 자기 갱신을 고정하지 않는다

현재 manifest는 `coordinate|keyword` ID만 고정하고 keyword의 실제 enum/range/pattern 값을 고정하지 않는다.

저장소 밖 임시 사본에서 `StyleOverride.line_break_policy` enum에 `x_new_policy`를 추가한 결과:

- 실제 문서에서 `x_new_policy`가 finding 없이 통과
- `--manifest-check` exit 0
- `--check-only` exit 0
- inventory 293/293, digest와 manifest diff 0

즉 방어가 의미상 약해져도 “drift 0”으로 보고된다.

또한 equivalent defense 하나를 삭제한 뒤 `--write-manifest`를 실행하면 성공/exit 0이지만 새 목록이 아니라 stale 목록으로 digest를 계산해 직후 `--manifest-check`가 MF-03으로 실패한다. manifest updater가 자체적으로 불일치 파일을 만든다.

required 배열 또는 manifest 목록에 동일 ID를 중복해도 declared/unique 수가 달라진 채 standalone manifest predicate가 성공할 수 있는 경계도 있다. full `verify-task-029`의 unit test만이 일부 중복을 잡는 구조는 standalone audit의 100% 주장과 맞지 않는다.

필수 수정:

1. manifest가 방어 ID뿐 아니라 enum/range/pattern/required/closed의 canonical 의미값도 fingerprint한다.
2. `--write-manifest`는 실제 기록할 entries로 digest를 계산하고, write 뒤 self-check 실패 시 nonzero로 끝난다.
3. killable/equivalent section 각각의 unique/disjoint, `defense_declared == defense_unique`, transformation uniqueness를 standalone success predicate에 직접 결박한다.
4. enum 확장, range 완화, pattern 변경, duplicate required/manifest ID, updater stale digest를 자기검증으로 추가한다.
5. 명시적 baseline 갱신은 계속 diff로 보이게 하되, 갱신 도구가 현재 schema와 불일치한 manifest를 성공으로 만들 수 없어야 한다.

### D-04 — LID·ArtifactRef 공개 문서가 기계 정본과 아직 충돌한다

문서 수정은 대부분 개선됐지만 다음 normative conflict가 남아 있다.

1. `docs/EVALS.md`는 한편으로 정답 발화의 모든 격자를 분모로 두고 Transcript 문자 offset을 시간으로 투영한다고 쓰고, 다른 한편으로 multi/gap/und segment는 분모에서 제외하며 intra-segment char→time은 미지원이라고 쓴다.
2. 어려운 구간을 `gap`/`und`로 내면 분모에서 제외되어 accuracy가 올라갈 수 있다. support/coverage/excluded/unknown 비율과 zero-denominator 처리 없이 정확도만 보고하면 평가 회피가 가능하다.
3. `docs/ARCHITECTURE.md`의 LID 미지원 fallback은 configured `dominant_language`를 기록하라고 하지만 canonical schema/validator와 TASK migration rule은 spans와 dominant 모두 부재를 요구한다.
4. TASK §5의 raw Transcript timing projection 문장은 TASK §17.7의 “intra-segment 미지원”과 충돌한다.
5. 필수 `document_refs` validation envelope의 role, 필요 조건, ArtifactRef shape가 public architecture/API 계약에 없고 구현 기록과 code docstring에만 있다.
6. generic ArtifactRef `uri`와 TASK-028 store output URI 규칙을 구분하지 않아 common schema의 opaque URI와 ARCHITECTURE의 relative-path 규칙이 충돌한다.

필수 수정:

- EVALS의 LID 분모·지원 범위·coverage/exclusion·zero denominator를 실행 가능하게 단일화한다.
- configured language를 LID 가설처럼 기록하는 기존 fallback을 금지/철회한다.
- TASK §5를 §17.7과 일치시키고 미지원 투영을 제거한다.
- `document_refs` validation envelope를 public architecture/API 계약에 기술한다.
- generic ArtifactRef URI와 TASK-028 store output URI를 분리해 적고, 비교하지 않는 `produced_by`/`parent_refs`/`timebase_ref`는 오너 결정으로 남긴다.

## 3. 비차단·오너 결정 및 통합 조건

다음은 이 재검토에서 임의 결정하지 않는다.

- ArtifactRef의 `uri`, `produced_by`, `created_at`, `parent_refs`, `timebase_ref` 동일성
- 비겹침 context용 별도 lineage field
- 언어별 분할 호출 provenance
- independent-channel/overlap capability의 전처리 전/후 의미
- same-stream/translation/source ID canonical order
- U-19 `norm-v1`

상태 정합성은 기능 수정과 섞지 않는다. 다만 승인/통합 전에 Lean Root가 별도 변경으로 다음을 해소해야 한다.

- PR #45에서 깨진 REVIEW-023~026 상대 링크: PR #46은 과거 구현 HEAD에서 분기했으므로 그대로 선행 병합하지 않는다. 최신 main 기반 review-only 브랜치로 REVIEW 파일만 옮기거나, PR #45 승인·병합 뒤 PR #46이 review-only diff가 된 것을 확인해 통합한다.
- STATUS의 fixture 158→159, merged/open PR 목록, TASK-029 잔존 제안 문구
- PLAN의 TASK-029 미확정 candidate 문구
- DECISIONS에 승인된 TASK-029 결정과 오너 결정 항목 추적

## 4. 재검토 조건

PR #45는 Draft로 유지한다. 같은 브랜치에 제한 수정 commit을 추가하고 새 fixed HEAD를 보고한다.

1. R-01의 위치별 비식별화 반례가 production과 독립 oracle 양쪽에서 차단됨
2. R-02의 raw JSON 숫자/문서 root 반례가 traceback·조용한 반올림 VALID 없이 안정 종료됨
3. R-03의 의미 약화·updater·중복 반례가 standalone audit exit 1을 만듦
4. D-04의 문서 정본 충돌과 LID denominator gaming이 해소됨
5. REVIEW-023~025에서 이미 해소한 방어와 전체 회귀 유지
6. `schema_core.py`, cache key, artifact/job canonical bytes 변경 0. 불가피하면 임의 변경하지 않고 Blocked
7. 신규 dependency/model/network 0
8. TASK-029/028/006, 전체 verify, Python 3.12 검증 통과
9. Ready 전환·merge·자기 승인은 제품 오너의 별도 승인 전 수행하지 않음
