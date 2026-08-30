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

    def documents(self, sources: dict[str, dict]) -> dict:
        documents = copy.deepcopy(sources[self.base])
        self.patch(documents)
        keep = self.keep or auto_keep(self.expected)
        return {key: documents[key] for key in keep if key in documents}


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
        )
    )


def _set(node: dict, **values: Any) -> None:
    node.update(values)


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
            ("E_LINEAGE", "subtitle_document/cues"),
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
            ("E_LINEAGE", "subtitle_document/cues"),
            ("E_LINEAGE", f"{C}/1/lineage_fragments/1/text"),
        ],
        fixture="K-12",
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
        [("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization")],
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
            ("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments"),
            ("E_SOURCE_REF", f"{L0}/0/source_fragments/0/source_segment_id"),
        ],
    )
    mutate(
        "IM-62", "cue lineage가 존재하지 않는 입력 segment를 참조했다", "base",
        lambda d: _set(cue(d, "cue-1")["lineage_fragments"][0], input_segment_id="tl-ghost"),
        [
            ("E_LINEAGE", "subtitle_document/cues"),
            ("E_LINEAGE", f"{C}/0/lines/0"),
            ("E_SOURCE_REF", f"{C}/0/lineage_fragments/0/input_segment_id"),
        ],
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
        [("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments")],
        fixture="K-32",
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
        [("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments")],
        fixture="K-34",
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
        [("E_ALIGNMENT", f"{L1}/0/target_text"), ("E_LINEAGE", "subtitle_document/cues")],
        fixture="K-39",
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
            ("E_LINEAGE", "subtitle_document/cues"),
            ("E_LINEAGE", f"{C}/0/lineage_fragments/1/line_index"),
            ("E_LINEAGE", f"{C}/0/lines/1"),
        ],
        fixture="K-43",
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
            ("E_LINEAGE", "subtitle_document/cues"),
            ("E_LINEAGE", f"{C}/2/line_break_whitespace/0/text"),
        ],
        fixture="K-45",
    )
    mutate(
        "IM-90", "cue lineage fragment 순서가 원문 순서가 아니다", "mini",
        lambda d: cue(d, "cue-m1").__setitem__(
            "lineage_fragments", list(reversed(cue(d, "cue-m1")["lineage_fragments"]))
        ),
        [("E_OFFSET_ORDER", f"{C}/0/lineage_fragments/1/char_start")],
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
        [("E_LINEAGE", "subtitle_document/cues")],
        fixture="K-47",
    )
    mutate(
        "IM-93", "cue lineage fragment 범위가 입력 text 길이를 넘는다", "mini",
        lambda d: _set(cue(d, "cue-m2")["lineage_fragments"][1], char_end=9),
        [
            ("E_LINEAGE", "subtitle_document/cues"),
            ("E_LINEAGE", f"{C}/1/lines/1"),
            ("E_OFFSET_RANGE", f"{C}/1/lineage_fragments/1/char_end"),
        ],
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
            ("E_OFFSET_ORDER", f"{C}/0/lineage_fragments/2/char_start"),
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
        [("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments")],
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
            ("E_SOURCE_COVERAGE", "translated_transcript/uncovered_source_fragments"),
        ],
    )
    mutate(
        "IM-119", "line_break_whitespace의 after_line_index가 줄 경계가 아니다", "mini",
        lambda d: _set(cue(d, "cue-m3")["line_break_whitespace"][0], after_line_index=5),
        [
            ("E_LINEAGE", "subtitle_document/cues"),
            ("E_LINEAGE", f"{C}/2/line_break_whitespace/0/after_line_index"),
        ],
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
            "VM-12", "SpeechSegment ID 유일성 검사 제거", target,
            "            if segment_id in seen_ids:", "            if False:", ("IM-113",),
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
            "    if not covered(start):", "    if False:", ("IM-115",),
        ),
        SourceMutant(
            "VM-25", "ASR segment 끝의 합집합 포함 검사 제거", target,
            "    if not covered(end):", "    if False:", ("IM-27",),
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
            "            if joined != line:", "            if False:", ("IM-87", "IM-88"),
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
    ]


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
    return [
        {
            "case_id": outcome.case_id,
            "passed": outcome.passed,
            "mismatches": list(outcome.mismatches),
        }
        for outcome in run_fixtures(fixture_dir, schemas)
    ]


