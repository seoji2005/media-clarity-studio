# CLAUDE.md

Claude Code 전용 진입점입니다. **짧게 유지합니다.**

## 먼저 읽을 것

**[`AGENTS.md`](AGENTS.md)가 규칙의 단일 출처이며, 모든 세션에서 읽기 순서의 첫 번째입니다.**
이 파일은 그 내용을 반복하지 않습니다. 충돌 시 `AGENTS.md`가 이깁니다.

읽는 순서는 `AGENTS.md` §0.2에 있습니다. 이 파일은 그 순서의 일부가 아닙니다.

## 시작 조건

Claude는 기본 작업자가 아니라 `AGENTS.md` §3의 escalation trigger에 배정된 specialist입니다.
TASK 또는 PR의 execution card에 trigger·역할·범위가 없으면 작업하지 말고 Root에 돌려보냅니다.
배정 역할은 Author 또는 Independent Reviewer 중 하나이며 같은 변경에서 둘 다 맡지 않습니다.
Reviewer는 고정 HEAD의 TASK·diff·직접 회귀만 보고 대상 브랜치를 수정하지 않습니다.

## Claude가 자주 잊는 것 다섯 가지

1. **`main`에 쓰지 않고, 병합하지 않는다.** 항상 `claude/<slug>` 브랜치 → PR.
2. **"복원"이라고 쓰지 않는다.** 재구성(reconstruction) / 추정(estimation)만 사용.
   **식별자도 마찬가지** — `reconstruct`, `ReconstructionAdapter`. (`AGENTS.md` §1)
3. **모르면 미해결로 남긴다.** 그럴듯한 기본값을 지어내지 않는다.
4. **내가 만든 전략을 "승인됨"으로 표시하지 않는다.** 제안됨으로 시작한다. (`docs/DECISIONS.md`)
5. **과제 필수 산출물을 추측으로 버리지 않는다.** 자막과 시각 재구성은 **둘 다 필수**다.
   (`docs/PRODUCT_SPEC.md` §2)

## 이 세션에서 하기 전에 확인할 것

- 지금 어떤 TASK를 하고 있는가? → `docs/tasks/TASK-XXX.md`
- 내가 Owner인가 Reviewer인가? → TASK 파일 머리말. **둘 다일 수 없다.**
  (Owner는 "수행 소유자"이며 구현자를 뜻하지 않는다)
- 내가 이 변경의 작성자인가? → 작성자라면 **리뷰도 승인도 하지 않는다.**
- 현재 단계는? → [`PLAN.md`](PLAN.md), [`STATUS.md`](STATUS.md)

## Phase 0에서 하지 않는 것

기능 코드, 의존성 설치, 모델 다운로드, CI 설정, 비밀정보 추가.
프레임워크·모델·OS·GPU 벤더를 조기에 고정하는 것도 포함됩니다.

## 작업을 마칠 때

- [`STATUS.md`](STATUS.md) 갱신 (자기 TASK 행 + 후속 작업 추가는 항상 허용 — `AGENTS.md` §6.1)
- 새 아키텍처 판단은 [`docs/DECISIONS.md`](docs/DECISIONS.md)에 **제안됨/승인됨/미해결/보류됨** 라벨과 함께 기록
- PR 설명은 `AGENTS.md` §7의 5개 절 형식을 그대로 사용
- 대화 맥락을 인계 근거로 삼지 않는다. **다음 세션(특히 독립 리뷰 세션)은 이 대화를 볼 수 없다.**
- **"했다"고 쓰기 전에 확인한다.** 원격 HEAD·PR 상태·diff로 검증하고,
  확인하지 못한 것은 "확인하지 않음"이라고 적는다 (`AGENTS.md` R10 / §3.5).

## 문체

사람이 읽는 설명은 한국어. 파일명·명령어·식별자·정착된 기술 용어는 영어 유지. (`AGENTS.md` §2)
