# TASK-025 — U-31 번역 대상 언어 한국어 확정

| 항목 | 값 |
|---|---|
| **ID** | TASK-025 |
| **Owner** | Lean Root Orchestrator (사람 제품 오너의 2026-08-22 직접 결정 반영) |
| **Reviewer** | 없음 — Gate M 제품 결정 전사·계약 정합성 변경, 코드·알고리즘 변경 없음 |
| **Phase** | Phase 1a / translation evaluation contract |
| **Status** | `In review` |
| **기준 main** | `f1524d5519afbd06d4d2a752dd3d0d4e1572a488` |
| **위험 등급** | **Gate M** — 사용자 산출물 언어 계약과 평가 입력 조건 변경 |

## 목표

U-31의 사람 제품 오너 답변을 번역 대상 언어 **한국어**, BCP-47 `ko`로 기록하고,
Phase 1의 제품·아키텍처·평가 문서가 같은 계약을 말하게 한다.

## 요구 행동과 불변식

- 번역 자막과 `TranslatedTranscript.target_language`의 현재 제품 프로필은 `ko`다.
- 번역 축 `ReferenceBundle.target_language`는 target-axis 정답이 있으면 `ko`여야 한다.
- U-31은 해소되고 TASK-005의 선행 조건에서 제거된다.
- TASK-005는 TASK-003 완료와 사람 U-06 선택 전에는 여전히 착수하지 않는다.
- 번역 모델·엔진·API·공급자(U-22), 품질 지표·합격선(U-07), 한국어 정규화·CPS 규칙(U-18·U-19)은 확정하지 않는다.
- 원문 transcript와 한국어 번역 subtitle은 계속 별도 산출물·평가 축으로 보존한다.
- 코드·테스트·Makefile과 PR #16 runtime blob은 변경하지 않는다.

## 수정 가능 범위

- `PLAN.md`
- `STATUS.md`
- `docs/DECISIONS.md`
- `docs/ARCHITECTURE.md`
- `docs/EVALS.md`
- `docs/PRODUCT_SPEC.md`
- `docs/tasks/TASK-024.md`
- 이 TASK 파일

## 범위 밖

모델·공급자·API 선택, 번역 구현, seed 코퍼스/Gate E 결정, U-06·U-07·U-18·U-19 해소,
기존 PR/branch 처분, merge/Ready 전환, history rewrite.

## Given / When / Then

1. **Given** U-31 답변 **한국어**, **When** 현재 계약 문서를 읽으면 **Then** 대상 언어가 모두 `ko`로 일치한다.
2. **Given** target-axis 정답 또는 번역 산출물, **When** 언어 필드를 검사하면 **Then** 누락·`undetermined`·비-`ko` 값은 계산 가능한 한국어 번역 축으로 취급하지 않는다.
3. **Given** Phase 1a 실행 그래프, **When** 선행 조건을 읽으면 **Then** TASK-005는 TASK-003·U-06만 기다리고 U-31은 완료다.
4. **Given** 이번 diff, **When** 범위를 검사하면 **Then** 코드·모델·의존성·CI 변경은 0건이다.

## 검증과 복구

- 변경 파일 닫힌 목록과 U-31/`target_language` 잔여 모순 검사
- Markdown 상대 링크 검사
- runtime/support blob 8개 `main`과 동일 확인
- 병합 전에는 Draft PR을 닫으면 `main`에 영향이 없다.