def run_input_mutations(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    register_mutations()
    sources = _base_documents(fixture_dir)
    results: list[dict[str, Any]] = []
    for mutation in MUTATIONS:
        documents = mutation.documents(sources)
        observed = tuple(sorted(validate_documents(documents, schemas).pairs))
        results.append(
            {
                "mutation_id": mutation.mutation_id,
                "title": mutation.title,
                "base": BASE_CASES[mutation.base],
                "expected": [list(pair) for pair in mutation.expected],
                "observed": [list(pair) for pair in observed],
                "passed": observed == mutation.expected,
            }
        )
    return results


def _check_only(fixture_dir: Path, schema_dir: Path) -> dict[str, Any]:
    schemas = SchemaSet(schema_dir)
    return {
        "fixtures": run_fixture_pass(schemas, fixture_dir),
        "mutations": run_input_mutations(schemas, fixture_dir),
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
            sentinel_ok = not (valid_cases & failed_cases)
            expected_kills = set(mutant.kills)
            if expected_kills:
                detected = bool(expected_kills & (failed_cases | failed_mutations))
            else:
                detected = bool(failed_cases or failed_mutations)
            results.append(
                {
                    "mutant_id": mutant.mutant_id,
                    "title": mutant.title,
                    "detected": detected,
                    "sentinel_ok": sentinel_ok,
                    "killed_by": sorted(
                        (expected_kills & (failed_cases | failed_mutations))
                        or (failed_cases | failed_mutations)
                    )[:6],
                }
            )
    return results


def _all_passed(payload: dict[str, Any]) -> bool:
    return all(case["passed"] for case in payload.get("fixtures", [])) and all(
        item["passed"] for item in payload.get("mutations", [])
    )


def _summary(name: str, rows: Sequence[dict[str, Any]], *, sentinel: bool) -> dict[str, Any]:
    total = len(rows)
    if sentinel:
        detected = sum(1 for row in rows if row.get("detected"))
        sentinel_ok = sum(1 for row in rows if row.get("sentinel_ok"))
        skipped = sum(1 for row in rows if row.get("skip_reason"))
    else:
        detected = sum(1 for row in rows if row.get("passed"))
        sentinel_ok = total
        skipped = 0
    return {
        "name": name,
        "total": total,
        "detected": detected,
        "kill_rate": (detected / total) if total else 1.0,
        "valid_case_sentinel_passed": sentinel_ok,
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
        return 0 if _all_passed(payload) else 1

    schema_rows = run_source_mutants(schema_mutants(), "schema")
    validator_rows = run_source_mutants(validator_mutants(), "validator")

    summaries = [
        _summary("fixture", fixture_rows, sentinel=False),
        _summary("input mutants", mutation_rows, sentinel=False),
        _summary("schema mutants", schema_rows, sentinel=True),
        _summary("validator code mutants", validator_rows, sentinel=True),
    ]
    report = {
        "summaries": summaries,
        "fixtures": fixture_rows,
        "input_mutants": mutation_rows,
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
        for label, rows in (("schema", schema_rows), ("validator", validator_rows)):
            for row in rows:
                if row.get("skip_reason"):
                    print(f"SKIP {label}-mutant {row['mutant_id']}: {row['skip_reason']}")
                elif not row["detected"]:
                    print(f"MISS {label}-mutant {row['mutant_id']}: {row['title']}")
                elif not row["sentinel_ok"]:
                    print(f"SENTINEL {label}-mutant {row['mutant_id']}: {row['title']}")
        print()
        for summary in summaries:
            print(
                f"{summary['name']:24s} detected {summary['detected']}/{summary['total']} "
                f"({summary['kill_rate'] * 100:.0f}%) · "
                f"valid-case sentinel {summary['valid_case_sentinel_passed']}/{summary['total']} · "
                f"SKIP {summary['skipped']}"
            )

    ok = (
        _all_passed(payload)
        and all(row.get("detected") and row.get("sentinel_ok") for row in schema_rows)
        and all(row.get("detected") and row.get("sentinel_ok") for row in validator_rows)
    )
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    raise SystemExit(main())
