# Seed 코퍼스·라이선스·합성 fixture 조사

- **TASK:** [TASK-003](tasks/TASK-003.md)
- **조사일:** 2026-08-12
- **상태:** Source Owner 조사 완료, 독립 검토 전
- **결정 경계:** U-06·U-31·U-07은 미해결, U-22는 보류됨(Deferred) 유지

이 문서는 [EVALS §2.5~2.6](EVALS.md)가 요구한 seed 코퍼스 조사와 첫 로컬 vertical slice용
fixture 조사를 함께 기록한다. 두 용도를 섞지 않는다. 6초 합성 fixture는 컨테이너·자막·내보내기
배선을 검증하지만 ASR 품질, 다국어, 화자 다양성, 겹치는 발화를 검증하지 못한다. 반대로 대형 ASR
코퍼스는 정답 전사를 제공하지만 영상·SRT·짧은 반복 실행에는 부적합하다.

> 이 문서는 법률 자문이 아니다. 공식 라이선스와 이용약관을 프로젝트 위험 선별에 필요한 수준으로
> 대조한 기록이다. 실제 외부 자료를 받는 시점에는 해당 버전의 datasheet, archive 내부 LICENSE,
> 접근 약관을 다시 고정하고 보존해야 한다.

## 1. 결론

### 1.1 첫 vertical slice 권고

**외부 자료 없이 로컬에서 생성하는 6초 Matroska 합성 fixture를 사용한다.** 이유는 다음과 같다.

- 저작권·서비스 약관·계정·네트워크·출처 변동을 첫 배선 검증에서 제거한다.
- video + audio + SRT를 모두 갖추고 `ffprobe`, soft-sub mux, subtitle 추출, 해시 기반 export 검증이 가능하다.
- U-31을 추측하지 않는다. cue는 번역 정답이 아니라 중립적인 fixture 표식이다.
- 생성 바이너리는 저장소에 커밋하지 않고 매번 로컬에서 만든다.
- ASR·번역·모델·공급자·API·downloader를 선택하지 않는다.

이 권고는 **U-06 seed 코퍼스 최종 선택이 아니다.** U-06은 아래 외부 코퍼스 비교를 보고 사람 제품
오너가 별도로 결정한다.

### 1.2 외부 후보의 역할 분리

| 역할 | 우선 검토 후보 | 이번 판정 |
|---|---|---|
| 실제 영상 + 기존 SRT의 2차 acceptance | Sintel 공식 배포본 | **조건부 채택 후보** — 로컬 전용, CC BY 3.0 attribution 고정 후 사용 |
| 영어 ASR 기준선 | LibriSpeech | **U-06 선택 후보** — 명확한 CC BY 4.0, 영상 없음 |
| 다국어 ASR 기준선 | Multilingual LibriSpeech (MLS) | **U-06 선택 후보** — CC BY 4.0, 8개 언어, 매우 큼 |
| 한국어·광범위 언어 ASR | Common Voice 26.0 | **조건부 후보** — CC0와 별개로 MDC 재호스팅·재공유 금지 및 계정 약관 적용 |
| 겹치는 발화·회의 음성 | CHiME-6 | **제외** — 공식 배포처 간 라이선스 설명이 일치하지 않음 |

## 2. 비교 기준

[EVALS §2.5](EVALS.md)의 필수 필드에 실제 사용 행위를 더했다.

| 필드 | 확인 내용 |
|---|---|
| 이름·출처 | 원저작자 또는 공식 steward의 원문 URL |
| 언어·규모 | 언어 수, 시간·파일 크기, 짧은 반복 실행 가능성 |
| 정답 형식 | transcript, cue, speaker stream, 영상·SRT 존재 여부 |
| 라이선스 | 정확한 버전과 원문 링크 |
| 허용 행위 | 다운로드, 로컬 처리, 재배포, 저장소 포함, 파생물·자막 생성 |
| 의무 | attribution, license notice, 변경 표시, ShareAlike, 추가 금지 사항 |
| 서비스 조건 | 계정·동의·자동 접근·재호스팅·재식별 제한 |
| 비용 | 공개 다운로드 비용과 대략적 저장·전송 부담 |
| 위험 | 출처 모호성, 약관 충돌, 개인정보, 정답 품질, 규모 |

