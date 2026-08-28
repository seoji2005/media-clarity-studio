# REVIEW-015 — TASK-006 Gate H 제한 재검토

- **대상 저장소:** `seoji2005/media-clarity-studio`
- **대상 PR:** #28 `feat: add TASK-006 evaluation contract schemas and validator`
- **대상 브랜치:** `claude/task-006-eval-contracts`
- **기준 `main`:** `5a6b25d870514433c579be6858de8c23fbd33dfc`
- **고정 검토 HEAD:** `cd94abf0c23c9e9023abbfed1c3999eda9c7efa0`
- **직접 부모:** `d72325737d1088104a11d05228b84bd47616fee0`
- **이전 리뷰:** `REVIEW-014` (PR #29), 대상 `d72325737d1088104a11d05228b84bd47616fee0`
- **Gate:** H
- **리뷰어:** Lean Root Orchestrator
- **판정:** **변경 요청**
- **결함 수:** 차단 0 · 중대 2 · 경미 1

이 문서는 고정 HEAD의 관측 기록이다. 구현 브랜치·기존 리뷰 원문·`main`을 수정하지 않는다.
수정은 Claude Code가 PR #28에 별도 focused commit으로 반영하고, Lean Root가 새 고정 HEAD에서
아래 세 항목과 직접 회귀만 다시 검토한다.

## 1. 직접 확인한 사실

- PR #28은 Open / Draft / 미병합이며 base는 `main`, 고정 HEAD는 위 SHA다.
- 기준 `main` 대비 2 commits ahead / 0 behind, 27파일, +9,630 / -14다.
- REVIEW-014 반영 커밋은 직접 부모가 이전 검토 HEAD인 일반 후속 커밋이다.
- 후속 커밋의 원격 13개 blob을 고정 SHA에서 직접 가져와 hash를 대조했다.
- `make verify-task-006`: H-01~H-14 14/14 PASS, 계약 테스트 116개 PASS, 전체 124개 PASS,
  실제 FFmpeg smoke PASS.
- `make verify`: 124개 PASS, 실제 FFmpeg smoke PASS.
- `make verify-task-006 PYTHON=python3.12`: PASS.
- REVIEW-014의 핵심 반례는 새 HEAD에서 거부됨을 확인했다.
- CI/status check는 구성되어 있지 않다.
- PR #28 본문은 아직 이전 HEAD `d723257…`, 1 commit, +8,443 / -14를 적고 있어 실제 상태와 다르다.

테스트 통과는 아래 계약 경계의 충분조건이 아니다. 독립적으로 만든 네 mutation에서 세 계약 결함을 재현했다.

## 2. 변경 요청

### M-01-R1 — source/degraded media가 서로의 timebase를 참조해도 통과한다

**심각도:** 중대

H-06 유효 문서에서 다음 두 값만 서로 바꾸면 validator가 `valid=True`를 반환한다.

- `source_media.timebase_ref = degraded_timebase.timebase_id`
- `degraded_media.timebase_ref = source_timebase.timebase_id`

현재 구현은 `timebase_ref`가 알려진 ID 집합의 멤버인지만 검사한다. 그러나 source media는
source timebase를, degraded media는 degraded timebase를 가리켜야 한다. 존재하는 다른 timebase를
가리키는 것은 dangling reference보다 더 조용한 시간축 오염이며 timing metric과 mapping의 재현성을
깨뜨릴 수 있다.

**요구:**

- `source_media.timebase_ref`가 있으면 정확히 `source_timebase.timebase_id`와 같아야 한다.
- `degraded_media.timebase_ref`가 있으면 정확히 `degraded_timebase.timebase_id`와 같아야 한다.
- 한쪽만 존재하거나 역할이 뒤바뀐 경우 안정 오류 코드와 실제 JSON Pointer 위치로 거부한다.
- 정상 source/degraded 연결의 positive test와 두 방향 swap mutation을 추가한다.

### M-04-R1 — paired sample 집합이 dataset의 진부분집합이어도 통과하고 hypothesis 집합은 생략 가능하다

**심각도:** 중대

다음 두 반례가 모두 `valid=True`다.

1. dataset sample 집합은 `{smp-001, smp-002}`인데 baseline/candidate paired 집합과 두
   hypothesis의 sample 집합을 모두 `{smp-001}`로 줄인다.
2. paired 집합은 유지한 채 baseline hypothesis의 `sample_ids` 필드를 제거한다.

현재 검사는 paired 집합이 dataset의 부분집합인지와, hypothesis의 `sample_ids`가 있을 때만
일치하는지를 본다. REVIEW-014와 TASK-006의 paired 계약은 baseline/candidate가 같은 전체 dataset
sample 집합에서 비교됐다는 증거를 요구한다. 선택적으로 빠질 수 있는 hypothesis 집합은 그 증거가 아니다.

**요구:**

- `paired_comparison`이 있으면 참조된 baseline/candidate hypothesis 모두에 `sample_ids`가
  존재해야 한다.
- baseline paired, candidate paired, baseline hypothesis, candidate hypothesis, dataset의 다섯
  sample 집합이 정확히 같아야 한다.
- 중복 ID가 별도 schema 규칙으로 금지되지 않았다면 집합 비교 전에 중복도 거부한다.
- 이미 다른 이유로 invalid인 H-14만 positive base로 쓰지 말고, 독립된 유효 paired 문서를 먼저
  통과시킨 뒤 진부분집합·누락·불일치 mutation을 각각 실패시킨다.

### R-03-1 — resume version 불일치의 위반 위치가 실제 입력을 가리키지 않는다

**심각도:** 경미

normalization version 불일치는 `E_RESUME_FINGERPRINT`로 거부되지만 위치가
`eval_run_manifest/resume/previous_metric_versions/source/cer`처럼 만들어진다.
`previous_metric_versions`는 배열이므로 이 pointer는 입력에서 해석되지 않는다. 실제 위치는 예를 들어
`.../previous_metric_versions/0/normalization_version`이다.

TASK-006 §3.6은 오류 코드와 위반 위치를 테스트 계약으로 고정한다. 진단이 실제 필드를 가리키지 않으면
사용자와 자동화가 수정 지점을 찾을 수 없다.

**요구:**

- 이전 version entry의 실제 배열 index를 보존한다.
- implementation/normalization 값 불일치는 각각 실제
  `.../<index>/implementation_version` 또는 `.../<index>/normalization_version`을 가리킨다.
- 필드 누락도 해당 entry 안의 실제 필드 위치 또는 존재하는 부모 container 위치를 사용한다.
- 모든 새 finding location을 JSON Pointer로 입력에 적용해 실제 노드 또는 허용된 누락 부모가
  해석되는지 테스트한다.

## 3. 운영 정합성

PR #28 본문의 고정 HEAD·tree·부모·commit 수·diff 통계·검증 개수는 현재 원격 상태와 맞게 갱신해야 한다.
이 항목 자체는 validator 코드 결함 수에 포함하지 않지만, `AGENTS.md` §3.5와 §9의 통합 전 조건이다.

## 4. 제한 재검토 범위

새 HEAD에서는 다음만 본다.

1. M-01-R1의 역할별 media↔timebase 연결
2. M-04-R1의 paired/hypothesis/dataset 정확 집합 동일성
3. R-03-1의 실제로 해석 가능한 resume finding location
4. 위 반례를 고정한 positive·mutation 회귀 테스트
5. 기존 H-01~H-14, TASK-006 테스트, 전체 `make verify`, 실제 FFmpeg smoke
6. 직접 영향을 받은 schema·validator·fixture·TASK/STATUS·PR 본문의 정합성
7. 범위 이탈, 테스트 약화, 새 dependency 없음

REVIEW-014에서 해소된 M-02·R-01 및 그 밖의 TASK-006 영역을 이유 없이 전면 재검토하지 않는다.
새 결함은 위 수정이 현재 통합을 실제로 위험하게 만드는 직접 회귀일 때만 보고한다.

## 5. 복구 경계와 승격 조건

- 이 리뷰 branch는 구현 branch를 수정하지 않는다.
- Claude Code는 amend/rebase/force-push 없이 별도 focused commit으로 반영한다.
- 실패 시 그 후속 커밋만 일반 revert할 수 있어야 한다.
- `main`, 기존 TASK-022 파일, REVIEW-014/015 원문, PR #29를 수정하지 않는다.
- PR #28은 Draft로 유지하며 Ready 전환·병합·branch 삭제를 하지 않는다.
- 세 변경 요청과 직접 회귀가 새 고정 HEAD에서 모두 해소되고 전체 검증이 통과하며 PR 본문이 실제
  HEAD와 일치할 때만 Gate H 승인 후보로 승격한다.
