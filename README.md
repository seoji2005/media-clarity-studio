# media-clarity-studio
Local-first multilingual subtitle generation and AI-assisted media restoration studio.

---

## 이 저장소는 무엇인가

`media-clarity-studio`는 **품질이 나쁜 외국어 영상**을 입력받아

1. 최대한 정확한 **자막(subtitle)** 을 생성하고,
2. 흐림·모자이크·저해상도 등으로 **손상된 화면 영역을 자연스럽게 재구성(reconstruction)** 하는

로컬 우선(local-first) 미디어 처리 도구를 목표로 합니다.

현재 단계는 **Phase 0 (Foundation)** 이며, 이 저장소에는 아직 **기능 코드가 없습니다.**
지금 있는 것은 사람과 AI 에이전트(GPT Work, Claude Code 세션들)가 **같은 전제 위에서** 작업하기 위한
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
└── docs/
    ├── PRODUCT_SPEC.md    # 과제 범위 vs 상용 범위, MVP, 비목표
    ├── ARCHITECTURE.md    # 모듈 경계 + 공통 계약 + 안전 게이트
    ├── EVALS.md           # 평가 설계, 지표 계산 규약, 통계 규칙
    ├── DECISIONS.md       # ADR + 미해결 목록
    ├── tasks/
    │   ├── TASK-000.md    # 소급 기록: Phase 0 문서 기반 (닫힘)
    │   ├── TASK-001.md    # 독립 저장소·아키텍처 리뷰 (닫힘)
    │   ├── TASK-002.md    # REVIEW-001 지적 반영
    │   └── TASK-007.md    # 운영 구조 전환 (문서 전용)
    └── reviews/
        └── REVIEW-001.md  # TASK-001 리뷰 결과 (변경 요청)
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

**병합에 대하여:** 에이전트는 `main`에 직접 쓰지 않고 **어떤 PR도 병합하지 않습니다.**
검토 후 병합하는 것은 **사람 오너의 정상 권한**입니다 (ADR-0009).

---

## AI 에이전트가 할 일 (운영 구조)

전체 규칙은 [`AGENTS.md`](AGENTS.md) §3에 있습니다. 요약하면 네 가지 역할입니다.

| 역할 | 하는 일 | 저장소 커밋 |
|---|---|---|
| **GPT Work** | 전체 오케스트레이션, 작업 분해, Claude에 줄 프롬프트 작성, 결과 비교로 오너 판단 지원 | 하지 않음 |
| **Claude Code Cloud 주 세션** | Lead Developer — 핵심 설계·구현, 복잡한 디버깅, 성능 최적화 | 함 (TASK Owner) |
| **독립 Claude Code 리뷰 세션** | Independent Reviewer — 저장소·TASK·PR diff만 보고 검증 | 리뷰 문서만 (TASK Reviewer) |
| **Claude 일반 대화** | 아키텍처 자문, 기술 선택 비교, 막힌 문제의 두 번째 의견 | 하지 않음 |

- 작업 시작 전 **반드시** [`AGENTS.md`](AGENTS.md)를 읽습니다.
- 각 작업은 `docs/tasks/TASK-XXX.md` 하나에 대응하며, **수행 소유자는 하나의 세션**입니다.
- **작성자와 리뷰어는 반드시 서로 다른 Claude Code 세션입니다.** 주 세션은 자기 변경을 스스로 승인하지 않습니다.
- **Claude 사용량이 제한적이므로** 주 세션은 고난도 구현에 집중하고,
  독립 리뷰는 **중요한 PR과 핵심 알고리즘 변경에만** 사용합니다 ([`AGENTS.md`](AGENTS.md) §3.2).
- 세션끼리는 서로의 대화 기록을 볼 수 없습니다.
  **모든 인계(handoff)는 저장소 안의 파일과 PR 설명으로만 이루어집니다.**
- 완료 보고만 믿지 않고, 가능한 경우 **GitHub 상태와 diff로 확인**합니다 ([`AGENTS.md`](AGENTS.md) §3.5).

**현재 진행 상황:** TASK-001(독립 리뷰)이 완료되어 `변경 요청` 판정을 받았고
([`docs/reviews/REVIEW-001.md`](docs/reviews/REVIEW-001.md)), 그 지적 사항이 문서 전반에 반영되었습니다.
이후 TASK-007로 위 운영 구조 전환을 문서에 반영했습니다.
다음 단계는 [`STATUS.md`](STATUS.md) §4를 보십시오.
