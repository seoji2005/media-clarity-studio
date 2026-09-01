# AGENTS.md — 공용 작업 규칙 (Authoritative)

이 문서는 `media-clarity-studio`에서 활동하는 **모든 행위자**(사람 제품 오너,
Lean Root Orchestrator, Codex 작성·리뷰 세션, 제한적으로 호출되는 Claude specialist,
제품·아키텍처 자문 세션)가
따르는 **규칙의 단일 출처(single source of truth)** 입니다.

- 다른 문서(`CLAUDE.md`, 각 `docs/tasks/TASK-*.md`)와 내용이 충돌하면 **이 문서가 이깁니다.**
- 규칙을 바꾸려면 이 문서를 수정하는 PR을 올려야 합니다. 대화나 커밋 메시지로만 바꿀 수 없습니다.
- 에이전트는 작업을 시작하기 전에 이 문서를 **처음부터 끝까지** 읽습니다.

마지막 갱신: 2026-08-31 (TASK-030, ADR-0029 — GPT-primary 운영 계약)

> **이 변경이 `main`에 merge된 뒤 시작하는 작업의 운영 구조는 TASK-030·ADR-0029와 §3을 따릅니다.**
> GPT/Codex가 기본 작업·검증 자원이며 Claude는 §3의 폐쇄형 trigger에서만 사용합니다.
> Lean Root의 병합은 사람 제품 오너가 특정 PR과 고정 HEAD를 명시적으로 승인한 뒤의
> 일반 merge로만 허용됩니다. 진행 중인 PR은 시작 당시 계약과 소유권을 유지합니다.
> TASK-007·027, ADR-0027·0028과 과거 수행 기록은 완료된 역사로 보존하며 미래 배정 근거로 쓰지 않습니다.

---

## 0. 이 프로젝트에서 절대 어기면 안 되는 것

**이 규칙들은 모든 AI 행위자(GPT/Codex 세션·서브에이전트·Claude 세션)에 적용됩니다.**
사람 제품 오너의 권한은 §0.1에 따로 적습니다.

| # | 규칙 | 이유 |
|---|---|---|
| R1 | **어떤 AI도 병합을 결정·승인하거나 `main`에 직접 커밋·push하지 않는다. Claude와 별도 Codex 작성/review 세션은 merge를 실행하지 않는다. Lean Root만 독립 reviewer 판정과 사람 제품 오너의 정확한 승인 뒤 `expected_head_sha`를 고정한 일반 merge를 기계적으로 실행할 수 있다. Lean Root가 Author였어도 이 기계적 실행은 review 판정이 아니며 같은 독립 reviewer·오너 승인 조건을 생략할 수 없다.** | 검토 없는 자동 병합과 승인 후 HEAD 변경을 막음 |
| R2 | **기존 사용자 콘텐츠를 삭제·축소하지 않는다.** 확장만 한다. | 사람이 쓴 내용이 조용히 사라지면 안 됨 |
| R3 | **재구성 결과를 "원본 복원"이라고 표현하지 않는다.** | 사실이 아니며, 학술적·상업적으로 위험한 주장 |
| R4 | **비밀정보(API 키, 토큰, 자격증명)를 저장소에 넣지 않는다.** | 되돌릴 수 없는 유출 |
| R5 | **모르는 것을 추측으로 채우지 않는다.** 문서에 "미해결"로 남긴다. | 잘못된 전제가 아래 단계 전부를 오염시킴 |
| R6 | **하나의 TASK에는 수행 소유자(Owner)가 정확히 한 명이다.** | 동시 편집 충돌·중복 작업 방지 |
| R7 | **에이전트 간 인계는 저장소 파일과 PR 설명으로만 한다.** | 서로의 대화 기록에 접근할 수 없음 |
| R8 | **리뷰가 필요한 변경의 작성자와 reviewer는 서로 다른 행위자 또는 fresh 세션이어야 한다.** reviewer가 대상 파일을 고치면 작성자가 되어 새 reviewer가 필요하며, 누구도 자기 변경에 승인 판정을 내리지 않는다. | 자기 검토는 검토가 아님 |
| R9 | **두 세션이 같은 파일을 동시에 수정하지 않는다.** 파일 소유는 TASK 단위로 배타적이다. | 동시 편집은 조용한 덮어쓰기를 만듦 |
| R10 | **완료 보고를 그대로 믿지 않는다.** 가능한 경우 GitHub 상태(브랜치 HEAD·PR 상태)와 diff로 확인한다. | "했다"는 주장이지 사실이 아님 |

R1–R10은 사람 제품 오너의 명시적 지시 없이는 예외가 없습니다.

**TASK-030 R2 예외:** 사람 제품 오너가 2026-08-31 운영 Markdown 최적화와 중복 축약을 명시적으로
지시했습니다. 따라서 에이전트가 작성한 과거 current/future 역할표는 `AGENTS.md` 링크로 축약할 수 있습니다.
완료된 역사 기록과 `README.md` 최초 2줄은 계속 보존합니다.

### 0.1 사람 제품 오너의 권한과 승인 경계

