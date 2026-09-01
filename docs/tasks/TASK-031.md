# TASK-031 — U-22 A-min 로컬 자막 calibration vertical slice

| 항목 | 값 |
|---|---|
| **ID** | TASK-031 |
| **결정자** | 사람 제품 오너 (2026-09-01, U-22 A-min 확정) |
| **Owner / Author** | Lean Root Author |
| **Reviewer** | 작성자와 다른 fresh GPT/Codex 세션 — 최종 fixed-HEAD Gate H 독립 검토 |
| **Phase** | Phase 1a — 첫 실제 자막 vertical slice와 calibration |
| **Gate** | H — 외부 모델·dependency, 12 GB GPU, Windows, cache/resume와 품질 판정 |
| **Status** | `In review` — H-01·H-02 제한 수정 완료, 새 fixed-HEAD 재검토 대기; 실제 반입·실행 금지 |
| **기준 main** | `356b964505c3d852e9a264d79da12f15e5e707e0` (PR #49 merge commit) |

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
| Source | live `main@356b964505c3d852e9a264d79da12f15e5e707e0` |
| Active TASK | TASK-031 / `In review` |
| Gate | H |
| Author / Reviewer | Lean Root Author / fresh GPT·Codex session |
| Approved scope | U-22 A-min 계약 기록, 실행 준비, 실제 10분 로컬 calibration과 보고 |
| PR / branch | #50 Draft / `lean-root/task-031-a-min-calibration` |
| Current checkpoint | 이전 fixed HEAD `9578de2…`의 H-01·H-02만 계약에 반영, 새 fixed-HEAD 재검토 인계 |
| Blocker | dependency manifest, 모델 weight 다운로드, 외부 network 사용은 별도 owner gate 전 금지 |
| Next allowed action | PR #50 live base·새 HEAD를 고정한 H-01·H-02와 prohibited drift 제한 재검토 |
| Forbidden now | 모델/weight 다운로드, dependency 설치·manifest 추가, 원격 추론, 사용자 미디어 commit, merge, 자기 승인 |

이 파일은 자신을 포함하는 commit SHA를 내장하지 않는다. reviewer는 PR #50의 live HEAD와 base를 조회해
고정하고, PR 본문의 compact handoff와 repository tree를 대조한다.

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
| outputs | candidate stage마다 ordered adapter-native `raw_output_refs`, normalized product 또는 benchmark output refs, axis별 accepted corrected output·correction record refs, alignment evidence ref가 필요한 run이면 그 ref |
| measurements | stage별 `PerformanceMeasurement/v1` refs와 quality event refs; 숫자를 manifest에 자유롭게 재기입하지 않음 |
| recovery | stage ID·unit ID·cache key·attempt record·artifact refs와, 배정된 end-to-end run의 `InterruptionRecord/v1` ref |
| config | pack hash, candidate config hash, calibration-only style hash, chunk/stitch hash, pipeline source commit |

`candidate_chain_hash`는 single candidate도 포함해 ordered adapter identity/config record의 canonical hash다.
candidate/config identity는 해당 `StageSpec` fingerprint와 raw output provenance에 있는 값과 정확히 같아야 한다.
`completed` manifest는 필요한 모든 ref가 존재·검증되고 raw output과 corrected output이 별도 CAS object이며,
correction·measurement·interruption record의 `run_id`와 config hash가 manifest와 같은 경우에만 유효하다.
독립 ASR은 source correction 1개, 독립 MT는 target correction 1개, end-to-end는 source·target correction을
각각 요구한다. end-to-end의 ASR·MT raw output을 하나의 최종 문자열로 접어 잃는 것을 금지한다.

### 5.2 raw·corrected·독립 MT evidence

- adapter가 반환한 원본 bytes 또는 lossless canonical serialization을 `raw_output_ref`로 먼저 보존한다.
  normalized `Transcript/v1`·`TranslatedTranscript/v1`·`SubtitleDocument/v1`은 이를 대체하지 않고 별도 ref다.
- 독립 MT raw/normalized 결과는 task-local `BenchmarkTranslationOutput/v1`이다. 최소한 benchmark input ref,
  target language `ko`, ordered source segment ID, 각 segment의 raw target text와 candidate/config identity를 담고
  제품 `TranslatedTranscript/v1`·product lineage를 가장하지 않는다.
- 사람이 수용한 결과는 task-local `CorrectedText/v1`이다. `source | target` axis, adapter-native raw output ref,
  evaluator에게 실제 표시한 normalized/presentation artifact ref, ordered displayed unit ID와 그에 대응하는
  accepted exact text를 담는다. 그 문서의 digest·size는 이를 가리키는 CAS ref에만 두어
  self-hash를 만들지 않으며, 원래 raw/product artifact를 덮어쓰지 않는다.

`BenchmarkTranslationOutput/v1`과 `CorrectedText/v1` validator는 입력 unit의 정확한 집합·순서·중복 없음과
raw/corrected ref의 CAS identity를 확인한다. 누락 unit을 빈 문자열로 조용히 보충하거나 집계 report의 문자열만
바꾸는 것을 금지한다.

### 5.3 `CorrectionRecord/v1`

각 source/target 수정 측정은 다음을 필수로 갖는다.

- `run_id`, blind output ID, axis, `candidate_chain_hash`, adapter-native raw output ref,
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
output ref와 같고, 그 producing stage의 input lineage가 같은 raw output ref를 포함해야 한다.

### 5.4 `InterruptionRecord/v1`

controlled interruption을 배정한 네 end-to-end run에는 다음이 필수다.

- `run_id`, `candidate_chain_hash`, 중단 대상 adapter·stage·unit ID, injection point와 interruption event
- 중단 전 completed unit마다 stage ID, unit ID, cache key, attempt ID와 output artifact ref/hash
- 중단 당시 미완료 unit과 attempt ID, resume attempt ID
- resume에서 reused unit과 restarted unit, 각각의 cache key·attempt·artifact identity
- 최종 aggregate output ref와 expected unit coverage/order/duplicate 검사 결과

validator는 중단 전 completed 집합과 resume reused 집합이 exact identity로 같고, 그 unit에 새 execution attempt가
없으며 bytes/hash가 불변인지 확인한다. 미완료 unit만 restarted될 수 있고 최종 coverage는 expected unit 집합과
정확히 같아야 한다. 중복·누락·dangling attempt가 있거나 report만 성공을 주장하면 실패한다.

### 5.5 집계의 fail-closed 규칙

최종 calibration report는 정확히 독립 ASR 2, 독립 MT 2, end-to-end 4개의 검증된
`CalibrationRunManifest/v1` CAS ref를 가진다. paired timestamp diagnostic은 별도 ref로 둔다. report의
correction time·RTF·VRAM·resume·quality 값은 연결된 record에서 재계산하며 자유 숫자를 허용하지 않는다.
8개 중 하나라도 schema/ref/identity/coverage 검증에 실패하거나 필요한 corrected/raw artifact가 없으면
report status는 `incomplete`이고 TASK 완료나 모델 채택 근거로 쓸 수 없다.

## 6. RTF·peak VRAM 측정 규약

### 6.1 실행 순서와 clock

`EnvironmentRecord/v1`은 닫힌 형식으로 OS product·version·build, CPU·RAM, GPU UUID·model·total bytes,
NVIDIA driver·CUDA·NVML, Python executable·version, backend/runtime package·source/wheel hash,
runner·sampler source commit과 clock source를 필수로 기록한다. 하나라도 없으면 이 환경의 측정은 `invalid`다.

- 각 candidate 측정은 다른 candidate가 resident하지 않은 fresh worker process와 깨끗한 단일 target GPU에서
  직렬 실행한다. GPU UUID와 시작 전 compute process 목록·device baseline memory를 기록한다. unrelated GPU
  process가 있으면 그 run의 VRAM evidence는 `invalid`다.
- 순서는 `baseline → external sampler 시작 → process-cold model load → 고정 별도 warm-up input 1회 → CUDA sync →
  timed adapter work → CUDA sync → raw output CAS commit → model unload/worker 종료 → baseline 복귀 확인`이다.
- process-cold load와 warm-up은 RTF numerator에서 제외하지만 `process_cold_load_ns`, `warmup_ns`로 따로
  기록한다. 여기서 process-cold는 fresh worker에 model/context가 resident하지 않았다는 뜻이며 OS page cache를
  강제로 비운 disk-cold를 주장하지 않는다. warm-up
  input/ref와 횟수는 후보 유형별로 결과 전에 고정하고 calibration pack 결과로 바꾸지 않는다.
- RTF clock은 Python `time.perf_counter_ns()`와 같은 host monotonic source를 쓰며 exact clock identity를
  environment record에 남긴다. CUDA backend는 timer 시작 직전과 마지막 candidate compute 직후에 device
  synchronize를 완료한다. sync를 제공하지 못하거나 그 호출 증거가 없으면 RTF는 `invalid`다.
- timed adapter work에는 adapter-owned preprocessing, VAD/chunk/batch scheduling, model inference와 decoding을
  포함한다. model load·warm-up, 공통 media extraction, 사람 교정, forced alignment, CAS serialization은 제외하고
  각각 별도 interval로 기록한다.

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
  NVML library·driver version, target GPU total bytes, monotonic sample timestamp를 모두 기록한다.
- sample stream은 매 run 새 record로 시작하며 peak를 0에서 다시 계산한다. idle baseline은 별도 필드이고
  peak에서 빼지 않는다. model load·warm-up·timed work·post-work sync 동안 sampler를 유지하므로 model residency도
  hard-gate peak에 포함한다. Windows display/driver의 정상 baseline도 device-wide 값에 포함하고, 별도 compute
  workload가 발견된 경우만 invalid로 판정한다.
- attribution 진단으로 worker PID와 선언된 child-process tree의 NVML process memory 합을 같이 기록하지만,
  12 GB hard gate와 후보 간 primary 비교는 device-wide peak를 쓴다. allocator peak는 backend-specific
  보조값일 뿐 서로 다른 backend 간 순위에 쓰지 않는다.
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

모든 논리 run은 task-local 닫힌 measurement record를 가진다. 최소 필드는 `run_id`, candidate/config/environment
identity와 `candidate_chain_hash`, `rtf_status`와 `vram_status`(각각 `measured | excluded_interruption | invalid`), clock·sync events,
load/warm-up/steady timed integer ns, denominator ns와 derived RTF, sampler identity·period·coverage,
baseline·device total·device peak·process-tree peak bytes, sample artifact ref, unload 결과와 invalid/exclusion reason이다.
validator는 interval·RTF·sample maximum을 원본 event/sample CAS artifact에서 재계산한다. controlled-interruption
run은 RTF만 `excluded_interruption`일 수 있고 valid VRAM evidence는 별도로 유지한다. required field, sync,
sample coverage 또는 identity가 없으면 해당 RTF 순위 또는 12 GB hard gate를 통과할 수 없다.

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
- [ ] 독립 MT benchmark input, calibration-only subtitle style과 alignment chunk/stitch contract가 hash로 고정됐다.
- [ ] 정확히 8개 run manifest가 raw/corrected/measurement/attempt/interruption CAS lineage를 fail-closed로 검증한다.
- [ ] 공통 600초 RTF와 external NVML peak VRAM 규약이 raw event/sample에서 재계산되고 invalid evidence가 hard gate를 통과하지 못한다.
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
