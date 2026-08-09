# ARCHITECTURE.md — 아키텍처

모듈 경계와 인터페이스 계약. **구현이 아니라 계약의 정의입니다.**

마지막 갱신: 2026-08-09 (Phase 0)
상태: **제안됨 (Proposed)** — 경계 원칙은 승인, 구체 기술은 미정

> 이 문서의 코드 블록은 전부 **계약 스케치(pseudo-contract)** 입니다.
> 실행 가능한 코드가 아니며 특정 언어를 강제하지 않습니다.
> 필드 이름은 제안이며, 구현 시 조정될 수 있습니다.

---

## 1. 설계 원칙

| # | 원칙 | 구체적 의미 |
|---|---|---|
| A1 | **파이프라인 분리** | 자막 경로와 영상 재구성 경로는 서로를 호출하지 않는다 |
| A2 | **계약 우선** | 모듈은 데이터 계약으로만 만난다. 내부 구현을 서로 모른다 |
| A3 | **모델 교체 가능** | 어떤 ASR·재구성 모델도 어댑터 뒤에 있다. 코어가 모델 API에 의존하지 않는다 |
| A4 | **단계별 산출물 보존** | 중간 결과를 디스크에 남긴다. 재실행·디버깅·평가의 전제 |
| A5 | **결정론 우선** | 시드·버전·설정을 기록한다. 비결정적 요소는 명시적으로 표시한다 |
| A6 | **평가는 일급 시민** | `eval`은 부가 도구가 아니라 모듈이다 |
| A7 | **UI는 껍데기** | 모든 기능은 UI 없이 실행 가능해야 한다 |

**A3이 중요한 이유:** 지금 우리는 어떤 모델이 최선인지 모릅니다.
모델을 어댑터 뒤에 두면 나중에 측정 결과로 교체할 수 있습니다.
코어에 특정 모델 API를 박아 넣으면 그 선택이 영구적 부채가 됩니다.

---

## 2. 모듈 지도

```
                        ┌──────────────┐
                        │      ui      │  (Phase 3, 선택적 껍데기)
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │ orchestrator │  작업 그래프 · 스케줄 · 캐시 · 자원
                        └──┬────────┬──┘
                           │        │
          ┌────────────────┘        └────────────────┐
          │                                          │
   ══ 자막 경로 (Phase 1) ══             ══ 영상 재구성 경로 (Phase 2) ══
          │                                          │
   ┌──────▼──────┐                            ┌──────▼──────┐
   │   ingest    │◄───────── 공유 ───────────►│   ingest    │
   └──────┬──────┘                            └──────┬──────┘
   ┌──────▼──────┐                            ┌──────▼──────┐
   │    audio    │ VAD·잡음·분리·분절          │   restore   │ 탐지·재구성·일관성
   └──────┬──────┘                            └──────┬──────┘
   ┌──────▼──────┐                                   │
   │     asr     │ 전사·언어식별                      │
   └──────┬──────┘                                   │
   ┌──────▼──────┐                                   │
   │  subtitle   │ 정렬·분할·형식화·출력              │
   └──────┬──────┘                                   │
          │                                          │
          └──────────────┐          ┌────────────────┘
                         │          │
                    ┌────▼──────────▼────┐
                    │       storage       │  프로젝트 · 작업 · 산출물 · manifest
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐        ┌──────────┐
                    │        eval         │        │  export  │ (Phase 4, 선택)
                    └─────────────────────┘        └──────────┘
```

**두 경로가 공유하는 것은 `ingest`와 `storage`뿐입니다.** 그 외에는 서로 독립입니다.

---

## 3. 모듈별 책임과 경계

### 3.1 `ingest` — 미디어 입력

| 항목 | 내용 |
|---|---|
| 책임 | 미디어 파일 조사, 트랙 정보 추출, 오디오/프레임 접근 제공, 입력 해시 계산 |
| 하지 않는 것 | 품질 판단, 잡음 제거, 전사, 화면 수정 |
| 받는 것 | 파일 경로 |
| 주는 것 | `MediaProfile` + 정규화된 오디오/프레임 접근자 |

