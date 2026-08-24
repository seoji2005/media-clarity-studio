# TASK-027 — Lean Root / Claude Code 운영 분업 계약

| 항목 | 값 |
|---|---|
| **ID** | TASK-027 |
| **결정자** | 사람 제품 오너 |
| **기록자 / Owner** | Lean Root Orchestrator |
| **Reviewer** | 없음 — Gate M 운영 결정 전사; 제품 오너가 PR diff 판단 |
| **Phase** | Project operations |
| **Status** | `Done` — 제품 오너 승인 |
| **기준 main** | `a42bcf504e51707ea26aa5e84ba7edf31a10ad04` |

## 목표

코드는 Claude Code가 작성하고, Lean Root는 비코드 작업·검증·리뷰·승인 후 통합을 담당한다는
제품 오너의 장기 운영 결정을 저장소 규칙으로 고정한다.

## 요구 행동과 불변식

- 소스·테스트·fixture generator·검증 스크립트·빌드·CI·의존성 변경은 Claude Code가 작성한다.
- Lean Root는 저장소 조사, 요구사항, TASK 계약, Claude Code 프롬프트, 비코드 연구·문서·상태,
  직접 검증, 코드 리뷰, PR 준비를 담당한다.
- 코드 결함은 Lean Root가 직접 고치지 않고 Claude Code에 제한 재작업 프롬프트로 반환한다.
- 작성자와 리뷰어는 서로 다른 행위자 또는 독립 세션이어야 한다.
- Lean Root는 제품 오너가 특정 PR과 고정 HEAD 병합을 명시적으로 승인한 뒤에만
  `expected_head_sha`를 고정해 일반 merge한다.
- 승인 뒤 HEAD가 바뀌면 병합을 멈추고 재검토·재승인한다.
- rebase·force-push·amend·history rewrite·branch 삭제·release·deploy는 별도 명시 승인 없이는 수행하지 않는다.
- Gate L/M은 최소 증거로 처리하고 Gate H/S에만 독립 검토·복구 절차를 집중한다.

## 범위 밖

제품 행동, 런타임 코드, 테스트, 외부 데이터, 모델·공급자·API 선택.

## 합격 기준

- **Given** 코드 변경이 필요할 때 **When** Lean Root가 다음 작업을 넘기면
  **Then** 직접 코드 대신 Claude Code가 그대로 실행할 수 있는 완결 프롬프트를 제공한다.
- **Given** Claude Code PR **When** 리뷰하면
  **Then** Lean Root가 고정 HEAD·diff·명령·artifact를 직접 확인하고 결함 수정은 Claude Code에 반환한다.
- **Given** 제품 오너의 병합 승인 **When** HEAD가 승인 SHA와 같으면
  **Then** Lean Root가 일반 merge 후 PR 종료와 최신 `main`을 확인한다.
- **Given** 승인 뒤 HEAD 변경 **When** 병합 직전 확인하면
  **Then** 자동으로 멈추고 재승인을 요청한다.

## 검증과 복구

문서 링크·역할·병합 경계의 상호 모순을 검사한다. 코드·의존성·CI 변경은 없다.
결정 변경 시 기존 기록을 삭제하지 않고 후속 ADR로 대체 관계를 남긴다.