| 행위 | GPT/Codex 작성 세션 | 독립 reviewer | Lean Root | 사람 제품 오너 |
|---|---|---|---|---|
| 코드·비코드 작성 | 배정 범위에서 가능 | 대상 브랜치 수정 금지 | 배정하거나 직접 작성 가능 | 가능 |
| 검증·리뷰 | 자기 변경 승인 금지 | **고정 HEAD 제한 검토** | 검증 조정, 직접 작성하지 않은 변경 검토 | 최종 제품 판단 |
| PR 생성·Ready 전환 | 가능 | 리뷰 PR만 가능 | 가능 | 가능 |
| PR 병합 | 금지 | 금지 | **오너의 특정 PR·고정 HEAD 승인 후 일반 merge만 가능** | 가능 |
| `main` 직접 커밋 | 금지 | 금지 | 금지 | 가능하나 권장하지 않음 |
| 미해결 제품 항목 확정 | 금지 (R5) | 금지 (R5) | 선택지·권고만 | **가능** |
| 규칙 변경 | 제안 | 제안 | 제안·문서화 | **승인** |

> R1의 목적은 검토 없는 자동 병합을 막는 것입니다. `진행`은 다음 안전 단계 승인이고,
> Lean Root가 제시한 approval capsule의 PR 번호·전체 HEAD SHA·reviewed base SHA에 바로 이어진
> 제품 오너의 명시적 `승인`만 병합 승인입니다.
> 승인 뒤 HEAD 또는 base가 바뀌면 멈추고 delta·merge result를 확인한 뒤 다시 승인받습니다.

### 0.2 에이전트 문서 읽기 순서 (모든 세션 공통)

**어떤 작업이든 1~3은 전부 읽고, 4~7은 TASK가 참조하거나 변경하는 절만 읽습니다.**

```
1. AGENTS.md                  ← 규칙. 항상 먼저
2. STATUS.md                  ← 지금 상태와 소유권
3. docs/tasks/TASK-XXX.md     ← 내가 할 일
4. docs/PRODUCT_SPEC.md       ← 관련 제품 경계만
5. docs/ARCHITECTURE.md       ← 관련 계약·모듈만
6. docs/EVALS.md              ← 관련 평가 규칙만
7. PLAN.md · docs/DECISIONS.md ← 관련 순서·근거만
```

`README.md`와 `CLAUDE.md`는 진입 안내이며 규칙의 출처가 아닙니다. 같은 세션에서 SHA가 바뀌지 않은
문서는 다시 읽지 않고, 재검토는 이전 고정 HEAD와 새 HEAD의 delta부터 확인합니다.

**새 Work 세션 복원:** 이전 대화를 붙여 넣지 않습니다. 아래 호출문으로 시작한 뒤 live `main`과 열린 PR의
base·HEAD·상태를 확인하고, live `main`의 이 파일 전체 → `STATUS.md` 전체 → 선택한 PR의 TASK 전체를 읽습니다.

`Use $media-clarity-orchestrator. Continue seoji2005/media-clarity-studio from live repository and PR facts. Use ChatGPT Pro at consequential product/architecture checkpoints and use bounded read-only subagents for orthogonal evidence when useful. Do not assume or paste prior conversation history; reconstruct state and take only the next safe action.`

그 뒤 `main / PR별 base·HEAD·TASK·Gate·Author·Reviewer·마지막 reviewed HEAD / blocker / Pro checkpoint /
next allowed action / forbidden now`를 한 execution card로 만들고 다음 안전 행동 하나만 고릅니다. 이 호출은
상태 복원과 이미 허용된 범위의 다음 행동만 승인하며 merge·dependency/model·network egress·파괴 행위를 승인하지 않습니다.

---

## 1. 용어 정책 (Terminology Policy)

영상 화질 개선 기능은 **원본을 아는 상태에서의 복구가 아닙니다.** 다음 표현 규칙을 지킵니다.

**사용해야 하는 표현**

- 재구성(reconstruction), 추정(estimation), 보강(enhancement), 그럴듯한 추정치(plausible estimate)
- "모자이크 영역을 **주변 정보와 학습된 사전지식으로 추정**하여 재구성했습니다"
- "이 결과는 원본과 다를 수 있습니다"

**사용하면 안 되는 표현**

- 복원 완료, 원본 복구, 원본과 동일, 모자이크 제거 성공, "지워진 정보를 되찾았다"
- 정확도를 암시하는 단정 (예: "정확히 복원됨")

**적용 범위:** 문서, UI 문구, 로그, 예외 메시지, 코드 주석, 변수·함수 이름, **모듈·어댑터 이름**,
커밋 메시지, PR 제목/본문.

**식별자 명명 규칙 (ADR-0026)**

| ❌ 쓰지 않음 | ✅ 사용 |
|---|---|
| `restore` (모듈명) | `reconstruct` |
| `RestoreAdapter` | `ReconstructionAdapter` |
| `restore_original()` | `reconstruct_region()` / `estimate_detail()` |
| `recovered_frame` | `estimated_frame` |

> 문서에서는 "재구성"이라 쓰면서 코드 식별자는 `restore`인 상태를 허용하지 않습니다.
> 용어 정책은 산문과 식별자에 **동일하게** 적용됩니다.

**R2에 의한 보존 예외 — 고치지 마십시오**

