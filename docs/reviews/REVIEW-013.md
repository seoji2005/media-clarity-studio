# REVIEW-013 — TASK-022 Gate H 고정 HEAD 독립 검토

## 0. 판정

**승인**

고정 HEAD `9dc1fee1e7ac9e1446d262963b2105ad234c1c36`에서 차단 0 · 중대 0 · 경미 0이다.
아래 환경 제한과 명시적 후속 경계는 이번 합성 Cloud Ubuntu slice의 계약 밖이거나 별도 실증
대상이므로 승인 자체를 막지 않는다.

## 1. 고정 좌표와 독립성

| 항목 | 확인값 |
|---|---|
| 대상 PR | #16 — Open / Draft / 미병합 |
| base | `main` @ `10d34b4a4545f9ae8894c8038e7f1cc9a7706d61` |
| head | `codex/task-022-synthetic-media-slice` @ `9dc1fee1e7ac9e1446d262963b2105ad234c1c36` |
| head tree | `b49a164cc73e679af36500213093c3a4b6833a2c` |
| 계보 | base와 merge-base 동일, 2 commits ahead / 0 behind |
| diff | 9개 파일 · +1149 / −0, TASK-022 허용 목록 안 |
| 리뷰 TASK | [TASK-023](../tasks/TASK-023.md) |
| 리뷰 브랜치 | `lean-root-review/task-023-task-022-gate-h` |

이 리뷰 세션은 PR #16의 작성 세션이 아니다. 작성자 보고나 대화는 증거로 채택하지 않았다.
`AGENTS.md` → `STATUS.md` → TASK-022 → PR 메타데이터/diff → 직접 관련 코드·문서 순서로
고정 상태를 읽었다.

## 2. 실행 환경과 코드 고정

- 격리 디렉터리: `/tmp/mcs-gateh-lpyuEp1k`
- Python: `3.12.13`
- FFmpeg/FFprobe: `6.1.1-3ubuntu5`
- GitHub에서 고정 HEAD의 변경 파일 9개를 각각 가져와 격리 디렉터리에 재구성했다.
- `git hash-object` 결과 9개가 GitHub blob SHA와 모두 일치했다:
  `9daa214`, `7aa279c`, `de5a868`, `1941401`, `7d510e2`, `f221804`,
  `791041b`, `1b46cdb`, `9205936`.

작성자 로컬 복사본은 사용하지 않았다.

## 3. 명령과 결과

### 3.1 필수 진입점

```bash
make verify
make smoke
```

둘 다 exit 0이었다. `make verify`는 compile check, unit test 8건, 실제 FFmpeg smoke를
포함해 통과했다. 별도 `make smoke`도 다음 고정 증거로 통과했다.

| 증거 | 값 |
|---|---|
| source SHA-256 | `3bd1180d5445839baf32643e7f78be15d4818c14f1d0152e79a57377919ce37b` |
| SRT SHA-256 | `c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97` |
| output/export SHA-256 | `2f2eb1ba73813133af5c311e3329c1bd5bf445f1192451397bb83af267a623ed` |
| source unchanged | true |
| canonical/raw equal | true / true |
| 기존 output/staging 보존 | true / true |
| unset guard 무변경 | true |
| raw 위반 사전 분류 | true |
| FFmpeg 실패 사전 기록 | true |

### 3.2 독립 경계 suite

```bash
PYTHONPATH=src python3 /tmp/mcs_gateh_review_tests.py
```

exit 0, 12개 그룹이 모두 PASS였다.

| 경계 | 독립 결과 |
|---|---|
| 성공 경로 | source/output/export hash, canonical/raw, manifest, 정확한 기존 SRT 경로 통과 |
| stream copy/profile | source와 output의 video/audio packet data hash 배열이 각각 동일; output은 `ffv1` + `pcm_s16le` + 단일 `subrip` |
| source 불변 | 성공·cue 실패·FFmpeg 실패·late failure 전후 SHA 동일 |
| staging guard | unset, empty, filesystem root, work와 same-dir 모두 work 생성 전 실패 |
| 기존 대상 | output, export, report regular file과 symlink target 바이트 보존 |
| broken symlink | leaf를 교체하지 않고 promotion이 실패; partial과 failure record만 남음 |
| leaf race | output/export/report 각각 경쟁 파일을 주입해 race winner 보존과 non-zero 확인 |
| cue 계약 | 역전, 중첩, 6초 duration 이탈이 export 전 실패하고 failure record 생성 |
| canonical/raw | BOM+CRLF는 canonical true/raw false로 `byte_shape_violation` 분리 기록 |
| FFmpeg partial | 가짜 FFmpeg가 partial 작성 후 exit 17; 완료 output/export/report 없음, failure record 있음 |
| late failure | export 뒤 report 전 실패 주입; complete output/extracted/export, success manifest 없음, failure record 있음 |
| source/output/export | export는 output과 byte-identical, report의 profile/hash와 실제 파일 일치 |

