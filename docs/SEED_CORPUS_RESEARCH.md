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
| 겹치는 발화·회의 음성 | CHiME-6 | **첫 fixture 제외** (공학적 근거 §3.6.4) / **seed 후보로는 유지** — 라이선스 1차 확인이 blocker (§3.6.2) |

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
| 의무 | **CC BY 3.0의 법적 의무:** 적절한 credit, 라이선스 링크, 파생 시 변경 표시, 추가 법적·기술적 제한 금지. **별도 — credit scroll:** 공식 배포자 Blender Durian의 공유 안내 페이지([sharing](https://durian.blender.org/sharing/))가 영화를 자유롭게 공유·상영하는 조건으로 **영화 자체의 credit scroll 포함**을 요청한다 (§3.2.1) |
| ShareAlike | 없음 |
| 비용·위험 | 무료. 전체 영화는 첫 반복 fixture로 크고, 짧은 clip은 credit scroll을 제거하므로 공개 재배포 전 별도 attribution sidecar와 전체 credit 보존 검토 필요 |

#### 3.2.1 credit scroll — 법적 의무와 배포자 요청의 구분

| 구분 | 내용 | 성격 |
|---|---|---|
| **CC BY 3.0** | attribution, 라이선스 링크, 변경 표시, 추가 제한 금지 | **법적 의무.** 라이선스 원문에서 나온다 |
| **credit scroll 포함** | 공식 배포자 Blender Durian의 [sharing 안내](https://durian.blender.org/sharing/)가 영화를 자유롭게 공유·상영하는 조건으로 영화의 credit scroll을 함께 포함할 것을 밝힌다 | **배포자가 게시한 공유 조건.** CC BY 3.0 본문에는 이 문구가 없다 |

> **이 문서는 credit scroll 요구를 "CC BY 3.0이 부과하는 법적 의무"로 격상하지 않는다.**
> 공식 배포자가 게시한 조건이며, 실무적으로는 attribution을 충족하는 가장 안전한 형태다.
> 짧은 clip은 credit scroll을 제거하므로, **clip 사용 시 별도 attribution sidecar로 credit을
> 보존**하고 공개 재배포 전에 이 조건을 다시 확인한다.
>
> **확인 한계 (2026-08-12):** `durian.blender.org`는 이 작업 환경의 egress proxy가 차단해
> (`403 CONNECT tunnel failed`) **1차 페이지를 직접 열지 못했다.** 위 URL은 REVIEW-010 M-05가
> 지목한 페이지이며, 문구의 정확한 표현과 현재 게시 여부는 **1차 확인이 가능한 환경에서
> 재확인해야 한다** (§11 주석).

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

### 3.6 CHiME-6 — 첫 fixture에서 제외, seed 후보로는 열어 둠

**이전 판은 "라이선스 출처 불일치"만을 제외 근거로 삼았다. REVIEW-010 M-03은 그 근거가 불완전하고
제품 오너의 선택지를 실제보다 좁힌다고 지적했다.** 아래는 네 층을 분리해 다시 기록한 것이다.

#### 3.6.1 출처별 게시 주체·적용 대상·날짜

| # | 출처 | 게시 주체 | 적용 대상 | 날짜 | 현재 효력 |
|---|---|---|---|---|---|
| S1 | [OpenSLR SLR150](https://openslr.org/150/) | OpenSLR (재배포처) | OpenSLR이 배포하는 CHiME-6 archive | 상시 게시 | **CC BY-SA 4.0** 표기 |
| S2 | [CHiME-6 challenge download 안내](https://chimechallenge.github.io/chime6/download.html) | 당시 CHiME-6 challenge 조직 | **당시 challenge 참가자의 CHiME-5 원자료 접근 절차** | CHiME-6 challenge 기간 (2020년경) | **역사적 안내.** 갱신 여부 미확인 |
| S3 | [현행 CHiME steward — CHiME-5 dataset](https://www.chimechallenge.org/datasets/chime5) | 현행 CHiME steward | CHiME-5 dataset 라이선스 | **2024-01-01 재발행 고지** | **1차 확인 실패 (§11 주석 참조)** |

**S2의 2,000 GBP는 저작권 라이선스가 아니라 당시 challenge의 원자료 접근·배포 조건이다.**
두 층을 같은 규칙처럼 나란히 두면 "현행 라이선스 충돌"처럼 읽히지만, 실제로는 **시점이 다른 두
문서**다. 이전 판이 그렇게 읽히도록 쓴 것은 정확하지 않았다.

#### 3.6.2 확인하지 못한 것 — blocker

**S1·S2·S3의 1차 페이지를 이 작업 환경에서 직접 열지 못했다.** `openslr.org`, `www.openslr.org`,
`chimechallenge.github.io`, `www.chimechallenge.org`는 egress proxy가 차단해 `403 CONNECT tunnel
failed`로 응답했다 (확인일 2026-08-12). 웹 검색은 S3에 "As of 1st Jan 2024, the CHiME-5 dataset has
been re-issued under a standard CC BY-SA 4.0 license, and is free for both academic and commercial
purposes"라는 문장이 있다고 노출했으나, **검색 스니펫은 1차 확인이 아니므로 이 문서는 그것을
확정된 사실로 기록하지 않는다.**

> **이 항목은 blocker다.** 재발행 고지의 존재·일자·적용 범위는 **1차 페이지를 직접 열 수 있는
> 환경에서 재확인해야 한다.** 그때까지 이 문서는 CHiME-6의 **법적 결론을 내리지 않는다** (R5).
> 아래 3.6.3~3.6.4의 판단은 라이선스 결론에 의존하지 않는 부분만 담는다.

#### 3.6.3 네 가지를 분리한 현재 판단

| 층 | 현재 상태 |
|---|---|
| **현재 라이선스상 사용 가능성** | **미확정 — 확인 필요.** S1은 CC BY-SA 4.0을 표기하고, S3에 2024-01-01 재발행 고지가 있다는 정황이 있다. 사실이면 학술·상업 모두 자유로우며 S2의 2,000 GBP는 과거 조건이 된다. **1차 확인 전에는 어느 쪽도 단정하지 않는다** |
| **저장소 재배포 시 의무** | CC BY-SA 4.0이 확정되면 **attribution·라이선스 링크·변경 표시에 더해 adaptation의 동일조건변경허락(ShareAlike)** 이 따른다. 이는 현재 채택 후보 중 **유일한 ShareAlike**이므로 파생 자막·가공물의 배포 조건을 별도 검토해야 한다 |
| **seed 코퍼스 후보로서의 가치** | **높음. 제외하지 않는다.** 겹치는 발화·원거리 마이크 정답을 화자별로 제공하는 후보가 현재 목록에 이것뿐이다 ([`EVALS.md`](EVALS.md) §2.6의 화자별 분리 요구, cpWER 전제). U-06 선택지에서 빼지 않는다 |
| **첫 vertical-slice fixture로서의 적합성** | **부적합 — 라이선스와 무관하게 확정.** 근거는 3.6.4 |

#### 3.6.4 첫 fixture 부적합 — 라이선스에 의존하지 않는 공학적 근거

아래는 **S1이 게시한 archive 구성만으로 판단**할 수 있으며 라이선스 결론을 기다리지 않는다.

| # | 근거 | 첫 slice 요구와의 충돌 |
|---|---|---|
| E1 | archive가 **97 GB train / 11 GB dev / 12 GB eval** | 첫 slice는 **6초 · 약 3.6 MB** fixture로 배선을 확인한다. 4자리 배수의 다운로드·저장이 배선 검증에 아무 정보를 더하지 않는다 |
| E2 | **영상 트랙이 없다** — dinner party 음성 녹음 corpus | slice의 `SOFT SUB`·`PROBE` 단계는 **video + audio 컨테이너**를 요구한다. 영상이 없으면 remux 경로 자체를 검증할 수 없다 |
| E3 | **배포 자막이 SRT가 아니다** — transcription archive(2.4 MB)는 challenge 전사 형식 | `EXISTING SRT` 분기는 SRT cue 입력을 전제한다. 변환 계층이 먼저 필요하므로 "기존 SRT" 경로 검증이 아니다 |
| E4 | **다중 화자·원거리 음성 중심 구성** | 첫 slice는 ASR 품질을 재지 않는다. 가장 어려운 음향 조건을 배선 검증에 넣으면 실패 원인이 배선인지 음향인지 분리되지 않는다 |
| E5 | **결정적(deterministic) fixture가 아니다** | §7의 합성 fixture는 동일 build에서 byte-identical 재생성이 가능하다(T1 관측). 실제 녹음은 그 성질이 없어 acceptance 기준을 해시로 고정할 수 없다 |

**판정:** **첫 vertical slice fixture에서는 제외한다** — 근거는 E1~E5이며 라이선스가 어떻게
확정되든 바뀌지 않는다. **동시에 seed 코퍼스 후보로는 유지한다** — 겹치는 발화 seed로서의 가치가
크고, 라이선스는 3.6.2의 1차 확인으로 해소될 수 있는 성격이다. 다운로드·가공·재배포·저장소 포함은
3.6.2가 해소되기 전까지 승인하지 않는다.

## 4. 행위별 요약표

`예*`는 저작권 라이선스상 가능하지만 현재 프로젝트에는 binary를 커밋하지 않는다는 뜻이다.

| 후보 | 다운로드 | 로컬 처리 | 재배포 | 저장소 포함 | 파생물·자막 | 핵심 의무 | 판정 |
|---|---|---|---|---|---|---|---|
| 완전 합성 | 외부 다운로드 없음 | 예 | 향후 fixture license 결정 후 | 현재 아니오 | 예 | 생성 명령·도구 버전·해시 기록 | **첫 vertical slice 권고** |
| Sintel | 공식 direct에서 예 | 예 | 예 | 예* / 프로젝트상 아니오 | 예 | CC BY 3.0 attribution·license link·변경 표시·credit | **2차 local acceptance** |
| LibriSpeech | 예 | 예 | 예 | 예* / 프로젝트상 아니오 | 예 | CC BY 4.0 attribution·license link·변경 표시 | **U-06 후보** |
| MLS | 예 | 예 | 예 | 예* / 프로젝트상 아니오 | 예 | CC BY 4.0 attribution·license link·변경 표시 | **U-06 후보** |
| Common Voice 26 Korean | 약관 동의 후 예 | 조건부 예 | 아니오 | 아니오 | 공개 배포 미승인 | 재호스팅·재공유·재식별 금지, 계정 약관 | **local-only 조건부** |
| CHiME-6 | 보류 | 보류 | 보류 | 아니오 | 보류 | S1은 CC BY-SA 4.0 표기. 확정 시 attribution·변경 표시 + **ShareAlike**. 1차 확인 blocker (§3.6.2) | **첫 fixture 제외 (§3.6.4) / seed 후보 유지** |

**"보류"는 "금지"가 아니라 "1차 확인 전 미승인"이다** (§3.6.2). 어느 **현재 채택 후보**에도
CC BY-SA가 없으므로 지금 시점에 동일조건변경허락 의무는 없다. CHiME-6를 채택하면 그때
CC BY-SA 4.0의 ShareAlike와 원자료 조건을 함께 확인해야 한다.

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
  README, source attribution을 보존한다. 재배포처 표기와 상위 source 조건이 다르게 보이면
  **어느 쪽이 현행인지 1차 확인 전까지** 사용을 중단한다 (CHiME-6의 현재 상태 — §3.6.1).

## 6. 제외 규칙

다음은 이름이 널리 쓰여도 fixture로 채택하지 않는다.

1. per-asset license, creator, 원본 URL이 없는 `sample-video` CDN·블로그 mirror
2. YouTube·SNS에서만 얻을 수 있고 서비스가 허용한 download 경로가 없는 파일
3. "free", "royalty-free", "for testing"만 있고 표준 license 원문·재배포 조건이 없는 파일
4. 재배포처 표기와 원자료 조건 중 **어느 것이 현행인지 1차 출처로 확인되지 않은** corpus
   (CHiME-6의 현재 상태 — 확인 전 미승인이며, 확인되면 이 항목에서 벗어난다)
5. 계정 약관이 재호스팅을 금지하는 dataset의 repository sample(Common Voice 현재 상태)
6. 개인정보·실제 사용자 미디어 또는 speaker 재식별 위험을 통제할 수 없는 자료
7. audio-only corpus를 영상·SRT 배선 fixture 하나로 가장하는 구성

## 7. 완전 합성 fixture 최소 사양

### 7.1 파일과 의미

| 파일 | 사양 | 역할 |
|---|---|---|
| `fixture-source.mkv` | 6초, Matroska, 640×360, 30 fps, yuv420p, FFV1 level 3, mono PCM s16le 48 kHz | 읽기 전용 local input |
| `fixture.srt` | UTF-8(BOM 없음), LF, 2 cues, 0.5~2.5초 / 3.0~5.5초, EOF = `0a 0a` (§7.1.1) | existing/generated SRT 경로 |
| `fixture-softsub.mkv` | source video/audio stream copy + SubRip subtitle stream | soft-sub output |
| `${MCS_ICLOUD_STAGING_DIR}/fixture-softsub.mkv` | output의 byte-identical copy | local iCloud-staging export |

`MCS_ICLOUD_STAGING_DIR`는 사용자가 지정한 **로컬 디렉터리**다. 실제 iCloud 계정, sync client,
provider API를 호출하지 않는다. 값이 없으면 절차가 **시작 전에 중단**된다 (§7.3).

SRT 내용 (**표시용** — 바이트는 §7.1.1이 고정한다):

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

#### 7.1.1 `fixture.srt`의 바이트 규약 — 위 블록을 눈으로 옮기지 말 것

**위 fenced block은 마지막 cue 뒤의 빈 줄을 표현하지 못한다.** 그 블록을 시각적으로 옮겨 적으면
§7.4의 SRT SHA-256이 재현되지 않는다 (REVIEW-010 M-01). 따라서 바이트는 **문서가 아니라 명령이**
고정한다.

| 항목 | 규약 |
|---|---|
| 인코딩 | **UTF-8, BOM 없음** (선두 `EF BB BF` 금지) |
| 줄바꿈 | **LF(`0a`)만.** CR(`0d`)을 포함하지 않는다 |
| 줄 끝 공백 | **trailing space·tab 없음** |
| 파일 끝 | **정확히 `0a 0a`** — 마지막 cue 텍스트 줄의 LF + 빈 줄 1개 |
| 총 바이트 | **98 bytes** |

이 규약은 임의 선택이 아니다. FFmpeg의 SubRip muxer가 **마지막 cue 뒤에 빈 줄을 붙여 출력**하므로,
입력을 같은 형태로 고정해야 §7.3의 raw 바이트 비교가 성립한다 (§7.4.1).

**생성 명령 — 복사 실행하면 위 규약이 그대로 나온다.** 마지막 인자 `''`가 EOF의 빈 줄을 만든다.

```bash
LC_ALL=C printf '%s\n' \
  '1' \
  '00:00:00,500 --> 00:00:02,500' \
  '[fixture cue 1]' \
  '' \
  '2' \
  '00:00:03,000 --> 00:00:05,500' \
  '[fixture cue 2]' \
  '' > fixture.srt
```

`printf`는 각 인자 뒤에 `\n` 하나씩만 붙이므로 결과 바이트가 인자 목록으로 완전히 결정된다.
here-doc은 편집기·들여쓰기·`<<-` 탭 처리에 따라 결과가 달라질 수 있어 쓰지 않는다.
`LC_ALL=C`는 이 절과 §7.3의 모든 명령에 적용한다 — 정렬·문자 분류·오류 메시지가 locale에
의존하지 않게 한다.

**생성 직후 확인** (규약 위반을 즉시 드러낸다):

```bash
LC_ALL=C sha256sum fixture.srt
wc -c < fixture.srt                      # 96
tail -c 2 fixture.srt | od -An -tx1      # 0a 0a
grep -c $'\r' fixture.srt || true        # 0  (CR 없음)
grep -nP '[ \t]+$' fixture.srt || true   # 출력 없음 (trailing space 없음)
head -c 3 fixture.srt | od -An -tx1      # 31 0a 30  (BOM `ef bb bf` 아님)
```

### 7.2 생성 명령

아래 명령은 **절차 검증용 recipe**이며 프로젝트의 장기 runtime·dependency 선택이 아니다.
실행 전 `ffmpeg -version`과 `ffmpeg -buildconf`를 manifest에 기록한다.

**실행 조건을 먼저 고정한다.** §7.2·§7.3의 모든 블록은 `LC_ALL=C`와 깨끗한 작업 디렉터리를
전제로 한다.

```bash
export LC_ALL=C
```

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
```

**VERIFY는 두 비교를 모두 수행하고 결과를 따로 기록한다** (§7.3.1). 하나만 통과해도 통과로 적지
않는다.

```bash
# (1) raw 바이트 비교 — §7.1.1 규약을 지킨 입력에서만 성립한다
diff -u fixture.srt fixture-extracted.srt && echo "RAW: identical"

# (2) canonical 비교 — 바이트 형태 차이에 견고하다
LC_ALL=C ./srt-canon.sh fixture.srt           > fixture.canon
LC_ALL=C ./srt-canon.sh fixture-extracted.srt > fixture-extracted.canon
diff -u fixture.canon fixture-extracted.canon && echo "CANONICAL: identical"
```

staging export는 **환경변수를 먼저 검증**한다. 값이 없거나 비어 있으면 파일시스템을 건드리기 전에
중단한다 (REVIEW-010 M-02).

```bash
: "${MCS_ICLOUD_STAGING_DIR:?set MCS_ICLOUD_STAGING_DIR to the staging directory}"
mkdir -p -- "$MCS_ICLOUD_STAGING_DIR"
cp -- fixture-softsub.mkv "$MCS_ICLOUD_STAGING_DIR/"
sha256sum fixture-softsub.mkv "$MCS_ICLOUD_STAGING_DIR/fixture-softsub.mkv"
```

`:?`는 미설정과 **빈 문자열을 모두** 오류로 처리한다. `--`는 값이 `-`로 시작해도 옵션으로 해석되지
않게 한다. 이 가드가 없으면 `mkdir -p ""`가 실패한 뒤 `cp`의 목적지가 `/fixture-softsub.mkv`로
해석될 수 있다.

공식 [FFprobe documentation](https://ffmpeg.org/ffprobe.html)은 `-show_streams`, `-show_format`, JSON
writer와 stream specifier를 정의한다.

#### 7.3.1 `srt-canon.sh` — canonicalization이 허용하는 차이

raw 비교는 **바이트가 같은가**를, canonical 비교는 **cue가 같은가**를 묻는다. 둘은 서로를 대체하지
않는다.

```bash
cat > srt-canon.sh <<'CANON'
#!/bin/sh
# SRT canonicalization — 아래 5종 차이만 제거하고 나머지는 전부 남긴다.
LC_ALL=C sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' -e 's/[ \t][ \t]*$//' -- "$1" |
LC_ALL=C awk '
  function flush(){ if(idx!=""){ printf "CUE\t%s\t%s\t%s\n", idx, tc, text } idx="";tc="";text="";state=0 }
  { if($0==""){ flush(); next }
    if(state==0){ idx=$0; state=1; next }
    if(state==1){ tc=$0;  state=2; next }
    text=(text==""?$0:text "\\n" $0) }
  END{ flush() }'
CANON
chmod +x srt-canon.sh
```

출력은 cue 하나당 한 줄인 `CUE<TAB>번호<TAB>시각줄<TAB>텍스트`다. 예:

```
CUE	1	00:00:00,500 --> 00:00:02,500	[fixture cue 1]
CUE	2	00:00:03,000 --> 00:00:05,500	[fixture cue 2]
```

| canonicalization이 **허용**(무시)하는 차이 | canonicalization이 **숨기지 않는** 차이 |
|---|---|
| UTF-8 BOM의 유무 | **cue 번호** |
| CRLF ↔ LF 줄바꿈 | **시작 시각** |
| 줄 끝 trailing space·tab | **종료 시각** |
| 파일 앞뒤의 빈 줄 개수 (EOF `0a` ↔ `0a 0a` 포함) | **cue 텍스트** (여러 줄은 `\n`으로 결합해 보존) |
| cue 사이 빈 줄의 **개수** | **cue의 추가·누락·순서** |

> **허용 목록에 없는 차이는 전부 diff로 드러난다.** 이 5종은 SubRip 직렬화가 의미를 보존한 채
> 바꿀 수 있는 표현 차이이고, 오른쪽 항목은 자막의 내용 자체이므로 정규화하지 않는다.
> §7.4.1의 음성 테스트 5건이 이 경계를 실측으로 확인한다.

### 7.4 검증 환경의 실제 결과

2026-08-12에 `ffmpeg 6.1.1-3ubuntu5`(dpkg `7:6.1.1-3ubuntu5`)에서 위 사양을 두 번 실행했다.
**REVIEW-010 반영 후 §7.1.1의 명령으로 깨끗한 임시 디렉터리에서 문자 그대로 재실행해 재측정한
값이다.**

| 항목 | 실제 결과 |
|---|---|
| source 반복 | 두 파일 SHA-256 `3bd1180d5445839baf32643e7f78be15d4818c14f1d0152e79a57377919ce37b` — byte-identical |
| soft-sub 반복 | 두 파일 SHA-256 `2f2eb1ba73813133af5c311e3329c1bd5bf445f1192451397bb83af267a623ed` — byte-identical |
| SRT 반복 | 두 파일 SHA-256 `c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97` — byte-identical. **§7.1.1 규약(98 bytes, EOF `0a 0a`)에 대응** |
| source 크기 | 3,635,787 bytes |
| output 크기 | 3,636,043 bytes |
| output format | Matroska, duration 6.000 s, probe score 100 |
| streams | video `ffv1` 640×360 30 fps + audio `pcm_s16le` 48 kHz mono + subtitle `subrip` |
| **cue round-trip (raw)** | 추출 SRT가 입력 SRT와 **byte-identical** — 추출본 SHA-256도 `c2ed5960…`. **§7.1.1 규약을 지킨 입력에서만 성립** (아래 주의) |
| **cue round-trip (canonical)** | `srt-canon.sh` 출력이 **동일**. cue 번호·시작/종료 시각·텍스트 2건 일치 |
| staging export | source output과 staging copy의 SHA-256 동일 |

이 해시는 **검증 환경의 증거**이지 다른 FFmpeg build의 golden hash가 아니다.

#### 7.4.1 raw 비교가 성립하는 이유와 그 한계

**raw 성공을 일반 사실로 읽으면 안 된다.** FFmpeg의 SubRip 출력은 마지막 cue 뒤에 **항상 빈 줄을
붙인다**. 즉 추출본의 EOF는 언제나 `0a 0a`다.

| 입력 `fixture.srt`의 EOF | 추출본 EOF | raw `diff` | canonical `diff` |
|---|---|---|---|
| **`0a 0a`** (§7.1.1 규약) | `0a 0a` | **통과** | 통과 |
| `0a` (fenced block을 눈으로 옮긴 경우) | `0a 0a` | **실패** — 후행 빈 줄 1개 차이 | 통과 |

따라서 raw 비교의 통과는 **추출이 아무것도 정규화하지 않는다는 증거가 아니라**, 입력을 추출이
내보내는 형태와 같게 고정했기 때문에 얻어진 결과다. 이 사실을 숨기지 않기 위해 §7.3은 두 비교를
모두 수행하고 §8은 두 결과를 각각 요구한다.

**바이트 형태 대조 (실측, 같은 환경·같은 명령):**

| 형태 | SHA-256 | §7.1.1 규약 |
|---|---|---|
| EOF `0a` (빈 줄 없음) | `9df382a65875ccfb1e055b219219d5eb3864751f79896b049f54952cb636c4d6` | 위반 |
| **EOF `0a 0a`** | **`c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97`** | **준수** |

`9df382a6…`는 REVIEW-010 §2.2가 재현한 값이며, 문서를 눈으로 옮겼을 때 나오는 형태다. 두 형태는
**soft-sub `.mkv` 해시가 서로 같다**(`2f2eb1ba…`) — mux 시 자막 payload가 정규화되기 때문이며,
결함이 `.srt` 파일과 그것을 직접 비교하는 VERIFY 단계에 한정된다는 뜻이다.

**canonicalization 경계 음성 테스트 (실측 5건).** 아래 변경은 **전부 canonical `diff`에서 검출**됐다
— 정규화가 cue 내용이나 timestamp 차이를 숨기지 않음을 확인한다.

| 변경 | canonical 비교 |
|---|---|
| 시작 시각 `00:00:00,500` → `00:00:00,600` | **검출** |
| 종료 시각 `00:00:05,500` → `00:00:05,400` | **검출** |
| cue 텍스트 `[fixture cue 2]` → `[fixture cue X]` | **검출** |
| cue 번호 `2` → `3` | **검출** |
| cue 1건 삭제 | **검출** |

반대로 BOM 추가·CRLF 변환·trailing space 추가·EOF 빈 줄 제거 4종은 canonical에서 **동일**로
판정됐다 (§7.3.1 허용 목록과 일치).

### 7.5 REVIEW-010 반영 후 재실행 기록 (2026-08-12)

수정된 §7.1.1·§7.2·§7.3의 명령을 **깨끗한 임시 디렉터리에서 문자 그대로** 실행했다.
도구는 `ffmpeg`/`ffprobe` **6.1.1-3ubuntu5** (dpkg `7:6.1.1-3ubuntu5`), `LC_ALL=C`,
GNU coreutils `sha256sum`·`printf`·`od`·`wc`, GNU `sed`·`awk`·`diff`.

| 검사 | 결과 |
|---|---|
| §7.1.1 `printf` 산출물 | SHA-256 `c2ed5960…`, 98 bytes, EOF `0a 0a`, CR 0개, trailing space 0개, BOM 없음 — **규약 전항 충족** |
| source 2회 생성 | 두 실행 모두 `3bd1180d…`, 3,635,787 bytes — **byte-identical** |
| SRT 2회 생성 | 두 실행 모두 `c2ed5960…` — **byte-identical** |
| soft-sub 2회 생성 | 두 실행 모두 `2f2eb1ba…`, 3,636,043 bytes — **byte-identical** |
| 추출 SRT | `c2ed5960…` — 입력과 동일 해시 |
| **raw 비교** | `diff -u` **통과** (§7.4.1의 성립 조건에서) |
| **canonical 비교** | `srt-canon.sh` 출력 **동일**, cue 2건의 번호·시작·종료·텍스트 일치 |
| canonicalization 음성 테스트 | 시각·텍스트·번호·누락 **5건 전부 검출** (§7.4.1) |
| staging 가드 — 미설정 | 오류 메시지 + **exit 2**, `/fixture-softsub.mkv` **미생성** |
| staging 가드 — 빈 문자열 | 오류 메시지 + **exit 2**, `/fixture-softsub.mkv` **미생성** |
| staging 가드 — 유효 경로 | **exit 0**, output과 staging copy SHA-256 `2f2eb1ba…` **동일** |

**환경 제약:** 이 실행 환경에는 `ffmpeg`이 사전 설치되어 있지 않아 `apt-get`으로 설치했고,
설치된 build가 문서 고정값과 **동일**했다. 라이선스 1차 출처 확인은 egress 차단으로 수행하지
못했다 (§3.2.1, §3.6.2, §11).

## 8. 첫 vertical slice 완료 조건

다음 조건을 모두 통과해야 한다.

| 단계 | 기계적 확인 |
|---|---|
| LOCAL INPUT | 원본 경로가 존재하고 non-empty이며 입력 SHA-256이 기록됨. 입력은 수정되지 않음 |
| PROBE | exit 0, duration 6.000 s, video 1 + audio 1, 예상 codec·크기·sample rate 확인 |
| EXISTING/GENERATED SRT | UTF-8 파싱 성공, cue 2개, 각 `[start,end)`가 duration 안에 있고 겹치지 않음. **생성 경로는 §7.1.1 규약을 만족** — BOM 없음, LF, trailing space 없음, EOF `0a 0a` |
| SOFT SUB | 새 output 생성, video/audio는 stream copy, subtitle `subrip` 1개 포함 |
| **VERIFY (a) canonical** | output 재-probe 후 subtitle 추출. `srt-canon.sh`를 통과시킨 입력과 추출본의 **cue 번호·시작 시각·종료 시각·텍스트가 전부 일치**. 원본 SHA 불변. **이것이 필수 기준이다** |
| **VERIFY (b) raw** | 입력과 추출본의 **바이트 동일**. §7.1.1 규약을 지킨 입력에서만 성립하며, 실패 시 (a)가 통과했다면 **바이트 형태 위반으로 분류**하고 cue 불일치와 구분해 보고한다 (§7.4.1) |
| ICLOUD-STAGING EXPORT | `MCS_ICLOUD_STAGING_DIR` **가드 통과**(미설정·빈 값이면 파일시스템 변경 없이 non-zero 종료), 로컬 staging 경로로 새 파일 복사, output과 export SHA-256 동일 |

> **(a)와 (b)를 하나로 합치지 않는다.** (b)만 보면 표현 차이를 내용 오류로 오판하고,
> (a)만 보면 바이트 규약 이탈을 놓친다. 둘의 결과를 각각 기록한다.

이 slice는 downloader, ASR, 번역, QC, hard-sub, packaging, 실제 iCloud sync를 포함하지 않는다.

## 9. U-06 의사결정 카드

사람 제품 오너가 별도로 선택해야 할 질문은 다음과 같다.

| 질문 | 선택지와 현재 근거 |
|---|---|
| 첫 배선 fixture | **합성 6초 권고.** 외부 권리·네트워크 없이 지금 실행 가능 |
| 실제 미디어 2차 acceptance | Sintel local-only 사용 여부. 사용 시 attribution manifest 필요 |
| 영어 ASR seed | LibriSpeech 채택 여부. 단순한 CC BY 4.0, 영어 read speech 한계 |
| 다국어 ASR seed | MLS 또는 Common Voice. MLS는 크고 언어 제한, Common Voice는 MDC 약관상 local-only |
| 겹치는 발화 seed | **CHiME-6가 현재 유일한 실질 후보다** — 화자별 분리 정답을 제공한다 ([`EVALS.md`](EVALS.md) §2.6, cpWER 전제). 채택 전 필요한 것은 **§3.6.2의 1차 출처 확인 한 가지**이며, 확인 결과 CC BY-SA 4.0이면 ShareAlike 의무만 추가로 검토하면 된다. 대안 후보 조사도 병행 가능 |

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

> **접근 한계 표기 규칙.** 아래 `[차단]` 표시는 **이 작업 환경의 egress proxy가 해당 도메인을
> 차단해 1차 페이지를 직접 열지 못했다**는 뜻이다 (`403 CONNECT tunnel failed`, 확인일 2026-08-12).
> 차단된 항목은 **확인된 사실로 인용하지 않으며**, 그 항목에 의존하는 판단은 blocker로 표시한다
> (§3.2.1, §3.6.2). 검색 스니펫은 1차 확인으로 취급하지 않는다.
> 차단 도메인: `durian.blender.org` · `openslr.org` / `www.openslr.org` ·
> `chimechallenge.github.io` · `www.chimechallenge.org` · `creativecommons.org` · `ffmpeg.org`.

- [Sintel About / license](https://durian.blender.org/about/) `[차단]`
- [Sintel Download & subtitles](https://durian.blender.org/download/) `[차단]`
- **[Sintel sharing 안내 — credit scroll 조건](https://durian.blender.org/sharing/)** `[차단]` — §3.2.1의 근거 페이지 (REVIEW-010 M-05)
- [CC BY 3.0 deed](https://creativecommons.org/licenses/by/3.0/) `[차단]`
- [LibriSpeech SLR12](https://www.openslr.org/12) `[차단]`
- [Multilingual LibriSpeech SLR94](https://www.openslr.org/94/) `[차단]`
- [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) `[차단]`
- [Common Voice 26.0 Korean datasheet](https://mozilladatacollective.com/datasets/cmqi922c5001pnq07dmj0oypw)
- [CC0 1.0 legal tool](https://creativecommons.org/publicdomain/zero/1.0/) `[차단]`
- [Mozilla Data Collective Terms](https://mozilladatacollective.com/terms)
- [Mozilla Data Collective terms FAQ](https://community.mozilladatacollective.com/faq-what-are-the-main-points-of-the-mdc-terms-of-use/)
- [Mozilla Data Collective API docs](https://mozilladatacollective.com/api-reference/docs)
- [CHiME-6 OpenSLR SLR150](https://openslr.org/150/) `[차단]` — §3.6.1 S1
- [CHiME-6 challenge download 안내 (역사적)](https://chimechallenge.github.io/chime6/download.html) `[차단]` — §3.6.1 S2
- **[현행 CHiME steward — CHiME-5 dataset](https://www.chimechallenge.org/datasets/chime5)** `[차단]` — §3.6.1 S3, 2024-01-01 재발행 고지 (REVIEW-010 M-03). **1차 확인 blocker**
- [CC BY-SA 4.0 deed](https://creativecommons.org/licenses/by-sa/4.0/) `[차단]`
- [YouTube Terms of Service](https://www.youtube.com/static?template=terms)
- [FFprobe documentation](https://ffmpeg.org/ffprobe.html) `[차단]` — 다만 `-show_streams`·`-show_format`·`-of json`의 동작은 §7.4 실행으로 확인
