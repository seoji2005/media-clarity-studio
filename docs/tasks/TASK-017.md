# TASK-017 — REVIEW-008 STATUS 상단 직접 잔여 제한 재검토

- **ID:** TASK-017
- **Owner:** TASK-013·TASK-014·TASK-015·TASK-016 / REVIEW-005·REVIEW-006·REVIEW-007·REVIEW-008을 작성한 동일 GPT Work 리뷰 세션 (사람 제품 오너 예외 승인)
- **Reviewer:** 없음 (§3.2 — 재귀적 리뷰 없음)
- **Phase:** Phase 1 planning / TASK-012 STATUS header rereview
- **Status:** In review
- **대상 PR:** #5
- **대상 브랜치:** `claude/task-012-phase1-plan-k3n7qw`
- **고정 대상 HEAD:** `5dbc1b1ca88bdc15b0c14e003ef66fd9c13953a8`
- **고정 대상 tree:** `1e7cf65ccf3b47b3b4f5327f29ac4d5fc21b3321`
- **고정 대상 STATUS.md blob:** `fa763ce61c0203ef64aab605097cd0c108f491ee`
- **기준 main:** `d11b2450d324ac7f509741acc1ac591313876d30`
- **원 제한 리뷰:** [REVIEW-008](../reviews/REVIEW-008.md) — 단일 항목 부분 해소 · M-01 부분 해소 · M-02 해소 유지 · 최종 변경 요청
- **원 리뷰 TASK:** [TASK-016](TASK-016.md)

## 1. 목표

REVIEW-008이 직접 잔여로 남긴 `STATUS.md` 상단 “마지막 갱신” 정합성 한 건과
그 한 줄 수정이 직접 만든 모순 또는 회귀만 고정 HEAD의 실제 파일·blob·tree와
`808d68e2… → 5dbc1b1c…` 실제 diff로 제한 재검토한다.

## 2. 범위

- Source Owner의 대응 완료 주장과 리뷰 판정의 분리
- 아직 수행되지 않은 제한 재검토의 상태 표기
- TASK-012 `In review`, 작업 보드 및 `STATUS.md` §4와의 정합성
- REVIEW-005~REVIEW-008 역사적 판정 보존
- U-22·U-31·U-07 미해결 유지와 실제 모델·공급자·서비스·API 선택 부재
- 이 한 줄이 직접 만든 모순 및 직접 회귀

## 3. 범위 밖

- 전체 PR 또는 이미 해소된 항목 재검토
- 새 독립 지적 추가
- REVIEW-005~REVIEW-008 및 TASK-012~TASK-016 원문 수정
- 대상 문서의 내용 수정
- 모델·공급자·서비스·API·언어·지표·실행 방식 선택
- 병합·Ready 전환·PR 닫기·대상 또는 기존 리뷰 브랜치 변경

## 4. 산출물

- `docs/tasks/TASK-017.md`
- `docs/reviews/REVIEW-009.md`
- `STATUS.md` — 마지막 갱신과 TASK-017 보드 행만
- Draft 리뷰 PR

## 5. 완료 조건

- [x] 고정 HEAD·tree·STATUS blob·main·PR #5·#9 상태를 독립 검증했다.
- [x] `116e033… → 808d68e… → 5dbc1b1…` 선형 계보와 마지막 한 줄 diff를 확인했다.
- [x] 기록 통합 tree와 원 리뷰 tree가 동일하고 TASK-016·REVIEW-008·당시 STATUS blob이 보존됨을 확인했다.
- [x] 상단 문장과 TASK-012 보드·§4의 정합성을 판정했다.
- [x] Source Owner 대응 주장과 리뷰 판정이 분리됨을 확인했다.
- [x] U-22·U-31·U-07 미해결 및 실제 선택 부재를 확인했다.
- [x] 단일 항목, M-01·M-02 및 최종 판정을 기록했다.
- [x] 세 허용 파일만 부모가 고정 HEAD인 단일 커밋으로 게시했다.

## 6. 결과

상세 근거는 [REVIEW-009](../reviews/REVIEW-009.md)에 있다.

- 단일 항목: **해소**
- **M-01: 해소**
- **M-02: 해소 유지**
- **최종 판정: 승인**

상단 문장은 REVIEW-008의 변경 요청을 역사적 판정으로 유지하면서 Source Owner의 직접 잔여
대응 완료와 아직 수행되지 않은 제한 재검토 대기를 구분한다. TASK-012는 `In review`이고,
승인은 병합·Ready 전환·TASK-012 `Done` 또는 계획 확정을 뜻하지 않는다.

## 7. 인계 메모

Source Owner는 TASK-017·REVIEW-009 원문을 별도 기록 커밋으로 통합한 뒤 사람 제품 오너에게
병합 판단을 넘긴다. 리뷰 PR을 병합·cherry-pick하거나 대상 브랜치를 리뷰 커밋으로
fast-forward하지 않는다.
