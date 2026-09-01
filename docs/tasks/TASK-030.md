# TASK-030 — GPT-primary 운영 계약과 Markdown 정합화

| 항목 | 값 |
|---|---|
| **ID** | TASK-030 |
| **결정자** | 사람 제품 오너 (2026-08-31 GPT-primary, 2026-09-01 run-resilience 승인) |
| **Owner / Author** | Lean Root Orchestrator |
| **Reviewer** | 작성자와 다른 fresh GPT/Codex 세션 — 고정 HEAD Gate M 독립 검토 필수 |
| **Phase** | Project operations |
| **Gate** | M — 권한·R1·R8·병합 경계 변경이므로 독립 리뷰 생략 금지 |
| **Status** | `In review` |
| **기준 main** | `6f94705598c1ef57a4d25682938cbcbbaf044732` (PR #45 merge commit) |

## 목표

GPT Work/Codex를 기본 실행 자원으로 사용하고 Claude는 닫힌 escalation 조건에서만 쓴다.
승인된 scope가 run·세션·모델 중단으로 소멸하지 않게 하며, coherent work를 durable checkpoint부터
재개하고 내부 단계마다 제품 오너에게 진행 승인을 반복 요청하지 않는 계약을 기계적 merge 경계와 함께
문서 정본에 반영한다. ChatGPT Pro·Ultra급 reasoning·read-only subagent는 reasoning이 실제 병목인
지점에만 제한한다. 반복되는 역할 설명은 `AGENTS.md`로 모으고 진입 문서는 링크 중심으로 줄인다.

## execution card

| 항목 | 값 |
|---|---|
| Source | `origin/main@6f94705598c1ef57a4d25682938cbcbbaf044732` |
| Target | `lean-root/task-030-gpt-primary-operations` — fixed HEAD는 PR handoff에서 고정 |
| Active TASK | TASK-030 / `In review` |
| Gate | M, fixed-HEAD independent review required |
| Author / Reviewer | Lean Root / fresh GPT·Codex session |
| Blocker | 독립 리뷰와 제품 오너의 정확한 PR·HEAD·reviewed base 승인 전 병합 금지 |
| Next action | coherent commit/push → remote HEAD 고정 → fresh Gate M review → owner decision |

## 범위

- `AGENTS.md`의 현재·미래 역할, 작성/검토 분리, Claude escalation, 서브에이전트 경계,
  승인 연속성, 중단 복구, durable checkpoint, 검증 사다리, retry/model budget,
  compact handoff, branch와 fixed-HEAD merge 규칙
- `docs/DECISIONS.md`의 운영 ADR을 ADR-0030으로 재번호화하고 ADR 수량·supersession 정합화
- `STATUS.md`의 PR #45/TASK-029 완료와 TASK-030 현재 상태 수동 정합화
- `PLAN.md`의 TASK-029 완료와 다음 미확정 기능 경계 정합화
- `PLAN.md`·`README.md`·`CLAUDE.md`의 중복 역할표를 정본 링크 중심으로 축약
- 이 TASK 문서와 PR handoff

제품 오너의 2026-08-31 “Markdown도 최적화” 지시는 에이전트가 작성한 중복 current/future 역할표를
축약하는 R2 예외의 근거다. 완료된 역사 기록과 `README.md` 최초 2줄은 삭제·축소하지 않는다.

## 범위 밖

- 코드·schema·test·fixture·script·Makefile·dependency·model·network 변경
- TASK-029 계약·구현·review 원문 또는 PR #45/#46 브랜치 수정. 병합 뒤 상태·계획 참조 정합화만 허용
- 완료된 TASK/REVIEW/ADR의 당시 수행 주체·판정 재작성
- `STATUS.md` 역사 절의 대규모 분리·삭제
- 기능 우선순위, 실제 모델, U-XX 결정

## 운영 계약

상세 정본은 `AGENTS.md` §3입니다. 이 TASK의 승인 범위는 다음 15개 결과를 함께 요구합니다.

1. **Approval continuity:** 제품 오너 승인은 run이 아니라 bounded TASK/PR scope에 적용한다.
2. **Run resilience:** 중단 뒤 live/durable state만 복원하고 A–D 상태별로 완료 지점 다음부터 계속한다.
3. **Durable checkpoint:** coherent 수정→focused verify→commit→push→remote HEAD 순서를 지킨다.
4. **One scope, multiple runs:** Author·Reviewer·Integration run 분리는 새 scope 승인이 아니다.
5. **Stop after durable state:** Author는 push·remote 확인 뒤 종료할 수 있고 fresh Reviewer가 이어받는다.
6. **Verification ladder:** identity/scope→focused→TASK/module→full 순서로 상승하며 같은 HEAD 증거를 반복하지 않는다.
7. **Bounded remediation:** exact HEAD, finding 기본 최대 5개, allowed/forbidden path, regression, stop condition을 고정한다.
8. **Retry budget:** 동일 HEAD/objective가 두 번 비정상 종료되면 세 번째 접근 방식을 바꾼다.
9. **Model/reasoning allocation:** mechanical work는 안정적인 기본 reasoning, Ultra급은 실제 reasoning 병목에 한정한다.
10. **ChatGPT Pro checkpoint:** 중요한 계약·대안·측정 milestone에 쓰고 단순 remediation/push/status에는 반복 호출하지 않는다.
11. **Subagent budget:** Gate L/M/H/S의 0/max1/max2/max3은 quota가 아니라 상한 기본값이다.
12. **Compact handoff:** `AGENTS.md` §7의 14필드 packet으로 clean session이 재개할 수 있다.
13. **Interruption UX:** 승인 범위 안에서 `계속/commit/push/review?`를 반복 질문하지 않는다.
14. **Current serialization:** PR #45는 기존 계약으로 끝내고, 그 merge 뒤 PR #47을 rebase·수동 정합화한다.
15. **Acceptance boundary:** Author/Reviewer 분리, consequential owner gate, exact-HEAD/base merge 승인은 약화하지 않는다.

## 완료 조건

- [x] 현재 규칙의 정본이 `AGENTS.md` 한 곳에 있고 진입 문서는 이를 재정의하지 않는다.
- [x] Claude trigger와 비-trigger가 모두 닫힌 목록으로 기록된다.
- [x] author/reviewer/merge authorizer가 구분되고 stale HEAD·base 이동 시 stop 조건이 있다.
- [x] 최소 읽기, execution card, delta 재검토, 단계별 검증, 서브에이전트 한계가 기록된다.
- [x] ADR-0030이 ADR-0028의 미래 규칙만 대체하고 LID ADR-0029·과거 기록·PR #45 소유권을 보존한다.
- [x] PR #45 merge 뒤 최신 `main`으로 rebase하고 STATUS·PLAN·DECISIONS·TASK-030을 수동 정합화한다.
- [x] 변경 파일이 Markdown에 한정되고 TASK-029 계약·구현·review 원문은 바뀌지 않는다.
- [x] 새 Work 호출문, A–D 복원, durable checkpoint, compact handoff, retry/model budget이 기록된다.
- [x] Pro checkpoint 3개와 mechanical 비호출, 필요한 만큼만 쓰는 subagent 상한이 기록된다.
- [x] 대화 기록이 없는 clean Work 세션이 live main·#45 merged·#47 Draft와 다음 행동을 정확히 복원한다.
- [ ] 작성자와 다른 fresh 세션이 고정 HEAD를 검토한다.
- [ ] 사람 제품 오너가 정확한 PR·HEAD·reviewed base를 승인한다.

## 측정 지표

- 현재·미래의 “Claude-only code” 또는 “GPT commit 금지” 충돌: 0건
- 현재·미래 규칙을 재정의하는 정본 외 상세 역할표: 0개 (superseded 역사표는 배너와 함께 보존)
- Claude escalation trigger: 6개, 비-trigger: 4개
- 변경된 비-Markdown 파일: 0개
- PR #45/#46 브랜치 및 TASK-029 계약·구현·review 원문 변경: 0개
- ChatGPT Pro checkpoint: 3개, 동일 SHA·질문 재호출 0회
- subagent 상한 기본값: Gate L/M/H/S = 0/max1/max2/max3, formal reviewer 대체 0회
- approval 재요청 gate: 5/5, A–D 복구 상태: 4/4, compact handoff: 14/14 fields
- clean-session continuity: main·#45 merged·#47 Draft·next action 4/4 일치
- PR #45 serialization: 기존 ownership/review·exact-head approval·merge·new-main rebase 4/4
- fresh fixed-HEAD review: 0/1 (다음 단계), owner exact-HEAD approval: 0/1 (review 뒤 요청)

## rollback 조건

- author/reviewer 분리가 약해지거나 오너 승인 없이 병합 가능한 문구가 생기면 병합하지 않는다.
- PR #45의 소유권·고정 HEAD·review 상태를 소급 변경하면 병합하지 않는다.
- 코드·schema·test 또는 dependency/model/network 변경이 필요해지면 범위 초과로 중단한다.
- 결함이 발견되면 이 TASK에서 바꾼 Markdown과 ADR-0030만 한 묶음으로 되돌린다.
  ADR-0027·0028과 역사 기록은 삭제하지 않는다.

## 전환

새 계약은 PR #47의 merge commit 이후 시작하는 TASK에만 적용한다. PR #45/TASK-029는 시작 당시의
Claude Author / Lean Root Reviewer 계약으로 완료됐고 `6f94705598c1ef57a4d25682938cbcbbaf044732`에
병합됐다. PR #47은 그 commit으로 rebase하고 STATUS·PLAN·DECISIONS·completion metrics를 수동
정합화했다. 다음 단계는 새 base·remote HEAD를 고정한 fresh Gate M independent review다.
그 review가 승인된 뒤에만 제품 오너에게 exact PR·HEAD·reviewed base merge 승인을 요청한다.
