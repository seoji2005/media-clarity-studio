"""TASK-029 자막 spine 계약 validator.

이 모듈은 `schemas/`의 다섯 신규 정본을 **실제로 읽어** 구조를 검사하고, JSON Schema로
표현할 수 없는 교차 문서·시간축·문자축·capability 불변식을 이어서 검사한다.

**구조 검사는 `schema_core`를 그대로 재사용한다.** `SchemaSet`·`SchemaValidator`·
`Finding`·strict JSON loader를 다시 구현하지 않으며 `schema_core.py`를 수정하지 않는다.
따라서 `oneOf`/`anyOf`/`allOf`/`if-then-else`/`contains`/custom format이 필요한 조건은
schema가 아니라 이 모듈의 domain 검사로 표현한다. Draft 2020-12 전체 지원을 주장하지 않는다.

Python 3.12 표준 라이브러리만 사용한다. 외부 dependency·모델·network를 쓰지 않는다.

이 모듈은 **읽기 전용**이다. 검증 실패에서 입력이나 기존 artifact를 수정·삭제하지 않는다.

문자축 규약
-----------
모든 `char_start`/`char_end`는 **exact stored text의 Unicode scalar value index**의
반개구간이다. UTF-8 byte·UTF-16 code unit·grapheme cluster offset과 섞지 않는다.
Python `str`은 scalar 열이지만 JSON `\\uD800` escape로 lone surrogate를 담을 수 있고,
그런 text는 안정적인 scalar offset을 정의할 수 없으므로 `E_UNICODE_SCALAR`로 거부하고
그 text에 대한 offset 검사를 더 진행하지 않는다.

오류 코드
---------
TASK-029 §8이 정한 최소 코드만 쓴다. 새 코드를 만들지 않았고, 표에 이름이 하나뿐인
규칙 묶음은 아래처럼 그 코드 하나로 모은다.

- ``E_SCHEMA`` — root schema·필수 필드·enum·닫힌 객체 위반. schema가 표현할 수 없는
  **문서 집합 수준의 구조 위반**(ID 중복, 조건부 동반 필수 필드, ``x-`` 확장 ID 규칙,
  language tag 자리의 ``"unknown"`` 문자열)도 여기에 속한다.
- ``E_LANGUAGE_GAP_REVIEW`` — §4.2 R6·R10의 language unknown 정직성 묶음. gap·explicit
  ``und``가 있는데 unknown review 상태가 없음, gap·``und``가 있는데 ``dominant_language``가
  있음, 전 범위가 덮였는데 ``dominant_language``가 파생 규칙과 다름.
- ``E_LINEAGE`` — cue upstream fragment의 ID·exact text·line 결합 동치·입력 범위 partition
  위반. 범위 자체가 비었거나 text 밖이면 ``E_OFFSET_RANGE``, 순서가 역전되면
  ``E_OFFSET_ORDER``가 먼저다.

finding 위치는 실제 입력에서 해석 가능한 **선행 ``/`` 없는** JSON Pointer이며, 존재하지
않는 leaf 대신 실제로 존재하는 부모를 가리킨다. message에는 source/target 원문, 절대 경로,
민감한 실제 값을 넣지 않는다. 판정은 message가 아니라 ``(code, location)``이다.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from media_clarity.schema_core import (
    DEFAULT_SCHEMA_DIR,
    REPO_ROOT,
    SCHEMA_DIALECT,
    SCHEMA_VERSION,
    Finding,
    JsonInputError,
    SchemaContractError,
    SchemaValidator,
    load_strict,
    loads_strict,
    sort_findings,
)
from media_clarity.schema_core import SchemaSet as _CoreSchemaSet


__all__ = [
    "ALLOWED_LINE_BREAK_SCALARS",
    "DEFAULT_SCHEMA_DIR",
    "DOCUMENT_KEYS",
    "ERROR_CODES",
    "EXPECTED_CASE_IDS",
    "Finding",
    "JsonInputError",
    "REPO_ROOT",
    "SCHEMA_DIALECT",
    "SCHEMA_FILES",
    "SCHEMA_VERSION",
    "SchemaContractError",
    "SchemaSet",
    "SchemaValidator",
    "TARGET_LANGUAGE",
    "UNDETERMINED_LANGUAGE",
    "ValidationResult",
    "check_asr_capability_binding",
    "check_speech_segments",
    "check_subtitle_document",
    "check_transcript",
    "check_translated_transcript",
    "check_translation_capability_binding",
    "discover_fixtures",
    "evaluate_fixture",
    "load_fixture",
    "load_strict",
    "loads_strict",
    "sort_findings",
    "validate_documents",
]


SCHEMA_FILES = (
    "common-v1.schema.json",
    "speech-segment-v1.schema.json",
    "adapter-capability-report-v1.schema.json",
    "transcript-v1.schema.json",
    "translated-transcript-v1.schema.json",
    "subtitle-document-v1.schema.json",
)


class SchemaSet(_CoreSchemaSet):
    """TASK-029의 자막 spine schema 묶음. 검사 의미는 `schema_core`와 동일하다."""

    def __init__(self, directory: Path = DEFAULT_SCHEMA_DIR):
        super().__init__(directory, SCHEMA_FILES)


#: 현재 제품의 성공 번역 산출물 언어. 추측·비-`ko` 승격은 계약 실패다 (U-31 해소).
TARGET_LANGUAGE = "ko"

#: 명시적 미결정 언어. gap과 동일하게 unknown+review로 다루며 검수 의무를 우회하지 못한다.
UNDETERMINED_LANGUAGE = "und"

#: language tag 자리에 오면 안 되는 문자열. 알 수 없으면 빈 배열 + 명시적 limitation이다.
FORBIDDEN_LANGUAGE_TAG = "unknown"

ERROR_CODES = (
    "E_SCHEMA",
    "E_TIME_RANGE",
    "E_TIME_ORDER",
    "E_CHANNEL_SEMANTICS",
    "E_STREAM_REF",
    "E_OFFSET_RANGE",
    "E_OFFSET_ORDER",
    "E_UNICODE_SCALAR",
    "E_LANGUAGE_GAP_REVIEW",
    "E_CAPABILITY_MISMATCH",
    "E_CONFIDENCE",
    "E_SOURCE_REF",
    "E_SOURCE_TEXT",
    "E_SOURCE_COVERAGE",
    "E_ALIGNMENT",
    "E_TEXT_AXIS",
    "E_TARGET_LANGUAGE",
    "E_CUE_ORDER",
    "E_CUE_OVERLAP",
    "E_CUE_REF",
    "E_LINEAGE",
    "E_REVIEW_STATE",
)

#: 문서 집합에서 인식하는 key와 그 schema 파일. 그 밖의 key는 E_SCHEMA다.
DOCUMENT_KEYS: dict[str, str] = {
    "speech_segments": "speech-segment-v1.schema.json",
    "transcript": "transcript-v1.schema.json",
    "translated_transcript": "translated-transcript-v1.schema.json",
    "subtitle_document": "subtitle-document-v1.schema.json",
}

#: TASK-029 §4.5가 고정한 line break 이동 가능 whitespace scalar 집합.
ALLOWED_LINE_BREAK_SCALARS = frozenset(
    chr(code)
    for code in (
        *range(0x0009, 0x000E),  # U+0009-U+000D
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),  # U+2000-U+200A
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    )
)

#: Transcript feature_status의 일곱 축. capability 축과 결과 증거를 함께 결박한다.
ASR_FEATURE_KEYS = (
    "token_timing",
    "token_confidence",
    "segment_confidence",
    "language_id",
    "language_confidence",
    "speaker_diarization",
    "nbest",
)

TRANSLATION_FEATURE_KEYS = ("segment_alignment", "translation_confidence")


# ---------------------------------------------------------------------------
# 작은 도우미
# ---------------------------------------------------------------------------


def _finding(location: str, code: str, message: str) -> Finding:
    return Finding(location=location, code=code, message=message)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))


def _has_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(char) <= 0xDFFF for char in text)


def _scalar_text(value: Any, location: str, findings: list[Finding]) -> str | None:
    """lone surrogate가 없는 text만 offset 검사 대상으로 돌려준다."""

    if not isinstance(value, str):
        return None
    if _has_surrogate(value):
        findings.append(
            _finding(
                location,
                "E_UNICODE_SCALAR",
                "lone surrogate가 있어 안정적인 Unicode scalar offset을 정의할 수 없다",
            )
        )
        return None
    return value


def _check_half_open(
    start: Any, end: Any, where: str, findings: list[Finding], *, what: str
) -> bool:
    """`end > start >= 0`이고 둘 다 finite인 반개구간인지 검사한다.

    `where`는 구간을 담은 **객체**의 위치다. 위반 필드에 맞춰 위치를 좁힌다.
    """

    if not _finite(start) or not _finite(end):
        findings.append(
            _finding(f"{where}/end_seconds", "E_TIME_RANGE", f"{what} 시간이 finite 숫자가 아니다")
        )
        return False
    if float(start) < 0:
        findings.append(
            _finding(f"{where}/start_seconds", "E_TIME_RANGE", f"{what} start_seconds가 음수다")
        )
        return False
    if float(end) <= float(start):
        findings.append(
            _finding(
                f"{where}/end_seconds",
                "E_TIME_RANGE",
                f"{what}는 positive duration 반개구간이어야 한다",
            )
        )
        return False
    return True


def _overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    """반개구간 [start, end) 끼리의 실제 겹침."""

    return a_start < b_end and b_start < a_end


def _check_confidence_value(
    value: Any, semantics: str | None, location: str, findings: list[Finding]
) -> None:
    """calibrated_probability만 [0,1]을 강제한다. 나머지는 finite provider-native 값이다."""

    if not _finite(value):
        findings.append(_finding(location, "E_CONFIDENCE", "confidence가 finite 숫자가 아니다"))
        return
    if semantics == "calibrated_probability" and not (0.0 <= float(value) <= 1.0):
        findings.append(
            _finding(
                location,
                "E_CONFIDENCE",
                "calibrated_probability confidence는 [0,1] 안에 있어야 한다",
            )
        )


def _check_review_state(
    node: Mapping[str, Any], location: str, findings: list[Finding]
) -> None:
    """`needs_review`와 비어 있지 않은 `review_reasons`는 서로 동치다."""

    needs = node.get("needs_review")
    reasons = node.get("review_reasons")
    if not isinstance(needs, bool) or not isinstance(reasons, list):
        return
    if needs != bool(reasons):
        findings.append(
            _finding(
                f"{location}/needs_review",
                "E_REVIEW_STATE",
                "needs_review와 review_reasons의 존재가 서로 동치가 아니다",
            )
        )
    if "other" in reasons:
        extension = node.get("review_extension_id")
        if not isinstance(extension, str):
            findings.append(
                _finding(
                    location,
                    "E_SCHEMA",
                    "review_reasons에 other가 있으면 review_extension_id가 필요하다",
                )
            )
    elif "review_extension_id" in node:
        findings.append(
            _finding(
                f"{location}/review_extension_id",
                "E_SCHEMA",
                "review_extension_id는 review_reasons에 other가 있을 때만 쓴다",
            )
        )
    if node.get("is_low_confidence") is True and "low_confidence" not in (reasons or []):
        findings.append(
            _finding(
                f"{location}/is_low_confidence",
                "E_REVIEW_STATE",
                "is_low_confidence=true이면 low_confidence review reason이 함께 있어야 한다",
            )
        )


def _check_language_tags(
    tags: Any, location: str, findings: list[Finding]
) -> None:
    """language tag 자리의 문자열 단독 `"unknown"`을 거부한다 (§4.3)."""

    if not isinstance(tags, list):
        return
    for index, tag in enumerate(tags):
        if tag == FORBIDDEN_LANGUAGE_TAG:
            findings.append(
                _finding(
                    f"{location}/{index}",
                    "E_SCHEMA",
                    'language tag 자리에 문자열 단독 "unknown"을 쓸 수 없다 — '
                    "빈 배열과 명시적 limitation을 쓴다",
                )
            )


@dataclass(frozen=True)
class _Range:
    """partition 검사용 범위 한 칸. `location`은 실제 입력에서 해석 가능해야 한다.

    `group`은 **같은 배열에서 나온 범위 묶음**이다. 서로 다른 배열(visible fragment와
    line_break_whitespace, covered fragment와 uncovered fragment)은 문서 안에서 나란히
    놓이지 않으므로 appearance order를 섞어 비교하지 않는다. partition 자체(gap·중복)는
    group과 무관하게 함께 본다.
    """

    start: int
    end: int
    location: str
    order: int
    group: str


def _check_partition(
    entries: Sequence[_Range],
    text_length: int,
    *,
    gap_location: str,
    coverage_code: str,
    subject: str,
    findings: list[Finding],
) -> None:
    """`entries`가 `[0, text_length)`를 gap·중복·겹침 없이 정확히 한 번 partition하는지.

    appearance order(`order`)가 원문 순서와 어긋나면 `E_OFFSET_ORDER`를 먼저 낸다.
    """

    if text_length <= 0:
        return
    ordered = sorted(entries, key=lambda item: (item.start, item.end, item.order))
    for group in sorted({item.group for item in entries}):
        appearance = sorted(
            (item for item in entries if item.group == group), key=lambda item: item.order
        )
        for previous, current in zip(appearance, appearance[1:]):
            if current.start < previous.start:
                findings.append(
                    _finding(
                        current.location,
                        "E_OFFSET_ORDER",
                        f"{subject} 범위가 원문 순서가 아니다",
                    )
                )
    cursor = 0
    for item in ordered:
        if item.start > cursor:
            findings.append(
                _finding(
                    gap_location,
                    coverage_code,
                    f"{subject}에 미신고 gap이 있다 ([{cursor}, {item.start}))",
                )
            )
        elif item.start < cursor:
            findings.append(
                _finding(
                    item.location,
                    coverage_code,
                    f"{subject} 범위가 앞 범위와 겹치거나 중복된다",
                )
            )
        cursor = max(cursor, item.end)
    if cursor < text_length:
        findings.append(
            _finding(
                gap_location,
                coverage_code,
                f"{subject}에 미신고 gap이 있다 ([{cursor}, {text_length}))",
            )
        )


# ---------------------------------------------------------------------------
# SpeechSegment 집합
# ---------------------------------------------------------------------------


def check_speech_segments(segments: Sequence[Any], location: str = "speech_segments") -> list[Finding]:
    """같은 실행의 ordered SpeechSegment 집합 불변식 (TASK-029 §4.1)."""

    findings: list[Finding] = []
    seen_ids: set[str] = set()
    ranges: list[tuple[str, str, float, float, list[str], int]] = []

    for index, segment in enumerate(segments):
        where = f"{location}/{index}"
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        if isinstance(segment_id, str):
            if segment_id in seen_ids:
                findings.append(
                    _finding(
                        f"{where}/segment_id",
                        "E_SCHEMA",
                        "segment_id가 문서 집합 안에서 중복이다",
                    )
                )
            seen_ids.add(segment_id)

        start, end = segment.get("start_seconds"), segment.get("end_seconds")
        valid_time = _check_half_open(start, end, where, findings, what="segment")

        stream_id = segment.get("stream_id")
        concurrent = segment.get("concurrent_stream_ids")
        if valid_time and isinstance(stream_id, str) and isinstance(concurrent, list):
            ranges.append((segment_id or "", stream_id, float(start), float(end), concurrent, index))

        _check_channel_semantics(segment, where, findings)
        _check_speech_confidence(segment, where, findings)
        _scalar_text(segment.get("speaker_label"), f"{where}/speaker_label", findings)

    findings.extend(_check_concurrent_streams(ranges, location))
    return findings


def _check_channel_semantics(
    segment: Mapping[str, Any], where: str, findings: list[Finding]
) -> None:
    method = segment.get("separation_method")
    semantics = segment.get("channel_semantics")
    has_channel = "source_channel_index" in segment

    if method == "channel":
        if not has_channel:
            findings.append(
                _finding(
                    f"{where}/separation_method",
                    "E_CHANNEL_SEMANTICS",
                    "separation_method=channel은 source_channel_index가 있어야 한다",
                )
            )
        if semantics != "independent":
            findings.append(
                _finding(
                    f"{where}/separation_method",
                    "E_CHANNEL_SEMANTICS",
                    "separation_method=channel은 channel_semantics=independent일 때만 허용한다 — "
                    "일반 stereo mix를 두 화자로 간주하지 않는다",
                )
            )
    if method == "none" and "speaker_label" in segment:
        findings.append(
            _finding(
                f"{where}/speaker_label",
                "E_CHANNEL_SEMANTICS",
                "separation_method=none이면 화자 분리 근거가 없으므로 speaker_label을 주장할 수 없다",
            )
        )


def _check_speech_confidence(
    segment: Mapping[str, Any], where: str, findings: list[Finding]
) -> None:
    for value_key, semantics_key in (
        ("speech_confidence", "speech_confidence_semantics"),
        ("speaker_confidence", "speaker_confidence_semantics"),
    ):
        has_value = value_key in segment
        has_semantics = semantics_key in segment
        if has_value and not has_semantics:
            findings.append(
                _finding(
                    f"{where}/{value_key}",
                    "E_CONFIDENCE",
                    f"{value_key}가 있으면 {semantics_key}가 함께 있어야 한다",
                )
            )
        if has_semantics and not has_value:
            findings.append(
                _finding(
                    f"{where}/{semantics_key}",
                    "E_CONFIDENCE",
                    f"{semantics_key}는 {value_key}가 있을 때만 쓴다",
                )
            )
        if has_value:
            _check_confidence_value(
                segment[value_key],
                segment.get(semantics_key),
                f"{where}/{value_key}",
                findings,
            )


def _check_concurrent_streams(
    ranges: Sequence[tuple[str, str, float, float, list[str], int]], location: str
) -> list[Finding]:
    """concurrent 참조의 존재·비자기참조·실제 겹침·상호 대칭 (§4.1 R5)."""

    findings: list[Finding] = []
    known_streams = {stream_id for _, stream_id, _, _, _, _ in ranges}
    for _, stream_id, start, end, concurrent, index in ranges:
        where = f"{location}/{index}/concurrent_stream_ids"
        for position, other in enumerate(concurrent):
            spot = f"{where}/{position}"
            if other == stream_id:
                findings.append(
                    _finding(spot, "E_STREAM_REF", "자기 자신의 stream을 concurrent로 참조했다")
                )
                continue
            if other not in known_streams:
                findings.append(
                    _finding(spot, "E_STREAM_REF", "존재하지 않는 stream을 참조했다")
                )
                continue
            partners = [
                entry
                for entry in ranges
                if entry[1] == other and _overlaps(start, end, entry[2], entry[3])
            ]
            if not partners:
                findings.append(
                    _finding(
                        spot,
                        "E_STREAM_REF",
                        "선언한 concurrent stream과 실제로 겹치는 구간이 없다",
                    )
                )
                continue
            if not any(stream_id in entry[4] for entry in partners):
                findings.append(
                    _finding(
                        spot,
                        "E_STREAM_REF",
                        "겹침을 선언한 두 stream의 concurrent 참조가 상호 대칭이 아니다",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TranscriptSegment:
    segment_id: str
    stream_id: str
    text: str | None
    location: str
    node: Mapping[str, Any]


def _transcript_segments(transcript: Mapping[str, Any], location: str) -> list[_TranscriptSegment]:
    collected: list[_TranscriptSegment] = []
    for stream_index, stream in enumerate(transcript.get("streams") or []):
        if not isinstance(stream, dict):
            continue
        stream_id = stream.get("stream_id")
        for segment_index, segment in enumerate(stream.get("segments") or []):
            if not isinstance(segment, dict):
                continue
            text = segment.get("text")
            collected.append(
                _TranscriptSegment(
                    segment_id=segment.get("segment_id") if isinstance(segment.get("segment_id"), str) else "",
                    stream_id=stream_id if isinstance(stream_id, str) else "",
                    text=text if isinstance(text, str) else None,
                    location=f"{location}/streams/{stream_index}/segments/{segment_index}",
                    node=segment,
                )
            )
    return collected


def check_transcript(
    transcript: Mapping[str, Any],
    speech_segments: Sequence[Any],
    location: str = "transcript",
) -> list[Finding]:
    """raw ASR evidence 불변식 (TASK-029 §4.2) + 입력 SpeechSegment 참조."""

    findings: list[Finding] = []
    capability = transcript.get("capability_report")
    capability = capability if isinstance(capability, dict) else {}

    speech_index: dict[str, tuple[float, float, str]] = {}
    for segment in speech_segments:
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        start, end = segment.get("start_seconds"), segment.get("end_seconds")
        stream_id = segment.get("stream_id")
        if isinstance(segment_id, str) and _finite(start) and _finite(end) and isinstance(stream_id, str):
            speech_index[segment_id] = (float(start), float(end), stream_id)

    seen_streams: set[str] = set()
    seen_segments: set[str] = set()

    for stream_index, stream in enumerate(transcript.get("streams") or []):
        if not isinstance(stream, dict):
            continue
        where = f"{location}/streams/{stream_index}"
        stream_id = stream.get("stream_id")
        if isinstance(stream_id, str):
            if stream_id in seen_streams:
                findings.append(
                    _finding(f"{where}/stream_id", "E_SCHEMA", "stream_id가 중복이다")
                )
            seen_streams.add(stream_id)
        _check_speaker_label_pair(stream, where, findings)

        for segment_index, segment in enumerate(stream.get("segments") or []):
            if not isinstance(segment, dict):
                continue
            spot = f"{where}/segments/{segment_index}"
            segment_id = segment.get("segment_id")
            if isinstance(segment_id, str):
                if segment_id in seen_segments:
                    findings.append(
                        _finding(f"{spot}/segment_id", "E_SCHEMA", "segment_id가 중복이다")
                    )
                seen_segments.add(segment_id)
            findings.extend(_check_transcript_segment(segment, spot, speech_index, capability))

    findings.extend(check_asr_capability_binding(transcript, location))
    return findings


def _check_speaker_label_pair(
    node: Mapping[str, Any], where: str, findings: list[Finding]
) -> None:
    """speaker_label과 speaker_label_source는 함께 있어야 한다 (§4.2 R13)."""

    has_label = "speaker_label" in node
    has_source = "speaker_label_source" in node
    if has_label and not has_source:
        findings.append(
            _finding(
                f"{where}/speaker_label",
                "E_SCHEMA",
                "speaker_label에는 speaker_label_source(input|adapter)가 함께 있어야 한다",
            )
        )
    if has_source and not has_label:
        findings.append(
            _finding(
                f"{where}/speaker_label_source",
                "E_SCHEMA",
                "speaker_label_source는 speaker_label이 있을 때만 쓴다",
            )
        )


def _check_transcript_segment(
    segment: Mapping[str, Any],
    where: str,
    speech_index: Mapping[str, tuple[float, float, str]],
    capability: Mapping[str, Any],
) -> list[Finding]:
    findings: list[Finding] = []

    text = _scalar_text(segment.get("text"), f"{where}/text", findings)
    _check_speaker_label_pair(segment, where, findings)
    _check_review_state(segment, where, findings)

    start, end = segment.get("start_seconds"), segment.get("end_seconds")
    valid_time = _check_half_open(start, end, where, findings, what="ASR segment")

    # 입력 SpeechSegment lineage — 존재·단일 stream·시간 포함.
    sources = segment.get("source_speech_segment_ids")
    intervals: list[tuple[float, float]] = []
    if isinstance(sources, list):
        streams: set[str] = set()
        for position, source_id in enumerate(sources):
            entry = speech_index.get(source_id) if isinstance(source_id, str) else None
            if entry is None:
                findings.append(
                    _finding(
                        f"{where}/source_speech_segment_ids/{position}",
                        "E_SOURCE_REF",
                        "존재하지 않는 SpeechSegment를 참조했다",
                    )
                )
                continue
            intervals.append((entry[0], entry[1]))
            streams.add(entry[2])
        if len(streams) > 1:
            findings.append(
                _finding(
                    f"{where}/source_speech_segment_ids",
                    "E_SOURCE_REF",
                    "서로 다른 stream의 입력을 한 segment lineage로 섞었다",
                )
            )
        if valid_time and intervals and len(intervals) == len(sources):
            findings.extend(_check_within_union(float(start), float(end), intervals, where))

    findings.extend(_check_tokens(segment, where, valid_time, capability))
    findings.extend(_check_segment_confidence(segment, where, capability))
    findings.extend(_check_alternatives(segment, where, capability))
    findings.extend(_check_language_spans(segment, where, text, capability))
    return findings


def _check_within_union(
    start: float, end: float, intervals: Sequence[tuple[float, float]], where: str
) -> list[Finding]:
    """ASR segment 시간이 참조한 입력 구간들의 합집합 안에 있는지 (§4.2 R2)."""

    merged: list[list[float]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])

    def covered(point: float) -> bool:
        return any(low <= point <= high for low, high in merged)

    findings: list[Finding] = []
    if not covered(start):
        findings.append(
            _finding(
                f"{where}/start_seconds",
                "E_TIME_RANGE",
                "ASR segment 시작이 참조한 입력 SpeechSegment 범위의 합집합 밖이다",
            )
        )
    if not covered(end):
        findings.append(
            _finding(
                f"{where}/end_seconds",
                "E_TIME_RANGE",
                "ASR segment 끝이 참조한 입력 SpeechSegment 범위의 합집합 밖이다",
            )
        )
    return findings


def _check_tokens(
    segment: Mapping[str, Any],
    where: str,
    valid_time: bool,
    capability: Mapping[str, Any],
) -> list[Finding]:
    findings: list[Finding] = []
    tokens = segment.get("tokens")
    if not isinstance(tokens, list):
        return findings

    semantics = capability.get("token_confidence_semantics")
    previous: tuple[float, float] | None = None
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue
        spot = f"{where}/tokens/{index}"
        _scalar_text(token.get("text"), f"{spot}/text", findings)

        has_start = "start_seconds" in token
        has_end = "end_seconds" in token
        if has_start != has_end:
            findings.append(
                _finding(
                    spot,
                    "E_TIME_RANGE",
                    "token의 start_seconds와 end_seconds는 둘 다 있거나 둘 다 없어야 한다",
                )
            )
        elif has_start:
            start, end = token["start_seconds"], token["end_seconds"]
            if not _finite(start) or not _finite(end):
                findings.append(
                    _finding(f"{spot}/end_seconds", "E_TIME_RANGE", "token 시간이 finite 숫자가 아니다")
                )
            else:
                start, end = float(start), float(end)
                if end < start:
                    findings.append(
                        _finding(f"{spot}/end_seconds", "E_TIME_RANGE", "token 시간이 역전됐다")
                    )
                if valid_time:
                    lower, upper = float(segment["start_seconds"]), float(segment["end_seconds"])
                    if start < lower:
                        findings.append(
                            _finding(
                                f"{spot}/start_seconds",
                                "E_TIME_RANGE",
                                "token 시작이 ASR segment 범위 밖이다",
                            )
                        )
                    if end > upper:
                        findings.append(
                            _finding(
                                f"{spot}/end_seconds",
                                "E_TIME_RANGE",
                                "token 끝이 ASR segment 범위 밖이다",
                            )
                        )
                if previous is not None and (start < previous[0] or end < previous[1]):
                    findings.append(
                        _finding(
                            f"{spot}/start_seconds",
                            "E_TIME_ORDER",
                            "token timing이 시간순이 아니다",
                        )
                    )
                previous = (start, end)

        if "confidence" in token:
            if semantics in (None, "none"):
                findings.append(
                    _finding(
                        f"{spot}/confidence",
                        "E_CAPABILITY_MISMATCH",
                        "token_confidence_semantics=none인 adapter가 token confidence를 냈다",
                    )
                )
            else:
                _check_confidence_value(token["confidence"], semantics, f"{spot}/confidence", findings)
    return findings


def _check_segment_confidence(
    segment: Mapping[str, Any], where: str, capability: Mapping[str, Any]
) -> list[Finding]:
    findings: list[Finding] = []
    if "segment_confidence" not in segment:
        return findings
    semantics = capability.get("segment_confidence_semantics")
    if semantics in (None, "none"):
        findings.append(
            _finding(
                f"{where}/segment_confidence",
                "E_CAPABILITY_MISMATCH",
                "segment_confidence_semantics=none인 adapter가 segment confidence를 냈다",
            )
        )
        return findings
    _check_confidence_value(
        segment["segment_confidence"], semantics, f"{where}/segment_confidence", findings
    )
    return findings


def _check_alternatives(
    segment: Mapping[str, Any], where: str, capability: Mapping[str, Any]
) -> list[Finding]:
    findings: list[Finding] = []
    alternatives = segment.get("alternatives")
    if not isinstance(alternatives, list):
        return findings
    if capability.get("supports_nbest") is not True and alternatives:
        findings.append(
            _finding(
                f"{where}/alternatives",
                "E_CAPABILITY_MISMATCH",
                "supports_nbest=false인 adapter가 alternatives를 냈다",
            )
        )
    semantics = capability.get("nbest_score_semantics")
    for index, alternative in enumerate(alternatives):
        if not isinstance(alternative, dict):
            continue
        spot = f"{where}/alternatives/{index}"
        _scalar_text(alternative.get("text"), f"{spot}/text", findings)
        if "score" in alternative:
            if semantics in (None, "none"):
                findings.append(
                    _finding(
                        f"{spot}/score",
                        "E_CAPABILITY_MISMATCH",
                        "nbest_score_semantics=none인데 alternative score가 있다",
                    )
                )
            else:
                _check_confidence_value(alternative["score"], semantics, f"{spot}/score", findings)
    return findings


def _check_language_spans(
    segment: Mapping[str, Any],
    where: str,
    text: str | None,
    capability: Mapping[str, Any],
) -> list[Finding]:
    """§4.2 R4·R6~R11 — scalar 범위, 순서, switch 경계, gap/und review, dominant 파생."""

    findings: list[Finding] = []
    spans = segment.get("language_spans")
    has_dominant = "dominant_language" in segment

    if capability.get("supports_language_id") is not True:
        if isinstance(spans, list) and spans:
            findings.append(
                _finding(
                    f"{where}/language_spans",
                    "E_CAPABILITY_MISMATCH",
                    "supports_language_id=false인 adapter가 language_spans를 냈다",
                )
            )
        if has_dominant:
            findings.append(
                _finding(
                    f"{where}/dominant_language",
                    "E_CAPABILITY_MISMATCH",
                    "supports_language_id=false인 adapter가 dominant_language를 냈다",
                )
            )
    if not isinstance(spans, list) or not spans:
        return findings

    language_semantics = capability.get("language_confidence_semantics")
    supports_intra = capability.get("supports_intra_sentential_lid") is True

    usable: list[tuple[int, int, str]] = []
    previous_end = 0
    for index, span in enumerate(spans):
        if not isinstance(span, dict):
            continue
        spot = f"{where}/language_spans/{index}"
        start, end = span.get("char_start"), span.get("char_end")
        ok = isinstance(start, int) and isinstance(end, int) and not isinstance(start, bool)
        if ok and end <= start:
            findings.append(
                _finding(f"{spot}/char_end", "E_OFFSET_RANGE", "빈 범위이거나 역전된 scalar 범위다")
            )
            ok = False
        if ok and text is not None and end > len(text):
            findings.append(
                _finding(f"{spot}/char_end", "E_OFFSET_RANGE", "scalar 범위가 text 길이를 넘는다")
            )
            ok = False
        if ok and index > 0 and start < previous_end:
            findings.append(
                _finding(
                    f"{spot}/char_start",
                    "E_OFFSET_ORDER",
                    "language span이 char_start 오름차순·비중첩이 아니다",
                )
            )
            ok = False
        if ok:
            previous_end = end
            language = span.get("language")
            usable.append((start, end, language if isinstance(language, str) else ""))

        if index == 0 and "switch_kind" in span:
            findings.append(
                _finding(
                    f"{spot}/switch_kind",
                    "E_SCHEMA",
                    "첫 language span에는 switch_kind를 쓰지 않는다 — 들어오는 경계가 없다",
                )
            )
        if index > 0 and "switch_kind" not in span:
            findings.append(
                _finding(
                    spot,
                    "E_SCHEMA",
                    "두 번째 이후 language span에는 switch_kind가 필수다",
                )
            )
        if span.get("switch_kind") == "intra_sentential" and not supports_intra:
            findings.append(
                _finding(
                    f"{spot}/switch_kind",
                    "E_CAPABILITY_MISMATCH",
                    "supports_intra_sentential_lid=false인 adapter가 intra_sentential 전환을 냈다",
                )
            )
        if "confidence" in span:
            if language_semantics in (None, "none"):
                findings.append(
                    _finding(
                        f"{spot}/confidence",
                        "E_CAPABILITY_MISMATCH",
                        "language_confidence_semantics=none인데 language span confidence가 있다",
                    )
                )
            else:
                _check_confidence_value(
                    span["confidence"], language_semantics, f"{spot}/confidence", findings
                )

    if text is None:
        return findings

    findings.extend(_check_language_coverage(segment, where, text, usable, has_dominant))
    return findings


def _check_language_coverage(
    segment: Mapping[str, Any],
    where: str,
    text: str,
    spans: Sequence[tuple[int, int, str]],
    has_dominant: bool,
) -> list[Finding]:
    """gap·explicit `und`의 review 의무와 `dominant_language` 파생 규칙 (§4.2 R6·R10)."""

    findings: list[Finding] = []
    known: list[tuple[int, int, str]] = []
    has_und = False
    cursor = 0
    has_gap = False
    for start, end, language in spans:
        if start > cursor:
            has_gap = True
        cursor = max(cursor, end)
        if language == UNDETERMINED_LANGUAGE:
            has_und = True
        else:
            known.append((start, end, language))
    if cursor < len(text):
        has_gap = True

    reasons = segment.get("review_reasons")
    reasons = reasons if isinstance(reasons, list) else []
    if has_gap or has_und:
        if segment.get("needs_review") is not True or "language_unknown" not in reasons:
            findings.append(
                _finding(
                    f"{where}/needs_review",
                    "E_LANGUAGE_GAP_REVIEW",
                    "language span gap 또는 explicit und가 있으면 "
                    "needs_review=true와 language_unknown review reason이 필수다",
                )
            )
        if has_dominant:
            findings.append(
                _finding(
                    f"{where}/dominant_language",
                    "E_LANGUAGE_GAP_REVIEW",
                    "gap 또는 und 범위가 있으면 dominant_language를 생략한다",
                )
            )
        return findings

    if has_dominant and known:
        totals: dict[str, int] = {}
        for start, end, language in known:
            totals[language] = totals.get(language, 0) + (end - start)
        best = max(totals.values())
        expected = next(language for _, _, language in known if totals[language] == best)
        if segment.get("dominant_language") != expected:
            findings.append(
                _finding(
                    f"{where}/dominant_language",
                    "E_LANGUAGE_GAP_REVIEW",
                    "dominant_language가 파생 규칙(길이 합 최대, 동률은 첫 span)과 다르다",
                )
            )
    return findings


def check_asr_capability_binding(
    transcript: Mapping[str, Any], location: str = "transcript"
) -> list[Finding]:
    """capability snapshot ↔ 실행 feature_status ↔ 실제 결과 필드의 삼자 결박 (§4.3)."""

    findings: list[Finding] = []
    capability = transcript.get("capability_report")
    if not isinstance(capability, dict):
        return findings
    capability_location = f"{location}/capability_report"

    _check_language_tags(
        capability.get("supported_languages"), f"{capability_location}/supported_languages", findings
    )

    units = capability.get("token_timing_units")
    units = units if isinstance(units, list) else []
    if capability.get("supports_word_timing") is not ("word" in units):
        findings.append(
            _finding(
                f"{capability_location}/supports_word_timing",
                "E_CAPABILITY_MISMATCH",
                "supports_word_timing은 token_timing_units에 word가 있을 때만 true다",
            )
        )
    if "max_candidate_languages" in capability and capability.get("restricts_candidate_languages") is not True:
        findings.append(
            _finding(
                f"{capability_location}/max_candidate_languages",
                "E_CAPABILITY_MISMATCH",
                "max_candidate_languages는 restricts_candidate_languages=true일 때만 쓴다",
            )
        )

    segments = _transcript_segments(transcript, location)
    evidence = {
        "token_timing": any(
            isinstance(token, dict) and "start_seconds" in token and "end_seconds" in token
            for segment in segments
            for token in (segment.node.get("tokens") or [])
        ),
        "token_confidence": any(
            isinstance(token, dict) and "confidence" in token
            for segment in segments
            for token in (segment.node.get("tokens") or [])
        ),
        "segment_confidence": any("segment_confidence" in segment.node for segment in segments),
        "language_id": any(
            (segment.node.get("language_spans") or []) or "dominant_language" in segment.node
            for segment in segments
        ),
        "language_confidence": any(
            isinstance(span, dict) and "confidence" in span
            for segment in segments
            for span in (segment.node.get("language_spans") or [])
        ),
        # independent channel의 stream 귀속·input label은 adapter diarization이 아니다.
        "speaker_diarization": any(
            segment.node.get("speaker_label_source") == "adapter" for segment in segments
        ),
        "nbest": any(bool(segment.node.get("alternatives")) for segment in segments),
    }
    supported = {
        "token_timing": bool(units),
        "token_confidence": capability.get("token_confidence_semantics") not in (None, "none"),
        "segment_confidence": capability.get("segment_confidence_semantics") not in (None, "none"),
        "language_id": capability.get("supports_language_id") is True,
        "language_confidence": capability.get("language_confidence_semantics") not in (None, "none"),
        "speaker_diarization": capability.get("supports_diarization") is True,
        "nbest": capability.get("supports_nbest") is True,
    }

    status_map = transcript.get("feature_status")
    status_map = status_map if isinstance(status_map, dict) else {}
    findings.extend(
        _check_feature_status(
            status_map,
            ASR_FEATURE_KEYS,
            supported,
            evidence,
            f"{location}/feature_status",
        )
    )

    token_unit = transcript.get("token_unit")
    if evidence["token_timing"] and units and token_unit not in units:
        findings.append(
            _finding(
                f"{location}/token_unit",
                "E_CAPABILITY_MISMATCH",
                "token timing이 있으면 token_unit이 capability의 token_timing_units에 있어야 한다",
            )
        )
    return findings


def _check_feature_status(
    status_map: Mapping[str, Any],
    keys: Sequence[str],
    supported: Mapping[str, bool],
    evidence: Mapping[str, bool],
    location: str,
) -> list[Finding]:
    """`produced | not_requested | no_result | unsupported`의 독립 결박 (§4.3)."""

    findings: list[Finding] = []
    for key in keys:
        status = status_map.get(key)
        if status is None:
            continue
        spot = f"{location}/{key}"
        if not supported[key] and status != "unsupported":
            findings.append(
                _finding(
                    spot,
                    "E_CAPABILITY_MISMATCH",
                    "capability가 지원하지 않는 축의 feature_status는 unsupported여야 한다",
                )
            )
        if supported[key] and status == "unsupported":
            findings.append(
                _finding(
                    spot,
                    "E_CAPABILITY_MISMATCH",
                    "capability가 지원하는 축을 unsupported로 보고했다",
                )
            )
        if status == "produced" and not evidence[key]:
            findings.append(
                _finding(spot, "E_CAPABILITY_MISMATCH", "produced인데 대응 결과 필드가 없다")
            )
        if status != "produced" and evidence[key]:
            findings.append(
                _finding(
                    spot,
                    "E_CAPABILITY_MISMATCH",
                    "produced가 아닌데 대응 결과 필드가 존재한다",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# TranslatedTranscript
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TranslationSegment:
    segment_id: str
    stream_id: str
    target_text: str | None
    location: str
    node: Mapping[str, Any]
    order: int


def _translation_segments(
    document: Mapping[str, Any], location: str
) -> list[_TranslationSegment]:
    collected: list[_TranslationSegment] = []
    order = 0
    for stream_index, stream in enumerate(document.get("streams") or []):
        if not isinstance(stream, dict):
            continue
        stream_id = stream.get("stream_id")
        for segment_index, segment in enumerate(stream.get("segments") or []):
            if not isinstance(segment, dict):
                continue
            target = segment.get("target_text")
            collected.append(
                _TranslationSegment(
                    segment_id=segment.get("segment_id") if isinstance(segment.get("segment_id"), str) else "",
                    stream_id=stream_id if isinstance(stream_id, str) else "",
                    target_text=target if isinstance(target, str) else None,
                    location=f"{location}/streams/{stream_index}/segments/{segment_index}",
                    node=segment,
                    order=order,
                )
            )
            order += 1
    return collected


def check_translated_transcript(
    document: Mapping[str, Any],
    transcript: Mapping[str, Any] | None,
    location: str = "translated_transcript",
) -> list[Finding]:
    """번역 산출물 불변식 (TASK-029 §4.4) + source Transcript 참조·coverage partition."""

    findings: list[Finding] = []

    if document.get("target_language") != TARGET_LANGUAGE:
        findings.append(
            _finding(
                f"{location}/target_language",
                "E_TARGET_LANGUAGE",
                f"성공 번역 산출물의 target_language는 정확히 {TARGET_LANGUAGE!r}여야 한다",
            )
        )

    findings.extend(check_translation_capability_binding(document, location))

    if transcript is None:
        findings.append(
            _finding(
                f"{location}/source_transcript",
                "E_SOURCE_REF",
                "번역 문서를 검증할 source Transcript가 문서 집합에 없다",
            )
        )
        return findings

    if document.get("timebase_ref") != transcript.get("timebase_ref"):
        findings.append(
            _finding(
                f"{location}/timebase_ref",
                "E_SOURCE_REF",
                "원문 Transcript와 다른 timebase_ref다",
            )
        )

    source_segments = _transcript_segments(transcript, "transcript")
    source_index = {segment.segment_id: segment for segment in source_segments if segment.segment_id}
    source_streams = {segment.stream_id for segment in source_segments}

    for stream_index, stream in enumerate(document.get("streams") or []):
        if isinstance(stream, dict) and stream.get("stream_id") not in source_streams:
            findings.append(
                _finding(
                    f"{location}/streams/{stream_index}/stream_id",
                    "E_SOURCE_REF",
                    "원문 Transcript에 없는 stream lineage다",
                )
            )

    #: source segment id -> [_Range]. covered와 uncovered를 한 축에서 partition한다.
    coverage: dict[str, list[_Range]] = {}
    order_counter = 0

    for segment in _translation_segments(document, location):
        node, where = segment.node, segment.location
        _check_review_state(node, where, findings)
        _scalar_text(node.get("target_text"), f"{where}/target_text", findings)
        fragments = node.get("source_fragments")
        fragments = fragments if isinstance(fragments, list) else []
        resolved: list[tuple[int, int, str, str]] = []

        previous_key: tuple[str, int] | None = None
        for index, fragment in enumerate(fragments):
            if not isinstance(fragment, dict):
                continue
            spot = f"{where}/source_fragments/{index}"
            source_id = fragment.get("source_segment_id")
            source = source_index.get(source_id) if isinstance(source_id, str) else None
            if source is None:
                findings.append(
                    _finding(
                        f"{spot}/source_segment_id",
                        "E_SOURCE_REF",
                        "존재하지 않는 Transcript segment를 참조했다",
                    )
                )
                continue
            bounds = _check_fragment_range(fragment, source.text, spot, findings)
            if bounds is None:
                continue
            start, end = bounds
            if previous_key is not None and previous_key[0] == source_id and start < previous_key[1]:
                findings.append(
                    _finding(
                        f"{spot}/char_start",
                        "E_OFFSET_ORDER",
                        "같은 source segment의 fragment가 원문 순서·비중첩이 아니다",
                    )
                )
            previous_key = (source_id, end)
            resolved.append((start, end, source_id, spot))
            coverage.setdefault(source_id, []).append(
                _Range(start=start, end=end, location=f"{spot}/char_start", order=order_counter,
                       group="covered")
            )
            order_counter += 1

        findings.extend(_check_alignment_kind(node, where, resolved, source_index))

    findings.extend(
        _check_uncovered_fragments(document, location, source_index, coverage, order_counter)
    )
    findings.extend(_check_coverage_partition(document, location, source_index, coverage))
    return findings


def _check_fragment_range(
    fragment: Mapping[str, Any],
    text: str | None,
    spot: str,
    findings: list[Finding],
) -> tuple[int, int] | None:
    """scalar 반개구간의 유효성과 exact substring 동치를 확인한다."""

    start, end = fragment.get("char_start"), fragment.get("char_end")
    if not isinstance(start, int) or isinstance(start, bool):
        return None
    if not isinstance(end, int) or isinstance(end, bool):
        return None
    if end <= start:
        findings.append(
            _finding(f"{spot}/char_end", "E_OFFSET_RANGE", "빈 범위이거나 역전된 scalar 범위다")
        )
        return None
    if text is None:
        return None
    if end > len(text):
        findings.append(
            _finding(f"{spot}/char_end", "E_OFFSET_RANGE", "scalar 범위가 원문 text 길이를 넘는다")
        )
        return None
    stored = fragment.get("source_text")
    if _scalar_text(stored, f"{spot}/source_text", findings) is None and isinstance(stored, str):
        return None
    if stored != text[start:end]:
        findings.append(
            _finding(
                f"{spot}/source_text",
                "E_SOURCE_TEXT",
                "source_text가 해당 scalar 범위의 exact substring과 다르다",
            )
        )
    return start, end


def _check_alignment_kind(
    node: Mapping[str, Any],
    where: str,
    resolved: Sequence[tuple[int, int, str, str]],
    source_index: Mapping[str, _TranscriptSegment],
) -> list[Finding]:
    """alignment_kind와 source fragment 모양의 일치 (§4.4 R2~R6)."""

    findings: list[Finding] = []
    kind = node.get("alignment_kind")
    target = node.get("target_text")
    reasons = node.get("review_reasons")
    reasons = reasons if isinstance(reasons, list) else []
    distinct = {source_id for _, _, source_id, _ in resolved}

    if kind == "one_to_one":
        whole = False
        if len(resolved) == 1:
            start, end, source_id, _ = resolved[0]
            source = source_index.get(source_id)
            whole = source is not None and source.text is not None and start == 0 and end == len(source.text)
        if not whole:
            findings.append(
                _finding(
                    f"{where}/alignment_kind",
                    "E_ALIGNMENT",
                    "one_to_one은 한 source segment 전체를 정확히 하나의 fragment로 참조해야 한다",
                )
            )
    elif kind == "merged":
        if len(resolved) < 2 or len(distinct) < 2:
            findings.append(
                _finding(
                    f"{where}/alignment_kind",
                    "E_ALIGNMENT",
                    "merged는 서로 다른 source segment 2개 이상을 참조해야 한다",
                )
            )
    elif kind == "split":
        strict = False
        if len(resolved) == 1 and len(distinct) == 1:
            start, end, source_id, _ = resolved[0]
            source = source_index.get(source_id)
            strict = (
                source is not None
                and source.text is not None
                and not (start == 0 and end == len(source.text))
            )
        if not strict:
            findings.append(
                _finding(
                    f"{where}/alignment_kind",
                    "E_ALIGNMENT",
                    "split은 한 source segment의 non-empty strict subrange 하나를 참조해야 한다",
                )
            )
    elif kind == "dropped":
        if target != "":
            findings.append(
                _finding(
                    f"{where}/target_text",
                    "E_ALIGNMENT",
                    "dropped 번역 segment의 target_text는 빈 문자열이어야 한다",
                )
            )
        if "untranslated_span" not in reasons:
            findings.append(
                _finding(
                    f"{where}/review_reasons",
                    "E_REVIEW_STATE",
                    "dropped 번역 segment에는 untranslated_span review reason이 필수다",
                )
            )

    if kind != "dropped" and target == "":
        findings.append(
            _finding(
                f"{where}/target_text",
                "E_ALIGNMENT",
                "dropped가 아닌 번역 segment의 target_text는 비어 있을 수 없다",
            )
        )
    return findings


def _check_uncovered_fragments(
    document: Mapping[str, Any],
    location: str,
    source_index: Mapping[str, _TranscriptSegment],
    coverage: dict[str, list[_Range]],
    order_start: int,
) -> list[Finding]:
    findings: list[Finding] = []
    uncovered = document.get("uncovered_source_fragments")
    uncovered = uncovered if isinstance(uncovered, list) else []
    order = order_start
    previous_key: tuple[str, int] | None = None

    for index, fragment in enumerate(uncovered):
        if not isinstance(fragment, dict):
            continue
        spot = f"{location}/uncovered_source_fragments/{index}"
        # uncovered fragment의 needs_review=true는 schema의 review_reasons minItems 1과
        # 아래 동치 검사의 **조합**으로 성립한다. 같은 위치를 두 번 보고하는 중복 검사를
        # 따로 두지 않는다 (reasons가 비면 schema가 먼저 거른다).
        _check_review_state(fragment, spot, findings)
        source_id = fragment.get("source_segment_id")
        source = source_index.get(source_id) if isinstance(source_id, str) else None
        if source is None:
            findings.append(
                _finding(
                    f"{spot}/source_segment_id",
                    "E_SOURCE_REF",
                    "존재하지 않는 Transcript segment를 참조했다",
                )
            )
            continue
        bounds = _check_fragment_range(fragment, source.text, spot, findings)
        if bounds is None:
            continue
        start, end = bounds
        if previous_key is not None and previous_key[0] == source_id and start < previous_key[1]:
            findings.append(
                _finding(
                    f"{spot}/char_start",
                    "E_OFFSET_ORDER",
                    "같은 source segment의 uncovered fragment가 원문 순서·비중첩이 아니다",
                )
            )
        previous_key = (source_id, end)
        coverage.setdefault(source_id, []).append(
            _Range(start=start, end=end, location=f"{spot}/char_start", order=order,
                   group="uncovered")
        )
        order += 1

    status = document.get("coverage_status")
    if status == "complete" and uncovered:
        findings.append(
            _finding(
                f"{location}/coverage_status",
                "E_SOURCE_COVERAGE",
                "complete는 uncovered_source_fragments가 비어 있을 때와 동치다",
            )
        )
    if status == "partial" and not uncovered:
        findings.append(
            _finding(
                f"{location}/coverage_status",
                "E_SOURCE_COVERAGE",
                "partial은 uncovered_source_fragments가 하나 이상일 때와 동치다",
            )
        )
    return findings


def _check_coverage_partition(
    document: Mapping[str, Any],
    location: str,
    source_index: Mapping[str, _TranscriptSegment],
    coverage: Mapping[str, list[_Range]],
) -> list[Finding]:
    """covered + uncovered가 원문의 모든 non-empty scalar range를 정확히 한 번 덮는지."""

    findings: list[Finding] = []
    gap_location = f"{location}/uncovered_source_fragments"
    for segment_id in sorted(source_index):
        source = source_index[segment_id]
        if source.text is None:
            continue
        _check_partition(
            coverage.get(segment_id, []),
            len(source.text),
            gap_location=gap_location,
            coverage_code="E_SOURCE_COVERAGE",
            subject=f"source segment {segment_id!r}의 번역 coverage",
            findings=findings,
        )
    return findings


def check_translation_capability_binding(
    document: Mapping[str, Any], location: str = "translated_transcript"
) -> list[Finding]:
    """TranslationCapabilityReport ↔ feature_status ↔ 결과 필드 결박 (§4.4)."""

    findings: list[Finding] = []
    capability = document.get("capability_report")
    if not isinstance(capability, dict):
        return findings
    capability_location = f"{location}/capability_report"

    for key in ("supported_source_languages", "supported_target_languages"):
        _check_language_tags(capability.get(key), f"{capability_location}/{key}", findings)

    targets = capability.get("supported_target_languages")
    if not isinstance(targets, list) or TARGET_LANGUAGE not in targets:
        findings.append(
            _finding(
                f"{capability_location}/supported_target_languages",
                "E_TARGET_LANGUAGE",
                f"성공 결과를 낼 capability snapshot에는 exact {TARGET_LANGUAGE!r}가 있어야 한다",
            )
        )

    segments = _translation_segments(document, location)
    semantics = capability.get("translation_confidence_semantics")
    for segment in segments:
        if "confidence" not in segment.node:
            continue
        spot = f"{segment.location}/confidence"
        if semantics in (None, "none"):
            findings.append(
                _finding(
                    spot,
                    "E_CAPABILITY_MISMATCH",
                    "translation_confidence_semantics=none인데 confidence가 있다",
                )
            )
        else:
            _check_confidence_value(segment.node["confidence"], semantics, spot, findings)

    evidence = {
        "segment_alignment": any(
            segment.node.get("alignment_evidence_source") == "adapter" for segment in segments
        ),
        "translation_confidence": any("confidence" in segment.node for segment in segments),
    }
    supported = {
        "segment_alignment": capability.get("supports_segment_alignment") is True,
        "translation_confidence": semantics not in (None, "none"),
    }
    status_map = document.get("feature_status")
    status_map = status_map if isinstance(status_map, dict) else {}
    findings.extend(
        _check_feature_status(
            status_map,
            TRANSLATION_FEATURE_KEYS,
            supported,
            evidence,
            f"{location}/feature_status",
        )
    )
    return findings


# ---------------------------------------------------------------------------
# SubtitleDocument
# ---------------------------------------------------------------------------


def check_subtitle_document(
    document: Mapping[str, Any],
    transcript: Mapping[str, Any] | None,
    translated: Mapping[str, Any] | None,
    location: str = "subtitle_document",
) -> list[Finding]:
    """표시 자막 문서 불변식 (TASK-029 §4.5) + 축·lineage·cue 시간 규칙."""

    findings: list[Finding] = []
    axis = document.get("text_axis")

    findings.extend(_check_axis(document, axis, transcript, translated, location))
    findings.extend(_check_resolved_style(document, location))
    findings.extend(_check_cue_times(document, location))
    findings.extend(_check_unsupported_features(document, location))

    direct, other = _axis_indexes(axis, transcript, translated)
    if direct is None:
        return findings
    findings.extend(_check_cue_lineage(document, location, direct, other))
    return findings


def _axis_indexes(
    axis: Any,
    transcript: Mapping[str, Any] | None,
    translated: Mapping[str, Any] | None,
) -> tuple[dict[str, str] | None, dict[str, str]]:
    """(직접 입력 segment_id -> text, 반대 축 segment_id -> text)."""

    source_map: dict[str, str] = {}
    if isinstance(transcript, dict):
        for segment in _transcript_segments(transcript, "transcript"):
            if segment.segment_id and segment.text is not None:
                source_map[segment.segment_id] = segment.text
    target_map: dict[str, str] = {}
    if isinstance(translated, dict):
        for segment in _translation_segments(translated, "translated_transcript"):
            if segment.segment_id and segment.target_text is not None:
                target_map[segment.segment_id] = segment.target_text

    if axis == "source":
        return (source_map if isinstance(transcript, dict) else None), target_map
    if axis == "target":
        return (target_map if isinstance(translated, dict) else None), source_map
    return None, {}


def _check_axis(
    document: Mapping[str, Any],
    axis: Any,
    transcript: Mapping[str, Any] | None,
    translated: Mapping[str, Any] | None,
    location: str,
) -> list[Finding]:
    findings: list[Finding] = []
    has_target_language = "target_language" in document

    if axis == "target":
        if not isinstance(translated, dict):
            findings.append(
                _finding(
                    f"{location}/text_axis",
                    "E_TEXT_AXIS",
                    "text_axis=target의 직접 입력 TranslatedTranscript가 문서 집합에 없다",
                )
            )
        if "source_transcript_ref" not in document:
            findings.append(
                _finding(
                    f"{location}/text_axis",
                    "E_TEXT_AXIS",
                    "text_axis=target이면 원본 Transcript ref가 필수다",
                )
            )
        if not has_target_language:
            findings.append(
                _finding(
                    f"{location}/text_axis",
                    "E_TARGET_LANGUAGE",
                    f"text_axis=target 문서에는 target_language={TARGET_LANGUAGE!r}가 필수다",
                )
            )
        elif document.get("target_language") != TARGET_LANGUAGE:
            findings.append(
                _finding(
                    f"{location}/target_language",
                    "E_TARGET_LANGUAGE",
                    f"target 자막 문서의 target_language는 정확히 {TARGET_LANGUAGE!r}여야 한다",
                )
            )
    elif axis == "source":
        if not isinstance(transcript, dict):
            findings.append(
                _finding(
                    f"{location}/text_axis",
                    "E_TEXT_AXIS",
                    "text_axis=source의 직접 입력 Transcript가 문서 집합에 없다",
                )
            )
        if has_target_language:
            findings.append(
                _finding(
                    f"{location}/target_language",
                    "E_TEXT_AXIS",
                    "text_axis=source 문서는 target_language를 갖지 않는다",
                )
            )
        if "source_transcript_ref" in document:
            findings.append(
                _finding(
                    f"{location}/source_transcript_ref",
                    "E_TEXT_AXIS",
                    "source_transcript_ref는 text_axis=target일 때만 쓴다",
                )
            )
    return findings


def _check_resolved_style(document: Mapping[str, Any], location: str) -> list[Finding]:
    findings: list[Finding] = []
    style = document.get("resolved_style")
    if not isinstance(style, dict):
        return findings

    def compare(effective: Mapping[str, Any], present: Mapping[str, Any], where: str) -> None:
        """`effective`는 override를 반영한 실효값, `present`는 그 문서에 실제 있는 필드다.

        위치는 실제 입력에서 해석돼야 하므로(§8) override에 없는 필드를 가리키지 않고
        존재하는 필드나 override 객체 자체로 좁힌다.
        """

        low = effective.get("min_duration_seconds")
        high = effective.get("max_duration_seconds")
        if not (_finite(low) and _finite(high) and float(high) <= float(low)):
            return
        for field in ("max_duration_seconds", "min_duration_seconds"):
            if field in present:
                spot = f"{where}/{field}"
                break
        else:
            spot = where
        findings.append(
            _finding(
                spot,
                "E_TIME_RANGE",
                "max_duration_seconds는 min_duration_seconds보다 커야 한다",
            )
        )

    compare(style, style, f"{location}/resolved_style")
    overrides = style.get("language_overrides")
    if isinstance(overrides, dict):
        for key in sorted(overrides):
            node = overrides[key]
            if isinstance(node, dict):
                compare({**style, **node}, node, f"{location}/resolved_style/language_overrides/{key}")
    return findings


def _check_cue_times(document: Mapping[str, Any], location: str) -> list[Finding]:
    """positive duration · canonical order · 같은 stream 겹침 금지 · concurrent 참조."""

    findings: list[Finding] = []
    cues = document.get("cues")
    cues = cues if isinstance(cues, list) else []
    usable: list[tuple[int, str, str, float, float, list[str]]] = []

    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            continue
        where = f"{location}/cues/{index}"
        _check_review_state(cue, where, findings)
        start, end = cue.get("start_seconds"), cue.get("end_seconds")
        if not _check_half_open(start, end, where, findings, what="cue"):
            continue
        cue_id = cue.get("cue_id")
        stream_id = cue.get("stream_id")
        concurrent = cue.get("concurrent_cue_ids")
        if not isinstance(cue_id, str) or not isinstance(stream_id, str) or not isinstance(concurrent, list):
            continue
        usable.append((index, cue_id, stream_id, float(start), float(end), concurrent))
        if cue.get("overlap_kind") == "none" and concurrent:
            findings.append(
                _finding(
                    f"{where}/overlap_kind",
                    "E_CUE_REF",
                    "overlap_kind=none인 cue는 concurrent cue를 선언하지 않는다",
                )
            )

    for previous, current in zip(usable, usable[1:]):
        previous_key = (previous[3], previous[4], previous[2], previous[1])
        current_key = (current[3], current[4], current[2], current[1])
        if current_key < previous_key:
            findings.append(
                _finding(
                    f"{location}/cues/{current[0]}",
                    "E_CUE_ORDER",
                    "cue 배열이 (start_seconds, end_seconds, stream_id, cue_id) 오름차순이 아니다",
                )
            )

    for position, current in enumerate(usable):
        for other in usable[position + 1 :]:
            if current[2] == other[2] and _overlaps(current[3], current[4], other[3], other[4]):
                findings.append(
                    _finding(
                        f"{location}/cues/{other[0]}",
                        "E_CUE_OVERLAP",
                        "같은 stream_id의 cue 시간이 겹친다",
                    )
                )

    by_id = {entry[1]: entry for entry in usable}
    for entry in usable:
        index, cue_id, _stream, start, end, concurrent = entry
        for position, other_id in enumerate(concurrent):
            spot = f"{location}/cues/{index}/concurrent_cue_ids/{position}"
            if other_id == cue_id:
                findings.append(_finding(spot, "E_CUE_REF", "자기 자신을 concurrent cue로 참조했다"))
                continue
            other = by_id.get(other_id)
            if other is None:
                findings.append(_finding(spot, "E_CUE_REF", "존재하지 않는 cue를 참조했다"))
                continue
            if not _overlaps(start, end, other[3], other[4]):
                findings.append(
                    _finding(spot, "E_CUE_REF", "선언한 concurrent cue와 실제 시간이 겹치지 않는다")
                )
                continue
            if cue_id not in other[5]:
                findings.append(
                    _finding(spot, "E_CUE_REF", "concurrent cue 참조가 상호 대칭이 아니다")
                )
    return findings


def _check_unsupported_features(document: Mapping[str, Any], location: str) -> list[Finding]:
    findings: list[Finding] = []
    cues = document.get("cues")
    cues = cues if isinstance(cues, list) else []
    known = {cue.get("cue_id") for cue in cues if isinstance(cue, dict)}
    records = document.get("unsupported_features")
    records = records if isinstance(records, list) else []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        where = f"{location}/unsupported_features/{index}"
        if record.get("cue_id") not in known:
            findings.append(
                _finding(f"{where}/cue_id", "E_CUE_REF", "존재하지 않는 cue를 참조했다")
            )
        needs_extension = record.get("feature_kind") == "other" or record.get("reason_code") == "other"
        identifier = record.get("feature_identifier")
        if needs_extension and not (isinstance(identifier, str) and identifier.startswith("x-")):
            findings.append(
                _finding(
                    f"{where}/feature_identifier",
                    "E_SCHEMA",
                    "feature_kind 또는 reason_code가 other이면 feature_identifier는 x- 접두사여야 한다",
                )
            )
    return findings


def _check_cue_lineage(
    document: Mapping[str, Any],
    location: str,
    direct: Mapping[str, str],
    other: Mapping[str, str],
) -> list[Finding]:
    """cue lineage의 ID·범위·exact text·line 결합 동치와 입력 scalar partition (§4.5)."""

    findings: list[Finding] = []
    cues = document.get("cues")
    cues = cues if isinstance(cues, list) else []
    coverage: dict[str, list[_Range]] = {}
    order = 0

    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            continue
        where = f"{location}/cues/{index}"
        lines = cue.get("lines")
        lines = lines if isinstance(lines, list) else []
        for line_index, line in enumerate(lines):
            _scalar_text(line, f"{where}/lines/{line_index}", findings)

        assembled: dict[int, list[str]] = {}
        for position, fragment in enumerate(cue.get("lineage_fragments") or []):
            if not isinstance(fragment, dict):
                continue
            spot = f"{where}/lineage_fragments/{position}"
            line_index = fragment.get("line_index")
            if not isinstance(line_index, int) or isinstance(line_index, bool) or not 0 <= line_index < len(lines):
                findings.append(
                    _finding(f"{spot}/line_index", "E_LINEAGE", "line_index가 lines 범위 밖이다")
                )
                continue
            bounds = _resolve_input_fragment(fragment, spot, direct, other, findings, field="text")
            if bounds is None:
                continue
            start, end, segment_id = bounds
            assembled.setdefault(line_index, []).append(fragment.get("text") or "")
            coverage.setdefault(segment_id, []).append(
                _Range(start=start, end=end, location=f"{spot}/char_start", order=order,
                       group="visible")
            )
            order += 1

        for line_index, line in enumerate(lines):
            if not isinstance(line, str):
                continue
            joined = "".join(assembled.get(line_index, []))
            if joined != line:
                findings.append(
                    _finding(
                        f"{where}/lines/{line_index}",
                        "E_LINEAGE",
                        "line의 visible lineage fragment 결합이 lines[line_index]와 다르다",
                    )
                )

        for position, gap in enumerate(cue.get("line_break_whitespace") or []):
            if not isinstance(gap, dict):
                continue
            spot = f"{where}/line_break_whitespace/{position}"
            after = gap.get("after_line_index")
            if not isinstance(after, int) or isinstance(after, bool) or not 0 <= after < max(len(lines) - 1, 0):
                findings.append(
                    _finding(
                        f"{spot}/after_line_index",
                        "E_LINEAGE",
                        "after_line_index가 실제 줄 경계를 가리키지 않는다",
                    )
                )
                continue
            moved = gap.get("text")
            if isinstance(moved, str) and any(char not in ALLOWED_LINE_BREAK_SCALARS for char in moved):
                findings.append(
                    _finding(
                        f"{spot}/text",
                        "E_LINEAGE",
                        "line_break_whitespace로 옮길 수 있는 것은 고정 whitespace scalar 집합뿐이다",
                    )
                )
                continue
            bounds = _resolve_input_fragment(gap, spot, direct, other, findings, field="text")
            if bounds is None:
                continue
            start, end, segment_id = bounds
            coverage.setdefault(segment_id, []).append(
                _Range(start=start, end=end, location=f"{spot}/char_start", order=order,
                       group="line_break")
            )
            order += 1

    for segment_id in sorted(direct):
        text = direct[segment_id]
        _check_partition(
            coverage.get(segment_id, []),
            len(text),
            gap_location=f"{location}/cues",
            coverage_code="E_LINEAGE",
            subject=f"입력 segment {segment_id!r}의 cue lineage",
            findings=findings,
        )
    return findings


def _resolve_input_fragment(
    fragment: Mapping[str, Any],
    spot: str,
    direct: Mapping[str, str],
    other: Mapping[str, str],
    findings: list[Finding],
    *,
    field: str,
) -> tuple[int, int, str] | None:
    """lineage fragment의 입력 segment·scalar 범위·exact substring을 확인한다."""

    segment_id = fragment.get("input_segment_id")
    if not isinstance(segment_id, str) or segment_id not in direct:
        if isinstance(segment_id, str) and segment_id in other:
            findings.append(
                _finding(
                    f"{spot}/input_segment_id",
                    "E_TEXT_AXIS",
                    "반대 축 문서의 segment를 직접 입력 lineage로 참조했다",
                )
            )
        else:
            findings.append(
                _finding(
                    f"{spot}/input_segment_id",
                    "E_SOURCE_REF",
                    "직접 입력 문서에 없는 segment를 참조했다",
                )
            )
        return None

    text = direct[segment_id]
    start, end = fragment.get("char_start"), fragment.get("char_end")
    if not isinstance(start, int) or isinstance(start, bool):
        return None
    if not isinstance(end, int) or isinstance(end, bool):
        return None
    if end <= start:
        findings.append(
            _finding(f"{spot}/char_end", "E_OFFSET_RANGE", "빈 범위이거나 역전된 scalar 범위다")
        )
        return None
    if end > len(text):
        findings.append(
            _finding(f"{spot}/char_end", "E_OFFSET_RANGE", "scalar 범위가 입력 text 길이를 넘는다")
        )
        return None
    stored = fragment.get(field)
    if _scalar_text(stored, f"{spot}/{field}", findings) is None and isinstance(stored, str):
        return None
    if stored != text[start:end]:
        findings.append(
            _finding(
                f"{spot}/{field}",
                "E_LINEAGE",
                "lineage fragment text가 해당 scalar 범위의 exact substring과 다르다",
            )
        )
    return start, end, segment_id


# ---------------------------------------------------------------------------
# 최상위 검증
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    findings: tuple[Finding, ...]

    @property
    def valid(self) -> bool:
        return not self.findings

    @property
    def pairs(self) -> tuple[tuple[str, str], ...]:
        """판정 계약 — message가 아니라 (code, location) 쌍이다."""

        return tuple((finding.code, finding.location) for finding in self.findings)


def _check_containers(documents: Mapping[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for key in sorted(documents):
        if key not in DOCUMENT_KEYS:
            findings.append(_finding(key, "E_SCHEMA", "알 수 없는 문서 key다"))
            continue
        value = documents[key]
        if key == "speech_segments":
            if not isinstance(value, list):
                findings.append(_finding(key, "E_SCHEMA", "speech_segments는 배열이어야 한다"))
        elif not isinstance(value, dict):
            findings.append(_finding(key, "E_SCHEMA", f"{key}는 객체여야 한다"))
    return findings


def validate_documents(documents: Mapping[str, Any], schemas: SchemaSet) -> ValidationResult:
    """schema 검사 → 문서별 의미 불변식 → 교차 문서 불변식.

    schema 검사에서 실패한 문서는 의미 검사를 건너뛴다. 구조가 깨진 문서 위에 파생 오류를
    쌓지 않기 위해서다 (기존 TASK-006·TASK-028 validator와 같은 방침).
    """

    container_findings = _check_containers(documents)
    if container_findings:
        return ValidationResult(findings=tuple(sort_findings(container_findings)))

    validator = SchemaValidator(schemas)
    findings: list[Finding] = []
    schema_failed: set[str] = set()

    segments = documents.get("speech_segments") or []
    for index, segment in enumerate(segments):
        location = f"speech_segments/{index}"
        result = validator.validate(segment, DOCUMENT_KEYS["speech_segments"], location)
        if result:
            schema_failed.add("speech_segments")
            findings.extend(result)
    for key in ("transcript", "translated_transcript", "subtitle_document"):
        if key not in documents:
            continue
        result = validator.validate(documents[key], DOCUMENT_KEYS[key], key)
        if result:
            schema_failed.add(key)
            findings.extend(result)

    if "speech_segments" not in schema_failed:
        findings.extend(check_speech_segments(segments))

    transcript = documents.get("transcript")
    translated = documents.get("translated_transcript")
    subtitle = documents.get("subtitle_document")

    transcript_ok = "transcript" in documents and "transcript" not in schema_failed
    translated_ok = "translated_transcript" in documents and "translated_transcript" not in schema_failed
    subtitle_ok = "subtitle_document" in documents and "subtitle_document" not in schema_failed

    if transcript_ok and "speech_segments" not in schema_failed:
        findings.extend(check_transcript(transcript, segments))
    if translated_ok:
        findings.extend(
            check_translated_transcript(translated, transcript if transcript_ok else None)
        )
    if subtitle_ok:
        findings.extend(
            check_subtitle_document(
                subtitle,
                transcript if transcript_ok else None,
                translated if translated_ok else None,
            )
        )

    return ValidationResult(findings=tuple(sort_findings(findings)))


# ---------------------------------------------------------------------------
# fixture runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureOutcome:
    case_id: str
    path: Path
    passed: bool
    mismatches: tuple[str, ...]
    observed: tuple[tuple[str, str], ...]


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = load_strict(path)
    if not isinstance(fixture, dict):
        raise JsonInputError(f"{path.name}: fixture root가 객체가 아니다")
    for key in ("case_id", "title", "expected", "documents"):
        if key not in fixture:
            raise JsonInputError(f"{path.name}: fixture에 {key}가 없다")
    return fixture


def _expected_pairs(expected: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    pairs = []
    for entry in expected.get("findings") or []:
        pairs.append((str(entry.get("code")), str(entry.get("location"))))
    return tuple(sorted(pairs))


def evaluate_fixture(path: Path, schemas: SchemaSet) -> FixtureOutcome:
    fixture = load_fixture(path)
    expected = fixture["expected"]
    result = validate_documents(fixture["documents"], schemas)

    mismatches: list[str] = []
    expected_valid = bool(expected.get("valid"))
    if result.valid != expected_valid:
        mismatches.append(f"valid: 기대 {expected_valid}, 관측 {result.valid}")
    wanted = _expected_pairs(expected)
    observed = tuple(sorted(result.pairs))
    if wanted != observed:
        missing = [pair for pair in wanted if pair not in observed]
        extra = [pair for pair in observed if pair not in wanted]
        if missing:
            mismatches.append("누락: " + ", ".join(f"{code}@{loc}" for code, loc in missing))
        if extra:
            mismatches.append("초과: " + ", ".join(f"{code}@{loc}" for code, loc in extra))

    return FixtureOutcome(
        case_id=str(fixture["case_id"]),
        path=path,
        passed=not mismatches,
        mismatches=tuple(mismatches),
        observed=observed,
    )


def discover_fixtures(directory: Path) -> list[Path]:
    return sorted(directory.glob("k-*.json"))


def run_fixtures(directory: Path, schemas: SchemaSet) -> list[FixtureOutcome]:
    return [evaluate_fixture(path, schemas) for path in discover_fixtures(directory)]


#: fixture 디렉터리에 반드시 있어야 하는 case ID. 조용한 누락을 막는다.
EXPECTED_CASE_IDS = tuple(f"K-{index:02d}" for index in range(1, 58))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m media_clarity.subtitle_contracts",
        description="TASK-029 자막 spine 계약 fixture runner (읽기 전용).",
    )
    parser.add_argument("--fixtures", required=True, type=Path, help="K-* fixture 디렉터리")
    parser.add_argument(
        "--schemas", type=Path, default=DEFAULT_SCHEMA_DIR, help="schema 디렉터리"
    )
    parser.add_argument(
        "--json", action="store_true", help="case별 결과를 JSON으로 출력한다 (mutation 감사용)"
    )
    parser.add_argument(
        "--require-all-cases",
        action="store_true",
        help="EXPECTED_CASE_IDS가 모두 발견됐는지 확인한다",
    )
    args = parser.parse_args(argv)

    try:
        schemas = SchemaSet(args.schemas)
    except (SchemaContractError, JsonInputError) as exc:
        if args.json:
            print(json.dumps({"schema_contract_error": str(exc)}, ensure_ascii=False))
        else:
            print(f"SCHEMA_CONTRACT_ERROR {exc}", file=sys.stderr)
        return 2

    if not args.fixtures.is_dir():
        print(f"FIXTURE_DIR_MISSING {args.fixtures}", file=sys.stderr)
        return 2

    try:
        outcomes = run_fixtures(args.fixtures, schemas)
    except JsonInputError as exc:
        print(f"E_JSON {exc}", file=sys.stderr)
        return 2

    failures = [outcome for outcome in outcomes if not outcome.passed]
    if args.json:
        print(
            json.dumps(
                {
                    "cases": [
                        {
                            "case_id": outcome.case_id,
                            "passed": outcome.passed,
                            "mismatches": list(outcome.mismatches),
                        }
                        for outcome in outcomes
                    ]
                },
                ensure_ascii=False,
            )
        )
    else:
        for outcome in outcomes:
            mark = "PASS" if outcome.passed else "FAIL"
            print(f"{mark} {outcome.case_id} {outcome.path.name}")
            for mismatch in outcome.mismatches:
                print(f"     {mismatch}")
        print(
            f"실행 {len(outcomes)}건 / 기대 {len(EXPECTED_CASE_IDS)}건 / 실패 {len(failures)}건"
        )

    if args.require_all_cases:
        observed = {outcome.case_id for outcome in outcomes}
        missing = [case_id for case_id in EXPECTED_CASE_IDS if case_id not in observed]
        if missing:
            print(f"CASE_MISSING {', '.join(missing)}", file=sys.stderr)
            return 2

    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    raise SystemExit(main())
