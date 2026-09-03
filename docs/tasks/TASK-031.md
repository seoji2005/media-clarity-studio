# TASK-031 — U-22 A-min 로컬 자막 calibration vertical slice

| 항목 | 값 |
|---|---|
| **ID** | TASK-031 |
| **결정자** | 사람 제품 오너 (2026-09-01, U-22 A-min 확정) |
| **Owner / Author** | Lean Root Author (TASK 전체). H-01·H-02 attempt 3·4는 Claude Code specialist가 작성했다. `d03885f…` 재검토 뒤 남은 `depends_on`·`cacheable` 결박 하나는 **2026-09-01 사람 제품 오너가 현재 Codex Author에게 명시적으로 재배정**했다 (아래 escalation 기록) |
| **Reviewer** | 계약 checkpoint `395a014f…`, preflight `e209653d…`, offline evidence core `2a5ccd38…`, manifest/report spine `1764c33b…`은 각각 작성자와 다른 fresh GPT/Codex 세션이 Gate H로 승인했다. 이후 coherent HEAD도 작성자와 다른 fresh reviewer가 검토한다 (R8) |
| **Phase** | Phase 1a — 첫 실제 자막 vertical slice와 calibration |
| **Gate** | H — 외부 모델·dependency, 12 GB GPU, Windows, cache/resume와 품질 판정 |
| **Status** | `In progress` — exact synthetic 8-cell/12-stage fixture와 fail-closed mutation matrix의 Author 검증 완료, fixed-HEAD Gate H 검토 대기. target Windows lock/environment evidence·model snapshot과 Windows/RTX 실측은 미착수 |
| **기준 main** | `356b964505c3d852e9a264d79da12f15e5e707e0` (PR #49 merge commit) |
| **계약 checkpoint** | 승인 HEAD `395a014fcda033c2be574e21d351e3bfec4c7e0e`, tree `c101ffcee0afc0c89fa4f4dada240ec2c8a6e59b`, PR #50 merge `e33ca4a15bfe0ba7091af6509bfdd9896904656c` |

## 목표

고정된 대표 10분 입력 하나에서 실제 오디오부터 원문 전사, 한국어 번역, 자막 문서와 calibration용 SRT까지
완전 로컬로 생성하고, 기존 CAS·lineage·checkpoint/resume 기반에 연결한다. 같은 입력과 고정 설정으로
ASR 2종 × 번역 2종을 분리·결합 측정해 U-22의 다음 모델 채택 판단에 필요한 정직한 증거를 만든다.

이 TASK는 계약을 더 넓히는 작업이 아니다. 기존 `Transcript/v1`, `TranslatedTranscript/v1`,
`SubtitleDocument/v1`, artifact store와 stage runtime을 실제 모델이 소비·생성하게 만드는 첫 측정
vertical slice다. 모델 우열이나 제품 완성도를 테스트 수로 주장하지 않는다.

## execution card

| 항목 | 값 |
|---|---|
| Source | live `main@ec7cdb93e97a3e823d8745e447edc4b83c7862d7` (PR #57 merge) |
| Active TASK | TASK-031 / `In progress` |
| Gate | H |
| Author / Reviewer | manifest/report spine `1764c33b…`은 Lean Root/Codex Author와 다른 fresh GPT/Codex가 Gate H 승인. 다음 synthetic fixture slice도 Lean Root/Codex Author / 별도 fresh reviewer |
| Approved scope | U-22 A-min 계약 기록, 재현 가능한 dependency manifest·Windows hash lock 준비, 고정 revision model weight 준비를 위한 network, 실제 10분 local calibration과 보고 |
| PR / branch | #50~#57 Closed/Merged / `lean-root/task-031-exact-matrix-validation` Author branch |
| Current checkpoint | production TASK-028 runtime/CAS로 8개 logical run과 12개 unique candidate-stage attempt를 만드는 정직한 `incomplete` fixture, cell/stage 누락·추가·재정렬·foreign/reuse mutation이 구현됐다. matrix 반례가 드러낸 candidate `config_hash`·backend identity·weight hash와 실제 StageSpec fingerprint의 미결박도 세 exact mapping으로 닫았다. timing/NVML/correction/interruption/final ancestry는 여전히 미검증이다 |
| Blocker | 현재 Work 환경은 Windows 11 / RTX 4070 SUPER가 아니므로 Windows transitive hash lock·CUDA stack·model cache receipt와 실제 측정 증거를 만들 수 없음 |
| Next allowed action | coherent HEAD를 push해 Draft PR로 고정하고 작성자와 다른 fresh GPT/Codex가 Gate H로 검토한다. 승인·제품 오너의 exact-HEAD merge 결정 뒤에만 Windows 실행 준비 도구로 진행한다 |
| Forbidden now | remote inference/comparator, 사용자 미디어 업로드·commit, model weight commit, 결과 전 기본 모델 채택, exact-HEAD 승인 없는 merge |

계약 checkpoint의 고정 좌표는 위 역사 기록으로 보존한다. 이후 구현 reviewer는 새 구현 PR의 live HEAD와
base를 별도로 고정하고 compact handoff와 repository tree를 대조한다.

### dependency/model/network 제품 오너 gate — 승인

2026-09-01 사람 제품 오너는 TASK-031 범위 안에서 다음을 승인했다.

- backend별 재현 가능한 dependency manifest와 Windows hash lock 준비
- §2의 다섯 공식 model ID를 고정 revision으로 준비·다운로드하는 데 필요한 외부 network 사용
- 준비 evidence를 바탕으로 local-only calibration 구현을 계속하는 것

이 승인은 remote inference/comparator, 사용자 미디어 전송, model weight의 Git commit, 영구/default model
채택 또는 PR 병합 승인이 아니다. target Windows에서 lock·CUDA stack·model receipt가 모두 검증되기 전에는
실행 readiness를 통과시키지 않는다.

### PR #52 첫 Gate H 변경 요청과 제한 remediation

fresh read-only reviewer는 PR #52 fixed HEAD
`5f56b12b0b508f1e01e01f52427760b4f2fc7b5d`(tree
`a92ea7c4077ab80c95551cc09fdf8cd35b052b67`, base/parent
`e9e7a4eb102a1573cf7479cb005a0fb4d647fa88`)에 **변경 요청**을 판정했다.

- H-01: lock의 SHA와 각 행의 pin/hash 모양만 검사해 `.in` direct package가 전부 빠지고
  `unrelated-package==9.9.9`만 있어도 readiness가 통과했다.
- H-02: `resolver_version`·`torch_version`·`cuda_version`·`cudnn_version`에 임의 문자열을 넣고
  `cuda_stack_status="windows_locked"`로 선언하면 target-Windows 기계 evidence 없이 통과했다.

remediation은 다음으로 한정한다.

1. lock의 각 resolved requirement는 exact pin+SHA-256을 유지하고, 실제 `.in`과 manifest가 합의한 모든
   direct package의 canonical name과 exact version이 lock에 존재해야 한다. transitive package는 허용하지만
   direct 누락·version 교체·unrelated-only lock은 `E_LOCK_INPUT`으로 실패한다.
2. 네 환경의 Python 경로와 evidence 경로를 고정한다. 각 고정 interpreter의 Windows capture가 resolver
   실행 파일·raw version, installed direct package, Windows build, GPU/driver, CUDA runtime/PyTorch/cuDNN을
   닫힌 receipt로 기록하고 manifest version을 그 probe 값으로만 갱신한다.
3. readiness는 receipt schema·outer digest·raw/parsed/manifest equality 뒤에도 고정 Python을 다시 실행해
   live probe와 receipt의 exact equality를 확인한다. 임의 version 문자열, receipt 변조 후 재hash, 환경 drift는
   각각 pending/evidence/live-mismatch finding으로 fail-closed한다. local administrator에 대한 원격 attestation은
   주장하지 않는다.

이 remediation의 작성자는 Lean Root/Codex이므로 새 HEAD를 승인하지 않으며 R8의 fresh reviewer가 필요하다.
focused `test_calibration_preflight.py` 16건과 전체 512 tests, preparation CLI, `git diff --check`는 통과했다.
실제 Windows 11/RTX 4070 SUPER capture와 네 live interpreter 재실행은 이 환경에서 확인하지 않았으며
review evidence로 가장하지 않는다.

### PR #52 final approval과 merge

- 작성자와 이전 `5f56b12…` 변경 요청 reviewer 모두와 분리된 fresh GPT/Codex 제한 재검토는 fixed HEAD
  `e209653d869362fda5eeac73775685649d594098`(tree
  `561c0ea437b8b9225c15079992286a234e9bb99d`)에서 H-01·H-02 해소와 prohibited drift 없음을 **승인**했다.
- 사람 제품 오너는 PR #52·전체 HEAD·reviewed base
  `e9e7a4eb102a1573cf7479cb005a0fb4d647fa88`를 정확히 승인했다.
- PR #52는 merge commit `033032ef14e2f130be18685010fc4fac2792d95f`로 병합됐다. 부모는 reviewed base와
  승인 HEAD이며 merge tree는 승인 tree와 같고 승인 HEAD 대비 변경 파일은 0개다.
- 이 병합은 preflight 기반만 완료한다. 실제 target Windows lock/environment evidence, model snapshot,
  10분 calibration, Windows/RTX 실측과 기본 모델 채택은 완료하거나 승인하지 않았다.

### escalation 기록 — `AGENTS.md` §3 trigger 3

같은 객관적 결함(H-01·H-02)을 GPT 제한 수정이 **두 번** 닫지 못했다. §3 trigger 3에 따라 세 번째 GPT
반복을 금지하고 Claude Code specialist에게 이 remediation을 배정했다. 두 attempt의 HEAD·잔여 결함·표적
검사는 다음과 같다.

| attempt | fixed HEAD | 닫으려 한 것 | 재검토에서 남은 결함 | 표적 검사 |
|---|---|---|---|---|
| 1 | `6c3df57ae60ae411baef546a42f3f51509559ee7` | H-01 성능 record ↔ candidate stage 결박, H-02 lazy iterator 소비와 NVML frozen identity | H-01: stage/workload lineage와 exact matrix coverage 미완결. H-02: lazy timing과 Windows/WDDM 측정 경계 미완결 | `6c3df57` 계약 본문의 stage lineage·matrix coverage·timing 문구 검사 |
| 2 | `111f118bf88f1913b10a04123b53bbc193b8d6ca` | 위 잔여 H-01·H-02 | H-01: (a) `job_id`·runtime `stage_id`·canonical attempt_path/attempt-record ref 부재로 measurement가 실행에 결박되지 않음, (b) runtime attempt identity 유일성 규정 부재이며 CAS 중복 제거와 실행 재사용을 구분하지 않음, (c) `final_pipeline_output_refs`의 내용·순서·계보·non-empty 미정의로 **빈 tuple이 동일성 검사를 통과**. H-02: (d) `output-materialized` event가 byte length만 결박해 timed-end 뒤 **same-length 교체가 검출되지 않음**, (e) NVML sample record가 measurement에 결박되지 않아 **하나의 unscoped record를 ASR·MT가 공유**해도 통과 | `111f118` 본문에 대한 텍스트 probe: `job_id` 출현 0회, `attempt_path` 0회, CAS dedup 구분 문구 0회, `final_pipeline_output_refs`의 정의·non-empty·ancestry 규정 0회, materialization event의 digest 결박 0회, sample record의 scope field 0회 |

| 3 | `33b7ccddc18878f9f3ffc8cb51f9abe42347d94c` (Claude Code specialist) | 위 (a)~(e) 다섯 우회 경로 | H-01 잔여: §5.1.1이 `AttemptRecord`에 **없는** 이름·모양을 요구했다 — `runtime_stage_id`(실물은 `stage_id`), 정의되지 않은 `stage_spec_fingerprint`(실물은 `fingerprints`와 `cache_key`), scalar `raw_output_ref`(실물은 ordered `outputs[]`). 모든 유효 record를 거부하거나 validator가 미규정 매핑을 지어내야 했고, attempt가 output을 여러 개 가질 때 하나만 결박해도 통과했다 | `schemas/job-v1.schema.json#/$defs/AttemptRecord`와 `job_runtime.py` record writer를 실물 대조: `runtime_stage_id` 부재, `stage_spec_fingerprint` 부재, `outputs`는 `ArtifactRef` array |
| 4 | `d03885f12232bc348cec5822978e8367121d19b9` (Claude Code specialist) | attempt 3의 AttemptRecord 이름·모양 불일치 | H-01 잔여: canonical StageSpec document의 `depends_on`·`cacheable`은 self-digest에는 들어가지만 실제 실행 증거와 비교되지 않았다. 두 값을 바꾸고 digest를 다시 계산해도 `fingerprints`·cache-key 검사를 통과할 수 있었다 | 실제 `StageSpec` 두 변형의 `fingerprints`·`stage_cache_key_document`·cache key 동일성 probe, `AttemptRecord.cacheable` writer와 dependency mapping 대조 |

이번(다섯 번째) remediation은 attempt 4가 남긴 **두 필드의 runtime provenance 결박 하나만** 닫는다.
사람 제품 오너는 2026-09-01 이 잔여 결함에 한해 Codex Author로 명시적으로 재배정했다. 이는 앞선
`AGENTS.md` §3 trigger 3, 두 GPT 실패와 Claude attempt의 역사를 지우거나 일반적인 GPT 반복을 다시 허용하는
운영 변경이 아니다. 앞선 (a)~(e) 다섯 경로와 H-02 조항은 문구·의미 모두 보존한다. 계약 범위를 넓히거나
§11의 구현 경계, 모델·dependency·network gate를 바꾸지 않는다.

### PR #54 offline evidence core final approval과 merge

- fresh GPT/Codex 제한 재검토는 fixed HEAD `2a5ccd38c401a0a33e575f4f0ae4f409c6db7456`
  (tree `786004490769ac3f26b6e843690f9ade5d6a4c7e`)에서 canonical CAS 결박 G54-01과 malformed
  identity 안정 finding G54-02의 해소, 기존 attempt uniqueness·정상 CAS byte dedup 보존을 **승인**했다.
- 사람 제품 오너는 PR #54·전체 HEAD·reviewed base
  `47df9935eb662b7d7e8176f416df656d07371cd6`를 정확히 승인했다.
- PR #54는 merge commit `1073b984a443caf0db5c1631eb09dbaf7c8830a0`로 병합됐다. 부모는 reviewed base와
  승인 HEAD이고 merge tree는 승인 tree와 같으며 승인 HEAD 대비 파일 변경은 0개다.
- 이는 hardware-independent runtime provenance만 완료한다. TASK-031은 계속 `In progress`이며
  manifest/report spine, synthetic 8-cell validation, timing/NVML, target Windows/model evidence와 실제
  calibration은 완료되지 않았다.

### manifest/report evidence spine 구현 경계

이 slice는 §5.1·§5.5의 evidence index와 hardware-independent runtime linkage만 구현한다.

- `CalibrationRunManifest/v1`, runtime-only `PerformanceMeasurement/v1`, `CalibrationReport/v1`은
  닫힌 schema이며 report에는 correction/RTF/VRAM 자유 숫자를 두지 않는다.
- fixed cell은 run kind, ordered adapter role, official model ID와 frozen revision을 결정한다.
  `candidate_chain_hash`는 ordered role+candidate identity/config record에서 재계산한다.
- task-local JSON ref는 canonical CAS URI·digest·bytes를 검증하고 report entry와 manifest,
  manifest candidate stage와 measurement projection은 exact equality여야 한다. measurement는 기존
  offline evidence core를 호출해 실제 TASK-028 attempt와 다시 결박한다.
- current validator는 미검증 축을 열거한 `incomplete`만 허용한다. timing/materialization·NVML,
  correction/interruption 의미와 final-output producer ancestry가 구현되기 전 `completed`는 fail-closed다.
- 다음 slice가 exact 8 manifest·12 measurement의 full synthetic fixture와 누락·추가·재정렬·foreign/reuse
  mutation을 exhaustive하게 고정한다. 이 slice의 단일-link positive test를 실제 calibration 완료로 해석하지 않는다.
- fresh Gate H는 fixed HEAD `51a7e08b15667956341898d34bc646c7ac44bcf5`에서 escaped unpaired
  surrogate를 포함한 referenced manifest/measurement의 canonical 재직렬화가 structured finding 대신
  `UnicodeEncodeError`를 유발하는 G56-01을 **변경 요청**했다. 제한 remediation은
  `UnicodeEncodeError`·`TypeError`·`ValueError`를 `E_CALIBRATION_ARTIFACT`로 변환하고 양쪽 참조 경계의
  mutation test를 고정한다. 새 fixed HEAD는 작성자와 다른 fresh reviewer 재검토가 필요했고 아래 final
  approval에서 충족됐다.
- focused manifest/report 17건, 기존 evidence 25건, preflight 16건과 전체 554 tests·FFmpeg smoke를 통과했다.

### PR #55 offline evidence merge 정합화

- Gate M 검토는 fixed HEAD `ad4f7ebb9330f87747fbb1cc90a9a4460b61c7ff`(tree
  `cfc3a34cef89723e2bb64eddd09582c5cc10e655`)에서 PR #54 병합 좌표와 다음 포인터가 정확하고
  prohibited drift가 없음을 **승인**했다.
- 사람 제품 오너는 PR #55·전체 HEAD·reviewed base
  `1073b984a443caf0db5c1631eb09dbaf7c8830a0`를 정확히 승인했다.
- PR #55는 merge commit `ad1e3e09959ca351432ecb2f50e4ba0c0255af28`로 병합됐으며 승인 HEAD 대비
  변경 파일은 0개다.

### PR #56 manifest/report final approval과 merge

- fresh 제한 재검토는 remediation fixed HEAD `1764c33b20c5a8aa9d5568eb7964a8eb44459a46`
  (tree `4d1d93e5b113a95824cea2b0add41f09ea81aeeb`)에서 G56-01 해소, 기존 정상 canonical CAS 검증
  보존과 prohibited drift 없음을 **승인**했다.
- 사람 제품 오너는 PR #56·전체 HEAD·reviewed base
  `ad1e3e09959ca351432ecb2f50e4ba0c0255af28`를 정확히 승인했다.
- PR #56은 merge commit `6cce66fbb07f01d0c5aa5388cdfa9d5525e84ad2`로 병합됐다. 승인 HEAD 대비
  merge commit은 1커밋 앞이고 변경 파일은 0개다.
- 이 병합은 manifest/report evidence spine만 완료한다. TASK-031은 계속 `In progress`이며 exact synthetic
  8-cell/12-stage validation, timing/NVML, Windows 실행 준비와 실제 model snapshot·실측은 남아 있다.

## 1. 고정 입력

- 총 길이 10분인 content-locked calibration pack 하나를 쓴다.
- 일본어 일반 발화, 일본어·영어 code-switching, 고유명사·숫자·전문용어, 무음·음악·배경소음,
  빠른 발화 또는 겹침 중 최소 하나를 포함한다.
- 여러 구간을 이어도 되지만 입력 파일, 구간 순서·경계, 구성 manifest와 SHA-256을 첫 결과 전에 고정한다.
- 결과를 본 뒤 구간을 교체하지 않는다. harness 결함으로 pack 자체가 무효라면 기존 pack과 결과를
  보존하고 새 identity로 전부 다시 시작한다.
- pack 원본, 모델 weight, 생성 미디어와 민감한 transcript는 Git에 넣지 않는다. 저장소에는 비식별
  manifest·hash·재현 명령·집계 결과만 남긴다.
- 이 결과는 단일 입력 engineering calibration이다. 전체 도메인이나 일반적인 모델 우열을 증명하지 않는다.

## 2. 후보와 실행 전 freeze

| 단계 | 후보 |
|---|---|
| ASR | faster-whisper large-v3 |
| ASR | Qwen3-ASR-1.7B |
| 번역 | MADLAD-400-3B-MT |
| 번역 | Qwen3.5-4B |
| 공통 scored alignment | Qwen ForcedAligner |

2026-09-01 계약 checkpoint에서 공식 배포처의 다음 immutable revision을 관측했다. 별도 gate가 승인되면
다운로드 직전에 동일 identity와 license metadata를 다시 확인하고, calibration manifest에는 full SHA를 쓴다.

| 역할 | 공식 model ID | candidate revision | 배포처 license metadata |
|---|---|---|---|
| ASR | `Systran/faster-whisper-large-v3` | `edaa852ec7e145841d8ffdb056a99866b5f0a478` | MIT |
| ASR | `Qwen/Qwen3-ASR-1.7B` | `7278e1e70fe206f11671096ffdd38061171dd6e5` | Apache-2.0 |
| 번역 | `google/madlad400-3b-mt` | `fa184c675da0b5c9e1c8694fccd4e12e2d422094` | Apache-2.0 |
| 번역 | `Qwen/Qwen3.5-4B` | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` | Apache-2.0 |
| 정렬 | `Qwen/Qwen3-ForcedAligner-0.6B` | `c7cbfc2048c462b0d63a45797104fc9db3ad62b7` | Apache-2.0 |

정본 확인 위치는 각 공식 repository의 commit page다:
[faster-whisper](https://huggingface.co/Systran/faster-whisper-large-v3/commit/edaa852ec7e145841d8ffdb056a99866b5f0a478),
[Qwen3-ASR](https://huggingface.co/Qwen/Qwen3-ASR-1.7B/commit/7278e1e70fe206f11671096ffdd38061171dd6e5),
[MADLAD](https://huggingface.co/google/madlad400-3b-mt/commit/fa184c675da0b5c9e1c8694fccd4e12e2d422094),
[Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-4B/commit/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a),
[ForcedAligner](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B/commit/c7cbfc2048c462b0d63a45797104fc9db3ad62b7).

배포처 metadata 기록은 프로젝트 사용·배포 적합성에 대한 법률 결론이 아니다. 각 후보의 precision·quantization,
decoding, VAD·chunking, context policy, CUDA·PyTorch·Python·Windows·driver 버전뿐 아니라 package version,
source commit 또는 wheel hash까지 실행 전에 한 manifest에 고정한다. mutable branch나 unpinned package를 실행
identity로 쓰지 않는다. 결과를 본 뒤 특정 후보만 beam, prompt, chunk 크기 등을 바꾸지 않는다. 공통 harness
결함을 고쳤다면 영향받은 비교군 전체를 같은 설정으로 다시 실행하고 이전 결과를 보존한다.

모델 후보 확정은 다운로드·재배포·상업 이용 허가가 아니다. license나 사용 조건이 불명확하면 그 후보는
hard gate에서 멈추고 제품 오너에게 근거를 반환한다.

## 3. 최소 실행 행렬

### 3.1 독립 ASR — 2회

같은 10분 오디오를 faster-whisper large-v3와 Qwen3-ASR-1.7B로 각각 실행한다.

- 치명적 누락·환각의 timestamp와 내용
- source transcript 수정시간
- 정상 완료 run의 RTF와 peak VRAM
- crash·OOM·비결정적 종료 등 Windows 실행 이상
- 모델 로딩·추론의 local-only 여부

### 3.2 독립 번역 — 2회

ASR 출력이 아니라 pack과 함께 고정한 동일 human-corrected source transcript를 MADLAD-400-3B-MT와
Qwen3.5-4B에 각각 넣는다.

이 입력은 ASR evidence인 `Transcript/v1`이 아니다. pack SHA와 연결된 task-local benchmark input으로
별도 저장하고, exact text·고정 segment ID/경계·human-correction provenance·content hash를 기록한다.
독립 번역 출력도 제품 `TranslatedTranscript/v1`을 가장하지 않는 benchmark evidence다. 실제 end-to-end
4회만 ASR이 생성한 immutable `Transcript/v1`을 TranslationAdapter에 넣어 `TranslatedTranscript/v1`을 만든다.

- 의미 누락·추가·반전
- 고유명사·숫자·code-switching 처리
- target Korean 수정시간
- 정상 완료 run의 RTF와 peak VRAM
- Windows 실행 이상과 local-only 여부

### 3.3 end-to-end — 4회

1. faster-whisper × MADLAD
2. faster-whisper × Qwen3.5
3. Qwen3-ASR × MADLAD
4. Qwen3-ASR × Qwen3.5

각 조합은 원본 오디오부터 `Transcript/v1` → `TranslatedTranscript/v1` → `SubtitleDocument/v1` → SRT까지
실제 pipeline으로 완료한다. 독립 단계 결과를 더해 end-to-end 실행을 대신하지 않는다. 따라서 완료에
필요한 최소 범위는 총 8개 논리 run이다.

SRT는 이 calibration의 공통 비교 export일 뿐 제품의 최종 출력 형식 결정이 아니다. U-09의
SRT/VTT/ASS 제품 선택은 계속 미해결로 둔다.

faster-whisper × MADLAD 한 조합의 선행 smoke는 harness 경로 확인용으로 허용하지만 TASK-031 또는
U-22를 완료하지 않는다.

## 4. 정렬 경계

- 네 end-to-end 조합의 공통 scored alignment는 Qwen ForcedAligner로 통일한다.
- faster-whisper native timestamp는 동일한 faster-whisper transcript에 한 번의 paired diagnostic으로만 비교한다.
- 정렬을 세 번째 factorial 축으로 만들지 않고 ASR·번역 점수에 별도 효과로 합산하지 않는다.
- forced alignment는 별도 immutable artifact이며 원문 `Transcript/v1`의 raw ASR text·timing을 덮어쓰지 않는다.
- 공식 구현의 단일 입력 상한이 5분이므로 10분 pack을 한 번에 넣지 않는다. 각 committed ASR audio/text
  segment를 반개구간 `[start, end)`의 결정론적 정렬 단위로 사용하고 각 단위를 300초 이하로 제한한다.
  300초를 넘는 segment가 생기면 결과를 보기 전에 고정한 ASR chunk 경계에서 나누며 임의 재분할하지 않는다.
- 각 정렬 단위의 출력은 원본 단위 identity와 time origin을 기록하고, pack 시간축에는 그 origin만 더해 stitch한다.
  겹치는 중복 단위를 만들지 않으며 입력 단위의 identity·순서·전 범위가 결과에서 정확히 한 번 나타나는지 검증한다.
- task-local `AlignmentEvidence/v1`은 최소한 source `Transcript/v1` artifact ref, audio artifact ref, aligner의
  exact model/runtime identity, 정렬 단위 ID와 time origin, source segment ID, exact source text의 Unicode scalar
  반개구간, 정렬된 start/end seconds, coverage gap과 실패 사유를 담는 닫힌 형식과 validator를 갖는다.
  source scalar 범위는 겹치거나 사라지지 않고 exact substring과 일치해야 하며 시간 범위는 원본 단위 안에 있어야 한다.
- 이 evidence는 calibration 전용 별도 CAS artifact다. `Transcript/v1`·`TranslatedTranscript/v1`·기존 token
  timing을 수정하지 않으며 제품의 장기 alignment schema를 자동 확정하지 않는다. 이 최소 형식과 validator를
  먼저 만들지 못하면 aligner 실행을 중단하고 계약 finding으로 돌린다.
- TASK-029에서 공식 LID accuracy는 계속 `unsupported`다. 임의 proxy를 LID라고 기록하지 않는다.

## 5. calibration evidence spine

모든 task-local evidence 문서는 canonical JSON의 닫힌 형식(`additionalProperties: false`)이고
`schema_version`을 가진다. 문서와 문서가 가리키는 raw/corrected output은 기존 artifact store의 CAS에
먼저 기록하며, ref에는 digest·size·kind·media type을 모두 넣는다. validator는 ref의 실제 bytes를 다시
읽어 digest·size·media type을 확인하고 아래 identity·상호 참조를 검증한다. 하나라도 없거나 맞지 않으면
run과 집계 report는 `completed`가 될 수 없다.
task-local JSON document ref의 exact identity는 `kind="text"`, `media_type="application/json"`이며,
adapter-native raw bytes는 실제 형식의 media type을 별도로 기록한다.

### 5.1 `CalibrationRunManifest/v1`

8개 논리 run 각각에 하나가 필요하며 최소 필드는 다음과 같다.

| 묶음 | 필수 내용 |
|---|---|
| run identity | `run_id`, `run_kind`(`independent_asr | independent_mt | end_to_end`), matrix cell, start/end UTC, 최종 status |
| candidate identity | 순서 있는 adapter role, official model ID·full revision, weight CAS hash, backend/runtime package·source identity, precision·quantization, decoding/VAD/chunk/context config hash와 그 ordered record의 `candidate_chain_hash` |
| environment | `EnvironmentRecord/v1` ref와 Windows build, GPU UUID·model·total memory, driver·CUDA·NVML, Python, sampler/runner source commit |
| inputs | calibration pack manifest/audio ref와 정확히 600초 timebase; 독립 MT는 benchmark input ref, end-to-end는 upstream `Transcript/v1` 등 실제 product document refs |
| outputs | candidate stage마다 ordered adapter-native `raw_output_refs`, normalized product 또는 benchmark output refs, `end_to_end`이면 §5.1.2의 네 원소 ordered `final_pipeline_output_refs`, axis별 accepted corrected output·correction record refs, alignment evidence ref가 필요한 run이면 그 ref |
| measurements | stage별 `PerformanceMeasurement/v1` refs와 quality event refs; 숫자를 manifest에 자유롭게 재기입하지 않음 |
| recovery | §5.1.1의 unit별 runtime identity tuple(`job_id`, `runtime_stage_id`(=`AttemptRecord.stage_id`), `attempt_id`, `attempt_record_ref`, `cache_key`, `stage_spec_digest`, `stage_spec_document_ref`, ordered `input_ref_tuple`, ordered `output_ref_tuple`), cache key 재계산에 필요한 `pipeline_id`·`dependency_cache_keys`, artifact refs, 배정된 end-to-end run의 `InterruptionRecord/v1` ref |
| config | pack hash, candidate config hash, calibration-only style hash, chunk/stitch hash, pipeline source commit |

`candidate_chain_hash`는 single candidate도 포함해 ordered adapter identity/config record의 canonical hash다.
candidate/config identity는 해당 `StageSpec` fingerprint와 raw output provenance에 있는 값과 정확히 같아야 한다.
`completed` manifest는 필요한 모든 ref가 존재·검증되고 raw output과 corrected output이 별도 CAS object이며,
correction·measurement·interruption record의 `run_id`와 config hash가 manifest와 같은 경우에만 유효하다.
독립 ASR은 source correction 1개, 독립 MT는 target correction 1개, end-to-end는 source·target correction을
각각 요구한다. end-to-end의 ASR·MT raw output을 하나의 최종 문자열로 접어 잃는 것을 금지한다.

`matrix_cell_id`는 다음 닫힌 집합 중 정확히 하나이며 candidate role·model ID와 서로 결정적으로 일치해야 한다.

| run kind | 허용 `matrix_cell_id` | 필수 candidate stage |
|---|---|---|
| `independent_asr` | `asr-faster-whisper`, `asr-qwen3-asr` | 각각 `asr` 1개 |
| `independent_mt` | `mt-madlad`, `mt-qwen3.5` | 각각 `mt` 1개 |
| `end_to_end` | `e2e-faster-whisper__madlad`, `e2e-faster-whisper__qwen3.5`, `e2e-qwen3-asr__madlad`, `e2e-qwen3-asr__qwen3.5` | 각각 ordered `asr`, `mt` 2개 |

각 candidate stage는 stable `candidate_stage_id`, `adapter_role`, ordered `unit_ids`, 각 unit과 같은 순서의
`stage_spec_digests`와 `stage_spec_document_refs`(§5.1.1.1), `attempt_ids`, `cache_keys`,
`input_ref_tuples`, `output_ref_tuples`(§5.1.1.2), `raw_output_refs`, 그리고
`aggregate_normalized_output_ref`를 manifest에 가진다. 같은 identity를 해당 stage의
`PerformanceMeasurement/v1`이 그대로 참조해야 한다. 따라서 전체
calibration에는 독립 run 4개에서 4개, end-to-end run 4개에서 8개인 **정확히 12개 candidate-stage
measurement**가 필요하다. forced alignment와 subtitle composition은 이 12개 후보 성능 측정에 포함하지 않는다.
measurement ref·`measurement_id`·candidate stage identity는 전역에서 유일하며 다른 run이나 stage에 재사용할 수
없다. validator는 runtime attempt record와 manifest와 measurement의 unit/attempt/cache/input/raw/aggregate output
tuple을 exact equality로 비교한다.

#### 5.1.1 measured candidate stage의 runtime identity 결박 (H-01)

`attempt_ids`만으로는 측정을 어느 실행에 결박할 수 없다. attempt ID는 그 자체로 전역 유일이 아니고,
가리키는 runtime record가 실제로 존재하는지도 증명하지 않는다. 그래서 12개 measured candidate stage는
각 unit마다 다음 **runtime identity tuple**을 manifest와 `PerformanceMeasurement/v1` 양쪽에 같은 순서로
가진다.

정본은 TASK-028의 실제 `AttemptRecord`
([`schemas/job-v1.schema.json`](../../schemas/job-v1.schema.json) `#/$defs/AttemptRecord`,
`src/media_clarity/job_runtime.py`가 기록)다. 아래 이름과 모양은 그 record에 **실제로 있는 필드**에만
결박하며, record 안에 없는 필드를 있다고 가정하지 않는다.

| field | 내용 | AttemptRecord 대응 |
|---|---|---|
| `job_id` | 그 unit을 실행한 TASK-028 runtime job의 ID | `job_id` |
| `runtime_stage_id` | runtime이 그 job 안에서 쓴 stage ID. calibration의 `candidate_stage_id`와 다른 축이며 둘 다 기록한다 | **`runtime_stage_id := AttemptRecord.stage_id`** — 값이 같아야 하는 별칭이며 record에 `runtime_stage_id`라는 필드가 있다고 가정하지 않는다 |
| `attempt_id` | 그 unit의 실행 attempt ID | `attempt_id` |
| `attempt_record_ref` | 그 attempt record의 **canonical attempt_path 또는 immutable attempt-record CAS ref**. 둘 중 하나를 실행 전에 골라 전 run에 동일하게 적용하고 environment record에 그 선택을 남긴다 | canonical attempt_path는 `jobs/<job_id>/stages/<stage_id>/attempts/<attempt_id>.json`이며 runtime의 `canonical_attempt_path()`가 돌려주는 project root 기준 relative path와 같아야 한다 |
| `cache_key` | 그 unit의 cache key | `cache_key` |
| `stage_spec_digest` | §5.1.1.1이 정의한 canonical StageSpec identity document의 digest | **AttemptRecord에는 이 필드가 없다.** §5.1.1.1의 절차로 재계산·대조한다 |
| `stage_spec_document_ref` | 그 canonical StageSpec identity document의 CAS ref | 없음 — manifest가 소유한다 |
| `input_ref_tuple` | 그 attempt가 실제로 소비한 ordered input refs | `inputs[]`와 **순서까지 exact equality** |
| `output_ref_tuple` | 그 attempt가 실제로 생산한 ordered output refs | `outputs[]`와 **순서까지 exact equality**. §5.1.1.2가 cardinality를 고정한다 |

validator는 `attempt_record_ref`를 **실제로 읽어** 그 record의 `job_id`·`stage_id`·`attempt_id`·
`cache_key`·`inputs[]`·`outputs[]`가 manifest·measurement의 같은 자리 값(`runtime_stage_id`는 `stage_id`에,
`input_ref_tuple`·`output_ref_tuple`은 배열에 순서까지 그대로)과 exact equality인지 확인하고,
`stage_spec_digest`는 §5.1.1.1의 절차로 **재계산**해 대조한다. record를 읽을 수 없거나, 매핑이 없거나,
한 자리라도 다르면 그 stage measurement는 `invalid`이고 run은 `completed`가 될 수 없다.

#### 5.1.1.1 canonical StageSpec identity (H-01)

`AttemptRecord`에는 `stage_spec_fingerprint`가 없다. 있는 것은 `fingerprints`(제공된 값만 담는 객체)와
`cache_key`뿐이고, `cache_key`는 stage identity에 더해 그 실행의 `input_artifact_hashes`와
`dependency_cache_keys`까지 포함하므로 StageSpec identity와 같지 않다. 그래서 아래 **하나의 결정적이고
구현 가능한 identity**를 정의하고, validator가 그것을 재계산해 record와 잇는다.

**canonical document.** `StageSpec` identity document는 다음 필드만 갖는 닫힌 JSON 객체다. 제공되지 않은
선택 fingerprint는 필드를 생략하지 않고 **`null`로 명시**한다 (runtime이 cache key에서 부재를 `null`로
다루는 것과 같은 규약).

```
kind                     "task031_stage_spec_identity"   (고정 문자열)
runtime_version          그 실행의 runtime version
schema_version           그 실행의 schema version
pipeline_id              JobSpec.pipeline_id
stage_id                 StageSpec.stage_id
implementation_version   StageSpec.implementation_version
depends_on               StageSpec.depends_on 을 오름차순 정렬한 배열
config_hash              StageSpec.config_hash            | null
dependency_fingerprint   StageSpec.dependency_fingerprint | null
source_hash              StageSpec.source_hash            | null
chunking_hash            StageSpec.chunking_hash          | null
model_hash               StageSpec.model_hash             | null
context_hash             StageSpec.context_hash           | null
random_seed              StageSpec.random_seed            | null
reproducibility_tier     StageSpec.reproducibility_tier   | null
cacheable                StageSpec.cacheable
```

**serialization과 digest.** 바이트 표현은 UTF-8, key 오름차순 정렬, separator `(",", ":")`,
NaN/Infinity 금지의 canonical JSON 하나뿐이다. `stage_spec_digest`는 그 바이트의 SHA-256이며 표기는
`common-v1`의 `content_hash` 형식이다. 다른 직렬화·다른 알고리즘·다른 필드 집합을 쓰지 않는다.

**저장 위치.** 이 document는 실행 전에 고정해 **기존 artifact store CAS에 기록**하고, 그 ref를 manifest의
해당 candidate stage unit에 `stage_spec_document_ref`로, digest를 `stage_spec_digest`로 둔다. 문서를
저장하지 않고 digest만 적는 것을 금지한다 — 재계산할 원본이 없으면 검증할 수 없다.

**validator 절차.** 각 measured unit에 대해 순서대로 수행하고, 한 단계라도 실패하면 그 measurement는
`invalid`다.

1. `stage_spec_document_ref`를 CAS에서 읽는다. ref가 없거나 읽히지 않으면 실패다.
2. 읽은 바이트를 위 canonical 규약으로 다시 직렬화해 digest를 계산하고 `stage_spec_digest`와 대조한다.
3. document의 `stage_id`가 `AttemptRecord.stage_id`와 같은지 확인한다.
4. document의 선택 fingerprint를 runtime의 기록 규약대로 **투영**한다 — `implementation_version`은 항상,
   나머지 일곱은 `null`이 아닐 때만 포함. 그 투영 결과가 `AttemptRecord.fingerprints`와 exact equality여야
   한다. 이어서 `AttemptRecord.cacheable`이 실제 record에 존재하는지 확인하고 document의 `cacheable`과
   boolean exact equality로 대조한다. TASK-028 writer는 이 필드를 항상 기록하지만 schema상 optional이므로,
   TASK-031 measured attempt에서 필드가 없으면 추측하지 않고 실패한다.
5. document의 `depends_on`은 오름차순·중복 없는 배열이어야 하며,
   `sorted(dependency_cache_keys.keys())`와 exact equality여야 한다. 누락·추가 dependency가 하나라도 있으면
   실패한다. 그 뒤 document와 그 attempt의 `inputs[]` artifact content hash 오름차순 목록, 이 검증된
   `dependency_cache_keys` mapping으로 **frozen JobSpec/StageSpec evidence에 정의된 stage cache key document**를
   그대로 구성해 canonical digest를 계산하고 `AttemptRecord.cache_key`와 대조한다. manifest는 이 재계산에
   필요한 `pipeline_id`와 `dependency_cache_keys`를 함께 기록한다.
6. document의 `runtime_version`·`schema_version`이 `AttemptRecord`의 같은 필드, 그리고
   `EnvironmentRecord/v1`에 고정한 값과 일치하는지 확인한다.

같은 `stage_spec_digest`가 여러 unit에 나타나는 것은 정상이다 — 같은 StageSpec identity라는 뜻이다.
실행을 구분하는 것은 §5.1.1의 attempt identity이지 이 digest가 아니다.
CAS document와 digest의 self-consistency만으로는 실행 provenance가 아니다. 위 `cacheable` equality와
`depends_on`↔`dependency_cache_keys` equality가 모두 성립해야 document가 실제 실행 StageSpec에 결박된다.

#### 5.1.1.2 output cardinality와 순서 (H-01)

이전 판은 unit마다 scalar `raw_output_ref` 하나만 결박했다. `AttemptRecord.outputs`는 **ordered array**이므로,
attempt가 output을 여러 개 가질 때 그중 하나만 적어도 통과했고 나머지는 검증되지 않았다.

- `output_ref_tuple`은 ordered이며 `AttemptRecord.outputs[]`와 **길이·순서·원소가 전부** 같아야 한다.
  원소 하나 누락, 추가, 순서 변경은 전부 `invalid`다.
- **measured candidate unit stage의 output cardinality는 정확히 1로 고정한다.** 각 unit stage는
  adapter-native raw output 하나만 생산하며, `len(AttemptRecord.outputs) != 1`이면 그 measurement는
  `invalid`다. 이 제한을 암묵으로 두지 않고 여기서 명시하며, 늘려야 하면 계약 변경으로 처리한다.
- 그 유일한 원소가 §5.1의 그 unit `raw_output_refs` 항목과 같아야 한다. `output_ref_tuple`이 비어 있거나
  둘 이상이면 `raw_output_refs`와의 대응이 성립하지 않으므로 실패한다.
- aggregate stage처럼 candidate 성능 측정 대상이 아닌 stage에는 이 cardinality 제한을 적용하지 않는다.

**runtime attempt-record identity는 12개 stage에서 유일하다.** 어떤 `(job_id, stage_id, attempt_id)`
삼중항 또는 `attempt_record_ref`도 서로 다른 두 candidate stage, 두 run, 두 `matrix_cell_id`에 나타날 수
없다. 한 실행을 두 measurement로 세는 것을 금지한다.

**CAS 중복 제거와 실행 재사용을 혼동하지 않는다.** 두 stage의 `output_ref_tuple` 원소나
`aggregate_normalized_output_ref`가 **같은 digest**인 것은 bytes가 같다는 뜻일 뿐이고 그 자체로 결함이
아니다 — content-addressed store의 정상 동작이다. 결함은 두 stage가 **같은 실행 attempt**를 가리키는
것이다. 따라서 판정 기준은 output digest가 아니라 위 runtime identity tuple이다.

그 결과 다음이 따라온다.

- measured candidate stage의 모든 unit attempt는 **그 measurement window 안에서 실제로 실행된
  attempt**여야 한다. cache hit로 실행을 건너뛴 unit이 하나라도 있으면 그 stage는 성능 measurement로
  쓸 수 없고 `rtf_status`·`vram_status`가 `invalid`다. cache hit 자체를 금지하는 것이 아니라, 실행하지
  않은 것을 실행 시간으로 보고하는 것을 금지한다.
- 서로 다른 end-to-end run이 같은 ASR 후보를 쓰더라도 각 run은 자기 measured ASR stage의 실행 attempt를
  따로 가진다. 두 run이 같은 attempt를 공유하면 12개 coverage가 성립하지 않는다.
- 같은 후보의 두 실행이 우연히 같은 output digest를 만들어도 attempt·job·stage·cache key identity가
  다르므로 정상이다. validator는 이 경우를 실패로 판정하지 않는다.

#### 5.1.2 `final_pipeline_output_refs`의 내용과 계보 (H-01)

이전 판은 이 tuple의 **동일성만** 요구했다. 그래서 manifest와 interruption record가 **둘 다 빈 tuple**이면
동일성 검사를 그대로 통과했고, 다른 run의 ref나 계보가 맞지 않는 ref를 넣어도 막히지 않았다. 아래로
닫는다.

모든 `end_to_end` run은 `final_pipeline_output_refs`를 **정확히 네 원소의 non-empty ordered tuple**로 가진다.

| 순서 | artifact | producer |
|---|---|---|
| 1 | `Transcript/v1` | 그 run의 measured ASR candidate stage |
| 2 | `TranslatedTranscript/v1` | 그 run의 measured MT candidate stage |
| 3 | `SubtitleDocument/v1` | 그 run의 subtitle composition stage |
| 4 | SRT export | 그 run의 SRT export stage |

- 빈 tuple, 길이가 4가 아닌 tuple, 순서가 다른 tuple은 **fail-closed**다. 동일성 검사가 통과해도 무효다.
- 각 ref는 CAS에서 실제로 읽히고 kind·media type이 그 위치의 계약과 맞아야 한다.
- 네 ref는 전부 **그 run의 `run_id`·`job_id`에 속한 attempt**가 생산해야 한다. 다른 run·다른 job이
  생산한 ref(foreign-run ref)는 digest가 같더라도 그 자리에 올 수 없다.
- **producer ancestry를 검사한다.** 2번의 producing attempt의 input tuple은 1번 ref를 포함해야 하고,
  3번은 2번을, 4번은 3번을 포함해야 한다. 한 단계라도 조상이 끊기거나 다른 문서를 가리키면
  ancestry-incompatible로 실패한다.
- 1번과 2번은 각각 그 run의 measured ASR·MT candidate stage의 `aggregate_normalized_output_ref`와
  같아야 한다. §5.1.1의 runtime identity로 그 stage가 실제 실행이었음이 확인된 경우에만 유효하다.
- `independent_asr`·`independent_mt` run은 end-to-end pipeline을 완료하지 않으므로
  `final_pipeline_output_refs`를 갖지 않는다. 이 두 run kind에서 이 field가 존재하면 실패다.

### 5.2 raw·corrected·독립 MT evidence

- adapter가 반환한 원본 bytes 또는 lossless canonical serialization을 `raw_output_ref`로 먼저 보존한다.
  normalized `Transcript/v1`·`TranslatedTranscript/v1`·`SubtitleDocument/v1`은 이를 대체하지 않고 별도 ref다.
- 독립 MT raw/normalized 결과는 task-local `BenchmarkTranslationOutput/v1`이다. 최소한 benchmark input ref,
  target language `ko`, ordered source segment ID, 각 segment의 raw target text와 candidate/config identity를 담고
  제품 `TranslatedTranscript/v1`·product lineage를 가장하지 않는다.
- 사람이 수용한 결과는 task-local `CorrectedText/v1`이다. `source | target` axis, ordered adapter-native
  `raw_output_refs`,
  evaluator에게 실제 표시한 normalized/presentation artifact ref, ordered displayed unit ID와 그에 대응하는
  accepted exact text를 담는다. 그 문서의 digest·size는 이를 가리키는 CAS ref에만 두어
  self-hash를 만들지 않으며, 원래 raw/product artifact를 덮어쓰지 않는다.

`BenchmarkTranslationOutput/v1`과 `CorrectedText/v1` validator는 입력 unit의 정확한 집합·순서·중복 없음과
raw/corrected ref의 CAS identity를 확인한다. source axis는 manifest의 해당 ASR candidate stage,
target axis는 해당 MT candidate stage의 ordered `raw_output_refs`와 exact equality여야 한다. 표시 artifact를
생산한 normalized stage의 input lineage도 그 ordered raw tuple 전체를 같은 순서로 가져야 하며 일부 raw unit을
생략하거나 다른 run·stage의 ref를 더할 수 없다. 누락 unit을 빈 문자열로 조용히 보충하거나 집계 report의
문자열만 바꾸는 것을 금지한다.

### 5.3 `CorrectionRecord/v1`

각 source/target 수정 측정은 다음을 필수로 갖는다.

- `run_id`, blind output ID, axis, `candidate_chain_hash`, ordered adapter-native `raw_output_refs`,
  evaluator에게 표시한 artifact ref, corrected output ref
- ordered clock event: 정확히 한 `start`, 0개 이상의 짝지어진 `pause`/`resume`, 정확히 한 `end`
- event마다 sequence, event kind, 같은 host의 `monotonic_ns`; `pause`에는 고정 reason code와 pause ID,
  `resume`에는 같은 pause ID
- evaluator pseudonymous ID, 정답 transcript 참조 여부, target에서 표시한 source view identity
- `effective_correction_ns = end - start - Σ(pause interval)`과 표시용 seconds

pause reason code는 `tool_failure | file_reload | operator_break | external_interruption`만 허용하고 제외 시간을
reason별로 별도 합계한다. 최초 파일 준비·모델 loading은 start 전이며 clock event에 넣지 않는다.
validator는 start가 처음, end가 마지막이고 monotonic time이 엄격히 증가하며 pause가 중첩되지 않고 모두
resume됐는지 확인한다. effective 값을 event에서 다시 계산해 stored 값과 exact integer로 비교하고, raw/corrected
ref와 manifest의 run/candidate-chain identity가 다르면 실패한다. 표시 artifact는 manifest의 normalized/benchmark
output ref와 같고, 그 producing stage의 input lineage와 correction record의 `raw_output_refs`는 manifest에 기록된
해당 candidate stage의 ordered raw tuple과 exact equality여야 한다.

### 5.4 `InterruptionRecord/v1`

controlled interruption을 배정한 네 end-to-end run에는 다음이 필수다.

- `run_id`, `matrix_cell_id`, `candidate_chain_hash`, pack/input refs와 config hashes, 중단 대상
  adapter·candidate stage·unit ID, injection point와 interruption event
- 중단 전 completed unit마다 stage ID, unit ID, cache key, attempt ID와 output artifact ref/hash
- 중단 당시 미완료 unit과 attempt ID, resume attempt ID
- resume에서 reused unit과 restarted unit, 각각의 cache key·attempt·artifact identity
- resumed candidate-stage aggregate output ref, manifest와 같은 §5.1.2의 네 원소 ordered
  `final_pipeline_output_refs`, expected unit coverage/order/duplicate 검사 결과
- 중단 전·resume 양쪽 unit의 §5.1.1 runtime identity tuple(`job_id`,
  `runtime_stage_id`(=`AttemptRecord.stage_id`), `attempt_id`, `attempt_record_ref`, `cache_key`,
  `stage_spec_digest`, `stage_spec_document_ref`, ordered `input_ref_tuple`, ordered `output_ref_tuple`)

validator는 중단 전 completed 집합과 resume reused 집합이 exact identity로 같고, 그 unit에 새 execution attempt가
없으며 bytes/hash가 불변인지 확인한다. 미완료 unit만 restarted될 수 있고 최종 coverage는 expected unit 집합과
정확히 같아야 한다. aggregate attempt의 ordered input tuple은 reused/restarted unit의 최종 output tuple과 exact
equality여야 하고, resumed aggregate output ref는 manifest의 해당 candidate stage normalized output ref와 같아야
한다. `final_pipeline_output_refs`도 manifest outputs의 동일 ordered tuple과 같아야 한다.

**네 축이 동시에 일치해야 한다 (H-01).** interruption record, runtime attempt record, manifest, 최종 출력이
서로 exact equality로 합의하지 않으면 실패다. 구체적으로:

- reused/restarted unit의 `attempt_record_ref`를 실제로 읽어 그 record의 `job_id`·`stage_id`·
  `attempt_id`·`cache_key`·`inputs[]`·`outputs[]`가 interruption record와 manifest의 같은 자리 값
  (`runtime_stage_id`는 `stage_id`에, `input_ref_tuple`·`output_ref_tuple`은 순서까지)과 일치하는지 확인하고,
  `stage_spec_digest`는 §5.1.1.1의 절차로 재계산해 대조한다. reused unit은 **중단 전과 같은 attempt record**를 가리켜야 하고 새
  execution attempt가 없어야 한다. restarted unit은 **중단 전과 다른 새 attempt record**를 가리켜야 한다.
- reused unit의 output digest가 같은 것은 정상이다(§5.1.1). 판정 기준은 attempt identity이지 digest가 아니다.
- `final_pipeline_output_refs`는 §5.1.2의 네 원소 non-empty ordered tuple이어야 한다. **빈 tuple은 manifest와
  interruption record가 둘 다 비어 있어 "일치"하더라도 fail-closed**다.
- 네 ref가 전부 그 run의 `run_id`·`job_id`에 속한 attempt의 산출물이어야 한다. foreign-run ref는 실패다.
- §5.1.2의 producer ancestry(`Transcript/v1` → `TranslatedTranscript/v1` → `SubtitleDocument/v1` → SRT)가
  attempt input tuple로 확인되지 않으면 ancestry-incompatible로 실패한다.

같은 run/config를 적고
다른 aggregate·최종 output을 가리키거나 중복·누락·dangling attempt가 있거나 report만 성공을 주장하면 실패한다.

### 5.5 집계의 fail-closed 규칙

최종 calibration report는 §5.1의 exact `matrix_cell_id` 집합을 각각 한 번만 덮는 독립 ASR 2, 독립 MT 2,
end-to-end 4개의 ordered run entry를 가지며, 각 entry는 검증된 `CalibrationRunManifest/v1` CAS ref와 그
manifest에서 읽은 `run_id`, `matrix_cell_id`를 함께 가진다. manifest ref, `run_id`, `matrix_cell_id`는 각각
유일해야 하며 중복 cell로 누락 cell을 채울 수 없다. 8개 manifest는 exact 12개
candidate-stage measurement ref를 한 번씩 소유하고 어느 ref도 run/stage 사이에 재사용하지 않는다. paired
timestamp diagnostic은 별도 ref로 둔다. report의
correction time·RTF·VRAM·resume·quality 값은 연결된 record에서 재계산하며 자유 숫자를 허용하지 않는다.
정확한 matrix coverage나 12개 stage measurement 중 하나라도 없거나, 8개 중 하나라도
schema/ref/identity/coverage 검증에 실패하거나 필요한 corrected/raw artifact가 없으면 report status는
`incomplete`이고 TASK 완료나 모델 채택 근거로 쓸 수 없다.

다음도 각각 `incomplete` 사유다.

- 12개 measured candidate stage의 §5.1.1 runtime identity tuple 중 하나라도 없거나, `attempt_record_ref`를
  읽을 수 없거나, record 값이 manifest·measurement와 다르거나, 같은 attempt identity가 두 stage에 나타남
- `runtime_stage_id`가 `AttemptRecord.stage_id`와 다르거나 그 매핑을 적지 않음
- `stage_spec_document_ref`가 없거나 읽히지 않거나, 재계산한 digest가 `stage_spec_digest`와 다르거나,
  fingerprint 투영이 `AttemptRecord.fingerprints`와 다르거나, `AttemptRecord.cacheable`이 없거나 document의
  `cacheable`과 다르거나, document의 `depends_on`이 오름차순·중복 없는 배열이 아니거나
  `sorted(dependency_cache_keys.keys())`와 다르거나, 재계산한 cache key가 `AttemptRecord.cache_key`와 다름
  (§5.1.1.1)
- `output_ref_tuple`이 `AttemptRecord.outputs[]`와 길이·순서·원소가 다르거나(누락·추가·순서 변경),
  measured candidate unit stage의 output cardinality가 1이 아님 (§5.1.1.2)
- `input_ref_tuple`이 `AttemptRecord.inputs[]`와 순서까지 같지 않음
- measured stage에 실행하지 않은 cache-hit unit이 섞임
- `end_to_end` run의 `final_pipeline_output_refs`가 비었거나 §5.1.2의 네 원소 ordered tuple이 아니거나
  foreign-run ref이거나 producer ancestry가 끊김
- interruption record·runtime record·manifest·최종 출력 네 축이 exact equality로 합의하지 않음
- materialization event의 pre-end digest와 저장된 CAS digest가 다름
- sample artifact ref를 두 measurement가 공유하거나 scope·covered window가 measurement와 맞지 않음

## 6. RTF·peak VRAM 측정 규약

### 6.1 실행 순서와 clock

`EnvironmentRecord/v1`은 닫힌 형식으로 OS product·version·build, Windows GPU driver model,
CPU·RAM, GPU UUID·model·total bytes, NVIDIA driver·CUDA·NVML, Python executable·version,
backend/runtime package·source/wheel hash, runner·sampler source commit과 clock source를 필수로 기록한다.
device-wide와 process attribution에 쓴 exact NVML function symbol, API/struct version과 field semantic도
결과 전에 고정한다. 하나라도 없으면 이 환경의 측정은 `invalid`다.

- 각 candidate 측정은 다른 candidate가 resident하지 않은 fresh worker process와 깨끗한 단일 target GPU에서
  직렬 실행한다. GPU UUID와 시작 전 compute process 목록·device baseline memory를 기록한다. unrelated GPU
  process가 있으면 그 run의 VRAM evidence는 `invalid`다.
- 순서는 `baseline → external sampler 시작 → process-cold model load → 고정 별도 warm-up input 1회 → pre-sync 완료 →
  timed-start → adapter 호출과 lazy output 완전 소비·lossless in-memory raw buffer materialization →
  unit별 digest 계산과 output-materialized event → post-compute device sync → timed-end →
  digest-bound buffer의 CAS commit과 재검증 → model unload/worker 종료 → baseline 복귀 확인`이다.
- process-cold load와 warm-up은 RTF numerator에서 제외하지만 `process_cold_load_ns`, `warmup_ns`로 따로
  기록한다. 여기서 process-cold는 fresh worker에 model/context가 resident하지 않았다는 뜻이며 OS page cache를
  강제로 비운 disk-cold를 주장하지 않는다. warm-up
  input/ref와 횟수는 후보 유형별로 결과 전에 고정하고 calibration pack 결과로 바꾸지 않는다.
- RTF clock은 Python `time.perf_counter_ns()`와 같은 host monotonic source를 쓰며 exact clock identity를
  environment record에 남긴다. CUDA backend는 timer 시작 직전과 마지막 candidate compute 및 lazy iterator
  소비가 끝난 직후에 target device synchronize를 완료한다. 각 sync event는 candidate stage/attempt ID,
  target GPU UUID, `pre | post` role, exact backend와 sync function/API, 호출 start/end monotonic ns, return/error를
  기록한다. 선택한 API가 그 backend의 target-device work와 stream을 모두 기다린다는 frozen 근거가 없거나,
  event 순서·return을 증명하지 못하면 RTF는 `invalid`다.
- timed adapter work에는 adapter-owned preprocessing, VAD/chunk/batch scheduling, model inference와 decoding을
  포함한다. generator/iterator를 반환하는 adapter는 이를 끝까지 소비하고 모든 adapter-native raw unit을 lossless
  in-memory buffer로 materialize해야 timed interval을 끝낼 수 있다. model load·warm-up, 공통
  media extraction, 사람 교정, forced alignment는 제외하고 각각 별도 interval로 기록한다.
  iterator 생성만으로 timer를 끝내거나 timed-end 뒤 inference/decoding을 유발하면 invalid다.

**timed buffer substitution을 닫는다 (H-02).** 이전 판의 `output-materialized` event는 unit 수·ordered unit
identity·**buffer byte length**만 결박했다. byte length는 내용을 결정하지 않으므로, timed-end 뒤 CAS 쓰기
구간에서 buffer를 **같은 길이의 다른 bytes**로 바꿔치기해도 unit 수·unit identity·length가 전부 그대로였고
`raw_output_refs`는 바뀐 buffer에서 계산됐다. 어떤 검사도 이를 잡지 못했다. 아래로 닫는다.

- `output-materialized` event는 **timed-end 이전에** 기록되며 unit 수, ordered unit identity, unit별 byte
  length에 더해 **unit별 content digest**와 ordered digest 전체의 `materialized_digest_tuple_hash`를 담는다.
  digest 알고리즘과 canonical 직렬화는 첫 결과 전에 freeze해 전 run에 동일하게 적용한다.
- 이 digest들은 **materialize된 바로 그 immutable buffer에서** timed interval 안에 계산한다. digest 계산을
  timed interval 밖으로 미루면 substitution 창이 다시 열리므로 허용하지 않는다. digest 계산 비용은
  `materialization_digest_ns`로 따로 기록해 RTF 해석에 쓸 수 있게 하되 timed interval에서 빼지 않는다.
- materialize된 buffer는 그 시점 이후 **immutable**이다. 같은 measurement 안에서 다시 쓰거나 교체하지 않는다.
- **CAS 쓰기는 timed interval 밖에 남을 수 있지만, 그 pre-end digest에 결박된 바로 그 buffer를 소비하고
  검증해야 한다.** CAS commit 뒤 각 `raw_output_refs` 원소의 실제 저장 digest를 다시 읽어 event의 unit별 digest와
  ordered digest tuple hash에 exact equality로 대조한다. 하나라도 다르면 그 measurement는 `invalid`이고 run은
  `completed`가 될 수 없다. 같은 길이의 교체는 digest가 달라지므로 여기서 반드시 검출된다.
- validator는 event의 ordered unit identity·digest tuple과 manifest·measurement의 ordered `raw_output_refs`가
  같은 순서로 일대일 대응하는지 확인한다. unit 수·순서가 같아도 digest가 다르면 실패다.

### 6.2 RTF denominator와 산식

- content-locked pack timebase는 정확히 `600.000`초다. 독립 ASR의 RTF와 독립 MT의 translation RTF 모두
  이 같은 source timeline을 denominator로 사용한다. 독립 MT가 text-only라는 사실과 `translation_rtf` 이름을
  명시해 audio inference RTF인 것처럼 합치지 않는다.
- `timed_inference_ns`와 `denominator_ns = 600000000000`을 원본 정수로 저장하고
  `rtf = timed_inference_ns / denominator_ns`를 계산한다. 표시값은 Decimal round-half-even 6자리이며
  validator는 원본 정수에서 재계산한다.
- controlled-interruption end-to-end run의 전체 wall time과 합성 RTF는 순위에서 제외한다. 그 run의 각
  정상 완료 stage interval과 제외 사유는 보존하되, 후보 순위 RTF는 독립 단계 정상 완료 run만 사용한다.

### 6.3 backend-neutral VRAM

- 1차 peak는 backend allocator가 아니라 target GPU UUID의 NVML `device memory.used` 원본 bytes를 persistent external
  sampler가 50 ms 주기로 관측한 device-wide absolute observed peak다. sampler implementation/source commit,
  NVML library·driver version, target GPU total bytes, monotonic sample timestamp를 모두 기록한다. exact device-memory
  query function과 v1/v2 struct·field semantic은 첫 결과 전에 freeze해 전 run에 동일하게 적용하며, v1과 v2의
  서로 다른 `used` 정의를 섞으면 전체 비교가 invalid다.
- sample stream은 매 run 새 record로 시작하며 peak를 0에서 다시 계산한다. idle baseline은 별도 필드이고
  peak에서 빼지 않는다. model load·warm-up·timed work·post-work sync 동안 sampler를 유지하므로 model residency도
  hard-gate peak에 포함한다. Windows display/driver의 정상 baseline도 device-wide 값에 포함하고, 별도 compute
  workload가 발견된 경우만 invalid로 판정한다.
- attribution 진단은 worker PID와 선언된 child-process tree 각각에 대해 frozen NVML process query function,
  API/struct version과 `usedGpuMemory` 원본 값을 사용한다. 각 측정의 `process_attribution_status`는
  `measured | unavailable_wddm | invalid` 중 하나다. `measured`이면 PID별 sample과 process-tree peak bytes가
  필수다. Windows WDDM에서 NVML이 process memory를 `NVML_VALUE_NOT_AVAILABLE`로 반환하면 status를
  `unavailable_wddm`로 하고 sentinel·driver model·reason을 기록하며 process-tree byte 값을 만들거나 0으로
  대체하지 않는다. WDDM 이외의 누락, 선언하지 않은 query/struct, 또는 다른 query error는 `invalid`다.
  process attribution이 `unavailable_wddm`여도 device-wide sample은 계속 필수이며 12 GB hard gate와 후보 간
  primary 비교는 device-wide peak를 쓴다. allocator peak는 backend-specific 보조값일 뿐 서로 다른 backend 간
  순위에 쓰지 않는다.
**NVML evidence를 측정 단위에 유일하게 결박한다 (H-02).** 이전 판은 measurement가 `sample artifact ref`
하나를 가리키게만 했고 그 sample record가 **어느 측정의 것인지** 규정하지 않았다. 그래서 end-to-end run
하나에 sampler record 하나만 만들고 그 run의 ASR measurement와 MT measurement가 **같은 unscoped record**를
참조해도 둘 다 통과했고, 다른 run의 record를 재사용하는 것도 막히지 않았다. 아래로 닫는다.

- 각 sample record는 자기 scope로 `measurement_id`, `run_id`, `matrix_cell_id`, `candidate_stage_id`,
  `adapter_role`, §5.1.1의 runtime identity tuple(ordered `job_id`·`runtime_stage_id`(=`AttemptRecord.stage_id`)·
  `attempt_id`·`attempt_record_ref`), target GPU UUID, sampler source commit, host clock identity, 그리고 covered
  monotonic window(`window_start_ns`, `window_end_ns`)를 **필수로** 담는다.
- 한 sample record는 **정확히 하나의 measurement**가 소유한다. 어떤 sample artifact ref도 두 measurement,
  두 candidate stage, 두 run에 나타날 수 없다. end-to-end run의 ASR measurement와 MT measurement는 서로 다른
  sample record를 가진다. 하나를 공유하면 두 measurement 모두 `invalid`다.
- sample record의 scope field는 그 measurement의 같은 이름 field와 exact equality여야 하고, GPU UUID는
  environment record의 target GPU UUID와 같아야 한다.
- 그 measurement의 load·warm-up·timed·post-sync를 모두 포함하는 구간이 sample record의 covered monotonic
  window **안에** 완전히 들어가야 한다. window 밖의 sample로 peak를 주장할 수 없다.
- 다른 GPU UUID, 다른 host clock, 다른 run의 sample은 값이 커도 그 measurement의 peak 근거가 아니다.

- 예정 50 ms sample 사이 실제 monotonic gap이 100 ms를 넘거나 load 전부터 post-sync까지 coverage가 없으면
  peak는 `invalid`다. controlled interruption은 중단 전과 resume 후 두 sample stream의 최대 absolute 값을
  해당 run peak로 사용하고 둘 중 하나가 invalid면 전체가 invalid다.
- pass에는 실제 RTX 4070 SUPER 12 GB device에서 OOM·driver reset 없이 완료하고
  `peak_device_used_bytes < device_total_bytes`인 증거가 필요하다. unload/worker 종료 뒤 최대 60초 동안
  target worker와 선언된 child PID가 NVML compute-process 목록에서 사라지는지 확인하고 post-unload
  device-used bytes를 기록한다. PID가 남으면 run은 `invalid`다. 안전 여유는
  `device_total_bytes - peak_device_used_bytes`로 계산하고 MiB 표시값은 `bytes / 1048576`로만 파생하되
  이 TASK에서 별도 최소 headroom을 발명하지 않는다.

### 6.4 `PerformanceMeasurement/v1`

각 required candidate stage는 task-local 닫힌 measurement record 하나를 가진다. 최소 필드는
`measurement_id`, `run_id`, `matrix_cell_id`, `candidate_stage_id`, `adapter_role`,
candidate/config/environment identity와 `candidate_chain_hash`, ordered `unit_ids`·`stage_spec_digests`·
`stage_spec_document_refs`·`attempt_ids`·`cache_keys`·`input_ref_tuples`·`output_ref_tuples`·`raw_output_refs`,
`aggregate_normalized_output_ref`, §5.1.1의 unit별 ordered runtime identity tuple
(`job_id`·`runtime_stage_id`(=`AttemptRecord.stage_id`)·`attempt_id`·`attempt_record_ref`)과 cache key
재계산 입력(`pipeline_id`·`dependency_cache_keys`),
`rtf_status`와 `vram_status`(각각
`measured | excluded_interruption | invalid`), clock·materialization·sync events, unit별 materialized content
digest와 `materialized_digest_tuple_hash`, `materialization_digest_ns`, load/warm-up/steady timed integer ns,
denominator ns와 derived RTF, sampler와 exact NVML query identity·period·coverage, baseline·device total·device peak,
`process_attribution_status`와 그 status가 `measured`일 때만 process-tree peak bytes, 이 measurement가 단독으로
소유하는 scoped sample artifact ref와 그 covered monotonic window, unload
결과와 invalid/exclusion reason이다.

validator는 runtime attempt record·manifest candidate stage와 unit/attempt/cache/input/raw/aggregate output tuple을
exact equality로 비교하고 interval·RTF·sample maximum을 원본 event/sample CAS artifact에서 재계산한다.
`attempt_record_ref`를 실제로 읽어 §5.1.1의 runtime identity tuple 전체가 일치하는지 확인한다 —
`runtime_stage_id`는 `AttemptRecord.stage_id`와, `input_ref_tuple`·`output_ref_tuple`은 `inputs[]`·`outputs[]`와
순서까지 같아야 하고, measured unit의 output cardinality는 1이어야 하며, `stage_spec_digest`는 §5.1.1.1의
절차로 재계산해 대조한다. 그 identity가 12개 stage에서 유일한지도 검사한다. 실행하지 않은 cache-hit unit이 섞이면 그 stage는 성능 measurement로 쓸 수
없다(§5.1.1). 모든 ordered raw output은 timed interval 안의 materialization event에 포함되어야 하며, 저장된
CAS digest가 그 event의 pre-end digest와 일치해야 한다(§6.1). sample artifact ref는 이 measurement가 단독
소유하고 scope field와 covered window가 §6.3의 조건을 만족해야 한다. measurement ref나 identity를
다른 stage/run에 재사용할 수 없으며 §5.1의 exact 12개 coverage가 필요하다. controlled-interruption run은 RTF만
`excluded_interruption`일 수 있고 valid device-wide VRAM evidence는 별도로 유지한다. WDDM의
`unavailable_wddm` process attribution은 그 자체로 device-wide hard gate를 무효화하지 않지만, required field,
sync, materialization, device-wide sample coverage 또는 identity가 없으면 해당 RTF 순위 또는 12 GB hard gate를
통과할 수 없다.

## 7. resume 검증

| end-to-end 조합 | controlled interruption 대상 |
|---|---|
| faster-whisper × MADLAD | faster-whisper 처리 중 |
| faster-whisper × Qwen3.5 | Qwen3.5 번역 중 |
| Qwen3-ASR × MADLAD | MADLAD 번역 중 |
| Qwen3-ASR × Qwen3.5 | Qwen3-ASR 처리 중 |

중단은 임의 GPU kernel 내부 복구가 아니라 시스템이 선언한 마지막 committed chunk·segment 경계에서 한다.
기존 runtime의 stage 완료 checkpoint보다 세밀한 nested checkpoint를 추가하지 않는다. 대신 freeze된 각
ASR chunk와 번역 segment/batch를 결정적 `StageSpec`으로 만들고, 그 산출물을 모으는 별도 aggregate stage를 둔다.
controlled interruption은 한 단위 stage가 CAS에 완료된 뒤 다음 단위 전 또는 실행 중인 미완료 단위에서 발생시켜,
resume가 완료 stage는 재사용하고 미완료 stage만 다시 시작한다. 이 표현으로 증명할 수 없으면 `job_runtime.py`를
즉석 수정하지 않고 integration finding으로 돌린다.

- 완료 chunk·segment를 다시 수행하지 않는다.
- 기존 artifact identity와 bytes를 그대로 재사용한다.
- resume 뒤 최종 산출물이 완료되고 중복·누락 segment가 없다.
- checkpoint, attempt, artifact identity와 재사용 근거가 로그에서 연결된다.
- 중단 run의 전체 wall time은 성능 순위에 쓰지 않는다.

## 8. 판정 규칙

### 8.1 hard gate

다음 중 하나라도 실패하면 기본 모델로 채택하지 않는다.

1. network 차단 상태에서 추론할 수 없음
2. license·사용·배포 조건이 프로젝트 목적과 양립하지 않거나 불명확함
3. Windows 11 + RTX 4070 SUPER 12 GB에서 OOM 또는 반복 비정상 종료
4. 목표 Windows 환경의 재현 가능한 실행 경로가 없음
5. 선언한 checkpoint 경계에서 resume하지 못함
6. resume가 완료 작업을 불필요하게 다시 수행함

### 8.2 quality veto와 순위

치명적 누락·환각은 평균 속도로 덮지 않는다. timestamp·내용과 함께 후보 제외, 추가 calibration 필요,
제한 fallback 중 하나로 판정한다. hard gate를 통과한 후보끼리는 다음 순서로 본다.

1. end-to-end source 수정시간 + target 수정시간
2. source·target 단계별 수정시간
3. RTF
4. peak VRAM과 실행 여유
5. Windows 실행 안정성

반복 측정이 없는 10분 단일 pack이므로 작은 차이로 승자를 만들지 않는다. 오류 양상과 수정시간이
명확히 갈리지 않으면 `inconclusive`로 남기고 두 adapter를 유지한다.

## 9. 수정시간 통제와 미지원 범위

- 모델명을 숨긴 익명 출력, source·target 각각 무작위 검토 순서, 모든 결과 생성 후 평가 시작을 적용한다.
- source clock은 동기 재생 가능한 익명 출력이 준비돼 처음 표시될 때 시작하고, evaluator가 수용한
  human-corrected source를 저장할 때 끝난다. target clock도 고정 source와 익명 한국어 출력이 준비돼
  처음 표시될 때 시작하고 evaluator가 수용한 한국어를 저장할 때 끝난다.
- evaluator의 실제 읽기·재생·탐색·편집 시간은 포함한다. 최초 파일 준비·모델 로딩은 start 전에 끝낸다.
  도구 failure·file reload·operator break·external interruption만 §5.3의 고정 reason code로 pause하고
  reason별 제외 시간을 기록하며 후보별로 같은 규칙을 쓴다.
- 정답 transcript를 참조했는지와 target 교정에서 사용한 source view를 기록한다.
- 단일 평가자·단일 입력·순서 학습 편향을 결과에 명시한다.
- `SubtitleDocument/v1` 생성 전에 `style_profile_id`, version과 모든 `resolved_style` 숫자·line-break policy를
  `calibration-only` profile로 한 번 고정하고 canonical JSON hash를 manifest에 넣는다. 네 조합 모두 같은
  snapshot을 쓰며 결과를 본 뒤 바꾸지 않는다. 이는 U-18 제품 기본값을 해결하거나 추천하는 결정이 아니다.
- 공식 LID accuracy와 chrF2는 이 calibration에서 `unsupported`다. 현재 정본 규칙이나 정답 bundle이
  계산 가능 조건을 충족하지 않으므로 proxy·임의 수치를 같은 이름으로 기록하지 않는다.
- 통계적으로 유의한 모델 우열, 장르·화자·음질 일반화, 장시간 production 안정성, remote 모델과의
  공정한 비용·개인정보 비교를 주장하지 않는다.

## 10. remote comparator와 network 경계

Remote Qwen-MT comparator는 TASK-031 채택 근거에서 제외한다. 후속 비교에는 업로드 가능 데이터,
network·privacy, 비용·사용량, 보존·학습 정책, latency 포함 범위를 제품 오너가 별도로 승인해야 한다.
모델 weight와 dependency를 승인된 출처에서 준비하는 network 단계와 실제 calibration run을 분리하고,
실제 run은 network 차단 상태에서 local-only를 증명한다.

## 11. 구현 경계

계약 checkpoint에서 수정 가능한 경로:

- `docs/tasks/TASK-031.md`
- `STATUS.md`
- `PLAN.md`
- `docs/DECISIONS.md`

별도 dependency/model/network gate가 닫힌 뒤 같은 TASK에서 허용할 구현 범위:

- 새 `src/media_clarity/calibration/` package와 전용 CLI
- 새 focused tests, calibration manifest·report template, `scripts/verify_task_031.py`
- task-local benchmark input, `AlignmentEvidence/v1`, `CalibrationRunManifest/v1`,
  `BenchmarkTranslationOutput/v1`, `CorrectedText/v1`, `CorrectionRecord/v1`, `InterruptionRecord/v1`,
  `EnvironmentRecord/v1`, `PerformanceMeasurement/v1` 닫힌 형식·validator
- TASK-031 전용 Make target
- 재현 가능한 dependency manifest와 lock 정보
- 필요한 최소 TASK-031 상태·결과 기록

기존 `artifact_store.py`, `job_runtime.py`, `subtitle_contracts.py`, `eval_contracts.py`, schema 계약은 우선
그대로 소비한다. 실제 integration에서 구체적 불일치가 재현되면 즉석 리팩터링하지 않고 finding으로
분리해 bounded remediation과 새 reviewer 범위를 고정한다.

## 범위 밖

- UI·editor·OCR·VLM·고급 diarization·source separation·시각 재구성
- 40~120분 장시간 안정성, packaging·installer·auto-update
- remote 추론 또는 remote comparator
- 모델 영구 채택과 기본값 변경 — calibration 결과 뒤 Pro challenge와 제품 오너 결정
- 공식 LID accuracy·chrF2 구현 또는 대체 proxy
- 사용자 미디어·모델 weight·대용량 생성 artifact의 Git commit
- unrelated contract/schema/runtime refactor와 운영 Markdown 정리

## 완료 조건

- [ ] content-locked 10분 pack과 human-corrected source가 결과 확인 전에 hash로 고정됐다.
- [ ] 네 후보와 aligner의 exact ID·revision·license·환경·설정이 실행 전에 고정됐다.
- [ ] 네 Windows hash lock이 각 `.in`의 모든 direct package canonical name·exact version을 포함하고, 누락·교체·unrelated-only mutation을 fail-closed로 거부한다.
- [ ] 네 environment evidence가 고정 Windows Python에서 기계 capture되고, resolver/direct package/GPU/CUDA/PyTorch/cuDNN manifest 값이 receipt와 readiness 시점 live re-probe에 exact equality로 결박된다. 임의 문자열·receipt 변조·environment drift는 통과하지 않는다.
- [ ] 독립 MT benchmark input, calibration-only subtitle style과 alignment chunk/stitch contract가 hash로 고정됐다.
- [ ] exact 8-cell matrix의 unique run manifest와 exact 12개 candidate-stage measurement가 raw/corrected/attempt/interruption CAS lineage를 fail-closed로 검증한다.
- [ ] 12개 measured candidate stage가 §5.1.1의 runtime identity tuple(`job_id`·`runtime_stage_id`=`AttemptRecord.stage_id`·`attempt_id`·`attempt_record_ref`·`cache_key`·ordered `input_ref_tuple`=`inputs[]`·ordered `output_ref_tuple`=`outputs[]`)로 실제 실행 attempt에 결박되고, 그 attempt identity가 전역에서 유일하며, CAS 중복 제거와 실행 재사용을 구분한다.
- [ ] §5.1.1.1의 canonical StageSpec identity document가 CAS에 저장되고, validator가 digest·`AttemptRecord.fingerprints`·`cacheable` exact equality와 `depends_on`↔`dependency_cache_keys` exact equality·cache key를 재계산해 실제 record에 잇는다. document·필드·매핑·재계산 중 하나라도 없거나 다르면 invalid다.
- [ ] measured candidate unit stage의 `output_ref_tuple`이 `AttemptRecord.outputs[]`와 길이·순서·원소까지 같고 cardinality가 정확히 1로 검증된다. 누락·추가·순서 변경은 invalid다.
- [ ] 네 end-to-end run이 §5.1.2의 네 원소 non-empty ordered `final_pipeline_output_refs`와 `Transcript/v1` → `TranslatedTranscript/v1` → `SubtitleDocument/v1` → SRT producer ancestry를 갖고, interruption record·runtime record·manifest·최종 출력이 exact equality로 합의한다.
- [ ] materialized raw buffer가 timed-end 이전에 digest로 결박되고, CAS commit이 그 digest를 소비·재검증해 same-length 교체가 검출된다.
- [ ] 각 NVML sample record가 `measurement_id`·`run_id`·`matrix_cell_id`·candidate stage·runtime attempt identity·GPU UUID·monotonic window로 유일하게 결박되고 두 measurement가 공유하지 않는다.
- [ ] 공통 600초 RTF가 lazy output의 timed materialization·exact sync event에서, external NVML peak VRAM이 frozen query의 raw sample에서 재계산된다.
- [ ] Windows driver model과 `measured | unavailable_wddm | invalid` process attribution이 정직하게 기록되고, device-wide invalid evidence는 12 GB hard gate를 통과하지 못한다.
- [ ] 독립 ASR 2회, 독립 번역 2회, end-to-end 4회가 실제로 완료됐다.
- [ ] 네 end-to-end 조합이 기존 CAS·lineage와 자막 spine 문서를 생성·검증했다.
- [ ] 네 model adapter가 각각 한 controlled interruption/resume 증거를 남겼다.
- [ ] local-only, Windows 11, RTX 4070 SUPER 12 GB, RTF와 peak VRAM 경계가 직접 측정됐다.
- [ ] 치명적 누락·환각, source/target 수정시간과 편향 통제가 결과에 기록됐다.
- [ ] LID·chrF2와 일반화·통계적 우열을 unsupported/미검증으로 정직하게 남겼다.
- [ ] code·tests·실행 artifact를 포함한 최종 coherent HEAD가 full regression을 통과했다.
- [ ] 작성자와 다른 fresh reviewer가 fixed HEAD를 Gate H로 승인했다.
- [ ] 측정 뒤 ChatGPT Pro challenge와 제품 오너 결정 전에는 기본 모델을 확정하지 않았다.

## rollback·stop condition

- contract checkpoint는 이 네 Markdown 파일 한 묶음으로 되돌릴 수 있다.
- 구현은 calibration 전용 새 package·manifest·tests를 한 rollback 단위로 유지하고 기존 artifact를 삭제하지 않는다.
- license 불명확, 12 GB/Windows 실행 불가, local-only 위반, 반복 OOM/crash, resume 재실행·중복·누락,
  pack identity drift가 발생하면 자동 채택하지 않고 해당 후보 또는 TASK를 `Blocked`로 전환한다.
- 범위를 넓히는 해결책, remote egress, 새 비용·privacy·destructive 작업이 필요하면 제품 오너 gate에서 멈춘다.

## 전환

TASK-031 결과는 모델 채택 결론이 아니라 U-22의 측정 evidence다. calibration report 뒤 ChatGPT Pro가
한 번 challenge하고, 제품 오너가 기본/fallback/추가 실험을 결정한다. 자막 10분 vertical slice가
완료되면 다음 기능 후보는 고급 자막 기능보다 먼저 최소 시각 재구성 vertical slice로 평가한다.
