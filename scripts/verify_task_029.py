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
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from media_clarity import subtitle_contracts as contracts  # noqa: E402
from media_clarity.subtitle_contracts import (  # noqa: E402
    DOCUMENT_KEYS,
    SchemaSet,
    load_fixture,
    run_fixtures,
    validate_documents,
)

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "subtitle_contracts"
SCHEMA_DIR = REPO_ROOT / "schemas"
VALIDATOR_PATH = "src/media_clarity/subtitle_contracts.py"

#: input mutation이 출발점으로 쓰는 정상 fixture.
BASE_CASES = {"base": "K-01", "mini": "K-02", "partial": "K-03", "coverage": "K-105"}


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
    #: 검증 컨텍스트 없이 문서 집합만으로 잡혀야 하는 반례.
    without_refs: bool = False

    def _restricted(self, sources: dict[str, dict], patch: bool) -> dict:
        documents = copy.deepcopy(sources[self.base])
        if patch:
            self.patch(documents)
        keep = self.keep or auto_keep(self.expected)
        if not patch and self.sentinel_keep is not None:
            keep = self.sentinel_keep
        # 검증 컨텍스트(`document_refs`)는 문서가 아니라 부가 정보이므로 기본으로 남긴다.
        # `without_refs` 반례는 **컨텍스트 부재 자체**가 결함이므로 변형된 쪽에서만 뺀다.
        # sentinel은 같은 문서 부분집합에 컨텍스트를 붙인 정상 입력이어야 한다.
        if not (patch and self.without_refs):
            keep = tuple(keep) + (contracts.REF_CONTEXT_KEY,)
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
    without_refs: bool = False,
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
            without_refs=without_refs,
        )
    )


def _set(node: dict, **values: Any) -> None:
    node.update(values)


#: 임의 정밀도 JSON 정수. `float()`로 바꾸면 `OverflowError`가 난다 (REVIEW-025 R-04).
_HUGE = 10 ** 400

#: 문장 내 전환이 든 원문. code-switch 반례가 이 문자열의 범위를 쪼갠다.
_SWITCHING_SOURCE = "今日はsunnyですね"


def _split_source_units(documents: dict, cuts: Sequence[tuple[int, int]]) -> None:
    """`tl-1`을 주어진 원문 범위대로 여러 번역 단위로 쪼갠다 (coverage는 유지한다)."""

    stream = documents["translated_transcript"]["streams"][0]
    template = tl(documents, "tl-1")
    rest = [item for item in stream["segments"] if item["segment_id"] != "tl-1"]
    units = []
    for index, (start, end) in enumerate(cuts):
        unit = copy.deepcopy(template)
        unit["segment_id"] = f"tl-1{chr(97 + index)}"
        unit["alignment_kind"] = "split"
        unit["target_text"] = f"조각{index}"
        unit["source_fragments"] = [
            {
                "source_segment_id": "tr-1",
                "char_start": start,
                "char_end": end,
                "source_text": _SWITCHING_SOURCE[start:end],
            }
        ]
        units.append(unit)
    stream["segments"] = units + rest


def _detach(ref: dict) -> dict:
    """같은 모양이지만 **다른 artifact**를 가리키는 ref (계보 절단 반례용)."""

    ref = copy.deepcopy(ref)
    ref["artifact_id"] = "art-detached"
    ref["content_hash"] = "sha256:" + "9" * 64
    return ref


def _as_video(ref: dict) -> dict:
    """문서가 아닌 media artifact를 가리키게 만든다 (kind/media_type 반례용)."""

    ref = copy.deepcopy(ref)
    ref["kind"] = "video"
    ref["media_type"] = "video/mp4"
    return ref


def _override(documents: dict, key: str) -> None:
    documents["subtitle_document"]["resolved_style"]["language_overrides"][key] = {}


def ref_context(documents: dict) -> dict:
    """문서 집합에서 **검증 컨텍스트**를 만든다 (REVIEW-024 H-01).

    "지금 검증하는 Transcript는 어떤 artifact인가"는 문서 안에 적을 수 없다
    (`content_hash`가 자기 자신의 해시라 순환이다). 합성 fixture에서는 상류 ref가 이미
    그 답을 담고 있으므로 그것을 컨텍스트로 승격한다. 실제 producer는 store에서 받는다.
    """

    context: dict[str, Any] = {}
    translated = documents.get("translated_transcript")
    subtitle = documents.get("subtitle_document")
    if isinstance(translated, dict) and "source_transcript" in translated:
        context["transcript"] = copy.deepcopy(translated["source_transcript"])
    elif isinstance(subtitle, dict) and subtitle.get("text_axis") == "source":
        context["transcript"] = copy.deepcopy(subtitle["input_document_ref"])
    if isinstance(subtitle, dict) and subtitle.get("text_axis") == "target":
        context["translated_transcript"] = copy.deepcopy(subtitle["input_document_ref"])
    return context


