# TASK-020 — TASK-003 변경 요청 반영분 제한 재검토 (REVIEW-010 M-01~M-05)

| 항목 | 값 |
|---|---|
| **ID** | TASK-020 |
| **Owner (수행 소유)** | **독립 Claude Code 리뷰 세션** — `AGENTS.md` §3 역할 3 |
| **Reviewer** | **없음 (§3.2)** — 재귀적 리뷰를 만들지 않는다. 사유는 아래 §1.1 |
| **Phase** | Phase 1a / TASK-003 제한 재검토 |
| **Status** | `In review` |
| **재검토 대상 PR** | `#12` (Open / Draft / 미병합) |
| **재검토 대상 브랜치** | `claude/task-003-seed-corpus-research-gptw-0812` |
| **고정 대상 HEAD** | `5b465a1043cfa957a24ddbb43eadefe762ad3888` |
| **고정 대상 tree** | `b899af13018aa22cfdb66402546042755acd507e` |
| **고정 blob — 조사 문서** | `0a6d8cd2b3eaaf2037df4c7470dbe0341282f9e7` (`docs/SEED_CORPUS_RESEARCH.md`) |
| **고정 blob — TASK-003** | `aec1cdf124d6d29f7078b15d38a5268026ea6eca` (`docs/tasks/TASK-003.md`) |
| **고정 blob — REVIEW-010** | `66c04cc977c97be4775a7520f33a41d750ead5df` (`docs/reviews/REVIEW-010.md`) |
| **고정 blob — TASK-019** | `3081ac708aff60c4fe9c9d4199665b4db4464f5f` (`docs/tasks/TASK-019.md`) |
| **비교 기준 `main`** | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| **직전 판정** | REVIEW-010 — **변경 요청** (중대 1 · 보통 3 · 경미 1) |
| **재검토 범위** | **REVIEW-010의 M-01~M-05와 PR #13 절차 이탈 기록의 사실성만.** 전체 재검토 아님 |
| **산출물** | `docs/tasks/TASK-020.md`, `docs/reviews/REVIEW-011.md` |
| **리뷰 브랜치** | `claude-review/task-020-task-003-followup` |
| **차단 질문** | 없음 — 단, M-03·M-05는 실행 환경의 egress 차단으로 **판정이 `차단`** (§4) |

## 1. 목표

`AGENTS.md` §4.1 6단계(재검토)를 수행한다. REVIEW-010이 `변경 요청`으로 지목한 M-01~M-05가
고정 HEAD `5b465a1043…`에서 실제로 해소됐는지를 **저장소·고정 SHA·PR diff·직접 실행·공식 원문**
만으로 판정하고, PR #12 본문이 새로 기록한 **PR #13 절차 이탈 서술의 사실성**을 관측 가능한
GitHub 객체로 대조한다.

### 1.1 `Reviewer: 없음 (§3.2)`의 사유

이 TASK의 산출물은 **리뷰 보고서 자체**(`REVIEW-011.md`)이며 대상 문서를 수정하지 않는다.
여기에 다시 독립 Reviewer를 배정하면 리뷰의 리뷰가 무한히 이어진다. `AGENTS.md` §3.2는
독립 리뷰를 **중요한 PR·핵심 알고리즘 변경**에 한정해 쓰도록 하며(사용량 제약), 리뷰 보고서
자체는 A열 조건에 해당하지 않는다. 이 보고서의 판정은 **사람 제품 오너가 직접 확인**한다.

### 1.2 세션 분리와 근거의 출처 (R8 / §3.1 / R7)

- 이 세션은 **TASK-003의 작성자 세션이 아니며**, REVIEW-010을 작성한 세션도 아니다.
  새로 시작한 독립 Claude Code 리뷰 세션이다.
- **작성자(Source Owner)의 대화 맥락을 전달받지 않았고, 근거로 사용하지 않았다.**
  Source Owner의 완료 보고·자기 검증 서술도 **증거로 채택하지 않았다** (R10).
- 판단 근거는 다음 넷뿐이다: ① 고정 SHA의 저장소 파일, ② PR #12·#13의 GitHub 객체와 diff,
  ③ **이 세션에서 직접 실행한 명령의 실측 출력**, ④ 직접 연 공식 1차 원문(열린 것에 한함).
- 문서만 보고 이해되지 않은 것은 추정하지 않고 `차단` 또는 `미해소`로 남겼다 (R5).

## 2. 고정 상태 확인 (착수 전, 2026-08-12)

**모든 고정값이 이동하지 않았음을 확인한 뒤에 브랜치를 만들었다.**

