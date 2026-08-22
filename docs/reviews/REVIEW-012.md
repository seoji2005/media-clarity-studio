# REVIEW-012 — TASK-003 Gate S 최종 로컬 제한 재검토

| 항목 | 값 |
|---|---|
| **수행 TASK** | [`TASK-021`](../tasks/TASK-021.md) |
| **리뷰어** | 독립 Claude Code 리뷰 세션 (`AGENTS.md` §3 역할 3) — **Source Owner 아님, 이전 라운드 세션도 아님** |
| **대상 PR** | `#12` — Open / Draft / 미병합 |
| **대상 브랜치** | `claude/task-003-seed-corpus-research-gptw-0812` |
| **고정 대상 HEAD** | `286b96032a84cfa46a1dff489ce590079e28629c` |
| **고정 대상 tree** | `686bc67852739832b771fbc9fed204d823ab7153` |
| **고정 대상 HEAD의 직접 부모** | `62bd6070596a3cf93ff9504dad86da03305b8273` (부모 1개) |
| **비교 기준 `main`** | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| **재검토 범위** | F-01·F-02·F-03 + Gate S/Gate E 분리의 정직성 |
| **명시적 제외 범위** | M-03·M-05의 사실관계, PR #13의 최종 처분, U-06/U-07/U-22/U-31 결정, 실제 코드 구현, PR #12 병합, TASK-003 `Done` 전환 |
| **최종 판정** | **승인 — Gate S 한정** (§12) |
| 확인일 | 2026-08-22 |

> **이 승인은 Gate S 한정이다.** M-03·M-05, Gate E, 외부 코퍼스 라이선스, TASK-003 전체,
> PR #12 병합 및 `Done` 전환을 승인하지 않는다. 사람 제품 오너는 이 판정을 근거로 별도 신규
> TASK에서 합성 media plumbing vertical slice 코드 착수를 결정할 수 있다.

---

## 1. 고정 HEAD/tree/부모/blob 대조표

**모든 값이 지시값과 일치했다.** git 객체와 GitHub API에서 독립적으로 재계산했다.

