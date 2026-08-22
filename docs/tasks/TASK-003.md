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
| **2026-08-22 사람 제품 오너 결정** | **Gate S / Gate E 분리** — 아래 "게이트 분리" 절 |
| **다음 Reviewer** | **Gate E 통합 독립 리뷰 필요** — 직접 증거와 Sintel 보수적 제외만 검토 |

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

### 외부 검증 반영 (고정 HEAD `a2227028…` 대상, 새 TASK/REVIEW 번호를 만들지 않음)

egress가 허용된 별도 환경의 **외부 검증 기록**이 고정 HEAD `a2227028ff711f366c82506f21d5cf30bdc44d3f`에
대해 제출됐다 (PR #12 comment
[`5267477354`](https://github.com/seoji2005/media-clarity-studio/pull/12#issuecomment-5267477354),
2026-08-12T13:30:02Z).

> **이 기록은 `TASK-021`도 `REVIEW-012`도 아니며 공식 Reviewer 판정이 아니다.** 승인·변경 요청
> review event가 아니고, TASK/REVIEW 번호·브랜치·커밋을 만들지 않았다. 아래 반영은 **외부 검증
> 증거에 근거한 Source Owner의 후속 정정**이며, **자기 승인이 아니다.**

| 항목 | 외부 검증 결과 | 이 커밋의 반영 위치 |
|---|---|---|
| **F-01** | **해소 확인** — SRT `c2ed5960…` · 98 bytes · EOF `0a 0a` | [`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) **§7.5.2** |
| **F-02** | **해소 확인** — 네 실행 방식 전부에서 `/fixture-softsub.mkv` 미생성, 부모 셸 생존·`errexit`/`nounset` 불변 | 같은 문서 **§7.5.2** |
| **F-03** | **해소 확인** — unset/empty는 non-zero(bash 1 / dash 2), valid는 zero | 같은 문서 **§7.5.2** |
| **M-03** | **1차 출처 확인 완료** — S1·S1-L·S2·S3 + CC BY-SA 4.0 deed·legal code | **§3.6.1**(S1-L 행 추가·현재 효력 갱신) · **§3.6.2**(제목·구조 교체) · **§3.6.3** · **§3.6.4** · **§1.2** · **§4** · **§5** · **§6-4** · **§9** · **§11** |
| **M-05** | **부분 확인** — CC BY 3.0 deed·legal code는 직접 확인, **Durian 1차 페이지는 여전히 차단** | **§3.2.1**(CC BY 3.0 층 확인 + 잔여 blocker를 Durian으로 한정) · **§11** |

**M-03 정정의 경계 — 확인된 범위를 넘겨 일반화하지 않았다.**

- SLR150이 **배포하는 CHiME-6 archive**의 표시 라이선스가 CC BY-SA 4.0임을 기록했다.
  다른 배포본이나 원 녹음의 권리 범위 전체로 확장하지 않았다.
- S3의 2024-01-01 재발행 고지는 **CHiME-5**에 적용된다고 적었다. CHiME-6의 직접 근거는 S1·S1-L이다.
- S2의 2,000 GBP는 **당시 challenge 접근 절차**로 두고 현행 라이선스와 같은 층으로 다루지 않았다.
- **첫 vertical-slice fixture 제외는 E1~E5로 그대로 유지**했다. 라이선스 확인은 이 제외를 바꾸지 않는다.
- **seed 코퍼스 후보로 계속 유지**하되, 실제 채택·다운로드는 **U-06 사람 제품 오너 결정**으로 남겼다 (R5).

**M-05는 축소만 하고 해소하지 않았다.** `durian.blender.org`는 외부 검증에서도 열리지 않았으므로
credit scroll 문구의 **현재 게시 여부와 정확한 적용 범위**는 미확인으로 남는다. 검색 스니펫을
직접 확인으로 승격하지 않았고, credit scroll을 CC BY 3.0 자체의 일반 의무로 단정하지 않았다.

**2026-08-12의 `403 CONNECT tunnel failed` 관측은 삭제하지 않았다.** §3.2.1·§3.6.2·§11에서 당시
환경의 **역사적 egress 실패**로 보존하고, 이후 확인과 시점을 구분해 적었다.

**Owner 역할 주의 (`AGENTS.md` §3.3).** 이번 정정은 REVIEW-010에서 M-03·M-05를 지적한 리뷰
세션이 수행했다. §3.3은 리뷰어가 자기 지적을 직접 고치는 것을 금지하되 **"사람 오너가 명시적으로
'직접 고쳐라'라고 지시한 경우"를 예외**로 두며, 이 작업은 그 지시에 근거한다. 이 예외는 수정
권한에만 적용되고 **판정 권한에는 적용되지 않는다** — 이 세션은 F-01~F-03이나 M-03의 해소를
스스로 `승인`으로 판정하지 않으며, TASK-003을 `Done`으로 바꾸지 않는다 (R8 / §3.1).

**상태:** `In review` 유지. 자기 승인이나 `Done` 전환을 하지 않으며, **새 고정 HEAD에서
F-01~F-03과 M-03 정정의 독립 재검토**, 그리고 **`durian.blender.org` 접근이 가능한 환경에서의
M-05 직접 확인**을 기다린다.

---

## 게이트 분리 — 2026-08-22 사람 제품 오너 결정

**결정 날짜: 2026-08-22.** 사람 제품 오너가 다음을 결정했다.

> 외부 출처 검증을 더 반복하며 구현을 막지 않는다. **M-03·M-05의 공식 원문 독립 검증은 별도
> 후속 작업으로 유예**하고, **외부 코퍼스에 의존하지 않는 합성 vertical slice를 먼저 완료한 뒤
> 코드 구현으로 넘어간다.**

**이 결정은 M-03·M-05를 사실로 승인하거나 해결하는 결정이 아니다.** 두 게이트를 **분리**하는
결정이다. 이 세션은 사람 제품 오너가 명시적으로 재배정한 **TASK-003의 후속 Source Owner**이며,
동시 편집 세션은 없다.

### A. Gate S — 합성 vertical slice 기술 게이트

| 항목 | 값 |
|---|---|
| 범위 | 6초 로컬 합성 fixture · 98-byte SRT 규약 · 고정 FFmpeg build에서의 해시·크기 · soft-sub mux와 subtitle 추출 · raw/canonical 검증 · staging 서브셸 안전성 · **F-01·F-02·F-03 수정** · 외부 저작물·계정·네트워크·모델·API에 의존하지 않는 첫 배선 검증 |
| 문서 위치 | [`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) **§7**(사양·명령·실측)과 **§8**(완료 조건) |
| M-03·M-05와의 관계 | **독립적이다.** 합성 fixture는 외부 저작물을 입력으로 쓰지 않으므로 라이선스 확인 상태가 이 게이트의 통과 여부를 바꾸지 않는다 |
| 판정 가능성 | **이 저장소의 Reviewer 환경에서 실제로 판정할 수 있다.** 필요한 것은 egress가 아니라 동일 build FFmpeg `6.1.1-3ubuntu5`와 bash·dash뿐이며, REVIEW-011 §1.3이 그 환경을 확보한 선례다 |
| 통과하면 | **합성 vertical slice 코드 착수가 허용된다** (§C) |

### B. Gate E — 외부 출처·코퍼스 검증 게이트 (**유예됨**)

| 항목 | 값 |
|---|---|
| 범위 | OpenSLR·CHiME 공식 원문 독립 검증 · Creative Commons 원문 독립 검증 · Durian sharing/about 직접 확인 · CHiME-6·Sintel·기타 외부 코퍼스의 **실제 채택** · 다운로드·가공·재배포·외부 acceptance 사용 |
| 상태 | **별도 후속 검토로 유예됨.** 해소·승인·확정이 아니다 |
| **M-03** | **외부 검증에서 확인됐다고 보고**됐고 Source Owner가 그 증거를 반영했다. **독립 Reviewer가 원문을 직접 확인한 최종 판정이 아니다** ([`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) §3.6.2) |
| **M-05** | **Durian sharing/about 1차 페이지 직접 확인이 끝나지 않았다.** 외부 검증에서도 본문을 열지 못했다 (같은 문서 §3.2.1) |
| 코드 착수와의 관계 | **Gate E는 코드 착수의 선행 조건이 아니다.** **외부 코퍼스 채택의 선행 조건**이다 |

**Gate E가 끝나기 전까지 지키는 것:**

- **CHiME-6를 채택하지 않는다.**
- **Sintel을 사용하지 않는다** — 첫 합성 vertical slice에도, 2차 acceptance에도.
- **외부 코퍼스를 다운로드하지 않는다.**
- **외부 코퍼스 라이선스가 독립 검증됐다고 주장하지 않는다.**
- **검색 snippet이나 외부 검증 comment를 공식 Reviewer 판정으로 승격하지 않는다.**

> PR #12 comment
> [`5267477354`](https://github.com/seoji2005/media-clarity-studio/pull/12#issuecomment-5267477354)과
> 커밋 `62bd607…`의 M-03 기록은 **외부 검증 증거로 보존**하되, **독립 Reviewer가 직접 확인한
> 최종 판정으로 표현하지 않는다.**

### C. 실행 순서의 좁은 예외

현재 [`../../PLAN.md`](../../PLAN.md) §3-1d는 TASK-005·TASK-006 이후 코드 구현을 제안한다.
**이번 결정은 그 계획 전체를 폐기하지 않고 다음 한 가지 예외만 허용한다.**

> **외부 코퍼스·ASR·번역·모델·공급자 선택이 없는 합성 media plumbing vertical slice는,
> Gate S 제한 리뷰 승인 후 TASK-005·TASK-006보다 먼저 구현할 수 있다.**

**실제 코드 작업은 이 TASK에서 하지 않는다. 별도 신규 TASK와 별도 브랜치에서 수행한다.**
그 코드 TASK의 경계는 다음과 같다.

| | 내용 |
|---|---|
| **허용 범위** | `LOCAL INPUT` → `PROBE` → `EXISTING/GENERATED SRT` → `SOFT SUB` → `VERIFY` → `LOCAL STAGING EXPORT` |
| **제외 범위 (닫힌 목록)** | 외부 코퍼스 · downloader · ASR · 번역 · 모델·API·공급자 · hard-sub · 실제 iCloud API·동기화 · GUI · 시각 재구성 |

### D. 다음 Reviewer — TASK-021 / REVIEW-012

**두 번호는 이 커밋에서 소비하지 않는다.** 다음 **로컬 제한 리뷰**가 그대로 사용한다.

**다음 Reviewer가 검토하는 것 (닫힌 목록):**

1. **F-01** — §7.1.1 자체 검사 블록의 98-byte 주석
2. **F-02** — staging 블록의 서브셸 실행 단위
3. **F-03** — non-zero / zero 규범과 셸별 실측 분리
4. **Gate S / Gate E 분리가 정직하고 모순 없이 기록됐는지**
5. **외부 출처를 확인했다고 과장한 문구가 없는지**

**다음 Reviewer가 판정하지 않는 것:**

- **M-03·M-05의 사실관계.** 두 항목은 Gate E로 유예됐고, 이 저장소의 Reviewer 환경은
  egress proxy의 CONNECT allowlist 정책으로 1차 원문을 열 수 없다. **원문을 열지 못한 상태에서
  사실관계를 판정하라고 요구하지 않는다.**
- PR #13의 역사적 처분 — 사람 제품 오너의 판단 대상이다.

### E. 이 커밋이 하지 않은 것

| 하지 않은 것 | 사유 |
|---|---|
| `STATUS.md` · `PLAN.md` 수정 | **PR #11(TASK-018)이 해당 상태 정합성 작업을 보유** 중인 coordination point다 (`AGENTS.md` R9 / §3.4). **실행 순서의 최종 `PLAN.md` 정합성은 PR #11 처리 후 별도 TASK로 반영한다.** 그때까지 예외의 기록 위치는 이 절과 [`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) §10.1, PR #12 본문이다 |
| `docs/DECISIONS.md` 수정 | 이번 범위 밖 |
| TASK-019 · TASK-020 · REVIEW-010 · REVIEW-011 수정 | **원문 불변** (`AGENTS.md` §4.1). 네 blob은 이 커밋 전후 동일하다 |
| M-03 · M-05를 해소·승인·확정으로 표기 | **유예이지 해결이 아니다** |
| 모델·공급자·서비스·API·downloader·외부 코퍼스 선택 | 0건. U-06·U-07 미해결, U-22 보류, U-31 한국어(`ko`) 해소 상태 유지 |
| **Source Owner 자기 승인 · TASK-003 `Done` 전환** | **금지** (R8 / `AGENTS.md` §3.1 / §6). `Status`는 `In review` 그대로다 |
| 어떤 PR의 merge · close · Ready 전환 | **금지** (R1). 최종 처분은 사람 제품 오너의 몫 |

---

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

## 0. 최신 통합 상태 — 2026-08-22

- Gate S는 REVIEW-012 승인 후 TASK-022·023 / PR #16으로 구현·병합됐다.
- U-31은 TASK-025 / PR #19에서 한국어(`ko`)로 해소됐다.
- 기존 PR #12·#15는 최신 main보다 15 commits 뒤처졌다. rebase/history rewrite 없이
  main `6f8f0b281044da0882fc557c639ce9e654ab6bf9` 기반 통합 브랜치로 유효 blob을 이식했다.
- M-03 공식 원문 직접 증거는 [`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) §10.3에 기록했다.
- M-05 Durian 3개 페이지는 직접 요청이 모두 `402 Payment Required`였다. 검색 스니펫을
  원문으로 승격하지 않고 Sintel을 현재 후보에서 제외했다.
- 외부 코퍼스 다운로드·채택·재배포는 0건이다. CHiME-6는 독립 리뷰·U-06 결정·ShareAlike
  검토 전까지 후보일 뿐이다.

### Gate E 독립 리뷰 계약

1. SLR150·LICENSE·CHiME steward/challenge·CC 원문 기록이 적용 대상을 넘지 않는지 확인한다.
2. M-05를 확인 완료로 쓰지 않고 Sintel 제외가 모든 현재 사용 경로를 닫는지 확인한다.
3. U-06·U-07·U-22를 해결하거나 모델·공급자·API를 선택한 표현이 없는지 확인한다.
4. 최신 main 대비 문서 변경만 있고 PR #16 runtime/support blob이 불변인지 확인한다.
5. 판정은 승인 / 조건부 승인 / 변경 요청 / 환경 차단 중 하나로 기록한다.

> 이 절이 현재 상태다. 아래 Gate S/E 분리 서술과 REVIEW-010~012 기록은 역사와 승인 근거로 보존한다.

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
- U-07 절대 품질 목표 수치 확정 또는 U-31 결정을 넘어선 번역 구현 선택
- downloader, ASR, 번역, QC, hard-sub, packaging 구현
- 실제 iCloud 연동 또는 동기화 API 선택
- 바이너리 fixture, 모델 가중치, 의존성, CI, 비밀정보 추가
- PR #10·#11과 그 브랜치의 수정·병합·닫기·Ready 전환
- `STATUS.md` · `PLAN.md` 수정 — **PR #11(TASK-018)이 소유 중인 상태 정합성 작업**이므로 직렬화.
  실행 순서의 최종 `PLAN.md` 정합성은 PR #11 처리 후 별도 TASK로 반영한다 (게이트 분리 §E)
- `docs/DECISIONS.md` 수정 — 이번 범위 밖
- **합성 vertical slice의 실제 코드 구현** — 별도 신규 TASK와 별도 브랜치에서 수행한다 (§C)
- **M-03·M-05의 공식 원문 독립 검증** — Gate E로 유예됐다 (§B)

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
- [x] U-22는 `Deferred`, U-06·U-07은 미해결인 상태를 그대로 유지한다.
- [x] 저장소 상대 링크와 U-/ADR 참조 정합성을 검사한다.
- [x] 실제 diff, branch HEAD/tree/blob, PR 및 check/workflow 상태를 사후 확인한다.
- [x] 고정 SHA를 독립 리뷰 세션에 인계하고 이 세션은 자기 변경을 승인하지 않는다.

> **첫 항목의 정확한 뜻 (과장 방지).** "확인"의 수준은 출처마다 다르며 `[x]`가 **독립 검증을
> 뜻하지 않는다.** M-03 관련 URL과 CC BY 3.0 원문은 **외부 검증이 직접 열어 보고**한 것이고,
> `durian.blender.org` 3개를 포함한 나머지는 **어느 기록에서도 1차 페이지를 열지 못했다.**
> 출처별 상태는 [`../SEED_CORPUS_RESEARCH.md`](../SEED_CORPUS_RESEARCH.md) §11의
> `[외부검증]` / `[차단]` 표기가 정답이며, **공식 독립 검증은 Gate E로 유예됐다.**
>
> **이 항목의 미완이 Gate S를 막지 않는다.** §7·§8의 합성 fixture는 외부 저작물을 쓰지 않기
> 때문이다.

## 6. 검증 기록

- 공식 원문 접근일: `2026-08-12`; 후보·허용 행위·의무·서비스 약관은
  `docs/SEED_CORPUS_RESEARCH.md`에 원문별로 기록했다. **확인 수준은 URL 단위로 다르며,
  `[외부검증]`(외부 검증이 열어 보고함 · 독립 Reviewer 미확인)과 `[차단]`(아무도 열지 못함)을
  구분해 같은 문서 §11에 표기했다.** 두 표기 모두 **독립 검증이 아니며 Gate E 대상이다.**
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

### 8.1 2026-08-22 이후의 인계 (게이트 분리 반영)

**위 §8 문단은 REVIEW-010·REVIEW-011 라운드의 인계 메모이며 역사 기록으로 보존한다.**
2026-08-22 결정 이후 다음 Reviewer의 범위는 **좁아졌다.**

| 다음 Reviewer가 볼 것 | 다음 Reviewer가 보지 않을 것 |
|---|---|
| F-01 · F-02 · F-03 | **M-03·M-05의 사실관계** — Gate E로 유예 |
| Gate S / Gate E 분리의 정직성·무모순성 | 라이선스 원문의 정확성 판정 |
| 외부 출처를 확인했다고 과장한 문구의 유무 | PR #13의 역사적 처분 |

- **번호:** `TASK-021` · `REVIEW-012`. **이 커밋은 두 번호를 소비하지 않았다.**
- **리뷰 성격:** **로컬 제한 리뷰.** egress가 필요 없다. 필요한 것은 동일 build FFmpeg
  `6.1.1-3ubuntu5`와 bash·dash뿐이다.
- **Gate S가 승인되면** 합성 vertical slice 코드 착수가 허용된다. 코드는 **별도 신규 TASK와
  별도 브랜치**에서 하며 허용·제외 범위는 §C에 있다.
- **Gate S 승인은 전체 연구의 승인도, 라이선스 승인도, `Done` 전환도, PR #12 병합도 아니다.**
  병합과 최종 처분은 사람 제품 오너만 결정한다 (R1 / ADR-0009).
- **REVIEW-010·REVIEW-011의 판정은 각자의 고정 HEAD에 대한 역사 기록**이며 이 정정이
  덮어쓰지 않는다.
