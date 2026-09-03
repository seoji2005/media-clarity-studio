# TASK-032 — 공개·합성 frozen target pack 기반 3-ASR Work-CPU screening

- **Status:** In progress — Gate H 계약 checkpoint 작성
- **Gate:** H (새 모델·dependency/network 경계와 후속 후보 선택에 영향을 주는 평가 계약)
- **Created:** 2026-09-03
- **Base:** `main@0c0f40ea318aff8b69180c9c6f510a627b0e0b9c`
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

### 4.2 sentinel과 primary

- 후보마다 2분 sentinel을 1회 실행해 load 실패, 빈 출력, 반복 hallucination, chunk 조립 오류와 CPU 실행 가능성을 본다.
- sentinel은 후보를 자동 탈락시키는 속도 경기가 아니다. 실험이 유효하게 실행됐는지 판정한다.
- valid한 후보는 같은 Work CPU에서 순차·batch 1·무양자화·결정적 decoding으로 18분 primary를 실행한다.
- clip 경계와 dominant-language hint는 후보 사이에 동일하게 고정한다.
- 공통 VAD를 쓴다면 경계를 출력 전에 freeze한다. 2분 silence/non-speech probe는 세 후보 모두 VAD를 우회해
  silence hallucination을 직접 측정한다.
- retry는 환경·harness failure와 candidate failure를 구분하는 frozen 규칙에 따라서만 허용한다. 이전 attempt와
  실패 메시지를 보존하고 조용히 덮어쓰지 않는다.

기본 실행량은 6 top-level jobs, 60 audio-minutes다(2분×3 sentinel + 18분×3 primary). 2위와 3위가
분리되지 않거나 서로 다른 핵심 stratum에서 비지배적이면 두 후보에만 12분 reserve를 실행한다.
이 경우 최대 8 jobs, 84 audio-minutes다.

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

단일 종합 점수는 만들지 않는다. 선택 근거의 우선순위는 다음과 같다.

1. fatal omission·hallucination·silence hallucination과 실험 무효 여부
2. human correction time
3. Japanese CER·English WER
4. mixed-language와 names/numbers/technical-term 오류

paired clip/stratum 표를 만든다. 3위가 위 우선순위에서 다른 두 후보에 실질적으로 지배되고 독점적 안전 우위가
없을 때만 상위 2종 승격을 권고한다. primary로 2위/3위가 분리되지 않거나 핵심 stratum별 우승자가 갈리면
미리 고정한 reserve를 실행한다. reserve 뒤에도 세 후보가 비지배적이면 결과를 `inconclusive`로 두고,
3-way local 확장은 자동 실행하지 않은 채 11-run/17-stage 계약안을 별도 owner decision으로 올린다.

## 6. evidence와 fail-closed 계약

이 TASK의 산출물은 `AsrScreenManifest/v1` 계열의 별도 CAS lineage다. TASK-031의
`CalibrationRunManifest/v1` 또는 completed 8/12 evidence로 가장하지 않는다.

최소 산출물:

1. frozen pack manifest와 primary/reserve content hash
2. 세 exact-revision model/access/license/file-hash receipt
3. dependency/runtime/config lock과 Work CPU environment receipt
4. sentinel·primary·reserve(실행된 경우)의 attempt, raw output, normalized hypothesis, failure record
5. reference/annotation와 metric records, blinded correction packet과 실제 human correction records
6. paired clip/stratum report, dominance table, `top_two | inconclusive | blocked` verdict
7. target Windows용 한 setup/model-snapshot 명령과 winner/fallback 약 10분 probe 명령, 예상 artifact 목록과
   정확한 fail-closed 오류 메시지 catalog

모든 ref는 digest·size·kind·media type을 검증한다. candidate/config/pack/environment hash가 맞지 않거나,
필수 clip·attempt·raw output·human record가 없으면 report는 `completed`가 될 수 없다. CAS·cache/resume·lineage,
중단 attempt 보존, 원본 불변 계약은 TASK-028·031보다 약화하지 않는다.

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
4. Work CPU 2분 sentinel을 후보별로 실행하고 같은 HEAD에서 evidence를 고정한다.
5. 가능한 후보의 18분 primary, 조건 충족 시 12분 reserve를 실행한다.
6. blind human records가 들어온 뒤 report를 완성한다.
7. Windows bundle을 dry-run 검증하되 target-hardware success로 표기하지 않는다.
8. fixed HEAD를 fresh GPT/Codex가 독립 Gate H review한다.

즉시 중단하고 증거를 남기는 조건:

- private/sensitive media나 불명확한 라이선스 자료가 입력에 들어오려는 경우
- model revision/file hash 또는 dependency/config identity를 고정할 수 없는 경우
- Cohere gated access가 수락되지 않았거나 offline snapshot을 재현할 수 없는 경우
- 유료 provider/GPU가 필요하지만 provider·GPU·지출 상한 승인이 없는 경우
- 결과를 본 뒤 pack, VAD, language hint, chunking, normalization 또는 ranking rule을 바꾸려는 경우
- TASK-031의 8/12 closed set을 이 TASK에서 변경해야 하는 경우

## 10. acceptance criteria

- [ ] 세 후보의 immutable identity와 access/license/file-hash receipt가 검증된다.
- [ ] 18분 primary와 12분 reserve가 출력 전에 함께 frozen되고 실제/합성 구성과 라이선스가 검증된다.
- [ ] 동일 config의 2분 sentinel과 가능한 18분 primary가 Work CPU에서 실행되거나, 정확한 blocker가 재현된다.
- [ ] raw output·attempt·failure·metric·human correction evidence가 별도 CAS lineage로 보존된다.
- [ ] 누락/위조/foreign ref/재사용/순서 변경이 fail-closed fixture로 거부된다.
- [ ] report가 `top_two`, `inconclusive`, `blocked` 중 하나만 내고, 범위를 넘어선 우월성·Windows 주장을 하지 않는다.
- [ ] 한 setup/model-snapshot 명령과 한 약 10분 winner/fallback local ASR 명령·expected artifacts·오류 catalog가 준비된다.
- [ ] TASK-031 exact 8/12 계약, models, dependencies, network, cost는 별도 amendment/approval 없이 바뀌지 않는다.
- [ ] fixed HEAD가 fresh GPT/Codex Gate H review에서 승인되고, 제품 오너가 exact PR/HEAD/base를 별도 승인한다.

## 11. rollback과 다음 허용 행동

rollback unit은 TASK-032 branch/PR 전체다. contract가 거절되면 네 문서 변경만 되돌리며 TASK-031과 기존
CAS evidence는 그대로 남는다.

- contract 승인·병합 뒤: deterministic schema/fixture/harness와 무료 Work-CPU preflight를 첫 구현 slice로 만든다.
- CPU 실행 가능: sentinel → primary → 필요 시 reserve 순서로 진행한다.
- CPU 실행 불가능: 준비 tooling을 끝낸 뒤 provider·GPU·지출 상한 decision gate만 제품 오너에게 요청한다.
- top two가 명확함: TASK-031 후보 identity amendment를 별도 Gate H로 제안한다.
- 세 후보가 비지배적: 11/17 확장안을 별도 제품 결정으로 올린다.
- 어느 경우도 Phase 2 visual enhancement code를 병행하지 않는다.