| 항목 | 지시값 | 실측값 | 판정 |
|---|---|---|---|
| head | `286b96032a84cfa46a1dff489ce590079e28629c` | `git rev-parse origin/claude/task-003-seed-corpus-research-gptw-0812` → 동일 | **일치** |
| tree | `686bc67852739832b771fbc9fed204d823ab7153` | `git rev-parse …^{tree}` → 동일 | **일치** |
| 직접 부모 | `62bd6070596a3cf93ff9504dad86da03305b8273` | `git rev-list --parents -n1` → 부모 1개, 동일 | **일치** |
| 기준 `main` | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` | 동일 | **일치** |
| blob — 조사 문서 | `8522777f543ae8e9089243de444280bc8ca37b8d` | 동일 | **일치** |
| blob — TASK-003 | `b5526edf93c69d20e89f631b24bcb192c923be10` | 동일 | **일치** |
| blob — TASK-019 | `3081ac708aff60c4fe9c9d4199665b4db4464f5f` | 동일 | **일치** |
| blob — REVIEW-010 | `66c04cc977c97be4775a7520f33a41d750ead5df` | 동일 | **일치** |
| blob — TASK-020 | `a1e77cc81e3c7e561afb13b35a4e0eb60206fd38` | 동일 | **일치** |
| blob — REVIEW-011 | `ee04c6bef6ab2ebacef496888d6852071717c3e8` | 동일 | **일치** |
| PR #12 전체 | 9커밋·6파일·+2751/−0 | GitHub API: `commits=9, changed_files=6, additions=2751, deletions=0` | **일치** |
| 최신 커밋 제목 | `docs: split external-source review from synthetic slice` | `git log -1 --format=%s` → 동일 | **일치** |
| 커밋 9 단독 diff | (문서 주장) SEED +253/−89, TASK-003 +136/−2 | `git diff --numstat 62bd607.. 286b960..` → 정확히 동일 | **일치** |

**PR 상태 (종료 시에도 재확인, §11):**

| PR | 지시값 | 실측값 | 판정 |
|---|---|---|---|
| #12 | Open/Draft/미병합, base main | `state=open, draft=true, merged=false`, base `main`@`10d34b4a…` | **일치** |
| #11 | Open/Draft/미병합, head `da161f86…` | 동일. `STATUS.md` 여전히 +38/−22 diff 보유 | **일치** |
| #13 | Closed/Merged, head `6399e222…` | `state=closed, merged=true, merge_commit_sha=6399e222…` | **일치** |
| #14 | Open/Draft/미병합, head `36a7a3a1…` | 동일. `merge-base --is-ancestor 36a7a3a1… 286b9603…` → **NO** (조상 아님) | **일치** |

**번호·파일·브랜치 미사용 확인:** 원격 전체 15개 ref에서 `git grep -E '\bTASK-021\b|\bREVIEW-012\b'`
결과, 실제 파일 `docs/tasks/TASK-021.md`·`docs/reviews/REVIEW-012.md`는 **어디에도 없었다.**
`docs/SEED_CORPUS_RESEARCH.md`·`docs/tasks/TASK-003.md` 본문에 "다음 Reviewer는 TASK-021/
REVIEW-012"라는 **전방 참조 문구**가 있으나, 이는 실제 파일·브랜치·`STATUS.md` §4 예약이
아니므로 사용·예약으로 보지 않았다. `claude-review/task-021-task-003-final-rereview` 브랜치도
원격에 없었다.

**로컬 실행 환경:** `bash`·`dash`·`mktemp`·`sha256sum`·`ffmpeg`·`ffprobe` 전부 존재.
`ffmpeg -version` → `6.1.1-3ubuntu5`, `dpkg -s ffmpeg` → `7:6.1.1-3ubuntu5` — **문서 고정값과
동일 build.**

**작업 checkout:** 브랜치 생성 직전 `git status --short` **clean.**

---

## 2. 검토 범위와 명시적 제외 범위

**포함:** F-01, F-02, F-03, M-01 핵심 재현성의 제한적 회귀 확인, Gate S/E 분리의 정직성,
외부 검증 지위를 과장하는 현재 문구의 유무, 제한된 정합성·위생 검사.

**명시적으로 판정하지 않은 것:**

- **M-03·M-05의 사실관계.** OpenSLR·CHiME·Creative Commons·Durian 공식 원문에 이 세션은
  접근하지 않았다 (egress는 이번 사전 게이트가 아니었고, 지시서 §8도 이를 요구하지 않았다).
  이 문서가 그 원문을 정확히 서술하는지는 **판정 대상이 아니다.**
- **PR #13의 최종 처분** — 역사적 절차 이탈 기록의 존재만 확인했고(§9), 처분은 사람 제품
  오너의 판단으로 남긴다.
- U-06·U-07·U-22·U-31의 해결, 외부 코퍼스 다운로드, 실제 코드 구현, PR #12 병합 여부,
  TASK-003 전체를 `Done`으로 전환하는 결정.

이 범위 밖 항목들은 아래 어떤 판정에서도 Gate S 승인을 거부하는 근거로 쓰지 않았다.

---

## 3. F-01 — SRT 크기 일관성

### 판정: **해소**

깨끗한 `mktemp -d`에서 §7.1.1의 `printf` 명령을 문자 그대로 실행했다.

| 항목 | 문서 기대값 | 실측값 | 판정 |
|---|---|---|---|
| `wc -c < fixture.srt` | `# 98` (§7.1.1 주석) | **98** | **일치 — F-01 반영 확인** |
| SHA-256 | `c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97` | 동일 | **일치** |
| EOF | `0a 0a` | `tail -c2 od` → ` 0a 0a` | **일치** |
| BOM | 없음 | `head -c3 od` → `31 0a 30` | **일치** |
| CR | 0개 | `grep -c $'\r'` → 0 | **일치** |
| trailing space | 0개 | `grep -nP '[ \t]+$'` → 출력 없음 | **일치** |
| 위반형(EOF `0a`만) 크기 | **97 bytes** (§7.4.1 표에 크기 열 추가됨) | **97** | **일치** |
| 위반형 SHA-256 | `9df382a65875ccfb1e055b219219d5eb3864751f79896b049f54952cb636c4d6` | 동일 | **일치** |

