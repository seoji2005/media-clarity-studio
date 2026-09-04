# TASK-032 — 공개·합성 frozen target pack 기반 3-ASR Work-CPU screening

- **Status:** In progress — 첫 구현 slice(schema·synthetic CAS/recovery fixture·무료 Work-CPU preflight) 작성·검증 완료; fresh Gate H review 대기, 모델 실행 미착수
- **Gate:** H (새 모델·dependency/network 경계와 후속 후보 선택에 영향을 주는 평가 계약)
- **Created:** 2026-09-03
- **Base:** `main@0c0f40ea318aff8b69180c9c6f510a627b0e0b9c`
- **Contract merge:** PR #61, `dd3e78645e9ece7fffd8843c10ba37abcdde0a8e` (approved fixed HEAD `0945cf31411e6b3c5cc149518e55cfff34087ce0`)
- **Parent work:** TASK-031의 후보 결정을 돕는 별도 screening. TASK-031 계약 자체는 이 TASK에서 수정하지 않음
- **Owner / Author:** Lean Root / GPT-Codex
- **Reviewer:** 이 fixed HEAD를 작성하지 않은 fresh GPT/Codex Gate H reviewer

## 1. 목적

TASK-031의 target Windows 11 / RTX 4070 SUPER 12 GB 실행 전에, 민감하지 않은 공개·허가·합성 음성만으로
다음 세 ASR 후보를 동일한 frozen target pack에서 먼저 비교한다.

1. `Qwen/Qwen3-ASR-1.7B`
2. `CohereLabs/cohere-transcribe-03-2026`
3. `Systran/faster-whisper-large-v3`

가능한 모든 준비와 1차 추론은 현재 Work 환경의 CPU에서 수행한다. 목표는 품질 후보를 두 개로 압축하고,
집에서는 나중에 **한 번의 재현 가능한 setup/model-snapshot 명령**과 **약 10분 winner/fallback local ASR run**만
남기는 것이다. CPU 결과는 Windows·12 GB·CUDA 호환성 증거가 아니며, 결과 표현은 오직
“이 frozen target pack에서 가장 좋음”으로 제한한다.

## 2. 승인·보안·비용 경계

제품 오너가 2026-09-03 승인한 현재 gate는 다음과 같다.

- 평가 입력은 공개 라이선스, 사용 허가가 확인된 실제 사람 음성, 또는 합성 비민감 자료로 한정한다.
- 개인·민감 사용자 미디어, 비밀정보, 인증 토큰, model weight, 생성 media, raw transcript는 Git에 넣지 않는다.
- 세 모델은 아래 exact revision만 준비·실행한다. mutable branch나 이름만으로 실행하지 않는다.
- Work CPU에서의 고정 모델/dependency 준비와 무료 실행만 허용한다.
- 유료 provider, 외부 GPU, 상용 ASR API는 승인되지 않았다. 현재 추가 지출 상한은 **0**이다.
- CPU로 신뢰할 수 있는 비교가 불가능하면 fixtures·harness·receipt·검증·Windows 실행 bundle을 계속 만들고,
  provider·GPU 유형·지출 상한을 제품 오너에게 제시한 뒤 별도 승인을 기다린다.
- Cohere repository는 `gated: auto`다. 제품 오너가 접근 조건을 직접 수락하지 않았거나 인증된 다운로드가
  불가능하면 우회하거나 credential을 요구·저장하지 않고 `blocked_access` evidence를 남긴다.
- cloud/Work 결과는 품질 후보 압축에만 쓰며 target Windows의 OOM·RTF·driver 판정으로 재사용하지 않는다.

