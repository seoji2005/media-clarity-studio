# media-clarity-studio
Local-first multilingual subtitle generation and AI-assisted media restoration studio.

---

## 이 저장소는 무엇인가

`media-clarity-studio`는 **품질이 나쁜 외국어 영상**을 입력받아

1. 최대한 정확한 **자막(subtitle)** 을 생성하고,
2. 흐림·모자이크·저해상도 등으로 **손상된 화면 영역을 자연스럽게 재구성(reconstruction)** 하는

로컬 우선(local-first) 미디어 처리 도구를 목표로 합니다.

현재 단계는 **Phase 0 (Foundation)** 이며, 이 저장소에는 아직 **기능 코드가 없습니다.**
지금 있는 것은 사람과 AI 에이전트(Claude, Codex)가 **같은 전제 위에서** 작업하기 위한
설계·평가·협업 문서뿐입니다. 문서 없이 코드를 먼저 쓰지 않는 것이 이 프로젝트의 의도된 순서입니다.

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

---

## 문서 지도

| 파일 | 목적 | 주 독자 |
|---|---|---|
| [`AGENTS.md`](AGENTS.md) | **모든 에이전트/사람이 따르는 공용 규칙의 단일 출처(authoritative)** | Claude, Codex, 사람 |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 전용 짧은 진입점 | Claude |
| [`PLAN.md`](PLAN.md) | 단계별(Phase) 제품 전략과 로드맵 | 전원 |
| [`STATUS.md`](STATUS.md) | 지금 무엇이 끝났고 누가 무엇을 소유하는가 | 전원 |
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | MVP 목표·비목표·사용자 흐름·제품 경계 | 전원 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 모듈 경계와 인터페이스 계약 | 구현 담당 |
| [`docs/EVALS.md`](docs/EVALS.md) | 자막/영상 재구성 평가 설계, 합성 열화 전략 | 구현·리뷰 담당 |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 결정 기록 — **제안됨 / 승인됨 / 미해결** 로 명시 | 전원 |
| [`docs/tasks/`](docs/tasks/) | 작업 단위 명세 (TASK-001 …) | 담당 에이전트 |

**읽는 순서 추천:** `README.md` → `PLAN.md` → `docs/PRODUCT_SPEC.md` → `docs/ARCHITECTURE.md` → `docs/EVALS.md` → `AGENTS.md`

---

## 지금 저장소 상태

```
media-clarity-studio/
├── README.md              # 이 파일
├── AGENTS.md              # 공용 규칙 (authoritative)
├── CLAUDE.md              # Claude 전용 진입점
├── PLAN.md                # 단계별 로드맵
├── STATUS.md              # 현재 상태 / 소유권 보드
└── docs/
    ├── PRODUCT_SPEC.md
    ├── ARCHITECTURE.md
    ├── EVALS.md
    ├── DECISIONS.md
    └── tasks/
        └── TASK-001.md    # 다음 작업: Codex의 독립 저장소·아키텍처 리뷰
```

- 소스 코드: **없음**
- 의존성 매니페스트(`requirements.txt`, `package.json`, `pyproject.toml` 등): **없음**
- 모델 가중치 / 다운로드 스크립트: **없음**
- CI 설정: **없음**
- 비밀정보(secret) / API 키 / `.env`: **없음**

이는 의도된 상태입니다. Phase 0에서는 아무것도 설치하거나 고정하지 않습니다.

---

## 아직 정해지지 않은 것 (의도적으로 미정)

다음 항목들은 **요구사항이 확정되기 전에 고정하지 않습니다.**

- ASR / 화자분리(diarization) / 음원분리(source separation) **모델 및 프레임워크**
- 영상 재구성(deblur, demosaic, super-resolution) **모델 계열**
- 데스크톱 UI 프레임워크
- 대상 운영체제 및 배포 형식
- GPU 벤더 및 가속 백엔드 (NVIDIA/AMD/Apple 중 무엇도 전제하지 않음)
- 라이선스 및 수익 모델

전체 목록과 판단 근거는 [`docs/DECISIONS.md`](docs/DECISIONS.md)의 **미해결(Unresolved)** 절에 있습니다.
모르는 것은 문서에 "모른다"고 적는 것이 이 프로젝트의 규칙입니다. 추측으로 채우지 않습니다.

---

## 사람(제품 오너)이 할 일

개발 경험이 많지 않아도 진행할 수 있도록, 사람이 판단해야 하는 지점만 문서에 모아두었습니다.

1. [`docs/DECISIONS.md`](docs/DECISIONS.md)의 **미해결** 항목 중 답할 수 있는 것에 답하기
   (예: "내 PC의 GPU는 무엇인가", "과제 제출 기한은 언제인가")
2. [`STATUS.md`](STATUS.md)에서 현재 진행 상황 확인
3. 각 에이전트가 올린 **Pull Request를 검토하고 병합 여부 결정**

에이전트는 `main`에 직접 쓰지 않습니다. 항상 리뷰 가능한 PR로 제안합니다.

---

## 에이전트(Claude / Codex)가 할 일

- 작업 시작 전 **반드시** [`AGENTS.md`](AGENTS.md)를 읽습니다.
- 각 작업은 `docs/tasks/TASK-XXX.md` 하나에 대응하며, **구현 소유자는 한 명(하나의 에이전트)** 입니다.
- 다른 에이전트는 **리뷰어**로 참여합니다. 소유자와 리뷰어는 같을 수 없습니다.
- 에이전트끼리는 서로의 대화 기록을 볼 수 없습니다.
  **모든 인계(handoff)는 저장소 안의 파일과 PR 설명으로만 이루어집니다.**

다음 작업은 [`docs/tasks/TASK-001.md`](docs/tasks/TASK-001.md) — **Codex**가 수행하는 독립 저장소·아키텍처 리뷰입니다.