def coverage_documents(base: dict) -> dict:
    """정상 base에 **선택 필드를 모두 켠** 네 번째 정상 문서 집합 (REVIEW-024 H-04).

    schema 방어 inventory는 각 방어가 실제로 적용되는 instance를 정상 fixture에서 찾는다.
    base 세 건에 한 번도 나타나지 않는 선택 필드는 그 방어를 감사할 수 없다. 이 집합이
    그 공백을 메운다. 여기서 켠 값은 전부 upstream 근거와 일치하는 정직한 값이다.
    """

    documents = copy.deepcopy(base)

    # SpeechSegment — value_semantics enum instance.
    _set(
        documents["speech_segments"][0],
        speech_confidence=0.87,
        speech_confidence_semantics="calibrated_probability",
    )

    # AdapterCapabilityReport — candidate language restriction.
    _set(
        documents["transcript"]["capability_report"],
        restricts_candidate_languages=True,
        max_candidate_languages=3,
    )

    # Transcript stream — stream 수준 input speaker label (sp-1의 실제 label과 같다).
    stream = documents["transcript"]["streams"][0]
    _set(stream, speaker_label="CH-L", speaker_label_source="input")

    # Transcript segment — other reason + x- 확장 ID.
    segment = tr(documents, "tr-2")
    _set(
        segment,
        review_reasons=sorted(set(segment["review_reasons"]) | {"other"}),
        review_extension_id="x-mcs-coverage",
    )

    # SubtitleDocument — language override(닫힌 StyleOverride)의 모든 수치 필드.
    documents["subtitle_document"]["resolved_style"]["language_overrides"]["ko"] = {
        "max_chars_per_line": 16,
        "max_lines": 2,
        "max_cps": 12.0,
        "min_duration_seconds": 0.8,
        "max_duration_seconds": 7.0,
        "min_gap_seconds": 0.08,
        "line_break_policy": "balanced",
    }
    return documents


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
        # REVIEW-024 H-02 — `input`이라고 주장하려면 값도 실제 입력 label과 같아야 한다.
        # 이 반례의 초점은 diarization evidence이므로 label은 upstream과 정확히 맞춘다.
        lambda d: _set(tr(d, "tr-1"), speaker_label_source="input", speaker_label="CH-L"),
        [("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization")],
        fixture="K-19",
    )
    mutate(
        "IM-36", "supports_nbest=false인데 alternatives가 있다", "base",
        lambda d: _set(asr_capability(d), supports_nbest=False),
        [
            # REVIEW-024 H-03 — nbest 미지원이면 score semantics도 none이어야 한다.
            ("E_CAPABILITY_MISMATCH", "transcript/capability_report/nbest_score_semantics"),
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
        [
            # 선언 목록이 문자열 `unknown` 하나뿐이면 실제 산출 언어(ja/en)를 덮지 못한다.
            ("E_CAPABILITY_MISMATCH", "transcript/capability_report/supported_languages"),
            ("E_SCHEMA", "transcript/capability_report/supported_languages/0"),
        ],
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
        [("E_SCHEMA", "transcript/feature_status")],
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
        [("E_SCHEMA", "translated_transcript/capability_report")],
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
        [("E_SCHEMA", f"{C}/0")],
    )

    # --- style profile --------------------------------------------------------------------
    mutate(
        "IM-96", "resolved_style의 max_duration이 min_duration보다 작다", "base",
        lambda d: _set(d["subtitle_document"]["resolved_style"], max_duration_seconds=0.5),
        [
            ("E_TIME_RANGE", "subtitle_document/resolved_style/language_overrides"),
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
        [("E_TIME_RANGE", "subtitle_document/resolved_style/language_overrides")],
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
        [("E_SCHEMA", "speech_segments/0")],
        keep=_LAYERS[3][1],
        fixture="K-81",
    )
    mutate(
        "IM-149", "Transcript root에 미지의 필드를 붙였다", "mini",
        lambda d: _set(d["transcript"], x_unknown_root=1),
        [("E_SCHEMA", "transcript")],
        keep=_LAYERS[2][1],
        fixture="K-82",
    )
    mutate(
        "IM-150", "AdapterCapabilityReport root에 미지의 필드를 붙였다", "mini",
        lambda d: _set(d["transcript"]["capability_report"], x_unknown_root=1),
        [("E_SCHEMA", "transcript/capability_report")],
        keep=_LAYERS[2][1],
        fixture="K-83",
    )
    mutate(
        "IM-151", "TranslatedTranscript root에 미지의 필드를 붙였다", "base",
        lambda d: _set(d["translated_transcript"], x_unknown_root=1),
        [("E_SCHEMA", "translated_transcript")],
        keep=_LAYERS[1][1],
        fixture="K-84",
    )
    mutate(
        "IM-152", "SubtitleDocument root에 미지의 필드를 붙였다", "base",
        lambda d: _set(d["subtitle_document"], x_unknown_root=1),
        [("E_SCHEMA", "subtitle_document")],
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
            # LID 미지원 선언은 intra-sentential LID·language confidence semantics와도 모순이다.
            ("E_CAPABILITY_MISMATCH",
             "transcript/capability_report/language_confidence_semantics"),
            ("E_CAPABILITY_MISMATCH",
             "transcript/capability_report/supports_intra_sentential_lid"),
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
        [("E_SCHEMA", "")],
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

    # --- REVIEW-024 H-01: ArtifactRef 계보 결박 ----------------------------------
    mutate(
        "IM-172", "자막의 source_transcript_ref가 번역 문서의 source_transcript와 다르다", "base",
        # 컨텍스트는 그대로 두고 **번역 쪽만** 떼어낸다. 그러면 자막 쪽 위치에는
        # 문서 집합 안 동일성 검사만 남아 그 방어를 단독으로 증명할 수 있다.
        lambda d: _set(
            d["translated_transcript"],
            source_transcript=_detach(d["translated_transcript"]["source_transcript"]),
        ),
        [
            ("E_SOURCE_REF", "subtitle_document/source_transcript_ref"),
            ("E_SOURCE_REF", "translated_transcript/source_transcript"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-106",
    )
    mutate(
        "IM-173", "자막의 직접 입력 ref를 video artifact로 바꿨다", "base",
        lambda d: _set(
            d["subtitle_document"],
            input_document_ref=_as_video(d["subtitle_document"]["input_document_ref"]),
        ),
        [
            # 같은 artifact_id를 가리키는 컨텍스트 ref와 metadata가 어긋난 것도 함께 잡힌다.
            ("E_SOURCE_REF", "document_refs/translated_transcript/kind"),
            ("E_SOURCE_REF", "document_refs/translated_transcript/media_type"),
            ("E_SOURCE_REF", "subtitle_document/input_document_ref/kind"),
            ("E_SOURCE_REF", "subtitle_document/input_document_ref/media_type"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-107",
    )
    mutate(
        "IM-174", "번역 문서의 source_transcript를 video artifact로 바꿨다", "base",
        lambda d: _set(
            d["translated_transcript"],
            source_transcript=_as_video(d["translated_transcript"]["source_transcript"]),
        ),
        [
            ("E_SOURCE_REF", "document_refs/transcript/kind"),
            ("E_SOURCE_REF", "document_refs/transcript/media_type"),
            ("E_SOURCE_REF", "translated_transcript/source_transcript/kind"),
            ("E_SOURCE_REF", "translated_transcript/source_transcript/media_type"),
        ],
        keep=_LAYERS[1][1],
        fixture="K-108",
    )
    mutate(
        "IM-175", "번역과 자막의 원본 ref를 함께 detached chain으로 바꿨다", "base",
        lambda d: (
            _set(
                d["translated_transcript"],
                source_transcript=_detach(d["translated_transcript"]["source_transcript"]),
            ),
            _set(
                d["subtitle_document"],
                source_transcript_ref=_detach(d["subtitle_document"]["source_transcript_ref"]),
            ),
        ),
        [
            ("E_SOURCE_REF", "subtitle_document/source_transcript_ref"),
            ("E_SOURCE_REF", "translated_transcript/source_transcript"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-109",
    )
    mutate(
        "IM-176", "자막의 직접 입력 ref가 실제 입력 문서가 아니다", "base",
        lambda d: _set(
            d["subtitle_document"],
            input_document_ref=_detach(d["subtitle_document"]["input_document_ref"]),
        ),
        [("E_SOURCE_REF", "subtitle_document/input_document_ref")],
        keep=_LAYERS[0][1],
        fixture="K-110",
    )

    # --- REVIEW-024 H-02: input speaker label 값 결박 -----------------------------
    mutate(
        "IM-177", "source=input인데 label 값이 실제 입력과 다르다", "base",
        lambda d: _set(tr(d, "tr-1"), speaker_label="SPK-B", speaker_label_source="input"),
        [
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/speaker_diarization"),
            ("E_CAPABILITY_MISMATCH", f"{T0}/0/speaker_label"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-111",
    )
    mutate(
        "IM-178", "stream 수준 source=input인데 입력에 label 근거가 없다", "mini",
        lambda d: _set(
            d["transcript"]["streams"][0], speaker_label="CH-X", speaker_label_source="input"
        ),
        [("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label_source")],
        keep=_LAYERS[2][1],
        fixture="K-112",
    )
    mutate(
        "IM-179", "겹치는 입력 label이 여러 개라 단일 값을 정할 수 없다", "base",
        # REVIEW-025 R-02 — ambiguity 반례는 **실제로 겹치는** 입력 둘로 만든다.
        # 겹치지 않는 입력을 근거로 쓰는 것은 IM-199가 따로 잡는다.
        lambda d: (
            _set(sp(d, "sp-3"), end_seconds=4.5, speaker_label="CH-Z"),
            _set(
                tr(d, "tr-4"),
                speaker_label="CH-L",
                speaker_label_source="input",
                source_speech_segment_ids=["sp-3", "sp-4"],
            ),
        ),
        [("E_CAPABILITY_MISMATCH", f"{T0}/2/speaker_label")],
        keep=_LAYERS[2][1],
        fixture="K-113",
    )
    mutate(
        "IM-180", "stream 수준 input label 값이 그 stream의 입력과 다르다", "base",
        lambda d: _set(
            d["transcript"]["streams"][0], speaker_label="CH-Z", speaker_label_source="input"
        ),
        [("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label")],
        keep=_LAYERS[2][1],
        fixture="K-114",
    )
    mutate(
        "IM-181", "stream 입력 label이 여러 개라 단일 값을 정할 수 없다", "base",
        lambda d: (
            _set(
                d["transcript"]["streams"][0], speaker_label="CH-L", speaker_label_source="input"
            ),
            _set(sp(d, "sp-3"), speaker_label="CH-Z"),
        ),
        [("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label")],
        keep=_LAYERS[2][1],
        fixture="K-115",
    )

    # --- REVIEW-024 H-03: capability 내부 논리와 실제 evidence ---------------------
    mutate(
        "IM-182", "supported_languages가 빈 배열인데 명시적 limitation이 없다", "mini",
        lambda d: _set(asr_capability(d), supported_languages=[], limitations=[]),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/supported_languages")],
        keep=_LAYERS[2][1],
        fixture="K-116",
    )
    mutate(
        "IM-183", "산출한 JA 증거가 선언한 지원 언어 밖이다", "base",
        lambda d: _set(asr_capability(d), supported_languages=["en"]),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/supported_languages")],
        keep=_LAYERS[2][1],
        fixture="K-117",
    )
    mutate(
        "IM-184", "LID 미지원인데 intra-sentential LID를 지원한다고 보고했다", "mini",
        lambda d: _set(asr_capability(d), supports_intra_sentential_lid=True),
        [("E_CAPABILITY_MISMATCH",
          "transcript/capability_report/supports_intra_sentential_lid")],
        keep=_LAYERS[2][1],
        fixture="K-118",
    )
    mutate(
        "IM-185", "LID 미지원인데 language confidence semantics를 주장했다", "mini",
        lambda d: _set(asr_capability(d), language_confidence_semantics="model_score"),
        [
            ("E_CAPABILITY_MISMATCH",
             "transcript/capability_report/language_confidence_semantics"),
            ("E_CAPABILITY_MISMATCH", "transcript/feature_status/language_confidence"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-119",
    )
    mutate(
        "IM-186", "supports_nbest=false인데 nbest_score_semantics가 none이 아니다", "mini",
        lambda d: _set(asr_capability(d), nbest_score_semantics="model_score"),
        [("E_CAPABILITY_MISMATCH", "transcript/capability_report/nbest_score_semantics")],
        keep=_LAYERS[2][1],
        fixture="K-120",
    )
    mutate(
        "IM-187", "번역한 원문 언어가 선언한 지원 원문 언어 밖이다", "base",
        lambda d: _set(mt_capability(d), supported_source_languages=["ko"]),
        [("E_CAPABILITY_MISMATCH",
          "translated_transcript/capability_report/supported_source_languages")],
        keep=_LAYERS[1][1],
        fixture="K-121",
    )
    mutate(
        "IM-188", "번역 supported_source_languages가 비었는데 limitation이 없다", "base",
        lambda d: _set(mt_capability(d), supported_source_languages=[], limitations=[]),
        [("E_CAPABILITY_MISMATCH",
          "translated_transcript/capability_report/supported_source_languages")],
        keep=_LAYERS[1][1],
        fixture="K-122",
    )

    # --- REVIEW-024 H-06: dynamic key가 error location으로 새지 않는다 --------------
    mutate(
        "IM-189", "language override key가 절대 Unix 경로다", "base",
        lambda d: _override(d, "/home/patient/secret.mp4"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-123",
    )
    mutate(
        "IM-190", "language override key가 Windows 경로다", "base",
        lambda d: _override(d, "C:\\Users\\p\\secret.mp4"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-124",
    )
    mutate(
        "IM-191", "language override key에 JSON Pointer 구분자 /가 있다", "base",
        lambda d: _override(d, "a/b"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-125",
    )
    mutate(
        "IM-192", "language override key에 JSON Pointer escape 문자 ~가 있다", "base",
        lambda d: _override(d, "~0"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-126",
    )
    mutate(
        "IM-193", "language override key가 1 scalar 비-ASCII다", "base",
        lambda d: _override(d, "日"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-127",
    )
    mutate(
        "IM-194", "language override key가 2 scalar ASCII다", "base",
        lambda d: _override(d, "X9"),
        # 모양이 안전해 보여도 정본이 선언한 어휘가 아니면 접는다 (REVIEW-025 R-05).
        # 남길 수 있는 것은 고정 field 이름과 language tag subset뿐이다.
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-128",
    )
    mutate(
        "IM-195", "알 수 없는 최상위 문서 key가 절대 경로다", "base",
        lambda d: d.__setitem__("/home/patient/secret.mp4", {}),
        # 안전한 상위 구간이 없으므로 root pointer(빈 문자열)로 접힌다. 경로는 남지 않는다.
        [("E_SCHEMA", "")],
        keep=("speech_segments", "/home/patient/secret.mp4"),
        fixture="K-129",
    )

    # --- 검증 컨텍스트 자체의 모양 ------------------------------------------------
    mutate(
        "IM-196", "document_refs가 객체가 아니다", "base",
        lambda d: d.__setitem__(contracts.REF_CONTEXT_KEY, []),
        [("E_SCHEMA", "document_refs")],
        keep=("speech_segments", "transcript"),
        fixture="K-130",
    )
    mutate(
        "IM-197", "document_refs에 단일 문서가 아닌 key가 있다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY].__setitem__("speech_segments", {}),
        [("E_SCHEMA", "document_refs")],
        keep=("speech_segments", "transcript"),
        fixture="K-131",
    )
    mutate(
        "IM-198", "document_refs 항목에 artifact identity가 없다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY].__setitem__("transcript", {}),
        [
            ("E_SCHEMA", "document_refs/transcript"),
            ("E_SOURCE_REF", "document_refs/transcript"),
        ],
        keep=("speech_segments", "transcript"),
        fixture="K-132",
    )

    # --- REVIEW-025 R-01: 검증 컨텍스트 fail-open과 ArtifactRef 일관성 ---------------
    mutate(
        "IM-199", "검증 컨텍스트가 아예 없다 (fail-open 금지)", "base",
        lambda d: None,
        [
            ("E_SOURCE_REF", "subtitle_document/input_document_ref"),
            ("E_SOURCE_REF", "subtitle_document/source_transcript_ref"),
            ("E_SOURCE_REF", "translated_transcript/source_transcript"),
        ],
        keep=_LAYERS[0][1],
        without_refs=True,
        fixture="K-133",
    )
    mutate(
        "IM-200", "검증 컨텍스트에 필요한 role이 빠졌다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY].pop("translated_transcript"),
        [("E_SOURCE_REF", "subtitle_document/input_document_ref")],
        keep=_LAYERS[0][1],
        fixture="K-134",
    )
    mutate(
        "IM-201", "Transcript와 TranslatedTranscript가 같은 identity로 붕괴했다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY].__setitem__(
            "translated_transcript",
            copy.deepcopy(d[contracts.REF_CONTEXT_KEY]["transcript"]),
        ),
        [
            ("E_SOURCE_REF", "document_refs/translated_transcript"),
            ("E_SOURCE_REF", "subtitle_document/input_document_ref"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-135",
    )
    mutate(
        "IM-202", "같은 artifact_id에 서로 다른 content_hash를 썼다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY]["transcript"].__setitem__(
            "content_hash", "sha256:" + "7" * 64
        ),
        [
            ("E_SOURCE_REF", "document_refs/transcript/content_hash"),
            ("E_SOURCE_REF", "subtitle_document/source_transcript_ref"),
            ("E_SOURCE_REF", "translated_transcript/source_transcript"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-136",
    )
    mutate(
        "IM-203", "같은 artifact_id·hash인데 byte_size가 다르다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY]["transcript"].__setitem__("byte_size", 4096),
        [("E_SOURCE_REF", "document_refs/transcript/byte_size")],
        keep=_LAYERS[0][1],
        fixture="K-137",
    )
    mutate(
        "IM-204", "검증 컨텍스트 ref에 계약 밖 필드를 넣었다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY]["transcript"].__setitem__("x_extra", 1),
        [("E_SCHEMA", "document_refs/transcript")],
        keep=_LAYERS[0][1],
        fixture="K-138",
    )
    mutate(
        "IM-205", "검증 컨텍스트에 쓰이지 않는 role을 넣었다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY].__setitem__(
            "subtitle_document", copy.deepcopy(d[contracts.REF_CONTEXT_KEY]["transcript"])
        ),
        [("E_SCHEMA", "document_refs")],
        keep=_LAYERS[0][1],
        fixture="K-139",
    )
    mutate(
        "IM-206", "검증 컨텍스트 ref가 문서가 아닌 video artifact다", "base",
        # 같은 artifact를 가리키는 ref를 **전부** video로 바꾼다. metadata 일관성은 유지되므로
        # 컨텍스트 자체의 문서-종류 결박만 남는다.
        lambda d: (
            _set(
                d[contracts.REF_CONTEXT_KEY],
                transcript=_as_video(d[contracts.REF_CONTEXT_KEY]["transcript"]),
            ),
            _set(
                d["translated_transcript"],
                source_transcript=_as_video(d["translated_transcript"]["source_transcript"]),
            ),
            _set(
                d["subtitle_document"],
                source_transcript_ref=_as_video(
                    d["subtitle_document"]["source_transcript_ref"]
                ),
            ),
        ),
        [
            ("E_SOURCE_REF", "document_refs/transcript/kind"),
            ("E_SOURCE_REF", "document_refs/transcript/media_type"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-140",
    )

    # --- REVIEW-025 R-02: 비겹치는 SpeechSegment lineage ---------------------------
    mutate(
        "IM-207", "겹치지 않는 입력의 label을 빌려 왔다 (덮는 입력은 unlabeled)", "base",
        lambda d: (
            sp(d, "sp-4").pop("speaker_label", None),
            _set(
                tr(d, "tr-4"),
                speaker_label="CH-L",
                speaker_label_source="input",
                source_speech_segment_ids=["sp-4", "sp-1"],
            ),
        ),
        [
            ("E_CAPABILITY_MISMATCH", f"{T0}/2/speaker_label_source"),
            ("E_TIME_RANGE", f"{T0}/2/source_speech_segment_ids/1"),
        ],
        keep=_LAYERS[2][1],
        fixture="K-141",
    )
    mutate(
        "IM-208", "ASR segment가 겹치지 않는 입력을 lineage로 참조했다", "base",
        lambda d: _set(tr(d, "tr-4"), source_speech_segment_ids=["sp-4", "sp-1"]),
        [("E_TIME_RANGE", f"{T0}/2/source_speech_segment_ids/1")],
        keep=_LAYERS[2][1],
        fixture="K-142",
    )
    mutate(
        "IM-209", "stream 입력 중 label 없는 것이 있는데 단일 input label을 주장했다", "base",
        lambda d: (
            [
                segment.pop("speaker_label", None)
                for segment in d["speech_segments"]
                if segment["segment_id"] in ("sp-3", "sp-4")
            ],
            _set(
                d["transcript"]["streams"][0],
                speaker_label="CH-L",
                speaker_label_source="input",
            ),
        ),
        [("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label")],
        keep=_LAYERS[2][1],
        fixture="K-143",
    )

    # --- REVIEW-025 R-03: translation code-switch capability ----------------------
    mutate(
        "IM-210", "문장 내 전환이 든 문자열을 한 단위로 번역하면서 code-switching 미지원", "base",
        lambda d: _set(mt_capability(d), supports_code_switching_input=False),
        [("E_CAPABILITY_MISMATCH",
          "translated_transcript/capability_report/supports_code_switching_input")],
        keep=_LAYERS[1][1],
        fixture="K-144",
    )
    mutate(
        "IM-211", "언어 경계를 가로지르는 fragment 하나로 번역하면서 code-switching 미지원", "base",
        lambda d: (
            _set(mt_capability(d), supports_code_switching_input=False),
            _split_source_units(d, [(0, 5), (5, 11)]),
        ),
        [("E_CAPABILITY_MISMATCH",
          "translated_transcript/capability_report/supports_code_switching_input")],
        keep=_LAYERS[1][1],
        fixture="K-145",
    )

    # --- REVIEW-025 R-04: 임의 정밀도 JSON 숫자 -------------------------------------
    mutate(
        "IM-212", "ASR segment 시작이 임의 정밀도 정수다", "base",
        lambda d: _set(tr(d, "tr-1"), start_seconds=_HUGE),
        [("E_TIME_RANGE", f"{T0}/0/end_seconds")],
        keep=_LAYERS[2][1],
        fixture="K-146",
    )
    mutate(
        "IM-213", "token confidence가 임의 정밀도 정수다", "base",
        lambda d: _set(tr(d, "tr-1")["tokens"][0], confidence=_HUGE),
        [("E_CONFIDENCE", f"{T0}/0/tokens/0/confidence")],
        keep=_LAYERS[2][1],
        fixture="K-147",
    )
    mutate(
        "IM-214", "ASR segment 시작이 임의 정밀도 음수다", "base",
        lambda d: _set(tr(d, "tr-1"), start_seconds=-_HUGE),
        [("E_SCHEMA", f"{T0}/0/start_seconds")],
        keep=_LAYERS[2][1],
        fixture="K-148",
    )
    mutate(
        "IM-215", "SpeechSegment 시작이 임의 정밀도 정수다", "base",
        lambda d: _set(sp(d, "sp-1"), start_seconds=_HUGE),
        [("E_TIME_RANGE", f"{S}/0/end_seconds")],
        keep=_LAYERS[3][1],
        fixture="K-149",
    )
    mutate(
        "IM-216", "resolved style 숫자가 임의 정밀도 음수다", "base",
        lambda d: _set(d["subtitle_document"]["resolved_style"], max_cps=-_HUGE),
        [("E_SCHEMA", "subtitle_document/resolved_style/max_cps")],
        keep=_LAYERS[0][1],
        fixture="K-150",
    )
    mutate(
        "IM-217", "번역 source fragment offset이 임의 정밀도 정수다", "base",
        lambda d: _set(tl(d, "tl-1")["source_fragments"][0], char_end=_HUGE),
        [
            ("E_ALIGNMENT", f"{L0}/0/alignment_kind"),
            ("E_OFFSET_RANGE", f"{L0}/0/source_fragments/0/char_end"),
            ("E_SOURCE_COVERAGE", f"{T0}/0/text"),
        ],
        keep=_LAYERS[1][1],
        fixture="K-151",
    )
    mutate(
        "IM-218", "cue 종료 시각이 임의 정밀도 정수다", "base",
        lambda d: _set(cue(d, "cue-1"), end_seconds=_HUGE),
        [
            ("E_CUE_OVERLAP", f"{C}/1"),
            ("E_CUE_OVERLAP", f"{C}/3"),
            ("E_CUE_OVERLAP", f"{C}/4"),
        ],
        keep=_LAYERS[0][1],
        fixture="K-152",
    )

    # --- REVIEW-025 R-05: dynamic key location alias --------------------------------
    mutate(
        "IM-219", "최상위 key가 실제 경로처럼 보이는 alias다", "base",
        lambda d: d.__setitem__("transcript/streams", {}),
        [("E_SCHEMA", "")],
        keep=("speech_segments", "transcript", "transcript/streams"),
        fixture="K-153",
    )
    mutate(
        "IM-220", "document_refs key가 실제 경로처럼 보이는 alias다", "base",
        lambda d: d[contracts.REF_CONTEXT_KEY].__setitem__("transcript/artifact_id", {}),
        [("E_SCHEMA", "document_refs")],
        keep=("speech_segments", "transcript"),
        fixture="K-154",
    )
    mutate(
        "IM-221", "language override key가 ASCII 개인 식별자처럼 보인다", "base",
        lambda d: _override(d, "patient_name"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-155",
    )
    mutate(
        "IM-222", "language override key가 사람 이름 모양이다", "base",
        lambda d: _override(d, "John_Doe"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-156",
    )
    mutate(
        "IM-223", "language override key가 실제 nested 경로와 같은 location으로 충돌한다", "base",
        # 실제 `ko` override의 결함 위치와, 그 위치를 그대로 흉내 낸 key가 함께 있다.
        # 이어붙인 문자열만 보면 둘을 구분할 수 없다 (REVIEW-025 R-05).
        lambda d: (
            d["subtitle_document"]["resolved_style"]["language_overrides"].__setitem__(
                "ko", {"max_duration_seconds": 1.0, "min_duration_seconds": 2.0}
            ),
            _override(d, "ko/max_duration_seconds"),
        ),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-157",
    )
    mutate(
        "IM-225", "und 구간을 사이에 둔 문장 내 전환을 한 단위로 번역했다", "base",
        # 알려진 언어는 하나(`ja`)뿐이라 "복수 언어" 조건으로는 잡히지 않는다.
        # fragment 안쪽의 intra-sentential 전환 경계만이 이 반례를 만든다 (REVIEW-025 R-03).
        lambda d: (
            _set(
                tr(d, "tr-1"),
                language_spans=[
                    {"char_start": 0, "char_end": 3, "language": "ja", "confidence": 0.95},
                    {"char_start": 3, "char_end": 8, "language": "und",
                     "switch_kind": "intra_sentential"},
                    {"char_start": 8, "char_end": 11, "language": "ja",
                     "switch_kind": "intra_sentential"},
                ],
                needs_review=True,
                review_reasons=["language_switch", "language_unknown"],
            ),
            tr(d, "tr-1").pop("dominant_language", None),
            _set(mt_capability(d), supports_code_switching_input=False),
            _split_source_units(d, [(0, 2), (2, 5), (5, 11)]),
        ),
        [("E_CAPABILITY_MISMATCH",
          "translated_transcript/capability_report/supports_code_switching_input")],
        keep=_LAYERS[1][1],
        fixture="K-159",
    )
    mutate(
        "IM-224", "language override key가 emoji다", "base",
        lambda d: _override(d, "\U0001f642"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-158",
    )

    # --- REVIEW-026 R-01: 위치별 비식별화 ------------------------------------------
    # 여기 key는 전부 **다른 위치에서는 정본 field**다. 전역 allowlist는 그 사실만으로
    # 사용자 제어 key를 안전하다고 오인했다. 이제 각자의 부모로 접혀야 한다.
    for index, (mutation_id, key, case) in enumerate(
        (
            ("IM-226", "uri", "K-160"),
            ("IM-227", "text", "K-161"),
            ("IM-228", "artifact_id", "K-162"),
        )
    ):
        mutate(
            mutation_id, f"최상위 key가 다른 위치의 정본 field 이름이다 ({key})", "base",
            (lambda name: lambda d: d.__setitem__(name, SENSITIVE_PROBE))(key),
            [("E_SCHEMA", "")],
            keep=("speech_segments", "transcript", key),
            fixture=case,
        )
    for mutation_id, key, case in (
        ("IM-229", "uri", "K-163"),
        ("IM-230", "speaker_label", "K-164"),
    ):
        mutate(
            mutation_id, f"document_refs key가 다른 위치의 정본 field 이름이다 ({key})", "base",
            (lambda name: lambda d: d[contracts.REF_CONTEXT_KEY].__setitem__(
                name, SENSITIVE_PROBE
            ))(key),
            [("E_SCHEMA", "document_refs")],
            keep=("speech_segments", "transcript"),
            fixture=case,
        )
    # BCP-47·private-use 모양은 임의 문자열을 담을 수 있다. 모양은 비식별화 근거가 아니다.
    for mutation_id, key, case in (
        ("IM-231", "en-John-Doe", "K-165"),
        ("IM-232", "en-x-secret", "K-166"),
        ("IM-233", "patient", "K-167"),
        ("IM-234", "password", "K-168"),
    ):
        mutate(
            mutation_id, f"language override key가 language tag 모양의 개인 식별자다 ({key})",
            "base",
            # 모양이 language tag와 같으므로 key 자체는 schema를 통과한다. 값이 계약을 어겨야
            # finding이 생기고, 그 location이 raw key를 노출하는지 볼 수 있다.
            (lambda name: lambda d: d["subtitle_document"]["resolved_style"][
                "language_overrides"
            ].__setitem__(name, {"max_cps": -1}))(key),
            [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
            keep=_LAYERS[0][1],
            fixture=case,
        )
    mutate(
        "IM-235", "language override key가 다른 위치의 정본 field 이름이다", "base",
        lambda d: _override(d, "speaker_label"),
        [("E_SCHEMA", "subtitle_document/resolved_style/language_overrides")],
        keep=_LAYERS[0][1],
        fixture="K-169",
    )

    # --- 오너 결정 option 3 (REVIEW-026 D-04): language span 정규형 ------------------
    # 맞닿은 같은 언어 span은 같은 시간 구간을 두 가지로 적을 수 있게 한다. 격자 채점이
    # 표현에 따라 달라지지 않도록 정규형을 하나로 고정한다.
    mutate(
        "IM-236", "맞닿은 두 span이 같은 언어다 (알려진 언어)", "base",
        lambda d: tr(d, "tr-1").__setitem__(
            "language_spans",
            [
                {"char_start": 0, "char_end": 3, "language": "ja", "confidence": 0.95},
                {"char_start": 3, "char_end": 5, "language": "en",
                 "switch_kind": "intra_sentential"},
                {"char_start": 5, "char_end": 8, "language": "en",
                 "switch_kind": "intra_sentential"},
                {"char_start": 8, "char_end": 11, "language": "ja",
                 "switch_kind": "intra_sentential"},
            ],
        ),
        [("E_OFFSET_ORDER", "transcript/streams/0/segments/0/language_spans/2/language")],
        fixture="K-170",
    )
    mutate(
        "IM-237", "맞닿은 두 span이 같은 언어다 (und)", "base",
        lambda d: tr(d, "tr-3").__setitem__(
            "language_spans",
            [
                {"char_start": 0, "char_end": 3, "language": "und"},
                {"char_start": 3, "char_end": 7, "language": "und",
                 "switch_kind": "unknown"},
            ],
        ),
        [("E_OFFSET_ORDER", "transcript/streams/1/segments/0/language_spans/1/language")],
        fixture="K-171",
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


#: nbest 함의 anchor (여러 줄이라 상수로 뺀다).
NBEST_OLD = (
    '    if capability.get("supports_nbest") is not True and capability.get(\n'
    '        "nbest_score_semantics"\n'
    '    ) not in (None, "none"):'
)


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
            """    if end <= start:
        findings.append(
            _finding(
                f"{where}/end_seconds",
                "E_TIME_RANGE",
                f"{what}는 positive duration 반개구간이어야 한다",
            )
        )
        return False""",
            "    if False:\n        return False", ("IM-24", "IM-25"),
        ),
        SourceMutant(
            "VM-03", "calibrated_probability 범위 검사 제거", target,
            '    if semantics == "calibrated_probability" and not (0 <= value <= 1):',
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
            """        extension = node.get("review_extension_id")
        if not isinstance(extension, str):
            findings.append(
                _finding(
                    location,
                    "E_SCHEMA",
                    "review_reasons에 other가 있으면 review_extension_id가 필요하다",
                )
            )""",
            "        pass", ("IM-103",),
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
            # REVIEW-024 G — VM-83이 같은 transformation이었다. 별도 mutant 두 개가 아니라
            # 선언 kill case를 합친 **하나의 multi-kill mutant**로 감사한다.
            "VM-25", "ASR segment 구간의 내부 빈틈 검사 제거", target,
            "    if end > holder[1]:", "    if False:",
            ("IM-27", "IM-122", "IM-123"),
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
            "        if not (_finite(low) and _finite(high) and high <= low):\n            return",
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
            "VM-93", "segment-level input speaker evidence 결박 호출 제거", target,
            """        findings.extend(
            _check_input_label_value(
                segment.get("speaker_label"),
                input_labels,
                where,
                unlabeled_evidence=unlabeled_cover,
            )
        )""",
            "        pass", ("IM-144", "IM-177", "IM-179"),
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
        Finding(location=safe_location(finding.location), code=finding.code,
                message=redact_schema_message(finding.message))
        for finding in findings
    ]""",
            "    return list(findings)", ("LEAK",),
        ),
        # --- REVIEW-024 E: depth 방어를 지우면 depth probe가 그 mutant를 죽여야 한다 ------
        SourceMutant(
            "VM-105", "confidence finite 검사 제거", target,
            '        findings.append(_finding(location, "E_CONFIDENCE", "confidence가 finite 숫자가 아니다"))\n        return',
            "        pass\n        return", ("DP-03",),
        ),
        SourceMutant(
            "VM-106", "half-open 구간의 음수 start 검사 제거", target,
            """    if start < 0:
        findings.append(
            _finding(f"{where}/start_seconds", "E_TIME_RANGE", f"{what} start_seconds가 음수다")
        )
        return False""",
            "    if False:\n        return False", ("DP-02",),
        ),
        SourceMutant(
            "VM-107", "token 시간의 finite 검사 제거", target,
            """            if not _finite(start) or not _finite(end):
                findings.append(
                    _finding(f"{spot}/end_seconds", "E_TIME_RANGE", "token 시간이 finite 숫자가 아니다")
                )""",
            "            if False:\n                pass", ("DP-04",),
        ),
        SourceMutant(
            "VM-108", "구간 시간의 finite 검사 제거", target,
            """    if not _finite(start) or not _finite(end):
        findings.append(
            _finding(f"{where}/end_seconds", "E_TIME_RANGE", f"{what} 시간이 finite 숫자가 아니다")
        )
        return False""",
            "    if False:\n        return False", ("DP-01",),
        ),
        # --- REVIEW-024 H-06: location의 dynamic key 정규화 ---------------------------
        SourceMutant(
            "VM-109", "경로별 어휘를 schema 전역 field 이름 집합으로 되돌린다", target,
            "    properties = node.get(\"properties\")\n    return frozenset(properties) if isinstance(properties, Mapping) else frozenset()",
            "    names: set[str] = set(DOCUMENT_KEYS) | {REF_CONTEXT_KEY}\n    stack: list[Any] = list(_schema_documents().values())\n    while stack:\n        item = stack.pop()\n        if isinstance(item, Mapping):\n            properties = item.get(\"properties\")\n            if isinstance(properties, Mapping):\n                names.update(properties)\n            stack.extend(item.values())\n        elif isinstance(item, list):\n            stack.extend(item)\n    return frozenset(names)",
            ("LOCATION", "IM-226", "IM-229"),
        ),
        SourceMutant(
            "VM-110", "location 구간의 alias 충돌 검사 제거", target,
            "            if len(matches) != 1 or matches[0] not in _declared_children(position):",
            "            if len(matches) < 1 or matches[0] not in _declared_children(position):",
            ("IM-219",),
        ),
        SourceMutant(
            "VM-111", "validate_documents의 location 정규화 제거", target,
            "    root = documents if isinstance(documents, Mapping) else None\n    resolved = [\n        Finding(location=safe_location(finding.location, root), code=finding.code,\n                message=finding.message)\n        for finding in findings\n    ]",
            "    resolved = list(findings)", ("LOCATION",),
        ),
        # --- REVIEW-024 H-01: ArtifactRef 계보 -------------------------------------
        SourceMutant(
            "VM-112", "상류 문서 ref의 kind 검사 제거", target,
            '    if ref.get("kind") != DOCUMENT_REF_KIND:', "    if False:",
            ("IM-173", "IM-174"),
        ),
        SourceMutant(
            "VM-113", "상류 문서 ref의 media_type 검사 제거", target,
            "    if essence != DOCUMENT_REF_MEDIA_TYPE:", "    if False:",
            ("IM-173", "IM-174"),
        ),
        SourceMutant(
            "VM-114", "번역 source_transcript의 identity 검사 제거", target,
            '        if _ref_identity(translated.get("source_transcript")) != transcript_ref:',
            "        if False:", ("IM-175",),
        ),
        SourceMutant(
            "VM-115", "자막 직접 입력 ref의 identity 검사 제거", target,
            '            if _ref_identity(subtitle.get("input_document_ref")) != expected:',
            "            if False:", ("IM-176",),
        ),
        SourceMutant(
            "VM-116", "자막 source_transcript_ref의 컨텍스트 identity 검사 제거", target,
            '            and _ref_identity(subtitle.get("source_transcript_ref")) != transcript_ref',
            "            and False", ("IM-175",),
        ),
        SourceMutant(
            "VM-117", "자막 ↔ 번역 source ref 동일성 검사 제거", target,
            '    if axis == "target" and isinstance(translated, Mapping) and "source_transcript_ref" in document:',
            "    if False:", ("IM-172",),
        ),
        # --- REVIEW-024 H-02: input speaker label 값 -------------------------------
        SourceMutant(
            "VM-118", "input label 근거 부재 검사 제거", target,
            "    if not input_labels:", "    if False:", ("IM-178",),
        ),
        SourceMutant(
            "VM-119", "input label 다중 값 ambiguity 검사 제거", target,
            "    if len(input_labels) > 1:", "    if False:", ("IM-179", "IM-181"),
        ),
        SourceMutant(
            "VM-120", "input label 값 동일성 검사 제거", target,
            "    if isinstance(label, str) and label not in input_labels:", "    if False:",
            ("IM-177", "IM-180"),
        ),
        SourceMutant(
            "VM-121", "stream-level input label 결박 호출 제거", target,
            """            findings.extend(
                _check_input_label_value(
                    stream.get("speaker_label"),
                    {value for value in evidence if value is not None},
                    where,
                    # 한 입력만 label을 갖고 나머지는 없으면 stream 전체의 화자를 그 하나로
                    # 정당화할 수 없다 (REVIEW-025 R-02).
                    unlabeled_evidence=any(value is None for value in evidence),
                )
            )""",
            "            pass", ("IM-178", "IM-180", "IM-181"),
        ),
        # --- REVIEW-024 H-03: capability 내부 논리 ---------------------------------
        SourceMutant(
            "VM-122", "intra-sentential LID 함의 검사 제거", target,
            '    if capability.get("supports_intra_sentential_lid") is True and not language_id:',
            "    if False:", ("IM-184",),
        ),
        SourceMutant(
            "VM-123", "language confidence semantics 함의 검사 제거", target,
            '    if capability.get("language_confidence_semantics") not in (None, "none") and not language_id:',
            "    if False:", ("IM-185",),
        ),
        SourceMutant(
            "VM-124", "nbest score semantics 함의 검사 제거", target,
            NBEST_OLD, "    if False:", ("IM-186",),
        ),
        SourceMutant(
            "VM-125", "빈 지원 언어 목록의 limitation 요구 제거", target,
            "    if isinstance(limitations, list) and limitations:", "    if True:",
            ("IM-182", "IM-188"),
        ),
        SourceMutant(
            "VM-126", "산출 언어 ↔ 선언 지원 언어 대조 제거", target,
            "    unsupported = sorted(emitted - {tag for tag in supported if isinstance(tag, str)})",
            "    unsupported = []", ("IM-183", "IM-187"),
        ),
        # --- 검증 컨텍스트 모양 ------------------------------------------------------
        SourceMutant(
            "VM-127", "document_refs 모양 검사 제거", target,
            "            findings.extend(_check_ref_context(documents[key], validator))",
            "            pass", ("IM-196", "IM-197", "IM-198"),
        ),
        # --- REVIEW-025 R-01: 컨텍스트 필수화와 ArtifactRef 일관성 --------------------
        SourceMutant(
            "VM-128", "컨텍스트 필수 role 판정 제거 (fail-open)", target,
            """    absent = [
        (role, location)
        for role, location in requirements
        if _ref_identity(refs.get(role)) is None
    ]""",
            "    absent = []", ("IM-199", "IM-200"),
        ),
        SourceMutant(
            "VM-129", "번역 문서가 요구하는 컨텍스트 role 선언 제거", target,
            '        requirements.append(("transcript", "translated_transcript/source_transcript"))',
            "        pass", ("IM-199",),
        ),
        SourceMutant(
            "VM-130", "자막 원본 ref가 요구하는 컨텍스트 role 선언 제거", target,
            '            requirements.append(("transcript", "subtitle_document/source_transcript_ref"))',
            "            pass", ("IM-199",),
        ),
        SourceMutant(
            "VM-131", "Transcript ↔ TranslatedTranscript identity 붕괴 검사 제거", target,
            "        and transcript_ref == translated_ref", "        and False", ("IM-201",),
        ),
        SourceMutant(
            "VM-132", "같은 artifact_id의 immutable metadata 일치 검사 제거", target,
            "            if ref.get(field) != original.get(field):", "            if False:",
            ("IM-202", "IM-203"),
        ),
        SourceMutant(
            "VM-133", "검증 컨텍스트 role 닫기 제거", target,
            "        if name not in REF_CONTEXT_ROLES:", "        if False:", ("IM-205",),
        ),
        SourceMutant(
            "VM-134", "검증 컨텍스트 ref의 공통 ArtifactRef 계약 검사 제거", target,
            """            findings.extend(
                redact_schema_findings(
                    validator.validate(
                        value[name], COMMON_SCHEMA_FILE, spot, pointer="/$defs/ArtifactRef"
                    )
                )
            )""",
            "            pass", ("IM-204",),
        ),
        SourceMutant(
            "VM-135", "검증 컨텍스트 ref의 문서 종류 결박 제거", target,
            "        findings.extend(_check_document_ref_shape(value[name], spot))",
            "        pass", ("IM-206",),
        ),
        # --- REVIEW-025 R-02: 비겹치는 입력 lineage --------------------------------
        SourceMutant(
            "VM-136", "입력 SpeechSegment 시간 겹침 검사 제거", target,
            "            if valid_time and not _overlaps(start, end, entry[0], entry[1]):",
            "            if False:", ("IM-207", "IM-208"),
        ),
        SourceMutant(
            "VM-137", "덮는 입력이 unlabeled일 때의 ambiguity 검사 제거", target,
            "    if unlabeled_evidence:", "    if False:", ("IM-209",),
        ),
        # --- REVIEW-025 R-03: translation code-switch --------------------------------
        SourceMutant(
            "VM-138", "translation code-switch capability 결박 제거", target,
            """        if (len(languages) > 1 or switched) and capability.get(
            "supports_code_switching_input"
        ) is not True:""",
            "        if False:", ("IM-210", "IM-211"),
        ),
        SourceMutant(
            "VM-139", "fragment 안쪽 intra-sentential 전환 판정 제거", target,
            '        if span.get("switch_kind") == "intra_sentential" and start < span_start < end:',
            "        if False:", ("IM-225",),
        ),
        # --- REVIEW-025 R-04: 임의 정밀도 숫자 ----------------------------------------
        SourceMutant(
            "VM-140", "int를 float로 강제 변환해 overflow를 되살린다", target,
            """    if not _is_number(value):
        return False
    if isinstance(value, int):
        return True
    return math.isfinite(value)""",
            "    return _is_number(value) and math.isfinite(float(value))",
            ("IM-212", "IM-213", "IM-215", "IM-218"),
        ),
        # --- REVIEW-025 R-05: location alias -----------------------------------------
        SourceMutant(
            "VM-141", "location 구간의 선언 어휘 allowlist 제거", target,
            "            if len(matches) != 1 or matches[0] not in _declared_children(position):",
            "            if len(matches) != 1:", ("LOCATION", "IM-221"),
        ),
        SourceMutant(
            "VM-142", "language tag 모양을 다시 비식별화 근거로 삼는다", target,
            "            if len(matches) != 1 or matches[0] not in _declared_children(position):",
            "            if len(matches) != 1 or not (\n                matches[0] in _declared_children(position)\n                or (matches[0][:2].isalpha() and matches[0][:2].islower())\n            ):",
            ("LOCATION", "IM-231", "IM-232"),
        ),
        # --- 오너 결정 option 3 (REVIEW-026 D-04): language span 정규형 --------------
        SourceMutant(
            "VM-144", "맞닿은 같은 언어 span의 정규형 검사 제거", target,
            "            if usable and usable[-1][1] == start and usable[-1][2] == tag:",
            "            if False:", ("IM-236", "IM-237"),
        ),
        SourceMutant(
            "VM-143", "container 조기 반환의 정규화 생략", target,
            """        # 조기 반환도 **같은 정규화**를 지난다 (REVIEW-025 R-05).
        return _finalize(container_findings, documents)""",
            "        return ValidationResult(findings=tuple(sort_findings(container_findings)))",
            ("LOCATION",),
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


def safe_pairs(documents: Any, schemas: SchemaSet) -> tuple[tuple[tuple[str, str], ...], str]:
    """검증을 돌리되 **예외를 그 case의 실패로 기록**한다 (REVIEW-025 R-04).

    validator가 특정 입력에서 예외를 내면 그것은 그 입력의 결함이지 감사 도구가 죽을 일이
    아니다. 예외를 잡아 두면 (a) 어떤 입력이 터졌는지 정확히 보고되고, (b) 나머지 정상
    case의 sentinel은 계속 실행돼 판정이 가려지지 않는다.
    """

    try:
        return tuple(sorted(validate_documents(documents, schemas).pairs)), ""
    except Exception as exc:  # noqa: BLE001 - 예외 자체가 결과다
        return (), f"{type(exc).__name__}: {exc}"[:200]


def _safe_result(documents: Any, schemas: SchemaSet) -> tuple[Any, str]:
    try:
        return validate_documents(documents, schemas), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"[:200]


def run_fixture_pass(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("k-*.json")):
        fixture = load_fixture(path)
        expected = tuple(sorted(
            (item["code"], item["location"])
            for item in fixture["expected"].get("findings") or []
        ))
        observed, crash = safe_pairs(fixture["documents"], schemas)
        mismatches: list[str] = []
        if crash:
            mismatches.append(f"검증이 예외로 중단됐다: {crash}")
        else:
            mismatches.extend(
                f"누락: {code}@{location}"
                for code, location in sorted(set(expected) - set(observed))
            )
            mismatches.extend(
                f"초과: {code}@{location}"
                for code, location in sorted(set(observed) - set(expected))
            )
        row: dict[str, Any] = {
            "case_id": str(fixture["case_id"]),
            "passed": not mismatches,
            "mismatches": mismatches,
        }
        if bool(fixture["expected"].get("valid")):
            # 정상 fixture는 그 자체가 valid-case sentinel이다 — 실제 결과를 센다.
            row["sentinel_ok"] = not crash and not observed
        rows.append(row)
    return rows


def run_input_mutations(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    register_mutations()
    sources = _base_documents(fixture_dir)
    results: list[dict[str, Any]] = []
    for mutation in MUTATIONS:
        documents = mutation.documents(sources)
        observed, crash = safe_pairs(documents, schemas)
        # valid-case sentinel — **변형하지 않은** 같은 문서 부분집합은 깨끗해야 한다.
        # 변형이 아니라 base나 keep 선택이 결함을 만든 경우를 여기서 잡는다.
        sentinel_pairs, sentinel_crash = safe_pairs(
            mutation.sentinel_documents(sources), schemas
        )
        results.append(
            {
                "mutation_id": mutation.mutation_id,
                "title": mutation.title,
                "base": BASE_CASES[mutation.base],
                "expected": [list(pair) for pair in mutation.expected],
                "observed": [list(pair) for pair in observed],
                "crash": crash,
                "passed": not crash and observed == mutation.expected,
                "sentinel_ok": not sentinel_crash and not sentinel_pairs,
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


def _resolves(documents: Any, location: str) -> bool:
    """location이 실제 입력에서 끝까지 해석되는지 (TASK-029 §8)."""

    node: Any = documents
    if location == "":
        return True
    for segment in location.split("/"):
        node = contracts._step(node, segment)
        if node is contracts._MISSING:
            return False
    return True


# ---------------------------------------------------------------------------
# 위치별 비식별화 oracle — production `safe_location()`과 **독립** (REVIEW-026 R-01)
# ---------------------------------------------------------------------------
#
# production은 location을 한 구간씩 따라가며 "이 자리의 어휘인가"를 그때그때 묻는다.
# 여기서는 반대 방향으로 만든다. 정본 schema를 먼저 **전부 펼쳐** 경로 패턴 집합
# (`transcript/streams/*/segments/*/text`)을 만들어 두고, finding location을 그 집합과
# 대조한다. production의 allowlist 함수·가정을 하나도 재사용하지 않는다.

#: 문서 집합 root의 합성 schema. 검증 컨텍스트 envelope의 role까지 여기서 고정한다.
_ORACLE_ROOT = {
    "properties": {
        "speech_segments": {"items": {"$ref": "speech-segment-v1.schema.json"}},
        "transcript": {"$ref": "transcript-v1.schema.json"},
        "translated_transcript": {"$ref": "translated-transcript-v1.schema.json"},
        "subtitle_document": {"$ref": "subtitle-document-v1.schema.json"},
        "document_refs": {
            "properties": {
                role: {"$ref": "common-v1.schema.json#/$defs/ArtifactRef"}
                for role in contracts.REF_CONTEXT_ROLES
            }
        },
    }
}

_ORACLE_PATTERNS: frozenset[str] | None = None


def _oracle_schema_documents() -> dict[str, Any]:
    return {
        name: json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        for name in contracts.SCHEMA_FILES
    }


def declared_path_patterns() -> frozenset[str]:
    """정본이 선언한 **경로 패턴**의 전수 집합. 배열 index는 `*`다.

    `patternProperties`는 펼치지 않는다. 그 자리의 key는 입력이 정하므로 어떤 모양이든
    location에 남으면 안 된다 (REVIEW-026 R-01 2번).
    """

    global _ORACLE_PATTERNS
    if _ORACLE_PATTERNS is not None:
        return _ORACLE_PATTERNS

    documents = _oracle_schema_documents()

    def resolve(node: Any, file: str) -> tuple[Any, str]:
        for _ in range(16):
            if not isinstance(node, Mapping) or "$ref" not in node:
                return node, file
            target, _, fragment = str(node["$ref"]).partition("#")
            file = target or file
            node = documents.get(file)
            for token in fragment.split("/"):
                if not token:
                    continue
                if not isinstance(node, Mapping) or token not in node:
                    return None, file
                node = node[token]
        return None, file  # pragma: no cover - 순환 $ref 방어

    patterns: set[str] = set()

    def expand(node: Any, file: str, path: str, seen: frozenset[tuple[str, int]]) -> None:
        node, file = resolve(node, file)
        if not isinstance(node, Mapping):
            return
        mark = (file, id(node))
        if mark in seen or len(seen) > 40:
            return
        seen = seen | {mark}
        properties = node.get("properties")
        if isinstance(properties, Mapping):
            for name, child in properties.items():
                child_path = f"{path}/{name}" if path else name
                patterns.add(child_path)
                expand(child, file, child_path, seen)
        items = node.get("items")
        if items is not None:
            child_path = f"{path}/*" if path else "*"
            patterns.add(child_path)
            expand(items, file, child_path, seen)

    expand(_ORACLE_ROOT, contracts.COMMON_SCHEMA_FILE, "", frozenset())
    _ORACLE_PATTERNS = frozenset(patterns)
    return _ORACLE_PATTERNS


def oracle_location_problem(documents: Any, location: str) -> str | None:
    """location이 계약상 안전한가. 안전하면 `None`, 아니면 이유 문자열."""

    if location == "":
        return None
    parts = location.split("/")
    node: Any = documents
    pattern: list[str] = []
    for index, part in enumerate(parts):
        remainder = "/".join(parts[index:])
        if isinstance(node, Mapping):
            if part not in node:
                return "구간이 실제 입력의 key가 아니다"
            for key in node:
                if key != part and (remainder == key or remainder.startswith(key + "/")):
                    return "다른 key와 alias된다"
            node = node[part]
            pattern.append(part)
        elif isinstance(node, list):
            if not part.isdigit() or not 0 <= int(part) < len(node):
                return "배열 index가 아니다"
            node = node[int(part)]
            pattern.append("*")
        else:
            return "더 내려갈 수 없는 노드다"
    if "/".join(pattern) not in declared_path_patterns():
        return "정본이 이 경로에서 선언하지 않은 이름이다"
    return None


def oracle_dynamic_keys(documents: Any) -> set[str]:
    """정본이 그 자리에서 선언하지 않은 **입력 제어 mapping key** 전수 (REVIEW-026 R-01 4번).

    이전 판은 텍스트 field 값만 민감 후보로 모아서 `patient`·`en-x-secret` 같은 key 자체가
    message에 실려도 잡지 못했다.
    """

    patterns = declared_path_patterns()
    found: set[str] = set()

    def walk(node: Any, pattern: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                child = f"{pattern}/{key}" if pattern else str(key)
                if child not in patterns:
                    found.add(str(key))
                    continue
                walk(value, child)
        elif isinstance(node, list):
            child = f"{pattern}/*" if pattern else "*"
            for item in node:
                walk(item, child)

    walk(documents, "")
    return found


def _leak_hits(documents: Any, findings: Sequence[Any]) -> list[tuple[str, str]]:
    """finding의 **message와 location** 모두에 입력 값이 새지 않았는지 본다.

    계약은 `(code, location)`이고 message는 사람용 설명이다. 둘 중 어느 쪽이든 입력 값을
    그대로 실으면 로그·리포트가 원문 유출 경로가 된다 (REVIEW-023 B-02, REVIEW-024 H-06).
    message만 씻으면 dynamic key가 location으로 샌다.

    `(kind, 설명)` 목록을 돌려준다. `kind`는 감사에서 kill id로 쓴다.
    """

    texts: set[str] = set()
    _text_values(documents, texts)
    # 세 scalar 미만은 조사·기호와 우연히 겹칠 수 있어 **message 판정**에서 뺀다.
    # location은 길이와 무관하게 아래 oracle이 전수로 막는다.
    texts = {value for value in texts if len(value) >= 3}
    texts.add(SENSITIVE_PROBE)
    # 동적 mapping key도 민감 후보다. `patient`·`en-x-secret`는 값이 아니라 key로 들어온다.
    message_values = texts | {key for key in oracle_dynamic_keys(documents) if len(key) >= 3}

    hits: list[tuple[str, str]] = []
    for finding in findings:
        where = f"{finding.code}@{finding.location}"
        if any(value in finding.message for value in message_values):
            hits.append(("LEAK", f"{where}: message에 입력 텍스트·동적 key 노출"))
        elif any(marker in finding.message for marker in _PATH_MARKERS):
            hits.append(("LEAK", f"{where}: message에 절대 경로 노출"))

        hits.extend(_location_hits(documents, finding, texts, where))
    return hits


def _location_hits(
    documents: Any, finding: Any, values: set[str], where: str
) -> list[tuple[str, str]]:
    """location이 사용자 제어 key를 담거나 다른 노드로 alias되지 않았는지.

    판정은 **production `safe_location()`을 부르지 않고** 독립 oracle로 한다. 이전 판은
    production과 같은 전역 `declared_segments()`·language-tag 가정을 공유해서, 그 가정
    자체가 틀린 반례(다른 위치의 정본 field 이름, BCP-47 private-use key)를 전부 안전하다고
    판정했다 (REVIEW-026 R-01).
    """

    location = finding.location
    hits: list[tuple[str, str]] = []
    if location == "":
        return hits

    problem = oracle_location_problem(documents, location)
    if problem is not None:
        hits.append(("LOCATION", f"{where}: {problem}"))
        return hits
    if any(value in location for value in values) or any(
        marker in location for marker in _PATH_MARKERS
    ):
        hits.append(("LOCATION", f"{where}: location에 입력 텍스트·경로 노출"))
    elif not _resolves(documents, location):
        hits.append(("LOCATION", f"{where}: location이 실제 입력에서 해석되지 않는다"))
    return hits


def run_leak_scan(schemas: SchemaSet, fixture_dir: Path) -> list[dict[str, Any]]:
    register_mutations()
    sources = _base_documents(fixture_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("k-*.json")):
        fixture = load_fixture(path)
        result, crash = _safe_result(fixture["documents"], schemas)
        hits = [] if crash else _leak_hits(fixture["documents"], result.findings)
        row: dict[str, Any] = {
            "leak_id": str(fixture["case_id"]),
            "passed": not hits,
            "kinds": sorted({kind for kind, _ in hits}),
            "hits": [note for _, note in hits][:4],
        }
        if bool(fixture["expected"].get("valid")):
            # 정상 fixture는 finding이 없어야 한다 — 스캔 자체의 valid-case sentinel.
            row["sentinel_ok"] = not crash and not result.findings
        rows.append(row)
    for mutation in MUTATIONS:
        documents = mutation.documents(sources)
        result, crash = _safe_result(documents, schemas)
        hits = [] if crash else _leak_hits(documents, result.findings)
        rows.append(
            {
                "leak_id": mutation.mutation_id,
                "passed": not hits,
                "kinds": sorted({kind for kind, _ in hits}),
                "hits": [note for _, note in hits][:4],
            }
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
        try:
            unit_observed = tuple(
                sorted((finding.code, finding.location) for finding in probe.unit())
            )
        except Exception as exc:  # noqa: BLE001 - depth probe가 터지는 것도 결과다
            unit_observed = ((type(exc).__name__, str(exc)[:80]),)
        documents = copy.deepcopy(sources[probe.base])
        probe.patch(documents)
        documents = {key: documents[key] for key in probe.keep if key in documents}
        shadow_observed, shadow_crash = safe_pairs(documents, schemas)
        rows.append(
            {
                "probe_id": probe.probe_id,
                "title": probe.title,
                "passed": not shadow_crash
                and unit_observed == (probe.unit_expected,)
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

    # 비객체 root는 fixture로 만들 수 없다 (fixture 자체가 객체를 담는다). raw JSON 경계와
    # 같은 입력을 여기서도 통과시켜 그 방어면이 실제로 발화하게 한다 (REVIEW-026 R-02c).
    payloads += [[], None, 7, "x"]

    probes = depth_probes()
    boundary = _boundary_cases(sources)
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        for documents in payloads:
            validate_documents(documents, schemas)
        # 심층 방어는 문서 경로로 도달하지 않는다. 단위 호출로 실제 발화시킨다.
        for probe in probes:
            probe.unit()
        # 공개 경계의 정규화도 방어면이다 — 직접 호출로 발화시킨다.
        for _, _, call in boundary:
            call()
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


# ---------------------------------------------------------------------------
# raw JSON 입력 경계 probe (REVIEW-026 R-02)
# ---------------------------------------------------------------------------
#
# 여기서 보는 것은 **파일 계약**이다. in-memory mutation은 이미 파싱된 Python 객체를 넣기
# 때문에 숫자 리터럴·문서 root 타입 문제를 절대 재현하지 못한다.

_OVER_LIMIT_DIGITS = "1" * 4301
_HUGE_DIGITS = "9" * 10000


def _raw_fixture(documents_literal: str) -> str:
    return (
        '{"case_id":"K-01","title":"raw probe",'
        '"expected":{"valid":true,"findings":[]},'
        f'"documents":{documents_literal}}}'
    )


#: `(probe_id, 설명, raw JSON 본문, 기대)`.
#: 기대는 `("profile", …)` = `num-profile-v1` 거부, `("input", …)` = 그 밖의 안정 입력 오류,
#: `("pairs", [...])` = 파싱 성공 뒤 정확한 `(code, location)` 집합.
_RAW_PROBES: tuple[tuple[str, str, str, tuple[str, Any]], ...] = (
    ("RJ-01", "4,301자리 양의 정수", _raw_fixture('{"speech_segments":[%s]}' % _OVER_LIMIT_DIGITS),
     ("profile", None)),
    ("RJ-02", "4,301자리 음의 정수", _raw_fixture('{"speech_segments":[-%s]}' % _OVER_LIMIT_DIGITS),
     ("profile", None)),
    ("RJ-03", "10,000자리 양의 정수", _raw_fixture('{"speech_segments":[%s]}' % _HUGE_DIGITS),
     ("profile", None)),
    ("RJ-04", "10,000자리 음의 정수", _raw_fixture('{"speech_segments":[-%s]}' % _HUGE_DIGITS),
     ("profile", None)),
    ("RJ-05", "4,300자리 정수는 profile 안이다 — 경계가 정확하다",
     _raw_fixture('{"speech_segments":%s}' % ("1" * 4300)),
     ("pairs", [("E_SCHEMA", "speech_segments")])),
    ("RJ-06", "confidence 1.0000000000000001이 1.0으로 반올림된다",
     _raw_fixture('{"transcript":{"confidence":1.0000000000000001}}'), ("profile", None)),
    ("RJ-07", "시작 시각 -1e-400이 -0.0으로 반올림된다",
     _raw_fixture('{"speech_segments":[{"start_seconds":-1e-400}]}'), ("profile", None)),
    ("RJ-08", "min_gap_seconds -1e-400이 -0.0으로 반올림된다",
     _raw_fixture('{"subtitle_document":{"resolved_style":{"min_gap_seconds":-1e-400}}}'),
     ("profile", None)),
    ("RJ-09", "max_cps 1e-400이 0.0으로 반올림된다",
     _raw_fixture('{"subtitle_document":{"resolved_style":{"max_cps":1e-400}}}'),
     ("profile", None)),
    ("RJ-10", "1e400은 binary64에서 유한하지 않다",
     _raw_fixture('{"speech_segments":[{"start_seconds":1e400}]}'), ("profile", None)),
    ("RJ-11", "정상 표기 decimal은 profile이 막지 않는다",
     _raw_fixture('{"speech_segments":[{"start_seconds":0.1,"end_seconds":0.30000000000000004}]}'),
     ("pairs", None)),
    ("RJ-12", "documents가 빈 배열이다", _raw_fixture("[]"), ("pairs", [("E_SCHEMA", "")])),
    ("RJ-13", "documents가 null이다", _raw_fixture("null"), ("pairs", [("E_SCHEMA", "")])),
    ("RJ-14", "documents가 정수다", _raw_fixture("7"), ("pairs", [("E_SCHEMA", "")])),
    ("RJ-15", "JSON 구문 오류", '{"case_id": ', ("input", None)),
    ("RJ-16", "중복 key", _raw_fixture('{"transcript":{},"transcript":{}}'), ("input", None)),
    ("RJ-17", "NaN 상수", _raw_fixture('{"speech_segments":[{"start_seconds":NaN}]}'),
     ("input", None)),
)


def run_raw_input_probes(schemas: SchemaSet) -> list[dict[str, Any]]:
    """raw JSON 본문이 traceback 없이 **안정 종료**하는지 (REVIEW-026 R-02).

    profile 거부는 schema 범위 위반과 다른 축이므로 그 구분까지 함께 고정한다.
    """

    rows: list[dict[str, Any]] = []
    for probe_id, title, text, (kind, expected) in _RAW_PROBES:
        note = ""
        try:
            fixture = contracts.loads_documents(text)
        except contracts.NumberProfileError as exc:
            observed, note = "profile", str(exc)
            fixture = None
        except contracts.JsonInputError as exc:
            observed, note = "input", str(exc)
            fixture = None
        except Exception as exc:  # noqa: BLE001 - traceback으로 끝나면 그 자체가 실패다
            observed, note = "crash", f"{type(exc).__name__}: {exc}"
            fixture = None
        else:
            observed = "pairs"

        pairs: list[list[str]] | None = None
        if observed == "pairs":
            try:
                result = validate_documents(fixture["documents"], schemas)
                pairs = sorted([code, location] for code, location in result.pairs)
            except Exception as exc:  # noqa: BLE001
                observed, note = "crash", f"{type(exc).__name__}: {exc}"

        passed = observed == kind
        if passed and kind == "pairs" and expected is not None:
            passed = pairs == sorted([code, location] for code, location in expected)
        rows.append({
            "probe_id": probe_id,
            "title": title,
            "expected": kind,
            "observed": observed,
            "pairs": pairs,
            "passed": passed,
            "note": note if not passed else "",
        })
    return rows


# ---------------------------------------------------------------------------
# 공개 validator 경계 probe (REVIEW-026 R-01 3번)
# ---------------------------------------------------------------------------
#
# `validate_documents()`만 접으면 `check_subtitle_document()`를 직접 부른 소비자에게는
# 같은 raw key가 그대로 간다. 공개 진입점 각각을 직접 호출해 확인한다.


def _boundary_cases(sources: dict[str, dict]) -> list[tuple[str, str, Callable[[], Any]]]:
    documents = copy.deepcopy(sources["base"])
    subtitle = documents["subtitle_document"]
    subtitle["resolved_style"]["language_overrides"]["en-x-secret"] = {"max_cps": -1}
    refs = dict(documents.get(contracts.REF_CONTEXT_KEY) or {})
    refs["speaker_label"] = SENSITIVE_PROBE
    leaky_documents = dict(documents)
    leaky_documents[contracts.REF_CONTEXT_KEY] = refs
    segments = copy.deepcopy(documents["speech_segments"])
    transcript = copy.deepcopy(documents["transcript"])
    translated = copy.deepcopy(documents["translated_transcript"])
    return [
        ("PB-01", "check_subtitle_document",
         lambda: contracts.check_subtitle_document(subtitle, transcript, translated)),
        ("PB-02", "check_transcript",
         lambda: contracts.check_transcript(transcript, segments)),
        ("PB-03", "check_speech_segments",
         lambda: contracts.check_speech_segments(segments)),
        ("PB-04", "check_translated_transcript",
         lambda: contracts.check_translated_transcript(translated, transcript)),
        ("PB-05", "check_asr_capability_binding",
         lambda: contracts.check_asr_capability_binding(transcript)),
        ("PB-06", "check_translation_capability_binding",
         lambda: contracts.check_translation_capability_binding(translated, transcript=transcript)),
        ("PB-07", "check_document_ref_identity",
         lambda: contracts.check_document_ref_identity(leaky_documents, refs)),
        ("PB-08", "check_artifact_consistency",
         lambda: contracts.check_artifact_consistency(leaky_documents)),
    ]


def run_boundary_probes(fixture_dir: Path) -> list[dict[str, Any]]:
    sources = _base_documents(fixture_dir)
    rows: list[dict[str, Any]] = []
    for probe_id, title, call in _boundary_cases(sources):
        try:
            findings = call()
        except Exception as exc:  # noqa: BLE001
            rows.append({"probe_id": probe_id, "title": title, "passed": False,
                         "note": f"{type(exc).__name__}: {exc}"})
            continue
        bad = [
            f"{finding.code}@{finding.location}"
            for finding in findings
            if _unsafe_public_location(finding.location)
        ]
        rows.append({
            "probe_id": probe_id, "title": title, "passed": not bad,
            "note": "; ".join(bad[:3]),
        })
    return rows


def _unsafe_public_location(location: str) -> bool:
    """공개 경계가 돌려준 location에 정본이 선언하지 않은 구간이 남았는가.

    문서 하나만 받은 호출이라 입력을 따라가는 대신 **경로 패턴 집합**과 직접 대조한다.
    """

    if location == "":
        return False
    pattern = "/".join("*" if part.isdigit() else part for part in location.split("/"))
    return pattern not in declared_path_patterns()


def _check_only(fixture_dir: Path, schema_dir: Path) -> dict[str, Any]:
    """임시 사본에서도 같은 것을 돌린다.

    depth probe가 여기 들어가야 **depth 방어만 지운 mutant**가 죽는다. production에서 4/4
    통과하는 것만으로는 그 방어가 살아 있다는 증거가 되지 못한다 (REVIEW-024 E).
    raw JSON probe와 공개 경계 probe도 같은 이유로 여기 있다 (REVIEW-026 R-01·R-02).
    """

    schemas = SchemaSet(schema_dir)
    return {
        "fixtures": run_fixture_pass(schemas, fixture_dir),
        "mutations": run_input_mutations(schemas, fixture_dir),
        "leaks": run_leak_scan(schemas, fixture_dir),
        "depth_probes": run_depth_probes(schemas, fixture_dir),
        "raw_probes": run_raw_input_probes(schemas),
        "boundary_probes": run_boundary_probes(fixture_dir),
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
            # 비노출 스캔은 kind별 kill id(`LEAK`·`LOCATION`)로 모은다.
            failed_leaks: set[str] = set()
            for item in observed.get("leaks", []):
                if not item["passed"]:
                    failed_leaks |= set(item.get("kinds") or ["LEAK"])
            # depth probe도 mutant 실행에서 함께 돌아야 depth-only 방어가 죽는다.
            failed_depth = {
                item["probe_id"]
                for item in observed.get("depth_probes", [])
                if not item["passed"]
            }
            # mutant 실행에서 관측된 sentinel 실패도 이 mutant의 sentinel 실패다.
            sentinel_ok = not (valid_cases & failed_cases) and not bad_sentinels(observed)
            expected_kills = set(mutant.kills)
            caught = failed_cases | failed_mutations | failed_leaks | failed_depth
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


#: `--check-only` 결과에서 sentinel을 들고 있는 분모와 그 row의 ID field.
_SENTINEL_SECTIONS = (
    ("fixtures", "case_id"),
    ("mutations", "mutation_id"),
    ("leaks", "leak_id"),
)


def bad_sentinels(payload: dict[str, Any]) -> list[str]:
    """실제로 실패한 valid-case sentinel 목록.

    이전 판은 `passed`만 보고 `sentinel_ok`를 성공 조건에서 뺐다. 그래서 출력에는
    sentinel 실패가 찍히는데 process는 exit 0이었다 (REVIEW-024 H-05).
    """

    bad: list[str] = []
    for section, id_field in _SENTINEL_SECTIONS:
        for row in payload.get(section, []):
            if row.get("sentinel_ok") is False:
                bad.append(f"{section}:{row.get(id_field)}")
    return sorted(bad)


def _all_passed(payload: dict[str, Any]) -> bool:
    """`--check-only`와 전체 audit가 **같은** 성공 조건을 쓴다 (REVIEW-024 H-05)."""

    return (
        all(case["passed"] for case in payload.get("fixtures", []))
        and all(item["passed"] for item in payload.get("mutations", []))
        and all(item["passed"] for item in payload.get("leaks", []))
        and all(item["passed"] for item in payload.get("depth_probes", []))
        and all(item["passed"] for item in payload.get("raw_probes", []))
        and all(item["passed"] for item in payload.get("boundary_probes", []))
        and not bad_sentinels(payload)
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
    subsumed = sum(1 for row in rows if row.get("subsumed"))
    return {
        "subsumed": subsumed,
        "name": name,
        "total": total,
        "detected": detected,
        "kill_rate": (detected / total) if total else 1.0,
        "sentinel_total": len(sentinel_rows),
        "sentinel_passed": sum(1 for row in sentinel_rows if row["sentinel_ok"]),
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# REVIEW-024 G — 같은 transformation을 두 mutant로 세지 않는다
# ---------------------------------------------------------------------------


def duplicate_transformations() -> list[list[str]]:
    """`(target, old, new)`가 같은 mutant 묶음. 하나라도 있으면 분모가 부풀려진 것이다."""

    seen: dict[tuple[str, str, str], list[str]] = {}
    for mutant in list(schema_mutants()) + list(validator_mutants()):
        seen.setdefault((mutant.target, mutant.old, mutant.new), []).append(mutant.mutant_id)
    return [ids for ids in seen.values() if len(ids) > 1]


def unique_transformation_count(schema_dir: Path = SCHEMA_DIR) -> dict[str, int]:
    """보고 total이 **실제 고유 transformation 수**인지 확인할 수 있게 함께 낸다."""

    schema = {(m.target, m.old, m.new) for m in schema_mutants()}
    validator = {(m.target, m.old, m.new) for m in validator_mutants()}
    defenses = collect_schema_defenses(schema_dir)
    return {
        "schema_declared": len(schema_mutants()),
        "schema_unique": len(schema),
        "validator_declared": len(validator_mutants()),
        "validator_unique": len(validator),
        "defense_declared": len(defenses),
        "defense_unique": len({defense.defense_id for defense in defenses}),
        "duplicate_groups": len(duplicate_transformations()),
    }


# ---------------------------------------------------------------------------
# REVIEW-024 H-05 — sentinel 실패가 반드시 exit 1이어야 한다
# ---------------------------------------------------------------------------

#: 임시 사본에서 **sentinel만** 실패시키는 패치. 각각 `--check-only`가 1로 끝나야 한다.
_SELF_TESTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "AS-01", "input mutant sentinel만 실패시킨다",
        '                "passed": not crash and observed == mutation.expected,\n'
        '                "sentinel_ok": not sentinel_crash and not sentinel_pairs,',
        '                "passed": not crash and observed == mutation.expected,\n'
        '                "sentinel_ok": False,',
    ),
    (
        "AS-02", "fixture sentinel만 실패시킨다",
        "            # 정상 fixture는 그 자체가 valid-case sentinel이다 — 실제 결과를 센다.\n"
        '            row["sentinel_ok"] = not crash and not observed',
        "            # 정상 fixture는 그 자체가 valid-case sentinel이다 — 실제 결과를 센다.\n"
        '            row["sentinel_ok"] = False',
    ),
    (
        "AS-03", "leak scan sentinel만 실패시킨다",
        "            # 정상 fixture는 finding이 없어야 한다 — 스캔 자체의 valid-case sentinel.\n"
        '            row["sentinel_ok"] = not crash and not result.findings',
        "            # 정상 fixture는 finding이 없어야 한다 — 스캔 자체의 valid-case sentinel.\n"
        '            row["sentinel_ok"] = False',
    ),
)

#: `--write-manifest`가 불일치 파일을 만들면 **스스로** nonzero로 끝나야 한다
#: (REVIEW-026 R-03 2번). 갱신 도구가 digest를 잘못 쓰도록 훼손하고 exit code를 본다.
_WRITER_SELF_TESTS: tuple[tuple[str, str, str, str, tuple[str, ...], int], ...] = (
    (
        "AS-04", "갱신 도구가 목록과 다른 digest를 쓰면 write 자체가 실패한다",
        "            \"갱신은 이 파일의 명시적 diff로만 한다.\"\n"
        "        ),\n"
        '        "digest": _manifest_digest(killable, equivalent),',
        "            \"갱신은 이 파일의 명시적 diff로만 한다.\"\n"
        "        ),\n"
        '        "digest": "sha256:" + "0" * 64,',
        ("--write-manifest",), 1,
    ),
)


def run_audit_self_tests() -> list[dict[str, Any]]:
    """감사 자체를 감사한다.

    이전 판은 `sentinel_ok`를 출력만 하고 성공 조건에서 뺐다. sentinel만 실패시킨 사본이
    exit 0으로 끝나는 것을 리뷰가 재현했다 (REVIEW-024 H-05). 이 자기검증은 그 반례를
    감사 안에 고정한다. 저장소 파일은 바꾸지 않는다.
    """

    script = Path("scripts/verify_task_029.py")
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mcs-029-selftest-") as tmp:
        root = Path(tmp) / "tree"
        shutil.copytree(
            REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
        )
        baseline = _run_check_only_code(root)
        if baseline != 0:
            return [{
                "selftest_id": "BASELINE", "title": "임시 사본 baseline",
                "passed": False, "note": f"baseline exit={baseline} (0이어야 한다)",
            }]
        path = root / script
        original = path.read_text(encoding="utf-8")
        cases = [
            (selftest_id, title, old, new, ("--check-only",), 1)
            for selftest_id, title, old, new in _SELF_TESTS
        ] + list(_WRITER_SELF_TESTS)
        for selftest_id, title, old, new, args, expect in cases:
            if original.count(old) != 1:
                rows.append({
                    "selftest_id": selftest_id, "title": title, "passed": False,
                    "note": f"패치 anchor가 {original.count(old)}회 — 자기검증 불가",
                })
                continue
            path.write_text(original.replace(old, new), encoding="utf-8")
            code = _run_script_code(root, *args)
            path.write_text(original, encoding="utf-8")
            rows.append({
                "selftest_id": selftest_id, "title": title, "passed": code == expect,
                "exit_code": code,
                "note": "" if code == expect
                else f"감사 자신을 훼손했는데 exit={code} ({expect}이어야 한다)",
            })
    return rows


def _run_check_only_code(root: Path) -> int:
    return _run_script_code(root, "--check-only")


# ---------------------------------------------------------------------------
# REVIEW-024 H-04 — production schema 방어 inventory (수동 표본이 아니다)
# ---------------------------------------------------------------------------

_RANGE_KEYWORDS = (
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "minItems", "maxItems",
)

#: inventory 대상 — TASK-029가 새로 만든 다섯 정본만이다. `common-v1`은 수정 금지다.
INVENTORY_FILES = (
    "speech-segment-v1.schema.json",
    "adapter-capability-report-v1.schema.json",
    "transcript-v1.schema.json",
    "translated-transcript-v1.schema.json",
    "subtitle-document-v1.schema.json",
)

#: instance 탐색에 쓰는 정상 fixture. 위반 입력은 여기서 파생한다.
_INVENTORY_BASES = ("base", "partial", "mini", "coverage")

#: 한 노드에서 서로를 함의할 수 있는 제약 keyword.
_CONSTRAINT_KEYWORDS = (
    "pattern", "enum", "const", "uniqueItems", "type",
) + _RANGE_KEYWORDS


def _is_subsumed(
    defense: SchemaDefense, documents: dict, expected: str, schema_dir: Path
) -> bool:
    """이 방어를 지워도 잡히는 이유가 **같은 노드의 다른 제약**뿐인지 확인한다."""

    with tempfile.TemporaryDirectory(prefix="mcs-029-subsume-") as tmp:
        work = Path(tmp) / "schemas"
        shutil.copytree(schema_dir, work)
        document = json.loads((work / defense.schema_file).read_text(encoding="utf-8"))
        node = _schema_node(document, defense.pointer)
        for keyword in _CONSTRAINT_KEYWORDS:
            node.pop(keyword, None)
        node.pop("required", None)
        (work / defense.schema_file).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        try:
            stripped = SchemaSet(work)
        except Exception:  # noqa: BLE001
            return False
        return ("E_SCHEMA", expected) not in set(validate_documents(documents, stripped).pairs)


_PROBE_KEY = "x_probe_defense"
_PROBE_ENUM = "x-probe-not-in-enum"


@dataclass(frozen=True)
class SchemaDefense:
    """production schema가 **기계적으로** 선언한 방어 하나.

    `defense_id`는 좌표(`파일#/pointer|keyword`)이고, `fingerprint`는 그 자리의 **의미값**이다.
    좌표만 고정하면 enum에 값을 하나 더 넣거나 `minimum`을 낮추거나 pattern을 바꿔도
    "drift 0"으로 통과한다 (REVIEW-026 R-03).
    """

    defense_id: str
    schema_file: str
    pointer: tuple[str, ...]
    kind: str
    fingerprint: str

    @property
    def is_root_required(self) -> bool:
        return self.kind.startswith("required:") and not self.pointer


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _defense_fingerprint(node: Mapping[str, Any], kind: str) -> str:
    """이 방어의 canonical 의미값. 값이 바뀌면 manifest diff 없이는 통과할 수 없다."""

    if kind.startswith("required:"):
        return f"required={kind.split(':', 1)[1]}"
    if kind == "enum":
        values = node.get("enum")
        canonical = sorted(_canonical(item) for item in values) if isinstance(values, list) else []
        return "enum=[" + ",".join(canonical) + "]"
    if kind == "closed":
        # 닫힌 객체의 의미값은 **허용되는 이름의 집합**이다. 새 property나 새 pattern이
        # 조용히 들어오면 그 객체는 그만큼 덜 닫힌 것이다.
        allowed: list[str] = []
        for container in ("properties", "patternProperties"):
            child = node.get(container)
            if isinstance(child, Mapping):
                allowed.extend(f"{container}:{name}" for name in child)
        return "closed=[" + ",".join(sorted(allowed)) + "]"
    if kind == "uniqueItems":
        return "uniqueItems=true"
    if kind == "pattern":
        return "pattern=" + _canonical(node.get("pattern"))
    if kind.startswith("range:"):
        keyword = kind.split(":", 1)[1]
        return f"{keyword}=" + _canonical(node.get(keyword))
    return "unknown"  # pragma: no cover - kind는 위에서 모두 다룬다


def collect_schema_defenses(schema_dir: Path) -> list[SchemaDefense]:
    """다섯 정본의 required·enum·범위·닫힌 객체·pattern·uniqueItems를 전수 수집한다.

    사람이 고른 표본이 아니라 schema 자신에서 뽑는다. 새 `required` 필드가 생기면 이
    목록이 저절로 늘고, 대응 mutation이 없으면 감사가 실패한다 (REVIEW-024 H-04).
    같은 `required` 이름을 두 번 적으면 같은 `defense_id`가 두 번 나오고, 그 중복 자체가
    manifest 검사 실패다 (REVIEW-026 R-03).
    """

    defenses: list[SchemaDefense] = []
    for name in INVENTORY_FILES:
        document = json.loads((schema_dir / name).read_text(encoding="utf-8"))

        def walk(node: Any, pointer: tuple[str, ...]) -> None:
            if not isinstance(node, dict):
                return
            kinds: list[str] = []
            required = node.get("required")
            if isinstance(required, list):
                kinds.extend(f"required:{field}" for field in required)
            if "enum" in node:
                kinds.append("enum")
            if node.get("additionalProperties") is False:
                kinds.append("closed")
            if node.get("uniqueItems") is True:
                kinds.append("uniqueItems")
            if "pattern" in node:
                kinds.append("pattern")
            kinds.extend(f"range:{keyword}" for keyword in _RANGE_KEYWORDS if keyword in node)
            for kind in kinds:
                defenses.append(
                    SchemaDefense(
                        defense_id=f"{name.split('-v1')[0]}#/{'/'.join(pointer)}|{kind}",
                        schema_file=name,
                        pointer=pointer,
                        kind=kind,
                        fingerprint=_defense_fingerprint(node, kind),
                    )
                )
            for container in ("properties", "$defs", "patternProperties"):
                child = node.get(container)
                if isinstance(child, dict):
                    for key, value in child.items():
                        walk(value, pointer + (container, key))
            for single in ("items", "propertyNames"):
                if single in node:
                    walk(node[single], pointer + (single,))
            if isinstance(node.get("additionalProperties"), dict):
                walk(node["additionalProperties"], pointer + ("additionalProperties",))

        walk(document, ())
    return defenses


def _schema_node(document: Any, pointer: Sequence[str]) -> Any:
    node = document
    for token in pointer:
        node = node[token]
    return node


def instance_paths(
    schemas: SchemaSet, documents: Mapping[str, Any]
) -> dict[tuple[str, tuple[str, ...]], list[str]]:
    """schema 노드 → 실제 문서 안에서 그 노드가 적용되는 위치 목록.

    `$ref`를 따라가되 기록은 **정의된 파일·pointer** 기준이다. inventory가 schema 문서
    좌표로 모이므로 둘이 정확히 맞물린다.
    """

    found: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    seen: set[tuple[str, tuple[str, ...], str]] = set()

    def walk(node: Any, file: str, pointer: tuple[str, ...], value: Any, where: str) -> None:
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            ref = node["$ref"]
            target, target_file = schemas.resolve(ref, file)
            fragment = ref.partition("#")[2]
            target_pointer = tuple(token for token in fragment.split("/") if token)
            walk(target, target_file, target_pointer, value, where)
            return
        key = (file, pointer, where)
        if key in seen:
            return
        seen.add(key)
        found.setdefault((file, pointer), []).append(where)
        properties = node.get("properties")
        if isinstance(properties, dict) and isinstance(value, Mapping):
            for name, child in properties.items():
                if name in value:
                    walk(child, file, pointer + ("properties", name), value[name],
                         f"{where}/{name}")
        pattern_properties = node.get("patternProperties")
        if isinstance(pattern_properties, dict) and isinstance(value, Mapping):
            for name in value:
                if isinstance(properties, dict) and name in properties:
                    continue
                # `schema_core`와 같은 규칙 — 처음 일치하는 pattern 하나만 적용한다.
                for pattern, child in pattern_properties.items():
                    if re.search(pattern, name) is not None:
                        walk(child, file, pointer + ("patternProperties", pattern),
                             value[name], f"{where}/{name}")
                        break
        items = node.get("items")
        if items is not None and isinstance(value, list):
            for index, item in enumerate(value):
                walk(items, file, pointer + ("items",), item, f"{where}/{index}")

    for key, schema_file in DOCUMENT_KEYS.items():
        if key not in documents:
            continue
        root = schemas.documents[schema_file]
        if key == "speech_segments":
            for index, segment in enumerate(documents[key]):
                walk(root, schema_file, (), segment, f"{key}/{index}")
        else:
            walk(root, schema_file, (), documents[key], key)
    return found


def _weaken(document: Any, defense: SchemaDefense) -> None:
    node = _schema_node(document, defense.pointer)
    kind = defense.kind
    if kind.startswith("required:"):
        field = kind.split(":", 1)[1]
        node["required"] = [name for name in node["required"] if name != field]
    elif kind == "enum":
        node["enum"] = list(node["enum"]) + [_PROBE_ENUM]
    elif kind == "closed":
        node["additionalProperties"] = True
    elif kind == "uniqueItems":
        node.pop("uniqueItems")
    elif kind == "pattern":
        node.pop("pattern")
    elif kind.startswith("range:"):
        node.pop(kind.split(":", 1)[1])
    else:  # pragma: no cover - 위 목록이 전부다
        raise AssertionError(kind)


def _violation_candidates(node: Mapping[str, Any], kind: str, current: Any) -> list[Any]:
    """방어를 깨는 후보 값. 같은 노드의 다른 방어에 걸리지 않는 것을 생성·검사로 고른다."""

    if kind == "enum":
        return [_PROBE_ENUM]
    if kind == "pattern":
        length = max(int(node.get("minLength", 1)), 1)
        return ["!" * length, "9" * length, "_" * length, "!!probe!!"]
    if kind == "uniqueItems":
        return [list(current) + [copy.deepcopy(current[0])]] if isinstance(current, list) and current else []
    keyword = kind.split(":", 1)[1]
    bound = node[keyword]
    if keyword == "minimum":
        return [bound - 1]
    if keyword == "maximum":
        return [bound + 1]
    if keyword == "exclusiveMinimum":
        return [bound]
    if keyword == "exclusiveMaximum":
        return [bound]
    if keyword == "minLength":
        return ["a" * (bound - 1), "x-" + "a" * max(0, bound - 3), ""]
    if keyword == "maxLength":
        candidates: list[Any] = []
        if isinstance(current, str) and current:
            # pattern이 함께 걸린 노드는 길이만 늘린 더미 문자열이 pattern에 먼저 걸린다.
            # 실제 값에 유효한 접미사를 반복해 **pattern은 지키면서** 길이만 넘긴다.
            for suffix in ("-a", "a"):
                grown = current
                while len(grown) <= bound:
                    grown += suffix
                candidates.append(grown)
        candidates.extend(["a" * (bound + 1), "x-" + "a" * (bound - 1)])
        return candidates
    if keyword == "minItems":
        return [list(current)[: bound - 1]] if isinstance(current, list) else []
    if keyword == "maxItems":
        base = list(current) if isinstance(current, list) else []
        filler = copy.deepcopy(base[0]) if base else {}
        return [base + [copy.deepcopy(filler) for _ in range(bound + 1 - len(base))]]
    return []  # pragma: no cover


def _pointer_parent(where: str) -> tuple[str, str]:
    head, _, tail = where.rpartition("/")
    return head, tail


def _apply_at(documents: dict, where: str, mutate) -> None:
    """`where`가 가리키는 값을 `mutate(값)`의 결과로 바꾼다."""

    tokens = where.split("/")
    node: Any = documents
    for token in tokens[:-1]:
        node = node[int(token)] if isinstance(node, list) else node[token]
    last = tokens[-1]
    if isinstance(node, list):
        node[int(last)] = mutate(node[int(last)])
    else:
        node[last] = mutate(node[last])


def _delete_at(documents: dict, where: str, field: str) -> None:
    node: Any = documents
    for token in where.split("/"):
        node = node[int(token)] if isinstance(node, list) else node[token]
    node.pop(field, None)


def _read_at(documents: Any, where: str) -> Any:
    node: Any = documents
    for token in where.split("/"):
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _add_key_at(documents: dict, where: str, key: str) -> None:
    node = _read_at(documents, where)
    node[key] = {}


def run_schema_defense_inventory(fixture_dir: Path, schema_dir: Path) -> list[dict[str, Any]]:
    """모든 schema 방어를 하나씩 약화하고 대응 위반 입력이 통과해 버리는지 본다.

    각 방어마다 세 가지를 함께 요구한다.

    1. **위반 입력이 production schema에서 실제로 거부된다** — 방어가 살아 있다는 증거.
    2. **그 방어만 약화하면 더 이상 거부되지 않는다** — 다른 방어에 가려지지 않았다는 증거.
    3. **약화한 schema에서도 정상 fixture는 통과한다** — valid-case sentinel.
    """

    schemas = SchemaSet(schema_dir)
    sources = _base_documents(fixture_dir)
    defenses = collect_schema_defenses(schema_dir)
    maps = {name: instance_paths(schemas, documents) for name, documents in sources.items()}

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mcs-029-schema-") as tmp:
        work = Path(tmp) / "schemas"
        shutil.copytree(schema_dir, work)
        originals = {
            name: (work / name).read_text(encoding="utf-8") for name in INVENTORY_FILES
        }

        for defense in defenses:
            row: dict[str, Any] = {
                "defense_id": defense.defense_id,
                "schema_file": defense.schema_file,
                "kind": defense.kind,
                "root_required": defense.is_root_required,
                "detected": False,
                "sentinel_ok": False,
                "passed": False,
                "note": "",
            }
            sites = [
                (base, where)
                for base in _INVENTORY_BASES
                if base in maps
                for where in maps[base].get((defense.schema_file, defense.pointer), [])
            ]
            if not sites:
                row["note"] = "정상 fixture에 이 schema 노드의 instance가 없다"
                rows.append(row)
                continue

            document = json.loads(originals[defense.schema_file])
            _weaken(document, defense)
            (work / defense.schema_file).write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            try:
                weakened = SchemaSet(work)
            except Exception as exc:  # noqa: BLE001 - 약화가 계약을 깨면 그것도 결과다
                (work / defense.schema_file).write_text(
                    originals[defense.schema_file], encoding="utf-8"
                )
                row["note"] = f"약화한 schema를 읽을 수 없다: {exc}"
                rows.append(row)
                continue

            # 같은 schema 노드가 여러 위치에 적용된다. 어느 하나에서라도 실제로 깨지면
            # 그 방어는 살아 있다. 전부 실패하면 마지막 실패 사유를 남긴다.
            outcome: dict[str, Any] = {}
            base_name, where = sites[0]
            for candidate_base, candidate_where in sites:
                outcome = _probe_defense(
                    defense, sources[candidate_base], candidate_where, schemas, weakened, schema_dir
                )
                base_name, where = candidate_base, candidate_where
                if outcome.get("detected"):
                    break
            (work / defense.schema_file).write_text(
                originals[defense.schema_file], encoding="utf-8"
            )
            row["instance"] = where
            row.update(outcome)
            row["sentinel_ok"] = all(
                not validate_documents(sources[name], weakened).findings
                for name in _INVENTORY_BASES
                if name in sources
            )
            row["passed"] = bool(row["detected"] and row["sentinel_ok"])
            if not row["sentinel_ok"] and not row["note"]:
                row["note"] = "약화한 schema에서 정상 fixture가 거부됐다"
            rows.append(row)

    # killable / equivalent 분모를 **고정 allowlist 기준으로** 나눈다.
    # 단독 kill이 불가능한 방어를 killable 분모에 섞으면 kill rate가 부정확해진다
    # (REVIEW-025 R-06). allowlist가 조용히 늘거나 줄면 그 자체가 실패다.
    try:
        allowlist = {
            str(entry.get("defense_id"))
            for entry in (load_defense_manifest().get("equivalent") or [])
        }
    except (OSError, json.JSONDecodeError):  # pragma: no cover - MF-00이 따로 보고한다
        allowlist = set()
    for row in rows:
        declared = row["defense_id"] in allowlist
        row["equivalent"] = declared
        if declared != bool(row.get("subsumed")):
            row["passed"] = False
            row["note"] = (
                "equivalent allowlist에 있으나 실제로는 단독 kill이 가능하다"
                if declared
                else "단독 kill이 불가능한데 equivalent allowlist에 없다"
            )
    return rows


def _probe_defense(
    defense: SchemaDefense,
    base_documents: dict,
    where: str,
    schemas: SchemaSet,
    weakened: SchemaSet,
    schema_dir: Path,
) -> dict[str, Any]:
    kind = defense.kind
    node = _schema_node(json.loads((schema_dir / defense.schema_file).read_text(encoding="utf-8")),
                        defense.pointer)

    def attempt(build) -> dict[str, Any] | None:
        documents = copy.deepcopy(base_documents)
        try:
            expected = build(documents)
        except (KeyError, IndexError, TypeError):
            return None
        strict = {pair for pair in validate_documents(documents, schemas).pairs}
        if ("E_SCHEMA", expected) not in strict:
            return {"note": "위반 입력이 production schema에서 거부되지 않는다",
                    "expected_location": expected}
        loose = {pair for pair in validate_documents(documents, weakened).pairs}
        if ("E_SCHEMA", expected) in loose:
            if _is_subsumed(defense, documents, expected, schema_dir):
                # 같은 노드의 다른 keyword가 이 방어를 **수학적으로 함의**한다
                # (예: `^[a-z]{2,8}…$` pattern은 minLength 2를 이미 보장한다).
                # 어떤 입력으로도 이 방어만 분리할 수 없다. 감사 공백이 아니라
                # 중복 선언이므로 그렇게 분류해 보고한다.
                return {"detected": True, "subsumed": True, "expected_location": expected,
                        "note": "같은 노드의 다른 keyword가 이 방어를 함의한다 (중복 선언)"}
            return {"note": "방어를 약화해도 다른 방어가 같은 위치를 잡는다 (가려짐)",
                    "expected_location": expected}
        return {"detected": True, "expected_location": expected}

    if kind.startswith("required:"):
        field = kind.split(":", 1)[1]

        def build_required(documents: dict) -> str:
            _delete_at(documents, where, field)
            return contracts.safe_location(where, documents)

        return attempt(build_required) or {"note": "required 위반 입력을 만들 수 없다"}

    if kind == "closed":
        def build_closed(documents: dict) -> str:
            _add_key_at(documents, where, _PROBE_KEY)
            return contracts.safe_location(f"{where}/{_PROBE_KEY}", documents)

        return attempt(build_closed) or {"note": "닫힌 객체 위반 입력을 만들 수 없다"}

    current = _read_at(base_documents, where)
    # uniqueItems 위반은 **중복된 원소 위치**로 보고된다. 배열 위치가 아니다.
    spot = f"{where}/{len(current)}" if kind == "uniqueItems" and isinstance(current, list) else where
    last: dict[str, Any] | None = None
    for candidate in _violation_candidates(node, kind, current):
        def build_value(documents: dict, value: Any = candidate) -> str:
            _apply_at(documents, where, lambda _old: copy.deepcopy(value))
            return contracts.safe_location(spot, documents)

        result = attempt(build_value)
        if result is None:
            continue
        if result.get("detected"):
            return result
        last = result
    return last or {"note": "이 방어를 깨는 입력 후보를 만들 수 없다"}


# ---------------------------------------------------------------------------
# REVIEW-025 R-06 — schema 방어의 **저장소 밖 고정 기준** (frozen manifest)
# ---------------------------------------------------------------------------

#: 방어 목록을 production schema에서 다시 만들면, 방어를 지웠을 때 분모도 함께 줄어들어
#: 감사가 조용히 통과한다. 그래서 현재 방어 ID 집합을 **schema 밖 파일**에 고정한다.
#: 추가·삭제는 이 파일의 명시적 diff 없이는 audit가 실패한다.
DEFENSE_MANIFEST_PATH = FIXTURE_DIR / "defense-manifest.json"


def _manifest_digest(
    killable: Sequence[Mapping[str, Any]], equivalent: Sequence[Mapping[str, Any]]
) -> str:
    """**실제로 기록되는 entry**에서 digest를 만든다.

    이전 판은 갱신 도구가 새 목록을 쓰면서 digest는 이전 목록으로 계산했다. 그래서
    `--write-manifest`가 exit 0으로 끝난 직후 `--manifest-check`가 MF-03으로 실패하는
    파일이 만들어졌다 (REVIEW-026 R-03).
    """

    payload = json.dumps(
        {
            "killable": sorted(
                [str(entry.get("defense_id")), str(entry.get("fingerprint"))] for entry in killable
            ),
            "equivalent": sorted(
                [str(entry.get("defense_id")), str(entry.get("fingerprint"))] for entry in equivalent
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_defense_manifest(path: Path = DEFENSE_MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_entries(manifest: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    return [entry for entry in (manifest.get(section) or []) if isinstance(entry, Mapping)]


def _duplicates(names: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for name in names:
        (repeated if name in seen else seen).add(name)
    return sorted(repeated)


def run_manifest_check(
    schema_dir: Path = SCHEMA_DIR, path: Path = DEFENSE_MANIFEST_PATH
) -> list[dict[str, Any]]:
    """production 방어 집합이 **고정 manifest와 정확히 같은지** (REVIEW-025 R-06 / REVIEW-026 R-03).

    - manifest에 있는데 schema에 없다 → 방어가 삭제됐다. 분모가 줄어드는 것이 아니라 실패다.
    - schema에 있는데 manifest에 없다 → 새 방어가 검토 없이 들어왔다. 역시 실패다.
    - 좌표는 같은데 **의미값**이 다르다 → enum 확장·범위 완화·pattern 변경이다. 실패다.
    - digest 불일치 → manifest 자체가 손상되거나 손으로 고쳐졌다.
    - 절 내부 중복·절 간 교집합·`declared != unique` → 분모가 부풀거나 겹쳤다.

    고유 transformation 검사도 여기서 함께 한다. audit의 성공 조건이 unit test가 아니라
    이 결과에 직접 걸리게 하기 위해서다.
    """

    rows: list[dict[str, Any]] = []
    try:
        manifest = load_defense_manifest(path)
    except (OSError, json.JSONDecodeError) as exc:  # noqa: BLE001
        return [{
            "check_id": "MF-00", "title": "defense manifest 읽기",
            "passed": False, "note": f"manifest를 읽을 수 없다: {exc}",
        }]

    killable_entries = _manifest_entries(manifest, "killable")
    equivalent_entries = _manifest_entries(manifest, "equivalent")
    declared_killable = [str(entry.get("defense_id")) for entry in killable_entries]
    declared_equivalent = [str(entry.get("defense_id")) for entry in equivalent_entries]
    declared_fingerprints = {
        str(entry.get("defense_id")): str(entry.get("fingerprint"))
        for entry in killable_entries + equivalent_entries
    }
    declared = set(declared_killable) | set(declared_equivalent)

    defenses = collect_schema_defenses(schema_dir)
    observed_fingerprints = {defense.defense_id: defense.fingerprint for defense in defenses}
    observed = set(observed_fingerprints)

    removed = sorted(declared - observed)
    added = sorted(observed - declared)
    rows.append({
        "check_id": "MF-01", "title": "production 방어가 삭제되지 않았다",
        "passed": not removed,
        "note": f"manifest에 있으나 schema에 없다: {', '.join(removed[:6])}" if removed else "",
        "missing": removed,
    })
    rows.append({
        "check_id": "MF-02", "title": "새 방어가 manifest에 등록됐다",
        "passed": not added,
        "note": f"schema에 있으나 manifest에 없다: {', '.join(added[:6])}" if added else "",
        "extra": added,
    })
    expected_digest = _manifest_digest(killable_entries, equivalent_entries)
    rows.append({
        "check_id": "MF-03", "title": "manifest digest가 목록과 일치한다",
        "passed": manifest.get("digest") == expected_digest,
        "note": "" if manifest.get("digest") == expected_digest
        else f"기대 {expected_digest} / 기록 {manifest.get('digest')}",
    })
    reasons_ok = all(
        isinstance(entry.get("reason"), str) and entry["reason"].strip()
        for entry in equivalent_entries
    )
    rows.append({
        "check_id": "MF-04", "title": "equivalent allowlist에 근거가 적혀 있다",
        "passed": reasons_ok,
        "note": "" if reasons_ok else "근거 없는 equivalent 항목이 있다",
    })
    duplicates = duplicate_transformations()
    rows.append({
        "check_id": "MF-05", "title": "같은 transformation을 두 mutant로 세지 않는다",
        "passed": not duplicates,
        "note": f"중복 transformation: {duplicates[:3]}" if duplicates else "",
    })
    drifted = sorted(
        defense_id
        for defense_id, fingerprint in observed_fingerprints.items()
        if defense_id in declared_fingerprints
        and declared_fingerprints[defense_id] != fingerprint
    )
    rows.append({
        "check_id": "MF-06", "title": "방어의 의미값(enum·범위·pattern·closed·required)이 그대로다",
        "passed": not drifted,
        "note": "; ".join(
            f"{defense_id}: manifest {declared_fingerprints[defense_id]} / "
            f"schema {observed_fingerprints[defense_id]}"
            for defense_id in drifted[:3]
        ),
        "drifted": drifted,
    })
    killable_dupes = _duplicates(declared_killable)
    equivalent_dupes = _duplicates(declared_equivalent)
    overlap = sorted(set(declared_killable) & set(declared_equivalent))
    rows.append({
        "check_id": "MF-07", "title": "manifest 두 절이 각각 유일하고 서로 겹치지 않는다",
        "passed": not (killable_dupes or equivalent_dupes or overlap),
        "note": (
            f"killable 중복 {killable_dupes[:3]} / equivalent 중복 {equivalent_dupes[:3]} / "
            f"교집합 {overlap[:3]}"
        ) if (killable_dupes or equivalent_dupes or overlap) else "",
    })
    counts = unique_transformation_count(schema_dir)
    consistent = (
        counts["defense_declared"] == counts["defense_unique"]
        and counts["schema_declared"] == counts["schema_unique"]
        and counts["validator_declared"] == counts["validator_unique"]
        and len(declared_killable) + len(declared_equivalent) == len(declared)
        and len(declared) == counts["defense_unique"]
    )
    rows.append({
        "check_id": "MF-08", "title": "보고 total이 실제 고유 수와 같다",
        "passed": consistent,
        "note": "" if consistent else (
            f"defense {counts['defense_declared']}/{counts['defense_unique']} · "
            f"schema {counts['schema_declared']}/{counts['schema_unique']} · "
            f"validator {counts['validator_declared']}/{counts['validator_unique']} · "
            f"manifest {len(declared_killable) + len(declared_equivalent)}/{len(declared)}"
        ),
        "counts": counts,
    })
    return rows


def write_defense_manifest(
    schema_dir: Path = SCHEMA_DIR, path: Path = DEFENSE_MANIFEST_PATH
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """manifest를 현재 schema 기준으로 다시 쓴다 (사람이 diff로 검토하는 명시적 갱신).

    digest는 **실제로 쓰는 entry**에서 계산하고, 쓴 직후 같은 파일로 자기검증을 돌린다.
    갱신 도구가 스스로 불일치 파일을 만들 수 없어야 한다 (REVIEW-026 R-03 2번).
    """

    previous: dict[str, Any] = {}
    if path.exists():
        try:
            previous = load_defense_manifest(path)
        except (OSError, json.JSONDecodeError):  # pragma: no cover - 손상 파일은 새로 쓴다
            previous = {}
    reasons = {
        str(entry.get("defense_id")): str(entry.get("reason", ""))
        for entry in _manifest_entries(previous, "equivalent")
    }
    observed = sorted(collect_schema_defenses(schema_dir), key=lambda item: item.defense_id)
    seen: set[str] = set()
    killable: list[dict[str, Any]] = []
    equivalent: list[dict[str, Any]] = []
    for defense in observed:
        if defense.defense_id in seen:
            continue
        seen.add(defense.defense_id)
        entry = {"defense_id": defense.defense_id, "fingerprint": defense.fingerprint}
        if defense.defense_id in reasons:
            equivalent.append({**entry, "reason": reasons[defense.defense_id]})
        else:
            killable.append(entry)
    manifest = {
        "note": (
            "TASK-029 schema 방어의 고정 기준. production schema에서 다시 생성하지 않는다 "
            "(REVIEW-025 R-06). 좌표와 의미값(fingerprint)을 함께 고정한다 (REVIEW-026 R-03). "
            "갱신은 이 파일의 명시적 diff로만 한다."
        ),
        "digest": _manifest_digest(killable, equivalent),
        "killable": killable,
        "equivalent": equivalent,
    }
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return manifest, run_manifest_check(schema_dir, path)


# ---------------------------------------------------------------------------
# defense drift 자기검증 — 저장소 밖 임시 사본에서만 수행한다
# ---------------------------------------------------------------------------


class _TempTree:
    """임시 사본을 고치고 되돌린다. 원본 저장소 파일은 건드리지 않는다."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._saved: dict[Path, str] = {}

    def _save(self, path: Path) -> None:
        if path not in self._saved:
            self._saved[path] = path.read_text(encoding="utf-8")

    def edit_json(self, relative: str, mutate: Callable[[Any], None]) -> None:
        path = self.root / relative
        self._save(path)
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def restore(self) -> None:
        for path, text in self._saved.items():
            path.write_text(text, encoding="utf-8")
        self._saved.clear()


_MANIFEST_RELATIVE = "tests/fixtures/subtitle_contracts/defense-manifest.json"


def _node_at(document: Any, pointer: Sequence[str]) -> Any:
    node = document
    for token in pointer:
        node = node[token]
    return node


def _drop_root_required(field: str) -> Callable[[Any], None]:
    def mutate(document: Any) -> None:
        if field not in document.get("required", []):
            raise AssertionError(f"root required에 {field}가 없다 — 자기검증 불가")
        document["required"] = [name for name in document["required"] if name != field]

    return mutate


def _expand_enum(pointer: Sequence[str], value: str) -> Callable[[Any], None]:
    def mutate(document: Any) -> None:
        node = _node_at(document, pointer)
        node["enum"] = list(node["enum"]) + [value]

    return mutate


def _relax_range(pointer: Sequence[str], keyword: str, value: Any) -> Callable[[Any], None]:
    def mutate(document: Any) -> None:
        node = _node_at(document, pointer)
        if keyword not in node:
            raise AssertionError(f"{keyword}가 없다 — 자기검증 불가")
        node[keyword] = value

    return mutate


def _change_pattern(pointer: Sequence[str], value: str) -> Callable[[Any], None]:
    def mutate(document: Any) -> None:
        node = _node_at(document, pointer)
        if "pattern" not in node:
            raise AssertionError("pattern이 없다 — 자기검증 불가")
        node["pattern"] = value

    return mutate


def _duplicate_root_required(field: str) -> Callable[[Any], None]:
    def mutate(document: Any) -> None:
        if field not in document.get("required", []):
            raise AssertionError(f"root required에 {field}가 없다 — 자기검증 불가")
        document["required"] = list(document["required"]) + [field]

    return mutate


def _duplicate_manifest_entry(section: str) -> Callable[[Any], None]:
    def mutate(document: Any) -> None:
        entries = document.get(section) or []
        if not entries:
            raise AssertionError(f"manifest {section}가 비어 있다 — 자기검증 불가")
        document[section] = list(entries) + [copy.deepcopy(entries[0])]

    return mutate


def _intersect_manifest_sections(document: Any) -> None:
    equivalent = document.get("equivalent") or []
    if not equivalent:
        raise AssertionError("manifest equivalent가 비어 있다 — 자기검증 불가")
    entry = copy.deepcopy(equivalent[0])
    entry.pop("reason", None)
    document["killable"] = list(document.get("killable") or []) + [entry]


@dataclass(frozen=True)
class DriftSelfTest:
    """임시 사본에서 방어나 manifest를 훼손하고 gate가 실제로 막는지 본다."""

    selftest_id: str
    title: str
    edits: tuple[tuple[str, Callable[[Any], None]], ...]
    #: `(인자, 기대 exit code)` 순서대로 실행한다.
    steps: tuple[tuple[tuple[str, ...], int], ...] = ((("--manifest-check",), 1),)


#: `line_break_policy` enum과 `extension_id` pattern은 REVIEW-026 R-03이 직접 지목한 자리다.
_STYLE_POLICY_POINTER = ("$defs", "StyleOverride", "properties", "line_break_policy")
_SEGMENT_TRACK_POINTER = ("properties", "source_track_index")
_TRANSCRIPT_EXTENSION_POINTER = ("$defs", "extension_id")

_DEFENSE_SELF_TESTS: tuple[DriftSelfTest, ...] = (
    DriftSelfTest("SD-01", "speech-segment root required source_track_index 삭제",
                  (("schemas/speech-segment-v1.schema.json",
                    _drop_root_required("source_track_index")),)),
    DriftSelfTest("SD-02", "transcript root required transcript_id 삭제",
                  (("schemas/transcript-v1.schema.json",
                    _drop_root_required("transcript_id")),)),
    DriftSelfTest("SD-03", "capability root required network_requirement 삭제",
                  (("schemas/adapter-capability-report-v1.schema.json",
                    _drop_root_required("network_requirement")),)),
    DriftSelfTest("SD-04", "translated root required source_transcript 삭제",
                  (("schemas/translated-transcript-v1.schema.json",
                    _drop_root_required("source_transcript")),)),
    DriftSelfTest("SD-05", "subtitle root required input_document_ref 삭제",
                  (("schemas/subtitle-document-v1.schema.json",
                    _drop_root_required("input_document_ref")),)),
    DriftSelfTest("SD-06", "line_break_policy enum에 x_new_policy를 추가한다",
                  (("schemas/subtitle-document-v1.schema.json",
                    _expand_enum(_STYLE_POLICY_POINTER, "x_new_policy")),)),
    DriftSelfTest("SD-07", "source_track_index의 minimum을 완화한다",
                  (("schemas/speech-segment-v1.schema.json",
                    _relax_range(_SEGMENT_TRACK_POINTER, "minimum", -1)),)),
    DriftSelfTest("SD-08", "extension_id pattern을 아무 문자열이나 받도록 바꾼다",
                  (("schemas/transcript-v1.schema.json",
                    _change_pattern(_TRANSCRIPT_EXTENSION_POINTER, "^.*$")),)),
    DriftSelfTest("SD-09", "root required 배열에 같은 이름을 중복해 넣는다",
                  (("schemas/transcript-v1.schema.json",
                    _duplicate_root_required("transcript_id")),)),
    DriftSelfTest("SD-10", "manifest killable 절 안에서 같은 ID를 중복한다",
                  ((_MANIFEST_RELATIVE, _duplicate_manifest_entry("killable")),)),
    DriftSelfTest("SD-11", "manifest equivalent 절 안에서 같은 ID를 중복한다",
                  ((_MANIFEST_RELATIVE, _duplicate_manifest_entry("equivalent")),)),
    DriftSelfTest("SD-12", "manifest killable과 equivalent가 겹친다",
                  ((_MANIFEST_RELATIVE, _intersect_manifest_sections),)),
    DriftSelfTest(
        "SD-13",
        "equivalent 방어(minLength)를 지우면 drift로 막히고, 갱신 도구는 "
        "stale digest가 아닌 일관된 파일을 만든다",
        (("schemas/transcript-v1.schema.json",
          lambda document: _node_at(document, _TRANSCRIPT_EXTENSION_POINTER).pop("minLength")),),
        steps=((("--manifest-check",), 1), (("--write-manifest",), 0), (("--manifest-check",), 0)),
    ),
)


def run_defense_drift_self_tests() -> list[dict[str, Any]]:
    """방어나 manifest를 훼손하면 `--manifest-check`가 반드시 exit 1이어야 한다.

    이 검사가 audit의 성공 조건에 직접 걸려 있으므로, 같은 훼손은 `make audit-task-029`와
    `make verify-task-029`도 exit 1로 만든다. 저장소 파일은 바꾸지 않는다.
    """

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mcs-029-drift-") as tmp:
        root = Path(tmp) / "tree"
        shutil.copytree(
            REPO_ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
        )
        baseline = _run_script_code(root, "--manifest-check")
        if baseline != 0:
            return [{
                "selftest_id": "BASELINE", "title": "임시 사본 manifest baseline",
                "passed": False, "note": f"baseline exit={baseline} (0이어야 한다)",
            }]
        tree = _TempTree(root)
        for selftest in _DEFENSE_SELF_TESTS:
            try:
                for relative, mutate in selftest.edits:
                    tree.edit_json(relative, mutate)
            except (AssertionError, KeyError, OSError) as exc:
                tree.restore()
                rows.append({
                    "selftest_id": selftest.selftest_id, "title": selftest.title,
                    "passed": False, "note": f"자기검증 준비 실패: {exc}",
                })
                continue
            observed: list[int] = []
            for args, _ in selftest.steps:
                observed.append(_run_script_code(root, *args))
            tree.restore()
            expected = [code for _, code in selftest.steps]
            rows.append({
                "selftest_id": selftest.selftest_id, "title": selftest.title,
                "passed": observed == expected,
                "exit_codes": observed,
                "note": "" if observed == expected
                else f"기대 exit {expected} / 관측 {observed}",
            })
    return rows


def _run_script_code(root: Path, *args: str) -> int:
    proc = subprocess.run(
        [sys.executable, "scripts/verify_task_029.py", *args],
        cwd=root,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": "src",
            "PATH": "/usr/bin:/bin",
            "HOME": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        },
        timeout=600,
    )
    return proc.returncode


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
    parser.add_argument(
        "--manifest-check",
        action="store_true",
        help="고정 defense manifest drift와 transformation 고유성만 확인한다",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="현재 schema 기준으로 defense manifest를 다시 쓴다 (명시적 갱신)",
    )
    args = parser.parse_args(argv)

    if args.write_manifest:
        manifest, self_check = write_defense_manifest(args.schemas)
        print(
            f"defense manifest 갱신 — killable {len(manifest['killable'])}건 · "
            f"equivalent {len(manifest['equivalent'])}건 · digest {manifest['digest']}"
        )
        # 쓴 직후 같은 파일로 자기검증한다. 갱신 도구가 불일치 파일을 만들면 여기서 끝난다.
        for row in self_check:
            if not row["passed"]:
                print(f"WRITE-SELFCHECK {row['check_id']}: {row['title']} — {row['note']}")
        return 0 if all(row["passed"] for row in self_check) else 1

    if args.manifest_check:
        rows = run_manifest_check(args.schemas)
        for row in rows:
            if not row["passed"]:
                print(f"DRIFT {row['check_id']}: {row['title']} — {row['note']}")
        if args.json:
            print(json.dumps(rows, ensure_ascii=False))
        return 0 if all(row["passed"] for row in rows) else 1

    payload = _check_only(args.fixtures, args.schemas)
    fixture_rows = payload["fixtures"]
    mutation_rows = payload["mutations"]
    leak_rows = payload["leaks"]
    depth_rows = payload["depth_probes"]
    raw_rows = payload["raw_probes"]
    boundary_rows = payload["boundary_probes"]

    def _print_check_only(target: dict[str, Any]) -> None:
        for row in target["fixtures"]:
            if not row["passed"]:
                print(f"FAIL fixture {row['case_id']}: {'; '.join(row['mismatches'])}")
        for row in target["mutations"]:
            if not row["passed"]:
                print(f"FAIL input-mutant {row['mutation_id']}: {row['title']}")
                print(f"     기대 {row['expected']}")
                print(f"     관측 {row['observed']}")
        for row in target["leaks"]:
            if not row["passed"]:
                print(f"{'/'.join(row['kinds'])} {row['leak_id']}: {'; '.join(row['hits'])}")
        for row in target["depth_probes"]:
            if not row["passed"]:
                print(f"FAIL depth-probe {row['probe_id']}: {row['title']}")
                print(f"     단위 기대 {row['unit_expected']} / 관측 {row['unit_observed']}")
                print(f"     상류 기대 {row['shadow_expected']} / 관측 {row['shadow_observed']}")
        for row in target.get("raw_probes", []):
            if not row["passed"]:
                print(f"FAIL raw-probe {row['probe_id']}: {row['title']}")
                print(f"     기대 {row['expected']} / 관측 {row['observed']} {row['note']}")
        for row in target.get("boundary_probes", []):
            if not row["passed"]:
                print(f"FAIL boundary-probe {row['probe_id']}: {row['title']} — {row['note']}")
        for name in bad_sentinels(target):
            print(f"SENTINEL {name}: valid-case sentinel이 실패했다")

    if args.check_only:
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            _print_check_only(payload)
        return 0 if _all_passed(payload) else 1

    audit_schemas = SchemaSet(args.schemas)
    coverage_rows = run_defense_coverage(audit_schemas, args.fixtures)
    inventory_rows = run_schema_defense_inventory(args.fixtures, args.schemas)
    manifest_rows = run_manifest_check(args.schemas)
    drift_rows = run_defense_drift_self_tests()
    selftest_rows = run_audit_self_tests()
    schema_rows = run_source_mutants(schema_mutants(), "schema")
    validator_rows = run_source_mutants(validator_mutants(), "validator")

    summaries = [
        _summary("fixture", fixture_rows, sentinel=False),
        _summary("input mutants", mutation_rows, sentinel=False),
        _summary("leak scan", leak_rows, sentinel=False),
        _summary("depth probes", depth_rows, sentinel=False),
        _summary("raw JSON probes", raw_rows, sentinel=False),
        _summary("public boundary probes", boundary_rows, sentinel=False),
        _summary("validator defense sites", coverage_rows, sentinel=False),
        _summary(
            "schema defense killable",
            [row for row in inventory_rows if not row.get("equivalent")],
            sentinel=True,
        ),
        _summary(
            "schema defense equivalent",
            [row for row in inventory_rows if row.get("equivalent")],
            sentinel=True,
        ),
        _summary("defense manifest", manifest_rows, sentinel=False),
        _summary("defense drift self-tests", drift_rows, sentinel=False),
        _summary("audit self-tests", selftest_rows, sentinel=False),
        _summary("schema mutants", schema_rows, sentinel=True),
        _summary("validator code mutants", validator_rows, sentinel=True),
    ]
    report = {
        "summaries": summaries,
        "fixtures": fixture_rows,
        "input_mutants": mutation_rows,
        "leaks": leak_rows,
        "depth_probes": depth_rows,
        "raw_probes": raw_rows,
        "boundary_probes": boundary_rows,
        "defense_sites": coverage_rows,
        "schema_defense_inventory": inventory_rows,
        "defense_manifest": manifest_rows,
        "defense_drift_self_tests": drift_rows,
        "audit_self_tests": selftest_rows,
        "schema_mutants": schema_rows,
        "validator_mutants": validator_rows,
        "unique_transformations": unique_transformation_count(args.schemas),
        "bad_sentinels": bad_sentinels(payload),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_check_only(payload)
        for row in inventory_rows:
            if not row["passed"]:
                print(
                    f"SCHEMA-DEFENSE {row['defense_id']}: {row['note']}"
                )
        for row in manifest_rows:
            if not row["passed"]:
                print(f"DRIFT {row['check_id']}: {row['title']} — {row['note']}")
        for row in drift_rows + selftest_rows:
            if not row["passed"]:
                print(f"SELFTEST {row['selftest_id']}: {row['note']}")
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
                + (f" · 중복 선언 {summary['subsumed']}" if summary["subsumed"] else "")
            )

    ok = (
        _all_passed(payload)
        and all(row["passed"] for row in coverage_rows)
        and all(row["passed"] for row in inventory_rows)
        # manifest drift와 transformation 고유성을 audit 성공 조건에 **직접** 건다.
        and all(row["passed"] for row in manifest_rows)
        and all(row["passed"] for row in drift_rows)
        and all(row["passed"] for row in selftest_rows)
        and all(row.get("detected") and row.get("sentinel_ok") for row in schema_rows)
        and all(row.get("detected") and row.get("sentinel_ok") for row in validator_rows)
    )
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    raise SystemExit(main())