```
MediaProfile:
  source_path        : 경로
  content_hash       : 내용 해시 (재현성 키)
  duration_seconds   : 실수
  container          : 문자열
  audio_tracks[]     : { index, codec, sample_rate, channels, language_hint? }
  video_tracks[]     : { index, codec, width, height, fps, bit_depth? }
  has_video          : 불리언
  probe_warnings[]   : 문자열   # 깨진 인덱스, 가변 프레임레이트 등
```

> `language_hint`는 **힌트일 뿐** 신뢰하지 않습니다. 컨테이너 메타데이터는 자주 틀립니다.

---

### 3.2 `audio` — 오디오 프론트엔드

| 항목 | 내용 |
|---|---|
| 책임 | 정규화, 발화 구간 탐지(VAD), 잡음 처리, 화자/음원 분리 검토, 분절(segmentation) |
| 하지 않는 것 | 전사, 언어 판정, 자막 형식 |
| 받는 것 | `MediaProfile` + 오디오 접근자 |
| 주는 것 | `SpeechSegment[]` |

```
SpeechSegment:
  segment_id       : 문자열
  start_seconds    : 실수
  end_seconds      : 실수
  audio_ref        : 잘라낸 오디오 참조
  speech_confidence: 0..1
  overlap_flag     : 불리언        # 겹친 발화로 의심됨
  speaker_label?   : 문자열         # diarization 채택 시에만
  snr_estimate?    : 실수
  processing_chain[]: 문자열        # 어떤 처리를 거쳤는지 기록
```

**이 모듈이 어려운 입력의 1차 방어선입니다.**

- 긴 무음 → 여기서 걸러야 `asr`이 환각을 만들 기회 자체가 줄어듭니다.
- 겹친 발화 → `overlap_flag`로 표시해 하류에서 다르게 다룰 수 있게 합니다.
- 잡음 → 과도한 잡음 제거는 오히려 인식률을 떨어뜨릴 수 있습니다.
  **잡음 제거 강도는 평가로 결정할 항목입니다** (미해결 U-12).

---

### 3.3 `asr` — 음성 인식

| 항목 | 내용 |
|---|---|
| 책임 | 구간별 전사, 언어 식별, 단어/토큰 단위 타이밍, 신뢰도 산출 |
| 하지 않는 것 | 자막 줄 나누기, 형식 규칙, 파일 출력 |
| 받는 것 | `SpeechSegment[]` |
| 주는 것 | `Transcript` |

```
Transcript:
  segments[]:
    segment_id     : 문자열
    text           : 문자열
    language       : 언어 코드 (BCP-47 제안)
    language_confidence : 0..1
    tokens[]       : { text, start_seconds, end_seconds, confidence }
    is_low_confidence : 불리언
    alternatives[]?: 문자열      # n-best, 사후 재채점 여지
  model_info       : { adapter_id, version, params_hash }
```

**어댑터 경계 (A3의 핵심)**

```
AsrAdapter (인터페이스):
  capabilities() -> { languages, supports_word_timing, supports_language_id,
                      supports_batching, requires_gpu }
  transcribe(segments, options) -> Transcript
```

코어는 `AsrAdapter`만 압니다. 어떤 모델이 뒤에 있는지 모릅니다.
**다국어 전환은 두 가지 전략이 가능**하며 어느 쪽이 나은지 아직 모릅니다 (미해결 U-13).

- (a) 구간별 언어 식별 후 언어별 모델 호출
- (b) 다국어 통합 모델에 그대로 맡김

---

### 3.4 `subtitle` — 자막 구성

| 항목 | 내용 |
|---|---|
| 책임 | 시간 정렬 다듬기, 자막 단위 분할, 줄바꿈, 형식 규칙 적용, 파일 출력 |
| 하지 않는 것 | 전사 내용 변경, 오디오 접근 |
| 받는 것 | `Transcript` |
| 주는 것 | `SubtitleDocument` + 자막 파일 |

```
SubtitleDocument:
  cues[]:
    cue_id         : 문자열
    start_seconds  : 실수
    end_seconds    : 실수
    lines[]        : 문자열      # 보통 1–2줄
    language       : 언어 코드
    speaker?       : 문자열
    confidence     : 0..1
    needs_review   : 불리언       # 사람이 볼 곳을 표시
  style_profile    : { max_chars_per_line, max_lines, max_cps,
                       min_duration, max_duration, min_gap }
  provenance       : { input_hash, config_hash, generated_at, pipeline_version }
```

