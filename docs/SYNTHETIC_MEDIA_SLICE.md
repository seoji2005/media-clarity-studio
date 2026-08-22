# 합성 media plumbing vertical slice

외부 코퍼스·모델·네트워크 없이 Gate S의 첫 배선을 실행하는 임시 CLI다. 일반 영상 처리기가
아니며 6초 합성 profile만 의도적으로 허용한다.

## 검증

필수 도구는 Python 3.12+, FFmpeg/FFprobe다. Python package 의존성은 없다.

```bash
make verify
```

## 직접 실행

먼저 PR #12 `docs/SEED_CORPUS_RESEARCH.md` §7.2의 명령으로 `fixture-source.mkv`를 만든다.

```bash
export PYTHONPATH=src
export MCS_ICLOUD_STAGING_DIR=/absolute/local/staging
python3 -m media_clarity \
  --input /absolute/path/fixture-source.mkv \
  --generate-fixture-srt \
  --work-dir /absolute/local/work
```

기존 SRT는 `--generate-fixture-srt` 대신 `--srt /absolute/path/input.srt`를 쓴다.

성공하면 work 디렉터리에 soft-sub MKV, 추출 SRT, verify JSON이 생기고 staging 디렉터리에
byte-identical MKV가 생긴다. 기존 대상은 덮어쓰지 않는다. 실패 뒤의 `.partial-*`와
`*.failure-*.json`은 완료 산출물이 아니다.

`MCS_ICLOUD_STAGING_DIR`는 실제 iCloud API가 아니라 사용자가 지정한 로컬 디렉터리다. unset/empty
또는 filesystem root면 어떤 work/staging 디렉터리도 만들기 전에 실패한다.

## 현재 검증 경계

- Cloud Ubuntu + FFmpeg `6.1.1-3ubuntu5`에서만 자동 검증했다.
- Windows 11/NTFS, iCloud for Windows 동기화, 실제 player 재생은 아직 검증하지 않았다.
- downloader, ASR, 번역, QC, hard-sub, packaging, GUI는 포함하지 않는다.
