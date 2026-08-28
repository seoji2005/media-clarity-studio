# REVIEW-018 — TASK-028 Gate H 고정 HEAD 검토

## 1. 검토 대상

| 항목 | 값 |
|---|---|
| 저장소 | `seoji2005/media-clarity-studio` |
| 구현 PR | #36 `feat: add TASK-028 artifact store and resumable stage runtime` |
| Gate | H |
| 기준 `main` | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| 고정 HEAD | `9c60ccb67d5475ce1c794852ccadfd82594383a3` |
| tree | `2d7318225c47dff1abda8b2bb5359edac3fcb75b` |
| 직접 부모 | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| 검토자 | Lean Root Orchestrator |
| 검토일 | 2026-08-28 UTC |

이 문서는 위 고정 HEAD만 검토한다. 이후 구현 branch push나 PR 본문 변경은 이 판정을
자동으로 갱신하지 않는다.

## 2. 최종 판정

**변경 요청 — Gate H. 필수 수정 5건.**

필수 명령, J-01~J-16, H-01~H-14, 기존 전체 테스트와 FFmpeg smoke는 독립 실행에서
모두 통과했다. content-addressed store의 streaming hash, no-overwrite 승격, dedupe,
손상 artifact 거부와 일반적인 단계 재개 경로도 구현되어 있다.

그러나 별도 반례에서 다음 hard gate 위반이 재현됐다.

1. schema-valid이지만 의미상 완료되지 않은 빈 `completed` attempt가 cache hit가 된다.
2. cache hit가 먼저 발견되면 남아 있는 `running` attempt가 `interrupted`로 보존되지 않는다.
3. 외부 절대 경로를 `source_identity`로 주면 manifest에 그대로 복제된다.
4. artifact 저장 실패 때 보존된 temp 파일과 안정 오류가 failed attempt에 연결되지 않는다.
5. 잘못된 seed `ArtifactRef`가 안정 계약 오류가 아니라 raw `KeyError`를 내고 job 디렉터리를 만든다.

이 결함들은 누락·손상·중단 후 복구에서 거짓 완료, 미완료 상태 잔류, 민감 경로 노출,
실패 증거 단절을 만들 수 있다. TASK-028의 목적 자체가 재현 가능하고 손상 안전한 resume
기반이므로 승인할 수 없다.

## 3. 원격 경계와 범위

- PR #36은 Open / Draft / 미병합이다.
- base는 `main@b554760…`, head는
  `claude/task-028-resumable-runtime@9c60ccb…`이다.
- 구현 branch는 기준 `main`보다 1커밋 앞, 0커밋 뒤다.
- PR 전체 변경은 30파일 · +5,319 / -471이다.
- 고정 HEAD 재확인 직전에 구현 branch와 `9c60ccb…`를 비교한 결과
  ahead 0 / behind 0 / identical이었다.
- commit status와 GitHub Actions workflow run은 없다. 아래 실행 결과는 원격 고정 SHA의
  변경 파일을 격리 트리에 반영해 Lean Root가 직접 얻은 증거다.
- 구현 branch, 구현 코드, schema, fixture, PR 상태는 이 리뷰에서 수정하지 않았다.

## 4. 직접 실행 결과

| 명령 | 결과 |
|---|---|
| `make verify-task-028` | exit 0 — J fixture 16/16, store 28, runtime 61, 전체 259, TASK-028 smoke PASS, FFmpeg smoke PASS |
| `make verify-task-006` | exit 0 — H fixture 14/14, 계약 162, 전체 259, FFmpeg smoke PASS |
| `make verify` | exit 0 — 전체 259, FFmpeg smoke PASS |
| `make verify-task-028 PYTHON=python3.12` | exit 0 — J fixture 16/16, 전체 259, smoke PASS |
| `make verify-task-006 PYTHON=python3.12` | exit 0 — H fixture 14/14, 전체 259, smoke PASS |

통과 테스트와 구현이 같은 가정을 공유할 가능성을 확인하기 위해 production API와 실제
JSON attempt 파일을 사용한 독립 반례를 추가 실행했다.