저장소 포함 가능성은 두 층으로 판정한다.

1. **라이선스상 가능성:** 저작권 라이선스가 재배포를 허용하는가.
2. **프로젝트상 가능성:** [AGENTS §8](../AGENTS.md)의 바이너리·저작권 자료 위생 규칙과 저장소
   크기 정책을 통과하는가.

라이선스가 허용해도 현재 프로젝트에는 외부 미디어 바이너리를 커밋하지 않는다.

## 3. 후보별 근거

### 3.1 완전 합성 local fixture — 첫 vertical slice 권고

| 항목 | 값 |
|---|---|
| 출처 | FFmpeg `lavfi`의 `testsrc2` + `sine`, 이 문서의 SRT 텍스트 |
| 언어 | 번역 언어 없음. cue는 `[fixture cue 1]`, `[fixture cue 2]` |
| 규모 | 6초, 640×360, 30 fps, 약 3.64 MB(검증 환경) |
| 정답 형식 | 두 cue의 UTF-8 SRT, 정확한 시작·종료 시각 |
| 외부 라이선스 | 없음. 외부 저작물을 입력으로 사용하지 않음 |
| 재배포 | 생성물을 공유하려면 향후 프로젝트/fixture 라이선스를 사람이 정해야 함. 현재는 로컬 생성·폐기 |
| 비용 | 네트워크·계정·외부 비용 없음 |
| 위험 | 실제 음성·실영상 분포를 대표하지 않음. FFmpeg build가 다르면 바이트 해시가 달라질 수 있음 |

이 fixture는 [ADR-0018](DECISIONS.md)의 재현성 구분을 따른다. 동일 build·동일 명령·동일 입력에서
이번 두 번의 실행은 T1(바이트 동일)이었지만, 다른 FFmpeg 버전·빌드까지 같은 해시를 보장하지 않는다.
버전과 명령을 기록하는 것만으로는 전체 환경에서 T1이 아니며, 일반 배포 시 주장은 T3로 제한한다.

### 3.2 Sintel — 실제 영상 + 공식 SRT의 2차 acceptance 후보

