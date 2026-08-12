# TASK-003 — seed 코퍼스·라이선스·합성 fixture 조사

| 항목 | 값 |
|---|---|
| **ID** | TASK-003 |
| **Owner (수행 소유)** | **Claude Code 주 세션** — `AGENTS.md` §3 역할 2. 저장소 근거는 아래 "Owner 판정 근거" |
| **Reviewer** | **독립 Claude Code 리뷰 세션 필요** — `AGENTS.md` §3.2 A열(데이터 출처·라이선스와 다음 vertical slice의 중요 판단 근거) |
| **Phase** | Phase 1a / seed corpus research |
| **Status** | `In review` |
| **기준 브랜치** | `main` |
| **기준 SHA** | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| **기준 tree** | `4c01ffebeb92077ed7e61ca18a380d0a0e20f174` |
| **작업 브랜치** | `claude/task-003-seed-corpus-research-gptw-0812` |
| **Draft PR** | `#12` |
| **차단 질문** | 없음 — U-31은 이 작업을 막지 않음 |

### 독립 검토 이력 (역사 기록 — 판정을 덮어쓰지 않는다)

| 회차 | 리뷰 TASK / 문서 | 고정 대상 HEAD | 판정 |
|---|---|---|---|
| 1 | [TASK-019](TASK-019.md) / [REVIEW-010](../reviews/REVIEW-010.md) | `e063c3331681e519dcd6296cbc5cd48276eabb85` | **변경 요청** — M-01 중대 · M-02~M-04 보통 · M-05 경미 |
| 2 | [TASK-020](TASK-020.md) / [REVIEW-011](../reviews/REVIEW-011.md) | `5b465a1043cfa957a24ddbb43eadefe762ad3888` | **변경 요청** — F-01 보통 · F-02 보통 · F-03 경미 |

**REVIEW-011의 항목별 판정:** M-01 부분 해소 · M-02 부분 해소 · **M-03 차단** · M-04 해소 ·
**M-05 차단**. 새 차단 결함은 없으며 F-01~F-03은 전부 문서에서 수정 가능한 항목이었다.

**F-01~F-03 반영 (이 TASK 안에서 수행, 새 TASK 번호를 만들지 않음):**