| 반례 | 실제 결과 |
|---|---|
| 완료 record의 `outputs=[]`, `verified_artifact_count=0` | schema finding 0, cache `hit`, callable 0회, 출력 0개 |
| 동일 stage에 과거 completed와 더 최신 running attempt 공존 | completed hit 반환 뒤 최신 attempt가 계속 `running` |
| `source_identity`에 임시 디렉터리 아래 절대 source path | manifest에 절대 경로가 byte-for-byte 기록됨 |
| artifact 승격 과정에서 `ContractViolation` | 실제 incoming temp 파일은 남지만 failed record의 `temp_paths=[]`, `error_code=null`, `error_location=null` |
| `seed_inputs={'extract': [{}]}` | raw `KeyError('content_hash')`; `jobs/job-a` 디렉터리 생성 |

## 5. 필수 수정

### M-01 — 완료 attempt의 semantic invariant가 없어 거짓 cache hit가 가능하다

`_read_attempts()`는 JSON schema만 검사하고, `_verify_checkpoint()`는 status가
`completed`인지 본 뒤 `outputs`를 순회한다. 현재 schema는 completed attempt의 빈 outputs,
종료 시각 부재, 검증 수 0을 허용한다. 따라서 출력 순회가 0회인 record가 성공 checkpoint로
인정되고 callable을 건너뛴다.

TASK-028 §3.5는 completed checkpoint와 **모든 출력 artifact가 존재하고 hash·size가 맞을 때만**
재사용하도록 요구하고 §3.6은 schema와 semantic invariant를 모두 요구한다. 빈 완료 record를
정상 hit로 취급하는 것은 거짓 cache hit다.

필수 수정:

- Job/Attempt semantic validator를 production 경로에 추가한다.
- cache lookup 전에 읽은 attempt가 상태별 불변식을 만족하는지 검사한다.
- `completed`는 완료에 필요한 terminal metadata와 출력·검증 집계가 일관돼야 한다.
  이번 TASK의 stage 계약에서 zero-output 완료를 허용하지 않는다면 `outputs`도 비어 있으면 안 된다.
- `verified_artifact_count == len(outputs)`와 검증 byte 집계 등 저장된 완료 증거의 자기 일관성을
  검사한다.
- 의미상 손상된 checkpoint는 hit로 쓰지 않고 `E_CHECKPOINT_INVALID` 같은 안정 코드와
  실제 record 위치로 거부한다.
- running/failed/interrupted/completed 상태별 허용·필수 필드도 한 표와 테스트로 고정한다.

### M-02 — cache hit 경로가 stale running attempt 보존을 우회한다

`_run_stage()`는 `_lookup_cache()`와 hit return을 먼저 수행한 뒤 miss 경로에서만
`_preserve_running_attempts()`를 호출한다. 따라서 matching completed record와 더 최신
running record가 함께 있으면 hit가 즉시 반환되고 running record가 영구히 running으로 남는다.

TASK-028 §3.5와 J-10은 프로그램 재시작 시 남은 running record를 지우거나 덮어쓰지 않고
interrupted로 보존하도록 요구한다. 이 규칙은 miss에만 적용되는 조건이 아니다.

필수 수정:

- 어떤 cache hit return보다 먼저 해당 stage의 모든 stale running attempt를
  결정적으로 interrupted로 전이한다.
- completed old key + running new key + fingerprint가 다시 old key로 돌아온 재시작 반례를 추가한다.
- 기존 attempt ID와 완료 record를 수정·재사용하지 않고 새 상태 기록 순서를 보존한다.

### M-03 — `source_identity`가 외부 절대 경로를 manifest에 복제한다

`JobSpec.source_identity`는 “비민감 식별자”라는 주석만 있고 preflight 검사가 없다.
호출자가 POSIX absolute path를 전달한 반례에서 그 문자열이 manifest에 그대로 기록됐다.

TASK-028 §3.1과 완료 조건은 외부 입력 실제 경로와 전체 외부 경로를 manifest/log에 복제하지
않도록 hard gate로 둔다. 호출자 주석만으로는 production API의 안전 경계가 되지 않는다.

필수 수정:

- filesystem mutation 전에 `source_identity`를 검증한다.
- POSIX absolute, Windows drive/UNC, traversal과 명백한 path-like 값은 안정
  `E_UNSAFE_PATH` 및 실제 입력 위치로 거부한다.
- 거부 시 manifest/job directory를 만들지 않는 테스트와 Windows 형태의 반례를 추가한다.
- 원문 source path가 exception/message/record에도 남지 않는지 검사한다.

### M-04 — artifact 실패 증거가 failed attempt와 연결되지 않는다

artifact store는 실패한 incoming temp를 보존하지만, `add_file()`이 예외로 끝나면
`WriteOutcome`이 반환되지 않는다. runtime은 `ContractViolation`을 구체적으로 보존하지 않고
generic failure 경로로 전환하므로 failed attempt에는 실제 `temp_paths`와 안정
`error_code`·`error_location`이 남지 않는다.

