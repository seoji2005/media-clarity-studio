# TASK-026 — U-06 seed 코퍼스 선택 계약

| 항목 | 값 |
|---|---|
| **ID** | TASK-026 |
| **결정자** | 사람 제품 오너 |
| **기록자** | Lean Root Orchestrator |
| **Reviewer** | 없음 — Gate M 제품 결정 전사. 실제 다운로드는 별도 Gate H |
| **Phase** | Phase 1a / evaluation data contract |
| **Status** | `Done` — 제품 오너 승인 |
| **기준 main** | `52b2ea92b0f913326c99efc1777026641a294663` |
| **차단 질문** | 없음 — U-06 해소 |

## 목표

TASK-005 평가 하네스 설계가 참조할 최소 seed 조합과 사용 경계를 확정한다.

## 승인된 조합

1. **일본어:** Common Voice Scripted Speech 26.0 Japanese
   - dataset ID: `cmqim4lxy00tunr07cjkcupeg`
   - 표시 크기: 14.35 GB
   - local-only cache
   - 재호스팅·재공유·화자 재식별 금지
2. **영어:** LibriSpeech SLR12의 `dev-clean`, `dev-other`, `test-clean`, `test-other`
   - CC BY 4.0 attribution·license notice·변경 표시 보존
3. **일본어↔영어 전환:** 위 seed의 발화를 deterministic recipe로 합성
4. **자연 겹침:** CHiME-6 dev는 cpWER 구현 시점까지 유예
5. **JECS:** 비상업·개인 사용 및 재배포 금지 조건 때문에 제외
6. **MLS·Sintel:** 현재 미선택

## 불변식

- 이번 TASK에서는 외부 코퍼스를 다운로드·가공·재배포하지 않는다.
- 외부 미디어·추출 clip·계정 자격증명을 저장소, PR, CI artifact에 넣지 않는다.
- dev와 frozen-test는 source·speaker 단위로 분리한다.
- 합성 코드스위칭은 recipe version, seed, source ID, time mapping을 기록한다.
- Common Voice는 MDC가 허용하는 접근 경로만 사용하고 화자 재식별을 시도하지 않는다.
- 실제 확보 전 archive URL·약관·크기·hash를 다시 고정한다.
- CHiME-6는 별도 Gate H 승인 전 다운로드하지 않는다.

## 범위 밖

- 계정 생성과 로그인
- 데이터 다운로드·압축 해제·cache 생성
- downloader·adapter·평가 하네스 코드
- 모델·공급자·API 선택
- U-07 품질 임계값 확정

## 합격 기준

- **Given** TASK-003 비교 근거와 제품 오너 승인
  **When** 현재 계약을 읽으면
  **Then** 선택·제외·유예 대상과 실제 다운로드 금지가 모순 없이 구분된다.
- **Given** TASK-005가 시작될 때
  **When** seed 요구사항을 참조하면
  **Then** 일본어·영어·합성 전환의 dev/frozen-test 역할을 설계할 수 있다.
- **Given** 외부 데이터 확보가 필요해질 때
  **When** 별도 작업을 만들면
  **Then** Gate H 검증·hash·cache·삭제 rehearsal 없이는 다운로드를 시작할 수 없다.

## 검증과 복구

- Markdown 상대 링크와 상태 문서의 U-06 표기를 검사한다.
- 코드·의존성·CI 변경이 없어 `make verify`는 재실행하지 않는다.
- 결정 변경 시 이 문서를 삭제하거나 덮어쓰지 않고 후속 결정으로 대체 관계를 기록한다.
