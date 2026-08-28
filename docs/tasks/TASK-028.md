# TASK-028 — Content-addressed artifact store와 재개 가능한 stage runtime

| 항목 | 값 |
|---|---|
| **ID** | TASK-028 |
| **Owner** | Claude Code 구현 세션 |
| **Reviewer** | Lean Root Orchestrator — 구현 세션과 분리된 고정 HEAD Gate H 검토 |
| **Phase** | Phase 1a / shared storage·orchestrator foundation |
| **Status** | `In review` |
| **구현 상태** | **`Implemented — awaiting fixed HEAD rereview`** — 구현 세션 자기 승인 없음 |
| **1차 Gate H 검토** | `REVIEW-018` (PR #37, 리뷰 commit `a08981795739901b9fa14733ff3e0a9afc614e8a`) — 고정 HEAD `9c60ccb67d5475ce1c794852ccadfd82594383a3`, 판정 **변경 요청** (필수 수정 5건). 반영은 §12.8 |
| **2차 Gate H 재검토** | `REVIEW-019` (PR #38, 리뷰 commit `c57e22b507a97d1b7f63bc8ab530bb7935efaa2c`) — 고정 HEAD `26139810bb4f3d8c1033d7802254c4144c370eac`, 판정 **변경 요청** (REVIEW-018 5건 해소 · 추가 필수 수정 4건). 반영은 §12.10 |
| **3차 Gate H 재검토** | `REVIEW-020` (PR #39, 리뷰 commit `801a804b467ea61378203f96f4680fc3d78996ff`) — 고정 HEAD `45459b0331113ea18319cdf6072e24e64b6c3da4`, 판정 **변경 요청** (REVIEW-018·019 직접 반례 해소 · 추가 필수 수정 2건). 반영은 §12.12 |
| **4차 Gate H 재검토** | `REVIEW-021` (PR #40, 리뷰 commit `c35f5b7201697469508fa49264d76a5542cc0d2b`) — 고정 HEAD `f0c5e86c3a23f8b358464f7117d63c46149b9403`, 판정 **변경 요청** (REVIEW-020 직접 반례 해소 · 추가 필수 수정 1건). 반영은 §12.14 |
| **구현 기준 main** | `b55476086ca55a2bb806fb237239be604ed7efb8` |
| **구현 브랜치** | `claude/task-028-resumable-runtime` |
| **계약 상태** | **Approved — PR #34 병합 완료** |
| **계약 기준 main** | `d000284d71e18788a89c8be4ca3c45c26db35b5a` |
| **계약 승인 HEAD** | `3ebb407ff14498a8d6cc23303b9bf5773d4b2de0` |
| **계약 merge commit** | `0056ca01225cd662b9d3f3c5de079a380b893378` |
| **위험 등급** | **Gate H** — 파일 형식·원자적 쓰기·캐시·중단 후 재개 |
| **선행** | TASK-006 Done, TASK-022 Done |
| **차단 질문** | 없음. U-16 보관 정책은 미정이므로 자동 삭제·GC를 구현하지 않는다 |

## 1. 최종 판정과 우선순위 근거

다음 단일 구현 TASK는 ASR 모델·외부 corpus·지표 계산기보다 먼저 **공용 artifact/cache/resume
기반**을 만든다.

| 후보 | 지금 먼저 하지 않는 이유 |
|---|---|
| faster-whisper·Qwen ASR adapter | 긴 실행의 checkpoint·캐시 무효화·artifact 검증이 없어 실패 시 전체 재실행 또는 잘못된 재사용 위험 |
| seed corpus 실제 다운로드 | 데이터는 필요하지만 다운로드·추출 결과를 안전하고 재현 가능하게 materialize할 공용 기반이 먼저 필요 |
| CER/WER·번역 metric 실행기 | TASK-006은 계약을 제공하지만 실제 run writer가 없고, `norm-v1` 내용(U-19)도 아직 미정 |
| **TASK-028 runtime foundation** | TASK-022에서 검증한 원본 불변·partial·원자적 승격을 모든 후속 stage가 재사용하게 하며 치명적 복구 실패를 먼저 줄임 |

이 TASK는 정확도를 직접 높이지 않는다. 대신 향후 ASR·번역·평가·OCR가 같은 입력을 반복 계산하지
않고, 오류·중단·설정 변경 뒤에도 어떤 artifact를 재사용했는지 검증할 수 있게 한다. 사용자의
의사결정 규칙 중 **데이터 손상·복구 실패 우선 차단**을 적용한 결과다.

## 2. 목표

Python 3.12 표준 라이브러리만으로 다음 두 공용 기반을 구현한다.

1. **Content-addressed artifact store**
   - SHA-256으로 바이트를 식별한다.
   - 기존 artifact를 덮어쓰지 않는다.
   - 같은 바이트는 안전하게 deduplicate한다.
   - 완료 artifact만 `ArtifactRef/v1`로 반환한다.
2. **재개 가능한 synchronous stage runtime**
   - stage 입력·설정·구현·선택적 모델/문맥 fingerprint로 cache key를 만든다.
   - 완료 checkpoint와 artifact를 모두 검증한 경우에만 cache hit로 재사용한다.
   - 실패·중단 뒤 완료된 앞단계는 재사용하고 실패 stage부터 다시 실행한다.
   - fingerprint가 바뀌면 기존 run에 이어 쓰지 않는다.

이 TASK의 완료 시점에도 실제 ASR·번역·metric 알고리즘은 없다. 후속 구현이 안전하게 올라갈
공용 실행 기반만 존재한다.

## 3. 계약

### 3.1 저장 layout

구현은 아래 의미를 보존하는 local-only layout을 사용한다. 세부 디렉터리 이름은 schema와
문서에서 한 번 정하면 테스트로 고정한다.

```text
<project_root>/
├── artifacts/
│   └── sha256/<prefix>/<digest>
└── jobs/
    └── <job_id>/
        ├── manifest.json
        ├── stages/
        │   └── <stage_id>/
        │       └── attempts/<attempt_id>.json
        └── logs/
```

- manifest·attempt record·artifact URI는 project root 기준 portable relative path다.
- 절대 경로, Windows drive/UNC, `..` traversal을 저장하지 않는다.
- 외부 입력의 실제 경로는 manifest/log에 복제하지 않는다. 입력은 hash와 호출자가 제공한
  비민감 식별자로 연결한다.
- 보관 정책 U-16이 미정이므로 자동 삭제·GC·eviction은 없다.

### 3.2 artifact 쓰기

- 입력 파일은 chunked streaming으로 SHA-256과 byte size를 계산한다. 전체 파일을 RAM에 올리지 않는다.
- 새 바이트는 대상과 **같은 filesystem**의 임시 파일에 exclusive create로 쓴다.
- 파일 내용을 flush하고 가능한 범위에서 durability 처리를 한 뒤 SHA-256·size를 다시 확인한다.
- 검증된 임시 파일만 최종 content-addressed 경로로 no-overwrite 승격한다.
- 최종 경로가 이미 있으면 기존 바이트의 SHA-256·size를 확인한다.
  - 같으면 dedupe hit다.
  - 다르면 hash/path collision 또는 저장소 손상으로 실패한다. 기존 파일을 수정하지 않는다.
- 성공한 뒤에만 `ArtifactRef/v1`을 만든다.
- `ArtifactRef.content_hash`는 `sha256:<64 lowercase hex>`다.
- 원본 입력·기존 output·기존 checkpoint는 어떤 실패 경로에서도 수정·삭제하지 않는다.
- 실패한 임시 파일은 완료 artifact로 보이지 않아야 한다. 자동 삭제는 하지 않으며 attempt record가
  임시 경로를 portable relative path로 기록한다.

### 3.3 stage fingerprint와 cache key

stage cache key는 canonical JSON 바이트의 SHA-256이다. canonical JSON은 UTF-8,
키 정렬, 결정적 separator, NaN/Infinity 금지로 고정한다.

최소 입력:

- runtime schema version
- pipeline ID
- stage ID
- stage implementation version
- 정렬된 입력 `ArtifactRef.content_hash` 목록
- config hash
- dependency/environment fingerprint
- 선택적 source hash
- 선택적 chunking hash
- 선택적 model hash
- 선택적 context hash
- 선택적 random seed와 reproducibility tier

규칙:

- path·mtime·파일명만으로 cache identity를 만들지 않는다.
- 선택 항목은 **없음 자체가 canonical 값**에 들어간다. 조용히 key 계산에서 빼지 않는다.
- stage가 비결정적이거나 필요한 fingerprint를 제공하지 못하면 `cacheable: false`로 실행한다.
  거짓 cache hit를 만들지 않는다.
- model/config/context/chunking/dependency/implementation version 중 하나라도 바뀌면 cache miss다.
- 이 TASK는 Context Bundle 구조나 모델을 정하지 않는다. `context_hash`·`model_hash`는
  후속 stage가 공급하는 불투명 fingerprint다.

### 3.4 job과 stage 상태

`Job/v1`은 최소 다음 상태를 표현한다.

- job: `queued | running | paused | failed | completed | cancelled`
- stage attempt: `running | interrupted | failed | completed`
- cache: `hit | miss | bypassed`

완료 순서:

1. stage callable이 임시 출력을 만든다.
2. artifact store가 각 출력을 검증·승격하고 `ArtifactRef`를 만든다.
3. artifact를 다시 열어 hash·size를 검증한다.
4. attempt record를 `completed`로 원자적 기록한다.
5. job manifest가 해당 completed attempt를 가리키도록 원자적 기록한다.

4번 전에 종료되면 완료로 간주하지 않는다. CAS에 orphan object가 남을 수 있지만 다음 재개에서
완료 checkpoint 없이 cache hit로 가장하지 않는다.

### 3.5 재개와 무효화

- 같은 job fingerprint에서만 재개한다.
- `completed` checkpoint와 모든 출력 artifact가 존재하고 hash·size가 맞을 때만 stage를 재사용한다.
- `running` attempt가 남은 채 프로그램이 재시작되면 그 record를 지우거나 덮어쓰지 않는다.
  `interrupted`로 보존하고 새 attempt ID로 다시 실행한다.
- stage A가 완료되고 B가 실패하면 재개 시 A는 검증 후 hit, B는 새 attempt로 실행한다.
- A의 fingerprint가 바뀌면 A와 그 downstream은 miss다. 독립 branch stage는 자기 fingerprint가
  그대로면 재사용할 수 있다.
- job fingerprint가 다르면 `E_RESUME_FINGERPRINT` 또는 이 TASK에서 정한 안정 오류 코드로
  기존 job 재개를 거부한다. 호출자는 새 job ID를 사용한다.
- 손상·누락 artifact는 hit로 쓰지 않는다. 기존 evidence를 보존하고 안정 오류 코드와 위치를 남긴다.

### 3.6 manifest·schema·오류

- `schemas/job-v1.schema.json`은 JSON Schema Draft 2020-12, 안정 `$id`,
  `schema_version: "1.0.0"`, 닫힌 production 객체를 사용한다.
- 공통 `ArtifactRef/v1`은 `common-v1.schema.json`의 상대 `$ref`로 재사용한다.
- duplicate JSON key와 NaN/Infinity를 거부한다.
- schema validation과 semantic invariant 검사를 모두 제공한다.
- 오류는 안정 코드, 실제 입력에서 해석되는 JSON Pointer 위치, 비민감 메시지를 제공한다.
- TASK-006 validator와 keyword 해석을 복제해 두 구현이 갈라지게 하지 않는다. 필요한 최소
  공용 schema-validation helper를 추출하고 기존 TASK-006 동작·오류 순서·테스트를 그대로 보존한다.
- 새 외부 JSON Schema dependency는 추가하지 않는다. Draft 2020-12 전체 구현이라고 주장하지 않는다.

최소 안정 오류 범주:

- schema/JSON 오류
- unsafe path
- artifact collision·손상·누락
- stage fingerprint·resume 불일치
- 잘못된 상태 전이·DAG cycle
- stage 실행 실패

정확한 코드 이름은 구현 전에 schema·테스트에서 한 번 정하고 TASK 문서에 기록한다.

### 3.7 관측 지표

각 attempt와 job manifest에는 최소 다음을 기록한다.

- stage ID·attempt ID·cache key
- cache hit/miss/bypassed와 이유
- 시작·종료 UTC timestamp와 wall duration
- 입력·출력 artifact ID/hash/byte size
- implementation/config/dependency/model/context/chunking fingerprint 중 제공된 값
- attempt count와 안정 error code
- 재현성 등급
- 검증한 artifact 수와 총 byte 수

원본 미디어 바이트, transcript·번역문, 비밀정보, 전체 외부 경로를 로그에 복제하지 않는다.
GPU VRAM·CPU/RAM sampler는 이 TASK 범위가 아니다. 필드는 후속 계측이 확장 가능하게 하되
측정하지 않은 값을 0으로 쓰지 않는다.

## 4. 필수 시나리오

| ID | Given / When / Then |
|---|---|
| **J-01** | 새 deterministic stage가 성공하면 artifact와 completed attempt·manifest가 생성되고 schema 검증을 통과한다 |
| **J-02** | 같은 입력·fingerprint로 재실행하면 callable을 호출하지 않고 검증된 cache hit를 사용한다 |
| **J-03** | config·implementation·dependency·model·context·chunking hash를 하나씩 바꾸면 각각 cache miss다 |
| **J-04** | cacheable=false이면 동일 fingerprint여도 bypassed로 실행하고 이유를 기록한다 |
| **J-05** | 기존 CAS object가 같은 hash·size면 dedupe하며 새 바이트를 덮어쓰지 않는다 |
| **J-06** | 기존 CAS object가 손상됐으면 hit로 쓰거나 덮어쓰지 않고 안정 오류로 실패한다 |
| **J-07** | stage callable 실패 또는 임시 출력 뒤 실패하면 completed checkpoint·final manifest를 만들지 않고 failure evidence를 보존한다 |
| **J-08** | artifact 승격 후 checkpoint 전 중단을 주입하면 orphan object를 완료 stage로 가장하지 않고 재개가 안전하다 |
| **J-09** | A 완료 뒤 B 실패 시 재개하면 A는 hit, B만 새 attempt로 실행한다 |
| **J-10** | 이전 `running` attempt가 남아 있으면 interrupted로 보존하고 새 attempt를 만든다 |
| **J-11** | job fingerprint가 바뀐 resume은 기존 job에 이어 쓰지 않고 거부한다 |
| **J-12** | 완료 checkpoint의 artifact가 누락·변조되면 cache hit를 거부한다 |
| **J-13** | 절대·drive·UNC·traversal path와 project root 밖 target을 preflight에서 거부하고 filesystem을 바꾸지 않는다 |
| **J-14** | 입력 파일이 hashing/copy 중 바뀌면 성공 artifact를 만들지 않는다 |
| **J-15** | DAG cycle·없는 dependency·중복 stage ID를 실행 전에 거부한다 |
| **J-16** | stage A와 독립인 C는 A fingerprint 변경 때 C의 유효 cache를 계속 재사용한다 |

각 시나리오는 production API를 실제로 호출해야 한다. fixture의 expected 값을 그대로 읽어
통과시키는 runner를 만들지 않는다.

## 5. 산출물 및 수정 가능 범위

- `schemas/job-v1.schema.json`
- 공용 schema-validation helper에 필요한 최소 `src/media_clarity/` 파일
- `src/media_clarity/artifact_store.py`
- `src/media_clarity/job_runtime.py`
- `tests/test_artifact_store.py`
- `tests/test_job_runtime.py`
- `tests/fixtures/job_runtime/`
- `scripts/smoke_task_028.py`
- `Makefile`의 TASK-028 검증 target
- 실제 schema 경로·storage/orchestrator 구현 경계에 필요한 최소 `docs/ARCHITECTURE.md`
- 이 TASK의 구현 상태와 `STATUS.md` 자기 행
- 새 실행 임시 경로를 무시하는 데 필요한 최소 `.gitignore`

기존 TASK-006 schema 7개와 `eval_contracts.py`는 공용 validator 추출에 직접 필요한 최소
변경만 허용한다. 기존 오류 코드·판정 순서·H-01~H-14 의미를 바꾸지 않는다.

## 6. 범위 밖

- ASR·VAD·diarization·forced alignment·번역·자막 분할·OCR/VLM
- 실제 모델·GPU·CUDA·VRAM sampler·batch scheduler
- 외부 corpus 다운로드·압축 해제·계정·네트워크
- 실제 CER/WER/chrF2·통계 계산
- Context Bundle 구조·correction ledger·translation memory
- worker process supervision·프로세스 격리·멀티프로세스 동시 실행
- In/Out 구간 재처리·기존 결과 병합
- 자동 삭제·GC·용량 quota·retention 정책(U-16)
- SQLite·외부 DB·새 dependency·CI
- 기존 TASK-022 동작 변경이나 일반 pipeline으로의 대규모 refactor
- Windows 11/NTFS에서 검증했다고 주장하는 것
- U-07·U-12·U-13·U-15·U-16·U-18·U-19·U-22·U-26·U-27 확정

## 7. 완료 조건

- [ ] `Job/v1` schema와 semantic validator가 J-01~J-16을 실제로 판정한다.
- [ ] content-addressed artifact write가 streaming hash·no-overwrite·dedupe·손상 거부를 지킨다.
- [ ] stage cache key가 모든 계약 fingerprint를 결정적으로 포함한다.
- [ ] 완료 checkpoint와 artifact를 함께 검증한 hit만 재사용한다.
- [ ] 실패·중단·resume mismatch에서 기존 artifact·record를 삭제·덮어쓰지 않는다.
- [ ] 부분 실패 뒤 완료 stage만 재사용되고 변경 stage와 downstream만 다시 실행된다.
- [ ] 로그·manifest에 원본 바이트·텍스트·비밀정보·전체 외부 경로가 없다.
- [ ] J-01~J-16이 각각 발견·실행됐음을 fixture runner와 unit test가 독립 확인한다.
- [ ] 기존 H-01~H-14, TASK-006 157 tests, 전체 165 tests, TASK-022 FFmpeg smoke가 회귀 없이 통과한다.
- [ ] `make verify-task-028`, `make verify-task-006`, `make verify`가 모두 통과한다.
- [ ] 테스트 삭제·skip·완화, dependency·CI·외부 데이터·생성 artifact commit이 없다.
- [ ] Python 3.12에서 검증한다.
- [ ] 구현 PR은 Draft이며 사람 제품 오너 승인 전 Ready·merge하지 않는다.

## 8. 검증과 mutation 감사

필수 명령:

```bash
make verify-task-028
make verify-task-006
make verify
make verify-task-028 PYTHON=python3.12
git diff --check
git status --short
```

mutation 감사 최소 항목:

- cache key에서 config/model/context/chunking/dependency/implementation 중 하나씩 제거
- completed 기록을 artifact 검증보다 먼저 수행
- artifact hash 재검증 제거
- running attempt를 completed로 재사용
- resume fingerprint 비교 제거
- downstream invalidation 제거
- no-overwrite 승격을 overwrite로 변경
- unsafe path 검사 제거
- 로그에 source absolute path 또는 fixture text를 포함

각 mutation에서 관련 테스트가 실제 실패해야 한다. 중복 방어로 미탐지되는 줄이 있으면 숨기지
말고 어떤 상위 검사가 대신 잡는지 보고한다.

## 9. 실패·중단·복구

- PR을 병합하지 않으면 `main`에는 영향이 없다.
- runtime은 사용자가 명시한 test/project root 안에서만 새 파일을 만든다.
- 기존 artifact·manifest·attempt를 자동 삭제하거나 덮어쓰지 않는다.
- 실패한 attempt와 orphan partial/object는 증거로 남고 completed cache로 쓰이지 않는다.
- schema·fingerprint가 바뀌면 기존 job에 억지로 이어 쓰지 않고 새 job을 요구한다.
- 구현 결함이 발견되면 해당 PR을 병합하지 않는 것이 rollback이다.
- 병합 후 회귀가 발견되면 새 코드 경로를 사용하지 않고 기존 TASK-022 synthetic slice 진입점을
  유지할 수 있어야 한다. TASK-022를 TASK-028 runtime으로 강제 전환하지 않는다.

## 10. 예상 작업량과 효과

측정 전 추정이며 확정 일정이 아니다.

| 항목 | 추정 |
|---|---|
| 구현 | 12~20시간 |
| 테스트·실패 주입·안정화 | 8~14시간 |
| Lean Root 고정 HEAD 검토 | 4~8시간 |
| 첫 실행 처리시간 | 전체 input/output SHA-256 때문에 디스크 순차 읽기 1~2회 추가. 실제 p50/p95는 구현 smoke에서 측정 |
| cache hit | stage callable을 생략하므로 후속 ASR·번역처럼 비싼 stage에서 큰 절감 가능. 이번 synthetic fixture만으로 실제 영상 절감률을 주장하지 않음 |
| GPU·VRAM | 사용하지 않음 |
| 저장공간 | 동일 content는 dedupe. 실패 evidence·orphan과 자동 GC 부재로 증가 가능하며 U-16 결정 전 숫자를 만들지 않음 |
| 정확도 | 직접 변화 없음 |
| 수동 수정시간 | 직접 변화 없음 |
| 유지보수 | 공용 runtime 2개 모듈과 Job schema 1개 추가. 모델별 독자 캐시 구현을 막아 장기 복잡도 감소 기대 |

## 11. 인계 메모

- 계약은 PR #34로 `main`에 병합됐다. Claude Code는 최신 `main`에서 전용 구현 branch를 만들고 Draft PR까지만 준비한다.
- 코드는 Claude Code가 작성하고 Lean Root가 고정 HEAD에서 직접 재현한다.
- 작성자는 자기 변경을 승인하지 않는다.
- TASK-022의 원자적 partial/no-overwrite 구현은 참고할 수 있지만, 해당 파일을 공용 runtime으로
  대규모 refactor하거나 기존 smoke 의미를 바꾸지 않는다.
- TASK-006의 validator를 재사용할 때 이름만 공유하고 의미가 갈라지는 복제 구현을 만들지 않는다.
- 미정 U-XX나 모델·corpus·Context Bundle 세부를 이 TASK에서 결정하지 않는다.

---

## 12. 구현 기록 (Claude Code 구현 세션)

**상태: `Implemented — awaiting fixed HEAD rereview`.** 아래는 구현 세션의 주장이며 검증이 아니다.
판정은 Lean Root가 고정 HEAD에서 직접 재현한다 (`AGENTS.md` R10 / §3.5).
구현 세션은 자기 변경을 승인하지 않았고 병합·Ready 전환을 하지 않았다.

### 12.1 산출물

| 파일 | 내용 |
|---|---|
| `schemas/job-v1.schema.json` | `Job/v1` manifest(root)와 `$defs/AttemptRecord`. Draft 2020-12, 안정 `$id`, `schema_version` `1.0.0`, 닫힌 production 객체. `ArtifactRef/v1`은 `common-v1.schema.json`의 상대 `$ref`로 재사용 |
| `src/media_clarity/schema_core.py` | **공용** schema 부분집합 검사기. TASK-006 `eval_contracts`에서 추출했고 `job_runtime`이 같은 구현을 쓴다 |
| `src/media_clarity/artifact_store.py` | content-addressed store — streaming SHA-256, no-overwrite 원자 승격, dedupe, 손상 거부, 경로 안전성 |
| `src/media_clarity/job_runtime.py` | canonical JSON fingerprint, DAG preflight, cache/resume, attempt 상태 기계, J-01~J-16 fixture runner |
| `tests/test_artifact_store.py` · `tests/test_job_runtime.py` | 계약 unit·mutation test |
| `tests/fixtures/job_runtime/j-01.json` … `j-16.json` | J-01~J-16 |
| `scripts/smoke_task_028.py` | 임시 project root end-to-end (FFmpeg·네트워크 없음) |
| `Makefile` | `fixtures-task-028` · `test-task-028` · `smoke-task-028` · `verify-task-028` |

### 12.2 확정한 안정 오류 코드 (§3.6이 요구한 기록)

| 코드 | 범주 | 언제 |
|---|---|---|
| `E_JSON` | schema/JSON | duplicate key · `NaN`/`Infinity` · 파싱 실패 |
| `E_SCHEMA` | schema/JSON | manifest·attempt record·fixture가 schema를 어김 |
| `E_UNSAFE_PATH` | unsafe path | POSIX 절대 · Windows drive/UNC · `..` · 빈 segment · Windows 비호환 segment · symlink를 통한 root 탈출 |
| `E_ARTIFACT_COLLISION` | artifact | 최종 CAS 경로에 **다른** 바이트가 있음 (손상 또는 hash collision) |
| `E_ARTIFACT_MISSING` | artifact | 기록된 artifact 파일이 없음 |
| `E_ARTIFACT_CORRUPT` | artifact | 파일은 있으나 hash·size가 기록과 다름 |
| `E_ARTIFACT_PROMOTE` | artifact | 원자적 no-overwrite 승격을 제공할 수 없음 (덮어쓰기로 대체하지 않음) |
| `E_INPUT_CHANGED` | artifact | 입력 파일이 hashing/copy 중 변경됨 (descriptor stat 불일치) |
| `E_RESUME_FINGERPRINT` | resume | job fingerprint가 기존 job과 다름 — 새 job ID 필요 |
| `E_STATE_TRANSITION` | 상태 | 재시작으로 `running` → `interrupted` 전이가 일어남 (attempt record에 기록) |
| `E_DAG_CYCLE` | DAG | 의존 cycle 또는 자기 자신 의존 |
| `E_DAG_DEPENDENCY` | DAG | 존재하지 않는 dependency 또는 빈 DAG |
| `E_DAG_DUPLICATE_STAGE` | DAG | 중복 stage ID |
| `E_STAGE_FAILED` | stage 실행 | stage callable이 실패했거나 등록되지 않음 |
| `E_CHECKPOINT_INVALID` | 상태 | manifest·attempt record를 읽을 수 없거나 `completed`가 아닌 attempt를 hit로 쓰려 함 |

위치는 실제 입력에서 해석되는 JSON Pointer(`job_fingerprint`, `dag/0/depends_on/0`,
`outputs/0` 등)이거나 계약된 filesystem 위치(project root 기준 relative path)다.
메시지 문구가 아니라 **코드와 위치가 테스트 계약**이다.

### 12.3 job fingerprint와 stage cache key의 구분

§3.5는 두 가지를 동시에 요구한다.

1. "job fingerprint가 다르면 기존 job 재개를 거부한다"
2. "A의 fingerprint가 바뀌면 A와 downstream은 miss다. 독립 branch stage는 자기 fingerprint가
   그대로면 재사용할 수 있다"

stage의 config/model/context/implementation이 job fingerprint에 들어가면 (2)를 시도하는 순간
(1)이 resume을 거부해 버려 둘이 양립하지 않는다. 따라서 다음처럼 나눴다.

- **job fingerprint** = pipeline ID + runtime/schema version + source identity + DAG topology
- **stage cache key** = 위 §3.3의 최소 입력 전부 + **직접 dependency의 cache key**

이 구분으로 J-03·J-11·J-16이 모두 동시에 성립한다. **계약과 모순되는 해석은 발견하지 못했다.**
`tests/test_job_runtime.py`의 `JobFingerprintTests`가 이 경계를 고정한다.

### 12.4 명시적 한계 (과장하지 않는다)

- **Draft 2020-12 전체 구현이 아니다.** `schema_core.SUPPORTED_KEYWORDS` 부분집합만 검사하고,
  그 밖의 keyword가 schema에 나타나면 데이터 오류가 아니라 `SchemaContractError`로 중단한다.
- **Windows 11/NTFS에서 실행하지 않았다.** Windows 비호환 경로 segment(`:`·예약 장치명·trailing
  dot/space)를 **거부하는 규칙**을 만들고 그 규칙을 Linux에서 테스트했을 뿐이다. Windows에서
  검증했다고 주장하지 않는다 (§6).
- **멀티프로세스 공격자에 대한 완전한 보안을 주장하지 않는다.** 이번 TASK는 local synchronous
  runtime이며 경로 검사는 사고와 설정 실수를 막는 수준이다. TOCTOU 경합은 범위 밖이다.
- 원자적 no-overwrite 승격은 `os.link`에 의존한다. hard link를 지원하지 않는 filesystem에서는
  **덮어쓰는 fallback 없이** `E_ARTIFACT_PROMOTE`로 실패한다. 그런 filesystem에서 실행하지 않았다.
- 중단 시나리오는 실제 프로세스 강제 종료가 아니라 결정적 failure-injection hook으로 재현했다.
  hook은 §3.4의 완료 순서에 정확히 대응하는 네 지점이다 — chunk 읽기 직후(`on_chunk`),
  CAS 승격 직후(`after_promote`), 출력 승격 완료 직후(`after_stage_outputs`),
  completed 전이 직전(`before_completed_write`). **production 기본값에서는 어떤 hook도
  실행되지 않는다** (`FailureInjection`을 명시적으로 넘기지 않으면 전부 `None`).
- 실제 ASR·번역·OCR·metric 알고리즘, 모델·GPU, worker supervision, 멀티프로세스 scheduler,
  외부 corpus, Context Bundle 구조는 구현하지 않았다.
- **미정값을 채우지 않았다.** U-07·U-12·U-13·U-15·U-16·U-18·U-19·U-22·U-26·U-27은 그대로다.
  U-16이 미정이므로 자동 삭제·GC·eviction·quota가 없다.

### 12.5 TASK-006 공용 helper 추출

TASK-006 validator와 keyword 해석을 복제하지 않기 위해(§3.6) JSON 로딩·`SchemaSet`·
`SchemaValidator`·timestamp/portable path 의미 검사를 `schema_core.py`로 옮기고,
`eval_contracts`는 그 이름을 그대로 재수출한다. `SchemaValidator.validate()`에 선택적
`pointer` 인자만 추가했다 (`job-v1.schema.json#/$defs/AttemptRecord` 검사용).

추출 전후 **H-01~H-14 판정·오류 코드·위치·메시지·출력 순서가 완전히 동일**한 것을
저장소 밖에서 dump 비교로 확인했고, `tests/test_eval_contracts.py`의
`SharedSchemaCoreTests`가 "두 모듈이 같은 객체를 쓴다"는 사실을 고정한다.

### 12.6 실행한 검증

```bash
make verify-task-028      # J-01~J-16 fixture + store/runtime test + smoke + 기존 전체 verify
make verify-task-006      # H-01~H-14 + TASK-006 계약 test + 기존 전체 verify
make verify               # static + 전체 unit + 실제 FFmpeg smoke
make verify-task-028 PYTHON=python3.12
make verify-task-006 PYTHON=python3.12
git diff --check
git status --short
```

### 12.7 mutation 감사 (저장소 밖 임시 사본)

`artifact_store.py`·`job_runtime.py`의 검사를 **하나씩 무력화**해 회귀 테스트가 실제로
실패하는지 확인했다. 저장소 파일은 바꾸지 않았다.

**34개 mutation 중 34개 탐지.**

| 묶음 | mutation | 결과 |
|---|---|---|
| cache key | config·implementation·dependency·model·context·chunking·source fingerprint 각각 제거 (7종) | 전부 탐지 |
| cache key | 직접 dependency cache key 제거 (downstream invalidation 무력화) | 탐지 |
| cache key | 선택 항목의 부재를 canonical 값에서 생략 | 탐지 |
| checkpoint | completed 기록을 artifact 재검증보다 먼저 수행 | 탐지 |
| checkpoint | cache hit 전 artifact hash 재검증 제거 | 탐지 |
| checkpoint | running attempt를 completed hit로 재사용 | 탐지 |
| checkpoint | running attempt를 보존하지 않고 같은 ID 재사용 | 탐지 |
| checkpoint | callable 호출 전 running attempt 기록 제거 | 탐지 |
| resume | job fingerprint 비교 제거 | 탐지 |
| CAS | no-overwrite 승격을 `os.replace` overwrite로 변경 | 탐지 |
| CAS | 기존 object hash 재검증 제거 (무조건 dedupe hit) | 탐지 |
| CAS | 승격된 최종 바이트 재검증 제거 | 탐지 |
| CAS | `verify_ref`의 hash·size·존재 확인 각각 제거 (3종) | 전부 탐지 |
| path | unsafe path 검사 제거 / root containment 제거 / Windows 비호환 segment 제거 / Windows 예약 장치명 제거 | 전부 탐지 |
| 입력 | descriptor stat 복사 전후 비교 제거 | 탐지 |
| 민감정보 | attempt record에 source absolute path 기록 / 실패 메시지에 원문 포함 | 전부 탐지 |
| DAG | 중복 stage ID·없는 dependency·cycle 검사 각각 제거 (3종) | 전부 탐지 |
| JSON | canonical JSON의 NaN/Infinity 금지 해제 / key 정렬 해제 | 전부 탐지 |
| 순서 | topological 순서의 결정성 제거 | 탐지 |

**정직하게 적는 두 가지.**

1. **`DAG cycle 검사 제거`는 assertion 실패가 아니라 무한 루프로 나타난다.** 감사 driver에
   per-run timeout을 두어 "정지하지 않음"을 실패로 센다. 실제 코드에는 cycle 검사가 있으므로
   `deterministic_order`는 항상 종료한다.
2. **처음 두 라운드에서 3건이 미탐지였다.** 숨기지 않고 그 3건을 관측 가능하게 만드는 검사를
   추가해 마지막 라운드에서 전부 탐지되게 했다.
   - `선택 항목의 부재 생략` → `stage_cache_key_document()`를 노출해 canonical 문서의
     **필드 집합 자체**를 `CACHE_KEY_FIELDS`로 고정하고, key가 문서를 거르지 않고 그대로
     해싱한 값인지 **값이 빈 stage로도** 확인한다.
   - `승격된 최종 바이트 재검증 제거` → `after_promote` hook으로 승격 직후 파일을 손상시켜
     재검증이 실제로 동작하는지 확인한다.
   - `completed 기록을 재검증보다 먼저 수행` → `before_completed_write` hook으로 completed
     전이 직전에 중단시킨다. 순서가 뒤바뀐 구현이면 이 시점에 이미 completed record가 남아
     다음 실행이 hit가 되므로 구분된다.

### 12.8 REVIEW-018 변경 요청 반영 (2차 커밋)

`REVIEW-018` (PR #37, 리뷰 commit `a089817…`)이 고정 HEAD `9c60ccb…`에서 **변경 요청**으로
지목한 M-01~M-05를 제한 범위로 반영했다. REVIEW-018 원문과 PR #37, `main`은 수정하지 않았다.
다섯 반례를 먼저 production API로 **재현한 뒤** 고쳤다.

| ID | 반영 위치 |
|---|---|
| **M-01** | `job_runtime.py`: `ATTEMPT_STATE_RULES` 표와 `check_attempt_semantics()` 신설. `_read_attempts()`가 schema 검사 뒤, **cache lookup 전에** 호출한다. `completed`는 `outputs`가 비어 있을 수 없고 `verified_artifact_count == len(outputs)`·`verified_artifact_bytes == sum(byte_size)`가 성립해야 하며 `ended_at`·`wall_duration_seconds`가 있어야 한다. 완료가 아닌 상태는 출력·검증 집계를 가질 수 없다. 코드 `E_CHECKPOINT_INVALID`, 위치는 실제 record 파일 + JSON Pointer |
| **M-02** | `_run_stage()`가 `_lookup_cache()` **이전에** `_preserve_running_attempts()`를 호출한다. hit 여부와 무관하게 stale running이 `interrupted`로 전이된다. 전이 record는 `error_code=E_STATE_TRANSITION`·`error_location`·`interrupted_at`을 가진다 |
| **M-03** | `artifact_store.opaque_identity_error()` 신설, `preflight()`가 filesystem mutation 전에 호출한다. POSIX 절대·Windows drive·UNC·traversal·backslash·`~`·경로 구분자를 `E_UNSAFE_PATH` @ `source_identity`로 거부한다. **사유 문자열에 값 자체를 담지 않는다** |
| **M-04** | `ContractViolation`에 `temp_paths`를 실었다. `add_file()`은 실패 시 `surviving_temp_paths()`로 **실제 남아 있는** 임시 경로만 예외에 붙이고, `_fail_attempt()`가 안정 `error_code`·`error_location`·`temp_paths`를 failed record에 기록한다 |
| **M-05** | `check_seed_inputs()` 신설, `preflight()`에서 호출한다. 모든 seed entry를 `common-v1.schema.json#/$defs/ArtifactRef`로 검사하고 `verify_ref()`로 존재·hash·size까지 mutation 전에 확인한다. 위치는 `seed_inputs/<stage>/<index>` 이하로 실제 입력에서 해석된다 |

**zero-output stage는 계약에 없다.** J-01~J-16과 smoke의 모든 stage가 출력을 하나 이상
만들므로 `outputs=[]`인 `completed` record를 거부하는 것이 현재 stage 계약과 일치한다.
계약을 임의로 확장하지 않았다.

**`ended_at`을 지어내지 않는다.** interrupted attempt가 **언제 죽었는지는 관측하지 못했다.**
그래서 `ended_at`·`wall_duration_seconds`를 만들어 내지 않고, 전이를 **관측한** 시각을
`interrupted_at`이라는 별도 필드로 남긴다. 측정하지 않은 값을 쓰지 않는다는 §3.7과 같은 원칙이다.

**schema 변경은 한 곳뿐이다.** `job-v1.schema.json`에 `interrupted_at`을 추가하고 `ended_at`의
description을 명확히 했다. `common-v1.schema.json`과 TASK-006 schema 7개, H-01~H-14 fixture,
TASK-022 구현은 **blob 무변경**이다. J-01~J-16 fixture도 변경하지 않았다 — 16건의 관측값이
그대로 유지된다.

### 12.9 REVIEW-018 반영 뒤 mutation 감사

M-01~M-05의 새 검사 16종을 더해 저장소 밖 임시 사본에서 다시 감사했다.

**50개 mutation 중 50개 탐지. 미탐지 0건, 감사 불가(SKIP) 0건.**

| 묶음 | mutation | 결과 |
|---|---|---|
| M-01 | semantic invariant 호출 제거 / completed 빈 outputs 허용 / `verified_artifact_count` 일치 검사 제거 / `verified_artifact_bytes` 일치 검사 제거 / 상태별 필수·금지 필드 검사 제거 / 완료가 아닌 상태의 outputs 금지 제거 (6종) | 전부 탐지 |
| M-02 | hit 반환 전 보존을 miss 경로로 되돌림 / interrupted record의 code·location·관측 시각 제거 (2종) | 전부 탐지 |
| M-03 | `source_identity` 검사 제거 / 거부 사유에 값 자체를 포함(경로 누출) (2종) | 전부 탐지 |
| M-04 | 예외에 보존 temp 경로 미탑재 / failed record에 code·location 미기록 / surviving 필터 제거 (3종) | 전부 탐지 |
| M-05 | seed 선행 검증 제거 / seed schema 검사만 제거 / seed artifact 존재·hash·size 확인 제거 (3종) | 전부 탐지 |
| 기존 §12.7의 34종 | cache key·checkpoint·CAS·path·입력 변경·민감정보·DAG·JSON·순서 | 전부 탐지 유지 |

**중복 방어로 미탐지된 항목은 없다.** 이전 라운드에서 패턴이 낡아 SKIP된 2건
(`승격된 최종 바이트 재검증 제거`, `surviving 필터 제거`)은 SKIP을 증거로 삼지 않고
패턴을 실제 코드에 맞춘 뒤 다시 돌려 두 건 모두 탐지되는 것을 확인했다.

§12.7의 주석은 그대로 유효하다 — `DAG cycle 검사 제거`는 assertion 실패가 아니라 무한
루프로 나타나며, per-run timeout이 "정지하지 않음"을 실패로 센다.

### 12.10 REVIEW-019 변경 요청 반영 (3차 커밋)

`REVIEW-019` (PR #38, 리뷰 commit `c57e22b…`)가 고정 HEAD `2613981…`에서 **변경 요청**으로
지목한 M-01-R1~R3·M-05-R1을 제한 범위로 반영했다. REVIEW-018·019 원문과 PR #37·#38,
`main`은 수정하지 않았다. 네 반례를 먼저 production API로 **재현한 뒤** 고쳤다.

REVIEW-019는 REVIEW-018의 다섯 직접 반례가 모두 해소됐음을 확인했고, `interrupted_at`으로
`ended_at`을 추정하지 않은 판단도 승인했다.

| ID | 반영 위치 |
|---|---|
| **M-01-R1** | `check_attempt_identity()`·`check_attempt_uniqueness()` 신설. `_read_attempts()`가 각 record의 `job_id`·`stage_id`·`attempt_id`를 현재 spec·stage·**실제 파일 stem**과 대조하고, `aNNNN`의 숫자와 `attempt_number`가 일치하는지 검사하며, 디렉터리 안의 ID·number 중복을 거부한다. `_lookup_cache()`가 record만이 아니라 **`(path, record)` 연결을 유지**해 돌려주고, `StageOutcome.attempt_path`에 실제 경로를 담아 manifest가 검증된 실제 path만 기록한다 |
| **M-01-R2** | `JobRuntime.check_manifest_semantics()`·`_check_stage_state()` 신설. 기존 manifest를 쓰거나 덮어쓰기 **전에** schema/runtime version·job ID·pipeline ID·source identity 존재 여부와 값·DAG topology와 선언 순서를 대조하고, stage ID 유일성·DAG membership을 검사하며, 각 stage state가 가리키는 **실제 attempt 파일**의 존재·record identity·status·cache key 일치를 확인한다. `completed` manifest는 DAG의 모든 stage를 정확히 한 번 포함하고 전부 completed attempt를 가리켜야 한다 |
| **M-01-R3** | `ATTEMPT_STATE_RULES` 강화 — `failed`는 `error_code`·`error_location` 필수, `running`은 `error_code`·`error_location`·`interrupted_at`·`ended_at`·`wall_duration_seconds` 전부 금지. `check_attempt_semantics()`가 저장된 `error_code`가 선언된 `ERROR_CODES`에 속하는지, `interrupted`의 code가 정확히 `E_STATE_TRANSITION`인지 검사한다 |
| **M-05-R1** | `check_seed_inputs()`가 `sorted()` **전에** 모든 key의 타입과 값을 검사한다. non-string key와 안전하지 않은 stage 식별자를 `E_SCHEMA` @ `seed_inputs`로 거부하며 **key 값을 메시지에 복제하지 않는다** |

**실패 경로가 기존 manifest를 덮어쓰지 않게 했다.** `run_job()`이 이번 실행에서 실제로
attempt record를 쓴 경우에만(`progress`가 비어 있지 않을 때만) 실패 manifest를 기록한다.
checkpoint 무결성 거부처럼 **새 evidence를 만들지 않은** 실행은 기존 manifest를 건드리지 않는다.

**`E_RESUME_FINGERPRINT`가 먼저다.** manifest semantic 검사는 job fingerprint 비교를
통과한 뒤에만 실행한다. 그래야 J-11의 "fingerprint가 다르면 `E_RESUME_FINGERPRINT` @
`job_fingerprint`" 계약이 그대로 유지되고, fingerprint는 유지한 채 identity만 조작한
manifest는 `E_CHECKPOINT_INVALID`로 잡힌다.

**중복 방어를 숨기지 않는다.** `check_attempt_uniqueness()`는 file stem 검사가 함께 있으면
디렉터리 경로로는 도달하지 않는다 — 서로 다른 두 파일이 같은 `attempt_id`를 가질 수 없고,
ID가 `attempt_number`를 결정하기 때문이다. 그래서 이 검사는 stem 검사에 대한 **중복 방어**이며,
회귀 테스트는 함수 자체를 반례로 검증하고 디렉터리 경로로 실제 도달하는 형태(`a0002.json`
안의 number 1)는 `attempt_number` 위치에서 별도로 고정한다.

**schema 변경 없음.** 이번 반영은 `job_runtime.py`와 `tests/test_job_runtime.py`만 바꾼다.
`schemas/job-v1.schema.json`, `artifact_store.py`, `common-v1.schema.json`, TASK-006
schema·fixture, TASK-022 구현, J-01~J-16 fixture, `schema_core.py`, `Makefile`,
`.gitignore`, `docs/ARCHITECTURE.md`는 **blob 무변경**이다.

### 12.11 REVIEW-019 반영 뒤 mutation 감사

M-01-R1~R3·M-05-R1의 새 검사 22종을 더해 저장소 밖 임시 사본에서 다시 감사했다.

**74개 mutation 중 72개 탐지. 감사 불가(SKIP) 0건, 미탐지 2건.**

| 묶음 | mutation | 결과 |
|---|---|---|
| M-01-R1 | record `job_id` 대조 / `stage_id` 대조 / 파일 stem 대조 / `attempt_id`↔`attempt_number` 수치 일치 / 정체성 검사 호출 자체 (5종) | 전부 탐지 |
| M-01-R1 | attempt ID·number 중복 검사 **호출** 제거 | **미탐지** — 아래 참조 |
| M-01-R1 | manifest가 record 내부 ID로 경로를 재구성 | **미탐지** — 아래 참조 |
| M-01-R2 | semantic validator 호출 / job·pipeline identity / DAG topology / completed 완전성 / stage state 중복 / manifest↔attempt 연결 / dangling attempt_path / status↔record status / 실패 경로의 무조건 덮어쓰기 (9종) | 전부 탐지 |
| M-01-R3 | failed의 error 필수 규칙 / running의 `error_location` 금지 / 선언된 코드 집합 / interrupted의 정확한 code (4종) | 전부 탐지 |
| M-05-R1 | seed key 타입 선행 검사 / key 식별자 유효성 검사 (2종) | 전부 탐지 |
| 기존 50종 (REVIEW-018까지) | cache key·checkpoint·CAS·path·입력 변경·민감정보·DAG·JSON·순서·M-01~M-05 | 전부 탐지 유지 |

**미탐지 2건 — 숨기지 않고 상위 방어를 밝힌다.**

두 항목 모두 **중복 방어**이며, 각각 상위 검사가 대신 잡는다. 그리고 그 사실을
**보완 mutation으로 실증**했다.

1. **attempt ID·number 중복 검사 호출 제거.** 상위 방어는 **파일 stem 대조**다. 서로 다른
   두 파일이 같은 `attempt_id`를 가질 수 없고 ID가 `attempt_number`를 결정하므로, 디렉터리
   경로로는 중복이 도달하지 않는다. 검사 자체가 공허하지 않다는 것은 보완 mutation
   `중복 검사 함수 본문 무력화`가 **탐지**되는 것으로 확인했다 — 직접 단위 테스트가 잡는다.
   디렉터리 경로로 실제 도달하는 형태(`a0002.json` 안의 number 1)는 `attempt_number`
   위치에서 별도로 고정한다.
2. **manifest가 record 내부 ID로 경로를 재구성.** 상위 방어는 **정체성 검사**다. 정체성이
   강제되면 `attempt_id == 파일 stem`이므로 재구성한 경로와 실제 경로가 같아진다. 두 방어를
   **함께** 제거한 보완 mutation `정체성 검사 제거 + manifest 경로 재구성`은 **탐지**되므로,
   dangling manifest 경로가 실제로 막혀 있음이 확인된다.

이전 라운드에서 낡은 패턴으로 SKIP된 4건(`running attempt를 completed hit로 재사용`,
`callable 호출 전 running attempt 기록 제거`, `M-01 semantic invariant 검사 자체를 제거`,
`M-02 hit 반환 전 stale running 보존`)은 SKIP을 증거로 삼지 않고 패턴을 실제 코드에 맞춘 뒤
다시 돌려 **전부 탐지**되는 것을 확인했다.

처음 라운드에서 미탐지였던 `manifest status ↔ record status 대조 제거`와
`seed key 타입 선행 검사 제거`는 회귀 테스트의 공백이었다. 각각 `completed` 완전성 규칙이
가리지 않는 `failed` manifest 경로와, 정수 key의 **진단 사유**를 고정하는 테스트를 추가해
마지막 라운드에서 탐지되게 했다.

### 12.12 REVIEW-020 변경 요청 반영 (4차 커밋)

`REVIEW-020` (PR #39, 리뷰 commit `801a804…`)이 고정 HEAD `45459b0…`에서 **변경 요청**으로
지목한 M-01-R2-R1·M-01-R2-R2를 제한 범위로 반영했다. REVIEW-018·019·020 원문과
PR #37·#38·#39, `main`은 수정하지 않았다. 두 반례를 먼저 production API로 **재현한 뒤** 고쳤다.

REVIEW-020은 REVIEW-018의 다섯 반례와 REVIEW-019의 네 반례가 모두 해소됐음을 확인했고,
fingerprint를 semantic 검사보다 먼저 처리하는 판단과 새 evidence가 없는 거부에서 기존
manifest를 수정하지 않는 판단도 유지 승인했다.

| ID | 반영 위치 |
|---|---|
| **M-01-R2-R1** | `JobRuntime.canonical_attempt_path()` 신설. `_check_stage_state()`가 stage state의 `attempt_path`를 현재 `job_id`·`stage_id`·`attempt_id`로 계산한 `jobs/<job_id>/stages/<stage_id>/attempts/<attempt_id>.json`과 **문자열 수준에서 정확히** 비교한다. 존재하고 내부 record가 유효하더라도 relocated·aliased·잘못된 parent 경로는 checkpoint로 인정하지 않는다. manifest 경로로 도달한 record에도 실제 path·spec·stage로 `check_attempt_identity()`와 `check_attempt_semantics()`를 적용한다. 코드 `E_CHECKPOINT_INVALID`, 위치 `.../attempt_path` |
| **M-01-R2-R2** | `JobRuntime._check_execution_prefix()` 신설. manifest의 stage ID 목록이 `deterministic_order(spec)`의 **정확한 prefix**인지 검사한다. `completed`는 전체 순서와 정확히 일치해야 하고, `running`·`failed` 등 비완료 상태는 빈 prefix를 포함한 유효 prefix만 허용한다. downstream-only subset·dependency gap·out-of-order state를 `E_CHECKPOINT_INVALID`와 실제 `stages/<index>/stage_id` 또는 `stages` 위치로 거부한다 |

**왜 canonical 경로여야 하는가.** cache discovery는 canonical 디렉터리만 읽는다. 따라서
relocated 사본을 가리키는 manifest를 받아들이면 checkpoint는 유효해 보이는데 lookup은 miss가
되어, 비싼 stage를 다시 실행하고 손상 manifest를 덮어쓴다. 존재·schema·필드 일치만으로는
이 모순을 막을 수 없다.

**왜 prefix여야 하는가.** 이 runtime은 `deterministic_order(spec)` 순서로 실행하며 성공한
stage를 차례로 누적한다. 그러므로 저장된 stage 목록은 그 순서의 completed prefix 외에는
runtime이 만들 수 없다. `[beta]`는 alpha dependency evidence가 빠진 모순 graph다.

**기존 위치 하나가 더 앞선 검사로 옮겨졌다 (약화 아님).** stage state의 `attempt_id`만 바꾸는
조작은 canonical 경로도 함께 어긋나므로 이제 `/attempt_id`가 아니라 `/attempt_path`에서 잡힌다.
거부 자체는 그대로이며, `attempt_id`와 `attempt_path`를 함께 canonical로 옮긴 경우도 그 파일이
없으므로 거부되는 것을 별도 회귀로 고정했다.

**알려진 중복 방어 (숨기지 않는다).** `_check_stage_state()`의 state↔record `attempt_id` 직접
비교는 canonical 경로 결박과 `check_attempt_identity()`가 함께 있으면 도달하지 않는다 —
canonical 경로가 `attempt_id`를 결정하고 정체성 검사가 record의 `attempt_id`를 파일 stem에
묶기 때문이다. 진단을 좁혀 주므로 유지했고, mutation 감사 결과에 그대로 적는다.

**schema·fixture·Makefile·artifact store 변경 없음.** 이번 반영은 `job_runtime.py`와
`tests/test_job_runtime.py`만 바꾼다.

### 12.13 REVIEW-020 반영 뒤 mutation 감사

M-01-R2-R1·R2의 새 검사 7종을 더해 저장소 밖 임시 사본에서 다시 감사했다.

**81개 mutation 중 79개 탐지. 감사 불가(SKIP) 0건, 미탐지 2건.**

| 묶음 | mutation | 결과 |
|---|---|---|
| M-01-R2-R1 | canonical path 대조 제거 / canonical을 존재 여부로만 대체 / 가리킨 record의 정체성 검사 제거 / 가리킨 record의 semantic 검사 제거 (4종) | 전부 탐지 |
| M-01-R2-R2 | 실행 prefix 검사 호출 제거 / prefix 순서 비교를 집합 비교로 약화 / completed 전체 순서 일치 검사 제거 (3종) | 전부 탐지 |
| 기존 74종 (REVIEW-019까지) | cache key·checkpoint·CAS·path·입력 변경·민감정보·DAG·JSON·순서·M-01~M-05·M-01-R1~R3·M-05-R1 | 전부 탐지 유지 |

**이번 라운드에서 스스로 만든 감사 공백 2건을 복구했다.** 새 검사가 기존 mutation을 가려
이전에 탐지되던 두 항목이 미탐지로 바뀌었는데, 그대로 두지 않고 회귀 테스트를 보강했다.

1. **`실패 경로가 기존 manifest를 무조건 덮어씀`** — canonical path 결박이 기존 반례를 더
   이른 단계에서 잡아 `progress` 가드가 실행되지 않게 됐다. manifest 자체는 정상이고
   **manifest가 참조하지 않는** 두 번째 attempt record만 손상시켜 stage loop 안에서 거부되는
   경로를 새 회귀로 추가했고, 이 mutation은 다시 **탐지**된다.
2. **`stage state 중복 검사 제거`** — 실행 prefix 검사가 중복도 함께 잡아 단독 mutation이
   무해해졌다. 중복 진단 자체를 고정하는 회귀(`중복` 사유 확인)를 추가해 다시 **탐지**되게 했고,
   두 검사를 **함께** 제거한 조합 mutation도 탐지되는 것을 확인했다.

**남은 미탐지 2건은 §12.11에 이미 기록한 REVIEW-019의 중복 방어 그대로다.**
`attempt ID·number 중복 검사 호출 제거`는 파일 stem 대조가, `manifest가 record 내부 ID로
경로를 재구성`은 정체성 검사가 상위 방어이며, 각각 보완 mutation(함수 본문 무력화 / 두 방어
동시 제거)이 **탐지**되는 것으로 실증했다. 새로 생긴 미탐지는 없다.

**추가로 확인한 중복 방어.** `_check_stage_state()`의 state↔record `attempt_id` 직접 비교는
canonical 경로 결박과 정체성 검사가 함께 있으면 도달하지 않는다. 진단을 좁혀 주므로 유지했다.

### 12.14 REVIEW-021 변경 요청 반영 (5차 커밋)

`REVIEW-021` (PR #40, 리뷰 commit `c35f5b7…`)이 고정 HEAD `f0c5e86…`에서 **변경 요청**으로
지목한 M-01-R2-R3을 제한 범위로 반영했다. REVIEW-018·019·020·021 원문과 PR #37·#38·#39·#40,
`main`은 수정하지 않았다. 반례를 먼저 production API로 **재현한 뒤** 고쳤다.

REVIEW-021은 REVIEW-020의 두 반례가 모두 해소됐음을 확인했고, canonical path 문자열 동일성과
deterministic prefix 결박 판단도 유지 승인했다.

| ID | 반영 위치 |
|---|---|
| **M-01-R2-R3** | `job_runtime.py` `_check_stage_state()`에 completed prefix 규칙 추가. manifest status와 **무관하게** stage state가 가리키는 **실제 attempt record**가 `status=completed`여야 한다. 기존 state↔record `attempt_status` 일치 검사가 state 값을 record에 묶으므로, 두 검사가 함께 "state와 record가 모두 completed"를 강제한다. 코드 `E_CHECKPOINT_INVALID`, 위치 `.../stages/<index>/attempt_status`. `check_manifest_semantics()`에 있던 **completed manifest 전용** attempt_status 검사는 이 규칙에 완전히 포함되므로 제거했다 — 좁은 규칙을 넓은 규칙으로 바꾼 것이며 약화가 아니다 |

**왜 status와 무관해야 하는가.** `_write_manifest()`는 `outcomes`에서 stage 목록을 만들고,
`outcomes`에는 성공한 stage만 들어간다 (`StageOutcome.attempt_status`는 cache hit·성공 두
경로에서만 `completed`로 설정된다). 그러므로 실패·중단·실행 중 attempt를 가리키는 stage state는
manifest가 `failed`여도 이 runtime이 만들 수 없는 checkpoint다. 받아들이면 실패 evidence가
정상 prefix로 둔갑해 stage가 다시 실행되고, 손상 manifest가 `completed`로 덮어써진다.

**두 검사를 굳이 나눈 이유 (중복 방어를 만들지 않기 위해).** "state가 completed"와
"record가 completed"를 둘 다 직접 검사하면 세 검사가 서로를 가려 **어느 하나를 제거해도 회귀
테스트가 실패하지 않는다.** 실제로 그 형태를 먼저 만들어 mutation 감사에서 미탐지 4건을
관측했고, 그래서 판정 기준을 **실제 record 하나**로 좁혔다. 지금은 일치 검사를 지우면
`state=failed` + `record=completed` 조작이 통과하고, completed 규칙을 지우면 REVIEW-021 반례가
통과한다. 두 검사 모두 단독으로 mutation 탐지된다.

**실패 evidence를 정상화하지 않는다.** 거부는 기존 attempt record를 삭제하지도, `completed`로
고치지도 않는다. `run_job()`은 `check_manifest_semantics()`를 stage loop와 `job_dir` 생성
**이전에** 호출하므로 callable 0회이고 manifest·attempt는 byte 불변이다.

**schema 변경 없음.** `StageState.attempt_status` enum은 그대로 넓게 유지하고 현재 runtime의
completed-prefix 계약을 semantic validator에서만 강제한다. 이번 반영은 `job_runtime.py`와
`tests/test_job_runtime.py`만 바꾼다. `schemas/job-v1.schema.json`, `artifact_store.py`,
`common-v1.schema.json`, TASK-006 schema·fixture, TASK-022 구현, J-01~J-16 fixture,
`schema_core.py`, `Makefile`, `.gitignore`, `docs/ARCHITECTURE.md`는 **blob 무변경**이다.

### 12.15 REVIEW-021 반영 뒤 회귀와 mutation 감사

**새 회귀 테스트 12건** — `tests/test_job_runtime.py::ReviewM01R2R3CompletedPrefixTests`.
전체 test 수는 343 → 355, `test_job_runtime.py`는 137 → 149다.

| 종류 | 테스트 |
|---|---|
| 반례 | `failed`·`interrupted`·`running` attempt를 stage state로 넣은 manifest 3건, `ATTEMPT_STATE_RULES`의 비완료 상태 전수 1건, state만 `completed`라고 주장한 record 1건, 실패 evidence 보존 1건 |
| 정상 사례 | `failed + stages=[]`, `failed + [alpha completed]`, `running + completed prefix`, `completed + 전체 completed order`, 정상 prefix에서 alpha hit 후 beta만 실행, production이 쓰는 manifest는 언제나 completed prefix |

각 반례는 실제 callable 실패로 valid `failed` attempt를 먼저 만들고, schema 검증이 통과하는
것을 확인한 뒤 semantic 검증과 `run_job()`이 `E_CHECKPOINT_INVALID @ .../stages/0/attempt_status`로
거부하는지, callable 0회이고 manifest·attempt record가 byte 불변인지 확인한다.

**저장소 밖 임시 사본 mutation 감사 — 15개 중 15개 탐지. 미탐지 0건, 감사 불가(SKIP) 0건.**

| 묶음 | mutation | 결과 |
|---|---|---|
| M-01-R2-R3 | completed prefix 규칙 제거 / 규칙을 존재 여부로만 약화 / 규칙을 completed manifest에만 적용(REVIEW-021 이전 동작) (3종) | 전부 탐지 |
| 기존 manifest semantic | semantic 검사 호출 자체 / job·pipeline identity / DAG topology / stage state 중복 / dangling attempt_path / execution prefix 호출 / canonical path 결박 / state↔record status 일치 (8종) | 전부 탐지 |
| 기존 attempt | 가리킨 record의 정체성 검사 / semantic 검사 (2종) | 전부 탐지 |
| 기존 실패 경로 | `progress` 가드 제거(무조건 덮어쓰기) | 탐지 |
| 보완 | completed 규칙 + state↔record 일치 검사 **동시** 제거 | 탐지 |

**감사 목록에서 사라진 항목 하나를 밝힌다.** §12.11·§12.13의
`completed manifest의 stage가 completed attempt를 가리키는지 검사 제거`는 그 코드가 더 넓은
규칙으로 교체돼 더 이상 존재하지 않는다. 같은 조작(완료 manifest가 비완료 attempt를 가리킴)은
이제 `completed prefix 규칙 제거` mutation이 대신 덮으며 **탐지**된다.

**§12.11에 기록한 REVIEW-019의 중복 방어 2건은 그대로다.**
`attempt ID·number 중복 검사 호출 제거`는 파일 stem 대조가, `manifest가 record 내부 ID로
경로를 재구성`은 정체성 검사가 상위 방어다. 이번 변경은 두 항목에 영향을 주지 않는다.

### 12.16 REVIEW-018~021 반례 전수 재실행

새 HEAD에서 저장소 밖 script가 **production API만** 호출해 11개 기존 반례와 REVIEW-021의 3개
변형을 다시 실행했다.

| 리뷰 | 반례 | 관측된 코드 · 위치 |
|---|---|---|
| 018 | M-01 완료 evidence 모순 | `E_CHECKPOINT_INVALID @ …/a0001.json/verified_artifact_count`, callable 0회 |
| 018 | M-02 stale running 보존 | hit 경로에서도 `interrupted` + `E_STATE_TRANSITION` + `interrupted_at`, `ended_at` 생성 안 함 |
| 018 | M-03 path 모양 source identity | `E_UNSAFE_PATH @ source_identity`, job tree 미생성, 값 미노출 |
| 018 | M-04 실패 evidence | failed record에 `E_STAGE_FAILED` + location + `temp_paths` |
| 018 | M-05 seed artifact 누락 | `E_ARTIFACT_MISSING @ artifacts/sha256/…`, job tree 미생성 |
| 019 | M-01-R1 record 정체성 | `E_CHECKPOINT_INVALID @ …/a0001.json/job_id`, callable 0회 |
| 019 | M-01-R2 manifest 완결성 | `E_CHECKPOINT_INVALID @ …/manifest.json/stages`, callable 0회 |
| 019 | M-01-R3 error evidence 없는 failed | `E_CHECKPOINT_INVALID @ …/a0001.json`, callable 0회 |
| 019 | M-05-R1 non-string seed key | `E_SCHEMA @ seed_inputs`, job tree 미생성 |
| 020 | M-01-R2-R1 relocated record | `E_CHECKPOINT_INVALID @ …/stages/0/attempt_path`, canonical 보존 |
| 020 | M-01-R2-R2 downstream-only manifest | `E_CHECKPOINT_INVALID @ …/stages/0/stage_id`, callable 0회 |
| **021** | **M-01-R2-R3 failed / interrupted / running** | **`E_CHECKPOINT_INVALID @ …/stages/0/attempt_status`, callable 0회, manifest·attempt byte 불변, 실패 evidence 상태 유지** |

이전 고정 HEAD `f0c5e86…`에서 같은 script를 돌리면 REVIEW-021의 세 변형은 모두
`schema_findings=[] · semantic_findings=[] · calls=1 · run_status=completed ·
manifest_unchanged=false`로 통과한다. 결함과 수정이 같은 입력에서 구분된다.

### 12.17 REVIEW-021 반영 뒤 실행한 검증

```bash
make verify-task-028      # exit 0 — J 16/16, store 36, runtime 149, 전체 355, TASK-028 smoke PASS, FFmpeg smoke PASS
make verify-task-006      # exit 0 — H 14/14, 계약 162, 전체 355, FFmpeg smoke PASS
make verify               # exit 0 — 전체 355, FFmpeg smoke PASS
make verify-task-028 PYTHON=python3.12   # exit 0 — J 16/16, 전체 355, smoke PASS
make verify-task-006 PYTHON=python3.12   # exit 0 — H 14/14, 계약 162, 전체 355, smoke PASS
git diff --check
git status --short
```

`ffmpeg`는 이 실행 환경에 처음부터 설치돼 있지 않아 컨테이너에 설치한 뒤 실행했다.
저장소에는 의존성·CI·외부 데이터를 추가하지 않았다.

### 12.18 남은 미검증 경계 (REVIEW-021 §8과 동일)

- Windows 11/NTFS 실제 실행
- hard-link 미지원 filesystem의 실제 동작
- 실제 프로세스 강제 종료와 OS crash durability
- 멀티프로세스/TOCTOU 경합
- JSON Schema Draft 2020-12 전체 구현과 외부 meta-validator

이번 반영은 Linux 단일 프로세스 기본 경로에서 재현·수정·재검증했다.
