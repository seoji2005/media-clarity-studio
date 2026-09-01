# media-clarity-studio
Local-first multilingual subtitle generation and AI-assisted media restoration studio.

---

## 이 저장소는 무엇인가

`media-clarity-studio`는 **품질이 나쁜 외국어 영상**을 입력받아

1. 최대한 정확한 **자막(subtitle)** 을 생성하고,
2. 흐림·모자이크·저해상도 등으로 **손상된 화면 영역을 자연스럽게 재구성(reconstruction)** 하는

로컬 우선(local-first) 미디어 처리 도구를 목표로 합니다.

현재 단계는 **Phase 1a**입니다. 합성 미디어 plumbing, 평가 계약, content-addressed artifact store와
재개 가능한 local synchronous stage runtime까지 구현·병합됐습니다. 실제 ASR·번역·화자분리·정렬,
OCR/VLM, 시각 재구성과 제품 UI는 아직 본격 구현 전입니다. 현재 상태의 정본은
[`STATUS.md`](STATUS.md)입니다.

> **용어 원칙 (반드시 준수)**
> AI 기반 deblur / demosaic / restoration 결과는 항상 **"재구성(reconstruction)" 또는 "추정(estimation)"** 으로
> 기술합니다. 원본을 **복원했다 / 되살렸다 / 원본과 같다** 라고 표현하지 않습니다.
> 알 수 없는 원본을 정확히 되찾는 것은 원리적으로 불가능하며, 산출물은 **그럴듯한 추정치**입니다.
> 이 원칙은 코드 주석, UI 문구, 커밋 메시지, PR 설명, 로그 메시지 전부에 적용됩니다.

---

## 배경

- 이 프로젝트는 **대학 과제**에서 출발했습니다.
- 입력 영상은 **의도적으로 어렵게** 만들어져 있습니다.
  - 겹치는 발화(overlapping speech)
  - 크거나 불규칙한 잡음
  - 긴 무음 구간
  - 한 영상 안에서의 다국어 전환(code-switching)
  - 낮은 품질의 오디오·비디오
  - 부분적인 blur / mosaic 영역
  - 의도적으로 낮춘 해상도
- **채점용 원본(hidden reference)은 채점자만 보유**합니다.
  따라서 **채점 피드백으로부터 직접 학습하거나 튜닝할 수 없습니다.**
  → 이 제약이 평가 전략 전체를 규정합니다. 자세한 내용은 [`docs/EVALS.md`](docs/EVALS.md).
- 장기적으로는 크리에이터가 **비용을 지불하고 쓸 만한 로컬 상용 제품**으로 발전할 수 있습니다.
  다만 상용화는 **Phase 4** 이후의 이야기이며, 지금 그것을 전제로 설계를 고정하지 않습니다.

### 과제 범위와 상용 제품 범위는 다릅니다

| | 대학 과제 (고정된 요구사항) | 상용 제품 (우리가 정함) |
|---|---|---|
| 자막 | **필수** | Phase 1 |
| 시각 재구성 | **필수 — 생략 불가** | Phase 2 |
| 배점 비중 | **모름 (U-24)** | 해당 없음 |

> **`PLAN.md`의 Phase 번호는 착수 순서이지 중요도 순위가 아닙니다.**
> "Phase 2니까 급하면 버려도 된다"는 해석은 틀렸습니다. 과제는 두 산출물을 모두 요구합니다.
> 일정 부족으로 범위를 줄여야 한다면 **사람 제품 오너가 결정**합니다.
> 자세한 구분은 [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) §2.

---

## 문서 지도

| 파일 | 목적 | 주 독자 |
|---|---|---|
| [`AGENTS.md`](AGENTS.md) | **모든 에이전트/사람이 따르는 공용 규칙의 단일 출처(authoritative)** | 전원 |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 전용 짧은 진입점 | Claude |
| [`PLAN.md`](PLAN.md) | 단계별(Phase) 제품 전략과 로드맵 | 전원 |
| [`STATUS.md`](STATUS.md) | 지금 무엇이 끝났고 누가 무엇을 소유하는가 | 전원 |
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | MVP 목표·비목표·사용자 흐름·제품 경계 | 전원 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 모듈 경계와 인터페이스 계약 | 구현 담당 |
| [`docs/EVALS.md`](docs/EVALS.md) | 자막/영상 재구성 평가 설계, 합성 열화 전략 | 구현·리뷰 담당 |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 결정 기록 — **제안됨 / 승인됨 / 미해결** 로 명시 | 전원 |
| [`docs/tasks/`](docs/tasks/) | 작업 단위 명세 (TASK-000, TASK-001 …) | 담당 세션 |
| [`docs/reviews/`](docs/reviews/) | 독립 리뷰 기록 (REVIEW-001 …) | 전원 |

**에이전트 읽기 순서:** `AGENTS.md`가 **항상 첫 번째**입니다. 전체 순서는 [`AGENTS.md`](AGENTS.md) §0.2를 따르십시오.

**새 Work에서 이어가기:** `Use $media-clarity-orchestrator. Continue seoji2005/media-clarity-studio from live repository and PR facts.`
나머지 복원·Pro·서브에이전트 규칙은 [`AGENTS.md`](AGENTS.md) §0.2·§3의 정본을 따릅니다.