| 예외 | 왜 예외인가 |
|---|---|
| `README.md`의 **최초 2줄** (제목 + `Local-first multilingual subtitle generation and AI-assisted media restoration studio.`) | 사람이 최초 커밋(`968a105`)에 쓴 콘텐츠입니다. **R2(기존 사용자 콘텐츠 삭제·축소 금지)가 §1보다 우선**합니다 |
| GitHub **저장소 description** (같은 문구) | 같은 이유. 저장소 설정은 사람 오너의 것입니다 |

> 두 곳의 `restoration` 표현은 **R2에 따라 보존되는 역사적 예외이며, 수정 대상이 아닙니다.**
> §1을 근거로 이 두 곳을 "고치면" **R2를 위반**합니다 (REVIEW-002 R-12).
> 예외는 이 두 곳뿐입니다. **새로 쓰는 문장에는 §1이 그대로 적용됩니다.**
> 저장소 description의 변경 여부는 **사람 제품 오너만** 판단합니다.

**윤리적 경계:** 모자이크/블러 재구성은 **화질 개선 목적**에 한정합니다.
특정 인물의 신원 식별, 검열된 정보의 강제 노출을 목적으로 하는 기능은 제품 범위 밖입니다
([`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) 비목표 참조).

---

## 2. 언어 정책 (Language Policy)

- **사람이 읽는 설명 문장은 한국어**로 씁니다. (문서 산문, PR 설명, 리뷰 코멘트, UI 문구)
- 다음은 **영어를 유지**합니다.
  - 파일명·디렉터리명 (`docs/EVALS.md`, `TASK-001.md`)
  - 명령어 (`git switch -c`, `ffmpeg -i`)
  - 코드 식별자 (함수·변수·클래스·모듈 이름)
  - 정착된 기술 용어 (ASR, VAD, diarization, WER, PSNR, SSIM, LPIPS, code-switching, PR, CI …)
- 정착된 기술 용어는 **처음 등장할 때만** 괄호로 한국어 설명을 덧붙입니다. 매번 번역하지 않습니다.
- 커밋 메시지 제목은 **영어**(Conventional Commits), 본문은 한국어 허용. (§5 참조)

---

## 3. 역할과 소유권 (운영 구조)

**이 절이 향후 모든 배정의 기준입니다** (ADR-0029).

| # | 역할 | 주체 | 책임 | 저장소 변경 |
|---|---|---|---|---|
| — | **제품 오너** | 사람 | 제품 행동·우선순위·위험 수용·외부 비용·최종 병합 승인 | 가능 |
| 1 | **Lean Root Orchestrator** | GPT Work / Codex Work | 상태 복원, 다음 TASK 선택, 계약·배정, 조사·검증 조정, 오너 인계, 승인 후 통합 | 배정 시 코드·비코드 가능 |
| 2 | **Codex 작성 세션** | Root 또는 별도 Codex 세션 | 작은 범위의 코드·테스트·문서 구현과 직접 검증. 한 브랜치·배타적 파일 소유 | 배정 범위만 |
| 3 | **독립 reviewer** | 작성자와 다른 fresh GPT/Codex 세션; 필요 시 Claude | 고정 HEAD·TASK·diff·직접 회귀만 검토 | 대상 브랜치 수정 금지 |
| 4 | **ChatGPT Pro adviser** | 별도 자문 대화 | 중요한 계약·제품/아키텍처 선택·측정 milestone 방향에 대한 반론과 권고 | 하지 않음 |
| 5 | **Claude Code specialist** | Claude Code | §3의 폐쇄형 trigger에 해당하는 구현·cross-model 검토·교착 해소 | 배정 범위만 |
| 6 | **Claude adviser** | Claude 대화 | trigger가 기록된 아키텍처 자문·두 번째 의견 | 하지 않음 |

- TASK Owner는 수행 소유자 한 세션입니다. 복수 작성자가 필요하면 파일 경계가 겹치지 않는 별도 TASK로 나눕니다.
- 변경마다 Lean Root의 역할을 `Orchestrator` 또는 `Author` 중 하나로 기록합니다. Author이면 그 변경의 reviewer가 될 수 없습니다.
- Lean Root가 직접 작성하고 독립 리뷰가 필요한 작업이면 시작 전에 reviewer를 지정합니다.
  Root가 reviewer이면 대상 변경을 직접 고치지 않습니다.
- ChatGPT Pro adviser와 서브에이전트는 결정을 대신하거나 최종 승인하지 않습니다. 결과는 Root가 저장소 사실과 대조합니다.
- Claude는 다음 중 하나를 execution card 또는 PR에 기록한 경우에만 호출합니다.
  1. 시작 당시 계약이 Claude 소유로 고정된 진행 중 작업
  2. 제품 오너가 TASK·역할·범위를 명시해 요청
  3. 결정 gate가 닫힌 같은 객관적 결함을 GPT가 제한 수정으로 두 번 해결하지 못함
  4. GPT가 작성한 Gate S 변경의 cross-model 검토
  5. 독립 증거와 표적 테스트 뒤에도 Gate H의 구체적 blocker가 남음
  6. 한 차례 근거 교환 뒤에도 기술적 교착이 남음
- 복잡해 보인다는 인상, 일반 상태 갱신, 반복 테스트, 첫 보통 실패는 Claude trigger가 아닙니다.
- 3번 trigger는 두 attempt의 HEAD·결함·표적 테스트를 기록하고 세 번째 GPT 반복을 금지합니다.
  Gate S는 Author와 다른 모델의 fresh reviewer가 필수이며, 확보하지 못하면 Gate를 낮추지 않고 `Blocked`로 둡니다.

**ChatGPT Pro feedback checkpoint**

Root는 다음 세 지점에서 Pro 자문을 적극 사용합니다.

1. evidence lineage, cache/resume, privacy, model/dependency 또는 12 GB 경계를 바꾸는 Gate H/S 계약 고정 전
2. 사람 수정시간·누락/환각·end-to-publish·로드맵에 다른 영향을 주는 현실적 제품/아키텍처 대안 선택 전
3. calibration·10분 vertical slice·phase milestone의 측정 결과로 다음 방향을 고르기 전

직접 Pro 호출 수단이 없으면 Root가 질문 하나, 대안 최대 3개, hard gate, SHA로 확인한 사실·측정값,
불확실성 최대 5개만 담은 자문 packet을 만들고 제품 오너가 별도 Pro 대화에서 실행할 수 있게 합니다.
권고·위험 최대 5개·최소 판별 실험·번복 조건을 요청하며 같은 SHA의 같은 질문을 합의 목적으로 반복하지 않습니다.
Pro 답변은 저장소 사실·formal review·제품 오너 결정·dependency/model/network 승인 중 어느 것도 대체하지 않습니다.

### 3.1 작성자와 리뷰어의 분리 (R8)

- 작성자가 아닌 Lean Root는 기본 reviewer가 될 수 있습니다. Lean Root가 작성자이면 fresh reviewer를 지정합니다.
- formal fresh reviewer는 Author의 서브에이전트가 아닌 새 세션이며 고정 HEAD·TASK·이전 finding으로 시작합니다.
  Author의 완료 보고는 증거가 아닙니다.
- reviewer는 완료 보고를 증거로 쓰지 않고 고정 HEAD·diff·명령 출력·artifact를 직접 확인합니다.
- reviewer가 대상 파일을 수정하면 그 순간 작성자가 됩니다. 새 HEAD에는 새 reviewer가 필요합니다.
- Gate L/M은 근거를 공개하고 별도 REVIEW 문서를 생략할 수 있지만, 작성자가 자기 변경에 승인 판정을 내릴 수는 없습니다.
- 어느 행위자도 자기 변경에 최종 `승인` 판정을 내리지 않습니다.

### 3.2 위험 기반 리뷰 Gate

| Gate | 예 | 필수 절차 |
|---|---|---|
| **L** | 오탈자·단순 문구·비동작 문서 | 직접 수정, 최소 정적 확인, 별도 REVIEW 생략 가능 |
| **M** | 내부 로직·UI 동작·오류 처리·운영 계약 | 합격 사례, 관련 테스트/문서 검사, diff 검토, 영향 범위 회귀. 필요할 때만 추가 독립 리뷰 |
| **H** | 데이터 구조·파일 형식·복구·외부 인터페이스·FFmpeg/DB/모델 | 설계·불변식, 구현/리뷰 분리, 고정 HEAD, fixture 직접 재현, 전체 회귀, 롤백 확인 |
| **S** | 삭제·덮어쓰기·개인정보·비밀정보·배포·결제·원격 데이터 변경 | Gate H 전부, 실패 주입, 복구 rehearsal, 사람 승인, 실행 직전 대상 재확인 |

- 현재 TASK/REVIEW 문서 방식은 Gate H/S에 집중합니다. Gate L/M에 같은 무게를 강제하지 않습니다.
- `AGENTS.md`의 권한·R1·R8·병합 경계를 바꾸는 운영 계약은 Gate M이어도 고정 HEAD 독립 리뷰가 필수입니다.
- Gate S는 항상 cross-model review입니다. GPT/Codex Author이면 Claude, Claude Author이면 fresh GPT/Codex가
  검토합니다. reviewer가 패치하면 새 cross-model reviewer가 필요하며, 확보하지 못하면 `Blocked`입니다.
- 반복 가능한 판정은 REVIEW 문장보다 테스트 → lint/정적 검사 → 검증 스크립트 → 타입/스키마 순으로 자동화합니다.
- 독립 리뷰는 해당 변경과 직접 회귀만 봅니다. 제한 재검토를 프로젝트 전체 재검토로 확대하지 않습니다.

### 3.3 리뷰어의 권한 경계

독립 reviewer는 다음을 할 수 있습니다.

- PR의 고정 HEAD·base·diff·검증 상태 조회
- 안전한 검증 명령 직접 실행과 artifact 확인
- PR 코멘트·리뷰 판정 및 필요한 최소 REVIEW/STATUS 기록
- PR 코멘트와 `승인` / `변경 요청` / `차단` 판정

리뷰 대상 코드·테스트·문서를 직접 수정하지 않습니다. 변경 요청은 작성 Owner에게 반환합니다.
환경 차단은 제품 결함과 구분하며 TASK/REVIEW 번호를 소비하지 않습니다.

### 3.4 동시 편집과 직렬화 (R9)

- 쓰기 작업은 동시에 최대 2개이며 같은 파일·인터페이스를 동시에 수정하지 않습니다.
- GPU benchmark·실제 모델 실행은 동시에 1개만 수행합니다.
- `STATUS.md`는 coordination point입니다. 리뷰 중 작성자가 같은 상태 행을 수정하지 않습니다.
- 서브에이전트는 읽기·반례·테스트 설계처럼 서로 겹치지 않는 질문 하나만 맡습니다. 기본값은 read-only이며,
  최종 판정·병합·공유 파일 쓰기를 맡기지 않습니다. formal reviewer는 작성자의 서브에이전트로 대체할 수 없습니다.
- 위험도별 기본 수(Lean Root 제외)는 Gate L 0명, Gate M 1명, Gate H 2명, Gate S 3명입니다.
  다중 외부 근거·cross-contract 제품 판단은 2명으로 시작하고 독립 privacy/제3 도메인이 있을 때만 1명을 더합니다.
  단순 상태 조회·push·명백한 한 파일 수정, 앞 결과가 필요한 순차 작업에는 사용하지 않습니다.
- 각 요청에는 exact HEAD·경로·질문 하나·비범위를 주고, 답은 결론 한 줄과 근거 있는 finding 최대 5개로 제한합니다.
  Root가 결과를 하나의 판정 목록으로 중복 제거하며 같은 질문의 다수결을 만들지 않습니다.
- 리뷰 지적은 먼저 보존하고, 그 다음 작성 Owner가 별도 커밋으로 수정합니다.
- 충돌은 해당 Source Owner가 해결하고 Lean Root가 최종 diff를 확인합니다.

### 3.5 검증 원칙 (R10)

**"완료했다"는 주장이며 사실이 아닙니다.** 다음 담당자와 리뷰어는 가능한 범위에서 실물을 확인합니다.

| 주장 | 확인 방법 |
|---|---|
| "push 했다" | 원격 브랜치 HEAD SHA 확인 |
| "PR을 갱신했다" | PR 본문과 상태(Open / Draft / 병합 여부) 확인 |
| "N개 파일을 바꿨다" | `git diff --stat` 또는 PR의 변경 파일 목록 |
| "지적을 반영했다" | diff에서 해당 위치를 직접 확인 |

확인하지 못한 것은 **"확인하지 않음"이라고 적습니다.** 확인한 것처럼 적지 않습니다.

**토큰·검증 예산**

- 작업 시작 시 `base SHA / PR / head SHA / TASK / Gate / Owner / Reviewer / blocker / next action`의
  execution card를 먼저 고정합니다.
- 큰 파일보다 identity·diffstat·변경 경로를 먼저 보고, 이미 읽은 같은 SHA의 문서는 재독하지 않습니다.
- 검증은 `identity·scope → focused test → TASK/module test → 전체 회귀 1회` 순서입니다.
  실패 원인이 바뀌지 않았는데 전체 회귀를 반복하지 않습니다.
- 재검토는 `old_head..new_head`, 이전 지적, 직접 회귀만 봅니다. 전체 diff·fixture·로그 덤프를 인계에 복사하지 않습니다.
- 판정 목록은 하나만 유지합니다. 서브에이전트 결과는 Root가 중복 제거한 뒤 그 목록에 합칩니다.

**용어 주의 — "Owner"는 "구현자"가 아닙니다**

TASK의 산출물은 코드일 수도, 문서일 수도, **리뷰 보고서일 수도** 있습니다.
따라서 Owner는 **수행 소유자**입니다. 리뷰 TASK의 Owner는 그 리뷰를 수행하는 세션이며,
그 TASK의 Reviewer는 **리뷰 결과물을 검토하는** 다른 세션입니다.

**소유권 기록**

정식 TASK의 소유권은 `docs/tasks/TASK-XXX.md` 머리말과 [`STATUS.md`](STATUS.md) 보드 양쪽에 기록합니다.
두 곳이 다르면 **`docs/tasks/TASK-XXX.md`가 정답**입니다. TASK를 생략한 Gate L/M 작업은 PR 설명이 계약입니다.

---

## 4. 브랜치 규칙

```
<agent>/<short-slug>-<suffix>
```

- `claude/…` — Claude Code 구현 세션이 소유한 코드 작업
- `claude-review/…` — 추가 독립 Claude Code 리뷰 세션
- `codex/…` — Codex 작성 세션이 소유한 작업
- `codex-review/…` — 작성자와 다른 fresh Codex 리뷰 세션
- `lean-root/…` — Lean Root가 Author인 배정 작업 또는 리뷰·통합 준비 작업
- `human/…` — 사람이 직접 작업

예: `codex/task-031-correction-ledger`, `codex-review/task-031-rereview`, `lean-root/workflow-contract`

규칙:

1. 브랜치는 **최신 `main`에서 분기**합니다.
   단, **리뷰 브랜치는 리뷰 대상 브랜치에서 분기**합니다 (대상 문서가 `main`에 없을 수 있음).
2. **하나의 브랜치 = 하나의 작업 단위.** 정식 TASK가 있으면 하나의 브랜치에 하나만 담습니다.
3. 다른 세션이 소유한 브랜치에 push하지 않습니다. 리뷰 세션은 **리뷰 대상 브랜치에 커밋하지 않습니다** (§3.3).
4. `main`은 항상 병합 대상일 뿐, 작업 대상이 아닙니다. (R1)
5. 담당 PR이 이미 병합되었다면, 후속 작업은 **최신 `main`에서 다시 시작**합니다.
   병합된 이력 위에 새 커밋을 쌓지 않습니다.

### 4.1 리뷰와 통합 수명주기

1. 작성 Owner는 최신 `main`에서 배타적 브랜치와 PR을 만듭니다.
2. reviewer는 PR의 base/head를 고정하고 TASK 계약·diff·직접 검증을 교차 확인합니다.
3. 변경 요청이면 작성 Owner가 제한된 별도 커밋으로 반영합니다.
4. 재검토는 새 HEAD에서 이전 지적과 직접 회귀만 확인합니다.
5. 사람 제품 오너가 PR 번호·전체 HEAD SHA·reviewed base SHA를 지정해 병합을 명시적으로 승인합니다.
6. Lean Root는 승인된 HEAD와 base가 그대로일 때만 `expected_head_sha`를 사용해 일반 merge합니다.
   base가 한 번이라도 이동하면 멈추고 base delta와 merge result를 독립 확인한 뒤 재승인받습니다.
7. 병합 뒤 PR 종료 상태와 최신 `main`을 확인합니다.

새 운영 계약은 운영 PR의 merge commit 이후 시작하는 작업에 적용합니다. 진행 중 PR은 시작 당시
Author·Reviewer·remediation 소유권을 유지하고, 변경하려면 제품 오너가 명시적으로 종료·재배정합니다.

Gate L/M은 별도 리뷰 브랜치·REVIEW 문서를 생략할 수 있습니다. Gate H/S은 필요한 리뷰 증거와
복구 경계를 저장소에 남깁니다. 리뷰 원문을 보존해야 할 때는 의미상 수정하지 않습니다.

---

## 5. 커밋 규칙

Conventional Commits 형식을 사용합니다. **제목은 영어, 72자 이내.**

```
docs: add architecture and evaluation foundation

- 모듈 경계와 인터페이스 계약 정의
- 합성 열화 기반 평가 전략 추가
```

허용 type: `docs`, `feat`, `fix`, `refactor`, `test`, `chore`, `eval`, `spec`

금지 사항:

- 관련 없는 변경을 한 커밋에 섞기
- 생성 모델 이름·버전을 커밋 메시지에 남기기
- 대용량 바이너리(모델 가중치, 샘플 영상) 커밋 — §8 참조

---

## 6. TASK 프로토콜

정식 TASK는 다음 중 하나에 해당할 때 만듭니다.

- 사용자 행동 또는 외부 계약 변경
- 둘 이상의 모듈 변경
- 데이터 구조·호환성·복구·보안·개인정보·외부 서비스 영향
- 복수 단계 검증이 필요하거나 다음 세션까지 이어지는 작업

작은 문구·내부 정리·명백한 단일 버그는 PR/이슈 계약과 회귀 테스트로 처리할 수 있습니다.
정식 TASK 파일에는 다음이 **반드시** 들어갑니다.

| 항목 | 설명 |
|---|---|
| `ID` | `TASK-001` 형식, 3자리, **재사용 금지**. [`STATUS.md`](STATUS.md) §4에 후보로 예약된 번호도 사용된 것으로 봅니다. 새 TASK는 **어디에도 쓰이지 않은 다음 번호**를 씁니다 |
| `Owner` | 수행 소유자 하나. Root가 작업 성격·용량·독립성에 따라 Lean Root, Codex 또는 Claude specialist 중 배정 |
| `Reviewer` | Owner와 다른 행위자/세션. Gate L/M에서 추가 독립 리뷰를 생략하면 `없음 (§3.2)`과 근거를 적습니다 |
| `Phase` | [`PLAN.md`](PLAN.md)의 단계 |
| `Status` | `Not started` / `In progress` / `In review` / `Blocked` / `Done` |
| `목표` | 이 작업이 끝났을 때 존재하게 되는 것 |
| `범위 밖` | 명시적으로 하지 않을 것 |
| `산출물` | 생성/수정될 파일 목록 |
| `완료 조건` | 객관적으로 확인 가능한 체크리스트 |
| `인계 메모` | 리뷰어/다음 담당자가 알아야 할 것 |

**작업 흐름 — 선형 목록이 아니라 상태 그래프입니다**

작업은 한 방향으로 흐르지 않습니다. 리뷰가 `변경 요청`이면 되돌아오고,
사람만 답할 수 있는 질문이 나오면 앞 단계에서 멈춥니다. 그래서 **상태와 전이**로 적습니다.

```
                    ┌──────────────────────────────────────────┐
                    │                                          │
                    ▼                                          │
            ┌───────────────┐  차단 질문 있음                    │
   시작 ──▶ │ Decision gate │ ────────────▶ (사람 오너 답변 대기) │
            └───────┬───────┘                                   │
                    │ 차단 질문 없음                              │
                    ▼                                           │
            ┌───────────────┐                                   │
            │  Task ready   │  계약·Owner·배타적 파일 범위 확정      │
            └───────┬───────┘                                   │
                    ▼                                           │
            ┌───────────────┐                                   │
            │  Implementing │  주 세션 작업 ─── 차단 질문 발견 ─────┘
            └───────┬───────┘
                    ▼
            ┌───────────────┐
            │   Verifying   │  GitHub HEAD·diff·PR 상태 확인 (R10)
            └───────┬───────┘
                    │ 불일치 ──────────────▶ Implementing 으로 복귀
                    ▼
            ┌───────────────┐
            │  Review gate  │  §3.2로 Gate와 독립 리뷰 필요 여부 판정
            └───┬───────┬───┘
 Gate H/S(필요) │       │ Gate L/M + 판정 근거 기록
                ▼       │
      ┌──────────────────┐ │
      │Independent review│ │  작성자와 다른 세션이 고정 SHA 검토
      └───┬──────────┬───┘ │
   변경요청│          │승인 │
          ▼          ▼     ▼
   ┌─────────────┐  ┌────────────────┐
   │ Remediating │  │ Owner decision │  사람이 병합 여부 결정 (R1)
   └──────┬──────┘  └───────┬────────┘
          │                 │ 병합 또는 명시적 종료
          └──▶ Verifying    ▼
                      ┌──────────┐
                      │   Done   │
                      └──────────┘
```

**상태의 뜻**

| 상태 | 무엇을 하는가 | 누가 |
|---|---|---|
| **Decision gate** | 사람만 답할 수 있는 결정이 남아 있는지 확인 (R5) | Lean Root → 사람 오너 |
| **Task ready** | TASK 필요 여부, Owner 1명, 배타적 파일 범위 확정 | Lean Root |
| **Implementing** | 배정된 코드·비코드 범위만 작업 | 해당 Owner |
| **Verifying** | 원격 HEAD·diff·명령·artifact를 실물로 확인 | 작성자와 Root |
| **Review gate** | §3.2의 Gate와 독립 리뷰 필요 여부 판정 | Lean Root |
| **Independent review** | 작성자와 다른 fresh 세션이 고정 SHA 검토 | 지정 reviewer |
| **Remediating** | 지적 범위만 별도 커밋으로 반영 | 작성 Owner |
| **Owner decision** | 병합 여부와 위험 수용 결정 | **사람 제품 오너** |
| **Done** | 사람의 병합·명시적 종료 또는 이미 승인된 결정 전사 완료 후 도달 | — |

> 리뷰 `승인`만으로는 `Done`이 아닙니다. 일반 구현 작업은 사람 오너의 병합 또는 명시적 종료가
> 필요합니다. 제품 오너가 이미 확정한 결정만 기록하는 TASK는 결정 승인 근거를 명시하면 전사 완료로
> `Done`이 될 수 있으며, 저장소 반영 여부는 PR 상태로 별도 확인합니다.

**각 전이가 저장하는 상태값** — TASK 파일과 PR 설명에 **모두** 기록합니다.

| 상태값 | 예 |
|---|---|
| 대상 SHA | `941410c2be2cba33c48d541415d24701b28bcf9a` (전체 SHA) |
| Owner / Reviewer | 서로 다른 행위자·세션 (R8) |
| TASK 상태 | `Not started` / `In progress` / `In review` / `Blocked` / `Done` |
| 차단 질문 | `U-08`, `U-11` (없으면 "없음") |
| 리뷰 필요 여부와 근거 | 필요 — Gate H 외부 인터페이스 변경 (§3.2) |
| 리뷰 판정 | `승인` / `변경 요청` / `차단` |
| 리뷰 산출물 브랜치·커밋 | `codex-review/<slug>` @ `<SHA>` |
| 다음 허용 행동 | 예: "Remediating — 대상 문서만 수정, 병합 금지" |

**주체 주의 (R-10)**

- Lean Root는 상태 복원·TASK 계약·배정·검증 조정·오너 인계·승인 후 통합을 담당합니다.
- 작성 Owner는 코드·테스트·fixture·문서 중 배정된 범위만 담당합니다. Claude 사용은 §3의 trigger를 만족해야 합니다.
- 작성자는 자기 변경을 승인하지 않습니다. Gate H/S은 반드시 다른 행위자/세션이 고정 HEAD를 검토합니다.

TASK 범위를 벗어나는 문제를 발견하면 **그 자리에서 고치지 말고** 새 TASK 후보로 기록합니다
(`STATUS.md`의 "발견된 후속 작업" 절). 범위 확장은 소유자의 재량이 아닙니다.

### 6.1 항상 허용되는 기록 행위 (범위 제한의 예외)

**작업 흐름이 요구하는 상태 기록은 TASK의 "범위 밖"에 걸리지 않습니다.**
이 예외가 없으면 "STATUS.md를 갱신하라"는 규칙과 "지정된 파일만 수정하라"는 규칙이 서로 충돌합니다.

어떤 TASK를 수행하든 Owner는 다음을 **항상** 할 수 있고, 해야 합니다.
**리뷰 세션도 자기 리뷰 TASK에 대해 동일하게 허용됩니다** (§3.3 허용 목록).

| 허용되는 수정 | 범위 |
|---|---|
| 자기 TASK 파일의 `Status` 필드 | 그 필드만 |
| `STATUS.md`의 작업 보드에서 **자기 TASK의 행** | 그 행만 |
| `STATUS.md`의 "발견된 후속 작업" 절에 **항목 추가** | 추가만. 기존 항목 삭제·수정 금지 |
| `STATUS.md`의 "마지막 갱신" 날짜 | — |

**여전히 금지:** 다른 TASK의 행 수정, 위험 등록부·차단 요인 절의 재작성,
자기 TASK와 무관한 문서 수정. 그런 변경이 필요하면 후속 작업으로 기록합니다.

> `STATUS.md`를 두 브랜치가 함께 만지므로, 이 예외를 쓸 때는 **§3.4의 직렬화 순서**를 따릅니다.

### 6.2 부트스트랩 예외 (Bootstrap Exception)

Phase 0의 최초 문서 기반 작업은 **TASK 파일이 존재하기 전에** 수행되었습니다.
TASK 파일 자체가 그 작업의 산출물이었기 때문입니다. 닭과 달걀 문제입니다.

- 이 예외는 [`docs/tasks/TASK-000.md`](docs/tasks/TASK-000.md)에 **소급 기록(retrospective)** 되어 있습니다.
- **이후 어떤 작업도 이 예외를 원용할 수 없습니다.** TASK-000은 1회성이며 닫혔습니다.
- 이후 정식 TASK가 필요한 작업은 TASK 파일을 먼저 만들고 시작합니다. Gate L/M의 작은 작업은 §6 기준으로 생략할 수 있습니다.

---

## 7. 인계(Handoff) 프로토콜

에이전트는 **서로의 대화 기록에 접근할 수 없습니다.** 따라서:

- "아까 말한 대로", "이전 세션에서 정한 것처럼" 같은 표현은 **금지**입니다.
- 다음 담당자가 알아야 할 모든 것은 **저장소 안의 파일**에 있어야 합니다.
- PR 설명은 그 자체로 완결적이어야 합니다. 최소 다음을 포함합니다.

```markdown
## 무엇을 했나
## 왜 이렇게 했나
## 어떤 결정을 했고, 무엇이 아직 미해결인가
## 어떻게 확인했나
## 리뷰어가 특히 봐 줬으면 하는 것
```

- 새로 생긴 사실은 반드시 문서에 반영합니다.
  - 아키텍처 결정 → `docs/DECISIONS.md`
  - 진행 상태 → `STATUS.md`
  - 범위 변경 → `docs/PRODUCT_SPEC.md` 또는 `PLAN.md`

---

## 8. 리포지토리 위생 (Repository Hygiene)

Phase 0에서 다음은 **명시적으로 금지**입니다. 이후 단계에서 사람 오너 승인 후 해제됩니다.

- 의존성 설치 및 매니페스트 추가 (`pip install`, `npm install`, `requirements.txt`, `package.json`, `pyproject.toml`)
- 모델 가중치 다운로드 또는 커밋
- CI/CD 설정 (`.github/workflows/`)
- 비밀정보, `.env`, 자격증명, 사설 엔드포인트 주소
- 저작권이 있는 샘플 미디어 파일

항상 금지:

- 개인정보가 포함된 실제 사용자 미디어 커밋
- 대용량 바이너리 직접 커밋 (필요해지면 별도 스토리지 전략을 결정으로 남길 것)

---

## 9. 리뷰 기준

리뷰어는 작성자와 다른 행위자 또는 fresh 독립 세션입니다 (§3.1, R8).
작성자의 완료 보고 대신 저장소·TASK 계약·PR diff·직접 실행 결과를 봅니다.

최소 확인 항목:

1. 새 행동이 합격 기준과 일치하는가
2. 원본 미디어·시간 구간·부분/완료 산출물·재개·hash 불변식이 보존되는가
3. 버그 회귀 테스트가 실제로 기존 결함을 잡는가
4. 테스트 삭제·완화, 범위 이탈, 불필요한 의존성·비밀정보·생성물이 없는가
5. 관련 테스트와 필요한 전체 회귀가 통과하는가
6. 실제 artifact 또는 사용자 흐름이 확인됐는가
7. 환경 차단과 제품 결함, 검증한 OS/하드웨어 경계를 구분했는가
8. PR 설명·STATUS와 실제 HEAD·diff가 일치하는가

판정은 `승인` / `조건부 승인` / `변경 요청` / `차단` / `환경 차단`입니다.
Gate L/M은 PR 근거만으로 REVIEW 문서를 생략할 수 있고, Gate H/S은 고정 HEAD와 직접 재현 증거를
저장소에 남깁니다. 판정은 병합이 아니며 병합에는 사람 제품 오너의 별도 승인이 필요합니다.

---

## 10. 문서 우선순위

충돌 시 다음 순서로 우선합니다.

```
1. AGENTS.md              (규칙)
2. docs/PRODUCT_SPEC.md   (무엇을 만드는가 — 과제 범위 vs 상용 범위 포함)
3. docs/ARCHITECTURE.md   (어떻게 나누는가)
4. docs/EVALS.md          (무엇이 좋은 것인가)
5. PLAN.md                (언제 하는가)
6. docs/tasks/TASK-*.md   (지금 무엇을 하는가)
7. README.md · CLAUDE.md  (진입 안내 — 규칙의 출처가 아님)
```

- `docs/DECISIONS.md`는 위 문서들의 **근거 기록**입니다.
  규칙을 새로 만들지 않고, 왜 그렇게 되었는지를 설명합니다.
- `docs/reviews/REVIEW-*.md`는 **관측 기록**입니다. 지적 사항의 반영 여부는 위 문서들이 정답입니다.
- 이 우선순위는 충돌 해소용이며, **읽는 순서는 §0.2**입니다. 둘을 혼동하지 마십시오.