| ID | 내용 | 반영 위치 |
|---|---|---|
| **F-01** | §7.1.1 자체 검사 블록의 `wc -c` 주석이 `96`으로 같은 절의 규약(98 bytes)·실측과 모순 | [`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) §7.1.1 주석 `96` → `98`, §7.4.1 대조표에 크기 열(98 / 97) 추가 |
| **F-02** | 대화형 셸에서 `:?` 실패 후에도 `cp`가 실행되어 `/fixture-softsub.mkv`가 실제로 생성됨 | §7.3 staging 블록을 `( set -eu; … )` **서브셸 한 단위**로 교체하고 실행 규약 8항 명시 |
| **F-03** | staging 실패를 `exit 2`로 고정한 표현이 bash에서 재현되지 않음 | §7.4 표와 §7.5.1을 **non-zero / zero** 규범으로 교체. 셸·실행 방식별 실측표를 별도로 기록 |

**M-03·M-05는 이번 수정 대상이 아니다.** REVIEW-011은 두 항목의 **문서 구조에 새 결함이 없다**고
판정했고, 필요한 것은 Source Owner의 추정 수정이 아니라 **공식 1차 페이지를 직접 열 수 있는
독립 검증 환경**이다. 따라서 `[차단]` 표시를 유지하고, 검색 결과를 직접 확인으로 바꾸지 않으며,
라이선스 결론을 새로 단정하지 않았다. **두 항목이 해소됐다고 주장하지 않는다.**

**상태:** `In review` 유지. 자기 승인이나 `Done` 전환을 하지 않으며, **새 고정 HEAD에서
F-01~F-03의 제한 재검토**와 **egress 허용 환경에서의 M-03·M-05 직접 확인**을 기다린다.

### Owner 판정 근거 (REVIEW-010 M-04 반영)

이전 판은 Owner를 `GPT Work Root Orchestrator (사람 제품 오너의 이 대화상 명시적 수행 지시 예외)`로
적었다. **이 표기는 두 가지 이유로 잘못이었고 정정한다.**

| 문제 | 근거 |
|---|---|
| GPT Work는 Owner가 될 수 없다 | [`AGENTS.md`](../../AGENTS.md) §3: "**Owner / Reviewer가 될 수 있는 것은 2번과 3번뿐입니다.** GPT Work(1)와 Claude 일반 대화(4)는 … TASK의 Owner도 Reviewer도 아닙니다." §6 주체 주의도 "GPT Work는 … 저장소 파일을 만들지 않습니다"로 적는다 |
| "이 대화상 예외"는 근거가 될 수 없다 | R7·§7은 인계를 **저장소 파일과 PR 설명으로만** 하도록 하고 대화 참조 표현을 금지한다. §3.1은 파일만 보고 이해되지 않는 것을 **결함**으로 규정한다. 따라서 저장소에서 검증 불가능한 예외는 표기 근거가 되지 못한다 |

**정정 후 Owner = `AGENTS.md` §3 역할 2 (Claude Code 주 세션).** 저장소에서 확인 가능한 근거는
다음 두 가지이며, 새 명칭이나 새 예외를 만들지 않았다.

1. **브랜치 접두사.** `AGENTS.md` §4는 `claude/…`를 "Claude Code **주 세션**이 소유한 작업",
   `claude-review/…`를 독립 리뷰 세션의 브랜치로 정의한다. 이 TASK의 작업 브랜치는
   `claude/task-003-seed-corpus-research-gptw-0812`로 **주 세션 소유 브랜치**다.
2. **§3의 폐쇄 목록.** Owner가 될 수 있는 역할은 2와 3뿐이고, 이 TASK의 산출물은 리뷰 보고서가
   아니라 조사 문서이므로 역할 3이 아니다. 남는 것은 **역할 2**뿐이다.

**Source Owner와 독립 Reviewer는 계속 분리된다** (R8 / §3.1). 이 TASK의 Reviewer는 별도 세션이
수행한 [TASK-019](TASK-019.md) / [REVIEW-010](../reviews/REVIEW-010.md)이며, **REVIEW-010의
Reviewer 표기는 변경하지 않았다.**

> **`STATUS.md` 보드 행 통합은 이 커밋에 포함하지 않는다.** `STATUS.md`는 PR #11(TASK-018)이
> 소유 중인 coordination point이므로 `AGENTS.md` §3.4의 직렬화 순서를 따라 **PR #11 처리 후**
> 최신 `main`에서 통합한다.

## 1. 목표

공식 원문을 근거로 seed 코퍼스와 짧은 로컬 미디어 fixture 후보의 사용 조건을 비교하고,
외부 자료가 부적합하거나 불필요한 첫 vertical slice에는 완전 합성 fixture를 쓸 수 있도록
재현 가능한 최소 사양과 생성 절차를 제시한다. 조사 결과는 사람 제품 오너가 U-06을 선택할
수 있는 근거가 되어야 한다.

## 2. 범위

- 짧은 로컬 미디어 fixture 및 향후 ASR 평가 seed 후보 조사
- 후보별 정확한 라이선스·공식 출처·정답 형식·규모·비용·위험 기록
- 다운로드, 로컬 처리, 재배포, 저장소 포함, 파생물·자막 생성 허용 여부 비교
- 저작자 표시·라이선스 고지·변경 표시·동일조건변경허락 등 의무 기록
- 콘텐츠 라이선스와 배포 서비스 이용약관의 구분
- 법적·출처상 모호한 후보의 제외 근거
- 완전 합성 fixture의 최소 사양·결정성 범위·생성 절차
- 다음 vertical slice에 대한 권고:
  `LOCAL INPUT → PROBE → EXISTING/GENERATED SRT → SOFT SUB → VERIFY → ICLOUD-STAGING EXPORT`

## 3. 범위 밖

- U-06 최종 선택 또는 외부 코퍼스 다운로드·저장소 포함
- U-22의 모델·엔진·실행 방식·공급자·서비스·API·라이선스 선택
- U-31 번역 대상 언어 또는 U-07 절대 품질 목표 수치 확정
- downloader, ASR, 번역, QC, hard-sub, packaging 구현
- 실제 iCloud 연동 또는 동기화 API 선택
- 바이너리 fixture, 모델 가중치, 의존성, CI, 비밀정보 추가
- PR #10·#11과 그 브랜치의 수정·병합·닫기·Ready 전환
- `STATUS.md` 수정 — TASK-018/PR #11이 소유 중인 coordination point이므로 직렬화

## 4. 산출물

- `docs/tasks/TASK-003.md`
- `docs/SEED_CORPUS_RESEARCH.md`

## 5. 완료 조건

- [x] 라이선스·이용약관을 현재 공식 원문에서 확인하고 접근일을 기록한다.
- [x] 후보별 필수 비교 필드와 허용 행위·의무를 표로 정리한다.
- [x] 콘텐츠 라이선스와 서비스 접근 조건을 분리해 설명한다.
- [x] 불명확하거나 첫 vertical slice에 부적합한 후보의 제외 사유를 기록한다.
- [x] 완전 합성 fixture의 최소 사양, 생성 절차, 재현성 한계를 기록한다.
- [x] 첫 vertical slice의 권고안과 향후 ASR seed 후보를 구분한다.
- [x] U-22는 `Deferred`, U-06·U-31·U-07은 미해결인 상태를 그대로 유지한다.
- [x] 저장소 상대 링크와 U-/ADR 참조 정합성을 검사한다.
- [x] 실제 diff, branch HEAD/tree/blob, PR 및 check/workflow 상태를 사후 확인한다.
- [x] 고정 SHA를 독립 리뷰 세션에 인계하고 이 세션은 자기 변경을 승인하지 않는다.

## 6. 검증 기록

- 공식 원문 접근일: `2026-08-12`; 후보·허용 행위·의무·서비스 약관은
  `docs/SEED_CORPUS_RESEARCH.md`에 원문별로 기록했다.
- 상대 Markdown 대상 5개(링크 6회)와 `U-06`, `U-07`, `U-22`, `U-31`, `ADR-0018`을
  기준 문서에 대조했고 누락은 0개였다.
- 합성 fixture를 같은 FFmpeg `6.1.1-3ubuntu5` 빌드와 같은 명령으로 2회 생성하여 source,
  SRT, soft-sub 산출물이 각각 byte-identical임을 확인했다. 결과 SHA-256은 조사 문서에 기록했다.
- soft-sub의 video/audio stream-copy, SubRip 추출 동일성, staging copy SHA 동일성을 확인했다.
- Draft PR #12를 독립 Reviewer 인계 경계로 사용한다. Source Owner 작업은 완료됐지만 독립
  판정 전이므로 상태는 `In review`이며, 이 세션은 승인하지 않는다.
- `STATUS.md`는 의도적으로 변경하지 않았다. TASK-018/PR #11 처리 후 최신 `main`에서
  coordination board에 직렬 통합한다.

## 7. 파일 소유와 열린 PR 경계

PR #10과 PR #11은 모두 `STATUS.md`를 수정한다. 이 TASK는 두 PR을 변경하지 않고,
새 파일 두 개만 소유한다. 현재 상태는 이 TASK 파일의 머리말과 Draft PR에 기록하며,
`STATUS.md` 보드 통합은 TASK-018 처리 후 Source Owner가 최신 `main`에서 수행한다.

## 8. 인계 메모

리뷰어는 고정 HEAD에서 라이선스 원문의 정확성, 허용 행위 표의 과장 여부, 서비스 약관과
콘텐츠 라이선스의 혼동 여부, 합성 fixture 명령의 재현 가능성, U-XX 미해결 보존을 중점 확인한다.
사람 제품 오너는 리뷰 결과와 비교표를 보고 U-06을 선택한다. 이 문서는 법률 자문이 아니라
프로젝트 위험 선별 기록이다.