**`needs_review`가 제품적으로 중요합니다.** 자동 결과는 초안입니다.
어디를 봐야 하는지 알려주는 것이 "다 맞다고 우기는 것"보다 유용합니다.

---

### 3.5 `restore` — 영상 재구성 (Phase 2)

| 항목 | 내용 |
|---|---|
| 책임 | 열화 영역 탐지, 재구성 **추정**, 시간적 일관성, 인공물 검사 |
| 하지 않는 것 | 오디오·자막 관련 일체. 원본 복구 주장 (`AGENTS.md` §1) |
| 받는 것 | `MediaProfile` + 프레임 접근자 |
| 주는 것 | `ReconstructionResult` |

```
DegradedRegion:
  frame_range      : { start_frame, end_frame }
  bbox_or_mask     : 영역 표현
  degradation_kind : "blur" | "mosaic" | "low_resolution" | "compression" | "unknown"
  severity_estimate: 0..1
  detector_confidence : 0..1

ReconstructionResult:
  regions[]        : DegradedRegion
  output_ref       : 재구성된 영상 참조
  is_estimate      : 항상 true            # 상수. 절대 false가 되지 않는다
  confidence_map?  : 영역별 추정 신뢰도
  temporal_consistency_score : 실수
  artifact_flags[] : { frame_range, kind, note }
  disclaimer       : "재구성 결과는 추정치이며 원본과 다를 수 있습니다"
  model_info       : { adapter_id, version, params_hash }
```

> **`is_estimate`가 상수 true인 것은 의도된 설계입니다.**
> 이 필드가 false가 될 수 있는 조건은 존재하지 않습니다.
> 원본을 모르는 상태에서 추정이 아닌 결과는 나올 수 없습니다.

```
RestoreAdapter (인터페이스):
  capabilities() -> { handles, max_resolution, temporal_aware, requires_gpu }
  reconstruct(frames, regions, options) -> ReconstructionResult
```

---

### 3.6 `eval` — 평가

| 항목 | 내용 |
|---|---|
| 책임 | 합성 열화 생성, 지표 계산, 리포트 출력, 실행 간 비교 |
| 하지 않는 것 | 파이프라인 내부 수정, 모델 학습 |
| 받는 것 | 산출물 + 정답(있는 경우) |
| 주는 것 | `EvalReport` |

설계 상세는 [`EVALS.md`](EVALS.md)에 있습니다. 여기서는 경계만 정의합니다.

```
EvalReport:
  run_id           : 문자열
  pipeline_version : 문자열
  config_hash      : 문자열
  seed             : 정수
  dataset_id       : 문자열
  metrics          : { 지표명 -> 값 }
  per_condition[]  : { condition_id, severity, metrics }
  compared_to?     : 이전 run_id
  notes[]          : 문자열
```

**`eval`은 파이프라인을 수정할 권한이 없습니다.** 측정만 합니다.
측정자와 피측정자를 분리해야 자기충족적 결과를 피할 수 있습니다.

---

### 3.7 `orchestrator` — 실행 조율

| 항목 | 내용 |
|---|---|
| 책임 | 단계 순서, 의존성, 캐시·재개, 자원 할당, 진행 보고, 오류 격리 |
| 하지 않는 것 | 미디어 처리 자체 |

```
Job:
  job_id, project_id, pipeline ("subtitle" | "restore" | "eval")
  input_ref, config, seed
  stages[]: { stage_id, status, started_at, finished_at, artifact_refs[], error? }
  status  : "queued"|"running"|"paused"|"failed"|"completed"|"cancelled"
```

**요구사항**

- 단계 산출물은 캐시된다 → 뒷단계 실패 시 앞단계를 다시 돌리지 않는다
- 한 단계의 실패가 다른 파이프라인을 중단시키지 않는다 (A1)
- 긴 작업은 중단·재개 가능하다 (사용자 PC는 껐다 켜집니다)
- 자원 정책은 **벤더 중립 추상화** 뒤에 둔다 (미해결 U-03)

---

### 3.8 `storage` — 저장과 파일 정리

| 항목 | 내용 |
|---|---|
| 책임 | 프로젝트/작업/산출물 배치, manifest 기록, 원본 보호 |
| 하지 않는 것 | 처리, 클라우드 전송 (`export` 담당) |