TASK-028 §3.2·§3.6·J-07·§9는 실패 temp를 자동 삭제하지 않고 attempt record에 portable path로
연결하며 안정 코드·위치를 남기도록 요구한다. 파일만 orphan으로 남기는 것은 복구·QC 증거가 아니다.

필수 수정:

- artifact failure가 실제 보존 temp 경로, 안정 코드, 위치를 runtime에 전달할 수 있게 한다.
  예외 metadata 또는 명시적 failure outcome 중 단순한 한 경로를 택한다.
- `ContractViolation`의 code/location을 failed attempt에 그대로 기록한다.
- 기록한 temp path는 project root 기준 portable relative path이고 실제 보존 파일을 가리켜야 한다.
- 성공 뒤 삭제된 temp 경로를 실패 증거로 잘못 기록하지 않는다.
- J-14형 입력 변경과 승격 실패 각각에서 실제 filesystem temp 집합과 record가 일치하는지 테스트한다.

### M-05 — 외부 seed ArtifactRef가 schema 검증 없이 사용된다

`seed_inputs`는 public API의 외부 입력 통로지만 `content_hash`를 직접 indexing한다.
필수 필드가 없는 입력은 schema/semantic finding이 아니라 raw `KeyError`를 내고,
오류 전에 job directory까지 생성한다.

필수 수정:

- 모든 seed `ArtifactRef/v1`를 공용 schema validator로 filesystem mutation 전에 검증한다.
- duplicate/누락/잘못된 hash·URI·byte size를 안정 `E_SCHEMA` 또는 계약된 코드와 실제
  `seed_inputs/<stage>/<index>` 위치로 거부한다.
- 예외 메시지에 외부 원문 경로나 텍스트를 복제하지 않는다.
- malformed seed 입력에서 project root가 byte-for-byte 또는 directory-entry 수준으로
  불변임을 테스트한다.

## 6. 통과한 경계와 회귀 보존 요구

다음은 독립 실행에서 통과했으며 재작업이 약화하면 안 된다.

- J-01~J-16 정확히 16건 발견·실행
- H-01~H-14 정확히 14건 발견·실행
- TASK-006 finding code/location/message/order 회귀 없음
- CAS 동일 바이트 dedupe와 기존 object no-overwrite
- 기존 CAS 손상·누락 거부
- streaming hash와 입력 변경 탐지
- artifact 승격 후 checkpoint 전 중단에서 거짓 completed 미생성
- 부분 실패 뒤 완료 upstream hit
- stage fingerprint와 downstream invalidation
- 독립 DAG branch cache 재사용
- unsafe artifact/job 경로 거부
- 실제 FFmpeg TASK-022 smoke

재작업은 위 다섯 항목과 직접 회귀에 한정한다. worker supervision, 멀티프로세스 scheduler,
GC, 실제 ASR/번역 stage, 외부 dependency, CI는 추가하지 않는다.

## 7. 남은 미검증 경계

- Windows 11/NTFS 실제 실행
- hard-link 미지원 filesystem의 실제 오류 동작
- 실제 프로세스 강제 종료와 OS crash durability
- 멀티프로세스/TOCTOU 경합
- JSON Schema Draft 2020-12 전체 구현과 외부 meta-validator

이는 공개된 범위 밖 또는 환경 한계다. 다만 M-01~M-05는 Linux 단일 프로세스의 현재 기본
경로에서 직접 재현되므로 이 한계들로 설명되지 않는다.

## 8. 다음 허용 행동

1. Claude Code가 기존 `claude/task-028-resumable-runtime` branch에 M-01~M-05와 직접
   회귀만 새 focused commit으로 반영한다.
2. amend, rebase, force-push, merge, Ready 전환, branch 삭제를 하지 않는다.
3. 기존 테스트를 삭제·skip·완화하지 않고 J-01~J-16·H-01~H-14·전체 verify를 다시 실행한다.
4. REVIEW-018의 다섯 반례를 production API로 재실행하고 안정 code/location과 filesystem
   불변·evidence 연결을 확인한다.
5. 새 HEAD를 보고하면 Lean Root가 새 고정 HEAD에서 Gate H 재검토한다.

이 변경 요청은 구현 PR을 병합하거나 거부하는 행위가 아니다. PR #36은 Draft 상태로 유지한다.
