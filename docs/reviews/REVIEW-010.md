# REVIEW-010 — TASK-003 seed 코퍼스·라이선스·합성 fixture 조사 독립 검토

| 항목 | 값 |
|---|---|
| **리뷰 TASK** | [TASK-019](../tasks/TASK-019.md) |
| **대상 PR** | [#12](https://github.com/seoji2005/media-clarity-studio/pull/12) |
| **대상 브랜치** | `claude/task-003-seed-corpus-research-gptw-0812` |
| **고정 대상 HEAD** | `e063c3331681e519dcd6296cbc5cd48276eabb85` |
| **고정 대상 tree** | `63e861ffe21d53dfd913c250c6a79150de51f567` |
| **대상 blob — 조사 문서** | `6cb7cac986efe06f41da93e638b26c0e3947901b` (`docs/SEED_CORPUS_RESEARCH.md`) |
| **대상 blob — TASK 문서** | `9f9e36f573ff58d9b4ff3bff04eb1fad4399817e` (`docs/tasks/TASK-003.md`) |
| **비교 기준 main** | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` (tree `4c01ffebeb92077ed7e61ca18a380d0a0e20f174`) |
| **대상 상태** | Open / Draft / 미병합 |
| **대상 전체** | 3커밋 · 2파일 · +484/−0 |
| **리뷰 브랜치** | `claude/task-003-seed-corpus-review-bf4nih` ([TASK-019](../tasks/TASK-019.md) §9 이탈 기록) |
| **재현 환경 FFmpeg** | `6.1.1-3ubuntu5` — 문서가 고정한 build와 **동일** |
| **최종 판정** | **변경 요청** |

## 1. 고정 상태 확인

이 세션은 PR #12의 Source Owner 세션이 아니며 작성자의 대화 맥락을 받지 않았다
(`AGENTS.md` R8 / §3.1). 판단 근거는 저장소 파일, PR diff, 공개 웹 원문, 실제 실행뿐이다.

GitHub 실물에서 다음을 확인했다.

- PR #12: `open` / `draft: true` / `merged: false` / `mergeable_state: clean`
- head ref `claude/task-003-seed-corpus-research-gptw-0812`, head SHA `e063c3331681e519dcd6296cbc5cd48276eabb85`
  — **지시된 고정 HEAD에서 이동하지 않았다.**
- 고정 HEAD 커밋 객체의 tree는 `63e861ffe21d53dfd913c250c6a79150de51f567`이다.
- base `main` = `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61`, tree `4c01ffebeb92077ed7e61ca18a380d0a0e20f174`.
- `git merge-base 10d34b4a e063c333` = `10d34b4a…` — 대상은 기준 main에서 직접 분기했고 뒤처지지 않았다.

부모 체인은 정확히 3커밋의 선형 계보다.

```
10d34b4a (main)
  └─ 7e8c94e7  docs: bootstrap task 003 seed corpus research      docs/tasks/TASK-003.md        +75
      └─ 9106610c  docs: research seed corpus and synthetic fixture options
                                                                   docs/SEED_CORPUS_RESEARCH.md  +394
          └─ e063c333  docs: move TASK-003 to independent review    docs/tasks/TASK-003.md        +28/−13
```

- 실제 diff는 `docs/SEED_CORPUS_RESEARCH.md` +394/−0, `docs/tasks/TASK-003.md` +90/−0 = **2파일 +484/−0**으로
  PR 본문 주장과 일치한다. 삭제된 줄은 없으므로 R2(기존 콘텐츠 축소 금지) 위반이 없다.
- 첫 커밋이 TASK 파일을 먼저 만들었다. `AGENTS.md` §6.2("새 작업은 반드시 TASK 파일을 먼저 만들고 시작합니다")를
  순서상 충족한다.

### 1.1 열린 PR 경계

| PR | 상태 | base | 변경 파일 |
|---|---|---|---|
| #10 | Open / Draft | `claude/task-012-phase1-plan-k3n7qw` | `STATUS.md` · `docs/reviews/REVIEW-009.md` · `docs/tasks/TASK-017.md` |
| #11 | Open / Draft | `main` | `PLAN.md` · `STATUS.md` · `docs/tasks/TASK-012.md` · `docs/tasks/TASK-018.md` |
| #12 | Open / Draft | `main` | `docs/SEED_CORPUS_RESEARCH.md` · `docs/tasks/TASK-003.md` |

**PR #12와 PR #10·#11의 파일 교집합은 0이다.** `STATUS.md`를 건드리지 않은 판단은 `AGENTS.md` §3.4의
직렬화 요구와 일치하며, R9(동시 편집 금지)를 지켰다.

### 1.2 CI 상태

- PR #12 head의 combined commit status: `total_count: 0`
- PR #12 head의 check run: `total_count: 0`
- 저장소 전체 workflow run: `total_count: 0`

CI는 **실패한 것이 아니라 구성되지 않았다.** Phase 0의 CI 금지(`AGENTS.md` §8)와 일치하며,
PR 본문의 같은 주장은 사실이다.

### 1.3 번호 확인

고정 HEAD·`main`·PR #10·PR #11의 모든 ref를 합쳐 사용된 번호는 TASK-000~TASK-018, REVIEW-001~REVIEW-009이다.
`STATUS.md` §4에 예약된 후보 번호(TASK-003·005·006)도 사용된 것으로 계산했다 (`AGENTS.md` §6).
따라서 **TASK-019와 REVIEW-010이 다음 빈 번호**이며 충돌이 없다.

## 2. 실제 재현 실행

깨끗한 임시 디렉터리에서 `docs/SEED_CORPUS_RESEARCH.md` §7.2·§7.3의 명령을 **원문 그대로** 2회 실행했다.

검토 환경의 FFmpeg은 `ffmpeg version 6.1.1-3ubuntu5`, dpkg `7:6.1.1-3ubuntu5`로 문서가 고정한 build와
동일했다. 따라서 해시 대조 결과를 환경 제약으로 분리할 필요가 없었고, 실측으로 판단했다.

### 2.1 일치한 항목

| 문서 §7.4 기록 | 실측 | 판정 |
|---|---|---|
| source SHA-256 `3bd1180d5445839baf32643e7f78be15d4818c14f1d0152e79a57377919ce37b` | 동일 (run1·run2) | **일치** |
| soft-sub SHA-256 `2f2eb1ba73813133af5c311e3329c1bd5bf445f1192451397bb83af267a623ed` | 동일 (run1·run2) | **일치** |
| output 크기 3,636,043 bytes | 3,636,043 bytes | **일치** |
| Matroska, duration 6.000 s, probe score 100 | `matroska,webm` · `6.000000` · `100` | **일치** |
| video `ffv1` 640×360 30 fps + audio `pcm_s16le` 48 kHz mono + subtitle `subrip` | stream 0/1/2가 정확히 그 구성 | **일치** |
| staging copy 해시 동일 | source output과 staging copy SHA-256 동일 | **일치** |
| 2회 생성 byte-identical | `.mkv` 두 산출물 모두 byte-identical | **일치** |
| §3.1 "약 3.64 MB" | source 3,635,787 bytes = 3.636 MB | **일치** |

`.mkv` 두 건에 대한 문서의 수치는 **전부 실측으로 확인**됐다. §7.4가 이 해시를 "검증 환경의 증거이지
다른 FFmpeg build의 golden hash가 아니다"로 한정하고 ADR-0018의 T1/T3 구분을 인용한 것도 정확하다.
동일 build·동일 명령에서 T1을 관측했고, 일반 배포 주장을 T3로 제한한 서술은 과장이 아니다.

### 2.2 불일치한 항목 — M-01의 근거

| 문서 §7.4 기록 | 실측 | 판정 |
|---|---|---|
| SRT SHA-256 `c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97` | `9df382a65875ccfb1e055b219219d5eb3864751f79896b049f54952cb636c4d6` | **불일치** |
| "cue round-trip: 추출 SRT와 입력 SRT의 diff 없음" | `diff -u` 실패 — 추출본에 후행 빈 줄 1개 추가 | **불일치** |

원인을 특정하기 위해 SRT의 바이트 형태 후보 5종을 만들어 대조했다.

| 형태 | SHA-256 | 문서 기록과 |
|---|---|---|
| A — §7.1 fence 내용 + 최종 개행 1개 | `9df382a6…` | 불일치 |
| **B — A + 후행 빈 줄 1개 (EOF가 `\n\n`)** | **`c2ed5960…`** | **일치** |
| C — CRLF 개행 | `038bc361…` | 불일치 |
| D — 최종 개행 없음 | `ee968f74…` | 불일치 |
| E — UTF-8 BOM + A | `5917bc0c…` | 불일치 |

형태 B로 실행하면 기록 해시가 재현되고 `diff`도 clean이다. 즉 **문서의 수치 자체는 정직하지만,
그 수치를 만든 바이트 형태가 문서 어디에도 고정되어 있지 않다.** §7.1의 fenced block은 마지막 cue
다음의 빈 줄을 표현하지 않으며, 인코딩·개행·후행 공백에 대한 서술도 없다.

부가 확인: 형태 A와 B는 **soft-sub `.mkv` 해시가 동일**했다(`2f2eb1ba…`). mux 시 자막 payload가
정규화되기 때문이다. 따라서 이 결함은 미디어 산출물의 결정성을 훼손하지 않고, SRT 파일 자체와
그것을 직접 비교하는 VERIFY 단계에만 영향을 준다.

### 2.3 staging 단계 확인 — M-02의 근거

`MCS_ICLOUD_STAGING_DIR`를 설정한 경우 §7.3의 마지막 블록은 정상 동작했고 해시가 보존됐다.
변수를 설정하지 않은 경우는 다음과 같다.

```
mkdir: cannot create directory '': No such file or directory
mkdir exit=1
cp target would be: [/fixture-softsub.mkv]
```

`mkdir`은 실패하지만 스크립트가 중단되지 않는 구성에서는 `cp`의 목적지가 파일시스템 루트로 해석된다.

### 2.4 vertical slice 6단계 성립 여부

`LOCAL INPUT → PROBE → EXISTING/GENERATED SRT → SOFT SUB → VERIFY → ICLOUD-STAGING EXPORT`의
각 단계를 실행으로 확인했다.

| 단계 | 실측 |
|---|---|
| LOCAL INPUT | source 생성·존재·non-empty·SHA-256 기록 가능. 이후 단계에서 원본 불변 |
| PROBE | `ffprobe` exit 0, duration `6.000000`, video 1 + audio 1 |
| EXISTING SRT | UTF-8 파싱 성공, cue 2개, `[0.5,2.5)`·`[3.0,5.5)`가 6초 안에 있고 겹치지 않음 |
| SOFT SUB | 새 output 생성, video/audio는 stream copy, `subrip` 1개 추가 |
| VERIFY | 재-probe 성공, 자막 추출 성공. **입력 SRT와의 동일성은 바이트 형태에 의존** (M-01) |
| ICLOUD-STAGING EXPORT | 로컬 디렉터리 복사, output과 export SHA-256 동일. 외부 API·계정 호출 없음 |

**결론: 합성 fixture는 이 slice의 배선을 실제로 검증할 수 있다.** 외부 저작물·계정·네트워크 없이
전 단계가 성립했고, `apt` 이외의 네트워크 접근이 필요하지 않았다. `GENERATED` 분기는 ASR을 요구하므로
이 fixture로 검증되지 않지만, 문서 서두가 "6초 합성 fixture는 컨테이너·자막·내보내기 배선을 검증하지만
ASR 품질, 다국어, 화자 다양성, 겹치는 발화를 검증하지 못한다"고 이미 한정했다. 과장이 아니다.

## 3. 사실관계 대조

접근일 2026-08-12 기준으로 현재 웹에서 대조했다. 검토 환경의 egress 정책상 일부 도메인은
직접 열 수 없어 웹 검색이 노출한 원문 인용으로 대조했고, 그 구분을 §6에 명시한다.

| 문서의 주장 | 대조 결과 |
|---|---|
| Sintel = CC BY 3.0 Unported | **확인** — Blender Durian 공식 기술과 일치 |
| Sintel 전체 길이 14분 48초 | **확인** |
| Sintel credit scroll 보존 요구 | **확인** — "share and show the movie freely, for as long you include the credit scroll of the film itself" |
| LibriSpeech = 약 1,000시간 16 kHz read English, CC BY 4.0 | **확인** |
| LibriSpeech 최소 dev archive 약 314~337 MB | **확인** — `dev-clean` 337M |
| MLS = 8개 언어(영·독·네·스·프·이·포·폴), CC BY 4.0 | **확인** — 언어 목록이 정확히 일치 |
| MLS 제한 지도학습 10분·1시간·10시간 구성 | **확인** |
| MLS archive 폴란드어 6.2 GB ~ 영어 2.4 TB | **미확인** (§6) |
| CHiME-6 OpenSLR SLR150 = CC BY-SA 4.0 | **확인** |
| CHiME-6 archive 97 GB / 11 GB / 12 GB / 2.4 MB | **확인** — 값이 정확히 일치 |
| CHiME-6 원 프로젝트 페이지의 commercial license 2,000 GBP | **확인** — 해당 페이지에 현재도 그 문구가 있다 |
| YouTube ToS가 서비스 허용·권리자 사전 허락 외 download·복제·수정을 제한 | **확인** — ToS의 "except (a) as specifically permitted by the Service; (b) with prior written permission from YouTube and, if applicable, the respective rights holders"와 일치 |
| Common Voice 26.0이 2026년 6월 release | **확인** (Korean 개별 수치는 §6) |
| Common Voice Korean 세부 수치·MDC 약관 문언 | **미확인** (§6) |
| `ffprobe`의 `-show_streams`·`-show_format`·`-of json` | **경험적 확인** — 실행에서 정상 동작 |

### 3.1 권리·의무 서술의 정확성

- **라이선스 층과 서비스 약관 층의 구분(§5)은 올바르다.** "콘텐츠 라이선스 = 저작권상 허락",
  "서비스 약관 = 접근·보관·공유 조건"의 분리가 정확하고, Common Voice에서 "CC0 표기만 보고
  repository redistribution을 허용하면 안 된다"는 경고는 두 층을 혼동하지 않은 정확한 서술이다.
- **허용 행위 서술에 과장이 없다.** §4 요약표의 `예*` 표기가 "저작권상 가능하지만 프로젝트상
  금지"를 명시적으로 분리한다. 라이선스가 허용하는 것을 프로젝트가 허용한다고 넘겨짚지 않았다.
- **의무 누락이 없다.** CC BY 3.0/4.0의 attribution·라이선스 링크·변경 표시가 모든 해당 행에
  기재됐다. ShareAlike는 채택 후보 중 CC BY-SA가 없으므로 "동일조건변경허락 의무는 없다"는
  결론이 맞고, CHiME-6 재검토 시에만 필요하다는 단서도 정확하다.
- **CC0에 attribution 의무가 없다는 점을 정확히 적으면서도** 재현성을 위해 출처·release·dataset ID를
  기록하라고 한 것은 법적 의무와 프로젝트 관행을 혼동하지 않은 서술이다.
- **Sintel 파생물 처리가 보수적이다.** clip·remux·자막 수정을 adaptation으로 보고 변경 표시를
  요구했으며, 짧은 clip이 credit scroll을 제거한다는 위험까지 짚었다. 이는 실제 위험이다.
- **불명확한 후보를 안전하게 제외했다.** CHiME-6는 라이선스 충돌 미해소를 이유로 다운로드·가공·
  재배포·저장소 포함을 모두 미승인했고, Common Voice는 재호스팅 금지를 이유로 저장소 포함을
  배제하고 공개 파생 배포를 승인하지 않았다. 둘 다 안전한 방향의 판단이다.
- **§6 제외 규칙 7항**은 출처 불명 CDN, 서비스 허용 경로 없는 파일, "royalty-free"만 있는 자료,
  약관 충돌 corpus, 개인정보 통제 불가 자료를 배제한다. 규칙으로서 결함을 찾지 못했다.

### 3.2 결정 경계 보존

| ID | 문서의 서술 | 판정 |
|---|---|---|
| U-06 | 미해결 — 비교표·의사결정 카드만 제공, 최종 선택 없음 | **보존** |
| U-22 | 보류됨(Deferred) 유지 — ASR·번역·재구성 모델, 공급자, API, 실행 방식 선택 없음 | **보존** |
| U-31 | 미해결 — cue를 번역 정답이 아닌 중립 표식으로 두고, subtitle language tag도 요구하지 않음 | **보존** |
| U-07 | 미해결 — 절대 품질 목표 수치 없음 | **보존** |

전체 diff에서 모델·공급자·서비스·API·downloader 선택, 의존성 매니페스트, 모델 가중치, CI 설정,
비밀정보, 바이너리 fixture 추가를 찾지 못했다. `AGENTS.md` §8의 Phase 0 금지 항목을 위반하지 않았다.
§7.2가 FFmpeg 명령을 "절차 검증용 recipe이며 프로젝트의 장기 runtime·dependency 선택이 아니다"라고
한정한 것도 U-22를 침범하지 않으려는 정확한 처리다.

### 3.3 참조·구조 정합성

- 상대 Markdown 대상: **5개 고유 / 6회 등장 / 누락 0** — `../AGENTS.md`, `../PLAN.md`,
  `DECISIONS.md`, `EVALS.md`(2회), `tasks/TASK-003.md`. 전부 고정 tree에 존재한다.
- code fence: `` ``` `` 행 6개 = **3쌍 균형**.
- U-XX 참조: U-06 14회, U-31 7회, U-07 2회, U-22 2회. 전부 기준 문서에 실재한다.
- ADR 참조: ADR-0018 1회. `docs/DECISIONS.md` §"ADR-0018 — 재현성을 세 등급으로 구분한다
  *(제안됨)*"에 실재하며, 문서의 T1/T3 인용이 원문 정의와 일치한다.
- `PLAN §3-1d` 표기: `PLAN.md` §3의 하위 절 `### 1d. Phase 1a 첫 실행 순서 (제안 — 검토 중,
  아직 확정되지 않았습니다)`를 가리킨다. 실재하며, 문서가 이를 "현재 제안 그래프"라 부른 것도
  원문의 "제안" 상태와 일치한다. 결함이 아니다.
- §2의 비교 기준이 `EVALS.md` §2.5가 요구한 8개 필드(이름·언어·규모·정답 형식·라이선스·
  재배포 가능성·비용·위험)를 모두 포함하고 허용 행위·의무·서비스 조건을 추가한다. 요구를 충족한다.

### 3.4 TASK-003 완료 조건 대조

TASK-003 §5의 11개 항목 중 10개는 고정 HEAD의 산출물로 충족을 확인했다. 다만 다음 항목은
부분 충족이다.

> - [x] 완전 합성 fixture의 최소 사양, 생성 절차, 재현성 한계를 기록한다.

최소 사양과 재현성 한계(T1/T3 구분)는 기록됐으나, **생성 절차가 기록된 해시를 재현하지 못한다**
(M-01). 따라서 이 항목은 충족으로 보지 않는다. 나머지 완료 조건과 §2 범위 항목은 충족한다.

## 4. 지지되는 판단

지적과 별개로, 다음은 검증에서 **적극적으로 지지**됐고 되돌릴 이유가 없다.

1. **synthetic-first 권고는 타당하다.** 외부 저작물·계정·네트워크 없이 6단계 전부가 로컬에서
   성립함을 실행으로 확인했다.
2. **U-06과 첫 fixture 결정의 분리가 옳다.** 문서는 권고가 U-06 선택이 아님을 §1.1·§9·§10에서
   반복해 명시하며, 조사와 결정의 역할 분리(`EVALS.md` §2.5)를 지킨다.
3. **`.mkv` 결정성 주장은 실측으로 확인됐다.**
4. **라이선스·약관 2층 분리와 보수적 제외가 안전한 방향이다.**
5. **`STATUS.md` 미변경 판단이 옳다.** PR #11과의 충돌을 구조적으로 회피했다.

## 5. 지적 (findings)

### M-01 — 중대 · SRT 바이트 형태 미고정으로 기록 해시와 VERIFY 기준이 재현되지 않음

- **파일·구역:** `docs/SEED_CORPUS_RESEARCH.md` §7.1(SRT fenced block), §7.3(`diff` 단계),
  §7.4(SRT SHA-256 행 및 "cue round-trip … diff 없음" 행), §8(VERIFY 행)
- **근거:** §7.1을 문자 그대로 따라 만든 SRT의 SHA-256은 `9df382a6…`로 기록값 `c2ed5960…`와
  다르다. 그 파일로 §7.3을 실행하면 `diff -u fixture.srt fixture-extracted.srt`가 후행 빈 줄
  1개 차이로 실패한다. EOF가 `\n\n`인 형태에서만 기록 해시가 재현되고 `diff`가 clean이다
  (§2.2의 5종 대조).
- **영향:** ① 리뷰어·후속 담당자가 문서만 보고 기록 해시를 재현할 수 없다 — `AGENTS.md` §3.1의
  "파일만 보고 이해되지 않으면 그것 자체가 결함"에 해당한다. ② §8이 "기계적 확인"으로 규정한
  VERIFY 기준이 바이트 형태에 취약하며, 문서에 적힌 형태로는 **실패한다.** 다음 구현 TASK가
  이 기준을 그대로 인용하면 처음부터 실패하는 acceptance를 얻는다. ③ ADR-0018의 T1 관측
  기록이 `.srt`에 한해 검증 불가 상태로 남는다.
- **환경 제약 아님:** 검토 환경의 FFmpeg build가 문서 고정값과 동일했고, `.mkv` 해시는 정확히
  재현됐다. 따라서 이 불일치는 build 차이가 아니라 문서의 재현 조건 고정 부족이다.
- **필요한 수정 조건:**
  1. `fixture.srt`의 정확한 바이트 형태를 고정한다 — 인코딩(UTF-8, BOM 없음), 개행(LF),
     **최종 cue 뒤 빈 줄의 유무**를 명시하고, fence 대신 바이트가 확정되는 생성 방법
     (`printf` 또는 종결자 명시 here-doc)을 제시한다.
  2. §7.4의 SRT SHA-256이 그 형태에 대응함을 명시한다.
  3. §7.3·§8의 비교를 형태에 견고하게 만든다 — 후행 공백 정규화 비교를 규정하거나,
     SubRip 추출이 후행 빈 줄을 덧붙인다는 사실을 명시하고 그에 맞춘 비교 기준을 적는다.

### M-02 — 보통 · `MCS_ICLOUD_STAGING_DIR` 미설정 시 staging 단계가 루트를 가리킴

- **파일·구역:** `docs/SEED_CORPUS_RESEARCH.md` §7.3 마지막 코드 블록, §7.1의 staging 행
- **근거:** 변수를 설정하지 않고 실행하면 `mkdir -p ""`가 exit 1로 실패하고, `cp`의 목적지가
  `/fixture-softsub.mkv`로 해석된다 (§2.3 실측). §7.1은 이 변수를 "사용자가 지정한 로컬
  디렉터리"라고 설명하지만, 어떤 단계도 값을 설정하거나 검증하지 않는다.
- **영향:** 문서의 명령 블록을 그대로 실행한 사람이 작업 디렉터리 밖으로 파일을 쓰거나
  원인이 불분명한 실패를 겪는다. "iCloud-staging export"가 로컬 디렉터리 조작임을 강조한
  문서의 안전 의도와 실제 스크립트의 동작이 어긋난다.
- **필요한 수정 조건:** 블록 선두에 미설정 시 중단하는 가드(예: `: "${MCS_ICLOUD_STAGING_DIR:?
  set to a local staging directory}"`)를 추가하거나, 명시적 예시 설정 단계를 절차에 포함한다.

### M-03 — 보통 · CHiME-6 제외 근거의 출처 집합이 불완전

- **파일·구역:** `docs/SEED_CORPUS_RESEARCH.md` §3.6, §4 요약표 CHiME-6 행, §6-4, §9 겹치는
  발화 seed 행, §11 출처 목록
- **근거:** 문서는 OpenSLR SLR150(CC BY-SA 4.0)과 `chimechallenge.github.io/chime6/download.html`
  (CHiME-5 별도 license 신청, commercial 2,000 GBP) **두 곳만** 대조해 "두 공식 설명만으로 …
  한 가지로 확정할 수 없다"고 결론했다. 두 문구가 현재도 각 페이지에 있다는 점은 확인했다.
  그러나 현행 CHiME steward 사이트(`chimechallenge.org`)에는 **CHiME-5가 2024-01-01자로
  CC BY-SA 4.0으로 재발행되어 학술·상업 모두 무료라는 고지**가 있는 것으로 확인된다. 이 고지를
  대조하면 2,000 GBP 문구는 갱신되지 않은 과거 안내일 가능성이 크고, "두 공식 설명의 충돌"이라는
  전제가 달라진다. (직접 열람은 egress 차단으로 불가 — §6 참조)
- **영향:** **제외 판정 자체는 안전한 방향이므로 위험을 만들지 않는다.** 문제는 §9 의사결정
  카드가 사람 제품 오너에게 "CHiME-6 license clarification … 필요"라고 안내한다는 점이다.
  공개된 clarification이 이미 존재한다면 오너는 실제보다 좁은 선택지를 보고 판단하게 되며,
  겹치는 발화 seed 후보가 근거 없이 0개로 남는다. 이는 `EVALS.md` §2.6의 "겹치는 발화 정답이
  화자별로 분리" 요구와 cpWER 전제에 직접 영향을 준다.
- **필요한 수정 조건:** 현행 CHiME steward 페이지를 출처 집합에 추가해 재대조하고, 재발행
  고지의 유무·일자를 §3.6에 기록한다. 그 결과에 따라 제외를 유지하되 사유를 갱신하거나,
  조건부 후보로 재분류한다. 어느 쪽이든 §11 출처 목록에 해당 페이지를 추가한다.
  라이선스 해석을 단정할 필요는 없고, 대조한 출처와 남은 불확실성을 적으면 충분하다.

### M-04 — 보통 · TASK-003의 `Owner`가 `AGENTS.md` §3과 충돌하고 예외 근거가 저장소에 없음

- **파일·구역:** `docs/tasks/TASK-003.md` 머리말 `Owner (수행 소유)` 행
- **근거:** 해당 행은 `**GPT Work Root Orchestrator** (사람 제품 오너의 이 대화상 명시적 수행
  지시 예외)`이다. `AGENTS.md` §3은 "Owner / Reviewer가 될 수 있는 것은 2번과 3번뿐입니다.
  GPT Work(1)와 Claude 일반 대화(4)는 … TASK의 Owner도 Reviewer도 아닙니다"라고 명시하고,
  §6의 주체 주의도 "GPT Work는 … 저장소 파일을 만들지 않습니다"라고 적는다. 예외의 근거는
  "이 대화상"에 있는데, `AGENTS.md` R7·§7은 인계를 저장소 파일과 PR 설명으로만 하도록 하고
  "아까 말한 대로" 류의 표현을 금지한다. §3.1은 파일만 보고 이해되지 않는 것을 결함으로 규정한다.
- **영향:** 독립 리뷰 세션인 이 세션은 해당 예외가 실제로 승인됐는지 저장소에서 확인할 수
  없었다. 선례(TASK-013~TASK-016)에서는 같은 성격의 예외가 `STATUS.md` 보드 행에 "사람 오너의
  예외 승인"으로 기록되어 검증 가능했다. 이번에는 `STATUS.md`를 의도적으로 건드리지 않았으므로
  (그 판단 자체는 M-02가 아니라 §4-5에서 지지한다) 저장소 어디에도 근거가 없다. 역할 분리
  감사 추적이 끊긴다.
- **필요한 수정 조건:** 예외 승인 사실을 저장소에서 확인 가능한 형태로 남긴다 — 직렬화 순서가
  허용하는 시점에 `STATUS.md` 행으로 기록하거나, TASK-003 머리말이 이미 승인된 기존 기록
  (선례 행·ADR)을 참조하도록 고친다. 또는 `AGENTS.md` §3에 맞춰 Owner를 재지정한다.
  대화를 근거로 삼는 표현은 제거한다.

### M-05 — 경미 · Sintel credit scroll 의무의 출처 페이지가 목록에 없음

- **파일·구역:** `docs/SEED_CORPUS_RESEARCH.md` §3.2 의무 행("공식 페이지의 credit scroll
  요구도 보존"), §11 공식 출처 목록
- **근거:** credit scroll 보존 요구는 확인됐으나, 그 문구는 §11이 나열한 `about/`·`download/`가
  아니라 Blender Durian의 공유 안내 페이지(`durian.blender.org/sharing/`)에 있는 것으로 확인된다.
  §3.2는 "공식 페이지"라고만 적어 어느 페이지인지 특정하지 않는다.
- **영향:** 의무 자체는 정확히 기재됐으므로 권리 판단에 오류는 없다. 다만 문서가 스스로 정한
  기준("원저작자 또는 공식 steward의 원문 URL")을 이 한 항목에서 충족하지 못해, 추후 재확인
  시 근거를 다시 찾아야 한다.
- **필요한 수정 조건:** credit scroll 요구가 실린 페이지를 §11에 추가하고 §3.2에서 그 페이지를
  지목한다.

## 6. 확인하지 못한 항목

검토 환경의 egress 정책이 여러 도메인을 차단해 **직접 열람에 실패**했다. 아래는 추정하지 않고
미확인으로 남긴다. 이들 중 어느 것도 위 지적의 근거로 쓰이지 않았다.

- **직접 열람 실패 도메인:** `durian.blender.org`, `openslr.org` / `www.openslr.org` /
  `us.openslr.org`, `chimechallenge.github.io`, `www.chimechallenge.org`,
  `mozilladatacollective.com`, `ffmpeg.org`. §3 표에서 "확인"으로 적은 항목은 웹 검색이
  노출한 해당 원문의 인용에 근거하며, **1차 페이지를 직접 연 것이 아니다.**
- **Common Voice Korean datasheet의 세부 수치** — 208.26 MB, 7,178 clips, 10.38시간(검증
  2.54시간), 210 speakers, 2026-06-17 release, dataset ID `cmqi922c5001pnq07dmj0oypw`.
  도메인 차단과 계정 게이트로 확인하지 못했다. dataset ID 형식이 같은 26.0 release의 다른
  언어 datasheet와 일치한다는 정황만 확인했다.
- **MDC Terms·FAQ·API 문서의 문언** — "dataset license와 supplemental terms가 추가적으로
  함께 적용", "충돌 시 더 제한적인 조건", "계정 종료 시 사용 중단·삭제 의무", "web UI 동의 후
  download URL 생성". 문서가 인용한 이 네 문장을 원문에서 확인하지 못했다. 검색 결과는 MDC
  약관이 Data Consumer License 허용 범위 밖의 복제·배포·파생물 작성을 금지한다는 점까지만
  보여준다. **문서의 방향(더 제한적인 쪽)과 모순되는 근거는 발견하지 않았다.**
- **MLS per-language archive 크기** — 폴란드어 6.2 GB, 영어 2.4 TB를 확인하지 못했다.
  8개 언어 구성·CC BY 4.0·제한 지도학습 구성은 확인했다.
- **M-03의 CHiME 재발행 고지** — 1차 페이지를 직접 열지 못했고 검색이 노출한 문장에 근거한다.
  따라서 M-03은 "제외 판정이 틀렸다"가 아니라 "출처 집합이 불완전하니 재대조하라"로 한정했다.
- `ffmpeg.org/ffprobe.html`의 문서 내용은 열지 못했으나, `-show_streams`·`-show_format`·
  `-of json`·stream specifier의 동작은 실행으로 확인했다.
- 저장소 밖에서 U-06·U-31·U-07·U-22가 별도로 결정됐는지, TASK-003 Owner 예외가 실제로
  승인됐는지는 GitHub 객체만으로 확인할 수 없다.
- PR #12의 본문 revision history와 과거 force-push 전무 여부의 전체 감사 로그는 확인하지 않았다.

## 7. 판정

**최종 판정: 변경 요청.**

- M-01(중대) 1건, M-02·M-03·M-04(보통) 3건, M-05(경미) 1건.
- 연구 결론 — synthetic-first 권고, 후보 역할 분리, 라이선스/약관 2층 구분, 보수적 제외,
  결정 경계 보존 — 은 검증에서 지지됐고 되돌릴 이유가 없다.
- 변경 요청의 중심은 **재현 절차의 바이트 수준 고정 부족(M-01)** 이다. 이것만으로도 다음 구현
  TASK가 실패하는 acceptance 기준을 물려받으므로 코드 착수 전에 해소해야 한다.

이 판정은 PR #12의 병합·Ready 전환·TASK-003 `Done`을 뜻하지 않는다. 어떤 판정이든 `Done`은
사람 제품 오너의 병합 또는 명시적 종료 후에만 도달한다 (`AGENTS.md` §6, §9-5, R1).

## 8. 다음 허용 행동

Source Owner(TASK-003 소유 세션)에게 필요한 조치는 다음과 같다.

1. TASK-019·REVIEW-010 원문을 **별도 기록 커밋으로 먼저 통합**한다 (`AGENTS.md` §3.4 순서 2).
   리뷰 문서를 수정하지 않고 원문 그대로 옮긴다 (§4.1 원문 불변).
2. 그 다음 M-01을 해소한다 — SRT 바이트 형태 고정, §7.4 해시의 대응 형태 명시, §7.3·§8 비교
   기준 재작성. 수정 후 같은 절차를 재실행해 새 해시를 기록한다.
3. M-02의 가드를 추가한다.
4. M-03의 출처 재대조를 수행하고 §3.6·§9·§11을 갱신한다. 제외를 유지해도 되지만 사유는
   갱신된 출처 집합에 근거해야 한다.
5. M-04의 Owner 예외 근거를 저장소에서 확인 가능하게 만든다.
6. M-05의 출처를 §11에 추가한다.
7. `STATUS.md` 통합은 PR #11 처리 후 최신 `main`에서 직렬로 수행한다.
8. 반영 후에는 **새 고정 HEAD**를 지정해 재검토를 요청한다. 반영 커밋을 "현재 HEAD"로 부르지
   않고 식별자로만 표기한다 (REVIEW-006 §3.2, REVIEW-007 §3.2의 잔여 결함과 같은 처리).

이 리뷰 세션은 대상 브랜치에 push하지 않았고, PR #10·#11·#12와 `main`을 변경하지 않았으며,
`STATUS.md`를 수정하지 않았다. 리뷰 PR의 병합·cherry-pick·Ready 전환도 하지 않는다.