`# 96` 문자열을 조사 문서 전체(`docs/SEED_CORPUS_RESEARCH.md`)에서 검색한 결과 **0건.**
§7.1.1 주석은 `# 98`로 정정되어 있고, §7.4.1 대조표에 **크기 열(98/97 bytes)**이 새로 추가되어
`# 98` 주석·98-byte 규약·97-byte 위반형이 서로 모순 없이 대응한다. §7.4·§7.5·§8과도 숫자
불일치가 없었다.

**남은 위험:** 없음. **Source Owner 수정 조건:** 없음.

---

## 4. F-02 — staging 서브셸 실행 단위

### 판정: **해소**

§7.3의 서브셸 블록(`( set -eu; : "${VAR:?…}"; mkdir -p --; cp --; sha256sum )`)을 문자 그대로
사용해 네 실행 방식 × 세 경우, 총 12개 조합을 실행했다.

**시험 전:** `/fixture-softsub.mkv` 부재를 확인했다 (부재 — 시험 진행). 유효 값은 매번
`mktemp -d` 경로만 사용했고, 실제 iCloud는 쓰지 않았다.

| 실행 방식 | unset | empty | valid | `/fixture-softsub.mkv` (unset·empty 후) |
|---|---|---|---|---|
| `bash -c "$BLOCK"` | non-zero (**1**) | non-zero (**1**) | **0**, copy 생성·해시 일치 | **미생성** |
| bash script (`bash block.sh`) | non-zero (**1**) | non-zero (**1**) | **0**, copy 생성·해시 일치 | **미생성** |
| `dash -c "$BLOCK"` | non-zero (**2**) | non-zero (**2**) | **0**, copy 생성·해시 일치 | **미생성** |
| **interactive bash — 전체 `(…)` 블록 paste (pty, `script -qefc "bash -i"`)** | non-zero (**1**) | non-zero (**1**) | **0**, copy 생성·해시 일치 | **미생성** |

**interactive 모드의 세부 관측 (F-02의 핵심 재현 지점):**

- pty에서 여는 `(`을 입력하는 즉시 bash가 `PS2` 연속 프롬프트(`>`)를 표시했다 — **괄호 서브셸이
  한 단위로 파싱됨**을 실측으로 확인했다.
- unset·empty 두 경우 모두, `:?` 실패 메시지(`bash: MCS_ICLOUD_STAGING_DIR: set …`) 뒤에
  `mkdir: cannot create directory` 메시지가 **나타나지 않았다** — `set -eu`가 서브셸 안에서
  `mkdir`·`cp`·`sha256sum` 실행을 **막았다.**
- 세 경우(unset/empty/valid) 전부에서 `echo PARENT_ALIVE=yes`가 정상 출력됐다 —
  **부모 대화형 셸 생존.**
- `$-`로 측정한 셸 옵션은 `himBHs`로 **paste 전후 동일**했다 (`errexit`=`e`, `nounset`=`u`
  둘 다 문자열에 없음 — 애초에 꺼져 있었고 그 상태가 **불변**이었다).
