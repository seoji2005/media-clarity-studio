# REVIEW-007 — REVIEW-006 잔여 6항목 한정 재검토

| 항목 | 값 |
|---|---|
| **리뷰 TASK** | [TASK-015](../tasks/TASK-015.md) |
| **대상 PR** | [#5](https://github.com/seoji2005/media-clarity-studio/pull/5) |
| **대상 브랜치** | `claude/task-012-phase1-plan-k3n7qw` |
| **고정 대상 HEAD** | `b57df672e67c1ff8ae1d001c874672e391c474c4` |
| **고정 대상 tree** | `420b8c4c864015b148d4a5a89a7a803389cf85ce` |
| **비교 기준 main** | `d11b2450d324ac7f509741acc1ac591313876d30` |
| **대상 상태** | Open / Draft / 미병합 |
| **대상 전체** | 6커밋 · 11파일 · +1569/−94 |
| **원 제한 리뷰** | [REVIEW-006](REVIEW-006.md) / [TASK-014](../tasks/TASK-014.md) |
| **원 리뷰 커밋 / PR** | `0538de73a9bddd725ab69a2ddeb5deda42fb30b3` / [#7](https://github.com/seoji2005/media-clarity-studio/pull/7) |
| **이번 범위** | REVIEW-006이 남긴 M-01 네 곳과 M-02 두 곳만 |
| **리뷰 브랜치** | `claude-review/task-015-task-012-residual-rereview-gptw-0811` |
| **M-01 판정** | **부분 해소** |
| **M-02 판정** | **해소** |
| **최종 판정** | **변경 요청** |

## 1. 연속성·고정 상태

- 이 세션은 TASK-013·TASK-014 / REVIEW-005·REVIEW-006과 리뷰 PR #6·#7을 작성한 **동일 GPT Work 리뷰 세션**이며, PR #5 Source Owner 세션이 아니다.
- 사람 제품 오너의 GPT Work 리뷰 예외 승인은 계속 유효하다.
- Source Owner의 “대응 완료” 주장과 PR #5 본문은 판정 증거로 사용하지 않았다.
- GitHub 앱에서 PR #5를 Open / Draft / 미병합, base `main`, head `claude/task-012-phase1-plan-k3n7qw`, HEAD `b57df672e67c1ff8ae1d001c874672e391c474c4`로 확인했다.
- `main...HEAD`는 6커밋·11파일·+1569/−94이고 merge base는 `main`의 `d11b2450d324ac7f509741acc1ac591313876d30`이다.
- 예상 6커밋 계보의 모든 인접 전이는 정확히 1커밋이다. 특히 `e0d99cf… → 15a47eb…`는 3파일·+220/−2, `15a47eb… → b57df67…`는 5파일·+142/−17이다.
- GitHub가 고정 HEAD에서 반환한 27개 파일 blob으로 전체 tree를 재구성한 결과는 `420b8c4c864015b148d4a5a89a7a803389cf85ce`이다. PR 본문이나 Source Owner 보고의 tree 값을 근거로 쓰지 않았다.
- 기록 통합 커밋 `15a47eb…`의 세 blob은 원 리뷰 커밋 `0538de7…`과 동일하다: TASK-014 `ab49b97631730c0f6814f88fd5c5c580f476b88c`, REVIEW-006 `0123a5494f57ee47bd4888600b05b5ae10246771`, STATUS `4d06a9724ca8ecd1b30ecedafec9bc76f3d59604`.

## 2. M-01 잔여 네 항목

### 2.1 ADR-0011 모듈 목록 — **해소**

- [DECISIONS](../DECISIONS.md) ADR-0011 제목은 “11개 모듈”이고 상태는 **제안됨**이다.
- 목록은 `ingest · audio · asr · translate · subtitle · reconstruct · eval · orchestrator · storage · ui · export`의 정확히 11개이며, `translate`가 `asr`와 `subtitle` 사이에 있다.
- [ARCHITECTURE](../ARCHITECTURE.md) §4의 모듈 지도·ID 목록과 이름·수·순서가 같다.
- `15a47eb… → b57df67…` diff에서 ADR-0011 변경은 제목의 10→11과 목록의 `translate` 추가뿐이다. 다른 모듈 경계나 실행 전략을 바꾸지 않았다.

### 2.2 ARCHITECTURE의 계약 참조 — **해소**

- `ReferenceBundle/v1` 예시의 “정답 축이 둘” 주석과 `reference_axis` 필드 주석은 모두 실제 규칙 절인 §3.0.1을 가리킨다.
- §3.0.1은 `source`를 원문 ASR 정답, `target`을 번역 자막 정답으로 정의하고 X-1~X-5에서 필수 축·교차 비교 금지·분리 보고·U-31 미해결 시 `unsupported`를 규정한다.
- 해당 문맥과 파일 전체에 잔여 `§3.4` 참조가 없다.
- 실제 diff는 두 주석의 참조만 `§3.4 → §3.0.1`로 바꾸며 계약 필드와 절 구조를 변경하지 않는다.

### 2.3 EVALS §8 scorecard — **해소**

- [EVALS](../EVALS.md) §8은 사람용 scorecard를 `source`와 `target`의 두 블록으로 분리하며 각 블록·행의 축을 식별할 수 있다.
- target 블록은 U-31 미해결 시 블록 전체를 `status: "unsupported"`, 사유 `"U-31 unresolved: target language undetermined"`로 표시한다. 0점이나 결측 평균으로 바꾸지 않는다.
- “번역 품질” 행은 **지표 미정 / TASK-005**로 남아 구체 지표를 선택하지 않는다.
- 두 블록의 합계·평균·가중치·종합 점수를 금지한다.
- 기존 baseline 대비 Δ, 95% CI, 무음 환각률의 방어 지표인 무음 오탐률, 미지원 지표, 계층별 악화 표기가 source 블록에 보존되고 target 블록에도 Δ·95% CI·미지원·계층별 악화 칸이 있다.
- §8의 두 블록은 [ARCHITECTURE](../ARCHITECTURE.md) §7.6 `EvalReport.metrics_by_axis.source/target`과 직접 대응한다.

### 2.4 U-22 범위 — **부분 해소**

해소된 부분:

- [DECISIONS](../DECISIONS.md) U-22는 ASR·번역·재구성 모델/엔진, 실행 방식(로컬/원격), 공급자, 라이선스, 재배포 조건을 모두 결정 범위로 식별한다.
- 실제 모델·API·공급자·실행 방식을 선택하지 않았고 U-22는 측정 뒤 결정할 보류/미결정 상태다.
- U-31은 대상 언어 미해결, U-07은 목표 수치 미해결로 유지된다.

남은 직접 모순:

- [EVALS](../EVALS.md) §4.7(d)는 번역 모델·엔진·실행 방식·**공급자**를 U-22가 측정 뒤 결정한다고 한다.
- DECISIONS U-22도 공급자 선택을 결정 범위에 포함한다.
- 그러나 [ARCHITECTURE](../ARCHITECTURE.md) §7.11의 공급자 중립 표는 “공급자·서비스 이름 — **이 저장소에서 결정하지 않음**”이라고 한다. 이는 U-22가 저장소 결정 기록으로 공급자를 선택할 수 있다는 앞의 두 문서와 결정 주체가 다르다.

따라서 요구 범위 대부분은 맞지만, 세 문서를 대조하면 공급자 결정의 귀속이 하나로 도출되지 않아 **부분 해소**다. 이는 새 독립 지적이 아니라 REVIEW-006 M-01 잔여 4번의 직접 정합성 판정이다.

**M-01 최종 판정: 부분 해소.** 네 항목 중 1~3은 해소, 4는 부분 해소다.

## 3. M-02 잔여 두 항목

### 3.1 실행 그래프의 코드 구현 노드 — **해소**

[PLAN](../../PLAN.md) §3-1d, [STATUS](../../STATUS.md) §4, [TASK-012](../tasks/TASK-012.md) §6, DECISIONS §4.1.3에서 다음 여섯 노드가 동일하게 도출된다.

| 노드 | 선행 | U-31 차단 |
|---|---|---|
| TASK-003 | 없음 — 지금 착수 가능 | 아니오 |
| 사람 U-06 선택 | TASK-003 결과 | 아니오 |
| 사람 U-31 답변 | 없음 — 독립 게이트 | — |
| TASK-005 | TASK-003·U-06·U-31 모두 | 예 |
| TASK-006 | TASK-005 | TASK-005를 통해 |
| 코드 구현 | TASK-006까지 완료 | TASK-005를 통해 간접적으로 |

- DECISIONS §4.1.3에 코드 구현 행이 실제로 있고 선행은 TASK-006까지 완료다.
- 기존 다섯 노드와 U-31의 “TASK-005부터 차단, TASK-003 비차단” 범위는 바뀌지 않았다.
- 네 문서 모두 계획을 제안됨/검토 중/확정 아님으로 유지한다.

### 3.2 STATUS의 HEAD·판정·반영 상태 — **해소**

- `f001ace…`는 REVIEW-005 이후의 **최초 실질 수정 커밋**으로만 설명되고 “새 HEAD”·“현재 HEAD”로 불리지 않는다.
- 다음 제한 재검토 대상은 PR #5의 현재 HEAD / 대상 브랜치의 최신 HEAD로 표현된다.
- REVIEW-005의 변경 요청, REVIEW-006의 부분 해소·변경 요청, Source Owner의 “잔여 항목 대응 완료” 주장, 아직 없던 이번 재검토 결과가 서로 다른 행과 문서로 분리된다.
- TASK-012는 `In review`이며 “잔여 항목 대응 완료, 제한 재검토 대기”다.
- TASK-014와 REVIEW-006의 blob은 수정 커밋에서도 원문 그대로다.
- GitHub의 실제 PR #5는 Open / Draft / 미병합으로 이 상태 서술과 모순되지 않는다.

**`STATUS.md`의 `f001ace…` 표기 판정:** 실질 수정 커밋 식별자로 문맥상 명확하며 실제 고정 HEAD `b57df672…`와 충돌하지 않는다. REVIEW-006이 지적한 “새 HEAD” 오도는 해소됐다.

**M-02 최종 판정: 해소.** 두 항목 모두 해소됐고 수정 범위 안의 직접 모순이 없다.

## 4. 실제 수정 diff와 범위

`15a47eb… → b57df67…`는 정확히 1커밋·5파일·+142/−17이다.

| 파일 | + | − | 범위 |
|---|---:|---:|---|
| `STATUS.md` | 9 | 5 | REVIEW-006 이력·반영 상태·현재 검토 대상 정렬 |
| `docs/ARCHITECTURE.md` | 2 | 2 | 계약 참조 두 곳 |
| `docs/DECISIONS.md` | 4 | 3 | ADR-0011·U-22·코드 구현 노드 |
| `docs/EVALS.md` | 26 | 1 | §8 scorecard |
| `docs/tasks/TASK-012.md` | 101 | 6 | REVIEW-006 기록과 잔여 대응·인계 |
| **합계** | **142** | **17** | |

REVIEW-005·REVIEW-006, TASK-013·TASK-014, PLAN, PRODUCT_SPEC, AGENTS, README, CLAUDE는 이 수정 커밋에서 바뀌지 않았다. 코드·의존성·CI·모델·데이터셋·비밀정보 추가는 없다.

## 5. 확인하지 못한 항목

- Source Owner 세션의 현재 실행 여부는 GitHub에서 확인할 수 없다.
- PR 본문 revision history와 과거 force-push 전무 여부의 전체 감사 로그는 확인하지 못했다.
- 로컬 저장소·working tree 상태는 커넥터 중심 검토의 증거로 사용하지 않았다. 보완용 `gh`는 이 환경에 설치되어 있지 않았다.
- 모델·데이터셋·번역 품질 지표의 실제 적합성과 구현 충분성은 이번 제한 범위 밖이다.
- 저장소 밖에서 U-31·U-07·U-22가 별도로 결정됐는지는 확인하지 않았다. 고정 HEAD의 기록만 판정했다.

## 6. 최종 판정

**변경 요청.** M-02는 해소됐지만 M-01의 U-22 범위가 부분 해소이므로 승인 조건을 충족하지 않는다.

Source Owner는 TASK-015·REVIEW-007 원문을 먼저 별도 기록 커밋으로 통합한 뒤, M-01 잔여 4번의 공급자 결정 귀속만 별도 커밋으로 일치시켜 새 HEAD에서 그 모순만 제한 재검토로 인계할 수 있다. 병합 여부는 사람 제품 오너가 결정한다.
