# TASK-028 — Content-addressed artifact store와 재개 가능한 stage runtime

| 항목 | 값 |
|---|---|
| **ID** | TASK-028 |
| **Owner** | Claude Code 구현 세션 |
| **Reviewer** | Lean Root Orchestrator — 구현 세션과 분리된 고정 HEAD Gate H 검토 |
| **Phase** | Phase 1a / shared storage·orchestrator foundation |
| **Status** | `Not started — contract proposed` |
| **기준 main** | `d000284d71e18788a89c8be4ca3c45c26db35b5a` |
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

## 5. 수정 가능 범위

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

- 이 TASK 계약이 `main`에 병합되기 전에는 Claude Code가 구현을 시작하지 않는다.
- 코드는 Claude Code가 작성하고 Lean Root가 고정 HEAD에서 직접 재현한다.
- 작성자는 자기 변경을 승인하지 않는다.
- TASK-022의 원자적 partial/no-overwrite 구현은 참고할 수 있지만, 해당 파일을 공용 runtime으로
  대규모 refactor하거나 기존 smoke 의미를 바꾸지 않는다.
- TASK-006의 validator를 재사용할 때 이름만 공유하고 의미가 갈라지는 복제 구현을 만들지 않는다.
- 미정 U-XX나 모델·corpus·Context Bundle 세부를 이 TASK에서 결정하지 않는다.