공식 [About](https://durian.blender.org/about/)은 영화 `Sintel`을 **CC BY 3.0 Unported**로
표시한다. 공식 [Download & Watch](https://durian.blender.org/download/)는 직접 영상 다운로드와
영어·스페인어·프랑스어 등 SRT, 전체 40개 subtitle 탐색 경로를 제공한다. 공식 제작 기록의 전체
길이는 **14분 48초**다.

| 항목 | 값 |
|---|---|
| 언어·트랙 | 대사가 있는 영상, 공식 다국어 SRT |
| 정답 형식 | SRT cue. ASR용 화자별 정답은 아님 |
| 라이선스 | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |
| 다운로드·로컬 처리 | 공식 direct download에서 가능 |
| 재배포·파생물·자막 | 허용. clip, remux, subtitle 수정·번역은 adaptation으로 보고 attribution·변경 표시 필요 |
| 저장소 포함 | 라이선스상 가능하나 현재 프로젝트상 금지. 로컬 cache만 허용 후보 |
| 의무 | 적절한 credit, 라이선스 링크, 파생 시 변경 표시, 추가 법적·기술적 제한 금지. 공식 페이지의 credit scroll 요구도 보존 |
| ShareAlike | 없음 |
| 비용·위험 | 무료. 전체 영화는 첫 반복 fixture로 크고, 짧은 clip은 credit scroll을 제거하므로 공개 재배포 전 별도 attribution sidecar와 전체 credit 보존 검토 필요 |

**판정:** 첫 배선 검증에는 불필요하다. 합성 fixture가 통과한 뒤, 공식 origin에서 받은 파일을
로컬에만 두고 실제 컨테이너·기존 SRT acceptance를 확인하는 2차 후보로 둔다. YouTube 사본은 쓰지 않는다.

### 3.3 LibriSpeech — 영어 ASR seed 후보

[OpenSLR SLR12](https://www.openslr.org/12)는 약 **1,000시간, 16 kHz read English speech**,
정렬된 transcript, dev/test/train archive를 제공하며 라이선스를 **CC BY 4.0**으로 표시한다.
가장 작은 공식 dev archive도 약 314~337 MB다.

| 항목 | 값 |
|---|---|
| 언어·화자 | 영어, 다화자 read speech |
| 정답 형식 | 발화 단위 audio + transcript·metadata. 영상·SRT 없음 |
| 라이선스 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| 다운로드·로컬 처리 | 가능 |
| 재배포·파생물·자막 | 허용. attribution, 라이선스 링크, 변경 표시 필요 |
| 저장소 포함 | 라이선스상 가능하나 현재 프로젝트상 금지 |
| ShareAlike | 없음 |
| 비용·위험 | 무료. 영어만, read speech 편향, 겹치는 발화·영상 없음, archive가 첫 fixture에는 큼 |

**판정:** U-06의 영어 기준선 후보다. 첫 vertical slice fixture나 다국어·overlap 단독 seed로는 부족하다.

### 3.4 Multilingual LibriSpeech — 다국어 ASR seed 후보

[OpenSLR SLR94](https://www.openslr.org/94/)는 LibriVox 기반 **8개 언어**(영어, 독일어, 네덜란드어,
스페인어, 프랑스어, 이탈리아어, 포르투갈어, 폴란드어)의 train/dev/test와 제한 지도학습용
10분·1시간·10시간 구성을 설명하고 라이선스를 **CC BY 4.0**으로 표시한다. 전체 archive는
폴란드어 6.2 GB부터 영어 2.4 TB까지 매우 크다.

| 항목 | 값 |
|---|---|
| 정답 형식 | audio + transcript. 영상·SRT·한국어 없음 |
| 허용 행위·의무 | LibriSpeech와 동일한 CC BY 4.0 범위 |
| 저장소 포함 | 라이선스상 가능하나 현재 프로젝트상 금지 |
| 비용·위험 | 데이터 자체는 무료. 전송·저장 비용 큼, read audiobook 편향, 언어 간 규모 불균형 |

**판정:** 다국어 seed 후보지만 U-31의 실제 대상 언어가 8개 언어 밖이면 직접 정답 축을 제공하지 않는다.
U-31을 추측해 미리 받지 않는다.

### 3.5 Common Voice Scripted Speech 26.0 Korean — 조건부 local-only 후보

현재 [Korean datasheet](https://mozilladatacollective.com/datasets/cmqi922c5001pnq07dmj0oypw)는
2026-06-17 release, **208.26 MB**, 7,178 clips, 10.38시간(검증 2.54시간), 210 speakers,
MP3 + TSV transcript를 기록하고 라이선스를 **CC0-1.0**으로 표시한다.

그러나 같은 datasheet는 다음을 추가로 금지한다.

- speaker identity 확인·재식별 시도
- dataset 재호스팅 또는 재공유

현재 [Mozilla Data Collective Terms](https://mozilladatacollective.com/terms)는 dataset license와
supplemental terms가 **추가적으로 함께** 적용된다고 명시한다. [공식 FAQ](https://community.mozilladatacollective.com/faq-what-are-the-main-points-of-the-mdc-terms-of-use/)
도 충돌 시 더 제한적인 조건을 따르며, 계정 종료 시 내려받은 dataset 사용 중단·삭제 의무가 생길 수
있다고 설명한다. [API 문서](https://mozilladatacollective.com/api-reference/docs)는 web UI에서 약관에
먼저 동의해야 download URL을 만들 수 있다고 명시한다.

| 행위 | 판정 |
|---|---|
| 다운로드 | 계정·dataset terms 동의 후 공식 경로에서 가능 |
| 로컬 ASR 처리 | intended use 범위에서 가능 후보. 재식별 금지 |
| 재배포·저장소 포함 | **불가** — datasheet의 재호스팅·재공유 금지 |
| 파생 subtitle 공개 | CC0만 보면 가능하지만 추가 약관의 파생·재공유 경계를 별도 확인하지 않았으므로 **공개 배포 승인 안 함** |
| attribution | CC0 자체는 요구하지 않지만 출처·release·dataset ID는 재현성을 위해 기록 |
| 비용·위험 | 금전 비용은 없을 수 있으나 계정·약관·철회·삭제·개인 음성 관리 의무가 큼 |

**판정:** 저장소 fixture로 제외한다. 향후 U-06이 Common Voice를 선택하더라도 local-only cache,
접근자 제한, dataset ID·release·동의 시점 기록, 재식별 금지, 삭제 절차가 선행되어야 한다.

### 3.6 CHiME-6 — 라이선스 출처 불일치로 제외

[OpenSLR SLR150](https://openslr.org/150/)은 CHiME-6를 **CC BY-SA 4.0**으로 표시하고
97 GB train, 11 GB dev, 12 GB eval, 2.4 MB transcription archive를 제공한다. 반면 원 프로젝트의
[CHiME-6 download 안내](https://chimechallenge.github.io/chime6/download.html)는 기반 CHiME-5 data에
별도 non-commercial/commercial license 신청이 필요하고 commercial license는 2,000 GBP라고 설명한다.

두 공식 설명만으로 OpenSLR 재배포본 전체와 원 녹음에 어떤 조건이 우선하는지 한 가지로 확정할 수
없다. CC BY-SA라면 attribution·변경 표시와 adaptation의 동일조건변경허락이 필요하지만, 별도 원자료
license가 함께 적용되면 그보다 제한될 수 있다.

**판정:** 겹치는 발화 요구에는 매력적이지만 서면 clarification 또는 archive 내부 license 대조 전에는
다운로드·가공·재배포·저장소 포함을 모두 승인하지 않는다.

## 4. 행위별 요약표

`예*`는 저작권 라이선스상 가능하지만 현재 프로젝트에는 binary를 커밋하지 않는다는 뜻이다.

| 후보 | 다운로드 | 로컬 처리 | 재배포 | 저장소 포함 | 파생물·자막 | 핵심 의무 | 판정 |
|---|---|---|---|---|---|---|---|
| 완전 합성 | 외부 다운로드 없음 | 예 | 향후 fixture license 결정 후 | 현재 아니오 | 예 | 생성 명령·도구 버전·해시 기록 | **첫 vertical slice 권고** |
| Sintel | 공식 direct에서 예 | 예 | 예 | 예* / 프로젝트상 아니오 | 예 | CC BY 3.0 attribution·license link·변경 표시·credit | **2차 local acceptance** |
| LibriSpeech | 예 | 예 | 예 | 예* / 프로젝트상 아니오 | 예 | CC BY 4.0 attribution·license link·변경 표시 | **U-06 후보** |
| MLS | 예 | 예 | 예 | 예* / 프로젝트상 아니오 | 예 | CC BY 4.0 attribution·license link·변경 표시 | **U-06 후보** |
| Common Voice 26 Korean | 약관 동의 후 예 | 조건부 예 | 아니오 | 아니오 | 공개 배포 미승인 | 재호스팅·재공유·재식별 금지, 계정 약관 | **local-only 조건부** |
| CHiME-6 | 미승인 | 미승인 | 미승인 | 아니오 | 미승인 | 공식 license 충돌 해소 필요 | **제외** |

어느 채택 후보에도 CC BY-SA가 없으므로 동일조건변경허락 의무는 없다. CHiME-6를 다시 검토할 때만
CC BY-SA 4.0의 ShareAlike와 원자료 별도 license를 함께 확인해야 한다.

## 5. 콘텐츠 라이선스와 서비스 이용약관

두 층은 다른 질문에 답한다.

| 층 | 답하는 질문 | 예 |
|---|---|---|
| 콘텐츠 라이선스 | 저작물을 복제·수정·재배포할 저작권상 허락이 있는가 | CC BY 3.0, CC BY 4.0, CC0 |
| 서비스 약관·datasheet | 그 서비스에서 어떻게 접근·다운로드·보관·공유할 수 있는가 | MDC 계정 동의·재호스팅 금지, YouTube download 제한 |

- **Sintel:** 공식 Blender origin과 CC BY 표기가 일치한다. 공식 direct download를 사용한다.
- **Common Voice:** CC0 표기만 보고 repository redistribution을 허용하면 안 된다. MDC의 현재
  supplemental terms와 Korean datasheet가 재호스팅·재공유를 금지한다.
- **YouTube:** [현재 Terms of Service](https://www.youtube.com/static?template=terms)는 서비스가
  명시적으로 허용하거나 YouTube와 권리자 허락이 있는 경우 등을 제외하고 content download·복제·수정을
  제한한다. 같은 Sintel이라도 YouTube 사본을 downloader로 받지 않고 Blender 공식 origin을 쓴다.
- **OpenSLR:** resource page의 license를 출발점으로 하되, 실제 acquisition 시 archive 내부 LICENSE와
  README, source attribution을 보존한다. CHiME-6처럼 상위 source 조건이 다르면 사용을 중단한다.

## 6. 제외 규칙

다음은 이름이 널리 쓰여도 fixture로 채택하지 않는다.

1. per-asset license, creator, 원본 URL이 없는 `sample-video` CDN·블로그 mirror
2. YouTube·SNS에서만 얻을 수 있고 서비스가 허용한 download 경로가 없는 파일
3. "free", "royalty-free", "for testing"만 있고 표준 license 원문·재배포 조건이 없는 파일
4. dataset page와 원자료 license가 충돌하는 corpus(CHiME-6 현재 상태)
5. 계정 약관이 재호스팅을 금지하는 dataset의 repository sample(Common Voice 현재 상태)
6. 개인정보·실제 사용자 미디어 또는 speaker 재식별 위험을 통제할 수 없는 자료
7. audio-only corpus를 영상·SRT 배선 fixture 하나로 가장하는 구성

## 7. 완전 합성 fixture 최소 사양

### 7.1 파일과 의미

| 파일 | 사양 | 역할 |
|---|---|---|
| `fixture-source.mkv` | 6초, Matroska, 640×360, 30 fps, yuv420p, FFV1 level 3, mono PCM s16le 48 kHz | 읽기 전용 local input |
| `fixture.srt` | UTF-8, 2 cues, 0.5~2.5초 / 3.0~5.5초 | existing/generated SRT 경로 |
| `fixture-softsub.mkv` | source video/audio stream copy + SubRip subtitle stream | soft-sub output |
| `${MCS_ICLOUD_STAGING_DIR}/fixture-softsub.mkv` | output의 byte-identical copy | local iCloud-staging export |

`MCS_ICLOUD_STAGING_DIR`는 사용자가 지정한 **로컬 디렉터리**다. 실제 iCloud 계정, sync client,
provider API를 호출하지 않는다.

SRT 내용:

```srt
1
00:00:00,500 --> 00:00:02,500
[fixture cue 1]

2
00:00:03,000 --> 00:00:05,500
[fixture cue 2]
```

이 cue는 번역 결과가 아니며 대상 언어를 정하지 않는다. subtitle language tag도 U-31이 해결되기
전에는 요구하지 않는다.

### 7.2 생성 명령

아래 명령은 **절차 검증용 recipe**이며 프로젝트의 장기 runtime·dependency 선택이 아니다.
실행 전 `ffmpeg -version`과 `ffmpeg -buildconf`를 manifest에 기록한다.

```bash
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i testsrc2=size=640x360:rate=30:duration=6 \
  -f lavfi -i sine=frequency=440:sample_rate=48000:duration=6 \
  -map 0:v:0 -map 1:a:0 -shortest \
  -c:v ffv1 -level:v 3 -pix_fmt yuv420p \
  -c:a pcm_s16le -ar 48000 -ac 1 \
  -fflags +bitexact -flags:v +bitexact -flags:a +bitexact \
  -metadata creation_time=1970-01-01T00:00:00Z \
  fixture-source.mkv
```

### 7.3 probe → soft-sub → verify → staging

```bash
ffprobe -v error -show_format -show_streams -of json \
  fixture-source.mkv > fixture-source.probe.json

ffmpeg -hide_banner -loglevel error -y \
  -i fixture-source.mkv -i fixture.srt \
  -map 0:v:0 -map 0:a:0 -map 1:0 \
  -c:v copy -c:a copy -c:s srt \
  -metadata:s:s:0 title="fixture captions" \
  -metadata creation_time=1970-01-01T00:00:00Z \
  -fflags +bitexact \
  fixture-softsub.mkv

ffprobe -v error -show_format -show_streams -of json \
  fixture-softsub.mkv > fixture-softsub.probe.json

ffmpeg -hide_banner -loglevel error -y \
  -i fixture-softsub.mkv -map 0:s:0 -c:s srt fixture-extracted.srt

diff -u fixture.srt fixture-extracted.srt
mkdir -p "${MCS_ICLOUD_STAGING_DIR}"
cp fixture-softsub.mkv "${MCS_ICLOUD_STAGING_DIR}/fixture-softsub.mkv"
sha256sum fixture-softsub.mkv \
  "${MCS_ICLOUD_STAGING_DIR}/fixture-softsub.mkv"
```

공식 [FFprobe documentation](https://ffmpeg.org/ffprobe.html)은 `-show_streams`, `-show_format`, JSON
writer와 stream specifier를 정의한다.

### 7.4 검증 환경의 실제 결과

2026-08-12에 기존 설치된 `ffmpeg 6.1.1-3ubuntu5`에서 위 사양을 두 번 실행했다.

| 항목 | 실제 결과 |
|---|---|
| source 반복 | 두 파일 SHA-256 `3bd1180d5445839baf32643e7f78be15d4818c14f1d0152e79a57377919ce37b` — byte-identical |
| soft-sub 반복 | 두 파일 SHA-256 `2f2eb1ba73813133af5c311e3329c1bd5bf445f1192451397bb83af267a623ed` — byte-identical |
| SRT | SHA-256 `c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97` |
| output 크기 | 3,636,043 bytes |
| output format | Matroska, duration 6.000 s, probe score 100 |
| streams | video `ffv1` 640×360 30 fps + audio `pcm_s16le` 48 kHz mono + subtitle `subrip` |
| cue round-trip | 추출 SRT와 입력 SRT의 diff 없음 |
| staging export | source output과 staging copy의 SHA-256 동일 |

이 해시는 **검증 환경의 증거**이지 다른 FFmpeg build의 golden hash가 아니다.

## 8. 첫 vertical slice 완료 조건

다음 조건을 모두 통과해야 한다.

| 단계 | 기계적 확인 |
|---|---|
| LOCAL INPUT | 원본 경로가 존재하고 non-empty이며 입력 SHA-256이 기록됨. 입력은 수정되지 않음 |
| PROBE | exit 0, duration 6.000 s, video 1 + audio 1, 예상 codec·크기·sample rate 확인 |
| EXISTING/GENERATED SRT | UTF-8 파싱 성공, cue 2개, 각 `[start,end)`가 duration 안에 있고 겹치지 않음 |
| SOFT SUB | 새 output 생성, video/audio는 stream copy, subtitle `subrip` 1개 포함 |
| VERIFY | output 재-probe, subtitle 추출 후 입력 SRT와 동일, 원본 SHA 불변 |
| ICLOUD-STAGING EXPORT | 로컬 staging 경로로 새 파일 복사, output과 export SHA-256 동일 |

이 slice는 downloader, ASR, 번역, QC, hard-sub, packaging, 실제 iCloud sync를 포함하지 않는다.

## 9. U-06 의사결정 카드

사람 제품 오너가 별도로 선택해야 할 질문은 다음과 같다.

| 질문 | 선택지와 현재 근거 |
|---|---|
| 첫 배선 fixture | **합성 6초 권고.** 외부 권리·네트워크 없이 지금 실행 가능 |
| 실제 미디어 2차 acceptance | Sintel local-only 사용 여부. 사용 시 attribution manifest 필요 |
| 영어 ASR seed | LibriSpeech 채택 여부. 단순한 CC BY 4.0, 영어 read speech 한계 |
| 다국어 ASR seed | MLS 또는 Common Voice. MLS는 크고 언어 제한, Common Voice는 MDC 약관상 local-only |
| 겹치는 발화 seed | 현재 채택 후보 없음. CHiME-6 license clarification 또는 다른 후보 조사 필요 |

TASK-003은 비교표와 권고를 제공할 뿐 U-06을 `해결됨`으로 바꾸지 않는다.

## 10. 미해결 유지와 다음 구현 인계

| ID | 상태 | 이 조사에서 하지 않은 것 |
|---|---|---|
| U-06 | **미해결** | seed corpus 최종 선택·다운로드 없음 |
| U-22 | **보류됨(Deferred) 유지** | ASR·번역·재구성 모델, 공급자, API, 실행 방식 선택 없음 |
| U-31 | **미해결** | 번역 대상 언어 추측 없음 |
| U-07 | **미해결** | 절대 품질 목표 수치 설정 없음 |

독립 리뷰와 사람 제품 오너의 U-06 판단 전까지 다음 허용 행동은 합성 fixture를 이용한 **코드 없는
절차 재현**뿐이다. 저장소의 현재 제안 그래프([PLAN §3-1d](../PLAN.md))를 건너뛰지 않는다.

1. 독립 리뷰가 이 조사 문서를 고정 HEAD에서 검토한다.
2. 사람 제품 오너가 비교표를 보고 U-06을 선택하고, 독립 게이트 U-31에 답한다.
3. TASK-005 평가 하네스 설계 명세와 TASK-006 `ReferenceBundle/v1` 구체화를 순서대로 완료한다.
4. 코드 착수 게이트가 열린 뒤 첫 구현 TASK는 이 합성 fixture와 위 6단계 acceptance를 사용한다.
5. 그 구현은 input overwrite를 금지하고 iCloud-staging을 로컬 directory로만 다룬다.
6. 공식 origin의 Sintel local-only acceptance는 선택적으로 추가하고, downloader, ASR, 번역, QC,
   hard-sub, packaging은 각각 후속 단계에서 연결한다.

## 11. 공식 출처 목록

모든 링크의 접근일은 2026-08-12다.

- [Sintel About / license](https://durian.blender.org/about/)
- [Sintel Download & subtitles](https://durian.blender.org/download/)
- [CC BY 3.0 deed](https://creativecommons.org/licenses/by/3.0/)
- [LibriSpeech SLR12](https://www.openslr.org/12)
- [Multilingual LibriSpeech SLR94](https://www.openslr.org/94/)
- [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/)
- [Common Voice 26.0 Korean datasheet](https://mozilladatacollective.com/datasets/cmqi922c5001pnq07dmj0oypw)
- [CC0 1.0 legal tool](https://creativecommons.org/publicdomain/zero/1.0/)
- [Mozilla Data Collective Terms](https://mozilladatacollective.com/terms)
- [Mozilla Data Collective terms FAQ](https://community.mozilladatacollective.com/faq-what-are-the-main-points-of-the-mdc-terms-of-use/)
- [Mozilla Data Collective API docs](https://mozilladatacollective.com/api-reference/docs)
- [CHiME-6 OpenSLR SLR150](https://openslr.org/150/)
- [CHiME-6 original download/license 안내](https://chimechallenge.github.io/chime6/download.html)
- [CC BY-SA 4.0 deed](https://creativecommons.org/licenses/by-sa/4.0/)
- [YouTube Terms of Service](https://www.youtube.com/static?template=terms)
- [FFprobe documentation](https://ffmpeg.org/ffprobe.html)