- **파일시스템 무변경:** `/fixture-softsub.mkv`는 unset·empty 케이스 모두에서 **생성되지
  않았다.** 이것이 REVIEW-011이 지적한 원래 버그("대화형 셸에서 `cp`가 계속 실행되어
  `/fixture-softsub.mkv`가 실제로 생성됨")가 **재현되지 않음**을 뜻한다.

**valid 케이스 3종 모두** staging copy가 생성됐고 `sha256sum`이 원본과 정확히
`2f2eb1ba73813133af5c311e3329c1bd5bf445f1192451397bb83af267a623ed`로 일치했다.

**남은 위험:** 없음. **Source Owner 수정 조건:** 없음.

---

## 5. F-03 — non-zero/zero 규범과 셸별 실측 분리

### 판정: **해소**

§7.5.1의 규범 문구를 §7의 본문에서 대조했다. 문서는 다음을 명시한다.

- **규범:** unset/empty → non-zero, valid → zero. "**정확한 non-zero 값은 acceptance 기준이
  아니다** … 이전 판이 `exit 2`로 고정한 것은 dash에서만 성립하는 값이었다"
- **실측 표(§7.5.1):** `bash -c` 1/1/0, bash script 1/1/0, `dash -c` 2/2/0, interactive 1/1/0을
  **개별 셸의 관측값**으로만 제시하고 규범과 분리
- **핵심 판정 기준**을 종료 코드 숫자가 아니라 "① 파일시스템 변경이 없을 것 ② 후속 명령이
  실행되지 않을 것"로 명시

이 세션의 §4 실측표와 문서 §7.5.1의 실측표를 대조하면 **네 실행 방식 전부에서 exit code가
정확히 일치했다** (bash 1/1/0, dash 2/2/0). `exit 2`라는 문자열은 문서 전체에서 `grep -n
'exit 2'` 결과 **2곳뿐**이었고 — SEED_CORPUS_RESEARCH.md §7.5.1의 "이전 판이 `exit 2`로
고정한 것은 dash에서만 성립하는 값이었다"와 TASK-003.md의 F-03 반영 요약 행 — **둘 다 이전
판을 비판하는 역사적 문맥이며, 현재 acceptance 기준으로 쓰이지 않았다.** 셸에 따라 값이
다르다는 서술이 실제 동작과 일치했다.

**남은 위험:** 없음. **Source Owner 수정 조건:** 없음.

---

## 6. 두 번 생성한 해시·크기·stream·duration·probe 결과 (M-01 핵심 재현성 회귀 확인)

동일 build FFmpeg `6.1.1-3ubuntu5`로 §7.2·§7.3 전체를 서로 다른 `mktemp -d`에서 2회 독립
실행했다. 연구 전체를 재검토하지 않고 F 수정이 기존 재현성을 깨지 않았는지만 확인했다.

| 산출물 | SHA-256 | 크기 | 2회 결과 |
|---|---|---|---|
| `fixture.srt` | `c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97` | 98 | **byte-identical** |
| `fixture-source.mkv` | `3bd1180d5445839baf32643e7f78be15d4818c14f1d0152e79a57377919ce37b` | 3,635,787 | **byte-identical** |
| `fixture-softsub.mkv` | `2f2eb1ba73813133af5c311e3329c1bd5bf445f1192451397bb83af267a623ed` | 3,636,043 | **byte-identical** |
| `fixture-extracted.srt` | SRT와 동일 (`c2ed5960…`) | 98 | 입력과 동일 |

**모두 지시된 기대값과 정확히 일치했다.**

| 확인 | 결과 |
|---|---|
| video codec | `ffv1` |
| audio codec | `pcm_s16le`, 48000 Hz, mono (1채널) |
| subtitle codec | `subrip` |
| duration | `6.000000` |
| probe score | `100` |
| raw 검증 (`diff -u fixture.srt fixture-extracted.srt`) | **통과** |
| canonical 검증 (`srt-canon.sh` 출력 `diff`) | **통과**, cue 2건 번호·시각·텍스트 일치 |
| 음성 테스트 5건 (시작시각/종료시각/텍스트/cue번호/cue삭제) | **전부 검출** |
| 97-byte 위반형 | raw **실패**, canonical **통과** — §7.4.1 표와 일치 |

**회귀 없음.** F-01~F-03 반영 이후에도 M-01의 핵심 재현성은 그대로 유지된다.

---

## 7. `/fixture-softsub.mkv` 및 루트 무변경 확인

- 시험 착수 전 `/fixture-softsub.mkv` **부재**를 확인했다.
- unset·empty 12케이스(4방식×2경우×해시확인 포함 검증) 전부에서 **생성되지 않았다.**
- valid 케이스에서 생성된 파일은 매번 `mktemp -d` 경로 안이었고, `/`(파일시스템 루트)에는
  아무것도 만들어지지 않았다.
- 시험 종료 후 재확인 결과 `/fixture-softsub.mkv`는 **부재**로 유지됐다 (M-01 재현 파이프라인이
  루트가 아닌 `mktemp -d` 안에서만 실행됐으므로 애초에 루트에 아무것도 만들지 않았다).

---

## 8. interactive 부모 셸 생존과 shell option 불변 확인

pty(`script -qefc "bash -i"`)로 실제 interactive bash를 띄우고 전체 `(…)` 블록을 붙여넣기
형태로 주입했다.

| 케이스 | 부모 셸 생존 | `$-` (paste 전) | `$-` (paste 후) | 불변 |
|---|---|---|---|---|
| unset | **예** — 이후 명령 계속 처리 | `himBHs` | `himBHs` | **예** |
| empty | **예** | `himBHs` | `himBHs` | **예** |
| valid | **예** | `himBHs` | `himBHs` | **예** |

`e`(errexit)·`u`(nounset) 문자는 세 경우 모두 `$-` 문자열에 **나타나지 않았다** — 서브셸
안의 `set -eu`가 부모로 누출되지 않았다는 뜻이다.

---

## 9. Gate S/Gate E 문서 정합성 대조표

수정 커밋 `286b9603…`(§ Gate S/E 분리 정정)와 그 결과물인 `docs/SEED_CORPUS_RESEARCH.md`·
`docs/tasks/TASK-003.md`에서 다음 주장을 대조했다.

| 지시서 §7의 확인 항목 | 문서에서의 실제 서술 | 판정 |
|---|---|---|
| Gate S는 외부 저작물·계정·네트워크·모델·API에 의존하지 않는 합성 fixture 기술 게이트다 | §1.1, §7.5.2 인용문, §8 대조표 "외부 의존 — 없음"이 반복 명시 | **일치** |
| Gate S 통과는 합성 media plumbing 코드 착수만 허용한다 | §8 "통과하면 — 합성 vertical slice 코드 착수가 허용된다", TASK-003 §C 허용/제외 닫힌 목록 | **일치** |
| Gate E는 외부 출처 독립 검증과 외부 코퍼스 채택·다운로드·재배포의 선행 조건이다 | TASK-003 §B 표 "코드 착수와의 관계 — Gate E는 코드 착수의 선행 조건이 아니다. 외부 코퍼스 채택의 선행 조건이다" | **일치** |
| M-03은 "외부 검증이 확인했다고 보고했고 Source Owner가 반영함"이지 독립 Reviewer 확인·해소·승인이 아니다 | §3.6.2 지위 박스 "외부 검증에서 확인됐다고 보고 … Source Owner가 그 증거를 반영 … 독립 Reviewer가 원문을 직접 확인한 최종 판정(REVIEW-012)이 아니다" | **일치, 정확히 이 표현** |
| M-05는 Durian 원문 미확인 상태다 | §3.2.1 "여전히 확인하지 못한 것 (M-05)" 박스, §11 Durian 3개 링크 전부 `[차단]` | **일치** |
| Gate E 완료 전 CHiME-6 미채택, Sintel 미사용, 외부 코퍼스 미다운로드 유지 | §B "Gate E가 끝나기 전까지 지키는 것" 목록에 세 항목 전부 명시, §3.2·§3.6.4·§4·§9에서 반복 | **일치** |
| Gate S 승인은 전체 TASK-003 승인·라이선스 승인·PR 병합·`Done` 전환을 뜻하지 않는다 | TASK-003 §D "Gate S 승인은 전체 연구의 승인도, 라이선스 승인도, `Done` 전환도, PR #12 병합도 아니다. 병합과 최종 처분은 사람 제품 오너만 결정한다" | **일치** |
| TASK-005·006 이전 코드 착수는 좁은 예외이며 외부 코퍼스·ASR·번역·모델·공급자 선택을 포함하지 않는다 | §C 인용 박스 + 허용/제외 닫힌 목록(외부 코퍼스·downloader·ASR·번역·모델·API·공급자·hard-sub·실제 iCloud API·GUI·시각 재구성 전부 제외) | **일치** |
| `PLAN.md`는 폐기·변경되지 않았고 PR #11 처리 후 별도 정합성 작업 필요가 숨겨지지 않았다 | `git diff --stat main branch -- PLAN.md` → **diff 없음** (실측 확인). §E "PLAN.md 수정 안 함 — 실행 순서의 최종 정합성은 PR #11 처리 후 별도 TASK로 반영" | **일치** |

**모순 없음.** 위 여덟 항목 모두 문서 서술과 실제 diff·git 상태가 부합했다.

---

## 10. 과장 가능 표현 검색 결과와 문맥 분류

`docs/SEED_CORPUS_RESEARCH.md`·`docs/tasks/TASK-003.md` 전체에서 지시된 8개 표현을 검색했다.

| 검색어 | 총 등장 | 현재-효력으로 읽히는 무조건적 사용 |
|---|---|---|
| `M-03 해소` | 0 | — |
| `blocker 해소` | 1 (부정문 "…아니다"에만) | **없음** |
| `라이선스 blocker는 없다` | 0 | — |
| `1차 확인 완료` | 0 | — |
| `직접 확인 완료` | 0 | — |
| `독립 검증 완료` | 0 | — |
| `승인` | 28회 | **없음** — 전부 "…아니다/승인하지 않는다/자기 승인이 아니다/승인은 …을 뜻하지 않는다" 형태의 부정·한정문. 긍정형으로 쓰인 "Gate S 제한 리뷰 **승인**"·"Gate S가 **승인되면**" 계열은 **이 REVIEW-012가 내리는 판정 그 자체**(미래 시점의 조건문)를 가리키므로 M-03·M-05나 과거 사실에 대한 과장이 아니다 |
| `확정` | 12회 | **없음** — "…확정이 아니다"가 8회, 나머지는 "첫 fixture 부적합 — 라이선스와 무관하게 확정"(E1~E5의 공학적 제외 판정, 라이선스와 독립적임을 스스로 명시)과 "M-01을 실측으로 확정한 선례"(Gate S 범위 내 재현 가능한 사실에 대한 서술)로, 둘 다 M-03·M-05의 사실관계 확정을 주장하지 않는다 |
| `해소` | 다수 | F-01~F-03에 대해서만 "해소 확인"(§7.5.2, "외부 검증의 독립 재현" 절 — 외부 검증 결과로 귀속되며, 같은 절 말미가 "이 기록은 새 독립 Reviewer의 승인이 아니다 … 공식 판정은 다음 독립 재검토에서 이루어진다"로 즉시 한정). M-03·M-05에는 "해소"가 전부 부정문으로만 등장 |

**역사 기록과 현재 상태 주장의 구분:** 2026-08-12 `403 CONNECT tunnel failed` 관측(§3.2.1·
§3.6.2·§11)은 삭제되지 않고 "역사 기록 (삭제하지 않음)"으로 명시적으로 표시되어 있으며,
그 옆에 "이후 egress가 허용된 별도 환경의 외부 검증"이라는 **시점 구분 문구**가 항상 따라온다.
`[외부검증]`·`[차단]` 두 표기 모두 §11 범례에서 "**어느 표기도 Gate S의 통과 조건이 아니다.
이 목록 전체가 Gate E의 대상이다**"로 마무리되어, 현재 상태 표가 확인된 사실을 부풀리지 않고
있음을 확인했다.

**결론: 외부 검증 지위를 독립 Reviewer 판정으로 격상하는 과장 표현을 찾지 못했다.**

---

## 11. 대상 브랜치와 기존 ref의 사후 불변 확인

| 대상 | 재확인 결과 |
|---|---|
| `main` | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` — **불변** |
| 대상 브랜치 `claude/task-003-seed-corpus-research-gptw-0812` | `286b96032a84cfa46a1dff489ce590079e28629c` — **push 없음, 불변** |
| PR #10 | 상태 변경 없음 |
| PR #11 | Open/Draft/미병합, head `da161f86…` — **불변** |
| PR #12 | 본문·상태·label 변경 없음 — **읽기만 함** |
| PR #13 | Closed/Merged 유지 — **읽기만 함, 쓰기 없음** |
| PR #14 | Open/Draft/미병합, head `36a7a3a1…` — **불변**. `merge-base --is-ancestor` 재확인 결과도 여전히 **NO** |
| 기존 리뷰 브랜치(`claude-review/task-020-…` 등) | 수정하지 않음 |
| `docs/SEED_CORPUS_RESEARCH.md` · `docs/tasks/TASK-003.md` (대상 문서) | **수정하지 않음** |
| TASK-019 · TASK-020 · REVIEW-010 · REVIEW-011 | **수정하지 않음** (blob 4종 §1에서 재확인) |

---

## 12. 최종 판정

### **승인 — Gate S 한정**

**근거:**

- F-01·F-02·F-03이 이 세션의 독립 실행으로 **완전히 재현·해소 확인**됐다 (§3~§5).
- 고정 해시·크기·stream·duration·probe 결과가 지시값과 **정확히 일치**했고, 2회 생성이
  byte-identical했다 (§6). **M-01 핵심 재현성에 회귀 없음.**
- 네 실행 방식 × 세 경우, 총 12개 조합에서 staging 서브셸이 규범대로 동작했다 — 특히
  REVIEW-011이 지적한 대화형 셸 부작용(`/fixture-softsub.mkv` 실제 생성)이 **재현되지
  않았다** (§4, §7).
- interactive 부모 셸이 매 케이스 생존했고 `errexit`·`nounset` 옵션이 **불변**이었다 (§8).
- Gate S/Gate E 분리 서술 8개 항목이 실제 diff·git 상태와 **모순 없이 일치**했다 (§9).
- 과장 가능 표현 8종을 전수 검색한 결과 외부 검증 지위를 독립 Reviewer 판정으로 격상하는
  현재-상태 문구를 **찾지 못했다** (§10).
- 제한된 정합성 검사(§1의 blob 4종 불변, code fence 20행=10쌍, 상대 링크 12개 전수 실재,
  U-06/U-07/U-22/U-31/ADR-0018 참조 실재, 추가된 줄의 금지 용어 0건, 변경 파일 `.md` 2개뿐,
  `.github/` 트리 없음, commit status/check run/workflow run 전부 0)에서 **새 차단 결함을
  찾지 못했다.**
- PR #12 본문의 diff 수치 주장(커밋 9 단독 +253/−89·+136/−2, 전체 +2751/−0·6파일·9커밋,
  최신 커밋 제목)이 실제 git 객체와 **정확히 일치**했다.

**Gate E와 PR #13은 이 REVIEW-012가 판정하지 않았다.** M-03·M-05의 공식 원문 사실관계는
egress가 허용된 별도 검증 환경을 필요로 하며, 이 재검토는 그 환경에 접근하지 않았고 지시서도
접근을 요구하지 않았다. PR #13의 병합·종료 역사 기록은 §1에서 존재만 재확인했고 최종 처분은
판정하지 않았다.

**한 문장 결론:** F-01~F-03이 재현으로 확인되고 Gate S/E 분리가 정직하므로, **사람 제품
오너는 이 저장소에서 별도 신규 TASK를 열어 외부 코퍼스·ASR·번역·모델·API·공급자를 포함하지
않는 합성 media plumbing vertical slice의 코드 착수를 지금 결정할 수 있다.**

---

Gate S 한정 승인이므로, 사람 제품 오너는 외부 코퍼스·ASR·번역·모델·API·공급자를 제외한 합성 media plumbing vertical slice의 별도 코드 TASK를 시작할 수 있습니다.