| 후보 | exact revision | 관측한 배포처 metadata | 선행 위험 |
|---|---|---|---|
| Qwen3-ASR-1.7B | `7278e1e70fe206f11671096ffdd38061171dd6e5` | Apache-2.0 | Windows/12 GB 미검증 |
| Cohere Transcribe 2B | `b1eacc2686a3d08ceaae5f24a88b1d519620bc09` | Apache-2.0, `gated: auto`, BF16 2B | code-switching·비음성 공식 제한, 접근 수락 필요 |
| faster-whisper large-v3 | `edaa852ec7e145841d8ffdb056a99866b5f0a478` | MIT | Windows/12 GB 미검증 |

정본 확인 위치는 [Qwen commit](https://huggingface.co/Qwen/Qwen3-ASR-1.7B/commit/7278e1e70fe206f11671096ffdd38061171dd6e5),
[Cohere model API](https://huggingface.co/api/models/CohereLabs/cohere-transcribe-03-2026),
[faster-whisper commit](https://huggingface.co/Systran/faster-whisper-large-v3/commit/edaa852ec7e145841d8ffdb056a99866b5f0a478)이다.
배포처 metadata는 법률 의견이나 사용 적합성 보증이 아니다. 실행 전에는 각 파일 hash, license/access receipt,
package/source identity, runtime과 decoding config를 별도 manifest에 고정한다.

## 3. frozen target pack

모델 출력이나 중간 점수를 보기 전에 primary와 reserve를 함께 freeze한다.

| stratum | primary 분량 | 필수 내용 |
|---|---:|---|
| clean Japanese | 3분 | 실제 사람 음성 포함 |
| clean English | 3분 | 실제 사람 음성 포함 |
| code-switching·이름·숫자·기술용어 | 4분 | 일본어↔영어 문장 내 전환 포함 |
| 빠른 대화·약한 overlap | 3분 | 발화자 경계와 약한 동시 발화 |
| 음악·소음·compression | 3분 | 강도와 codec recipe 기록 |
| silence·non-speech | 2분 | speech 0인 구간과 비음성 event |
| **primary 합계** | **18분** | 위 닫힌 구성 |

- reserve는 **12분**이며 같은 strata의 취약 사례를 보강한다. primary와 동시에 hash를 고정하되 평소에는 열지 않는다.
- 전체 pack에는 적법한 실제 사람 음성과 최소 두 TTS engine을 분산한다. TTS-only pack으로 일반 우위를 주장하지 않는다.
- 각 clip은 source/license/consent 분류, reference transcript, language spans, names/numbers annotations,
  duration/timebase, 원본 hash, deterministic degradation recipe와 산출 hash를 가진다.
- 라이선스·reference transcript·업로드 허용 분류가 확인되지 않은 실제 음성은 pack에 들어갈 수 없다.
- Git에는 작은 synthetic fixture와 비식별 manifest/hash만 둔다. 실제 pack bytes는 기존 CAS 밖으로 복제하지 않는다.

## 4. 공정한 실행 규약

### 4.1 무비용 preflight

세 후보 모두에 대해 model revision, gated-access 상태, file/weight hash, dependency lock, Python·OS·CPU·RAM,
runner source commit, precision·quantization, decoding, punctuation, VAD, language hint, chunk/stitch/context 설정을
출력 전에 고정한다. 후보별 API 차이는 adapter가 흡수하되 결과를 본 뒤 한 후보만 설정을 바꾸지 않는다.

### 4.2 sentinel, controlled resume와 primary

- 후보마다 ordered clip unit이 둘 이상인 2분 sentinel top-level job을 1회 실행해 load 실패, 빈 출력,
  반복 hallucination, chunk 조립 오류와 CPU 실행 가능성을 본다.
- 세 후보 각각의 sentinel에는 controlled interruption을 정확히 한 번 주입한다. 최소 한 unit이 CAS에 완료된 뒤
  다음 unit이 완료되기 전에 중단하고 같은 job을 resume한다.
- resume는 이미 완료된 unit의 callable을 다시 실행하지 않고 동일한 attempt/output ref를 재사용해야 한다.
  interrupted attempt는 보존하고 incomplete/pending unit만 실행하며, 최종 ordered coverage에는 모든 unit이
  정확히 한 번 있어야 한다. 누락·중복·완료 unit 재실행은 해당 후보 evidence를 invalid로 만든다.
- sentinel은 후보를 자동 탈락시키는 속도 경기가 아니다. 실험이 유효하게 실행되고 실제 cache/resume 계약을
  지켰는지 판정한다.
- valid한 후보는 같은 Work CPU에서 순차·batch 1·무양자화·결정적 decoding으로 18분 primary를 실행한다.
- clip 경계와 dominant-language hint는 후보 사이에 동일하게 고정한다.
- 공통 VAD를 쓴다면 경계를 출력 전에 freeze한다. 2분 silence/non-speech probe는 세 후보 모두 VAD를 우회해
  silence hallucination을 직접 측정한다.
- retry는 환경·harness failure와 candidate failure를 구분하는 frozen 규칙에 따라서만 허용한다. 이전 attempt와
  실패 메시지를 보존하고 조용히 덮어쓰지 않는다.

기본 실행량은 6 top-level jobs, 60 unique scheduled audio-minutes다(2분×3 sentinel + 18분×3 primary).
§5의 primary predicate가 unique bottom을 만들지 못하면 reserve를 개봉해 **세 후보 모두** 같은 12분을 실행한다.
이 경우 최대 9 top-level jobs, 96 unique scheduled audio-minutes다. interruption으로 재실행된 미완료 unit의
실제 처리량은 이 nominal 수치에 숨기지 않고 attempt별 audio-minutes로 별도 보고한다.

## 5. 품질·사람 평가와 선택 규칙

후보별로 최소한 다음을 보고한다.

- Japanese CER, English WER
- mixed-language error와 language-span/code-switch 오류
- names, numbers, technical terms 오류
- timestamp와 함께 기록한 fatal omission, hallucination, silence hallucination
- 동일 편집자가 만든 source correction time과 correction record
- 실행 성공/실패, elapsed time과 Work CPU 환경. CPU 속도는 target local hard gate가 아니다.

후보명은 가리고 clip 순서를 섞는다. 한 편집자가 clip별 후보 순서를 균형화해 correction time을 기록하고,
fatal event만 두 번째 평가자가 독립 판정한다. 사람이 실제로 편집하지 않은 값을 correction time으로 만들거나
자동 edit distance를 같은 이름으로 기록하지 않는다.

단일 종합 점수는 만들지 않는다. primary metric은 clip별
`fatal_clip_rate = fatal omission·hallucination·silence hallucination 중 하나 이상이 있는 scored clip 수 /
전체 scored clip 수` 하나다. 나머지는 아래의 순서 있는 secondary tier다.

1. primary `fatal_clip_rate`와 stratum×fatal-event-kind safety cell
2. human correction seconds per audio minute
3. Japanese CER·English WER
4. mixed-language와 names/numbers/technical-term annotated-item error rate

### 5.1 출력 전 decision rule freeze

첫 candidate output 전에 닫힌 `AsrScreenDecisionRule/v1`을 CAS에 저장하고 ref와 SHA-256을 pack config,
모든 run manifest와 report에 넣는다. 최소한 ordered candidate IDs, primary/reserve pack hash, metric/denominator,
tier order, `source_id` cluster key, percentile cluster-bootstrap 10,000회, bootstrap seed `32061`, 양측 95% CI,
최소 source group 수 5와 아래 minimum practical effect(MPE)를 포함한다.

| tier | screen 전용 MPE |
|---|---|
| `fatal_clip_rate` | `max(1 / eligible_clip_count, 0.01)` absolute rate |
| correction time | `max(3.0 seconds/audio-minute, pairwise slower mean의 5%)` |
| CER/WER와 annotated-item error rate | 0.01 absolute rate (1 percentage point) |
| safety cell event count | 1 event; 한 cell이라도 더 나쁘면 그 pair의 lower-tier 승리를 veto |

이 값은 U-27의 제품 전체 품질 목표가 아니라 이 작은 screen의 후보 제거 규칙이다. 결과 뒤 낮추거나 metric,
denominator, source grouping, seed, CI, tier 순서를 바꾸지 않는다. model decoding은 sampling 없는 결정 경로여야
한다. backend stochasticity를 끌 수 없으면 임의의 1-seed 결과를 쓰지 않고 preflight를 `blocked`로 끝낸다.

lower-is-better 지표의 paired 차이를 `A - B`로 둔다.

- 95% CI upper bound가 `-MPE`보다 작으면 A가 B보다 `materially_better`다.
- CI 전체가 `[-MPE, +MPE]` 안이면 `equivalent`다.
- 그 밖, CI 누락 또는 `n_sources < 5`는 `indeterminate`이며 승패를 만들지 않는다.

rule document/ref/hash가 없거나 어느 manifest/report와 다르거나 validator가 위 상수를 재계산해 일치시키지
못하면 verdict는 `blocked`이고 report는 `completed`가 될 수 없다.

### 5.2 pairwise predicate와 reserve

A가 B를 이기는 predicate는 tier를 위에서부터 순서대로 적용한다.

1. A의 `fatal_clip_rate`가 materially better이고 모든 stratum×event safety cell count가 B 이하이면 A 승리다.
2. 두 fatal rate가 equivalent이고 모든 safety cell count가 정확히 같을 때만 correction tier로 내려간다.
3. correction time이 materially better이면 A 승리, equivalent일 때만 text tier로 내려간다.
4. text tier에서는 적용 가능한 모든 rate의 CI upper bound가 `+MPE` 이하이고 하나 이상의 upper bound가
   `-MPE`보다 작을 때만 A 승리다. metric 하나라도 insufficient이면 승패 없음이다.
5. 상위 tier가 trade-off 또는 indeterminate이면 lower tier로 덮지 않고 그 pair를 incomparable로 둔다.

후보 C가 다른 두 후보 각각에 이 predicate로 패하고 그런 후보가 정확히 하나일 때만 C를 unique bottom으로
판정해 나머지 둘을 `top_two`로 권고한다. 다른 경우 primary verdict는 `reserve_required`다. reserve를
개봉하면 세 후보 모두 실행하고 primary+reserve 합친 동일 clip 집합에 같은 rule/hash를 재적용한다. 합친
결과에서 unique bottom이 생기면 `top_two`, 아니면 `inconclusive`다. 어떤 필수 evidence가 invalid/누락이면
`blocked`가 우선한다. paired clip/stratum, CI, MPE, safety veto와 pairwise relation 전체를 report에 보존한다.

reserve 뒤 `inconclusive`이면 3-way local 확장을 자동 실행하지 않고 11-run/17-stage 계약안을 별도 owner
decision으로 올린다.

## 6. evidence와 fail-closed 계약

이 TASK의 산출물은 `AsrScreenManifest/v1` 계열의 별도 CAS lineage다. TASK-031의
`CalibrationRunManifest/v1` 또는 completed 8/12 evidence로 가장하지 않는다.

최소 산출물:

1. frozen pack manifest와 primary/reserve content hash
2. 세 exact-revision model/access/license/file-hash receipt
3. dependency/runtime/config lock, Work CPU environment receipt와 `AsrScreenDecisionRule/v1` ref/hash
4. sentinel·primary·reserve(실행된 경우)의 attempt, raw output, normalized hypothesis, failure record
5. 후보별 sentinel interruption/resume record와 completed/incomplete unit의 before/after attempt·output refs
6. reference/annotation와 metric records, blinded correction packet과 실제 human correction records
7. paired clip/stratum report, CI·MPE·safety veto·pairwise relation, `top_two | inconclusive | blocked` verdict
8. target Windows용 한 setup/model-snapshot 명령과 winner/fallback 약 10분 probe 명령, 예상 artifact 목록과
   정확한 fail-closed 오류 메시지 catalog

모든 ref는 digest·size·kind·media type을 검증한다. candidate/config/pack/environment/decision-rule hash가
맞지 않거나, 필수 clip·attempt·raw output·human record 또는 후보별 interruption/resume record가 없으면
report는 `completed`가 될 수 없다. validator는 완료 unit 재실행, incomplete unit 미실행, 이전 interrupted
attempt 손실, 최종 ordered coverage의 누락·중복을 거부한다. CAS·cache/resume·lineage, 중단 attempt 보존,
원본 불변 계약은 TASK-028·031보다 약화하지 않는다.

## 7. target local hard gate와 TASK-031 관계

screen 상위 후보도 다음 local hard gate를 통과하기 전에는 채택되지 않는다.

- no OOM, crash or unrecoverable execution
- model preparation 뒤 fully local inference
- Windows 11 / RTX 4070 SUPER 12 GB 지원
- ASR RTF `<= 1.0`은 **제안값**이며 별도 contract amendment에서 명시적으로 freeze하기 전에는 합격선이 아니다

hard gate를 통과한 후보 사이에서는 속도가 아니라 frozen pack 품질과 human correction time으로 순위를 정한다.
상위 2종을 TASK-031의 local 2×2 ASR×MT calibration에 넣으려면 screening 결과 뒤 TASK-031 후보 identity를
명시적으로 amendment하고 fresh independent review와 제품 오너 승인을 받아야 한다. 이 TASK는 현재의
정확한 8 logical runs/12 candidate stages를 11/17로 늘리거나 Cohere를 조용히 끼워 넣지 않는다.

## 8. scope / non-scope / ownership

### 이 계약 PR의 허용 경로

- `docs/tasks/TASK-032.md`
- `STATUS.md`
- `PLAN.md`
- `docs/DECISIONS.md`

### 승인 후 implementation의 예상 exclusive 경로

- `config/task-032-*`
- `requirements/task-032/**`
- `schemas/asr-screen-*.schema.json`
- `src/media_clarity/asr_screen/**`
- `scripts/task_032_*`
- `tests/test_task032_*`
- `tests/fixtures/task_032/**`
- TASK-032 target을 추가하는 범위의 `Makefile`

정확한 implementation allowlist는 첫 구현 slice의 fixed base에서 다시 선언한다. 기존 TASK-031 schema/runtime은
소비만 하며 변경하지 않는다. 필요한 변경이 생기면 amendment와 review 전에는 쓰지 않는다.

### non-scope

- MT·alignment·subtitle·end-to-end 실행
- TASK-031 후보 교체, 3-way local 확장, 최종 모델 채택
- 유료 cloud GPU/API 또는 provider 선택
- target Windows 호환성·12 GB·RTF 합격 주장
- private media upload, model weight·평가 media·큰 generated artifact의 Git 저장
- Phase 2 live-action enhancement 구현. 이는 subtitle vertical slice 뒤 별도 Gate H TASK로만 연다.

## 9. 검증 ladder와 stop conditions

1. contract path allowlist와 TASK-031 무변경을 확인한다.
2. schema/validator와 small synthetic normal·boundary·failure·recovery fixtures를 먼저 만든다.
3. pack/license/access/model/dependency preflight를 fail-closed로 실행한다.
4. Work CPU 2분 sentinel을 후보별로 controlled-interrupt/resume하고 reuse·retry·coverage evidence를 고정한다.
5. 가능한 후보의 18분 primary를 실행하고, predicate가 요구하면 세 후보 모두 12분 reserve를 실행한다.
6. hash-locked decision rule의 CI·MPE·pairwise predicate를 검증하고 blind human records 뒤 report를 완성한다.
7. Windows bundle을 dry-run 검증하되 target-hardware success로 표기하지 않는다.
8. fixed HEAD를 fresh GPT/Codex가 독립 Gate H review한다.

즉시 중단하고 증거를 남기는 조건:

- private/sensitive media나 불명확한 라이선스 자료가 입력에 들어오려는 경우
- model revision/file hash 또는 dependency/config identity를 고정할 수 없는 경우
- Cohere gated access가 수락되지 않았거나 offline snapshot을 재현할 수 없는 경우
- 유료 provider/GPU가 필요하지만 provider·GPU·지출 상한 승인이 없는 경우
- 결과를 본 뒤 pack, VAD, language hint, chunking, normalization, decision-rule hash·CI·MPE·ranking predicate를 바꾸려는 경우
- TASK-031의 8/12 closed set을 이 TASK에서 변경해야 하는 경우

## 10. acceptance criteria

- [ ] 세 후보의 immutable identity와 access/license/file-hash receipt가 검증된다.
- [ ] 18분 primary와 12분 reserve가 출력 전에 함께 frozen되고 실제/합성 구성과 라이선스가 검증된다.
- [ ] reserve가 열리면 세 후보 모두 같은 12분을 실행하며 최대 9 jobs/96 unique scheduled audio-minutes가 검증된다.
- [ ] `AsrScreenDecisionRule/v1`의 metric·CI·MPE·source 수·predicate·hash가 출력 전에 고정되고 변경/누락이 fail-closed다.
- [ ] 세 후보 각각의 2분 sentinel에서 실제 controlled interruption/resume가 수행되고 완료 unit 재사용,
  미완료 unit만 재실행, 이전 attempt 보존, 최종 ordered coverage의 누락·중복 없음이 검증된다.
- [ ] 동일 config의 가능한 18분 primary가 Work CPU에서 실행되거나, 정확한 blocker가 재현된다.
- [ ] raw output·attempt·failure·metric·human correction evidence가 별도 CAS lineage로 보존된다.
- [ ] 누락/위조/foreign ref/재사용/순서·rule-hash 변경과 resume 위반이 fail-closed fixture로 거부된다.
- [ ] report가 `top_two`, `inconclusive`, `blocked` 중 하나만 내고, 범위를 넘어선 우월성·Windows 주장을 하지 않는다.
- [ ] 한 setup/model-snapshot 명령과 한 약 10분 winner/fallback local ASR 명령·expected artifacts·오류 catalog가 준비된다.
- [ ] TASK-031 exact 8/12 계약, models, dependencies, network, cost는 별도 amendment/approval 없이 바뀌지 않는다.
- [x] fixed HEAD `0945cf31411e6b3c5cc149518e55cfff34087ce0`가 fresh GPT/Codex Gate H review에서 승인되고, 제품 오너가 PR #61의 exact HEAD/base를 별도 승인해 `dd3e78645e9ece7fffd8843c10ba37abcdde0a8e`로 병합됐다.

## 11. rollback과 다음 허용 행동

계약 checkpoint의 rollback unit은 PR #61 전체다. 병합 전 거절 시 네 문서 변경만 되돌리는 범위였으며,
병합 뒤 rollback이 필요해도 TASK-031과 기존 CAS evidence는 그대로 보존한다.

- contract 승인·병합 뒤: deterministic schema/fixture/harness와 무료 Work-CPU preflight를 첫 구현 slice로 만든다.
- CPU 실행 가능: 후보별 interrupted/resumed sentinel → primary → 필요 시 세 후보 reserve 순서로 진행한다.
- CPU 실행 불가능: 준비 tooling을 끝낸 뒤 provider·GPU·지출 상한 decision gate만 제품 오너에게 요청한다.
- top two가 명확함: TASK-031 후보 identity amendment를 별도 Gate H로 제안한다.
- 세 후보가 비지배적: 11/17 확장안을 별도 제품 결정으로 올린다.
- 어느 경우도 Phase 2 visual enhancement code를 병행하지 않는다.
