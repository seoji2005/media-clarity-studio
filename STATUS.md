# STATUS.md — 현재 상태

**"지금 무엇이 되어 있고, 누가 무엇을 들고 있는가."**
새 세션을 시작하는 에이전트는 [`AGENTS.md`](AGENTS.md) 다음으로 이 파일을 봅니다 (`AGENTS.md` §0.2).

마지막 갱신: 2026-08-29 (TASK-028 최종 승인·PR #36 병합 상태 정합화)
현재 단계: **Phase 1a** — TASK-028 완료, 다음 기능 계약은 제품 오너 승인 대기

---

## 1. 한눈에 보기

| 항목 | 상태 |
|---|---|
| 현재 Phase | **Phase 1a** (Phase 0·계획 기준선 완료, 합성 plumbing slice 병합됨) |
| Phase 0 | **완료 — `main`에 병합됨** (PR #1, 병합 SHA `d11b2450d324ac7f509741acc1ac591313876d30`) |
| 기능 코드 | **있음** — TASK-022 CLI: local input → probe → SRT → soft-sub → verify → local staging export |
| 런타임 / 의존성 | Python 3.12+ 표준 라이브러리와 FFmpeg/ffprobe. Python package 의존성·모델·CI·비밀정보 없음 |
| 병합된 PR | **#1·#5·#16·#18·#19·#21·#22·#23·#24·#25·#28·#33·#34·#36** — 각 merge commit은 §3에 기록; 현재 HEAD는 GitHub에서 조회 |
| 열린 PR | **#6~#10·#12·#14·#15·#17·#29~#32·#41** — #41은 `REVIEW-022` 기록을 담은 Draft이며 구현 PR이 아님 |
| 미병합 종료 | **#2·#3·#4·#11** — #11은 TASK-024로 대체, branch·원문 보존 |
| 운영 구조 | **TASK-027 결정** — 코드는 Claude Code, 비코드·검증·리뷰·승인 후 통합은 Lean Root (`AGENTS.md` §3, ADR-0028) |
| 현재 작업 | **상태 정합성** — TASK-028 최종 승인 기록을 보존하고 병합 뒤 상태를 문서에 반영. 새 기능 구현은 시작하지 않음 |
| U-31 | **답변됨 (2026-08-22)** — 번역 대상 언어 **한국어(`ko`)** |
| 다음 실행 의존성 | **제품 오너가 다음 기능 TASK 계약을 승인** → Claude Code 구현 → Lean Root 고정 HEAD 검토 → 제품 오너 병합 판단 |
| U-08 | **답변됨 (2026-08-09)** — **채점 정답은 번역 자막** |
| U-11 | **부분 답변됨 (2026-08-09)** — **약 2개월·품질 우선.** 정확한 제출 날짜는 **미확정** |
| 차단 요인 | **다음 기능 범위와 의존성·모델 가중치 반입 gate가 미승인.** U-16 보관 정책은 미정이므로 자동 삭제·GC를 범위 밖에 두며, 다른 U-XX도 임의 확정하지 않음 |

---

## 2. 작업 보드

### 2.1 완료된 역사 기록 (닫힘 — 미래 배정의 근거가 아님)

아래 두 행은 **이미 끝난 작업의 사실 기록**입니다. 당시 운영 구조에서 실제로 그렇게 수행되었습니다.
현재 운영 구조(`AGENTS.md` §3)는 다르며, 이 기록을 근거로 새 배정을 하지 않습니다.

| TASK | 제목 | Owner (당시) | Reviewer (당시) | Phase | Status |
|---|---|---|---|---|---|
| [TASK-000](docs/tasks/TASK-000.md) | Phase 0 문서 기반 구축 (소급 기록) | Claude | Codex | 0 | **Done** |
| [TASK-001](docs/tasks/TASK-001.md) | 저장소·아키텍처 독립 리뷰 | Codex | Claude | 0 | **Done** (판정: 변경 요청) |

### 2.2 Phase 0 — **완료 (PR #1로 `main`에 병합됨)**

아래 TASK는 전부 **PR #1에 포함되어 병합**되었습니다. 더 이상 `In review`가 아닙니다.
병합 SHA: **`d11b2450d324ac7f509741acc1ac591313876d30`**

| TASK | 제목 | Owner | Reviewer | Phase | Status |
|---|---|---|---|---|---|
| [TASK-002](docs/tasks/TASK-002.md) | REVIEW-001 지적 반영 | Claude Code 주 세션 | 독립 Claude Code 리뷰 세션 (REVIEW-002) | 0 | **Done** (PR #1 병합됨) |
| [TASK-007](docs/tasks/TASK-007.md) | 운영 구조 전환 (문서 전용) | Claude Code 주 세션 | 독립 Claude Code 리뷰 세션 (REVIEW-002) | 0 | **Done** (PR #1 병합됨) |
| [TASK-004](docs/tasks/TASK-004.md) | PR #1 (`941410c`) 독립 검토 | **독립 Claude Code 리뷰 세션** | 없음 (§3.2 — 리뷰 결과는 사람 오너가 판단) | 0 | **Done** (판정: 변경 요청 — [REVIEW-002](docs/reviews/REVIEW-002.md)) |
| [TASK-008](docs/tasks/TASK-008.md) | REVIEW-002 지적 반영 (중대 8 · 경미 6) | Claude Code 주 세션 | 독립 리뷰 세션 (REVIEW-003·004) | 0 | **Done** (PR #1 병합됨) |
| [TASK-009](docs/tasks/TASK-009.md) | REVIEW-002 제한 재검토 | **REVIEW-002를 작성한 독립 리뷰 세션** | 없음 (§3.2 — 재귀적 리뷰를 만들지 않음) | 0 | **Done** (판정: 변경 요청 — [REVIEW-003](docs/reviews/REVIEW-003.md), M-06 부분 해소) |
| [TASK-010](docs/tasks/TASK-010.md) | M-06 시간축·줄 결합 모호성 제거 | Claude Code 주 세션 | REVIEW-003을 작성한 독립 리뷰 세션 (REVIEW-004) | 0 | **Done** (PR #1 병합됨) |
| [TASK-011](docs/tasks/TASK-011.md) | M-06 두 반례 한정 최종 확인 | **REVIEW-002·REVIEW-003을 작성한 독립 리뷰 세션** | 없음 (§3.2 — 재귀적 리뷰를 만들지 않음) | 0 | **Done** (판정: **승인** — [REVIEW-004](docs/reviews/REVIEW-004.md)) |

> **TASK-011과 REVIEW-004의 기록은 역사 기록으로 보존됩니다.** 과거 판정을 다시 쓰지 않습니다.
> 리뷰 PR **#2·#3·#4는 리뷰 기록이 `main`에 보존된 뒤 미병합으로 종료**되었습니다
> (`AGENTS.md` §4.1 7단계 — 리뷰 PR의 처리는 사람 제품 오너의 결정).

### 2.3 Phase 1 계획 기준선·합성 plumbing slice

| TASK | 제목 | Owner | Reviewer | Phase | Status |
|---|---|---|---|---|---|
| [TASK-003](docs/tasks/TASK-003.md) | seed 코퍼스·라이선스·합성 fixture 조사 및 Gate E 증거 통합 | Claude Code 주 세션 → Lean Root 통합 | Gate S: TASK-021/REVIEW-012 승인; Gate E: PR #21 고정 HEAD 제한 재검토 통과 | Phase 1a seed corpus | **Done** — PR #21 병합 |
| [TASK-005](docs/tasks/TASK-005.md) | 평가 하네스 설계 명세 | Lean Root Orchestrator | 없음 — Gate M 비코드 설계; 제품 오너가 고정 HEAD 승인 | Phase 1a evaluation foundation | **Done — PR #25 병합** |
| [TASK-006](docs/tasks/TASK-006.md) | ReferenceBundle/v1 및 평가 실행 계약 구체화 | Claude Code 구현 세션 | Lean Root 고정 HEAD 검토 — `REVIEW-014`·`015`·`016` **변경 요청**, [`REVIEW-017`](docs/reviews/REVIEW-017.md) **승인** | Phase 1a evaluation contracts | **Done — PR #28 병합** (`bd00f604565cac09b91b07286437032486933a08`) |
| [TASK-028](docs/tasks/TASK-028.md) | Content-addressed artifact store와 재개 가능한 stage runtime | Claude Code 구현 세션 | Lean Root 고정 HEAD Gate H 검토 — `REVIEW-018`~`021` 변경 요청, [`REVIEW-022`](docs/reviews/REVIEW-022.md) 승인 | Phase 1a shared storage·orchestrator foundation | **Done — PR #36 병합** (`1d05de31aa39fd4dc8790d6c6e6442c0f8765ddc`) |
| [TASK-012](docs/tasks/TASK-012.md) | Phase 1 계획 기준선 확립 | Claude Code 주 세션 | TASK-013~017 / REVIEW-005~009 (사람 오너의 예외 승인) | Phase 1 planning / 1a 진입 | **Done** — REVIEW-009 승인 후 PR #5 병합 (`10d34b4a4545f9ae8894c8038e7f1cc9a7706d61`) |
| [TASK-013](docs/tasks/TASK-013.md) | TASK-012 고정 HEAD 독립 검토 | **이 독립 GPT Work 리뷰 세션** (사람 오너 예외 승인) | 없음 (§3.2 — 재귀적 리뷰 없음) | Phase 1 planning / TASK-012 review | **In review** (판정: 변경 요청 — [REVIEW-005](docs/reviews/REVIEW-005.md)) |
| [TASK-014](docs/tasks/TASK-014.md) | TASK-012 M-01·M-02 제한 재검토 | **REVIEW-005를 작성한 동일 GPT Work 리뷰 세션** (사람 오너 예외 승인) | 없음 (§3.2 — 재귀적 리뷰 없음) | Phase 1 planning / TASK-012 limited rereview | **In review** (M-01·M-02 부분 해소 · 판정: 변경 요청 — [REVIEW-006](docs/reviews/REVIEW-006.md)) |
| [TASK-015](docs/tasks/TASK-015.md) | REVIEW-006 잔여 6항목 한정 재검토 | **TASK-013·TASK-014 / REVIEW-005·REVIEW-006을 작성한 동일 GPT Work 리뷰 세션** (사람 오너 예외 승인) | 없음 (§3.2 — 재귀적 리뷰 없음) | Phase 1 planning / TASK-012 residual rereview | **In review** (M-01 부분 해소 · M-02 해소 · 판정: 변경 요청 — [REVIEW-007](docs/reviews/REVIEW-007.md)) |
| [TASK-016](docs/tasks/TASK-016.md) | REVIEW-007 U-22 공급자 결정 귀속 단일 항목 재검토 | **TASK-013·TASK-014·TASK-015 / REVIEW-005·REVIEW-006·REVIEW-007을 작성한 동일 GPT Work 리뷰 세션** (사람 오너 예외 승인) | 없음 (§3.2 — 재귀적 리뷰 없음) | Phase 1 planning / TASK-012 U-22 attribution rereview | **In review** (M-01 부분 해소 · M-02 해소 유지 · 판정: 변경 요청 — [REVIEW-008](docs/reviews/REVIEW-008.md)) |
| [TASK-017](docs/tasks/TASK-017.md) | REVIEW-008 STATUS 상단 직접 잔여 제한 재검토 | **TASK-013·TASK-014·TASK-015·TASK-016 / REVIEW-005·REVIEW-006·REVIEW-007·REVIEW-008을 작성한 동일 GPT Work 리뷰 세션** (사람 오너 예외 승인) | 없음 (§3.2 — 재귀적 리뷰 없음) | Phase 1 planning / TASK-012 STATUS header rereview | **In review** (M-01 해소 · M-02 해소 유지 · 판정: **승인** — [REVIEW-009](docs/reviews/REVIEW-009.md)) |
| [TASK-018](docs/tasks/TASK-018.md) | PR #5 병합 후 상태 정합성 정리 | GPT Work Root Orchestrator (사람 오너 지시 예외) | 없음 (§3.2 B열 — 상태 기록) | Phase 1a entry | **Done** — PR #11 미병합 종료, TASK-024로 대체 |
| [TASK-022](docs/tasks/TASK-022.md) | 합성 media plumbing vertical slice | Lean Root Orchestrator | 독립 Lean Root 세션 ([REVIEW-013](docs/reviews/REVIEW-013.md)) | Phase 1a synthetic slice | **Done** — PR #16 병합 |
| [TASK-023](docs/tasks/TASK-023.md) | TASK-022 Gate H 고정 HEAD 독립 검토 | Lean Root Independent Reviewer | 없음 | Phase 1a review | **Done** — 승인 기록이 PR #16에 포함됨 |
| [TASK-024](docs/tasks/TASK-024.md) | PR #16 병합 후 상태 정합성 정리 | Lean Root Orchestrator | 없음 — Gate L/M 상태 기록 | Phase 1a reconciliation | **Done** — PR #18 병합 |
| [TASK-025](docs/tasks/TASK-025.md) | U-31 번역 대상 언어 한국어 확정 | Lean Root Orchestrator | 없음 — Gate M 제품 결정 전사 | Phase 1a translation contract | **Done** (PR #19) |
| [TASK-026](docs/tasks/TASK-026.md) | U-06 seed 코퍼스 선택 계약 | 사람 제품 오너 결정 → Lean Root 기록 | 없음 — Gate M 결정 전사; 실제 다운로드는 별도 Gate H | Phase 1a evaluation data contract | **Done** — 제품 오너 승인 |
| [TASK-027](docs/tasks/TASK-027.md) | Lean Root / Claude Code 운영 분업 계약 | 사람 제품 오너 결정 → Lean Root 기록 | 없음 — Gate M 운영 결정 전사 | Project operations | **Done** — 제품 오너 승인 |

> 코드 변경은 Claude Code가 작성하고 Lean Root가 검증·리뷰합니다 (`AGENTS.md` §3.1, R8).
> Gate H·S 독립 리뷰는 구현 세션과 분리하며, **작성자 세션은 자기 변경을 스스로 승인하지 않습니다.**
> **Owner는 "수행 소유자"이며 구현자를 뜻하지 않습니다.** 리뷰 TASK의 Owner는 리뷰 수행자입니다.
> 이 표와 `docs/tasks/TASK-XXX.md`가 다르면 **TASK 파일이 정답**입니다.

---

## 3. 완료된 것

### 3.1 Phase 0 문서 기반 (TASK-000, Claude)

| 파일 | 상태 |
|---|---|
| `README.md` | 리뷰 반영됨 |
| `AGENTS.md` | 리뷰 반영됨 (§0.1 권한, §0.2 읽기 순서, §6.1 예외, §6.2 부트스트랩 신설) |
| `CLAUDE.md` | 리뷰 반영됨 |
| `PLAN.md` | 리뷰 반영됨 (§0 범위 구분 신설) |
| `STATUS.md` | 이 파일 |
| `docs/PRODUCT_SPEC.md` | 리뷰 반영됨 (§2 과제/상용 범위 구분 신설) |
| `docs/ARCHITECTURE.md` | **전면 개정** (공통 계약·ReferenceBundle·안전 게이트·재현성 등급) |
| `docs/EVALS.md` | **전면 개정** (지표 계산 규약·데이터 분할·통계 규칙·방어 지표) |
| `docs/DECISIONS.md` | 리뷰 반영됨 (ADR-0019~0026 추가, 라벨 정정). 이후 TASK-008에서 다섯 ADR을 **제안됨으로 재정정** |
| `docs/tasks/TASK-000.md` | 신규 (소급 기록) |
| `docs/tasks/TASK-001.md` | 리뷰 반영됨 |
| `docs/reviews/REVIEW-001.md` | 신규 |

**기존 사용자 콘텐츠 보존:** `README.md`의 원래 제목과 한 줄 소개는 파일 맨 위에 그대로입니다 (R2).

### 3.2 독립 리뷰 (TASK-001) — **완료된 역사 기록**

- 대상 커밋 `38146ae`, 판정 **변경 요청**
- 차단 5건 · 중대 15건 · 경미 2건 → [`docs/reviews/REVIEW-001.md`](docs/reviews/REVIEW-001.md)
- 출처: **Codex/GPT Work가 수행, 사람 제품 오너를 통해 전달, Claude가 전사** (당시 실제 경로)

> 이것은 **이미 일어난 일의 기록**입니다. 사실이므로 바꾸지 않습니다.
> **향후 독립 리뷰는 새 독립 Claude Code 세션이 수행합니다** (`AGENTS.md` §3, ADR-0027).

### 3.3 리뷰 반영 (TASK-002, Claude Code 주 세션 — PR #1의 후속 커밋)

REVIEW-001의 F-01~F-22 전부에 대응했습니다. **다만 "대응"은 "값을 정했다"가 아닙니다.**
구조를 만들고 값은 U-XX로 남긴 항목이 다수입니다 (REVIEW-001 §3).

### 3.4 운영 구조 전환 (TASK-007, Claude Code 주 세션 — PR #1의 후속 커밋)

향후 운영을 **GPT Work / Claude Code 주 세션 / 독립 Claude Code 리뷰 세션 / Claude 일반 대화**
네 역할로 전환하고, 문서 전반의 미래 운영 서술을 여기에 맞췄습니다 (`AGENTS.md` §3, ADR-0027).
Codex·Codex Cloud·GitHub `@codex review`는 **향후 역할·배정·절차에서 제거**되었습니다.
과거 기록은 **완료된 역사 기록**으로 보존했습니다.

### 3.5 독립 검토 2회차 (TASK-004) — 완료

- 대상 HEAD `941410c`, 판정 **변경 요청**
- **차단 0 · 중대 8 · 경미 6 · 의견 1** → [`docs/reviews/REVIEW-002.md`](docs/reviews/REVIEW-002.md)
- 수행: **독립 Claude Code 리뷰 세션** (PR #1 작성자 세션이 아님). 리뷰 PR은 **#2** (Draft, 미병합)
- 리뷰 원문은 `AGENTS.md` §4.1 4단계에 따라 Source Owner가 **byte-for-byte 그대로** 이 브랜치에 보존했습니다

### 3.6 REVIEW-002 반영 (TASK-008, Claude Code 주 세션 — PR #1의 후속 커밋)

중대 8건(M-01~M-08)과 경미 6건(R-09~R-14)에 대응했습니다. **"대응"은 "검증되었다"가 아닙니다.**

| 발견 | 반영 위치 |
|---|---|
| M-01 | `docs/DECISIONS.md` — **ADR-0019·0022·0024·0025·0026을 제안됨으로 정정** (오너가 미승인 확인) |
| M-02 | `AGENTS.md` §3.3 — 리뷰어 허용 목록 4종 명시 |
| M-03 | `AGENTS.md` §3.4 — "구조적으로 충돌하지 않는다" 삭제, `STATUS.md`를 coordination point로 정의 |
| M-04 | `AGENTS.md` §3.2 — A열 우선 tie-break + TASK-002 경계 사례 |
| M-05 | `docs/ARCHITECTURE.md` §3·§3.3, `docs/EVALS.md` §3.2·§5.1 — 정답 `degradation_kind` |
| M-06 | `docs/EVALS.md` §4.0.1 알고리즘 A–D, §4.1·§4.3·§4.4·§4.5 |
| M-07 | `docs/EVALS.md` §5.4 — 마스크 내부 측정 범위 + **U-30** 등록 |
| M-08 | `docs/PRODUCT_SPEC.md` §6.1 — N2의 완전한 보증 제거 |
| R-09~R-14 | PR #1 설명 · `AGENTS.md` §6·§4.1·§1 · `docs/ARCHITECTURE.md` §3.0 · `docs/reviews/REVIEW-001.md` |
| O-01 | **반영 의무 없음.** 이번에는 분할하지 않고 기존 진입점·R-9 대응 유지 (TASK-008 §6) |

> 검증은 **REVIEW-002를 작성한 독립 세션**의 재검토로 이루어집니다 (`AGENTS.md` R8 / §3.1).

### 3.7 Phase 0 종료 — `main` 병합 (PR #1)

- **PR #1이 병합되었습니다.** 병합 SHA **`d11b2450d324ac7f509741acc1ac591313876d30`**
- 최종 독립 검토 **REVIEW-004** 판정 **승인** (TASK-011) 후 사람 제품 오너가 병합
- 리뷰 PR **#2·#3·#4**는 리뷰 기록(`TASK-004·009·011`, `REVIEW-002·003·004`)이 `main`에
  보존된 뒤 **미병합으로 종료**되었습니다
- 이 문장은 PR #1 병합 시점의 역사 기록입니다. 현재 기능 코드는 TASK-022/PR #16으로 추가됐고,
  Python package 의존성·모델·CI·비밀정보는 여전히 없습니다.

### 3.8 U-08·U-11 답변 (2026-08-09, 사람 제품 오너)

| ID | 답변 | 남은 것 |
|---|---|---|
| **U-08** | **채점 정답은 번역 자막** | 당시 대상 언어가 정해지지 않아 U-31 등록 → **2026-08-22 한국어(`ko`)로 해소** |
| **U-11** | **약 2개월 · 품질 우선** (속도보다 품질) | **정확한 제출 날짜 미확정** — 정밀 일정 수립에 필요 |

상세: [`docs/DECISIONS.md`](docs/DECISIONS.md) §4.1.1 · §4.1.2 · §4.1.3

### 3.9 Phase 1 계획 기준선 병합 (TASK-012 / PR #5)

- 최종 제한 재검토 REVIEW-009 판정은 **승인**이다.
- Source Owner 기록 통합 커밋은 `1f4c099b03d41ecc496b857b4868a0d8ef8feed1`이고,
  리뷰 커밋 `a574f093faa6fdcfc98833ef39b020929ec8ed3f`과 tree
  `4c01ffebeb92077ed7e61ca18a380d0a0e20f174`가 동일하다.
- 사람 제품 오너가 PR #5를 일반 merge했고, `main` merge commit은
  `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61`이다.
- TASK-012는 `Done`으로 전이한다. 다만 병합은 `docs/DECISIONS.md`에서
  **제안됨**인 ADR이나 미해결 U-XX를 자동 승인·해결하지 않는다.
- 리뷰 PR #6~#10은 Open / Draft / 미병합 상태로 남아 있으며 처리는 사람 제품 오너의 결정이다.

### 3.10 PR #11 종료와 상태 기록 대체 (TASK-018 / TASK-024)

- PR #11은 최신 `main`과 양쪽으로 갈라져 현재 코드 상태와 충돌하므로 2026-08-22 미병합 종료했다.
- branch와 원문은 보존했고, 유효한 TASK-012 완료·제안 경계 기록만 TASK-024가 최신 `main`에 이식한다.
- PR #11 종료는 코드·기존 리뷰 PR·결정 상태를 바꾸지 않는다.

### 3.11 합성 media plumbing slice 병합 (TASK-022·023 / PR #16)

- REVIEW-013은 고정 HEAD `9dc1fee1e7ac9e1446d262963b2105ad234c1c36`에서 **승인**,
  차단·중대·경미 결함 0건으로 판정했다.
- `make verify`는 unit 8건과 실제 FFmpeg smoke를 통과했고, 사람 제품 오너가 PR #16을 일반 merge했다.
- `main` merge commit은 `e3a99c762ecd7030843e535db7dc3f7147bf811e`이다.
- Windows 11/NTFS, 실제 iCloud sync/player, 다른 FFmpeg/OS는 확인하지 않았으며 승인 증거가 아니다.

### 3.12 PR #18 병합과 U-31 답변

- 사람 제품 오너가 PR #18을 일반 merge했고 `main`은 `f1524d5519afbd06d4d2a752dd3d0d4e1572a488`이다.
- TASK-024는 병합 조건을 충족해 `Done`이다.
- 2026-08-22 사람 제품 오너가 U-31에 **한국어(BCP-47 `ko`)** 로 답했다.
- 이 답변은 모델·공급자·API(U-22), 한국어 정규화·CPS(U-18·U-19), 목표 수치(U-07)를 정하지 않는다.

### 3.13 U-31 한국어 계약 병합 (TASK-025 / PR #19)

- 사람 제품 오너가 PR #19를 일반 merge했고 merge commit은
  `b193077035fc3b48312a8327f26c74d9e975d42f`이다.
- TASK-025는 병합 조건을 충족해 `Done`이다.
- 번역 대상 언어는 한국어(BCP-47 `ko`)이며 모델·공급자·API와 한국어 정규화 규칙은 여전히 미정이다.
- 상단 보드는 self-referential HEAD 갱신 반복을 막기 위해 현재 HEAD SHA를 기록하지 않고 GitHub 조회를 기준으로 한다.

### 3.14 TASK-003 Gate E 통합 완료

- PR #21의 고정 HEAD `2d75a590a0bebaeca3827488fca4d69b4c1054e6` 제한 재검토에서 주요 문제 없음 판정을 받았다.
- 사람 제품 오너 승인 후 PR #21을 일반 merge했고 merge commit은 `d69bf4ba356c5b4765e50c7dab0d173ceabef968`이다.
- M-03 근거는 OpenSLR SLR150 배포본 범위로 제한하고, 직접 검증하지 못한 M-05는 Sintel 후보 제외로 닫았다.
- TASK-003은 `Done`이다. U-06은 TASK-026에서 해소됐으며 외부 코퍼스 다운로드·재배포는 아직 없다.

### 3.15 TASK-003 상태 정합성 병합 (PR #22)

- PR #22는 TASK-003·조사 문서·STATUS를 `Done`으로 맞췄고 merge commit은 `52b2ea92b0f913326c99efc1777026641a294663`이다.
- 코드·의존성·CI·외부 데이터 변경은 없었다.

### 3.16 U-06 seed 코퍼스 계약 병합 (TASK-026 / PR #23)

- 사람 제품 오너가 선택 조합과 local-only·재배포 경계를 승인했고 merge commit은 `a42bcf504e51707ea26aa5e84ba7edf31a10ad04`이다.
- 실제 외부 데이터 다운로드·cache 생성은 별도 Gate H이며 아직 수행하지 않았다.

### 3.17 현재 운영 분업 계약 병합 (TASK-027 / PR #24)

- 모든 코드 변경은 Claude Code가 작성하고 Lean Root가 비코드 작업·검증·리뷰·승인 후 통합을 맡는다.
- 사람 제품 오너 승인 후 일반 merge했으며 merge commit은 `176a6f106940e02e2c1d88c5fc372a4b2269d441`이다.

### 3.18 평가 하네스 설계 계약 병합 (TASK-005 / PR #25)

- 사람 제품 오너가 고정 HEAD `19e5084b344c6d0e19d18f5785facd91086eda04`를 승인했다.
- PR #25는 일반 merge됐고 merge commit은 `744c84e684f56662cc0e324d7de32df0fb66db47`이다.
- source/target 분리, chrF2, blind paired review, 실패·재개·artifact와 H-01~H-14 계약이 확정됐다.
- 코드·테스트·의존성·CI·외부 데이터 변경은 없었다.

### 3.19 평가 실행 계약 병합 (TASK-006 / PR #28)

- Gate H 1~3차 검토인 [REVIEW-014](docs/reviews/REVIEW-014.md)·[REVIEW-015](docs/reviews/REVIEW-015.md)·[REVIEW-016](docs/reviews/REVIEW-016.md)의 **변경 요청**은 각 고정 HEAD의 역사 기록으로 보존한다.
- 4차 고정 HEAD 검토 [REVIEW-017](docs/reviews/REVIEW-017.md)은 `1e94cf8aa7ede86974e1553754b960f57941da83`에서 **승인 — 기술 지적 0건, 비차단 절차 일탈 1건**으로 판정했다.
- 사람 제품 오너가 그 고정 HEAD를 승인했고 PR #28은 일반 merge됐다. merge commit은 `bd00f604565cac09b91b07286437032486933a08`이다.
- 승인 HEAD와 merge commit을 비교하면 merge commit만 1개 앞서고 변경 파일은 0개다. 따라서 승인된 구현 tree가 `main`에 그대로 반영됐다.
- TASK-006의 `Done`은 평가 계약·schema·validator·fixture의 병합을 뜻한다. 실제 ASR·번역·지표 알고리즘이나 파일시스템 run writer가 구현됐다는 뜻은 아니다.

### 3.20 TASK-028 runtime foundation 계약 병합 (PR #34)

이 절은 구현 전 **계약 병합 시점의 역사 기록**이다. 현재 완료 상태는 §3.21이 기록한다.

- 사람 제품 오너가 고정 HEAD `3ebb407ff14498a8d6cc23303b9bf5773d4b2de0`을 승인했다.
- PR #34는 일반 merge됐고 merge commit은 `0056ca01225cd662b9d3f3c5de079a380b893378`이다.
- 승인 HEAD와 merge commit의 파일 차이는 0개이며 변경은 `PLAN.md`, `STATUS.md`, `docs/tasks/TASK-028.md` 세 문서뿐이다.
- 당시에는 계약만 승인·병합됐으며 구현 코드·schema·테스트·dependency·CI가 없었다. TASK 상태는 `Not started`였다.

### 3.21 TASK-028 구현 최종 승인·병합 (REVIEW-022 / PR #36)

- [`REVIEW-022`](docs/reviews/REVIEW-022.md)는 구현 고정 HEAD
  `9cfaf4dad35b313ae2a2357f5257c2897a7b01a3`을 **승인**했다.
- 사람 제품 오너 승인 뒤 PR #36이 일반 merge됐고, merge commit은
  `1d05de31aa39fd4dc8790d6c6e6442c0f8765ddc`이다.
- 승인 HEAD 대비 merge commit은 1커밋 앞, 0커밋 뒤이며 변경 파일은 0개다.
- 병합된 `main`에서 `make verify-task-028`은 J 16/16, artifact store 36, runtime 149,
  전체 355 tests와 TASK-028·FFmpeg smoke를 통과했다.
- Windows 11/NTFS, 실제 OS crash durability와 멀티프로세스 경합은 후속 검증 경계다.
- PR #41은 리뷰 당시 원문을 담은 Open / Draft / 미병합 PR이다. 이 상태 정합성 변경은
  `REVIEW-022` 원문을 그대로 `main`에 보존하기 위한 별도 문서 변경이며, #41 종료는 자동 수행하지 않는다.

---

## 4. 다음 작업

### 현재 진행 중

| TASK | 내용 | Owner |
|---|---|---|
| 상태 정합성 — 기능 TASK와 분리 | `REVIEW-022` 원문 보존과 TASK-028·STATUS·PLAN·README의 병합 상태 정리. 코드·schema·runtime 변경 없음 | Lean Root Orchestrator (Gate L/M 문서 상태) |

> **판정과 반영 상태는 서로 다른 사실입니다. 섞지 마십시오.**
>
> | 사실 | 값 | 바뀌나 |
> |---|---|---|
> | REVIEW-005의 **판정** (고정 HEAD `c049090…`) | **변경 요청** | **아니오 — 역사 기록** (R2, `AGENTS.md` §4.1 원문 불변) |
> | REVIEW-005 이후 **최초 실질 수정 커밋** | `f001acecc1e20f88b4625428e6ac136208d4c718` (`docs: address task 012 review findings`) — **식별자일 뿐, 검토 대상 HEAD가 아닙니다** |
> | REVIEW-006의 **판정** (고정 HEAD `e0d99cf…`) | M-01 **부분 해소** · M-02 **부분 해소** · 최종 **변경 요청** | **아니오 — 역사 기록** |
> | REVIEW-006 이후 **잔여 6항목 수정 커밋** | `b57df672e67c1ff8ae1d001c874672e391c474c4` (`docs: address task 012 rereview findings`) — **식별자일 뿐, 검토 대상 HEAD가 아닙니다** |
> | REVIEW-007의 **판정** (고정 HEAD `b57df67…`) | M-01 **부분 해소**(잔여 1~3 해소, U-22 귀속만 남음) · M-02 **해소** · 최종 **변경 요청** | **아니오 — 역사 기록** |
> | REVIEW-007 이후 **잔여 1항목 반영 상태** | **대응 완료** (Source Owner 주장) | REVIEW-008이 직접 상태 잔여를 판정 |
> | REVIEW-008의 **판정** (고정 HEAD `116e033…`) | 단일 항목·M-01 **부분 해소** · M-02 **해소 유지** · 최종 **변경 요청** | **아니오 — 역사 기록** |
> | REVIEW-008 이후 **STATUS 상단 직접 잔여 반영** | `5dbc1b1ca88bdc15b0c14e003ef66fd9c13953a8` | REVIEW-009 고정 대상 |
> | REVIEW-009의 **판정** (고정 HEAD `5dbc1b1…`) | 단일 항목·M-01 **해소** · M-02 **해소 유지** · 최종 **승인** | **최종 제한 재검토** |
> | 리뷰 기록 통합 | `1f4c099b03d41ecc496b857b4868a0d8ef8feed1` | 리뷰 tree와 동일 |
> | 사람 제품 오너 결정 | PR #5 **병합** | merge commit `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
>
> 과거 변경 요청과 최종 승인은 각 고정 HEAD의 역사 기록으로 모두 유지됩니다.
> TASK-012의 `Done`은 사람 병합 전이를 뜻하며, 제안됨 ADR·U-22·U-31·U-07의
> 자동 승인 또는 해결을 뜻하지 않습니다.

### Phase 1a 실행 순서 **(전체 후속 순서는 제안됨 유지; TASK-028은 완료됨.** [`PLAN.md`](PLAN.md) §3-1d**)**

> TASK-012와 PR #5는 완료·병합됐지만, `docs/DECISIONS.md`에서 **제안됨**인 ADR과
> 아래 전체 실행 순서를 자동 승인한 것으로 해석하지 않습니다. TASK-028 계약은 사람 제품 오너가
> PR #34로 한정 승인했지만, 후속 ASR·번역·외부 코퍼스 노드는 별도 계약과 승인이 필요합니다.
> TASK-022/PR #16은 별도로 승인된 합성 plumbing 예외이며 TASK-003과 U-06 선택은 완료됐습니다.

| 노드 | 내용 | **선행 (PLAN.md §3-1d와 동일)** | U-31 상태 |
|---|---|---|---|
| **U-31** | 번역 대상 언어 | 없음 | **완료 — 한국어(`ko`)** |
| **TASK-003** | seed 코퍼스·라이선스·합성 데이터 대안 조사 + 비교표 작성 | 없음 | **완료** |
| **(사람) U-06 선택** | Common Voice 26 일본어 + LibriSpeech dev/test, 합성 코드스위칭; CHiME-6 유예 | TASK-003 결과 | **완료 — TASK-026** |
| **TASK-005** | 평가 하네스 설계 명세 (Phase 1a) | TASK-003 · U-06 선택 | **Done — PR #25** |
| **TASK-006** | `ReferenceBundle/v1` 및 평가 실행 계약 구체화 | **TASK-005** | **Done — PR #28** |
| TASK-006 코드 구현 | schema·validator·fixture | TASK-006 계약 승인·병합 | **Done — PR #28** |
| **TASK-028** | 공용 artifact/cache/resume runtime | TASK-006 완료 | **Done — REVIEW-022 승인, PR #36 병합** |
| 다음 기능 TASK | 자막 spine 기계 계약 정본화 후보; 범위·번호는 오너 승인 전 확정 아님 | TASK-028 완료와 별도 TASK 계약 | **제안 — 구현 미착수** |

> **TASK-005 평가 하네스 설계와 TASK-006 평가 실행 계약은 완료됐습니다.** TASK-006 계약은 PR #27,
> schema·validator·fixture 구현은 Gate H REVIEW-017 승인 뒤 PR #28로 병합됐습니다.
> REVIEW-014·015·016의 변경 요청과 REVIEW-017의 승인은 각 고정 HEAD의 역사 기록으로 보존합니다.
> **TASK-003·005·006은 예약된 번호이며 의미를 바꾸지 않았습니다.**
> TASK-028 계약은 PR #34, 구현은 REVIEW-022 승인 뒤 PR #36으로 병합됐습니다.
> 다음 기능 후보는 SpeechSegment·Transcript·번역·자막 결과 계약의 기계 정본화이며,
> 별도 TASK 계약과 사람 제품 오너 승인 전에는 번호·범위·구현을 확정하지 않습니다.
> 실제 모델·corpus·ASR·번역·metric·worker supervision은 별도 gate가 필요합니다.
> PR #16은 승인된 좁은 합성 예외라는 경계를 유지합니다.

**TASK-003과 U-06 결정은 완료됐습니다.** 실제 외부 코퍼스 다운로드·검증·cache 생성은 별도 작업입니다.

---

## 5. 차단 요인 — 사람 제품 오너의 답변 필요

**에이전트가 추측하지 않습니다 (R5).**

**해제된 차단**

| ID | 질문 | 결과 |
|---|---|---|
| **U-08** | 채점 정답 자막은 **원어**인가 **번역**인가? | **답변됨 — 번역 자막.** Phase 1 계획 착수 차단 **해제** |
| **U-11** | 과제 제출 기한은 언제인가? | **부분 답변됨 — 약 2개월·품질 우선.** Phase 1 계획 착수 차단 **해제** |
| **U-31** | 번역 대상 언어는 무엇인가? | **답변됨 (2026-08-22) — 한국어(`ko`).** TASK-005의 언어 결정 차단 **해제** |
| **U-06** | seed 코퍼스 최종 선택 | **답변됨 — Common Voice 26 일본어 + LibriSpeech dev/test, 합성 코드스위칭. CHiME-6 dev는 cpWER 시점까지 유예, JECS 제외.** |

**아직 남은 것**

| 항목 | 무엇이 막히는가 | 누가 답하나 |
|---|---|---|
| **정확한 제출 날짜** (U-11의 미답변 부분) | **정밀 일정 수립.** 마일스톤·버퍼를 **날짜로 고정**하는 것 | 사람 제품 오너 |

> **"약 2개월"은 운영상 시간 예산이지 확정된 캘린더 마감일이 아닙니다.**
> **임의의 제출 날짜를 만들어 적지 않습니다** (R5).
> **Phase 1 계획 착수는 이미 가능**하며, 막혀 있는 것은 **정밀 일정**뿐입니다.

> **U-06(seed 코퍼스)은 TASK-026에서 해소됐습니다.** 실제 다운로드는 별도 Gate H 작업이며,
> 승인된 범위와 약관을 다시 확인한 뒤에만 수행합니다.

### 그 외 확인되면 좋은 것

| ID | 질문 | 왜 중요한가 |
|---|---|---|
| **U-24** | 채점 배점표가 공개되어 있는가 (자막 vs 시각 비중) | **범위 판단의 근거.** 모르는 동안 두 산출물을 동등하게 다룸 |
| U-23 | 실제 사용할 PC의 GPU / VRAM / OS | 모델 크기 상한 |
| U-10 | 채점에 화자 구분(diarization)이 포함되는가 | `audio`·`subtitle` 복잡도 |
| U-09 | 자막 출력 형식 (SRT / VTT / ASS) | 형식별 표현력 차이 |
| U-25 | 입력 영상의 대략적 길이와 개수 | 처리 시간 예산 |
| U-28 | 재구성 안전 게이트의 기본 정책 수준 | Phase 2 착수 전 필요. 법적·윤리적 판단 포함 |

전체 목록: [`docs/DECISIONS.md`](docs/DECISIONS.md) §4

---

## 6. 발견된 후속 작업 (아직 TASK 아님)

작업 중 발견했지만 **범위 밖이라 손대지 않은 것**들입니다 (`AGENTS.md` §6).

| # | 내용 | 언제 |
|---|---|---|
| F1 | `.gitignore`가 없다 — 산출물·캐시 디렉터리 정의 필요 | Phase 1 착수 시 |
| F2 | 라이선스 파일(`LICENSE`)이 없다 | U-05 결정 후 |
| F3 | `norm-v1` 정규화 규칙을 별도 문서로 분리해야 할 수 있다 | Phase 1a |
| F4 | 열화 레시피 파라미터 표가 별도 문서로 커질 것 | Phase 1a |
| F5 | 사람 검토 루브릭·추출 절차를 독립 템플릿 파일로 분리 | Phase 2 |
| F6 | 지표 계산 규약(EVALS §4·§5)이 커지면 `docs/METRICS.md`로 분리 | Phase 1a |
| F7 | `ReferenceBundle` 예시 파일(스키마 샘플)이 있으면 이해가 쉬움 | Phase 1a |
| F8 | ADR 번호가 20개를 넘으면 `docs/decisions/` 디렉터리로 분할 검토 | 필요 시 |
| F9 | `README.md`의 "사람(제품 오너)이 할 일" 예시가 U-08("원어인가 번역인가")을 **아직 미해결처럼** 들고 있음 — U-08은 2026-08-09에 답변됨. `README.md`는 TASK-012의 범위 밖이라 손대지 않음 | 다음 문서 정비 시 |

> F1은 TASK-022에서 `.gitignore`를 추가해 해소됐다. 위 표는 발견 당시 기록을 보존한다.

**이 항목들을 임의로 처리하지 마십시오.** TASK로 승격된 뒤에 합니다.

---

## 7. 위험 등록부 (Risk Register)

| # | 위험 | 영향 | 현재 대응 |
|---|---|---|---|
| R-1 | 합성 열화가 실제 채점 입력과 다름 | 평가가 잘못된 방향을 가리킴 | 신호 6종 병용 ([`docs/EVALS.md`](docs/EVALS.md) §1.1). **제거 불가** |
| R-2 | 일정 부족으로 두 도메인 모두를 충분히 못 함 | 과제 산출물 미완 | U-11 확인 후 **목표 수준**을 낮춤. 도메인 폐기는 오너 결정 (AS-4) |
| R-3 | 로컬 GPU 성능 부족 | 처리 시간 과다 | U-23 확인 후 모델 크기 상한 결정 |
| R-4 | seed 코퍼스 확보 지연 | 평가 하네스 지연 | 조사를 에이전트가 선행 (ADR-0024) |
| R-5 | 우리 지표에만 과적합 | 실제 채점 개선 없음 | 다축 분리, 종합 점수 금지, frozen-test, 방어 지표 |
| R-6 | 재구성 환각을 못 걸러냄 | 허위 정보 제공 | 인공물 탐지 + blind 검토 필수화 |
| R-7 | 세션 간 문서 갈라짐 | 서로 다른 전제로 작업 | `AGENTS.md` 단일 출처 (ADR-0008), 동시 편집 금지 (R9) |
| **R-8** | **안전 게이트 우회 또는 오분류** | 의도적 비식별 처리를 재구성 → 윤리·법적 문제 | 기본 `skip`, "모르면 확인", 감사 로그 (ADR-0022, **제안됨**). 분류는 완전하지 않음 ([`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) §6.1). **U-28 미정** |
| **R-9** | **문서가 커져 오너가 못 읽음** | 결정이 지연됨 | 오너용 진입점은 `README.md`와 이 파일 §5로 한정 |
| **R-10** | **반영이 형식적일 수 있음** | 구조만 만들고 실효 없음 | 독립 세션의 검토로 확인 (TASK-004 완료 → REVIEW-002). TASK-008 반영은 **아직 검증 전** |
| **R-11** | **작성자가 자기 작업을 검토·승인함** | 검토가 형식만 남음 | 작성자 ≠ 리뷰어 세션 강제 (R8), 작성자 자기 승인 금지 (`AGENTS.md` §3.1) |
| **R-12** | **완료 보고가 실제와 다름** | 잘못된 상태 위에서 다음 작업 시작 | GitHub 상태·diff로 확인 (R10, `AGENTS.md` §3.5) |
| **R-13** | **Claude 사용량 소진** | 고난도 구현이 막힘 | 주 세션은 고난도 구현에 집중, 독립 리뷰는 중요한 단계에만 (`AGENTS.md` §3.2) |
| **R-14** | **`STATUS.md`를 두 브랜치가 함께 수정** | 리뷰 기록 통합 시 충돌 | `STATUS.md`를 coordination point로 직렬화 (`AGENTS.md` §3.4). 충돌은 Source Owner가 해결, 최종 diff는 사람 오너가 확인 |

---

## 8. 갱신 규칙

작업을 마치는 에이전트는 **반드시** 이 파일을 갱신합니다.

- §2 보드의 **자기 TASK 행** Status 변경 (항상 허용 — `AGENTS.md` §6.1)
- §3에 완료 항목 추가
- §6에 발견된 후속 작업 **추가** (기존 항목 삭제·수정 금지)
- 문서 맨 위 "마지막 갱신" 날짜 수정

§5 차단 요인과 §7 위험의 **재작성**은 해당 TASK의 범위에 포함될 때만 합니다.

**이 파일이 낡으면 다음 에이전트가 잘못된 전제로 시작합니다.**