**사람이 처음 볼 때 추천 순서:** `README.md`(이 파일) → [`AGENTS.md`](AGENTS.md) → [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) §2 → [`PLAN.md`](PLAN.md) → [`STATUS.md`](STATUS.md)

---

## 지금 저장소 상태

```
media-clarity-studio/
├── README.md              # 이 파일
├── AGENTS.md              # 공용 규칙 (authoritative, 항상 먼저 읽음)
├── CLAUDE.md              # Claude 전용 진입점
├── PLAN.md                # 단계별 로드맵
├── STATUS.md              # 현재 상태 / 소유권 보드
├── Makefile               # 공용 검증 진입점
├── schemas/               # 실행 가능한 공통·평가·job 계약
├── src/media_clarity/     # 합성 slice, 평가 validator, artifact store, stage runtime
├── tests/                 # 계약·mutation·runtime 테스트와 fixture
├── scripts/               # smoke·검증 스크립트
└── docs/
    ├── PRODUCT_SPEC.md    # 과제 범위 vs 상용 범위, MVP, 비목표
    ├── ARCHITECTURE.md    # 모듈 경계 + 공통 계약 + 안전 게이트
    ├── EVALS.md           # 평가 설계, 지표 계산 규약, 통계 규칙
    ├── DECISIONS.md       # ADR + 미해결 목록
    ├── tasks/             # TASK 계약과 구현 기록
    └── reviews/           # 고정 HEAD 독립 검토 기록
```

- 소스 코드: **있음** — 합성 media slice, 평가 계약 validator, CAS, cache/checkpoint/resume runtime
- 의존성 매니페스트(`requirements.txt`, `package.json`, `pyproject.toml` 등): **없음**
- 모델 가중치 / 다운로드 스크립트: **없음**
- CI 설정: **없음**
- 비밀정보(secret) / API 키 / `.env`: **없음**

현재 Python 코드는 표준 라이브러리를 사용하고 media smoke는 FFmpeg/ffprobe를 사용합니다.
실제 모델·외부 corpus·추가 의존성은 각 gate와 제품 오너 승인 전에는 반입하지 않습니다.

---

## 아직 정해지지 않은 것 (의도적으로 미정)

다음 항목들은 **요구사항이 확정되기 전에 고정하지 않습니다.**

- ASR / 화자분리(diarization) / 음원분리(source separation) **모델 및 프레임워크**
- 영상 재구성(deblur, demosaic, super-resolution) **모델 계열**
- 데스크톱 UI 프레임워크
- 대상 운영체제 및 배포 형식
- GPU 벤더 및 가속 백엔드 (NVIDIA/AMD/Apple 중 무엇도 전제하지 않음)
- 가격·수익 모델

> **단, 모델·데이터의 라이선스와 재배포 조건은 미루지 않습니다.**
> 모델 후보를 고르는 시점에 **선정 기준의 일부**로 확인합니다 (ADR-0019).
> 나중에 알게 되면 파이프라인을 다시 만들어야 하기 때문입니다.

전체 목록과 판단 근거는 [`docs/DECISIONS.md`](docs/DECISIONS.md)의 **미해결(Unresolved)** 절에 있습니다.
모르는 것은 문서에 "모른다"고 적는 것이 이 프로젝트의 규칙입니다. 추측으로 채우지 않습니다.

---

## 사람(제품 오너)이 할 일

개발 경험이 많지 않아도 진행할 수 있도록, 사람이 판단해야 하는 지점만 문서에 모아두었습니다.

1. [`STATUS.md`](STATUS.md) §5의 **차단 항목**에 답하기
   (예: "정답 자막이 원어인가 번역인가", "제출 기한은 언제인가")
2. 에이전트가 조사해 온 **비교표를 보고 고르기** (예: seed 코퍼스 후보 — 조사는 에이전트가 합니다)
3. 각 에이전트가 올린 **Pull Request를 검토하고 병합 여부 결정**

> **조사는 사람의 몫이 아닙니다.** 후보를 찾고 라이선스를 정리하고 장단점을 비교하는 일은
> 에이전트가 합니다. 오너에게는 **결정**만 요청합니다 (ADR-0024).

**병합에 대하여:** 에이전트는 `main`에 직접 쓰지 않습니다. 병합을 승인하는 주체는 사람 오너뿐이며,
Lean Root는 오너가 지정한 PR·HEAD·reviewed base가 그대로일 때만 기계적으로 일반 merge할 수 있습니다
([`AGENTS.md`](AGENTS.md) R1 / §4.1).

---

## AI 에이전트가 할 일 (운영 구조)

전체 역할·Claude escalation·작성/검토 분리·병합 규칙은 [`AGENTS.md`](AGENTS.md) §3~§4가
유일한 정본입니다. GPT/Codex가 기본 실행 자원이고 Claude는 기록된 폐쇄형 trigger에만 사용합니다.
현재 작업·Owner·Reviewer·다음 허용 행동은 [`STATUS.md`](STATUS.md), 작업별 범위와 합격 조건은
`docs/tasks/TASK-XXX.md`를 봅니다. 이 README는 운영 규칙을 별도로 재정의하지 않습니다.

**현재 진행 상황과 다음 허용 행동:** 움직이는 상태를 이 파일에 복제하지 않습니다.
정본인 [`STATUS.md`](STATUS.md)를 보십시오.
