# EVAL_HARNESS.md — Phase 1a 평가 하네스 실행 계약

상태: **TASK-005 완료 — PR #25 병합**

이 문서는 [EVALS.md](EVALS.md)의 지표 계산 규약을 실제 실행 단위로 묶는 계약이다.
지표 알고리즘 자체는 EVALS가 정답이며, 이 문서는 입력 검증·실행 상태·필수 metric plan·artifact·
실패·재개·비교·사람 검토를 고정한다. 구체 스키마는 후속 TASK-006에서 확정한다.

## 1. 목표와 범위

하나의 명령이 같은 입력·설정에서 다음을 재현 가능하게 만든다.

    preflight → run → per-source metric → source/target 분리 집계 → 비교 → report

이번 설계가 고정하는 것:

- 원문 ASR 축과 한국어 번역 자막 축의 분리
- metric의 필수 시도 여부와 미지원/표본 부족 처리
- 번역 품질 자동 지표와 사람 검토의 역할
- 실행 상태, 실패 보존, 중단 후 재개 경계
- 필수 fixture와 기계 판독 artifact

범위 밖:

- ReferenceBundle/v1 필드·JSON Schema 확정 (TASK-006)
- 평가 하네스 코드와 의존성 추가
- 외부 코퍼스 다운로드·계정·cache 생성
- ASR·번역 모델·공급자·API 선택
- U-07 절대 품질 목표, U-18·U-19·U-26·U-27의 미정 수치

## 2. 불변식

1. 원문 source와 번역 target 지표를 합계·평균·가중 점수로 만들지 않는다.
2. 가설/정답의 축 또는 대상 언어가 다르면 낮은 점수가 아니라 계약 실패다.
3. 미지원은 0점이 아니며 결측 평균에 넣지 않는다.
4. 같은 source에서 파생된 조각은 dev/frozen-test를 넘나들지 않는다.
5. 비교는 같은 표본에 baseline과 candidate를 실행하는 paired comparison이다.
6. 실패·중단 기록과 부분 artifact를 삭제하거나 완료 artifact로 가장하지 않는다.
7. 원본 미디어와 사용자 텍스트를 로그에 복제하지 않는다.
8. metric·normalizer·dataset·reference·pipeline fingerprint가 다르면 같은 실행으로 재개하지 않는다.
9. frozen-test 결과를 보고 조정하면 해당 split을 dev로 강등하고 접근 기록을 보존한다.
10. 자동 지표 하나만으로 제품 품질이나 채점 성적을 보장하지 않는다.

## 3. 입력과 preflight

### 3.1 필수 입력

| 입력 | 필수 내용 |
|---|---|
| dataset manifest | dataset_id, split, source 그룹, sample ID, license boundary, source/speaker 분리 증거 |
| reference set | ReferenceBundle/v1 목록과 content hash |
| hypothesis set | pipeline/config fingerprint, source/target axis, target language, artifact hash |
| metric plan | metric ID·버전·축·필수 여부·필요 정답·normalizer·통계 단위 |
| run config | seed 목록, baseline run, 재현성 등급, output root |

### 3.2 preflight 판정 순서

1. 파일 존재·hash·schema version 확인
2. sample ID의 중복·누락·고아 hypothesis 확인
3. dev/frozen-test source·speaker 교집합 0 확인
4. 축·target_language="ko"·timebase·TimeMapping 계약 확인
5. metric별 필요 정답과 capability 확인
6. output 경로가 원본·reference·hypothesis 경로와 분리됐는지 확인

schema·축·언어·split 누출·hash 불일치는 run_status: "invalid"로 종료한다.
metric 하나의 필요 정답 부족은 실행 전체를 무효화하지 않고 그 metric을 unsupported로 계획한다.

## 4. 실행 상태와 재개

| run 상태 | 의미 | 완료 artifact 승격 |
|---|---|---|
| planned | preflight 전/중 | 금지 |
| invalid | 입력·schema·축·split 계약 실패 | 금지, 진단만 보존 |
| running | 유효 입력으로 계산 중 | 금지 |
| completed | 필수 metric이 모두 computed 또는 사전 허용된 insufficient_n | 허용 |
| partial | 일부 결과는 있으나 필수 metric이 failed·예상 밖 unsupported | 금지 |
| failed | 실행기 자체가 진행 불가 | 금지 |
| aborted | 사용자 중단·프로세스 종료 | 금지, 재개 후보 |

metric 상태는 computed | unsupported | insufficient_n | failed 네 값이다.
unsupported와 insufficient_n에는 value를 쓰지 않고 reason·n·필요 capability를 기록한다.

재개는 다음이 모두 같을 때만 허용한다.

- dataset/reference/hypothesis/metric-plan/config fingerprint
- metric 구현 버전과 norm-v1 버전
- 완료된 per-source shard의 content hash

불일치하면 새 run_id로 시작한다. shard는 임시 파일에 쓴 뒤 hash 검증과 atomic rename 후에만
완료로 표시한다. 실패 event는 append-only로 남긴다.

