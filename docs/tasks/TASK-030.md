# TASK-030 — GPT-primary 운영 계약과 Markdown 정합화

| 항목 | 값 |
|---|---|
| **ID** | TASK-030 |
| **결정자** | 사람 제품 오너 (2026-08-31 대화 지시) |
| **Owner / Author** | Lean Root Orchestrator |
| **Reviewer** | 작성자와 다른 fresh GPT/Codex 세션 — 고정 HEAD Gate M 독립 검토 필수 |
| **Phase** | Project operations |
| **Gate** | M — 권한·R1·R8·병합 경계 변경이므로 독립 리뷰 생략 금지 |
| **Status** | `In review` |
| **기준 main** | `5264f6bec469ae741e8c99d8d5d150cf78e2b76f` |

## 목표

GPT Work/Codex를 기본 실행 자원으로 사용하고 Claude Pro는 닫힌 escalation 조건에서만 쓰며,
ChatGPT Pro와 읽기 전용 서브에이전트를 중요한 지점에 제한적으로 적극 사용하는
운영 계약을 기계적 승인 경계와 함께 문서 정본에 반영한다. 반복되는 역할 설명은 `AGENTS.md`로
모으고 다른 진입 문서는 링크 중심으로 줄여 품질을 유지하면서 세션 토큰과 중복 검토를 줄인다.

## execution card

| 항목 | 값 |
|---|---|
| Source | `origin/main@5264f6bec469ae741e8c99d8d5d150cf78e2b76f` |
| Target | `lean-root/task-030-gpt-primary-operations` — fixed HEAD는 PR handoff에서 고정 |
| Active TASK | TASK-030 / `In review` |
| Gate | M, fixed-HEAD independent review required |
| Author / Reviewer | Lean Root / fresh GPT·Codex session |
| Blocker | 독립 리뷰와 제품 오너의 정확한 PR·HEAD·reviewed base 승인 전 병합 금지 |
| Next action | Draft PR → fixed HEAD review → owner decision |

## 범위

- `AGENTS.md`의 현재·미래 역할, 작성/검토 분리, Claude escalation, 서브에이전트 경계,
  최소 읽기·검증 사다리, branch와 fixed-HEAD merge 규칙
- `docs/DECISIONS.md`의 ADR-0029와 ADR 수량 정합화
- `STATUS.md`의 TASK-030 행, 현재 운영 요약, R-13 대응
- `PLAN.md`·`README.md`·`CLAUDE.md`의 중복 역할표를 정본 링크 중심으로 축약
- 이 TASK 문서와 PR handoff

제품 오너의 2026-08-31 “Markdown도 최적화” 지시는 에이전트가 작성한 중복 current/future 역할표를
축약하는 R2 예외의 근거다. 완료된 역사 기록과 `README.md` 최초 2줄은 삭제·축소하지 않는다.

## 범위 밖

- 코드·schema·test·fixture·script·Makefile·dependency·model·network 변경
- TASK-029 계약·구현·review 결과 또는 PR #45 브랜치 수정
- 완료된 TASK/REVIEW/ADR의 당시 수행 주체·판정 재작성
- `STATUS.md` 역사 절의 대규모 분리·삭제
- 기능 우선순위, 실제 모델, U-XX 결정

## 운영 계약

1. 사람 제품 오너는 제품 행동·우선순위·비용·위험 수용·최종 병합을 결정한다.
2. Lean Root는 상태 복원, 다음 TASK, 배정, 검증 조정, 오너 인계를 책임지며 배정된 변경을 직접 작성할 수 있다.
3. Codex 작성 세션은 한 브랜치·배타적 파일의 작은 구현 단위를 소유한다.
4. 리뷰가 필요한 변경의 작성자와 reviewer는 다른 행위자 또는 fresh 세션이다. reviewer가 패치하면 작성자가 되어 새 reviewer가 필요하다.
5. 서브에이전트는 위험도별 기본 수와 정확한 SHA·직교 질문 하나를 받는 read-only 증거 수집이 기본이며
   최종 판정이나 formal reviewer를 대신하지 않는다.
