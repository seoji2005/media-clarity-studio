#!/usr/bin/env python3
"""TASK-029 자막 spine 계약 단일 검증 진입점.

세 가지를 **분모를 섞지 않고** 각각 실행·보고한다 (TASK-029 §9).

1. **fixture** — `tests/fixtures/subtitle_contracts/k-*.json`을 production validator로
   실행하고 exact `(code, location)` 쌍을 확인한다.
2. **input mutants** — 정상 fixture 문서를 메모리에서 한 필드·한 관계씩 변형하고, 선언한
   `(code, location)`이 그대로 나오는지 확인한다. 각 mutant는 대응 base 정상 fixture가
   여전히 통과하는지(valid-case sentinel)도 함께 본다.
3. **schema mutants / validator code mutants** — **저장소 밖 임시 사본**에서 production
   schema의 방어(`required`·`enum`·범위·닫힌 객체)와 domain validator의 핵심 분기를 하나씩
   약화하고, 지정한 defect case가 실제로 탐지되지 않게 되는지(=mutant kill)와 valid-case
   sentinel이 여전히 통과하는지를 함께 확인한다. 저장소 파일은 바꾸지 않는다.

`--check-only`는 1·2만 수행한다. 임시 사본에서 이 모드를 돌려 3의 판정 근거로 쓴다.

Python 3.12 표준 라이브러리만 사용한다. network·모델·외부 dependency를 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from media_clarity import subtitle_contracts as contracts  # noqa: E402
from media_clarity.subtitle_contracts import (  # noqa: E402
    SchemaSet,
    load_fixture,
    run_fixtures,
    validate_documents,
)

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "subtitle_contracts"
SCHEMA_DIR = REPO_ROOT / "schemas"
VALIDATOR_PATH = "src/media_clarity/subtitle_contracts.py"

#: input mutation이 출발점으로 쓰는 정상 fixture.
BASE_CASES = {"base": "K-01", "mini": "K-02", "partial": "K-03"}


# ---------------------------------------------------------------------------
# 문서 탐색 도우미 — fixture 구조를 그대로 쓴다
# ---------------------------------------------------------------------------


def sp(documents: dict, segment_id: str) -> dict:
    for item in documents["speech_segments"]:
        if item["segment_id"] == segment_id:
            return item
    raise KeyError(segment_id)


def tr(documents: dict, segment_id: str) -> dict:
    for stream in documents["transcript"]["streams"]:
        for segment in stream["segments"]:
            if segment["segment_id"] == segment_id:
                return segment
    raise KeyError(segment_id)


def tl(documents: dict, segment_id: str) -> dict:
    for stream in documents["translated_transcript"]["streams"]:
        for segment in stream["segments"]:
            if segment["segment_id"] == segment_id:
                return segment
    raise KeyError(segment_id)


def cue(documents: dict, cue_id: str) -> dict:
    for item in documents["subtitle_document"]["cues"]:
        if item["cue_id"] == cue_id:
            return item
    raise KeyError(cue_id)


def asr_capability(documents: dict) -> dict:
    return documents["transcript"]["capability_report"]


def mt_capability(documents: dict) -> dict:
    return documents["translated_transcript"]["capability_report"]


T0 = "transcript/streams/0/segments"
T1 = "transcript/streams/1/segments"
L0 = "translated_transcript/streams/0/segments"
L1 = "translated_transcript/streams/1/segments"
C = "subtitle_document/cues"
S = "speech_segments"

#: 결함과 무관한 하류 문서는 fixture·mutant 입력에서 뺀다. 검사는 상류 → 하류 한 방향이라
#: 하류 문서를 빼도 상류 finding이 달라지지 않는다.
_LAYERS = (
    ("subtitle_document",
     ("speech_segments", "transcript", "translated_transcript", "subtitle_document")),
    ("translated_transcript", ("speech_segments", "transcript", "translated_transcript")),
    ("transcript", ("speech_segments", "transcript")),
    ("speech_segments", ("speech_segments",)),
)


def auto_keep(expected: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    if not expected:
        return _LAYERS[0][1]
    for prefix, keep in _LAYERS:
        if any(location == prefix or location.startswith(prefix + "/") for _, location in expected):
            return keep
    return _LAYERS[0][1]


@dataclass(frozen=True)
class Mutation:
    """input mutant 하나. `expected`는 관측이 아니라 **선언**이다."""

    mutation_id: str
    title: str
    base: str
    patch: Callable[[dict], Any]
    expected: tuple[tuple[str, str], ...]
    fixture: str | None = None
    keep: tuple[str, ...] | None = None
    #: 변형이 **문서 집합에서 상류 문서를 빼는 것 자체**인 mutant는 같은 부분집합을
    #: sentinel로 쓸 수 없다 (부분집합이 곧 결함이다). 그때만 온전한 계층을 지정한다.
    sentinel_keep: tuple[str, ...] | None = None

    def _restricted(self, sources: dict[str, dict], patch: bool) -> dict:
        documents = copy.deepcopy(sources[self.base])
        if patch:
            self.patch(documents)
        keep = self.keep or auto_keep(self.expected)
        if not patch and self.sentinel_keep is not None:
            keep = self.sentinel_keep
        return {key: documents[key] for key in keep if key in documents}

    def documents(self, sources: dict[str, dict]) -> dict:
        return self._restricted(sources, patch=True)

    def sentinel_documents(self, sources: dict[str, dict]) -> dict:
        """변형 전 같은 문서 부분집합 — 이 mutant의 valid-case sentinel이다."""

        return self._restricted(sources, patch=False)


MUTATIONS: list[Mutation] = []


def mutate(
    mutation_id: str,
    title: str,
    base: str,
    patch: Callable[[dict], Any],
    expected: list[tuple[str, str]],
    *,
    fixture: str | None = None,
    keep: tuple[str, ...] | None = None,
    sentinel_keep: tuple[str, ...] | None = None,
) -> None:
    MUTATIONS.append(
        Mutation(
            mutation_id=mutation_id,
            title=title,
            base=base,
            patch=patch,
            expected=tuple(sorted(expected)),
            fixture=fixture,
            keep=keep,
            sentinel_keep=sentinel_keep,
        )
    )


def _set(node: dict, **values: Any) -> None:
    node.update(values)


#: 민감 값 비노출 회귀에 쓰는 표식. 실제 개인정보가 아니라 합성 문자열이다.
SENSITIVE_PROBE = "MCS-SENSITIVE-PROBE-VALUE"


def _move_translation_segment(documents: dict, segment_id: str, target_stream: int) -> None:
    """번역 segment를 다른 stream으로 옮긴다 (stream 결박 반례용)."""

    streams = documents["translated_transcript"]["streams"]
    for stream in streams:
        for position, segment in enumerate(stream["segments"]):
            if segment["segment_id"] == segment_id:
                stream["segments"].pop(position)
                streams[target_stream]["segments"].append(segment)
                return
    raise KeyError(segment_id)


# ---------------------------------------------------------------------------
# input mutation 목록 (TASK-029 §9)
# ---------------------------------------------------------------------------


def register_mutations() -> None:
    if MUTATIONS:
        return

    # --- 축 교환과 target language -----------------------------------------
    mutate(
        "IM-01", "source axis 문서에 target_language를 붙였다", "mini",
        lambda d: _set(d["subtitle_document"], target_language="ko"),
        [("E_TEXT_AXIS", "subtitle_document/target_language")],
        fixture="K-04",
    )
    mutate(
        "IM-02", "source axis 문서에 source_transcript_ref를 붙였다", "mini",
        lambda d: _set(
            d["subtitle_document"],
            source_transcript_ref=copy.deepcopy(d["subtitle_document"]["input_document_ref"]),
        ),
        [("E_TEXT_AXIS", "subtitle_document/source_transcript_ref")],
    )
    mutate(
        "IM-03", "target axis cue가 반대 축 Transcript segment를 lineage로 참조했다", "base",
        lambda d: _set(cue(d, "cue-4")["lineage_fragments"][0], input_segment_id="tr-4"),
        [
            ("E_LINEAGE", f"{L0}/3/target_text"),
            ("E_LINEAGE", f"{C}/4/lines/0"),
            ("E_TEXT_AXIS", f"{C}/4/lineage_fragments/0/input_segment_id"),
        ],
        fixture="K-05",
    )
    mutate(
        "IM-04", "target axis 문서에서 target_language를 뺐다", "base",
        lambda d: d["subtitle_document"].pop("target_language"),
        [("E_TARGET_LANGUAGE", "subtitle_document/text_axis")],
    )
    mutate(
        "IM-05", "target axis 문서의 target_language를 비-ko로 바꿨다", "base",
        lambda d: _set(d["subtitle_document"], target_language="en"),
        [("E_TARGET_LANGUAGE", "subtitle_document/target_language")],
        fixture="K-06",
    )
    mutate(
        "IM-06", "target axis 문서에서 원본 Transcript ref를 뺐다", "base",
        lambda d: d["subtitle_document"].pop("source_transcript_ref"),
        [("E_TEXT_AXIS", "subtitle_document/text_axis")],
    )
    mutate(
        "IM-07", "번역 문서의 target_language를 비-ko로 바꿨다", "base",
        lambda d: _set(d["translated_transcript"], target_language="en"),
        [("E_TARGET_LANGUAGE", "translated_transcript/target_language")],
        fixture="K-07",
    )
    mutate(
        "IM-08", "번역 capability snapshot이 ko를 지원 대상에서 뺐다", "base",
        lambda d: _set(mt_capability(d), supported_target_languages=["en"]),
        [("E_TARGET_LANGUAGE",
          "translated_transcript/capability_report/supported_target_languages")],
    )

    # --- language span ------------------------------------------------------
    mutate(
        "IM-09", "language span이 text scalar 범위를 벗어났다", "base",
        lambda d: _set(tr(d, "tr-2")["language_spans"][0], char_end=99),
        [("E_OFFSET_RANGE", f"{T0}/1/language_spans/0/char_end")],
        fixture="K-08",
    )
    mutate(
        "IM-10", "language span이 앞 span과 겹친다", "base",
        lambda d: tr(d, "tr-2")["language_spans"].append(
            {"char_start": 3, "char_end": 11, "language": "en", "switch_kind": "unknown"}
        ),
        [("E_OFFSET_ORDER", f"{T0}/1/language_spans/1/char_start")],
        fixture="K-09",
    )
    mutate(
        "IM-11", "language span gap이 있는데 unknown review 상태가 없다", "base",
        lambda d: _set(tr(d, "tr-2"), needs_review=False, review_reasons=[]),
        [("E_LANGUAGE_GAP_REVIEW", f"{T0}/1/needs_review")],
        fixture="K-10",
    )
    mutate(
        "IM-12", "explicit und가 있는데 language_unknown review reason이 없다", "base",
        lambda d: _set(tr(d, "tr-3"), review_reasons=["low_confidence"]),
        [("E_LANGUAGE_GAP_REVIEW", f"{T1}/0/needs_review")],
        fixture="K-11",
    )
    mutate(
        "IM-13", "gap이 있는데 dominant_language를 기록했다", "base",
        lambda d: _set(tr(d, "tr-2"), dominant_language="en"),
        [("E_LANGUAGE_GAP_REVIEW", f"{T0}/1/dominant_language")],
    )
    mutate(
        "IM-14", "explicit und가 있는데 dominant_language를 기록했다", "base",
        lambda d: _set(tr(d, "tr-3"), dominant_language="en"),
        [("E_LANGUAGE_GAP_REVIEW", f"{T1}/0/dominant_language")],
    )
    mutate(
        "IM-15", "전 범위가 덮였는데 dominant_language가 파생 규칙과 다르다", "base",
        lambda d: _set(tr(d, "tr-1"), dominant_language="en"),
        [("E_LANGUAGE_GAP_REVIEW", f"{T0}/0/dominant_language")],
    )
    mutate(
        "IM-16", "첫 language span에 switch_kind를 붙였다", "base",
        lambda d: _set(tr(d, "tr-1")["language_spans"][0], switch_kind="unknown"),
        [("E_SCHEMA", f"{T0}/0/language_spans/0/switch_kind")],
    )
    mutate(
        "IM-17", "두 번째 language span에서 switch_kind를 뺐다", "base",
        lambda d: tr(d, "tr-1")["language_spans"][1].pop("switch_kind"),
        [("E_SCHEMA", f"{T0}/0/language_spans/1")],
    )
    mutate(
        "IM-18", "supports_intra_sentential_lid=false인데 intra_sentential 전환을 냈다", "base",
        lambda d: _set(asr_capability(d), supports_intra_sentential_lid=False),
        [
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/language_spans/1/switch_kind"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/language_spans/2/switch_kind"),
        ],
    )
    mutate(
        "IM-19", "language span char_start가 음수다 (schema 방어)", "base",
        lambda d: _set(tr(d, "tr-1")["language_spans"][0], char_start=-1),
        [("E_SCHEMA", f"{T0}/0/language_spans/0/char_start")],
    )
    mutate(
        "IM-20", "language tag가 구조 subset을 벗어났다 (schema 방어)", "base",
        lambda d: _set(tr(d, "tr-1")["language_spans"][0], language="JA"),
        [("E_SCHEMA", f"{T0}/0/language_spans/0/language")],
    )

    # --- Unicode scalar -----------------------------------------------------
    mutate(
        "IM-21", "emoji 앞뒤 offset을 UTF-16 code unit 기준으로 바꿨다", "mini",
        lambda d: _set(cue(d, "cue-m2")["lineage_fragments"][1], char_start=4),
        [
            ("E_LINEAGE", f"{T0}/1/text"),
            ("E_LINEAGE", f"{C}/1/lineage_fragments/1/text"),
        ],
        fixture="K-12",
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-22", "ASR n-best 대안 text에 lone surrogate가 있다", "base",
        lambda d: _set(tr(d, "tr-1")["alternatives"][0], text="a\ud800b"),
        [("E_UNICODE_SCALAR", f"{T0}/0/alternatives/0/text")],
        fixture="K-13",
    )
    mutate(
        "IM-23", "cue line text에 lone surrogate가 있다", "mini",
        lambda d: cue(d, "cue-m1")["lines"].__setitem__(0, "\ud800"),
        [("E_LINEAGE", f"{C}/0/lines/0"), ("E_UNICODE_SCALAR", f"{C}/0/lines/0")],
    )

    # --- 시간 ---------------------------------------------------------------
    mutate(
        "IM-24", "cue duration이 0이다", "base",
        lambda d: _set(cue(d, "cue-4"), end_seconds=4.0),
        [("E_TIME_RANGE", f"{C}/4/end_seconds")],
        fixture="K-14",
    )
    mutate(
        "IM-25", "cue timestamp가 역전됐다", "base",
        lambda d: _set(cue(d, "cue-4"), start_seconds=6.0, end_seconds=4.0),
        [("E_TIME_RANGE", f"{C}/4/end_seconds")],
    )
    mutate(
        "IM-26", "cue start_seconds가 음수다 (schema 방어)", "base",
        lambda d: _set(cue(d, "cue-1"), start_seconds=-1.0),
        [("E_SCHEMA", f"{C}/0/start_seconds")],
    )
    mutate(
        "IM-27", "ASR segment 시간이 참조한 입력 SpeechSegment 합집합 밖이다", "base",
        lambda d: _set(tr(d, "tr-4"), end_seconds=9.0),
        [("E_TIME_RANGE", f"{T0}/2/end_seconds")],
        fixture="K-15",
    )
    mutate(
        "IM-28", "token timestamp가 ASR segment 범위 밖이다", "base",
        lambda d: _set(tr(d, "tr-1")["tokens"][2], end_seconds=9.9),
        [("E_TIME_RANGE", f"{T0}/0/tokens/2/end_seconds")],
    )
    mutate(
        "IM-29", "token timing 순서가 역전됐다", "base",
        lambda d: _set(tr(d, "tr-1")["tokens"][2], start_seconds=0.1, end_seconds=0.5),
        [("E_TIME_ORDER", f"{T0}/0/tokens/2/start_seconds")],
        fixture="K-16",
    )
    mutate(
        "IM-30", "token의 start만 있고 end가 없다", "base",
        lambda d: tr(d, "tr-1")["tokens"][0].pop("end_seconds"),
        [("E_TIME_RANGE", f"{T0}/0/tokens/0")],
    )

    # --- capability 결박 -----------------------------------------------------
    mutate(
        "IM-31", "미지원 confidence를 1.0으로 채웠다", "mini",
        lambda d: _set(tr(d, "tm-1"), segment_confidence=1.0),
        [
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/segment_confidence"),
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/segment_confidence"),
        ],
        fixture="K-17",
    )
    mutate(
        "IM-32", "timing 미지원 adapter가 token timing을 냈다", "mini",
        lambda d: _set(
            tr(d, "tm-1"),
            tokens=[{"text": "日本語", "start_seconds": 0.0, "end_seconds": 2.0}],
        ),
        [("E_CAPABILITY_MISMATCH", "transcript/feature_status/token_timing")],
    )
    mutate(
        "IM-33", "LID 미지원 adapter가 language_spans를 냈다", "mini",
        lambda d: _set(
            tr(d, "tm-1"),
            language_spans=[{"char_start": 0, "char_end": 3, "language": "ja"}],
        ),
        [
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/language_spans"),
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/language_id"),
        ],
        fixture="K-18",
    )
    mutate(
        "IM-34", "diarization 미지원 adapter가 adapter-produced speaker label을 냈다", "mini",
        lambda d: _set(tr(d, "tm-1"), speaker_label="SPK-X", speaker_label_source="adapter"),
        [
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/speaker_label_source"),
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization"),
        ],
    )
    mutate(
        "IM-35", "input/channel에서 복사한 label을 adapter diarization 결과로 셌다", "base",
        lambda d: _set(tr(d, "tr-1"), speaker_label_source="input"),
        [("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization")],
        fixture="K-19",
    )
    mutate(
        "IM-36", "supports_nbest=false인데 alternatives가 있다", "base",
        lambda d: _set(asr_capability(d), supports_nbest=False),
        [
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/alternatives"),
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/nbest"),
        ],
        fixture="K-20",
    )
    mutate(
        "IM-37", "nbest_score_semantics=none인데 alternative score가 있다", "base",
        lambda d: _set(asr_capability(d), nbest_score_semantics="none"),
        [("E_CAPABILITY_MISMATCH", f"{T0}/0/alternatives/0/score")],
    )
    mutate(
        "IM-38", "supports_word_timing이 token_timing_units와 어긋난다", "base",
        lambda d: _set(asr_capability(d), supports_word_timing=False),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/supports_word_timing")],
    )
    mutate(
        "IM-39", "token timing이 있는데 token_unit이 지원 timing unit이 아니다", "base",
        lambda d: _set(d["transcript"], token_unit="character"),
        [("E_CAPABILITY_MISMATCH", "transcript/token_unit")],
    )
    mutate(
        "IM-40", "restricts_candidate_languages=false인데 max_candidate_languages가 있다", "base",
        lambda d: _set(asr_capability(d), max_candidate_languages=3),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/max_candidate_languages")],
    )
    mutate(
        "IM-41", 'supported_languages에 문자열 단독 "unknown"을 넣었다', "base",
        lambda d: _set(asr_capability(d), supported_languages=["unknown"]),
        [("E_SCHEMA", "transcript/capability_report/supported_languages/0")],
        fixture="K-21",
    )
    mutate(
        "IM-42", "capability report에서 determinism_tier를 뺐다 (schema 방어)", "base",
        lambda d: asr_capability(d).pop("determinism_tier"),
        [("E_SCHEMA", "transcript/capability_report")],
    )
    mutate(
        "IM-43", "feature_status에 여덟 번째 key를 넣었다 (닫힌 객체)", "base",
        lambda d: _set(d["transcript"]["feature_status"], forced_alignment="produced"),
        [("E_SCHEMA", "transcript/feature_status/forced_alignment")],
    )
    mutate(
        "IM-44", "번역 confidence semantics가 none인데 confidence가 있다", "base",
        lambda d: _set(mt_capability(d), translation_confidence_semantics="none"),
        [
            ("E_CAPABILITY_MISMATCH", f"{L0}/0/confidence"),
            ("E_CAPABILITY_MISMATCH",
             "translated_transcript/feature_status/translation_confidence"),
        ],
        fixture="K-22",
    )
    mutate(
        "IM-45", "orchestrator lineage를 adapter-produced semantic alignment로 가장했다", "base",
        lambda d: (
            _set(mt_capability(d), supports_segment_alignment=False),
            _set(d["translated_transcript"]["feature_status"], segment_alignment="unsupported"),
        ),
        [("E_CAPABILITY_MISMATCH", "translated_transcript/feature_status/segment_alignment")],
        fixture="K-23",
    )
    mutate(
        "IM-46", "segment_alignment=produced인데 adapter 증거가 없다", "base",
        lambda d: _set(tl(d, "tl-1"), alignment_evidence_source="orchestrator"),
        [("E_CAPABILITY_MISMATCH", "translated_transcript/feature_status/segment_alignment")],
    )
    mutate(
        "IM-47", "TranslationCapabilityReport에 알 수 없는 필드를 넣었다 (닫힌 객체)", "base",
        lambda d: _set(mt_capability(d), supports_confidence=True),
        [("E_SCHEMA", "translated_transcript/capability_report/supports_confidence")],
    )

    # --- channel semantics ----------------------------------------------------
    mutate(
        "IM-48", "separation_method=channel인데 channel_semantics가 mixed다", "base",
        lambda d: _set(sp(d, "sp-1"), channel_semantics="mixed"),
        [("E_CHANNEL_SEMANTICS", f"{S}/0/separation_method")],
        fixture="K-24",
    )
    mutate(
        "IM-49", "separation_method=channel인데 source_channel_index가 없다", "base",
        lambda d: sp(d, "sp-1").pop("source_channel_index"),
        [("E_CHANNEL_SEMANTICS", f"{S}/0/separation_method")],
    )
    mutate(
        "IM-50", "separation_method=none인데 speaker_label을 주장했다", "mini",
        lambda d: _set(sp(d, "sp-m1"), speaker_label="SPK-X"),
        [("E_CHANNEL_SEMANTICS", f"{S}/0/speaker_label")],
        fixture="K-25",
    )
    mutate(
        "IM-51", "speech_confidence만 있고 semantics가 없다", "base",
        lambda d: _set(sp(d, "sp-4"), speech_confidence=0.9),
        [("E_CONFIDENCE", f"{S}/3/speech_confidence")],
        fixture="K-26",
    )
    mutate(
        "IM-52", "calibrated_probability confidence가 [0,1] 밖이다", "base",
        lambda d: _set(
            sp(d, "sp-4"),
            speech_confidence=1.5,
            speech_confidence_semantics="calibrated_probability",
        ),
        [("E_CONFIDENCE", f"{S}/3/speech_confidence")],
    )
    mutate(
        "IM-53", "concurrent_stream_ids에 같은 값을 두 번 넣었다 (uniqueItems)", "base",
        lambda d: _set(sp(d, "sp-1"), concurrent_stream_ids=["s-alt", "s-alt"]),
        [("E_SCHEMA", f"{S}/0/concurrent_stream_ids/1")],
    )
    mutate(
        "IM-54", "overlap_kind가 enum 밖이다", "base",
        lambda d: _set(sp(d, "sp-1"), overlap_kind="sideways"),
        [("E_SCHEMA", f"{S}/0/overlap_kind")],
    )

    # --- concurrent stream ----------------------------------------------------
    mutate(
        "IM-55", "concurrent stream이 자기 자신이다", "base",
        lambda d: _set(sp(d, "sp-1"), concurrent_stream_ids=["s-main"]),
        [("E_STREAM_REF", f"{S}/0/concurrent_stream_ids/0")],
        fixture="K-27",
    )
    mutate(
        "IM-56", "concurrent stream이 존재하지 않는다", "base",
        lambda d: _set(sp(d, "sp-1"), concurrent_stream_ids=["s-ghost"]),
        [("E_STREAM_REF", f"{S}/0/concurrent_stream_ids/0")],
    )
    mutate(
        "IM-57", "선언한 concurrent stream과 실제 시간이 겹치지 않는다", "base",
        lambda d: _set(sp(d, "sp-4"), concurrent_stream_ids=["s-alt"], overlap_kind="partial"),
        [("E_STREAM_REF", f"{S}/3/concurrent_stream_ids/0")],
    )
    mutate(
        "IM-58", "concurrent stream 참조가 비대칭이다", "base",
        lambda d: _set(sp(d, "sp-2"), concurrent_stream_ids=[]),
        [
            ("E_STREAM_REF", f"{S}/0/concurrent_stream_ids/0"),
            ("E_STREAM_REF", f"{S}/2/concurrent_stream_ids/0"),
        ],
        fixture="K-28",
    )

    # --- 참조와 원문 텍스트 ------------------------------------------------------
    mutate(
        "IM-59", "존재하지 않는 SpeechSegment를 참조했다", "base",
        lambda d: _set(tr(d, "tr-1"), source_speech_segment_ids=["sp-ghost"]),
        [("E_SOURCE_REF", f"{T0}/0/source_speech_segment_ids/0")],
        fixture="K-29",
    )
    mutate(
        "IM-60", "서로 다른 stream의 입력을 한 segment lineage로 섞었다", "base",
        lambda d: _set(tr(d, "tr-1"), source_speech_segment_ids=["sp-1", "sp-2"]),
        [("E_SOURCE_REF", f"{T0}/0/source_speech_segment_ids")],
        fixture="K-30",
    )
    mutate(
        "IM-61", "번역이 존재하지 않는 source segment를 참조했다", "base",
        lambda d: _set(tl(d, "tl-1")["source_fragments"][0], source_segment_id="tr-ghost"),
        [
            ("E_ALIGNMENT", f"{L0}/0/alignment_kind"),
            ("E_SOURCE_COVERAGE", f"{T0}/0/text"),
            ("E_SOURCE_REF", f"{L0}/0/source_fragments/0/source_segment_id"),
        ],
        keep=_LAYERS[1][1],
    )
    mutate(
        "IM-62", "cue lineage가 존재하지 않는 입력 segment를 참조했다", "base",
        lambda d: _set(cue(d, "cue-1")["lineage_fragments"][0], input_segment_id="tl-ghost"),
        [
            ("E_LINEAGE", f"{L0}/0/target_text"),
            ("E_LINEAGE", f"{C}/0/lines/0"),
            ("E_SOURCE_REF", f"{C}/0/lineage_fragments/0/input_segment_id"),
        ],
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-63", "source fragment text를 한 글자 바꿨다", "base",
        lambda d: _set(
            tl(d, "tl-1")["source_fragments"][0], source_text="今日はsunnyですぬ"
        ),
        [("E_SOURCE_TEXT", f"{L0}/0/source_fragments/0/source_text")],
        fixture="K-31",
    )
    mutate(
        "IM-64", "source_fragments를 빈 배열로 만들었다 (minItems)", "base",
        lambda d: _set(tl(d, "tl-1"), source_fragments=[]),
        [("E_SCHEMA", f"{L0}/0/source_fragments")],
    )

    # --- coverage partition ------------------------------------------------------
    mutate(
        "IM-65", "complete 번역인데 원문 coverage에 gap이 있다", "base",
        lambda d: _set(
            tl(d, "tl-3")["source_fragments"][0], char_start=6, source_text="world"
        ),
        [("E_SOURCE_COVERAGE", f"{T0}/1/text")],
        fixture="K-32",
        keep=_LAYERS[1][1],
    )
    mutate(
        "IM-66", "complete 번역인데 covered 범위가 중복된다", "base",
        lambda d: _set(
            tl(d, "tl-3")["source_fragments"][0], char_start=4, source_text="o world"
        ),
        [("E_SOURCE_COVERAGE", f"{L0}/2/source_fragments/0/char_start")],
        fixture="K-33",
    )
    mutate(
        "IM-67", "coverage_status=partial인데 uncovered가 비었다", "base",
        lambda d: _set(d["translated_transcript"], coverage_status="partial"),
        [("E_SOURCE_COVERAGE", "translated_transcript/coverage_status")],
    )
    mutate(
        "IM-68", "partial 번역인데 uncovered로도 덮이지 않은 gap이 남았다", "partial",
        lambda d: _set(
            d["translated_transcript"]["uncovered_source_fragments"][0],
            char_start=7,
            source_text="orld",
        ),
        [("E_SOURCE_COVERAGE", f"{T0}/1/text")],
        fixture="K-34",
        keep=_LAYERS[1][1],
    )
    mutate(
        "IM-69", "partial 번역의 uncovered fragment가 중복이다", "partial",
        lambda d: d["translated_transcript"]["uncovered_source_fragments"].append(
            copy.deepcopy(d["translated_transcript"]["uncovered_source_fragments"][0])
        ),
        [
            ("E_OFFSET_ORDER", "translated_transcript/uncovered_source_fragments/1/char_start"),
            ("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments/1/char_start"),
        ],
        fixture="K-35",
    )
    mutate(
        "IM-70", "partial 번역의 covered와 uncovered 범위가 겹친다", "partial",
        lambda d: _set(
            d["translated_transcript"]["uncovered_source_fragments"][0],
            char_start=3,
            source_text="lo world",
        ),
        [("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments/0/char_start")],
        fixture="K-36",
    )
    mutate(
        "IM-71", "partial 번역인데 coverage_status를 complete로 적었다", "partial",
        lambda d: _set(d["translated_transcript"], coverage_status="complete"),
        [("E_SOURCE_COVERAGE", "translated_transcript/coverage_status")],
    )
    mutate(
        "IM-72", "uncovered fragment의 needs_review를 false로 바꿨다", "partial",
        lambda d: _set(
            d["translated_transcript"]["uncovered_source_fragments"][0], needs_review=False
        ),
        [("E_REVIEW_STATE", "translated_transcript/uncovered_source_fragments/0/needs_review")],
        fixture="K-37",
    )

    # --- alignment kind ------------------------------------------------------------
    mutate(
        "IM-110", "uncovered fragment에서 review reason을 지웠다 (minItems)", "partial",
        lambda d: _set(
            d["translated_transcript"]["uncovered_source_fragments"][0],
            needs_review=False,
            review_reasons=[],
        ),
        [("E_SCHEMA", "translated_transcript/uncovered_source_fragments/0/review_reasons")],
        fixture="K-57",
    )

    mutate(
        "IM-73", "one_to_one segment를 merged라고 적었다", "base",
        lambda d: _set(tl(d, "tl-1"), alignment_kind="merged"),
        [("E_ALIGNMENT", f"{L0}/0/alignment_kind")],
        fixture="K-38",
    )
    mutate(
        "IM-74", "merged segment를 one_to_one이라고 적었다", "base",
        lambda d: _set(tl(d, "tl-5"), alignment_kind="one_to_one"),
        [("E_ALIGNMENT", f"{L0}/3/alignment_kind")],
    )
    mutate(
        "IM-75", "strict subrange를 one_to_one이라고 적었다", "base",
        lambda d: _set(tl(d, "tl-2"), alignment_kind="one_to_one"),
        [("E_ALIGNMENT", f"{L0}/1/alignment_kind")],
    )
    mutate(
        "IM-76", "전체 범위를 split이라고 적었다", "base",
        lambda d: _set(tl(d, "tl-1"), alignment_kind="split"),
        [("E_ALIGNMENT", f"{L0}/0/alignment_kind")],
    )
    mutate(
        "IM-77", "dropped인데 target_text가 비어 있지 않다", "base",
        lambda d: _set(tl(d, "tl-4"), target_text="번역"),
        [("E_ALIGNMENT", f"{L1}/0/target_text"), ("E_LINEAGE", f"{L1}/0/target_text")],
        fixture="K-39",
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-78", "dropped인데 untranslated_span review reason이 없다", "base",
        lambda d: _set(tl(d, "tl-4"), review_reasons=["source_ambiguous"]),
        [("E_REVIEW_STATE", f"{L1}/0/review_reasons")],
    )
    mutate(
        "IM-79", "alignment_kind가 enum 밖이다", "base",
        lambda d: _set(tl(d, "tl-1"), alignment_kind="paraphrase"),
        [("E_SCHEMA", f"{L0}/0/alignment_kind")],
    )

    # --- cue 시간·참조 ---------------------------------------------------------------
    mutate(
        "IM-80", "cue 배열이 canonical order가 아니다", "base",
        lambda d: d["subtitle_document"]["cues"].insert(
            3, d["subtitle_document"]["cues"].pop(4)
        ),
        [("E_CUE_ORDER", f"{C}/4")],
        fixture="K-40",
    )
    mutate(
        "IM-81", "같은 stream의 cue 시간이 겹친다", "base",
        lambda d: _set(cue(d, "cue-3"), start_seconds=3.2),
        [("E_CUE_OVERLAP", f"{C}/3")],
        fixture="K-41",
    )
    mutate(
        "IM-82", "concurrent cue가 자기 자신이다", "base",
        lambda d: _set(cue(d, "cue-2"), concurrent_cue_ids=["cue-2"]),
        [
            ("E_CUE_REF", f"{C}/1/concurrent_cue_ids/0"),
            ("E_CUE_REF", f"{C}/2/concurrent_cue_ids/0"),
        ],
    )
    mutate(
        "IM-83", "concurrent cue가 존재하지 않는다", "base",
        lambda d: _set(cue(d, "cue-2"), concurrent_cue_ids=["cue-ghost"]),
        [
            ("E_CUE_REF", f"{C}/1/concurrent_cue_ids/0"),
            ("E_CUE_REF", f"{C}/2/concurrent_cue_ids/0"),
        ],
    )
    mutate(
        "IM-84", "선언한 concurrent cue와 실제 시간이 겹치지 않는다", "base",
        lambda d: _set(cue(d, "cue-4"), concurrent_cue_ids=["cue-1"]),
        [
            ("E_CUE_REF", f"{C}/4/concurrent_cue_ids/0"),
            ("E_CUE_REF", f"{C}/4/overlap_kind"),
        ],
        fixture="K-42",
    )
    mutate(
        "IM-85", "concurrent cue 참조가 비대칭이다", "base",
        lambda d: _set(cue(d, "cue-3"), concurrent_cue_ids=[]),
        [("E_CUE_REF", f"{C}/2/concurrent_cue_ids/1")],
    )

    # --- cue lineage ------------------------------------------------------------------
    mutate(
        "IM-86", "cue lineage fragment의 line_index가 lines 범위 밖이다", "mini",
        lambda d: _set(cue(d, "cue-m1")["lineage_fragments"][1], line_index=5),
        [
            ("E_LINEAGE", f"{T0}/0/text"),
            ("E_LINEAGE", f"{C}/0/lineage_fragments/1/line_index"),
            ("E_LINEAGE", f"{C}/0/lines/1"),
        ],
        fixture="K-43",
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-87", "cue lineage fragment text를 바꿨다", "mini",
        lambda d: (
            _set(cue(d, "cue-m1")["lineage_fragments"][0], text="月"),
            cue(d, "cue-m1")["lines"].__setitem__(0, "月"),
        ),
        [("E_LINEAGE", f"{C}/0/lineage_fragments/0/text")],
        fixture="K-44",
    )
    mutate(
        "IM-88", "line text가 visible fragment 결합과 다르다", "mini",
        lambda d: cue(d, "cue-m1")["lines"].__setitem__(1, "本"),
        [("E_LINEAGE", f"{C}/0/lines/1")],
    )
    mutate(
        "IM-89", "허용 집합 밖 문자를 line_break_whitespace로 옮겼다", "mini",
        lambda d: (
            _set(cue(d, "cue-m3")["line_break_whitespace"][0],
                 char_start=3, char_end=4, text="d"),
            _set(cue(d, "cue-m3")["lineage_fragments"][0], char_end=3, text="Goo"),
            cue(d, "cue-m3")["lines"].__setitem__(0, "Goo"),
        ),
        [
            ("E_LINEAGE", f"{T0}/2/text"),
            ("E_LINEAGE", f"{C}/2/line_break_whitespace/0/text"),
        ],
        fixture="K-45",
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-90", "cue의 렌더링 line 순서를 뒤집고 line_index도 함께 교환했다", "mini",
        lambda d: (
            cue(d, "cue-m1").__setitem__("lines", ["本語", "日"]),
            _set(cue(d, "cue-m1")["lineage_fragments"][0], line_index=1),
            _set(cue(d, "cue-m1")["lineage_fragments"][1], line_index=0),
        ),
        [("E_OFFSET_ORDER", f"{C}/0/lineage_fragments/0/char_start")],
        fixture="K-46",
    )
    mutate(
        "IM-91", "cue lineage fragment 범위가 겹친다", "mini",
        lambda d: _set(cue(d, "cue-m2")["lineage_fragments"][1], char_start=2),
        [
            ("E_LINEAGE", f"{C}/1/lineage_fragments/1/char_start"),
            ("E_LINEAGE", f"{C}/1/lineage_fragments/1/text"),
        ],
    )
    mutate(
        "IM-92", "line break whitespace 기록을 빼서 원문 scalar가 덮이지 않는다", "mini",
        lambda d: _set(cue(d, "cue-m3"), line_break_whitespace=[]),
        [("E_LINEAGE", f"{T0}/2/text")],
        fixture="K-47",
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-93", "cue lineage fragment 범위가 입력 text 길이를 넘는다", "mini",
        lambda d: _set(cue(d, "cue-m2")["lineage_fragments"][1], char_end=9),
        [
            ("E_LINEAGE", f"{T0}/1/text"),
            ("E_LINEAGE", f"{C}/1/lines/1"),
            ("E_OFFSET_RANGE", f"{C}/1/lineage_fragments/1/char_end"),
        ],
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-94", "같은 scalar 범위를 두 fragment가 중복해서 덮는다", "mini",
        lambda d: cue(d, "cue-m1")["lineage_fragments"].append(
            {"line_index": 0, "input_segment_id": "tm-1", "char_start": 0, "char_end": 1,
             "text": "日"}
        ),
        [
            ("E_LINEAGE", f"{C}/0/lineage_fragments/2/char_start"),
            ("E_LINEAGE", f"{C}/0/lines/0"),
        ],
        fixture="K-48",
    )
    mutate(
        "IM-95", "cue에 알 수 없는 필드를 넣었다 (닫힌 객체)", "mini",
        lambda d: _set(cue(d, "cue-m1"), position="bottom-center"),
        [("E_SCHEMA", f"{C}/0/position")],
    )

    # --- style profile --------------------------------------------------------------------
    mutate(
        "IM-96", "resolved_style의 max_duration이 min_duration보다 작다", "base",
        lambda d: _set(d["subtitle_document"]["resolved_style"], max_duration_seconds=0.5),
        [
            ("E_TIME_RANGE", "subtitle_document/resolved_style/language_overrides/ko"),
            ("E_TIME_RANGE", "subtitle_document/resolved_style/max_duration_seconds"),
        ],
        fixture="K-49",
    )
    mutate(
        "IM-97", "resolved_style snapshot을 통째로 뺐다", "base",
        lambda d: d["subtitle_document"].pop("resolved_style"),
        [("E_SCHEMA", "subtitle_document")],
        fixture="K-50",
    )
    mutate(
        "IM-98", "language override의 min_duration이 max_duration보다 크다", "base",
        lambda d: _set(
            d["subtitle_document"]["resolved_style"]["language_overrides"]["ko"],
            min_duration_seconds=9.0,
        ),
        [("E_TIME_RANGE",
          "subtitle_document/resolved_style/language_overrides/ko/min_duration_seconds")],
    )
    mutate(
        "IM-99", "resolved_style의 max_cps를 0으로 두었다 (exclusiveMinimum)", "base",
        lambda d: _set(d["subtitle_document"]["resolved_style"], max_cps=0),
        [("E_SCHEMA", "subtitle_document/resolved_style/max_cps")],
    )
    mutate(
        "IM-100", "style profile 수치를 schema 기본값처럼 문서에서 뺐다", "base",
        lambda d: d["subtitle_document"]["resolved_style"].pop("max_cps"),
        [("E_SCHEMA", "subtitle_document/resolved_style")],
        fixture="K-51",
    )

    # --- review 상태와 확장 -------------------------------------------------------------------
    mutate(
        "IM-101", "review reason이 있는데 needs_review=false다", "base",
        lambda d: _set(cue(d, "cue-2"), needs_review=False),
        [("E_REVIEW_STATE", f"{C}/1/needs_review")],
        fixture="K-52",
    )
    mutate(
        "IM-102", "needs_review=true인데 review reason이 없다", "base",
        lambda d: _set(tl(d, "tl-3"), review_reasons=[]),
        [("E_REVIEW_STATE", f"{L0}/2/needs_review")],
    )
    mutate(
        "IM-103", "review reason에 other가 있는데 확장 ID가 없다", "base",
        lambda d: _set(cue(d, "cue-1"), needs_review=True, review_reasons=["other"]),
        [("E_SCHEMA", f"{C}/0")],
        fixture="K-53",
    )
    mutate(
        "IM-104", "확장 ID가 x- 접두사 pattern을 어겼다", "base",
        lambda d: _set(
            cue(d, "cue-1"),
            needs_review=True,
            review_reasons=["other"],
            review_extension_id="y-custom",
        ),
        [("E_SCHEMA", f"{C}/0/review_extension_id")],
    )
    mutate(
        "IM-105", "is_low_confidence=true인데 low_confidence review reason이 없다", "base",
        lambda d: _set(tr(d, "tr-1"), is_low_confidence=True),
        [("E_REVIEW_STATE", f"{T0}/0/is_low_confidence")],
        fixture="K-54",
    )
    mutate(
        "IM-106", "transcript segment에서 needs_review를 뺐다 (required)", "base",
        lambda d: tr(d, "tr-1").pop("needs_review"),
        [("E_SCHEMA", f"{T0}/0")],
    )

    # --- unsupported feature ---------------------------------------------------------------------
    mutate(
        "IM-107", "unsupported feature가 존재하지 않는 cue를 참조했다", "base",
        lambda d: _set(d["subtitle_document"]["unsupported_features"][0], cue_id="cue-ghost"),
        [("E_CUE_REF", "subtitle_document/unsupported_features/0/cue_id")],
        fixture="K-55",
    )
    mutate(
        "IM-108", "feature_kind=other인데 확장 ID가 x- 접두사가 아니다", "base",
        lambda d: _set(d["subtitle_document"]["unsupported_features"][0], feature_kind="other"),
        [("E_SCHEMA", "subtitle_document/unsupported_features/0/feature_identifier")],
        fixture="K-56",
    )
    mutate(
        "IM-109", "unsupported feature의 feature_kind가 enum 밖이다", "base",
        lambda d: _set(d["subtitle_document"]["unsupported_features"][0], feature_kind="glow"),
        [("E_SCHEMA", "subtitle_document/unsupported_features/0/feature_kind")],
    )


    # --- 개별 domain 분기를 고립시키는 보완 mutant (§9 "보완 mutant/fixture") ------------
    mutate(
        "IM-111", "번역 coverage의 꼬리 범위가 덮이지 않았다", "base",
        lambda d: _set(tl(d, "tl-3")["source_fragments"][0], char_end=9, source_text=" wor"),
        [("E_SOURCE_COVERAGE", f"{T0}/1/text")],
        keep=_LAYERS[1][1],
    )
    mutate(
        "IM-112", "capability가 지원하는 축을 unsupported로 보고했다", "base",
        lambda d: (
            tr(d, "tr-1").pop("alternatives"),
            _set(d["transcript"]["feature_status"], nbest="unsupported"),
        ),
        [("E_CAPABILITY_MISMATCH", "transcript/feature_status/nbest")],
    )
    mutate(
        "IM-113", "SpeechSegment ID가 문서 집합 안에서 중복이다", "base",
        lambda d: _set(sp(d, "sp-2"), segment_id="sp-1"),
        [("E_SCHEMA", f"{S}/1/segment_id")],
        keep=("speech_segments",),
    )
    mutate(
        "IM-114", "speaker_label만 있고 speaker_label_source가 없다", "base",
        lambda d: tr(d, "tr-1").pop("speaker_label_source"),
        [
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization"),
            ("E_SCHEMA", f"{T0}/0/speaker_label"),
        ],
    )
    mutate(
        "IM-115", "ASR segment 시작이 입력 구간 합집합보다 앞이다", "base",
        lambda d: _set(tr(d, "tr-2"), start_seconds=2.0),
        [("E_TIME_RANGE", f"{T0}/1/start_seconds")],
    )
    mutate(
        "IM-116", "language span의 char_end가 char_start와 같다", "base",
        lambda d: _set(tr(d, "tr-2")["language_spans"][0], char_end=0),
        [("E_OFFSET_RANGE", f"{T0}/1/language_spans/0/char_end")],
    )
    mutate(
        "IM-117", "번역 문서의 timebase_ref가 원문과 다르다", "base",
        lambda d: _set(d["translated_transcript"], timebase_ref="tb-other"),
        [("E_SOURCE_REF", "translated_transcript/timebase_ref")],
    )
    mutate(
        "IM-118", "source fragment 범위가 원문 text 길이를 넘는다", "base",
        lambda d: _set(tl(d, "tl-1")["source_fragments"][0], char_end=99),
        [
            ("E_ALIGNMENT", f"{L0}/0/alignment_kind"),
            ("E_OFFSET_RANGE", f"{L0}/0/source_fragments/0/char_end"),
            ("E_SOURCE_COVERAGE", f"{T0}/0/text"),
        ],
        keep=_LAYERS[1][1],
    )
    mutate(
        "IM-119", "line_break_whitespace의 after_line_index가 줄 경계가 아니다", "mini",
        lambda d: _set(cue(d, "cue-m3")["line_break_whitespace"][0], after_line_index=5),
        [
            ("E_LINEAGE", f"{T0}/2/text"),
            ("E_LINEAGE", f"{C}/2/line_break_whitespace/0/after_line_index"),
        ],
        keep=_LAYERS[0][1],
    )
    mutate(
        "IM-120", "dropped가 아닌 번역 segment의 target_text가 비었다", "base",
        lambda d: _set(tl(d, "tl-2"), target_text=""),
        [
            ("E_ALIGNMENT", f"{L0}/1/target_text"),
            ("E_LINEAGE", f"{C}/1/lines/0"),
            ("E_OFFSET_RANGE", f"{C}/1/lineage_fragments/0/char_end"),
        ],
    )
    mutate(
        "IM-121", "capability 미지원 축을 not_requested로 보고했다", "mini",
        lambda d: _set(d["transcript"]["feature_status"], token_timing="not_requested"),
        [("E_CAPABILITY_MISMATCH", "transcript/feature_status/token_timing")],
    )

    # --- REVIEW-023 B-01: 시간·stream·lineage 교차 문서 결박 ------------------------
    mutate(
        "IM-122", "ASR 구간이 입력 SpeechSegment 사이의 gap을 가로지른다 ([0,2)+[3,4)에 [0,3.5))",
        "base",
        lambda d: _set(
            tr(d, "tr-1"), source_speech_segment_ids=["sp-1", "sp-3"], end_seconds=3.5
        ),
        [("E_TIME_RANGE", f"{T0}/0/end_seconds")],
        keep=_LAYERS[2][1],
        fixture="K-58",
    )
    mutate(
        "IM-123", "ASR 구간이 입력 gap을 가로질러 두 번째 구간 끝까지 뻗는다 ([0,4))", "base",
        lambda d: _set(
            tr(d, "tr-1"), source_speech_segment_ids=["sp-1", "sp-3"], end_seconds=4.0
        ),
        [("E_TIME_RANGE", f"{T0}/0/end_seconds")],
        keep=_LAYERS[2][1],
    )
    mutate(
        "IM-124", "Transcript만 원본과 무관한 timebase를 쓴다", "base",
        lambda d: _set(d["transcript"], timebase_ref="tb-detached"),
        [("E_SOURCE_REF", "transcript/timebase_ref")],
        keep=_LAYERS[2][1],
        fixture="K-59",
    )
    mutate(
        "IM-125", "TranslatedTranscript만 원본과 무관한 timebase를 쓴다", "base",
        lambda d: _set(d["translated_transcript"], timebase_ref="tb-detached"),
        [("E_SOURCE_REF", "translated_transcript/timebase_ref")],
        keep=_LAYERS[1][1],
        fixture="K-60",
    )
    mutate(
        "IM-126", "SubtitleDocument만 원본과 무관한 timebase를 쓴다", "base",
        lambda d: _set(d["subtitle_document"], timebase_ref="tb-detached"),
        [("E_SOURCE_REF", "subtitle_document/timebase_ref")],
        keep=_LAYERS[0][1],
        fixture="K-61",
    )
    mutate(
        "IM-127", "같은 실행의 SpeechSegment가 서로 다른 timebase를 쓴다", "base",
        lambda d: _set(sp(d, "sp-2"), timebase_ref="tb-detached"),
        [("E_SOURCE_REF", f"{S}/1/timebase_ref")],
        keep=_LAYERS[3][1],
    )
    mutate(
        "IM-128", "ASR segment가 다른 stream의 입력을 참조한다", "base",
        lambda d: _set(tr(d, "tr-2"), source_speech_segment_ids=["sp-2"]),
        [("E_STREAM_REF", f"{T0}/1/source_speech_segment_ids")],
        keep=_LAYERS[2][1],
        fixture="K-62",
    )
    mutate(
        "IM-129", "번역 segment가 다른 stream의 원문 segment를 참조한다", "base",
        lambda d: _move_translation_segment(d, "tl-6", 0),
        [("E_STREAM_REF", f"{L0}/4/source_fragments/0/source_segment_id")],
        keep=_LAYERS[1][1],
        fixture="K-63",
    )
    mutate(
        "IM-130", "cue가 다른 stream의 입력 segment를 참조한다", "base",
        lambda d: _set(cue(d, "cue-4"), stream_id="s-alt"),
        [("E_STREAM_REF", f"{C}/4/lineage_fragments/0/input_segment_id")],
        keep=_LAYERS[0][1],
        fixture="K-64",
    )
    mutate(
        "IM-131", "Transcript stream_id가 중복이다", "base",
        lambda d: d["transcript"]["streams"].append({"stream_id": "s-main", "segments": []}),
        [("E_SCHEMA", "transcript/streams/2/stream_id")],
        keep=_LAYERS[2][1],
        fixture="K-65",
    )
    mutate(
        "IM-132", "Transcript segment_id가 중복이다", "base",
        lambda d: _set(tr(d, "tr-5"), segment_id="tr-4"),
        [("E_SCHEMA", f"{T0}/3/segment_id")],
        keep=_LAYERS[2][1],
        fixture="K-66",
    )
    mutate(
        "IM-133", "TranslatedTranscript stream_id가 중복이다", "base",
        lambda d: d["translated_transcript"]["streams"].append(
            {"stream_id": "s-main", "segments": []}
        ),
        [("E_SCHEMA", "translated_transcript/streams/2/stream_id")],
        keep=_LAYERS[1][1],
        fixture="K-67",
    )
    mutate(
        "IM-134", "TranslatedTranscript segment_id가 중복이다", "base",
        lambda d: _set(tl(d, "tl-3"), segment_id="tl-2"),
        [("E_SCHEMA", f"{L0}/2/segment_id")],
        keep=_LAYERS[1][1],
        fixture="K-68",
    )
    mutate(
        "IM-135", "cue_id가 중복이다", "base",
        lambda d: _set(cue(d, "cue-4"), cue_id="cue-1"),
        [("E_SCHEMA", f"{C}/4/cue_id")],
        keep=_LAYERS[0][1],
        fixture="K-69",
    )
    mutate(
        "IM-136", "merged 번역의 source fragment 순서를 뒤집었다", "base",
        lambda d: _set(
            tl(d, "tl-5"), source_fragments=list(reversed(tl(d, "tl-5")["source_fragments"]))
        ),
        [("E_OFFSET_ORDER", f"{L0}/3/source_fragments/1/char_start")],
        keep=_LAYERS[1][1],
        fixture="K-70",
    )

    # --- REVIEW-023 B-02: capability 진실성과 field absence -------------------------
    mutate(
        "IM-137", "LID 결과가 없는데 language_spans를 빈 배열로 채웠다", "base",
        lambda d: _set(tr(d, "tr-4"), language_spans=[]),
        [("E_SCHEMA", f"{T0}/2/language_spans")],
        keep=_LAYERS[2][1],
        fixture="K-71",
    )
    mutate(
        "IM-138", "n-best 결과가 없는데 alternatives를 빈 배열로 채웠다", "base",
        lambda d: _set(tr(d, "tr-4"), alternatives=[]),
        [("E_SCHEMA", f"{T0}/2/alternatives")],
        keep=_LAYERS[2][1],
        fixture="K-72",
    )
    mutate(
        "IM-139", "token timing 결과가 없는데 tokens를 빈 배열로 채웠다", "base",
        lambda d: _set(tr(d, "tr-4"), tokens=[]),
        [("E_SCHEMA", f"{T0}/2/tokens")],
        keep=_LAYERS[2][1],
        fixture="K-73",
    )
    mutate(
        "IM-140", "ASR capability snapshot의 adapter_id가 provenance와 다르다", "base",
        lambda d: _set(asr_capability(d), adapter_id="asr-other"),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/adapter_id")],
        keep=_LAYERS[2][1],
        fixture="K-74",
    )
    mutate(
        "IM-141", "ASR capability snapshot의 adapter_version이 provenance와 다르다", "base",
        lambda d: _set(asr_capability(d), adapter_version="9.9.9"),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/adapter_version")],
        keep=_LAYERS[2][1],
    )
    mutate(
        "IM-142", "번역 capability snapshot의 adapter_id가 provenance와 다르다", "base",
        lambda d: _set(mt_capability(d), adapter_id="mt-other"),
        [("E_CAPABILITY_MISMATCH", "translated_transcript/capability_report/adapter_id")],
        keep=_LAYERS[1][1],
        fixture="K-75",
    )
    mutate(
        "IM-143", "diarization 미지원 adapter가 stream-level adapter label을 냈다", "mini",
        lambda d: _set(
            d["transcript"]["streams"][0], speaker_label="SPK-X", speaker_label_source="adapter"
        ),
        [
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization"),
            ("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label_source"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-76",
    )
    mutate(
        "IM-144", "speaker_label_source=input인데 입력 SpeechSegment에 label이 없다", "mini",
        lambda d: _set(tr(d, "tm-1"), speaker_label="SPK-X", speaker_label_source="input"),
        [("E_CAPABILITY_MISMATCH", f"{T0}/0/speaker_label_source")],
        keep=_LAYERS[2][1],
        fixture="K-77",
    )
    mutate(
        "IM-145", "overlap_kind=none인데 concurrent stream을 선언했다", "base",
        lambda d: _set(sp(d, "sp-4"), concurrent_stream_ids=["s-alt"]),
        [
            ("E_STREAM_REF", f"{S}/3/concurrent_stream_ids/0"),
            ("E_STREAM_REF", f"{S}/3/overlap_kind"),
        ],
        keep=_LAYERS[3][1],
        fixture="K-78",
    )
    mutate(
        "IM-146", "language_spans 없이 dominant_language만 남겼다", "base",
        lambda d: (tr(d, "tr-4").pop("language_spans"), _set(tr(d, "tr-4"), dominant_language="en")),
        [("E_LANGUAGE_GAP_REVIEW", f"{T0}/2/dominant_language")],
        keep=_LAYERS[2][1],
        fixture="K-79",
    )

    # --- REVIEW-023 B-02: 민감 값이 message에 새지 않는다 ----------------------------
    mutate(
        "IM-147", "enum 밖의 민감 문자열을 review_reasons에 넣었다", "base",
        lambda d: _set(cue(d, "cue-2"), review_reasons=[SENSITIVE_PROBE]),
        [("E_SCHEMA", f"{C}/1/review_reasons/0")],
        keep=_LAYERS[0][1],
        fixture="K-80",
    )

    # --- REVIEW-023 B-03: 다섯 schema의 **root** 닫힌 객체 방어 ---------------------
    # $defs 수준 닫힌 객체는 SM-04·SM-09·SM-14가 이미 감사한다. root additionalProperties
    # 는 그와 다른 방어면이라 문서마다 별도 반례를 둔다.
    mutate(
        "IM-148", "SpeechSegment root에 미지의 필드를 붙였다", "mini",
        lambda d: _set(d["speech_segments"][0], x_unknown_root=1),
        [("E_SCHEMA", "speech_segments/0/x_unknown_root")],
        keep=_LAYERS[3][1],
        fixture="K-81",
    )
    mutate(
        "IM-149", "Transcript root에 미지의 필드를 붙였다", "mini",
        lambda d: _set(d["transcript"], x_unknown_root=1),
        [("E_SCHEMA", "transcript/x_unknown_root")],
        keep=_LAYERS[2][1],
        fixture="K-82",
    )
    mutate(
        "IM-150", "AdapterCapabilityReport root에 미지의 필드를 붙였다", "mini",
        lambda d: _set(d["transcript"]["capability_report"], x_unknown_root=1),
        [("E_SCHEMA", "transcript/capability_report/x_unknown_root")],
        keep=_LAYERS[2][1],
        fixture="K-83",
    )
    mutate(
        "IM-151", "TranslatedTranscript root에 미지의 필드를 붙였다", "base",
        lambda d: _set(d["translated_transcript"], x_unknown_root=1),
        [("E_SCHEMA", "translated_transcript/x_unknown_root")],
        keep=_LAYERS[1][1],
        fixture="K-84",
    )
    mutate(
        "IM-152", "SubtitleDocument root에 미지의 필드를 붙였다", "base",
        lambda d: _set(d["subtitle_document"], x_unknown_root=1),
        [("E_SCHEMA", "subtitle_document/x_unknown_root")],
        keep=_LAYERS[0][1],
        fixture="K-85",
    )

    # --- REVIEW-023 B-03: coverage guard가 비어 있다고 지목한 방어면 ------------------
    # 아래 반례가 없으면 해당 분기는 한 번도 발화하지 않는다. mutant 표본이 아니라
    # `run_defense_coverage`가 기계적으로 찾아낸 목록이다.
    mutate(
        "IM-153", "other reason 없이 review_extension_id를 썼다", "base",
        lambda d: _set(tr(d, "tr-2"), review_extension_id="x-foo"),
        [("E_SCHEMA", f"{T0}/1/review_extension_id")],
        keep=_LAYERS[2][1],
        fixture="K-86",
    )
    mutate(
        "IM-154", "값 없이 speaker_confidence_semantics만 남겼다", "base",
        lambda d: _set(sp(d, "sp-1"), speaker_confidence_semantics="model_score"),
        [("E_CONFIDENCE", f"{S}/0/speaker_confidence_semantics")],
        keep=_LAYERS[3][1],
        fixture="K-87",
    )
    mutate(
        "IM-155", "speaker_label 없이 speaker_label_source만 남겼다", "base",
        lambda d: tr(d, "tr-1").pop("speaker_label"),
        [("E_SCHEMA", f"{T0}/0/speaker_label_source")],
        keep=_LAYERS[2][1],
        fixture="K-88",
    )
    mutate(
        "IM-156", "token 시간이 역전됐다", "base",
        lambda d: _set(tr(d, "tr-1")["tokens"][1], start_seconds=1.4, end_seconds=0.9),
        [("E_TIME_RANGE", f"{T0}/0/tokens/1/end_seconds")],
        keep=_LAYERS[2][1],
        fixture="K-89",
    )
    mutate(
        "IM-157", "token 시작이 ASR segment 범위보다 앞이다", "base",
        lambda d: _set(
            tr(d, "tr-2"),
            tokens=[{"text": "Hello", "start_seconds": 2.0, "end_seconds": 3.5}],
        ),
        [("E_TIME_RANGE", f"{T0}/1/tokens/0/start_seconds")],
        keep=_LAYERS[2][1],
        fixture="K-90",
    )
    mutate(
        "IM-158", "token_confidence_semantics=none인데 token confidence가 있다", "base",
        lambda d: _set(asr_capability(d), token_confidence_semantics="none"),
        [
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/token_confidence"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/tokens/0/confidence"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/tokens/1/confidence"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/tokens/2/confidence"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-91",
    )
    mutate(
        "IM-159", "supports_language_id=false인데 LID 결과가 남아 있다", "base",
        lambda d: _set(asr_capability(d), supports_language_id=False),
        [
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/language_id"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/dominant_language"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/language_spans"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/1/language_spans"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/2/dominant_language"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/2/language_spans"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/3/dominant_language"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/3/language_spans"),
            ("E_CAPABILITY_MISMATCH", f"{T1}/0/language_spans"),
            ("E_CAPABILITY_MISMATCH", f"{T1}/1/dominant_language"),
            ("E_CAPABILITY_MISMATCH", f"{T1}/1/language_spans"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-92",
    )
    mutate(
        "IM-160", "language_confidence_semantics=none인데 span confidence가 있다", "base",
        lambda d: _set(asr_capability(d), language_confidence_semantics="none"),
        [
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/language_confidence"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/language_spans/0/confidence"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-93",
    )
    mutate(
        "IM-161", "번역 문서만 있고 원문 Transcript가 문서 집합에 없다", "base",
        lambda d: None,
        [("E_SOURCE_REF", "translated_transcript/source_transcript")],
        keep=("speech_segments", "translated_transcript"),
        sentinel_keep=_LAYERS[1][1],
        fixture="K-94",
    )
    mutate(
        "IM-162", "번역 stream이 원문에 없는 stream을 주장했다", "base",
        lambda d: _set(d["translated_transcript"]["streams"][0], stream_id="s-ghost"),
        [
            ("E_SOURCE_REF", "translated_transcript/streams/0/stream_id"),
            ("E_STREAM_REF", f"{L0}/0/source_fragments/0/source_segment_id"),
            ("E_STREAM_REF", f"{L0}/1/source_fragments/0/source_segment_id"),
            ("E_STREAM_REF", f"{L0}/2/source_fragments/0/source_segment_id"),
            ("E_STREAM_REF", f"{L0}/3/source_fragments/0/source_segment_id"),
            ("E_STREAM_REF", f"{L0}/3/source_fragments/1/source_segment_id"),
        ],
        keep=_LAYERS[1][1],
        fixture="K-95",
    )
    mutate(
        "IM-163", "번역 source fragment가 빈 scalar 범위다", "base",
        lambda d: _set(tl(d, "tl-1")["source_fragments"][0], char_start=2, char_end=2),
        [
            ("E_ALIGNMENT", f"{L0}/0/alignment_kind"),
            ("E_OFFSET_RANGE", f"{L0}/0/source_fragments/0/char_end"),
            ("E_SOURCE_COVERAGE", f"{T0}/0/text"),
        ],
        keep=_LAYERS[1][1],
        fixture="K-96",
    )
    mutate(
        "IM-164", "번역 source fragment가 없는 Transcript segment를 참조했다", "base",
        lambda d: _set(tl(d, "tl-1")["source_fragments"][0], source_segment_id="tr-ghost"),
        [
            ("E_ALIGNMENT", f"{L0}/0/alignment_kind"),
            ("E_SOURCE_COVERAGE", f"{T0}/0/text"),
            ("E_SOURCE_REF", f"{L0}/0/source_fragments/0/source_segment_id"),
        ],
        keep=_LAYERS[1][1],
        fixture="K-97",
    )
    mutate(
        "IM-165", "target 축 자막인데 TranslatedTranscript가 문서 집합에 없다", "base",
        lambda d: None,
        [("E_TEXT_AXIS", "subtitle_document/text_axis")],
        keep=("speech_segments", "transcript", "subtitle_document"),
        sentinel_keep=_LAYERS[0][1],
        fixture="K-98",
    )
    mutate(
        "IM-166", "source 축 자막인데 Transcript가 문서 집합에 없다", "mini",
        lambda d: None,
        [("E_TEXT_AXIS", "subtitle_document/text_axis")],
        keep=("speech_segments", "subtitle_document"),
        sentinel_keep=_LAYERS[0][1],
        fixture="K-99",
    )
    mutate(
        "IM-167", "cue lineage fragment가 빈 scalar 범위다", "base",
        lambda d: _set(cue(d, "cue-1")["lineage_fragments"][0], char_start=1, char_end=1),
        [
            ("E_LINEAGE", f"{L0}/0/target_text"),
            ("E_LINEAGE", f"{C}/0/lines/0"),
            ("E_OFFSET_RANGE", f"{C}/0/lineage_fragments/0/char_end"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-100",
    )
    mutate(
        "IM-168", "문서 집합에 알 수 없는 key가 들어왔다", "base",
        lambda d: d.update(x_bogus={}),
        [("E_SCHEMA", "x_bogus")],
        keep=("speech_segments", "x_bogus"),
        fixture="K-101",
    )
    mutate(
        "IM-169", "speech_segments가 배열이 아니다", "base",
        lambda d: d.update(speech_segments={}),
        [("E_SCHEMA", "speech_segments")],
        keep=("speech_segments",),
        fixture="K-102",
    )
    mutate(
        "IM-170", "transcript가 객체가 아니다", "base",
        lambda d: d.update(transcript=[]),
        [("E_SCHEMA", "transcript")],
        keep=("speech_segments", "transcript"),
        fixture="K-103",
    )
    mutate(
        "IM-171", "uncovered fragment가 없는 Transcript segment를 참조했다", "partial",
        lambda d: d["translated_transcript"]["uncovered_source_fragments"][0].update(
            source_segment_id="tr-ghost"
        ),
        [
            ("E_SOURCE_COVERAGE", f"{T0}/1/text"),
            ("E_SOURCE_REF", "translated_transcript/uncovered_source_fragments/0/source_segment_id"),
        ],
        keep=_LAYERS[1][1],
        fixture="K-104",
    )


# ---------------------------------------------------------------------------
# schema / validator code mutant 목록 — 저장소 밖 임시 사본에서만 적용한다
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceMutant:
    mutant_id: str
    title: str
    target: str
    old: str
    new: str
    kills: tuple[str, ...] = field(default_factory=tuple)


def _validator_source() -> str:
    return (REPO_ROOT / VALIDATOR_PATH).read_text(encoding="utf-8")


def _call_text(source: str, func_name: str, marker: str) -> str:
    """`func_name(...)` 호출 중 `marker`를 담은 것 하나의 **전체 소스**를 돌려준다.

    같은 helper를 여러 곳에서 부를 때 호출 지점별 mutant를 만들기 위한 것이다.
    """

    needle = f"{func_name}("
    start = 0
    while True:
        start = source.index(needle, start)
        depth, index = 0, start + len(needle) - 1
        while True:
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        call = source[start : index + 1]
        if marker in call:
            return call
        start = index + 1


def _call_site_mutants(
    entries: Sequence[tuple[str, str, str, str, tuple[str, ...]]]
) -> list[SourceMutant]:
    """`(mutant_id, title, func_name, marker, kills)` 목록을 호출 무력화 mutant로 만든다.

    같은 helper의 호출 지점마다 독립 mutant를 두어야 어느 계층의 유일성 검사가 실제로
    살아 있는지 증명된다 (REVIEW-023 B-03).
    """

    source = _validator_source()
    return [
        SourceMutant(
            mutant_id, title, VALIDATOR_PATH, _call_text(source, func_name, marker), "None", kills
        )
        for mutant_id, title, func_name, marker, kills in entries
    ]


def schema_mutants() -> list[SourceMutant]:
    """production schema의 방어를 하나씩 약화한다. `kills`는 그때 놓치게 되는 case다."""

    sub = "schemas/subtitle-document-v1.schema.json"
    txt = "schemas/transcript-v1.schema.json"
    cap = "schemas/adapter-capability-report-v1.schema.json"
    seg = "schemas/speech-segment-v1.schema.json"
    mt = "schemas/translated-transcript-v1.schema.json"
    return [
        SourceMutant(
            "SM-01", "SubtitleDocument root required에서 resolved_style을 뺐다", sub,
            '    "resolved_style",\n    "unsupported_features",',
            '    "unsupported_features",',
            ("K-50",),
        ),
        SourceMutant(
            "SM-02", "ResolvedStyle required에서 max_cps를 뺐다", sub,
            '        "max_cps",\n        "min_duration_seconds",',
            '        "min_duration_seconds",',
            ("K-51",),
        ),
        SourceMutant(
            "SM-03", "ResolvedStyle.max_cps의 exclusiveMinimum을 없앴다", sub,
            '      ],\n      "properties": {\n        "max_chars_per_line": { "type": "integer", "minimum": 1 },\n        "max_lines": { "type": "integer", "minimum": 1 },\n        "max_cps": { "type": "number", "exclusiveMinimum": 0 },',
            '      ],\n      "properties": {\n        "max_chars_per_line": { "type": "integer", "minimum": 1 },\n        "max_lines": { "type": "integer", "minimum": 1 },\n        "max_cps": { "type": "number" },',
            ("IM-99",),
        ),
        SourceMutant(
            "SM-04", "Cue를 닫힌 객체에서 열린 객체로 바꿨다", sub,
            '    "Cue": {\n      "type": "object",\n      "additionalProperties": false,',
            '    "Cue": {\n      "type": "object",\n      "additionalProperties": true,',
            ("IM-95",),
        ),
        SourceMutant(
            "SM-05", "unsupported feature의 feature_kind enum을 넓혔다", sub,
            '            "vertical_text",\n            "other"',
            '            "vertical_text",\n            "glow",\n            "other"',
            ("IM-109",),
        ),
        SourceMutant(
            "SM-06", "review_extension_id의 x- pattern을 없앴다", txt,
            '      "maxLength": 128,\n      "pattern": "^x-[A-Za-z0-9][A-Za-z0-9._:-]*$"',
            '      "maxLength": 128',
            ("IM-104",),
        ),
        SourceMutant(
            "SM-07", "Transcript Segment required에서 needs_review를 뺐다", txt,
            '        "is_low_confidence",\n        "needs_review",\n        "review_reasons"',
            '        "is_low_confidence",\n        "review_reasons"',
            ("IM-106",),
        ),
        SourceMutant(
            "SM-08", "language span char_start의 minimum을 없앴다", txt,
            '        "char_start": { "type": "integer", "minimum": 0 },\n        "char_end": { "type": "integer", "minimum": 0 },\n        "language"',
            '        "char_start": { "type": "integer" },\n        "char_end": { "type": "integer", "minimum": 0 },\n        "language"',
            ("IM-19",),
        ),
        SourceMutant(
            "SM-09", "feature_status를 닫힌 객체에서 열린 객체로 바꿨다", txt,
            '      "type": "object",\n      "additionalProperties": false,\n      "required": [\n        "token_timing",',
            '      "type": "object",\n      "additionalProperties": true,\n      "required": [\n        "token_timing",',
            ("IM-43",),
        ),
        SourceMutant(
            "SM-10", "language_tag의 구조 pattern을 없앴다", cap,
            '      "maxLength": 64,\n      "pattern": "^[a-z]{2,8}(-[A-Za-z0-9]{1,8})*$"',
            '      "maxLength": 64',
            ("IM-20",),
        ),
        SourceMutant(
            "SM-11", "capability report required에서 determinism_tier를 뺐다", cap,
            '    "determinism_tier",\n    "limitations"',
            '    "limitations"',
            ("IM-42",),
        ),
        SourceMutant(
            "SM-12", "SpeechSegment.overlap_kind enum을 넓혔다", seg,
            '      "enum": ["none", "partial", "full", "unknown"]',
            '      "enum": ["none", "partial", "full", "unknown", "sideways"]',
            ("IM-54",),
        ),
        SourceMutant(
            "SM-13", "concurrent_stream_ids의 uniqueItems를 없앴다", seg,
            '      "type": "array",\n      "uniqueItems": true,\n      "items": { "$ref": "common-v1.schema.json#/$defs/identifier" }\n    },\n    "overlap_kind"',
            '      "type": "array",\n      "items": { "$ref": "common-v1.schema.json#/$defs/identifier" }\n    },\n    "overlap_kind"',
            ("IM-53",),
        ),
        SourceMutant(
            "SM-14", "TranslationCapabilityReport를 열린 객체로 바꿨다", mt,
            '    "TranslationCapabilityReport": {\n      "description": "ARCHITECTURE.md §7.11 번역 어댑터 능력 보고의 유일한 정본 정의 (TASK-029 §3·§4.4). 닫힌 field set이며 다른 schema나 Python 상수가 이 enum·필드 집합을 복제하지 않는다.",\n      "type": "object",\n      "additionalProperties": false,',
            '    "TranslationCapabilityReport": {\n      "description": "ARCHITECTURE.md §7.11 번역 어댑터 능력 보고의 유일한 정본 정의 (TASK-029 §3·§4.4). 닫힌 field set이며 다른 schema나 Python 상수가 이 enum·필드 집합을 복제하지 않는다.",\n      "type": "object",\n      "additionalProperties": true,',
            ("IM-47",),
        ),
        SourceMutant(
            "SM-15", "source_fragments의 minItems 1을 없앴다", mt,
            '          "type": "array",\n          "minItems": 1,\n          "items": { "$ref": "#/$defs/SourceFragment" }',
            '          "type": "array",\n          "items": { "$ref": "#/$defs/SourceFragment" }',
            ("IM-64",),
        ),
        SourceMutant(
            "SM-17", "UncoveredFragment.review_reasons의 minItems 1을 없앴다", mt,
            '          "type": "array",\n          "minItems": 1,\n          "uniqueItems": true,\n          "items": { "$ref": "#/$defs/review_reason" }',
            '          "type": "array",\n          "uniqueItems": true,\n          "items": { "$ref": "#/$defs/review_reason" }',
            ("IM-110",),
        ),
        SourceMutant(
            "SM-16", "alignment_kind enum을 넓혔다", mt,
            '          "enum": ["one_to_one", "merged", "split", "dropped", "unknown"]',
            '          "enum": ["one_to_one", "merged", "split", "dropped", "unknown", "paraphrase"]',
            ("IM-79",),
        ),
    ] + [
        # root 닫힌 객체 방어 — 다섯 schema 전부 (REVIEW-023 B-03).
        SourceMutant(
            mutant_id, f"{name} root의 additionalProperties false를 없앴다", path,
            '  "type": "object",\n  "additionalProperties": false,',
            '  "type": "object",',
            (kill,),
        )
        for mutant_id, name, path, kill in (
            ("SM-18", "SpeechSegment", seg, "IM-148"),
            ("SM-19", "Transcript", txt, "IM-149"),
            ("SM-20", "AdapterCapabilityReport", cap, "IM-150"),
            ("SM-21", "TranslatedTranscript", mt, "IM-151"),
            ("SM-22", "SubtitleDocument", sub, "IM-152"),
        )
    ]


def validator_mutants() -> list[SourceMutant]:
    """domain validator의 핵심 분기를 하나씩 무력화한다."""

    target = VALIDATOR_PATH
    return [
        SourceMutant(
            "VM-01", "lone surrogate 검사 제거", target,
            "    if _has_surrogate(value):", "    if False:", ("IM-22", "IM-23"),
        ),
        SourceMutant(
            "VM-02", "positive duration 검사 제거", target,
            "    if float(end) <= float(start):", "    if False:", ("IM-24", "IM-25"),
        ),
        SourceMutant(
            "VM-03", "calibrated_probability 범위 검사 제거", target,
            '    if semantics == "calibrated_probability" and not (0.0 <= float(value) <= 1.0):',
            "    if False:", ("IM-52",),
        ),
        SourceMutant(
            "VM-04", "needs_review ↔ review_reasons 동치 검사 제거", target,
            "    if needs != bool(reasons):", "    if False:", ("IM-101", "IM-102"),
        ),
        SourceMutant(
            "VM-05", "is_low_confidence ↔ low_confidence reason 결박 제거", target,
            '    if node.get("is_low_confidence") is True and "low_confidence" not in (reasons or []):',
            "    if False:", ("IM-105",),
        ),
        SourceMutant(
            "VM-06", "other 확장 ID 요구 제거", target,
            '    if "other" in reasons:', "    if False:", ("IM-103",),
        ),
        SourceMutant(
            "VM-07", 'language tag 자리의 "unknown" 거부 제거', target,
            "        if tag == FORBIDDEN_LANGUAGE_TAG:", "        if False:", ("IM-41",),
        ),
        SourceMutant(
            "VM-08", "partition gap 검사 제거", target,
            "        if item.start > cursor:", "        if False:",
            ("IM-65", "IM-68", "IM-92"),
        ),
        SourceMutant(
            "VM-09", "partition 중복·겹침 검사 제거", target,
            "        elif item.start < cursor:", "        elif False:",
            ("IM-66", "IM-69", "IM-70", "IM-94"),
        ),
        SourceMutant(
            "VM-10", "partition 꼬리 gap 검사 제거", target,
            "    if cursor < text_length:", "    if False:", ("IM-111",),
        ),
        SourceMutant(
            "VM-11", "appearance order 검사 제거", target,
            "            if current.start < previous.start:", "            if False:",
            ("IM-90",),
        ),
        SourceMutant(
            "VM-12", "SpeechSegment ID 유일성 판정 자체 제거", target,
            "    seen: set[str] = set()\n    for identifier, location in entries:",
            "    seen: set[str] = set()\n    for identifier, location in []:", ("IM-113",),
        ),
        SourceMutant(
            "VM-13", "separation_method=channel의 channel_semantics 결박 제거", target,
            '        if semantics != "independent":', "        if False:", ("IM-48",),
        ),
        SourceMutant(
            "VM-14", "separation_method=channel의 source_channel_index 요구 제거", target,
            "        if not has_channel:", "        if False:", ("IM-49",),
        ),
        SourceMutant(
            "VM-15", "separation_method=none의 speaker_label 금지 제거", target,
            '    if method == "none" and "speaker_label" in segment:', "    if False:",
            ("IM-50",),
        ),
        SourceMutant(
            "VM-16", "confidence ↔ semantics 동반 요구 제거", target,
            "        if has_value and not has_semantics:", "        if False:", ("IM-51",),
        ),
        SourceMutant(
            "VM-17", "concurrent stream self 참조 검사 제거", target,
            "            if other == stream_id:", "            if False:", ("IM-55",),
        ),
        # 존재·겹침·대칭 세 분기는 서로를 가린다 (하나를 지우면 나머지가 같은 code·location으로
        # 잡는다). 그래서 개별 mutant가 아니라 **한 번에 무력화하는 하나의 mutant**로 감사한다.
        SourceMutant(
            "VM-18", "concurrent stream 참조 검사(존재·겹침·대칭)를 한꺼번에 제거", target,
            "        for position, other in enumerate(concurrent):",
            "        for position, other in []:",
            ("IM-55", "IM-56", "IM-57", "IM-58"),
        ),
        SourceMutant(
            "VM-21", "speaker_label ↔ speaker_label_source 동반 요구 제거", target,
            "    if has_label and not has_source:", "    if False:", ("IM-114",),
        ),
        SourceMutant(
            "VM-22", "SpeechSegment 참조 존재 검사 제거", target,
            '                findings.append(\n                    _finding(\n                        f"{where}/source_speech_segment_ids/{position}",\n                        "E_SOURCE_REF",\n                        "존재하지 않는 SpeechSegment를 참조했다",\n                    )\n                )\n                continue',
            "                continue", ("IM-59",),
        ),
        SourceMutant(
            "VM-23", "단일 stream lineage 검사 제거", target,
            "        if len(streams) > 1:", "        if False:", ("IM-60",),
        ),
        SourceMutant(
            "VM-24", "ASR segment 시작의 합집합 포함 검사 제거", target,
            """        findings.append(
            _finding(
                f"{where}/start_seconds",
                "E_TIME_RANGE",
                "ASR segment 시작이 참조한 입력 SpeechSegment 범위의 합집합 밖이다",
            )
        )
        return findings""",
            "        return findings", ("IM-115",),
        ),
        SourceMutant(
            "VM-25", "ASR segment 구간의 내부 빈틈 검사 제거", target,
            "    if end > holder[1]:", "    if False:",
            ("IM-27",),
        ),
        SourceMutant(
            "VM-26", "token start/end 동반 요구 제거", target,
            '        if has_start != has_end:\n            findings.append(\n                _finding(\n                    spot,\n                    "E_TIME_RANGE",\n                    "token의 start_seconds와 end_seconds는 둘 다 있거나 둘 다 없어야 한다",\n                )\n            )',
            "        if has_start != has_end:\n            pass", ("IM-30",),
        ),
        SourceMutant(
            "VM-27", "token 시간순 검사 제거", target,
            "                if previous is not None and (start < previous[0] or end < previous[1]):",
            "                if False:", ("IM-29",),
        ),
        SourceMutant(
            "VM-28", "token이 segment 범위를 넘는지 검사 제거", target,
            "                    if end > upper:", "                    if False:", ("IM-28",),
        ),
        SourceMutant(
            "VM-29", "language span 빈/역전 범위 검사 제거", target,
            "        if ok and end <= start:", "        if ok and False:", ("IM-116",),
        ),
        SourceMutant(
            "VM-30", "language span의 text 길이 초과 검사 제거", target,
            "        if ok and text is not None and end > len(text):", "        if ok and False:",
            ("IM-09",),
        ),
        SourceMutant(
            "VM-31", "language span 순서·비중첩 검사 제거", target,
            "        if ok and index > 0 and start < previous_end:", "        if ok and False:",
            ("IM-10",),
        ),
        SourceMutant(
            "VM-32", "첫 span의 switch_kind 금지 검사 제거", target,
            '        if index == 0 and "switch_kind" in span:', "        if False:", ("IM-16",),
        ),
        SourceMutant(
            "VM-33", "이후 span의 switch_kind 필수 검사 제거", target,
            '        if index > 0 and "switch_kind" not in span:', "        if False:", ("IM-17",),
        ),
        SourceMutant(
            "VM-34", "intra-sentential LID capability 결박 제거", target,
            '        if span.get("switch_kind") == "intra_sentential" and not supports_intra:',
            "        if False:", ("IM-18",),
        ),
        SourceMutant(
            "VM-35", "gap·und의 unknown review 요구 제거", target,
            '        if segment.get("needs_review") is not True or "language_unknown" not in reasons:',
            "        if False:", ("IM-11", "IM-12"),
        ),
        SourceMutant(
            "VM-36", "gap·und일 때 dominant_language 금지 제거", target,
            "        if has_dominant:\n            findings.append(\n                _finding(\n                    f\"{where}/dominant_language\",\n                    \"E_LANGUAGE_GAP_REVIEW\",\n                    \"gap 또는 und 범위가 있으면 dominant_language를 생략한다\",",
            "        if False:\n            findings.append(\n                _finding(\n                    f\"{where}/dominant_language\",\n                    \"E_LANGUAGE_GAP_REVIEW\",\n                    \"gap 또는 und 범위가 있으면 dominant_language를 생략한다\",",
            ("IM-13", "IM-14"),
        ),
        SourceMutant(
            "VM-37", "dominant_language 파생 규칙 검사 제거", target,
            '        if segment.get("dominant_language") != expected:', "        if False:",
            ("IM-15",),
        ),
        SourceMutant(
            "VM-38", "supports_language_id=false의 spans 금지 제거", target,
            "        if isinstance(spans, list) and spans:", "        if False:", ("IM-33",),
        ),
        SourceMutant(
            "VM-39", "supports_word_timing 내부 결박 제거", target,
            '    if capability.get("supports_word_timing") is not ("word" in units):',
            "    if False:", ("IM-38",),
        ),
        SourceMutant(
            "VM-40", "max_candidate_languages 결박 제거", target,
            '    if "max_candidate_languages" in capability and capability.get("restricts_candidate_languages") is not True:',
            "    if False:", ("IM-40",),
        ),
        SourceMutant(
            "VM-41", "token_unit ↔ token_timing_units 결박 제거", target,
            '    if evidence["token_timing"] and units and token_unit not in units:',
            "    if False:", ("IM-39",),
        ),
        SourceMutant(
            "VM-42", "capability 미지원 축의 unsupported 요구 제거", target,
            '        if not supported[key] and status != "unsupported":', "        if False:", ("IM-121",),
        ),
        SourceMutant(
            "VM-43", "capability 지원 축의 unsupported 금지 제거", target,
            '        if supported[key] and status == "unsupported":', "        if False:",
            ("IM-112",),
        ),
        SourceMutant(
            "VM-44", "produced인데 결과가 없는 경우 검사 제거", target,
            '        if status == "produced" and not evidence[key]:', "        if False:",
            ("IM-35", "IM-46"),
        ),
        SourceMutant(
            "VM-45", "produced가 아닌데 결과가 있는 경우 검사 제거", target,
            '        if status != "produced" and evidence[key]:', "        if False:",
            ("IM-31", "IM-32", "IM-34", "IM-45"),
        ),
        SourceMutant(
            "VM-46", "target_language exact-ko 검사 제거", target,
            '    if document.get("target_language") != TARGET_LANGUAGE:', "    if False:",
            ("IM-07",),
        ),
        SourceMutant(
            "VM-47", "capability snapshot의 ko 지원 검사 제거", target,
            "    if not isinstance(targets, list) or TARGET_LANGUAGE not in targets:",
            "    if False:", ("IM-08",),
        ),
        SourceMutant(
            "VM-48", "번역 timebase 일치 검사 제거", target,
            '    if document.get("timebase_ref") != transcript.get("timebase_ref"):',
            "    if False:", ("IM-117",),
        ),
        SourceMutant(
            "VM-49", "source fragment의 exact substring 검사 제거", target,
            "    if stored != text[start:end]:\n        findings.append(\n            _finding(\n                f\"{spot}/source_text\",",
            "    if False:\n        findings.append(\n            _finding(\n                f\"{spot}/source_text\",",
            ("IM-63",),
        ),
        SourceMutant(
            "VM-50", "source fragment 범위 초과 검사 제거", target,
            "    if end > len(text):\n        findings.append(\n            _finding(f\"{spot}/char_end\", \"E_OFFSET_RANGE\", \"scalar 범위가 원문 text 길이를 넘는다\")\n        )\n        return None",
            "    if False:\n        findings.append(\n            _finding(f\"{spot}/char_end\", \"E_OFFSET_RANGE\", \"scalar 범위가 원문 text 길이를 넘는다\")\n        )\n        return None",
            ("IM-118",),
        ),
        SourceMutant(
            "VM-51", "one_to_one 전체 범위 요구 제거", target,
            "        if not whole:", "        if False:", ("IM-74", "IM-75"),
        ),
        SourceMutant(
            "VM-52", "merged cardinality 검사 제거", target,
            "        if len(resolved) < 2 or len(distinct) < 2:", "        if False:",
            ("IM-73",),
        ),
        SourceMutant(
            "VM-53", "split strict subrange 검사 제거", target,
            "        if not strict:", "        if False:", ("IM-76",),
        ),
        SourceMutant(
            "VM-54", "dropped의 빈 target_text 요구 제거", target,
            '        if target != "":', "        if False:", ("IM-77",),
        ),
        SourceMutant(
            "VM-55", "dropped의 untranslated_span reason 요구 제거", target,
            '        if "untranslated_span" not in reasons:', "        if False:", ("IM-78",),
        ),
        SourceMutant(
            "VM-56", "비-dropped의 빈 target_text 금지 제거", target,
            '    if kind != "dropped" and target == "":', "    if False:", ("IM-120",),
        ),
        SourceMutant(
            "VM-58", "complete ↔ uncovered 비어 있음 동치 검사 제거", target,
            '    if status == "complete" and uncovered:', "    if False:", ("IM-71",),
        ),
        SourceMutant(
            "VM-59", "partial ↔ uncovered 존재 동치 검사 제거", target,
            '    if status == "partial" and not uncovered:', "    if False:", ("IM-67",),
        ),
        SourceMutant(
            "VM-60", "target axis의 source_transcript_ref 요구 제거", target,
            '        if "source_transcript_ref" not in document:', "        if False:", ("IM-06",),
        ),
        SourceMutant(
            "VM-61", "target axis의 target_language 요구 제거", target,
            "        if not has_target_language:", "        if False:", ("IM-04",),
        ),
        SourceMutant(
            "VM-62", "target 자막 문서의 exact-ko 검사 제거", target,
            '        elif document.get("target_language") != TARGET_LANGUAGE:', "        elif False:",
            ("IM-05",),
        ),
        SourceMutant(
            "VM-63", "source axis의 target_language 금지 제거", target,
            "        if has_target_language:", "        if False:", ("IM-01",),
        ),
        SourceMutant(
            "VM-64", "source axis의 source_transcript_ref 금지 제거", target,
            '        if "source_transcript_ref" in document:', "        if False:", ("IM-02",),
        ),
        SourceMutant(
            "VM-65", "resolved_style의 max>min 검사 제거", target,
            "        if not (_finite(low) and _finite(high) and float(high) <= float(low)):\n            return",
            "        if True:\n            return", ("IM-96", "IM-98"),
        ),
        SourceMutant(
            "VM-66", "cue canonical order 검사 제거", target,
            "        if current_key < previous_key:", "        if False:", ("IM-80",),
        ),
        SourceMutant(
            "VM-67", "같은 stream cue 겹침 검사 제거", target,
            "            if current[2] == other[2] and _overlaps(current[3], current[4], other[3], other[4]):",
            "            if False:", ("IM-81",),
        ),
        SourceMutant(
            "VM-68", "overlap_kind=none의 concurrent cue 금지 제거", target,
            '        if cue.get("overlap_kind") == "none" and concurrent:', "        if False:",
            ("IM-84",),
        ),
        SourceMutant(
            "VM-69", "concurrent cue self 참조 검사 제거", target,
            "            if other_id == cue_id:", "            if False:", ("IM-82",),
        ),
        SourceMutant(
            "VM-70", "concurrent cue 존재 검사 제거", target,
            '            if other is None:\n                findings.append(_finding(spot, "E_CUE_REF", "존재하지 않는 cue를 참조했다"))\n                continue',
            "            if other is None:\n                continue", ("IM-83",),
        ),
        # 겹침·대칭 두 분기도 서로를 가리므로 한 mutant로 함께 무력화한다.
        SourceMutant(
            "VM-71", "concurrent cue 겹침·대칭 검사를 한꺼번에 제거", target,
            '            if not _overlaps(start, end, other[3], other[4]):\n                findings.append(\n                    _finding(spot, "E_CUE_REF", "선언한 concurrent cue와 실제 시간이 겹치지 않는다")\n                )\n                continue\n            if cue_id not in other[5]:\n                findings.append(\n                    _finding(spot, "E_CUE_REF", "concurrent cue 참조가 상호 대칭이 아니다")\n                )',
            "            continue",
            ("IM-84", "IM-85"),
        ),
        SourceMutant(
            "VM-73", "unsupported feature의 cue 존재 검사 제거", target,
            '        if record.get("cue_id") not in known:', "        if False:", ("IM-107",),
        ),
        SourceMutant(
            "VM-74", "other feature의 x- 확장 ID 요구 제거", target,
            "        if needs_extension and not (isinstance(identifier, str) and identifier.startswith(\"x-\")):",
            "        if False:", ("IM-108",),
        ),
        SourceMutant(
            "VM-75", "cue line_index 범위 검사 제거", target,
            "            if not isinstance(line_index, int) or isinstance(line_index, bool) or not 0 <= line_index < len(lines):",
            "            if False:", ("IM-86",),
        ),
        SourceMutant(
            "VM-76", "line 결합 ↔ lines[line_index] 동치 검사 제거", target,
            "            if joined != line:", "            if False:", ("IM-88",),
        ),
        SourceMutant(
            "VM-77", "line_break_whitespace 허용 집합 검사 제거", target,
            "            if isinstance(moved, str) and any(char not in ALLOWED_LINE_BREAK_SCALARS for char in moved):",
            "            if False:", ("IM-89",),
        ),
        SourceMutant(
            "VM-78", "after_line_index 검사 제거", target,
            "            if not isinstance(after, int) or isinstance(after, bool) or not 0 <= after < max(len(lines) - 1, 0):",
            "            if False:", ("IM-119",),
        ),
        SourceMutant(
            "VM-79", "반대 축 segment 참조의 E_TEXT_AXIS 판정 제거", target,
            "        if isinstance(segment_id, str) and segment_id in other:", "        if False:",
            ("IM-03",),
        ),
        SourceMutant(
            "VM-80", "cue lineage fragment의 exact substring 검사 제거", target,
            "    if stored != text[start:end]:\n        findings.append(\n            _finding(\n                f\"{spot}/{field}\",",
            "    if False:\n        findings.append(\n            _finding(\n                f\"{spot}/{field}\",",
            ("IM-21", "IM-87", "IM-91"),
        ),
        SourceMutant(
            "VM-81", "cue lineage 범위 초과 검사 제거", target,
            "    if end > len(text):\n        findings.append(\n            _finding(f\"{spot}/char_end\", \"E_OFFSET_RANGE\", \"scalar 범위가 입력 text 길이를 넘는다\")\n        )\n        return None",
            "    if False:\n        findings.append(\n            _finding(f\"{spot}/char_end\", \"E_OFFSET_RANGE\", \"scalar 범위가 입력 text 길이를 넘는다\")\n        )\n        return None",
            ("IM-93",),
        ),
        SourceMutant(
            "VM-82", "schema 검사 실패 문서의 의미 검사 건너뛰기 제거", target,
            "            schema_failed.add(key)", "            pass", ("IM-64",),
        ),
        # --- REVIEW-023 B-03이 요구한 의미 방어면 mutant ---------------------------
        SourceMutant(
            "VM-83", "ASR 구간의 내부-gap 검증 제거 (끝점만 확인)", target,
            "    if end > holder[1]:", "    if False:", ("IM-122", "IM-123"),
        ),
        SourceMutant(
            "VM-84", "Transcript timebase 결박 제거", target,
            '    if source_timebase is not None and transcript.get("timebase_ref") != source_timebase:',
            "    if False:", ("IM-124",),
        ),
        SourceMutant(
            "VM-85", "SubtitleDocument timebase 결박 제거", target,
            '    if expected_timebase is not None and document.get("timebase_ref") != expected_timebase:',
            "    if False:", ("IM-126",),
        ),
        SourceMutant(
            "VM-86", "SpeechSegment 단일 timebase 검사 제거", target,
            "        elif timebase != baseline:", "        elif False:", ("IM-127",),
        ),
        SourceMutant(
            "VM-87", "ASR segment의 stream 결박 제거", target,
            "        elif streams and isinstance(stream_id, str) and stream_id not in streams:",
            "        elif False:", ("IM-128",),
        ),
        SourceMutant(
            "VM-88", "번역 fragment의 stream 결박 제거", target,
            "            if segment.stream_id and source.stream_id and segment.stream_id != source.stream_id:",
            "            if False:", ("IM-129",),
        ),
        SourceMutant(
            "VM-89", "cue의 stream 결박 제거", target,
            "    if isinstance(cue_stream, str) and entry.stream_id and cue_stream != entry.stream_id:",
            "    if False:", ("IM-130",),
        ),
        SourceMutant(
            "VM-90", "ID 유일성 helper의 중복 판정 제거", target,
            "        if identifier in seen:", "        if False:",
            ("IM-113", "IM-131", "IM-132", "IM-133", "IM-134", "IM-135"),
        ),
        SourceMutant(
            "VM-91", "source fragment의 원문 순서 검사 제거 (merged 순서 포함)", target,
            "            if previous_key is not None and (\n                current_key[0] < previous_key[0]\n                or (current_key[0] == previous_key[0] and start < previous_key[1])\n            ):",
            "            if False:", ("IM-136",),
        ),
        SourceMutant(
            "VM-92", "segment-level adapter speaker evidence 결박 제거", target,
            '    if label_source == "adapter" and capability.get("supports_diarization") is not True:',
            "    if False:", ("IM-34",),
        ),
        SourceMutant(
            "VM-93", "segment-level input speaker evidence 결박 제거", target,
            '    if label_source == "input" and not input_labels:', "    if False:", ("IM-144",),
        ),
        SourceMutant(
            "VM-94", "stream-level adapter speaker evidence 결박 제거", target,
            '        if stream.get("speaker_label_source") == "adapter" and capability.get(\n            "supports_diarization"\n        ) is not True:',
            "        if False:", ("IM-143",),
        ),
        SourceMutant(
            "VM-95", "capability snapshot ↔ provenance adapter identity 결박 제거", target,
            "        if capability[field] != provenance[field]:", "        if False:",
            ("IM-140", "IM-141", "IM-142"),
        ),
        SourceMutant(
            "VM-96", "language_spans 없는 dominant_language 금지 제거", target,
            '        if has_dominant and capability.get("supports_language_id") is True:',
            "        if False:", ("IM-146",),
        ),
        SourceMutant(
            "VM-97", "SpeechSegment의 overlap_kind=none 모순 검사 제거", target,
            '        if segment.get("overlap_kind") == "none" and segment.get("concurrent_stream_ids"):',
            "        if False:", ("IM-145",),
        ),
        SourceMutant(
            "VM-98", "schema finding message의 비식별화 제거 (실제 값 노출)", target,
            """    return [
        Finding(location=finding.location, code=finding.code,
                message=redact_schema_message(finding.message))
        for finding in findings
    ]""",
            "    return list(findings)", ("LEAK",),
        ),
    ] + _call_site_mutants(
        [
            ("VM-99", "SpeechSegment ID 유일성 검사 호출 제거", "_check_duplicate_ids",
             "SpeechSegment segment_id", ("IM-113",)),
            ("VM-100", "Transcript stream ID 유일성 검사 호출 제거", "_check_duplicate_ids",
             "Transcript stream_id", ("IM-131",)),
            ("VM-101", "Transcript segment ID 유일성 검사 호출 제거", "_check_duplicate_ids",
             "Transcript segment_id", ("IM-132",)),
            ("VM-102", "TranslatedTranscript stream ID 유일성 검사 호출 제거",
             "_check_duplicate_ids", "TranslatedTranscript stream_id", ("IM-133",)),
            ("VM-103", "TranslatedTranscript segment ID 유일성 검사 호출 제거",
             "_check_duplicate_ids", "TranslatedTranscript segment_id", ("IM-134",)),
            ("VM-104", "cue ID 유일성 검사 호출 제거", "_check_duplicate_ids",
             "SubtitleDocument cue_id", ("IM-135",)),
        ]
    )


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def _base_documents(fixture_dir: Path) -> dict[str, dict]:
    by_case: dict[str, dict] = {}
    for path in sorted(fixture_dir.glob("k-*.json")):
        fixture = load_fixture(path)
        by_case[str(fixture["case_id"])] = fixture["documents"]
    return {name: by_case[case_id] for name, case_id in BASE_CASES.items()}


def run_fixture_pass(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for outcome in run_fixtures(fixture_dir, schemas):
        fixture = load_fixture(outcome.path)
        row: dict[str, Any] = {
            "case_id": outcome.case_id,
            "passed": outcome.passed,
            "mismatches": list(outcome.mismatches),
        }
        if bool(fixture["expected"].get("valid")):
            # 정상 fixture는 그 자체가 valid-case sentinel이다 — 실제 결과를 센다.
            row["sentinel_ok"] = not validate_documents(fixture["documents"], schemas).findings
        rows.append(row)
    return rows


def run_input_mutations(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    register_mutations()
    sources = _base_documents(fixture_dir)
    results: list[dict[str, Any]] = []
    for mutation in MUTATIONS:
        documents = mutation.documents(sources)
        observed = tuple(sorted(validate_documents(documents, schemas).pairs))
        # valid-case sentinel — **변형하지 않은** 같은 문서 부분집합은 깨끗해야 한다.
        # 변형이 아니라 base나 keep 선택이 결함을 만든 경우를 여기서 잡는다.
        sentinel_documents = mutation.sentinel_documents(sources)
        sentinel_findings = validate_documents(sentinel_documents, schemas).pairs
        results.append(
            {
                "mutation_id": mutation.mutation_id,
                "title": mutation.title,
                "base": BASE_CASES[mutation.base],
                "expected": [list(pair) for pair in mutation.expected],
                "observed": [list(pair) for pair in observed],
                "passed": observed == mutation.expected,
                "sentinel_ok": not sentinel_findings,
            }
        )
    return results


# ---------------------------------------------------------------------------
# 민감 값 비노출 스캔 (REVIEW-023 B-02)
# ---------------------------------------------------------------------------

#: 원문·번역문·표시 텍스트가 담기는 key. 여기 값이 finding message에 나오면 누출이다.
_TEXT_KEYS = frozenset(
    {
        "text",
        "target_text",
        "source_text",
        "lines",
        "speaker_label",
        "review_extension_id",
        "note",
    }
)

#: 절대 경로가 message에 섞이지 않는지 본다.
_PATH_MARKERS = ("/home/", "/tmp/", str(REPO_ROOT), "\\Users\\")


def _text_values(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _TEXT_KEYS:
                if isinstance(value, str):
                    out.add(value)
                elif isinstance(value, list):
                    out.update(item for item in value if isinstance(item, str))
            _text_values(value, out)
    elif isinstance(node, list):
        for item in node:
            _text_values(item, out)


def _leak_hits(documents: Any, findings: Sequence[Any]) -> list[str]:
    """finding message에 원문/번역문/민감 값/절대 경로가 들어갔는지 본다.

    계약은 `(code, location)`이고 message는 사람용 설명이다. message에 입력 값을 그대로
    싣는 순간 로그·리포트가 원문 유출 경로가 된다 (REVIEW-023 B-02).
    """

    values: set[str] = set()
    _text_values(documents, values)
    # 세 scalar 미만은 조사·기호와 우연히 겹칠 수 있어 판정에서 뺀다.
    values = {value for value in values if len(value) >= 3}
    values.add(SENSITIVE_PROBE)

    hits: list[str] = []
    for finding in findings:
        leaked = next((value for value in values if value in finding.message), None)
        if leaked is not None:
            hits.append(f"{finding.code}@{finding.location}: 입력 텍스트 노출")
            continue
        if any(marker in finding.message for marker in _PATH_MARKERS):
            hits.append(f"{finding.code}@{finding.location}: 절대 경로 노출")
    return hits


def run_leak_scan(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    register_mutations()
    sources = _base_documents(fixture_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("k-*.json")):
        fixture = load_fixture(path)
        result = validate_documents(fixture["documents"], schemas)
        hits = _leak_hits(fixture["documents"], result.findings)
        row: dict[str, Any] = {
            "leak_id": str(fixture["case_id"]),
            "passed": not hits,
            "hits": hits[:4],
        }
        if bool(fixture["expected"].get("valid")):
            # 정상 fixture는 finding이 없어야 한다 — 스캔 자체의 valid-case sentinel.
            row["sentinel_ok"] = not result.findings
        rows.append(row)
    for mutation in MUTATIONS:
        documents = mutation.documents(sources)
        result = validate_documents(documents, schemas)
        hits = _leak_hits(documents, result.findings)
        rows.append(
            {"leak_id": mutation.mutation_id, "passed": not hits, "hits": hits[:4]}
        )
    return rows


# ---------------------------------------------------------------------------
# 방어면 coverage guard (REVIEW-023 B-03)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DepthProbe:
    """schema가 먼저 거르는 **심층 방어** 하나를 두 방향에서 증명한다.

    1. `unit` — 내부 검사 함수를 직접 호출해 그 분기가 실제로 선언한 finding을 낸다.
    2. `patch` — 같은 값을 문서에 넣으면 상류 schema가 먼저 잡는다(=심층 방어가 문서
       경로에서 도달 불가인 이유). schema 방어가 사라지면 이 기대가 깨진다.

    둘을 함께 요구하므로 "도달 못 하니 면제"라는 allowlist가 아니다.
    """

    probe_id: str
    title: str
    unit: Callable[[], list[Any]]
    unit_expected: tuple[str, str]
    base: str
    patch: Callable[[dict], Any]
    keep: tuple[str, ...]
    shadow_expected: tuple[tuple[str, str], ...]


def _probe_interval_nonfinite() -> list[Any]:
    findings: list[Any] = []
    contracts._check_half_open(float("nan"), 1.0, "probe", findings, what="probe")
    return findings


def _probe_interval_negative() -> list[Any]:
    findings: list[Any] = []
    contracts._check_half_open(-1.0, 1.0, "probe", findings, what="probe")
    return findings


def _probe_confidence_nonfinite() -> list[Any]:
    findings: list[Any] = []
    contracts._check_confidence_value(float("nan"), "model_score", "probe", findings)
    return findings


def _probe_token_nonfinite() -> list[Any]:
    segment = {"tokens": [{"text": "a", "start_seconds": 0.0, "end_seconds": float("nan")}]}
    return contracts._check_tokens(segment, "probe", False, {})


def depth_probes() -> list[DepthProbe]:
    return [
        DepthProbe(
            "DP-01", "구간 시간이 finite 숫자가 아니다", _probe_interval_nonfinite,
            ("E_TIME_RANGE", "probe/end_seconds"),
            "base", lambda d: tr(d, "tr-1").update(end_seconds=float("nan")), _LAYERS[2][1],
            (("E_SCHEMA", f"{T0}/0/end_seconds"),),
        ),
        DepthProbe(
            "DP-02", "구간 start_seconds가 음수다", _probe_interval_negative,
            ("E_TIME_RANGE", "probe/start_seconds"),
            "base", lambda d: tr(d, "tr-1").update(start_seconds=-1.0), _LAYERS[2][1],
            (("E_SCHEMA", f"{T0}/0/start_seconds"),),
        ),
        DepthProbe(
            "DP-03", "confidence가 finite 숫자가 아니다", _probe_confidence_nonfinite,
            ("E_CONFIDENCE", "probe"),
            "base",
            lambda d: sp(d, "sp-1").update(
                speech_confidence=float("nan"), speech_confidence_semantics="model_score"
            ),
            _LAYERS[3][1],
            (("E_SCHEMA", f"{S}/0/speech_confidence"),),
        ),
        DepthProbe(
            "DP-04", "token 시간이 finite 숫자가 아니다", _probe_token_nonfinite,
            ("E_TIME_RANGE", "probe/tokens/0/end_seconds"),
            "base",
            lambda d: tr(d, "tr-1")["tokens"][0].update(end_seconds=float("nan")),
            _LAYERS[2][1],
            (("E_SCHEMA", f"{T0}/0/tokens/0/end_seconds"),),
        ),
    ]


def run_depth_probes(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    register_mutations()
    sources = _base_documents(fixture_dir)
    rows: list[dict[str, Any]] = []
    for probe in depth_probes():
        unit_observed = tuple(
            sorted((finding.code, finding.location) for finding in probe.unit())
        )
        documents = copy.deepcopy(sources[probe.base])
        probe.patch(documents)
        documents = {key: documents[key] for key in probe.keep if key in documents}
        shadow_observed = tuple(sorted(validate_documents(documents, schemas).pairs))
        rows.append(
            {
                "probe_id": probe.probe_id,
                "title": probe.title,
                "passed": unit_observed == (probe.unit_expected,)
                and shadow_observed == probe.shadow_expected,
                "unit_expected": [list(probe.unit_expected)],
                "unit_observed": [list(pair) for pair in unit_observed],
                "shadow_expected": [list(pair) for pair in probe.shadow_expected],
                "shadow_observed": [list(pair) for pair in shadow_observed],
            }
        )
    return rows


def _defense_sites() -> dict[int, str]:
    """domain validator에서 `_finding(...)`을 내보내는 **문장**의 줄 번호 목록.

    mutant 목록은 사람이 고른 표본이라 빠진 방어면이 있어도 100% kill로 보인다. 이
    inventory는 "선언한 방어면 전부가 실제로 한 번은 발화하는가"를 따로 증명한다.
    """

    import ast

    source = (REPO_ROOT / VALIDATOR_PATH).read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    sites: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "_finding"):
            continue
        statement: ast.AST | None = node
        while statement is not None and not isinstance(statement, ast.stmt):
            statement = parents.get(statement)
        if statement is None:
            continue
        sites[statement.lineno] = lines[statement.lineno - 1].strip()
    return dict(sorted(sites.items()))


def run_defense_coverage(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    sites = _defense_sites()
    target = str((REPO_ROOT / VALIDATOR_PATH).resolve())
    executed: set[int] = set()

    def tracer(frame, event, arg):  # pragma: no cover - 추적 콜백
        if frame.f_code.co_filename != target:
            return None
        if event == "line":
            executed.add(frame.f_lineno)
        return tracer

    register_mutations()
    sources = _base_documents(fixture_dir)
    payloads = [load_fixture(path)["documents"] for path in sorted(fixture_dir.glob("k-*.json"))]
    payloads += [mutation.documents(sources) for mutation in MUTATIONS]

    probes = depth_probes()
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        for documents in payloads:
            validate_documents(documents, schemas)
        # 심층 방어는 문서 경로로 도달하지 않는다. 단위 호출로 실제 발화시킨다.
        for probe in probes:
            probe.unit()
    finally:
        sys.settrace(previous)

    return [
        {
            "site_id": f"DS-{line:04d}",
            "line": line,
            "snippet": snippet[:96],
            "passed": line in executed,
        }
        for line, snippet in sites.items()
    ]


def _check_only(fixture_dir: Path, schema_dir: Path) -> dict[str, Any]:
    schemas = SchemaSet(schema_dir)
    return {
        "fixtures": run_fixture_pass(schemas, fixture_dir),
        "mutations": run_input_mutations(schemas, fixture_dir),
        "leaks": run_leak_scan(schemas, fixture_dir),
    }


def _run_check_only(root: Path) -> dict[str, Any]:
    """임시 사본에서 `--check-only --json`을 실행하고 결과를 읽는다."""

    proc = subprocess.run(
        [sys.executable, "scripts/verify_task_029.py", "--check-only", "--json"],
        cwd=root,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": "src",
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            # 같은 초에 크기가 같은 파일을 다시 쓰면 스테일 .pyc가 재사용될 수 있다.
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        timeout=600,
    )
    if proc.returncode == 2 or not proc.stdout.strip():
        return {"crashed": True, "stderr": proc.stderr[-2000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"crashed": True, "stderr": proc.stdout[-2000:]}


def run_source_mutants(mutants: Sequence[SourceMutant], label: str) -> list[dict[str, Any]]:
    """저장소 밖 임시 사본에서만 수행한다. 저장소 파일은 바꾸지 않는다."""

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"mcs-029-{label}-") as tmp:
        root = Path(tmp) / "tree"
        shutil.copytree(
            REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
        )
        baseline = _run_check_only(root)
        if baseline.get("crashed") or not _all_passed(baseline):
            return [{"mutant_id": "BASELINE", "title": "임시 사본 baseline", "detected": False,
                     "sentinel_ok": False, "note": "baseline이 통과하지 않았다"}]
        valid_cases = {
            case["case_id"] for case in baseline["fixtures"]
        } & set(BASE_CASES.values())

        for mutant in mutants:
            path = root / mutant.target
            original = path.read_text(encoding="utf-8")
            if original.count(mutant.old) != 1:
                results.append(
                    {
                        "mutant_id": mutant.mutant_id,
                        "title": mutant.title,
                        "detected": False,
                        "sentinel_ok": False,
                        "skip_reason": f"패턴이 {original.count(mutant.old)}회 — 감사 불가",
                    }
                )
                continue
            path.write_text(original.replace(mutant.old, mutant.new), encoding="utf-8")
            observed = _run_check_only(root)
            path.write_text(original, encoding="utf-8")

            if observed.get("crashed"):
                # schema 계약 위반이나 import 실패도 탐지다 — 정상 case가 통과할 수 없다.
                results.append(
                    {
                        "mutant_id": mutant.mutant_id,
                        "title": mutant.title,
                        "detected": True,
                        "sentinel_ok": False,
                        "note": "임시 사본이 계약 오류로 중단됐다",
                    }
                )
                continue

            failed_cases = {
                case["case_id"] for case in observed["fixtures"] if not case["passed"]
            }
            failed_mutations = {
                item["mutation_id"] for item in observed["mutations"] if not item["passed"]
            }
            # 민감 값 비노출 스캔은 단일 kill id `LEAK`로 모은다.
            failed_leaks = (
                {"LEAK"}
                if any(not item["passed"] for item in observed.get("leaks", []))
                else set()
            )
            sentinel_ok = not (valid_cases & failed_cases)
            expected_kills = set(mutant.kills)
            caught = failed_cases | failed_mutations | failed_leaks
            if expected_kills:
                # 선언된 kill case 중 하나만 잡혀도 killed로 세면 나머지 방어면이
                # 증명되지 않는다 (REVIEW-023 B-03). **전부** 잡혀야 killed다.
                missing = sorted(expected_kills - caught)
                detected = not missing
            else:
                missing = []
                detected = bool(caught)
            results.append(
                {
                    "mutant_id": mutant.mutant_id,
                    "title": mutant.title,
                    "detected": detected,
                    "sentinel_ok": sentinel_ok,
                    "missing_kills": missing,
                    "killed_by": sorted(expected_kills & caught)[:8] or sorted(caught)[:8],
                }
            )
    return results


def _all_passed(payload: dict[str, Any]) -> bool:
    return (
        all(case["passed"] for case in payload.get("fixtures", []))
        and all(item["passed"] for item in payload.get("mutations", []))
        and all(item["passed"] for item in payload.get("leaks", []))
    )


def _summary(name: str, rows: Sequence[dict[str, Any]], *, sentinel: bool) -> dict[str, Any]:
    """분모별 요약. sentinel은 **실제로 실행한 valid-case 결과**만 센다.

    이전 판은 mutant가 아닌 분모에서 row 수를 그대로 sentinel 통과 수로 출력했다
    (REVIEW-023 B-03). 지금은 fixture/input도 각자 실제 sentinel을 돌린다.
    """

    total = len(rows)
    if sentinel:
        detected = sum(1 for row in rows if row.get("detected"))
        skipped = sum(1 for row in rows if row.get("skip_reason"))
    else:
        detected = sum(1 for row in rows if row.get("passed"))
        skipped = 0
    sentinel_rows = [row for row in rows if "sentinel_ok" in row]
    return {
        "name": name,
        "total": total,
        "detected": detected,
        "kill_rate": (detected / total) if total else 1.0,
        "sentinel_total": len(sentinel_rows),
        "sentinel_passed": sum(1 for row in sentinel_rows if row["sentinel_ok"]),
        "skipped": skipped,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/verify_task_029.py",
        description="TASK-029 fixture + 3분류 mutation 감사 (읽기 전용).",
    )
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--schemas", type=Path, default=SCHEMA_DIR)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="fixture와 input mutation만 수행한다 (임시 사본 감사에서 쓴다)",
    )
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력한다")
    args = parser.parse_args(argv)

    payload = _check_only(args.fixtures, args.schemas)
    fixture_rows = payload["fixtures"]
    mutation_rows = payload["mutations"]
    leak_rows = payload["leaks"]

    if args.check_only:
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            for row in fixture_rows:
                if not row["passed"]:
                    print(f"FAIL fixture {row['case_id']}: {'; '.join(row['mismatches'])}")
            for row in mutation_rows:
                if not row["passed"]:
                    print(f"FAIL input-mutant {row['mutation_id']}: {row['title']}")
                    print(f"     기대 {row['expected']}")
                    print(f"     관측 {row['observed']}")
            for row in leak_rows:
                if not row["passed"]:
                    print(f"LEAK {row['leak_id']}: {'; '.join(row['hits'])}")
        return 0 if _all_passed(payload) else 1

    audit_schemas = SchemaSet(args.schemas)
    depth_rows = run_depth_probes(audit_schemas, args.fixtures)
    coverage_rows = run_defense_coverage(audit_schemas, args.fixtures)
    schema_rows = run_source_mutants(schema_mutants(), "schema")
    validator_rows = run_source_mutants(validator_mutants(), "validator")

    summaries = [
        _summary("fixture", fixture_rows, sentinel=False),
        _summary("input mutants", mutation_rows, sentinel=False),
        _summary("leak scan", leak_rows, sentinel=False),
        _summary("depth probes", depth_rows, sentinel=False),
        _summary("validator defense sites", coverage_rows, sentinel=False),
        _summary("schema mutants", schema_rows, sentinel=True),
        _summary("validator code mutants", validator_rows, sentinel=True),
    ]
    report = {
        "summaries": summaries,
        "fixtures": fixture_rows,
        "input_mutants": mutation_rows,
        "leaks": leak_rows,
        "depth_probes": depth_rows,
        "defense_sites": coverage_rows,
        "schema_mutants": schema_rows,
        "validator_mutants": validator_rows,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in fixture_rows:
            if not row["passed"]:
                print(f"FAIL fixture {row['case_id']}: {'; '.join(row['mismatches'])}")
        for row in mutation_rows:
            if not row["passed"]:
                print(f"FAIL input-mutant {row['mutation_id']}: {row['title']}")
                print(f"     기대 {row['expected']}")
                print(f"     관측 {row['observed']}")
        for row in leak_rows:
            if not row["passed"]:
                print(f"LEAK {row['leak_id']}: {'; '.join(row['hits'])}")
        for row in depth_rows:
            if not row["passed"]:
                print(f"FAIL depth-probe {row['probe_id']}: {row['title']}")
                print(f"     단위 기대 {row['unit_expected']} / 관측 {row['unit_observed']}")
                print(f"     상류 기대 {row['shadow_expected']} / 관측 {row['shadow_observed']}")
        for row in coverage_rows:
            if not row["passed"]:
                print(f"UNCOVERED {row['site_id']} ({VALIDATOR_PATH}:{row['line']}): {row['snippet']}")
        for label, rows in (("schema", schema_rows), ("validator", validator_rows)):
            for row in rows:
                if row.get("skip_reason"):
                    print(f"SKIP {label}-mutant {row['mutant_id']}: {row['skip_reason']}")
                elif not row["detected"]:
                    print(
                        f"MISS {label}-mutant {row['mutant_id']}: {row['title']} "
                        f"(잡히지 않은 kill case: {', '.join(row.get('missing_kills') or []) or '없음'})"
                    )
                elif not row["sentinel_ok"]:
                    print(f"SENTINEL {label}-mutant {row['mutant_id']}: {row['title']}")
        print()
        for summary in summaries:
            print(
                f"{summary['name']:26s} detected {summary['detected']}/{summary['total']} "
                f"({summary['kill_rate'] * 100:.0f}%) · "
                f"valid-case sentinel {summary['sentinel_passed']}/{summary['sentinel_total']} · "
                f"SKIP {summary['skipped']}"
            )

    ok = (
        _all_passed(payload)
        and all(row["passed"] for row in depth_rows)
        and all(row["passed"] for row in coverage_rows)
        and all(row.get("detected") and row.get("sentinel_ok") for row in schema_rows)
        and all(row.get("detected") and row.get("sentinel_ok") for row in validator_rows)
    )
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    raise SystemExit(main())