## 5. 필수 metric plan

### 5.1 원문 축 source

| metric 묶음 | 정책 |
|---|---|
| CER | 모든 언어에서 필수 시도. EVALS §4.1 알고리즘 A·D |
| WER | 공백 기반 언어만. 일본어 등 문자 단위 언어는 unsupported, CER로 대체 표시 |
| 무음 4종 | 환각 chars/min·events/hour·반복 루프·무음 오탐률을 같은 표에 보고 |
| timing 3종 | 시작/종료 오차, cue 누락률, cue 허위율. 어느 하나도 단독 승격 근거로 쓰지 않음 |
| format | CPS·줄 길이·줄 수·표시 시간·간격·같은 stream 내 겹침 |
| language switch | language_spans와 capability가 있으면 LID·전환점·intra-sentential을 분리 |
| overlap | cpWER 요건 충족 시 계산. 아니면 overlap coverage를 별도 이름으로 보고 |

### 5.2 번역 축 target:ko

| metric 묶음 | 정책 |
|---|---|
| **chrF2** | 참조 기반 자동 primary. §6의 고정 signature 사용 |
| 무음 4종 | 번역 단계의 추가 환각까지 같은 규약으로 측정 |
| timing 3종 | target cue 기준으로 source 축과 분리 보고 |
| format | 한국어 profile. U-18 미정값은 명시적 unsupported 또는 config 값과 함께 실험 |
| 사람 검토 | dev milestone과 frozen-test 승격 판단에 §7 blind paired review 사용 |

두 축 모두 계층은 최소 language × degradation_kind × severity × overlap × source_type을 유지한다.
n이 부족한 계층을 합쳐 숨기지 않는다.

## 6. 한국어 번역 품질 계약

### 6.1 필수 자동 지표 — chrF2

첫 구현의 reference-based primary는 sacreBLEU의 chrF2다.

| 항목 | 고정값 |
|---|---|
| char order | 6 |
| word order | 0 — chrF++가 아니라 문자 기반 chrF2 |
| beta | 2 |
| whitespace | 제외 |
| case | mixed |
| smoothing | effective order |
| 입력 | norm-v1을 통과한 detokenized 한국어 target hypothesis/reference |
| 계산 단위 | cue 단위 점수로 승격 판단 금지. source별 시간순 연결 점수와 전체 corpus 점수 |
| 재현 정보 | sacreBLEU 전체 signature·버전·reference 수·norm_version 기록 |

한국어 norm-v1이 없으면 chrF2는 unsupported다. 의미가 같은 자연스러운 번역도 표현이 다르면
점수가 낮아질 수 있으므로 chrF2 단독으로 후보를 승격하지 않는다.

BLEU·TER는 필수 지표가 아니다. COMET·BERTScore·LLM judge 같은 learned metric은 metric ID,
모델/가중치 hash, 라이선스, 실행 환경을 고정하고 비공개 한국어 사람 평가와의 방향 일치를 확인한
별도 실험에서만 추가할 수 있다. 검증 전에는 누락을 chrF2로 숨기거나 자동 승격 근거로 쓰지 않는다.

### 6.2 자동 guardrail

| guardrail | 목적 |
|---|---|
| empty target rate | 번역 누락 탐지 |
| source-copy / untranslated flag rate | 원문 통과를 성공 번역으로 가장하는 경로 탐지 |
| number·단위·고유명사 mismatch count | chrF 평균이 숨길 수 있는 치명 오류 표본화 |
| target language contract failures | 누락·undetermined·비-ko 산출물 차단 |

guardrail은 번역 품질 점수로 합산하지 않는다. 표본을 사람 검토 대상으로 올리는 신호다.

## 7. 사람 검토 — blind paired, MQM Core 축소형

milestone 비교는 같은 source/reference에 대한 baseline과 candidate를 A/B로 무작위 제시한다.
시스템 이름·버전·자동 점수는 숨기고 순서를 seed로 기록한다.

### 7.1 판정

- 전체 선호: A | B | tie | cannot_judge
- 오류 범주: accuracy/mistranslation | omission | addition | untranslated
- 보조 범주: terminology/proper_name_number | linguistic_convention | subtitle_presentation
- 심각도: critical | major | minor
- 자유 서술은 오류 span과 함께 저장하되 사용자 미디어 원문을 로그에 복제하지 않는다.

subtitle_presentation은 번역 의미 품질과 분리 보고한다. 평가자가 source 언어를 모르면
한국어 reference 기반 검토임을 표시하고 reviewer_source_language_proficiency: "none"을 기록한다.
source를 직접 평가할 수 있는 검토와 같은 집단으로 합산하지 않는다.

### 7.2 표본과 보고

- source 단위로 무작위·계층 표본을 고정하고 두 시스템에 같은 표본을 쓴다.
- 전체 A/B/tie 비율과 오류 범주·심각도 count를 함께 보고한다.
- 자동 지표와 사람 선호가 반대면 conflict로 표시하고 자동 승격을 중단한다.
- 단일 평가자의 판단을 객관적 정답처럼 표현하지 않는다. 평가자 수·가능 언어·표본 수를 기록한다.