**디렉터리 배치 (제안)**

```
<project_root>/
├── project.json              # 프로젝트 메타데이터
├── inputs/                   # 원본 참조 (기본: 복사하지 않고 참조 + 해시)
├── jobs/
│   └── <job_id>/
│       ├── manifest.json     # 설정·버전·시드·입력 해시
│       ├── stages/           # 단계별 중간 산출물 (A4)
│       └── logs/
├── outputs/
│   ├── subtitles/
│   └── reconstructions/      # 항상 "추정 결과"로 라벨링
└── evals/
    └── <run_id>/
```

**안전 규칙 (품질 속성 4: 안전한 기본값)**

- 원본 입력 파일은 **절대 수정하거나 덮어쓰지 않습니다.**
- 출력은 항상 새 파일로 씁니다. 같은 이름이 있으면 덮어쓰지 않고 알립니다.
- 삭제는 사용자의 명시적 행동으로만 일어납니다.

---

### 3.9 `ui` — 사용자 인터페이스 (Phase 3)

**A7: UI는 껍데기입니다.** `orchestrator`가 노출하는 것만 씁니다.
UI에만 있는 기능은 존재할 수 없습니다.

필수 요구 (프레임워크와 무관):

- 진행 상황과 남은 작업을 보여준다
- 자막을 직접 고칠 수 있다
- **원본과 추정 결과를 나란히 비교**할 수 있다
- 재구성 결과에 **추정임을 명시**한다 (`AGENTS.md` §1)
- 무엇이 왜 실패했는지 사람 말로 설명한다

프레임워크는 미정입니다 (미해결 U-02).

---

### 3.10 `export` — 내보내기 (Phase 4)

- 기본값은 **로컬**입니다. 클라우드 전송은 사용자가 켜야 합니다.
- 무엇을 보낼지 사용자가 선택합니다. 전체 미디어 자동 업로드는 없습니다.
- 대상 서비스는 미정입니다 (미해결 U-14).

---

## 4. 데이터 흐름 요약

**자막 경로 (Phase 1)**

```
파일 → MediaProfile → SpeechSegment[] → Transcript → SubtitleDocument → 자막 파일
                                                            ↓
                                                       EvalReport
```

**영상 재구성 경로 (Phase 2)**

```
파일 → MediaProfile → DegradedRegion[] → ReconstructionResult → 추정 영상 + 리포트
                                                    ↓
                                               EvalReport
```

두 흐름은 `storage`에서만 만납니다. 서로의 산출물을 입력으로 쓰지 않습니다.

---

## 5. 횡단 관심사 (Cross-cutting)

### 재현성

모든 작업은 다음을 manifest에 기록합니다.

```
input_hash · config_hash · pipeline_version · adapter versions · seed · timestamp
```

비결정적 요소(GPU 커널 비결정성 등)가 있으면 **manifest에 명시**합니다.
"재현 가능하다"는 주장은 확인된 범위에서만 합니다.

### 오류 처리

| 등급 | 의미 | 동작 |
|---|---|---|
| Recoverable | 한 구간 실패 | 표시하고 계속. `needs_review` 설정 |
| Degraded | 기능 축소 | 사용자에게 알리고 가능한 만큼 진행 |
| Fatal | 진행 불가 | 중단, 원인 설명, 부분 산출물 보존 |

**부분 결과를 조용히 버리지 않습니다.** 사용자의 계산 시간은 비용입니다.

### 로깅

무엇을 왜 그렇게 했는지 남깁니다. 사용자 미디어 내용 자체는 로그에 넣지 않습니다.

---

## 6. 이 문서에서 파생된 미해결 항목

| ID | 질문 | 영향 |
|---|---|---|
| U-12 | 잡음 제거 강도는 어디가 최적인가 | `audio` 설계 |
| U-13 | 다국어를 언어별 모델로 나눌 것인가, 통합 모델에 맡길 것인가 | `asr` 구조 |
| U-14 | 개인 클라우드 대상은 무엇인가 | `export` (Phase 4) |
| U-15 | diarization을 Phase 1에 넣을 것인가 | `audio`·`subtitle` 복잡도 |
| U-16 | 중간 산출물을 얼마나 오래 보관하는가 (디스크 비용) | `storage` |

전체 목록: [`DECISIONS.md`](DECISIONS.md)
