# TASK-022 — 합성 media plumbing vertical slice

| 항목 | 값 |
|---|---|
| **ID** | TASK-022 |
| **Owner** | Lean Root Orchestrator (사람 제품 오너의 2026-08-22 직접 수행 지시) |
| **Reviewer** | 독립 리뷰 필요 — Gate H, 고정 HEAD에서 별도 세션이 검토 |
| **Phase** | Phase 1a / synthetic media plumbing 예외 slice |
| **Status** | `Done` |
| **기준 branch / SHA** | `main` / `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| **위험 등급** | **Gate H** — FFmpeg·Matroska/SubRip·로컬 staging export |

## 목표

외부 코퍼스·모델·네트워크 없이 다음 한 줄을 실제 명령으로 통과시킨다.

`LOCAL INPUT → PROBE → EXISTING/GENERATED SRT → SOFT SUB → VERIFY → LOCAL STAGING EXPORT`

이 TASK는 PR #15의 Gate S 한정 승인에 따라 착수한다. PR #12·#15의 병합이나 TASK-003 `Done`을
전제로 주장하지 않는다.

## 현재 재현 상태

- `main`은 문서 전용이며 기능 코드, dependency manifest, CI, 단일 검증 진입점이 없다.
- PR #12의 합성 recipe는 FFmpeg `6.1.1-3ubuntu5`에서 직접 재현됐지만 제품 코드로 연결되지 않았다.

## 요구 행동과 불변식

- 6초 합성 profile(`ffv1` 640×360 30 fps + mono `pcm_s16le` 48 kHz)을 입력으로 검증한다.
- 기존 SRT 또는 정확한 98-byte fixture SRT 생성 경로를 지원한다.
- video/audio는 stream copy하고 `subrip` subtitle 하나를 추가한다.
- 추출 SRT의 canonical 의미와 raw bytes를 각각 비교해 기록한다.
- 입력 SHA-256은 실행 전후 같아야 한다.
- 기존 output, export, report를 덮어쓰지 않는다.
- `MCS_ICLOUD_STAGING_DIR`가 unset/empty이면 디렉터리 생성 전 실패한다.
- 완료 파일과 `.partial-*` 파일, 성공 manifest와 failure record를 구분한다.
- 외부 네트워크를 호출하지 않는다.

## 수정 가능 범위

- `.gitignore`
- `Makefile`
- `src/media_clarity/`
- `tests/test_synthetic_slice.py`
- `scripts/smoke_task_022.py`
- `docs/SYNTHETIC_MEDIA_SLICE.md`
- 이 TASK 파일의 상태 필드

`STATUS.md`는 PR #11이 소유한 coordination point이므로 수정하지 않는다.

## 범위 밖

외부 코퍼스, downloader, ASR, 번역, QC, 모델·API·공급자, hard-sub, packaging, 실제 iCloud
API·동기화, GUI, 시각 재구성, 의존성 설치, CI, binary fixture 커밋, PR merge/close/Ready 전환.

## Given / When / Then 합격 기준

1. **Given** 유효한 합성 input과 기존/생성 SRT, 유효한 빈 staging 경로
   **When** CLI를 실행하면 **Then** soft-sub MKV, 추출 SRT, staging copy, verify JSON이 생성되고
   source/output/export hash, stream profile, canonical/raw 비교가 모두 통과한다.
2. **Given** staging 환경변수가 unset 또는 empty
   **When** 실행하면 **Then** non-zero이며 work/staging 파일시스템을 바꾸지 않는다.
3. **Given** output 또는 staging target이 이미 존재
   **When** 실행하면 **Then** 기존 바이트를 보존하고 non-zero로 멈춘다.
4. **Given** cue 역전·중첩·duration 이탈 또는 의미 변경
   **When** 검증하면 **Then** export 전에 실패하고 원인을 failure record 또는 stderr에 남긴다.
5. **Given** FFmpeg 실패
   **When** 실행하면 **Then** 성공 manifest를 만들지 않고 partial/실패 진단을 완료 산출물과
   구분하며 원본은 불변이다.

## 필수 검증

```bash
make verify
make smoke
```

`make verify`는 compile check, 표준 라이브러리 unit test, 실제 FFmpeg smoke를 포함한다.

## 완료 증거와 리뷰

- 구현 세션은 명령 출력, 실제 manifest, diff를 기록하되 자기 승인하지 않는다.
- Gate H 독립 리뷰는 고정 HEAD에서 위 네 failure path와 전체 `make verify`를 직접 실행한다.
- 실제 Windows 11/NTFS/iCloud for Windows playback·sync는 이번 승인의 증거가 아니며 후속 경계다.

## 복구

브랜치 커밋을 병합하지 않으면 `main`에는 영향이 없다. 실행 산출물은 지정한 work/staging
디렉터리에만 생성되며 기존 파일은 덮어쓰지 않는다. `.partial-*`와 `*.failure-*.json`은 실패
진단용으로 남으므로 원인 확인 후 사용자가 해당 실행 디렉터리에서만 제거한다.


## 병합 결과 (2026-08-22)

[REVIEW-013](../reviews/REVIEW-013.md)이 고정 HEAD `9dc1fee1e7ac9e1446d262963b2105ad234c1c36`를
승인했고, 사람 제품 오너가 PR #16을 일반 merge했다. `main` merge commit은
`e3a99c762ecd7030843e535db7dc3f7147bf811e`이다. Windows/NTFS·실제 iCloud sync/player 경계는
여전히 미검증이다.
