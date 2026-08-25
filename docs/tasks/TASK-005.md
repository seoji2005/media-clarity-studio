# TASK-005 — 평가 하네스 설계 명세

| 항목 | 값 |
|---|---|
| **ID** | TASK-005 |
| **Owner** | Lean Root Orchestrator |
| **Reviewer** | 없음 — Gate M 비코드 설계. 제품 오너가 PR diff 판단; TASK-006 schema와 구현은 고정 HEAD 검토 |
| **Phase** | Phase 1a / evaluation foundation |
| **Status** | In review |
| **기준 main** | 176a6f106940e02e2c1d88c5fc372a4b2269d441 |
| **선행 조건** | TASK-003 Done, U-06 TASK-026에서 해소, U-31=ko |

## 목표

원문 ASR와 한국어 번역 자막을 분리 평가하는 하네스의 실행·실패·artifact·metric·fixture 계약을
확정하여 TASK-006이 스키마를 재작업 없이 구체화할 수 있게 한다.

## 현재 재현 상태

- EVALS는 source/target 축과 대부분의 계산 규약을 정의한다.
- 번역 품질 지표 선택, 실행 상태, 실패·재개, 필수 fixture 계약은 비어 있다.
- ReferenceBundle/v1·EvalReport/v1은 제안 상태이며 TASK-006이 구체화한다.
- 평가 하네스 코드는 아직 없고 이번 TASK에서 작성하지 않는다.

## 요구 행동과 불변식

- [EVAL_HARNESS.md](../EVAL_HARNESS.md)가 단일 실행 계약이다.
- source/target metric을 합치지 않는다.
- target 자동 primary는 signature가 고정된 chrF2이고 단독 승격 근거가 아니다.
- milestone 승격은 blind paired human review와 guardrail을 함께 본다.
- unsupported·insufficient_n·failed를 0으로 채우지 않는다.
- invalid·partial·failed·aborted artifact를 completed로 승격하지 않는다.
- source/speaker split 누출, axis/language mismatch, fingerprint 불일치는 실행 전에 차단한다.
- 외부 코퍼스·모델·API·절대 목표 수치는 선택하지 않는다.

## 수정 가능 범위

- docs/tasks/TASK-005.md
- docs/EVAL_HARNESS.md
- docs/EVALS.md
- PLAN.md
- STATUS.md

## 범위 밖

코드·테스트·fixture 파일 생성, 의존성·CI, ReferenceBundle JSON Schema, 외부 데이터 다운로드,
ASR/번역 모델 선택, U-07·U-18·U-19·U-26·U-27 수치 확정.

## Given / When / Then 합격 기준

- **Given** dual-axis 입력 **When** metric plan을 읽으면
  **Then** source와 target이 별도 블록에 있고 종합 점수가 없다.
- **Given** target=ko reference **When** 번역 품질을 계산하면
  **Then** 고정 signature chrF2와 blind human review 계약을 찾을 수 있다.
- **Given** 부분 정답·능력 부족 **When** metric을 계획하면
  **Then** unsupported/insufficient_n과 사유가 정의되고 0으로 대체되지 않는다.
- **Given** 실패·중단 **When** 실행 상태를 판정하면
  **Then** partial/completed가 구분되고 같은 fingerprint에서만 재개된다.
- **Given** TASK-006 **When** 인계를 받으면
  **Then** H-01~H-14를 schema fixture로 구체화할 수 있다.

## 필수 검증

- Markdown 링크·상태 표기 정합성
- 기존 EVALS 계산 규약 삭제·완화 없음
- TASK-003/U-06/U-31 선행 상태와 STATUS/PLAN 일치
- 코드·테스트·의존성·CI·외부 데이터 변경 0

## 실패·중단·복구

문서 간 모순이 발견되면 Ready로 전환하지 않는다. 결정 변경 시 기존 기록을 삭제하지 않고
후속 결정과 대체 관계를 남긴다. 코드 구현은 TASK-006 완료 전 시작하지 않는다.

## 완료 증거

고정 HEAD, 변경 파일 목록, 문서 검사 결과, 제품 오너 승인 및 PR 상태.
