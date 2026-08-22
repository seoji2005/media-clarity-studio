# TASK-021 — TASK-003 Gate S 최종 로컬 제한 재검토

| 항목 | 값 |
|---|---|
| **ID** | TASK-021 |
| **Owner (수행 소유)** | **독립 Claude Code 리뷰 세션** — `AGENTS.md` §3 역할 3 |
| **Reviewer** | **없음 (§3.2)** — 이 TASK의 산출물은 리뷰 보고서 자체(`REVIEW-012.md`)이므로 재귀적 리뷰를 만들지 않는다 |
| **Phase** | Phase 1a / TASK-003 제한 재검토 |
| **Status** | `In review` |
| **재검토 대상 PR** | `#12` (Open / Draft / 미병합) |
| **재검토 대상 브랜치** | `claude/task-003-seed-corpus-research-gptw-0812` |
| **고정 대상 HEAD** | `286b96032a84cfa46a1dff489ce590079e28629c` |
| **고정 대상 tree** | `686bc67852739832b771fbc9fed204d823ab7153` |
| **고정 대상 HEAD의 직접 부모** | `62bd6070596a3cf93ff9504dad86da03305b8273` (부모 1개) |
| **비교 기준 `main`** | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| **고정 blob — 조사 문서** | `8522777f543ae8e9089243de444280bc8ca37b8d` (`docs/SEED_CORPUS_RESEARCH.md`) |
| **고정 blob — TASK-003** | `b5526edf93c69d20e89f631b24bcb192c923be10` (`docs/tasks/TASK-003.md`) |
| **고정 blob — TASK-019** | `3081ac708aff60c4fe9c9d4199665b4db4464f5f` |
| **고정 blob — REVIEW-010** | `66c04cc977c97be4775a7520f33a41d750ead5df` |
| **고정 blob — TASK-020** | `a1e77cc81e3c7e561afb13b35a4e0eb60206fd38` |
| **고정 blob — REVIEW-011** | `ee04c6bef6ab2ebacef496888d6852071717c3e8` |
| **리뷰 브랜치** | `claude-review/task-021-task-003-final-rereview` |
| **차단 질문** | 없음 |

## 0. 역할과 세션 분리 (R8 / §3.1)

- 이 세션은 **TASK-003의 Source Owner가 아니며**, TASK-019·TASK-020을 수행한 세션도 아니다.
  새로 시작한 독립 Claude Code 리뷰 세션이다.
- **Source Owner의 대화 맥락이나 완료 보고를 증거로 쓰지 않았다.** 판단 근거는 다음 셋뿐이다:
  ① 고정 HEAD `286b9603…`의 저장소 파일, ② PR #12·#14의 GitHub 객체와 diff,
  ③ **이 세션에서 직접 실행한 명령의 실측 출력.**
- PR #12 comment `5267477354`("외부 검증 기록")도 **이 세션이 직접 확인한 사실이 아니다.**
  이 재검토는 그 comment의 진위를 판정하지 않는다 — F-01~F-03의 Gate S 재현성은
  **이 세션이 독립적으로 재실행**해 판정하며, M-03·M-05의 사실관계는 범위 밖이다 (§2).

## 1. 목표

REVIEW-011이 지목한 F-01·F-02·F-03 수정이 고정 HEAD `286b9603…`에서 실제로 해소됐는지를
**이 저장소의 로컬 실행 환경만으로** 판정하고, Gate S/Gate E 분리 서술이 정직하고 무모순인지
문서 감사로 확인한다. 통과하면 사람 제품 오너가 별도 코드 TASK에서 합성 media plumbing
vertical slice 구현에 착수할 수 있다.

**egress는 이 재검토의 사전 게이트가 아니다.** 외부 URL 접근 여부는 검사하지 않는다.

## 2. 검토 범위 — 닫힌 목록

**포함:**

1. **F-01** — `docs/SEED_CORPUS_RESEARCH.md` §7.1.1 자체 검사 블록의 98-byte 주석과
   관련 절(§7.4, §7.4.1, §7.5, §8)의 정합성
2. **F-02** — staging 명령이 `( set -eu; … )` 서브셸 한 단위로 정의되고 실제로 그렇게
   동작하는지, 네 실행 방식(`bash -c`, bash script, `dash -c`, interactive bash paste) 각각에서
3. **F-03** — 실패 종료가 특정 exit code(`exit 2`)로 고정되지 않고 non-zero/zero 규범과
   셸별 실측이 분리되어 있는지
4. **Gate S / Gate E 분리 서술의 정직성과 무모순성**
5. **외부 출처를 확인했다고 과장하는 현재 상태 문구의 유무** — 역사 기록과 현재 주장을 구분

**명시적으로 범위 밖 (판정하지 않음):**

- **M-03·M-05의 사실관계** — OpenSLR·CHiME·Creative Commons·Durian 공식 원문의 진위.
  Gate E로 유예된 항목이며, 이 저장소의 Reviewer 환경은 egress proxy의 CONNECT allowlist
  정책으로 1차 원문을 열 수 없다. 원문을 열지 못한 상태에서 사실관계를 판정하지 않는다.
- **PR #13의 최종 처분** — 역사적 절차 이탈 기록의 존재는 확인하되(§9), 처분은 사람 제품
  오너의 판단으로 남긴다.
- U-06·U-07·U-22·U-31의 해결, 외부 코퍼스 선택·다운로드, 실제 코드 구현, PR #12 병합 여부,
  TASK-003 전체를 `Done`으로 전환하는 결정.

**범위 밖 항목은 Gate S 승인 거부 사유로 쓰지 않는다.**

## 3. 로컬 재현 시험 계획