unit test의 의미 변경 변이(시작·끝 timestamp, cue text, index, cue 삭제)도 baseline canonical과
모두 달랐다.

## 4. no-overwrite·race 해석

`_require_new`는 정상 기존 leaf를 선행 차단하고, 실제 승격은 `os.link(partial, target)`로
no-replace를 강제한다. 그래서 선행 검사와 승격 사이에 파일이 생기는 TOCTOU leaf race에서도
기존 파일을 교체하지 않는다. broken symlink는 `Path.exists()` 선행 검사에는 잡히지 않지만
link 승격의 `EEXIST`에서 보존되며, 직접 재현으로 확인했다.

이 증거는 **leaf target 비덮어쓰기**에 대한 것이다. 적대적 프로세스가 상위 디렉터리 자체를
rename/rebind하는 다중 사용자 보안 모델까지 보증하지 않는다.

## 5. 실패 산출물 상태

| 실패 시점 | 완료 파일 | partial | failure record | success manifest |
|---|---|---|---|---|
| cue 검증 | 없음 | 없음 | 있음 | 없음 |
| FFmpeg partial 뒤 실패 | 없음 | 있음 | 있음 | 없음 |
| output/export promotion race | 앞 단계까지만 있음 | 있음 | 있음 | 없음 |
| export 뒤 report 전 실패 | output/extracted/export 있음 | 없을 수 있음 | 있음 | 없음 |
| 성공 | output/extracted/export 있음 | 없음 | 없음 | 있음 |

따라서 complete, `.partial-*`, `*.failure-*.json`, `*.verify.json`을 상태별로 구분한다.

## 6. 네트워크·의존성·scope

- 제품 Python import는 표준 라이브러리뿐이며 dependency manifest·설치 명령·CI·binary fixture가
  diff에 없다.
- 실행 subprocess는 사용자가 지정한 로컬 `ffmpeg`/`ffprobe`와 로컬 경로만 받는다. URL,
  downloader, socket/HTTP client, `curl`/`wget` 호출이 없다.
- 시스템 FFmpeg/FFprobe는 문서에 필수 도구로 명시되어 있으며 Python package 의존성은 없다.
- 변경 파일 9개는 TASK-022 수정 가능 범위와 정확히 일치한다. `STATUS.md`와 PR #11 소유
  coordination point는 변경하지 않았다.
- downloader, ASR, 번역, QC, 모델·API·공급자, hard-sub, packaging, GUI, 시각 재구성,
  실제 iCloud API/sync를 구현하거나 주장하지 않았다.

## 7. 증거 확대 주장 검토

`docs/SYNTHETIC_MEDIA_SLICE.md`와 PR #16 본문은 자동 검증을 Cloud Ubuntu +
FFmpeg `6.1.1-3ubuntu5`로 한정하고, Windows 11/NTFS, iCloud for Windows 동기화,
실제 player 재생을 명시적으로 미검증으로 남긴다. Cloud 증거를 다른 환경의 증거로 과장하지 않았다.

## 8. 환경 제한과 남은 미검증 경계

### 환경 제한 — 제품 결함 아님

`strace -f -e trace=network make verify`를 시도했으나 sandbox가
`PTRACE_TRACEME: Operation not permitted`로 거부했다. 따라서 runtime network syscall
trace는 확인하지 못했다. 이는 `make verify` 실패가 아니며, 별도 실행한 `make verify`와
`make smoke`는 통과했다. 네트워크 비사용 판정은 고정 코드의 import·명령·인수 정적 검사에
근거한다.

### 남은 미검증

- Windows 11/NTFS의 `os.link` no-replace 동작과 경로 의미
- 실제 iCloud for Windows sync 및 player playback
- FFmpeg/FFprobe `6.1.1-3ubuntu5` 이외 버전·다른 OS
- 적대적 상위 디렉터리 rename/rebind race
- 전원 상실 시 디렉터리 entry 내구성
- arbitrary local media, 외부 코퍼스, Gate E와 TASK-003/PR #12/#15 처분

이 항목은 이번 고정 6초 합성 profile의 승인 증거로 주장하지 않는다.

## 9. 최종 판정

**승인.** TASK-022의 Gate H 합격 기준을 고정 HEAD에서 독립 재현했고, 병합을 막는 결함을
찾지 못했다. 이 판정은 병합·Ready 전환·TASK-022 `Done`이 아니며 사람 제품 오너의 최종
판단을 대신하지 않는다.
