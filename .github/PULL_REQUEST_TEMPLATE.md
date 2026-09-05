## 무엇이 가능해지는가

<!-- 사용자 행동 또는 제거하는 구체적 실패를 한 문장으로. 준비 작업이면 실제 사용 기능과 구분. -->

## 범위와 고정 좌표

- TASK 또는 PR-level scope / Gate:
- Base / fixed HEAD:
- Author / independent reviewer:
- 허용 경로 / 비범위:

## 수용 사례와 검증

<!-- 정상·실패·재시작 중 필요한 사례. 명령, 실제 결과, 환경을 기록. -->
- Focused:
- TASK/module:
- Full regression / 미실행 이유:
- 사용자 흐름 또는 실제 artifact:
- 검증하지 않은 것: 실제 모델 / Windows / RTX / 사람 품질 평가 등

<!-- tests/fixture 통과를 실제 모델·제품 품질로 승격하지 않는다. -->
<!-- 선택적 개발 도구: python scripts/dev_verify.py --test <정확한 파일명> 또는 --full -->

## 결정과 다음 행동

- 미해결 blocker / 선택적 Nit / 범위 밖 후속 제안을 구분:
- 다음 허용 행동:
- 롤백 단위와 원본 보존:

기존 `AGENTS.md`가 정본이며 이 양식은 권한·Gate·필수 읽기·검증을 완화하지 않습니다.
실행 예와 근거: `docs/AGENT_DELIVERY.md`.
작성자는 자기 변경을 승인하지 않습니다. 병합은 오너의 exact PR/HEAD/base 승인 뒤에만 수행합니다.