## 8. 비교와 승격 판정

후보 비교는 source 단위 paired delta와 source-cluster bootstrap 95% CI를 사용한다.
절대 합격선 U-07, 최소 실질 효과 U-27, 최소 n·bootstrap 횟수 U-26은 임의로 채우지 않는다.

U-26·U-27이 정해지기 전 허용되는 판정:

- observed_improvement: 방향과 CI만 보고, 승격 아님
- no_clear_change: CI가 0을 포함하거나 효과가 seed 변동 안쪽
- observed_regression
- blocked_by_open_thresholds
- conflict_with_human_review

실제 promote는 다음을 모두 만족해야 한다.

1. primary metric의 사전 정의된 최소 효과와 CI 조건 충족
2. 무음·timing·format·계층별 guardrail의 허용 밖 악화 없음
3. 필요한 milestone human review가 자동 지표와 같은 방향
4. frozen-test 접근 정책과 U-07·U-26·U-27 값이 사전에 고정됨

## 9. artifact와 보안 경계

    evals/<split>/<run_id>/
    ├── manifest.json
    ├── report.partial.json
    ├── report.json
    ├── report.md
    ├── per_source.jsonl
    ├── events.jsonl
    └── human_review.jsonl

- manifest.json: 모든 fingerprint, seed, 재현성 등급, metric signature
- report.partial.json: 미완료 checkpoint·진단. top-level에 현재 run 상태 기록
- report.json: completed 실행의 기계 판독 결과. top-level `run_status: "completed"`
- report.md: 한국어 요약, source/target 블록 분리
- per_source.jsonl: source-cluster 통계에 필요한 최소 수치만
- events.jsonl: 상태 전이·오류·재개 기록, append-only
- human_review.jsonl: blind order·판정·오류 범주. 실제 미디어와 자격증명 금지

report.json은 완성 검증 후에만 생성한다. 그 전에는 report.partial.json만 존재한다.
외부 코퍼스·추출 clip·원문 transcript는 저장소·PR·CI artifact에 넣지 않는다.

## 10. 필수 계약 fixture

| ID | 상황 | 기대 판정 |
|---|---|---|
| H-01 | 정상 dual-axis, target=ko | 두 축 분리 계산, 종합 점수 없음 |
| H-02 | source reference만 존재 | source 계산, target metric unsupported |
| H-03 | target cue 있으나 language 누락/비-ko | preflight invalid |
| H-04 | hypothesis/reference axis mismatch | preflight invalid, 낮은 점수 금지 |
| H-05 | non-invertible TimeMapping | text 가능 범위만 계산, timing unsupported |
| H-06 | silence inserted span | 두 축 무음 4종에 귀속 |
| H-07 | overlap reference + single-stream hypothesis | cpWER unsupported, coverage 별도 계산 |
| H-08 | 최소 n 미만 stratum | insufficient_n, 상위 평균에 은폐 금지 |
| H-09 | dev/test source 또는 speaker 교집합 | run invalid |
| H-10 | metric 예외 발생 | run partial, 다른 metric·진단 보존 |
| H-11 | 중단 후 같은 fingerprint 재개 | 완료 shard 재사용, 중복 계산 없음 |
| H-12 | 중단 후 fingerprint 변경 | 재개 거부, 새 run_id |
| H-13 | source와 동일한 untranslated target | 성공으로 숨기지 않고 guardrail·review 표본 등록 |
| H-14 | baseline/candidate sample 집합 불일치 | paired comparison invalid |

TASK-006은 이 표의 각 행을 schema-valid example 또는 schema-invalid fixture로 표현해야 한다.
구현 단계에서는 의도적으로 잘못된 축 합산·unsupported=0·split 누출 구현이 테스트에서 실패하는지 확인한다.

## 11. TASK-006·구현 인계

TASK-006에서 최소 다음을 구체화한다.

- ReferenceBundle/v1, EvalRunManifest/v1, EvalReport/v1, event/metric status schema
- sample/source/speaker 식별자와 reference/hypothesis 대응
- metrics_by_axis.source|target과 축 없는 metric의 위치
- run/metric 상태, unsupported reason, fingerprint, partial/completed artifact
- H-01~H-14 fixture의 유효/무효 경계

코드 구현은 TASK-006 완료 뒤 Claude Code에 전달한다. 구현 프롬프트는 수정 파일, 금지 범위,
H-01~H-14, 필수 명령과 실패 시 중단 조건을 포함해야 한다.

## 12. 근거

- [chrF 원 논문](https://aclanthology.org/W15-3049/)
- [sacreBLEU 공식 구현·signature](https://github.com/mjpost/sacrebleu)
- [COMET 원 논문](https://aclanthology.org/2020.emnlp-main.213/)
- [MQM Core typology](https://www.themqm.org/mqm-pillars/typology/)