6. ChatGPT Pro 자문은 중요한 계약 고정, 제품·아키텍처 선택, 측정 milestone 뒤 방향 결정에 적극 사용하되
   저장소 사실·review·오너 결정·외부 반입 승인을 대신하지 않는다.
7. Claude는 `AGENTS.md` §3의 닫힌 trigger를 기록한 경우에만 호출한다.
8. 병합은 제품 오너가 지정한 PR 번호·전체 HEAD SHA·reviewed base SHA와 일치할 때만 Lean Root가 기계적으로 실행할 수 있다.

## 완료 조건

- [x] 현재 규칙의 정본이 `AGENTS.md` 한 곳에 있고 진입 문서는 이를 재정의하지 않는다.
- [x] Claude trigger와 비-trigger가 모두 닫힌 목록으로 기록된다.
- [x] author/reviewer/merge authorizer가 구분되고 stale HEAD·base 이동 시 stop 조건이 있다.
- [x] 최소 읽기, execution card, delta 재검토, 단계별 검증, 서브에이전트 한계가 기록된다.
- [x] ADR-0029가 ADR-0028의 미래 규칙만 대체하고 과거 기록과 PR #45 소유권을 보존한다.
- [x] 변경 파일이 Markdown에 한정되고 TASK-029 행·파일은 바뀌지 않는다.
- [x] 새 Work 호출문과 live repository 기반 복원 절차, Pro checkpoint 3개, 위험도별 subagent 기본값이 기록된다.
- [x] 대화 기록이 없는 clean Work 세션이 live main·PR #45·PR #47과 기본 다음 행동을 정확히 복원하는 dry-run을 통과한다.
- [ ] 작성자와 다른 fresh 세션이 고정 HEAD를 검토한다.
- [ ] 사람 제품 오너가 정확한 PR·HEAD·reviewed base를 승인한다.

## 측정 지표

- 현재·미래의 “Claude-only code” 또는 “GPT commit 금지” 충돌: 0건
- 정본 외 문서에 복제된 상세 역할표: 0개
- Claude escalation trigger: 6개, 비-trigger: 4개
- 변경된 비-Markdown 파일: 0개
- PR #45 및 TASK-029 변경: 0개
- ChatGPT Pro checkpoint: 3개, 동일 SHA·질문 재호출 0회
- subagent 기본 수: Gate L/M/H/S = 0/1/2/3, formal reviewer 대체 0회
- clean-session continuity dry-run: main·#45·#47 identity 및 다음 행동 4/4 일치
- 독립 fixed-HEAD review와 owner exact-HEAD approval: 각각 1회

## rollback 조건

- author/reviewer 분리가 약해지거나 오너 승인 없이 병합 가능한 문구가 생기면 병합하지 않는다.
- PR #45의 소유권·고정 HEAD·review 상태를 소급 변경하면 병합하지 않는다.
- 코드·schema·test 또는 dependency/model/network 변경이 필요해지면 범위 초과로 중단한다.
- 결함이 발견되면 이 TASK에서 바꾼 Markdown과 ADR-0029만 한 묶음으로 되돌린다.
  ADR-0027·0028과 역사 기록은 삭제하지 않는다.

## 전환

새 계약은 이 PR의 merge commit 이후 시작하는 TASK에만 적용한다. PR #45/TASK-029는 시작 당시의
Claude author / Lean Root reviewer 계약으로 완료하거나 제품 오너가 명시적으로 종료한다.
기본 순서는 PR #45를 먼저 종료한 뒤 이 브랜치를 최신 `main`에 갱신하고 새 base·HEAD로 재검토하는 것이다.
역순은 제품 오너가 명시적으로 선택할 때만 허용한다.
운영 PR과 PR #45의 `STATUS.md` 충돌은 각 Source Owner가 해결하고 최종 diff를 다시 검토한다.
