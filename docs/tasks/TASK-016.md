# TASK-016 — REVIEW-007 U-22 공급자 결정 귀속 단일 항목 재검토

- **ID:** TASK-016
- **Owner:** TASK-013·TASK-014·TASK-015 / REVIEW-005·REVIEW-006·REVIEW-007을 작성한 동일 GPT Work 리뷰 세션 (사람 제품 오너 예외 승인)
- **Reviewer:** 없음 (§3.2 — 재귀적 리뷰 없음)
- **Phase:** Phase 1 planning / TASK-012 U-22 attribution rereview
- **Status:** In review
- **대상 PR:** #5
- **대상 브랜치:** `claude/task-012-phase1-plan-k3n7qw`
- **고정 대상 HEAD:** `116e033ff9e0433d7d458ab4dfd8c85d44fa8938`
- **고정 대상 tree:** `3f3d670e4a7c4d61ead4ef678baf8b1e5ae0a531`
- **기준 main:** `d11b2450d324ac7f509741acc1ac591313876d30`
- **원 제한 리뷰:** [REVIEW-007](../reviews/REVIEW-007.md) — M-01 부분 해소 · M-02 해소 · 최종 변경 요청
- **원 리뷰 TASK:** [TASK-015](TASK-015.md)

## 1. 목표

REVIEW-007 M-01 잔여 4번의 공급자 결정 귀속 한 항목과 그 수정이 직접 만든 모순만
고정 HEAD의 실제 파일 및 두 새 커밋의 실제 diff로 제한 재검토하고, 단일 항목과
M-01·M-02의 최종 상태 및 상위 판정을 기록한다.

## 2. 범위

- `docs/ARCHITECTURE.md` §7.11, `docs/DECISIONS.md` U-22, `docs/EVALS.md` §4.7(d)의 공급자 결정 귀속
- 공급자 중립 어댑터 계약과 U-22·U-31·U-07 미해결 유지
- `docs/tasks/TASK-012.md`와 `STATUS.md`의 관련 판정·대응·재검토 대기 기록
- `b57df672… → 434fa438… → 116e033…` 계보와 두 커밋의 실제 diff
- 위 수정이 직접 만든 범위 내 모순 및 직접 회귀

## 3. 범위 밖

- 전체 PR 재검토
- REVIEW-007에서 해소된 M-01 잔여 1~3과 M-02의 처음부터 재검토
- REVIEW-005·REVIEW-006·REVIEW-007 원문 및 역사적 판정 수정
- 대상 문서 또는 잔여 위치 직접 수정
- 모델·언어·공급자·서비스·API·지표·실제 구현 충분성 판단
- 병합·Ready 전환·PR 닫기·대상 또는 기존 리뷰 브랜치 변경
- 새로운 독립 지적 번호 추가

## 4. 산출물

- `docs/tasks/TASK-016.md`
- `docs/reviews/REVIEW-008.md`
- `STATUS.md` — 마지막 갱신과 TASK-016 보드 행만
- Draft 리뷰 PR

## 5. 완료 조건

- [x] 고정 HEAD·tree·main·PR 상태와 두 새 커밋 계보를 독립 검증했다.
- [x] 세 문서의 U-22 공급자 결정 귀속과 실제 선택 부재를 대조했다.
- [x] 공급자 중립 계약 및 U-22·U-31·U-07 미해결 유지를 확인했다.
- [x] 수정이 M-01 잔여 1~3과 M-02에 직접 회귀를 만들지 않았는지 확인했다.
- [x] `STATUS.md` 상단 마지막 갱신과 보드·§4의 정합성을 판정했다.
- [x] 단일 항목, M-01·M-02 및 상위 판정을 기록했다.
- [x] 세 허용 파일만 부모가 고정 HEAD인 단일 커밋으로 게시했다.
- [x] 대상·main·PR #1~#8·기존 리뷰 브랜치의 무변경을 확인했다.

## 6. 인계 메모

이 TASK의 Owner는 위 동일 GPT Work 리뷰 세션 하나이며 Reviewer는 없다.
Source Owner의 대응 완료 주장이나 PR 본문을 해소 증거로 쓰지 않고 고정 HEAD의 실제 파일과
실제 diff만 근거로 삼는다. 승인은 병합·Ready 전환·TASK-012 Done이 아니며 병합 판단은
사람 제품 오너에게 남긴다.

## 7. 결과

상세 근거는 [REVIEW-008](../reviews/REVIEW-008.md)에 있습니다.

- M-01 잔여 4(U-22 공급자 결정 귀속): **부분 해소**
  - 세 권위 문서의 결정 귀속, 공급자 중립 계약, 실제 선택 부재는 해소
  - `STATUS.md` 상단 마지막 갱신이 수정 커밋이 직접 기록한 현재 상태보다 뒤처져 직접 상태 모순이 남음
- **M-01: 부분 해소**
- **M-02: 해소 유지** — 이번 수정의 직접 회귀 없음
- **최종 판정: 변경 요청**

이 판정은 병합·Ready 전환·TASK-012 Done을 뜻하지 않으며 병합 판단은 사람 제품 오너에게 남긴다.
