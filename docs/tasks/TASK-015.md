# TASK-015 — REVIEW-006 잔여 6항목 한정 재검토

- **ID:** TASK-015
- **Owner:** TASK-013·TASK-014 / REVIEW-005·REVIEW-006을 작성한 동일 GPT Work 리뷰 세션 (사람 제품 오너 예외 승인)
- **Reviewer:** 없음 (§3.2 — 재귀적 리뷰 없음)
- **Phase:** Phase 1 planning / TASK-012 residual rereview
- **Status:** In review
- **대상 PR:** #5
- **대상 브랜치:** `claude/task-012-phase1-plan-k3n7qw`
- **고정 대상 HEAD:** `b57df672e67c1ff8ae1d001c874672e391c474c4`
- **고정 대상 tree:** `420b8c4c864015b148d4a5a89a7a803389cf85ce`
- **기준 main:** `d11b2450d324ac7f509741acc1ac591313876d30`
- **원 제한 리뷰:** [REVIEW-006](../reviews/REVIEW-006.md) — M-01 부분 해소 · M-02 부분 해소 · 최종 변경 요청
- **원 리뷰 TASK:** [TASK-014](TASK-014.md)

## 1. 목표

REVIEW-006이 부분 해소로 남긴 M-01 네 항목과 M-02 두 항목만 고정 HEAD의 실제 파일과
`15a47eb854bb5b75dc45b8fe5128dcb71d95aa72...b57df672e67c1ff8ae1d001c874672e391c474c4`
diff로 제한 재검토하고, 각 잔여 항목과 M-01·M-02의 해소 여부 및 최종 판정을 기록한다.

## 2. 범위

- M-01: ADR-0011 모듈 목록, ARCHITECTURE 계약 참조, EVALS §8 scorecard, U-22 범위
- M-02: 실행 그래프의 코드 구현 노드, STATUS의 HEAD·판정·반영 상태
- 위 수정이 직접 만든 범위 내 모순
- GitHub 고정 상태·계보·REVIEW-006 원문 blob 보존·문서 링크 검증

## 3. 범위 밖

- 전체 PR 또는 REVIEW-005의 열 항목 재검토
- REVIEW-006에서 이미 해소된 항목 재개방
- REVIEW-005·REVIEW-006 원문 및 역사적 판정 수정
- 대상 문서·잔여 여섯 위치 직접 수정
- 모델·언어·공급자·데이터셋·실제 구현 충분성 판단
- 병합·Ready 전환·PR 닫기·대상 또는 기존 리뷰 브랜치 변경
- 새로운 독립 지적 번호 추가

## 4. 산출물

- `docs/tasks/TASK-015.md`
- `docs/reviews/REVIEW-007.md`
- `STATUS.md` — 마지막 갱신과 TASK-015 보드 행만
- Draft 리뷰 PR

## 5. 완료 조건

- [x] 고정 HEAD·tree·main·PR 상태·6커밋 계보를 독립 검증했다.
- [x] 기록 통합 커밋의 TASK-014·REVIEW-006·STATUS blob이 원 리뷰 커밋과 동일하다.
- [x] M-01 네 잔여 항목을 각각 해소/부분 해소/미해소로 판정했다.
- [x] M-02 두 잔여 항목을 각각 해소/부분 해소/미해소로 판정했다.
- [x] 최종 판정을 승인/변경 요청/차단 중 하나로 기록했다.
- [x] 세 허용 파일만 부모가 고정 HEAD인 단일 커밋으로 게시했다.
- [x] 대상·main·PR #1~#7·기존 리뷰 브랜치의 무변경을 확인했다.

## 6. 인계 메모

이 TASK의 Owner는 위 동일 GPT Work 리뷰 세션 하나이며 Reviewer는 없다.
Source Owner의 대응 완료 주장은 증거로 쓰지 않고 GitHub의 고정 파일·diff만 근거로 삼는다.
승인은 병합이나 Done이 아니며 병합 판단은 사람 제품 오너에게 남긴다.

## 7. 결과

상세 근거는 [REVIEW-007](../reviews/REVIEW-007.md)에 있습니다.

- M-01 잔여 1~3: 해소
- M-01 잔여 4(U-22 범위): 부분 해소 — 공급자 결정 주체가 ARCHITECTURE §7.11과 DECISIONS/EVALS에서 다름
- **M-01: 부분 해소**
- M-02 잔여 5~6: 해소
- **M-02: 해소**
- **최종 판정: 변경 요청**

승인은 병합이나 Done이 아니며, 이번 변경 요청 역시 병합 판단을 대신하지 않는다.