- **F-01:** 깨끗한 `mktemp -d`에서 §7.1.1의 `printf` 명령을 문자 그대로 실행해 `fixture.srt`를
  만들고, `wc -c`·`od`·`sha256sum`으로 실측해 문서 주석·규약·§7.4.1 대조표와 대조한다.
- **F-02·F-03:** §7.3의 서브셸 블록을 그대로 사용해 `bash -c`, bash script, `dash -c`,
  실제 interactive bash paste(pty) 네 방식 각각에서 unset·empty·valid 세 경우를 시험한다.
  시험 전 `/fixture-softsub.mkv` 부재를 확인하고, 존재하면 출처를 알 수 없으므로 삭제하지 않고
  중단한다. 실제 iCloud는 사용하지 않고 valid 값은 `mktemp -d` 경로만 쓴다.
- **M-01 회귀 확인 (제한):** 동일 build FFmpeg `6.1.1-3ubuntu5`로 §7.2·§7.3 전체를 2회 실행해
  source·SRT·soft-sub의 byte-identical 여부, raw/canonical 비교, 음성 테스트 5건, 위반형 97-byte
  해시를 재확인한다. 연구 전체를 처음부터 재검토하지 않는다.
- **Gate S/E 문서 감사:** §6.1의 문구를 grep으로 전수 검색해 문맥별(역사 기록 vs 현재 상태 주장)로
  분류하고, 과장 표현이 남아 있는지 판정한다.
- **제한된 정합성 검사:** 수정 커밋 `286b9603…`의 두 파일, F-01~F-03 직결 구역, M-03/M-05 관련
  구역(§3.6, §3.2.1, §4, §6, §9, §11), TASK-003 최신 이력, 4개 보존 blob 불변, code fence,
  상대 링크, U-XX·ADR-0018 참조, 금지 용어, Phase 0 위생, PR #12 본문과 실제 상태 일치.

## 4. 판정 규칙

REVIEW-012의 최종 판정은 다음 중 하나다.

- **승인 — Gate S 한정:** F-01~F-03이 직접 실행으로 완전히 해소되고, M-01 재현성에 회귀가
  없으며, Gate S/E 분리가 정직·무모순이고, 외부 검증 지위를 과장하는 현재 문구가 없고, 새
  차단 결함이 없을 때. 판정문은 이 승인이 Gate S 한정이며 M-03·M-05·Gate E·전체 TASK-003·
  PR 병합·`Done` 전환을 승인하지 않는다는 문장을 반드시 포함한다.
- **변경 요청:** F-01~F-03 중 하나라도 재현 실패, 또는 Gate S 범위 안에서 Source Owner가
  현재 문서에서 고칠 수 있는 재현 가능한 결함이 있을 때.
- **차단:** 사전 게이트는 통과했지만 검토 도중 예상하지 못한 로컬 환경 문제로 판정을 완료할
  수 없을 때만. Gate E의 egress 차단은 이 재검토의 차단 사유가 아니다.

## 5. `STATUS.md` 직렬화 유예

**이 TASK는 `STATUS.md`를 수정하지 않는다.** PR #11(TASK-018)이 Open 상태로 `STATUS.md`를
계속 소유 중인 coordination point다 (`git diff --stat origin/main origin/claude/task-018-post-merge-state-reconcile-gptw-0812 -- STATUS.md`로 재확인 — 38 insertions, 22 deletions,
diff 존재). `AGENTS.md` R9 / §3.4에 따라 같은 파일을 동시에 수정하지 않기 위해 직렬화를
우선하며, `STATUS.md` 통합은 PR #11 처리 후 최신 `main`에서 별도로 수행할 후속 작업이다.

## 6. 산출물

- `docs/tasks/TASK-021.md` (이 파일)
- `docs/reviews/REVIEW-012.md`

이 두 파일 외에는 어떤 저장소 파일도 생성·수정하지 않는다. 대상 브랜치·PR #12·PR #14·
`main`·기존 리뷰 브랜치는 변경하지 않는다.

## 7. 완료 조건

- [x] §2의 고정 HEAD/tree/부모/blob 6종과 PR #12/#11/#13/#14 상태를 GitHub 객체·git 객체로
      독립 재계산해 지시값과 일치함을 확인한다.
- [x] TASK-021·REVIEW-012 번호와 관련 파일명·브랜치명이 원격 전체에서 미사용임을 확인한다.
- [x] F-01을 직접 실행으로 재현한다. — **해소** (REVIEW-012 §3)
- [x] F-02·F-03을 네 실행 방식 × 세 경우로 직접 재현한다. — **둘 다 해소** (REVIEW-012 §4~§5)
- [x] M-01 핵심 재현성에 회귀가 없음을 제한 확인한다. — 회귀 없음 (REVIEW-012 §6)
- [x] Gate S/E 분리와 과장 표현 감사를 수행한다. — 모순·과장 없음 (REVIEW-012 §9~§10)
- [x] 제한된 정합성 검사를 수행한다. — 새 차단 결함 없음 (REVIEW-012 §9, §12)
- [x] REVIEW-012에 최종 판정과 근거를 기록한다. — **승인 — Gate S 한정**
- [ ] Draft 리뷰 PR을 생성한다.

## 9. 완료 기록

**최종 판정: 승인 — Gate S 한정.** 근거와 전체 재현 결과는 [`REVIEW-012`](../reviews/REVIEW-012.md)에
있다. 이 판정은 M-03·M-05·Gate E·PR #12 병합·TASK-003 `Done` 전환을 승인하지 않는다.

## 8. 인계 메모

최종 판정은 [`REVIEW-012`](../reviews/REVIEW-012.md)에 있다. `승인 — Gate S 한정`이라도
병합이나 TASK-003 `Done`을 뜻하지 않는다. M-03·M-05의 사실관계와 PR #13의 최종 처분은
계속 사람 제품 오너의 판단을 기다린다.