| 항목 | 지시된 고정값 | 실측값 | 판정 |
|---|---|---|---|
| PR #12 상태 | Open / Draft / 미병합 | `state=open`, `draft=true`, `merged=false`, `mergeable_state=clean` | **일치** |
| PR #12 head | `5b465a1043…` | `5b465a1043cfa957a24ddbb43eadefe762ad3888` | **일치** |
| tree | `b899af1301…` | `b899af13018aa22cfdb66402546042755acd507e` | **일치** |
| `5b465a1043…`의 직접 부모 | `6399e22249…` | `6399e22249aa324f03566abacd8ceaefe618efd5` (부모 **1개**) | **일치** |
| `main` | `10d34b4a…` | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` | **일치** |
| blob `docs/SEED_CORPUS_RESEARCH.md` | `0a6d8cd2b3eaaf2037df4c7470dbe0341282f9e7` | 동일 | **일치** |
| blob `docs/tasks/TASK-003.md` | `aec1cdf124d6d29f7078b15d38a5268026ea6eca` | 동일 | **일치** |
| blob `docs/reviews/REVIEW-010.md` | `66c04cc977c97be4775a7520f33a41d750ead5df` | 동일 | **일치** |
| blob `docs/tasks/TASK-019.md` | `3081ac708aff60c4fe9c9d4199665b4db4464f5f` | 동일 | **일치** |
| PR #12 전체 (main 대비) | 4파일 · 5커밋 · +1281 / −0 | `changed_files=4`, `commits=5`, `additions=1281`, `deletions=0` | **일치** |
| 수정 커밋 `5b465a1043…` 단독 | 2파일 · +328 / −44 | `SEED_CORPUS_RESEARCH.md` +300/−43, `TASK-003.md` +28/−1 = **+328/−44** | **일치** |
| TASK-020 번호 | 미사용·미예약 | 원격 15개 ref 전수 `git grep` 0건. 최대 사용 번호 TASK-019 | **사용 가능** |
| REVIEW-011 번호 | 미사용·미예약 | 원격 15개 ref 전수 `git grep` 0건. 최대 사용 번호 REVIEW-010 | **사용 가능** |

**고정값이 하나도 이동하지 않았으므로 중단하지 않고 재검토를 수행했다.**

사용한 확인 명령:

```
git rev-parse 5b465a1043cfa957a24ddbb43eadefe762ad3888
git rev-parse 5b465a1043cfa957a24ddbb43eadefe762ad3888^{tree}
git rev-list --parents -n 1 5b465a1043cfa957a24ddbb43eadefe762ad3888
git rev-parse 5b465a1043cfa957a24ddbb43eadefe762ad3888:docs/SEED_CORPUS_RESEARCH.md
git rev-parse 5b465a1043cfa957a24ddbb43eadefe762ad3888:docs/tasks/TASK-003.md
git rev-parse 5b465a1043cfa957a24ddbb43eadefe762ad3888:docs/reviews/REVIEW-010.md
git rev-parse 5b465a1043cfa957a24ddbb43eadefe762ad3888:docs/tasks/TASK-019.md
git diff --numstat 6399e22249aa324f03566abacd8ceaefe618efd5 5b465a1043cfa957a24ddbb43eadefe762ad3888
```

### 2.1 열린 PR 경계와 `STATUS.md` 소유 관계

| PR | 상태 | head | base | `STATUS.md` 수정 여부 |
|---|---|---|---|---|
| #10 | **Open / Draft** | `claude-review/task-017-…` @ `a574f093…` | `claude/task-012-phase1-plan-k3n7qw` | 이 재검토 대상 아님 |
| #11 | **Open / Draft** | `claude/task-018-post-merge-state-reconcile-gptw-0812` @ `da161f86…` | `main` | **수정함** — `STATUS.md` +60행 변경 |
| #12 | Open / Draft / 미병합 | `claude/task-003-…-gptw-0812` @ `5b465a1043…` | `main` | 수정 안 함 (diff 0) |
| #13 | **Closed / Merged** | `claude/task-003-seed-corpus-review-bf4nih` @ `6399e222…` | `claude/task-003-…-gptw-0812` @ `e063c333…` | 수정 안 함 |

**`STATUS.md`는 현재 PR #11(TASK-018)이 소유 중인 coordination point다.** PR #11은 Open이며
`STATUS.md`를 60행 수정한다. 따라서 `AGENTS.md` R9 / §3.4의 직렬화를 우선한다.

### 2.2 `STATUS.md` 상태 기록 유예 — 사유

**이 TASK는 `STATUS.md`를 수정하지 않는다.**

- `AGENTS.md` §6.1은 리뷰 세션에게도 자기 TASK 행·후속 작업 항목·갱신 날짜의 최소 기록을
  허용하지만, **§3.4는 그 예외를 쓸 때 직렬화 순서를 따르도록 요구**한다.
- 현재 PR #11이 `STATUS.md`를 소유·수정 중이므로, 지금 같은 파일에 행을 추가하면
  **R9(두 세션이 같은 파일을 동시에 수정하지 않는다)를 위반**하고 조용한 덮어쓰기를 만든다.
- 대상 TASK-003 자신도 같은 이유로 `STATUS.md` 통합을 유예했고(REVIEW-010 §4-5가 그 판단을
  지지함), 이 재검토가 그 판단을 뒤집을 근거를 찾지 못했다.

**따라서 TASK-020·REVIEW-011의 상태는 이 두 파일과 Draft 리뷰 PR에만 기록한다.**
`STATUS.md` 통합은 **PR #11 처리 후** 직렬화 순서가 열렸을 때 수행할 후속 작업이다
(REVIEW-011 §9 "후속 작업 후보"에 기록).

## 3. 범위

- REVIEW-010 M-01~M-05 각각의 해소 여부를 **직접 실행·직접 열람**으로 판정
- M-01의 SRT 바이트 규약·해시·raw/canonical 비교·음성 테스트 5건 실측 재현
- M-02의 staging 가드 3케이스 독립 실행과 파일시스템 결과 관측
- M-03·M-05의 공식 1차 원문 직접 접근 시도와 접근 실패 기록
- M-04의 Owner 정합성을 저장소 근거만으로 확정 가능한지 판정
- PR #13 절차 이탈 기록의 사실성 — endpoint 응답·commit ancestry·blob 동일성 대조
- 수정 구역과 직접 연결된 §4·§6·§8·§9·§11의 제한적 정합성 검사
- code fence 균형 · 상대 링크 · U-06/U-07/U-22/U-31 · ADR-0018 참조 실재
- Phase 0 위생(코드·의존성·CI·모델·데이터셋·비밀정보) 위반 여부
- PR #12 본문 주장과 실제 diff·GitHub 상태의 일치 여부

## 4. 범위 밖

- **연구 결론 전체의 처음부터 재검토** — `AGENTS.md` §4.1 6단계는 필요한 항목만 재검토한다
- 라이선스 법률 자문 또는 CHiME-6·Sintel의 법적 결론 확정
- U-06·U-07·U-22·U-31 해소, 모델·공급자·서비스·API·downloader 선택
- 대상 문서(`docs/SEED_CORPUS_RESEARCH.md`)·TASK-003·TASK-019·REVIEW-010의 수정 —
  리뷰어는 지적만 한다 (`AGENTS.md` §3.3)
- 대상 브랜치 push, PR #12·#13 수정, 어떤 PR의 병합·닫기·Ready 전환
- `main`·기존 브랜치 변경, force-push·reset·rebase·amend·history rewrite
- PR #13을 되살리기 위한 이력 재작성 요구
- TASK-003의 `Done` 전환
- `STATUS.md` 수정 (§2.2의 직렬화 유예)
- 실제 iCloud 쓰기, 대용량 데이터셋 다운로드
- 범위 밖 결함의 즉석 수정 — REVIEW-011 §9 "후속 작업 후보"에만 기록

## 5. 산출물

- `docs/tasks/TASK-020.md` (이 파일)
- `docs/reviews/REVIEW-011.md`

**이 두 파일 외에는 어떤 파일도 생성·수정하지 않는다.**

## 6. 완료 조건

- [x] 고정 HEAD·tree·4개 blob·비교 기준 main이 지시값과 일치함을 확인한다.
- [x] `5b465a1043…`의 직접 부모가 `6399e22249…`임을 확인한다.
- [x] PR #12가 Open/Draft/미병합이고 4파일·5커밋·+1281/−0임을 확인한다.
- [x] 수정 커밋 단독 diff가 2파일 +328/−44임을 확인한다.
- [x] TASK-020·REVIEW-011 번호가 어디에도 사용·예약되지 않았음을 확인한다.
- [x] 고정 HEAD에서 리뷰 브랜치를 만든다.
- [x] M-01을 깨끗한 임시 디렉터리에서 문서 명령 그대로 실행해 실측한다 (2회 생성 포함).
- [x] SRT 98 bytes·BOM·개행·EOF·trailing space를 직접 검사한다.
- [x] raw/canonical 비교와 음성 테스트 5건을 직접 실행한다.
- [x] canonicalization 허용 차이 5종이 실제로 허용되는지 직접 실행한다.
- [x] M-02의 3케이스를 독립 실행해 exit code와 파일시스템 결과를 관측한다.
- [x] M-03·M-05의 공식 1차 페이지 직접 접근을 시도하고 결과를 기록한다.
- [x] M-04를 저장소 근거만으로 확정 가능한지 판정한다.
- [x] PR #13의 state·merged·merged_at·merge_commit_sha·ancestry를 대조한다.
- [x] endpoint 간 `merged` 값 불일치를 조용히 선택하지 않고 전부 기록한다.
- [x] commit status·check run·workflow run 유무를 확인한다.
- [x] 제한된 정합성·위생 검사를 수행한다.
- [x] M-01~M-05 각각에 판정·근거·명령/URL·기대값·실측값·잔여 위험·필요 조건을 기록한다.
- [x] 확인하지 못한 항목을 추정하지 않고 분리해 기록한다.
- [x] 대상 브랜치·PR #10·#11·#12·#13·`main`을 변경하지 않았음을 사후 확인한다.

## 7. 검증 기록

- **실행 환경:** `ffmpeg` / `ffprobe` **6.1.1-3ubuntu5** (dpkg `7:6.1.1-3ubuntu5`),
  `LC_ALL=C`, GNU coreutils `sha256sum`·`printf`·`od`·`wc`, GNU `sed`·`awk`·`diff`·`grep`.
  이 환경에는 `ffmpeg`이 사전 설치되어 있지 않아 `apt-get update && apt-get install -y ffmpeg`로
  설치했고, 설치된 build가 **문서 고정값과 동일**했다. 따라서 해시 대조를 환경 제약이 아니라
  **실측**으로 판단할 수 있었다.
- **실행 위치:** 매 실행마다 `mktemp -d`로 만든 **새 임시 디렉터리**. 문서 명령을 **문자 그대로**
  복사 실행했다.
- 실측 결과 전체는 [`REVIEW-011`](../reviews/REVIEW-011.md) §2~§4에 있다.
- **egress 제약:** `durian.blender.org` · `openslr.org` / `www.openslr.org` ·
  `chimechallenge.github.io` · `www.chimechallenge.org` · `creativecommons.org` · `ffmpeg.org`는
  이 세션에서도 `403 CONNECT tunnel failed`로 차단됐다 (확인 시각 2026-08-12).
  **따라서 M-03·M-05는 `차단`으로 남긴다.** 검색 스니펫을 1차 확인으로 대체하지 않았다.
- `main`·대상 브랜치·PR #10·#11·#12·#13을 변경하지 않았다. 사후 확인은 REVIEW-011 §11에 있다.

### 7.1 브랜치 명명 — 규칙 준수 확인

`AGENTS.md` §4는 독립 리뷰 세션의 브랜치를 `claude-review/…`로 정한다. 이 TASK는
**`claude-review/task-020-task-003-followup`** 을 사용했고 push가 허용됐으므로 **명명 규칙 이탈이
없다.** (실행 환경이 기본 지정한 작업 브랜치는 `claude/task-003-independent-review-8aet58`이었으나,
재검토 지시가 `claude-review/…` 브랜치를 명시했고 그 이름이 §4와 일치하므로 그대로 사용했다.
TASK-019 §9가 기록한 접두사 이탈은 이번에는 발생하지 않았다.)

브랜치는 `AGENTS.md` §4 규칙 1의 단서대로 **`main`이 아니라 리뷰 대상 브랜치의 고정 HEAD
`5b465a1043cfa957a24ddbb43eadefe762ad3888`에서 분기**했다.

## 8. 인계 메모

- **최종 판정은 [`REVIEW-011`](../reviews/REVIEW-011.md) §10에 있다.**
- `승인`이든 아니든 **병합이나 `Done`을 뜻하지 않는다.** PR #12와 TASK-003은 계속
  사람 제품 오너의 판단을 기다린다 (`AGENTS.md` R1 / §6 / ADR-0009).
- **PR #13의 최종 처분은 이 리뷰가 결정하지 않는다.** 절차 이탈의 사실성만 판정했고,
  수용 여부·복구 여부는 사람 제품 오너의 몫으로 남긴다. 이 리뷰는 PR #13을 되살리기 위한
  force-push·history rewrite를 **요구하지 않는다.**
- **역사적 절차 이탈의 존재와 현재의 M-01~M-05 기술 판정은 분리해서 읽어야 한다.**
  이탈 기록이 정확하다는 사실만으로 대상 문서 내용을 다시 바꾸라고 요구하지 않았다.
- `STATUS.md` 통합은 PR #11 처리 후 직렬화 순서가 열렸을 때 수행한다 (§2.2).
- 이 세션은 대상 문서를 고치지 않았다. M-01·M-02의 잔여 결함은 **Source Owner가 대상
  브랜치에서** 수정한다.
