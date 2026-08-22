# TASK-019 — TASK-003 seed 코퍼스·합성 fixture 조사 독립 검토

| 항목 | 값 |
|---|---|
| **ID** | TASK-019 |
| **Owner (수행 소유)** | **독립 Claude Code 리뷰 세션** (이 TASK의 산출물은 리뷰 보고서다 — `AGENTS.md` §3.5) |
| **Reviewer** | 없음 (§3.2) — 재귀적 리뷰를 만들지 않는다. 이 기록의 채택 여부는 사람 제품 오너가 판단한다 |
| **Phase** | Phase 1a / seed corpus research 독립 검토 |
| **Status** | `In review` |
| **검토 대상 PR** | [#12](https://github.com/seoji2005/media-clarity-studio/pull/12) |
| **검토 대상 브랜치** | `claude/task-003-seed-corpus-research-gptw-0812` |
| **고정 대상 HEAD** | `e063c3331681e519dcd6296cbc5cd48276eabb85` |
| **고정 대상 tree** | `63e861ffe21d53dfd913c250c6a79150de51f567` |
| **비교 기준 main** | `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| **리뷰 브랜치** | `claude/task-003-seed-corpus-review-bf4nih` (§9 브랜치명 이탈 기록 참조) |
| **리뷰 기록** | [REVIEW-010](../reviews/REVIEW-010.md) |
| **최종 판정** | **변경 요청** |
| **차단 질문** | 없음 |

## 1. 목표

PR #12의 고정 HEAD에서 TASK-003 산출물 두 건을 독립 검토하고, 판정과 근거를 저장소에
남긴다. 이 세션은 TASK-003의 작성자가 아니며 (`AGENTS.md` R8), 검토 대상 파일을 수정하지
않는다.

## 2. 범위

- TASK-003의 범위·완료 조건 충족 여부
- 조사표의 후보명·언어·규모·정답 형식·라이선스·재배포 가능성·비용·위험이 근거와 일치하는지
- Sintel, LibriSpeech, MLS, Common Voice Korean, CHiME-6 및 제외 후보의 사실관계를
  공식 배포처·라이선스 원문에서 현재 웹으로 대조
- 저작권 라이선스와 서비스 이용약관의 구분, 허용 행위 서술의 과장 여부
- attribution·라이선스 고지·변경 표시·동일조건변경허락 의무의 누락 여부
- 합성 fixture 생성·검증 절차의 **실제 재현 실행**
- U-06·U-07·U-22·U-31 미해결 보존과 모델·공급자·서비스·API·downloader 미선택 확인
- 상대 링크·U-XX·ADR 참조·Markdown 구조 정합성
- 실제 diff, HEAD/tree/blob, PR 상태, commit status·check run·workflow run 확인

## 3. 범위 밖

- `docs/SEED_CORPUS_RESEARCH.md`·`docs/tasks/TASK-003.md`의 내용 수정 (`AGENTS.md` §3.3 금지)
- PR #10·#11·#12의 병합·닫기·Ready 전환·브랜치 push
- `STATUS.md` 수정 — TASK-018/PR #11이 소유 중인 coordination point이므로 직렬화
  (`AGENTS.md` §3.4). 이 TASK 행 통합은 PR #11 처리 후 Source Owner가 수행한다
- U-06 선택, U-31 답변, U-07 수치 확정, U-22 해소
- `main` force-push, history rewrite, 기존 브랜치 변경
- 법적 자문 또는 라이선스 해석의 단정 — 문서가 권리·의무를 안전하게 기술했는지만 판단한다

## 4. 산출물

- `docs/tasks/TASK-019.md`
- `docs/reviews/REVIEW-010.md`

## 5. 완료 조건

- [x] PR #12 head가 고정 HEAD `e063c333…`에서 이동하지 않았음을 GitHub 실물에서 확인한다.
- [x] main HEAD·tree, 대상 tree·blob, 부모 체인, 실제 diff를 재계산한다.
- [x] PR #10·#11과의 파일 중복 여부를 확인한다.
- [x] 공식 배포처·라이선스 원문을 현재 웹에서 확인하고, 확인하지 못한 항목을 분리한다.
- [x] 합성 fixture 명령을 깨끗한 임시 디렉터리에서 문서 원문 그대로 2회 실행한다.
- [x] 문서에 기록된 SHA-256·크기·stream 구성·cue round-trip·staging 해시를 실측과 대조한다.
- [x] 환경 제약과 문서 결함을 분리해 기록한다.
- [x] U-06·U-07·U-22·U-31 미해결 보존과 공급자·모델 미선택을 확인한다.
- [x] 상대 링크·U-XX·ADR 참조·code fence 균형을 검사한다.
- [x] commit status·check run·workflow run 유무를 확인한다.
- [x] 각 finding에 심각도·파일·구역·근거·영향·수정 조건을 기록한다.
- [x] 검토 대상 파일과 `STATUS.md`를 수정하지 않았음을 사후 확인한다.

## 6. 검증 기록

실행한 검증과 결과는 [REVIEW-010](../reviews/REVIEW-010.md)에 기록했다. 요약은 다음과 같다.

- 고정 HEAD·tree·blob·부모 체인·diff 규모(2파일 +484/−0, 3커밋)가 PR 본문 주장과 일치했다.
- 검토 환경의 FFmpeg은 문서가 고정한 `6.1.1-3ubuntu5`와 **동일 build**였다. 따라서 해시
  대조는 환경 제약이 아니라 실측 결과로 판단할 수 있었다.
- `.mkv` 산출물 두 건의 SHA-256과 크기(3,636,043 bytes)는 문서 기록과 **정확히 일치**했고
  2회 실행에서 byte-identical이었다.
- 반면 `fixture.srt`의 기록 SHA-256은 문서 §7.1을 그대로 따라서는 재현되지 않았고, §7.3의
  `diff` 단계가 실패했다. 원인은 SRT의 정확한 바이트 형태가 고정되지 않은 것이다 (M-01).
- 이는 환경 차이가 아니라 문서의 재현 조건 고정 부족이므로 구현 결함으로 판정한다.

## 7. 판정 요약

| 지적 | 심각도 | 요지 |
|---|---|---|
| **M-01** | **중대** | SRT 바이트 형태 미고정 — 기록 SHA-256 재현 불가, §7.3 `diff` 실패, §8 VERIFY 기준이 형태에 취약 |
| **M-02** | 보통 | `MCS_ICLOUD_STAGING_DIR` 미설정 시 `mkdir -p ""` 실패, `cp` 대상이 파일시스템 루트로 해석됨 |
| **M-03** | 보통 | CHiME-6 제외 근거의 출처 집합이 불완전 — 현행 CHiME steward의 재발행 고지를 대조하지 않음 |
| **M-04** | 보통 | TASK-003 `Owner`가 `AGENTS.md` §3와 충돌하고, 예외 근거가 저장소에서 확인되지 않음 |
| **M-05** | 경미 | Sintel credit scroll 의무의 출처 페이지가 §11 목록에 없음 |

**최종 판정: 변경 요청.** 상세 근거·영향·수정 조건은 [REVIEW-010](../reviews/REVIEW-010.md) §5에 있다.

## 8. 인계 메모

- 이 판정은 TASK-003의 **연구 결론을 뒤집지 않는다.** synthetic-first 권고, 후보 역할 분리,
  라이선스/약관 2층 구분, 보수적 제외 규칙은 검증에서 모두 지지됐다. 지적은 재현 절차의
  고정 부족과 근거 출처 보강에 집중된다.
- M-01은 다음 구현 TASK가 그대로 인용하면 **실패하는 acceptance 기준**을 만든다. 코드 착수
  전에 해소해야 한다.
- 이 세션은 `STATUS.md`를 수정하지 않았다. TASK-019 행과 REVIEW-010 기록의 보드 통합은
  PR #11 처리 후 Source Owner가 최신 `main`에서 직렬로 수행한다 (`AGENTS.md` §3.4).
- 승인이 아니므로 TASK-003의 상태 전환·통합은 이 세션이 수행하지 않았다.

## 9. 브랜치명 이탈 기록

`AGENTS.md` §4는 독립 리뷰 세션의 브랜치 접두사를 `claude-review/…`로 정한다. 이 세션은
실행 환경이 지정한 브랜치 `claude/task-003-seed-corpus-review-bf4nih`로만 push할 수 있었고,
다른 이름으로 push할 권한을 받지 못했다. 따라서 접두사가 규칙과 다르다.

- 역할 분리 자체는 유지된다. 이 브랜치는 **검토 대상 브랜치가 아니며**, 대상 파일을 수정하지
  않고 리뷰 문서 2건만 추가한다 (`AGENTS.md` §3.3 허용 목록).
- 규칙을 대화로 바꾸지 않는다. 이탈을 숨기지 않고 여기에 기록하며, 명칭 정정이 필요하면
  사람 제품 오너가 판단한다.
- 후속 작업 후보: 리뷰 브랜치 명명 규칙과 실행 환경 지정 브랜치가 충돌할 때의 처리 절차를
  `AGENTS.md` §4에 명시한다.
