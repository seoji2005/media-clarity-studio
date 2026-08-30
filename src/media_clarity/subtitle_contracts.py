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
    COMMON_SCHEMA_FILE,
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
    "REF_CONTEXT_KEY",
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
    "check_artifact_consistency",
    "check_document_ref_identity",
    "check_speech_segments",
    "check_subtitle_document",
    "check_transcript",
    "check_translated_transcript",
    "check_translation_capability_binding",
    "discover_fixtures",
    "dedupe_findings",
    "redact_schema_findings",
    "redact_schema_message",
    "safe_location",
    "speech_timebase",
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


_MISSING = object()


def _declared_segments() -> frozenset[str]:
    """다섯 정본이 **선언한 고정 field 이름**의 전수 집합.

    location 구간을 그대로 남겨도 되는 것은 이 allowlist뿐이다. 모양이 ASCII snake_case라는
    이유만으로는 안전하지 않다 — `patient_name`·`John_Doe`도 같은 모양이다 (REVIEW-025 R-05).
    """

    names: set[str] = set(DOCUMENT_KEYS)
    names.add(REF_CONTEXT_KEY)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    names.update(value)
                if key in ("patternProperties",):
                    continue
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for name in SCHEMA_FILES:
        try:
            walk(load_strict(DEFAULT_SCHEMA_DIR / name))
        except (JsonInputError, OSError):  # pragma: no cover - 정본이 없으면 allowlist만 줄어든다
            continue
    return frozenset(names)


_DECLARED_SEGMENTS: frozenset[str] | None = None


def declared_segments() -> frozenset[str]:
    global _DECLARED_SEGMENTS
    if _DECLARED_SEGMENTS is None:
        _DECLARED_SEGMENTS = _declared_segments()
    return _DECLARED_SEGMENTS


def _step(node: Any, segment: str) -> Any:
    """JSON Pointer 한 구간을 실제 입력에서 따라간다. 못 따라가면 `_MISSING`."""

    if isinstance(node, Mapping):
        return node[segment] if segment in node else _MISSING
    if isinstance(node, list):
        if not segment.isdigit():
            return _MISSING
        index = int(segment)
        return node[index] if 0 <= index < len(node) else _MISSING
    return _MISSING


#: 정본이 **선언한 dynamic key 어휘**를 가진 유일한 자리.
#: `patternProperties`의 language tag subset은 계약이 정한 vocabulary이지 자유 입력이 아니다.
LANGUAGE_OVERRIDES_LOCATION = "subtitle_document/resolved_style/language_overrides"


def _is_language_tag_subset(value: str) -> bool:
    """`^[a-z]{2,8}(-[A-Za-z0-9]{1,8})*$` 부분집합인가 (§4.3의 구조 subset).

    `schema_core`가 쓰는 정규식과 같은 어휘를 표준 라이브러리 문자열 연산으로 확인한다.
    """

    if not value:
        return False
    parts = value.split("-")
    primary = parts[0]
    if not 2 <= len(primary) <= 8 or not all("a" <= character <= "z" for character in primary):
        return False
    return all(
        1 <= len(part) <= 8
        and all(character.isascii() and character.isalnum() for character in part)
        for part in parts[1:]
    )


def _segment_allowed(parent_location: str, key: str) -> bool:
    """이 구간을 location에 그대로 남겨도 되는가.

    남길 수 있는 것은 (a) 정본이 선언한 고정 field 이름과 (b) 정본이 선언한 dynamic key
    어휘뿐이다. 모양이 ASCII snake_case라는 이유만으로는 남기지 않는다 (REVIEW-025 R-05).
    """

    if key in declared_segments():
        return True
    return parent_location == LANGUAGE_OVERRIDES_LOCATION and _is_language_tag_subset(key)


def _match_keys(node: Mapping[str, Any], remainder: str) -> list[str]:
    """남은 location 문자열의 **앞부분과 실제로 일치하는 key** 목록.

    `"a/b"`처럼 key 안에 `/`가 있으면 이어붙인 뒤에는 두 구간처럼 보인다. 그래서 구간 단위로
    자르지 않고, 실제 객체의 key 중 어느 것이 앞부분과 맞는지 본다. 둘 이상 맞으면 alias
    충돌이므로 어느 쪽인지 알 수 없다 (REVIEW-025 R-05).
    """

    return [
        key
        for key in node
        if isinstance(key, str) and (remainder == key or remainder.startswith(key + "/"))
    ]


def safe_location(location: str, root: Any = None) -> str:
    """사용자 제어 key를 location에서 **접는다**. 이어붙인 문자열을 사후 split하지 않는다.

    이전 판은 `/`로 이어붙인 raw location을 다시 split해서 구간 모양만 봤다. 그 시점에는
    dynamic key 경계가 이미 사라져서 다음이 전부 통과했다 (REVIEW-025 R-05).

    - 최상위 key `"transcript/streams"` → `transcript/streams` (실제 노드처럼 보임)
    - `document_refs["transcript/artifact_id"]` → `document_refs/transcript/artifact_id`
    - `language_overrides["a/b"]`가 실제 `a.b` 경로와 같은 location으로 충돌
    - `patient_name`·`John_Doe` 같은 ASCII 사용자 key가 그대로 노출

    지금은 **실제 입력을 따라가며** 구간을 확정한다. 각 단계에서 그 노드의 실제 key 중
    앞부분과 맞는 것을 찾고,

    - 맞는 key가 둘 이상이면(alias 충돌) 거기서 접는다,
    - 맞는 key가 정본이 **선언한 고정 field**가 아니면 거기서 접는다,
    - 아무 key도 맞지 않으면 거기서 접는다.

    `root`가 없으면 입력을 따라갈 수 없으므로 아무것도 접지 않고 그대로 돌려준다. 최종
    정규화는 `validate_documents`가 문서 집합을 들고 한 번에 수행한다.
    """

    if root is None or location == "":
        return location

    kept: list[str] = []
    node: Any = root
    remainder = location
    while remainder:
        if isinstance(node, Mapping):
            matches = _match_keys(node, remainder)
            if len(matches) != 1 or not _segment_allowed("/".join(kept), matches[0]):
                break
            key = matches[0]
            node = node[key]
            kept.append(key)
            remainder = remainder[len(key) + 1:] if len(remainder) > len(key) else ""
            continue
        if isinstance(node, list):
            segment, _, rest = remainder.partition("/")
            if not segment.isdigit() or not 0 <= int(segment) < len(node):
                break
            node = node[int(segment)]
            kept.append(segment)
            remainder = rest
            continue
        break
    return "/".join(kept)


def _finding(location: str, code: str, message: str) -> Finding:
    """location은 여기서 접지 않는다. 문서 집합을 들고 있는 `validate_documents`가 한 번에
    정규화한다 — container 조기 반환 경로도 같은 경로를 지난다 (REVIEW-025 R-05)."""

    return Finding(location=location, code=code, message=message)


#: 검증 대상 숫자는 `int`일 수도 `float`일 수도 있다. 임의 정밀도 `int`를 `float`로
#: 바꾸면 `OverflowError`가 나므로 원래 타입 그대로 다룬다 (REVIEW-025 R-04).
_Num = int | float


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    """finite 숫자인가. **`float()`로 강제 변환하지 않는다.**

    strict JSON loader는 401자리 정수 같은 임의 정밀도 `int`를 정상적으로 받는다.
    `float(10**400)`은 `OverflowError`를 내므로 validator가 finding 대신 crash했다
    (REVIEW-025 R-04). Python `int`는 언제나 finite이므로 변환 없이 판정한다.
    """

    if not _is_number(value):
        return False
    if isinstance(value, int):
        return True
    return math.isfinite(value)


def _as_number(value: Any) -> int | float | None:
    """비교·산술에 쓸 수 있는 finite 숫자면 **원래 타입 그대로** 돌려준다.

    `int`를 `float`로 바꾸지 않는다. Python은 `int`와 `float`를 직접 비교·연산할 수
    있으므로 변환이 필요 없고, 변환하는 순간 임의 정밀도 입력에서 터진다.
    """

    return value if _finite(value) else None


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
    if start < 0:
        findings.append(
            _finding(f"{where}/start_seconds", "E_TIME_RANGE", f"{what} start_seconds가 음수다")
        )
        return False
    if end <= start:
        findings.append(
            _finding(
                f"{where}/end_seconds",
                "E_TIME_RANGE",
                f"{what}는 positive duration 반개구간이어야 한다",
            )
        )
        return False
    return True


def _overlaps(a_start: _Num, a_end: _Num, b_start: _Num, b_end: _Num) -> bool:
    """반개구간 [start, end) 끼리의 실제 겹침."""

    return a_start < b_end and b_start < a_end


def _check_confidence_value(
    value: Any, semantics: str | None, location: str, findings: list[Finding]
) -> None:
    """calibrated_probability만 [0,1]을 강제한다. 나머지는 finite provider-native 값이다."""

    if not _finite(value):
        findings.append(_finding(location, "E_CONFIDENCE", "confidence가 finite 숫자가 아니다"))
        return
    if semantics == "calibrated_probability" and not (0 <= value <= 1):
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


def _check_duplicate_ids(
    entries: Sequence[tuple[Any, str]], findings: list[Finding], *, what: str
) -> set[str]:
    """`(id, location)` 목록의 중복을 **index 구축 전에** 보고한다.

    dict 인덱스는 last-write-wins라 중복 ID가 조용히 lineage를 바꿔치기한다
    (REVIEW-023 B-01). 그래서 인덱스를 만들기 전에 여기서 먼저 거른다.
    """

    seen: set[str] = set()
    for identifier, location in entries:
        if not isinstance(identifier, str):
            continue
        if identifier in seen:
            findings.append(
                _finding(location, "E_SCHEMA", f"{what}가 문서 집합 안에서 중복이다")
            )
        seen.add(identifier)
    return seen


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

    `order`는 **문서에 나타나는 순서**가 아니라 **실제로 소비·렌더링되는 순서**의 정렬
    키다. cue lineage에서는 `(cue index, 줄 위치, 줄 안 위치)`이므로 배열 순서만 맞추고
    `line_index`를 바꿔치기한 문서도 순서 위반으로 잡힌다 (REVIEW-023 B-01).

    `group`은 **같은 배열에서 나온 범위 묶음**이다. covered fragment와 uncovered
    fragment는 문서 안에서 나란히 놓이지 않으므로 순서를 섞어 비교하지 않는다.
    partition 자체(gap·중복)는 group과 무관하게 함께 본다.
    """

    start: int
    end: int
    location: str
    order: tuple[int, ...]
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
    # `subject`는 계약 문구(고정 문자열)만 받는다. 식별자·원문을 message에 넣지 않는다.
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
    ranges: list[tuple[str, str, float, float, list[str], int]] = []

    # 인덱스를 만들기 전에 ID 중복부터 거른다 (REVIEW-023 B-01).
    _check_duplicate_ids(
        [
            (segment.get("segment_id"), f"{location}/{index}/segment_id")
            for index, segment in enumerate(segments)
            if isinstance(segment, dict)
        ],
        findings,
        what="SpeechSegment segment_id",
    )
    timebases = _check_single_timebase(segments, location, findings)
    del timebases

    for index, segment in enumerate(segments):
        where = f"{location}/{index}"
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")

        start, end = segment.get("start_seconds"), segment.get("end_seconds")
        valid_time = _check_half_open(start, end, where, findings, what="segment")

        stream_id = segment.get("stream_id")
        concurrent = segment.get("concurrent_stream_ids")
        if valid_time and isinstance(stream_id, str) and isinstance(concurrent, list):
            ranges.append((segment_id or "", stream_id, start, end, concurrent, index))

        _check_channel_semantics(segment, where, findings)
        _check_speech_confidence(segment, where, findings)
        _scalar_text(segment.get("speaker_label"), f"{where}/speaker_label", findings)
        if segment.get("overlap_kind") == "none" and segment.get("concurrent_stream_ids"):
            findings.append(
                _finding(
                    f"{where}/overlap_kind",
                    "E_STREAM_REF",
                    "overlap_kind=none인 segment는 concurrent stream을 선언하지 않는다",
                )
            )

    findings.extend(_check_concurrent_streams(ranges, location))
    return findings


def _check_single_timebase(
    segments: Sequence[Any], location: str, findings: list[Finding]
) -> str | None:
    """한 실행의 SpeechSegment는 하나의 원본 시간축을 공유한다 (REVIEW-023 B-01).

    첫 segment의 `timebase_ref`를 기준으로 삼고, 다른 값을 쓰는 segment를 거부한다.
    downstream 문서는 이 값에 결박된다.
    """

    baseline: str | None = None
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        timebase = segment.get("timebase_ref")
        if not isinstance(timebase, str):
            continue
        if baseline is None:
            baseline = timebase
        elif timebase != baseline:
            findings.append(
                _finding(
                    f"{location}/{index}/timebase_ref",
                    "E_SOURCE_REF",
                    "같은 실행의 SpeechSegment가 서로 다른 원본 시간축을 쓴다",
                )
            )
    return baseline


def speech_timebase(segments: Sequence[Any]) -> str | None:
    """SpeechSegment 집합이 선언한 원본 시간축. 하류 문서 결박의 기준이다."""

    for segment in segments:
        if isinstance(segment, dict) and isinstance(segment.get("timebase_ref"), str):
            return segment["timebase_ref"]
    return None


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

    # index 구축 **전에** 중복 ID를 거른다. dict는 last-write-wins라 중복이 조용히
    # lineage를 바꿔치기한다 (REVIEW-023 B-01).
    streams = [
        (index, stream)
        for index, stream in enumerate(transcript.get("streams") or [])
        if isinstance(stream, dict)
    ]
    _check_duplicate_ids(
        [
            (stream.get("stream_id"), f"{location}/streams/{index}/stream_id")
            for index, stream in streams
        ],
        findings,
        what="Transcript stream_id",
    )
    _check_duplicate_ids(
        [
            (
                segment.get("segment_id"),
                f"{location}/streams/{index}/segments/{position}/segment_id",
            )
            for index, stream in streams
            for position, segment in enumerate(stream.get("segments") or [])
            if isinstance(segment, dict)
        ],
        findings,
        what="Transcript segment_id",
    )

    #: 첫 등장이 이긴다 — 중복은 위에서 이미 보고했고, 조용한 재결박을 막는다.
    speech_index: dict[str, tuple[float, float, str, str | None]] = {}
    for segment in speech_segments:
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        start, end = segment.get("start_seconds"), segment.get("end_seconds")
        stream_id = segment.get("stream_id")
        if (
            isinstance(segment_id, str)
            and segment_id not in speech_index
            and _finite(start)
            and _finite(end)
            and isinstance(stream_id, str)
        ):
            label = segment.get("speaker_label")
            speech_index[segment_id] = (
                start, end, stream_id, label if isinstance(label, str) else None
            )

    # 원본 시간축 결박 — 하류 문서만 다른 timebase를 쓰는 것을 막는다.
    source_timebase = speech_timebase(speech_segments)
    if source_timebase is not None and transcript.get("timebase_ref") != source_timebase:
        findings.append(
            _finding(
                f"{location}/timebase_ref",
                "E_SOURCE_REF",
                "Transcript의 timebase_ref가 입력 SpeechSegment의 원본 시간축과 다르다",
            )
        )

    for stream_index, stream in streams:
        where = f"{location}/streams/{stream_index}"
        stream_id = stream.get("stream_id")
        _check_speaker_label_pair(stream, where, findings)
        if stream.get("speaker_label_source") == "adapter" and capability.get(
            "supports_diarization"
        ) is not True:
            findings.append(
                _finding(
                    f"{where}/speaker_label_source",
                    "E_CAPABILITY_MISMATCH",
                    "supports_diarization=false인 adapter가 adapter-produced speaker label을 냈다",
                )
            )
        if stream.get("speaker_label_source") == "input":
            # stream 수준 input label도 그 stream의 **실제 입력 label 근거**와 결박한다.
            # 근거는 같은 stream_id를 가진 입력 SpeechSegment의 speaker_label이다.
            evidence = [
                entry[3] for entry in speech_index.values() if entry[2] == stream_id
            ]
            findings.extend(
                _check_input_label_value(
                    stream.get("speaker_label"),
                    {value for value in evidence if value is not None},
                    where,
                    # 한 입력만 label을 갖고 나머지는 없으면 stream 전체의 화자를 그 하나로
                    # 정당화할 수 없다 (REVIEW-025 R-02).
                    unlabeled_evidence=any(value is None for value in evidence),
                )
            )

        for segment_index, segment in enumerate(stream.get("segments") or []):
            if not isinstance(segment, dict):
                continue
            spot = f"{where}/segments/{segment_index}"
            findings.extend(
                _check_transcript_segment(segment, spot, speech_index, capability, stream_id)
            )

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


def _check_input_label_value(
    label: Any, input_labels: set[str], where: str, *, unlabeled_evidence: bool = False
) -> list[Finding]:
    """`speaker_label_source="input"`은 **실제 입력 label 값**과 결박한다 (REVIEW-024 H-02).

    이전 판은 "참조한 입력 중 label이 하나라도 있는가"만 봤다. 그래서 입력이 `SPK-A`인데
    Transcript가 `SPK-B/source=input`이라고 주장해도 통과했다. `input`은 "입력에서 복사했다"는
    뜻이므로 값이 같아야 한다.

    입력 label이 여러 개면 단일 값을 **조용히 고르지 않는다.** 어느 것을 복사했는지 계약이
    정하지 않았으므로 계약 위반으로 보고한다 (임의 선택은 근거 없는 값을 만든다).
    """

    findings: list[Finding] = []
    if not input_labels:
        findings.append(
            _finding(
                f"{where}/speaker_label_source",
                "E_CAPABILITY_MISMATCH",
                "speaker_label_source=input인데 참조한 입력에 speaker_label이 없다",
            )
        )
        return findings
    if unlabeled_evidence:
        # 구간을 덮는 입력 중 label이 없는 것이 있으면 "입력에서 복사했다"가 성립하지 않는다.
        # 옆에 있는 labelled 입력의 값을 빌려 오는 것을 막는다 (REVIEW-025 R-02).
        findings.append(
            _finding(
                f"{where}/speaker_label",
                "E_CAPABILITY_MISMATCH",
                "이 구간을 덮는 입력 중 speaker_label이 없는 것이 있어 input label을 단일 값으로 정할 수 없다",
            )
        )
        return findings
    if len(input_labels) > 1:
        findings.append(
            _finding(
                f"{where}/speaker_label",
                "E_CAPABILITY_MISMATCH",
                "참조한 입력의 speaker_label이 여러 개여서 input label을 단일 값으로 정할 수 없다",
            )
        )
        return findings
    if isinstance(label, str) and label not in input_labels:
        findings.append(
            _finding(
                f"{where}/speaker_label",
                "E_CAPABILITY_MISMATCH",
                "speaker_label_source=input인데 값이 실제 입력 speaker_label과 다르다",
            )
        )
    return findings


def _check_transcript_segment(
    segment: Mapping[str, Any],
    where: str,
    speech_index: Mapping[str, tuple[float, float, str, str | None]],
    capability: Mapping[str, Any],
    stream_id: Any = None,
) -> list[Finding]:
    findings: list[Finding] = []

    text = _scalar_text(segment.get("text"), f"{where}/text", findings)
    _check_speaker_label_pair(segment, where, findings)
    _check_review_state(segment, where, findings)

    start, end = segment.get("start_seconds"), segment.get("end_seconds")
    valid_time = _check_half_open(start, end, where, findings, what="ASR segment")

    # 입력 SpeechSegment lineage — 존재·단일 stream·시간 포함.
    sources = segment.get("source_speech_segment_ids")
    intervals: list[tuple[_Num, _Num]] = []
    input_labels: set[str] = set()
    unlabeled_cover = False
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
            # 이 ASR 구간과 **실제로 겹치는** 입력만 lineage이자 화자 근거다.
            # 겹치지 않는 과거·미래 segment의 label을 빌려 오는 것을 막는다 (REVIEW-025 R-02).
            if valid_time and not _overlaps(start, end, entry[0], entry[1]):
                findings.append(
                    _finding(
                        f"{where}/source_speech_segment_ids/{position}",
                        "E_TIME_RANGE",
                        "참조한 입력 SpeechSegment가 이 ASR segment 구간과 겹치지 않는다",
                    )
                )
                continue
            if entry[3] is None:
                unlabeled_cover = True
            else:
                input_labels.add(entry[3])
        if len(streams) > 1:
            findings.append(
                _finding(
                    f"{where}/source_speech_segment_ids",
                    "E_SOURCE_REF",
                    "서로 다른 stream의 입력을 한 segment lineage로 섞었다",
                )
            )
        elif streams and isinstance(stream_id, str) and stream_id not in streams:
            findings.append(
                _finding(
                    f"{where}/source_speech_segment_ids",
                    "E_STREAM_REF",
                    "ASR segment의 stream이 참조한 입력 SpeechSegment의 stream과 다르다",
                )
            )
        if valid_time and intervals and len(intervals) == len(sources):
            findings.extend(_check_within_union(start, end, intervals, where))

    # speaker evidence 결박 — adapter는 diarization 능력, input은 실제 입력 label이 근거다.
    label_source = segment.get("speaker_label_source")
    if label_source == "adapter" and capability.get("supports_diarization") is not True:
        findings.append(
            _finding(
                f"{where}/speaker_label_source",
                "E_CAPABILITY_MISMATCH",
                "supports_diarization=false인 adapter가 adapter-produced speaker label을 냈다",
            )
        )
    if label_source == "input":
        findings.extend(
            _check_input_label_value(
                segment.get("speaker_label"),
                input_labels,
                where,
                unlabeled_evidence=unlabeled_cover,
            )
        )

    findings.extend(_check_tokens(segment, where, valid_time, capability))
    findings.extend(_check_segment_confidence(segment, where, capability))
    findings.extend(_check_alternatives(segment, where, capability))
    findings.extend(_check_language_spans(segment, where, text, capability))
    return findings


def _check_within_union(
    start: _Num, end: _Num, intervals: Sequence[tuple[_Num, _Num]], where: str
) -> list[Finding]:
    """ASR segment 구간 **전체**가 입력 구간 합집합에 빈틈 없이 들어가는지 (§4.2 R2).

    양 끝점만 보면 `[0,2)`·`[3,4)` 입력에 대해 `[0,3.5)` 같은 구간이 통과한다 — 중간
    `[2,3)`은 입력에 없는데도 ASR 증거 구간으로 주장하게 된다 (REVIEW-023 B-01).
    그래서 끝점이 아니라 `start`를 포함하는 **하나의 연속 구간**이 `end`까지 덮는지 본다.
    """

    merged: list[list[float]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])

    findings: list[Finding] = []
    holder = next((span for span in merged if span[0] <= start <= span[1]), None)
    if holder is None:
        findings.append(
            _finding(
                f"{where}/start_seconds",
                "E_TIME_RANGE",
                "ASR segment 시작이 참조한 입력 SpeechSegment 범위의 합집합 밖이다",
            )
        )
        return findings
    if end > holder[1]:
        findings.append(
            _finding(
                f"{where}/end_seconds",
                "E_TIME_RANGE",
                "ASR segment 구간이 입력 SpeechSegment 합집합의 연속 구간 안에 "
                "빈틈 없이 들어가지 않는다",
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
    previous: tuple[_Num, _Num] | None = None
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
                if end < start:
                    findings.append(
                        _finding(f"{spot}/end_seconds", "E_TIME_RANGE", "token 시간이 역전됐다")
                    )
                if valid_time:
                    lower, upper = segment["start_seconds"], segment["end_seconds"]
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
        # 파생값은 근거가 있어야 한다. spans가 아예 없으면 dominant_language도 없다
        # (REVIEW-023 B-02). 빈 배열은 schema의 minItems 1이 먼저 거른다.
        if has_dominant and capability.get("supports_language_id") is True:
            findings.append(
                _finding(
                    f"{where}/dominant_language",
                    "E_LANGUAGE_GAP_REVIEW",
                    "language_spans 없이 dominant_language를 파생할 수 없다",
                )
            )
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


def _check_capability_implications(
    capability: Mapping[str, Any], location: str
) -> list[Finding]:
    """capability **내부** 함의. 결과 필드를 보기 전에 선언 자체가 모순이면 거부한다.

    `supports_language_id=false`인 adapter가 intra-sentential LID를 지원한다고 말하거나
    LID confidence semantics를 주장하는 것은 실행 결과와 무관하게 이미 모순이다
    (REVIEW-024 H-03). 이전 판은 결과 필드가 없으면 이 모순을 통과시켰다.
    """

    findings: list[Finding] = []
    language_id = capability.get("supports_language_id") is True

    if capability.get("supports_intra_sentential_lid") is True and not language_id:
        findings.append(
            _finding(
                f"{location}/supports_intra_sentential_lid",
                "E_CAPABILITY_MISMATCH",
                "supports_language_id=false인 adapter가 intra-sentential LID를 지원한다고 보고했다",
            )
        )
    if capability.get("language_confidence_semantics") not in (None, "none") and not language_id:
        findings.append(
            _finding(
                f"{location}/language_confidence_semantics",
                "E_CAPABILITY_MISMATCH",
                "supports_language_id=false인 adapter가 language confidence semantics를 주장했다",
            )
        )
    if capability.get("supports_nbest") is not True and capability.get(
        "nbest_score_semantics"
    ) not in (None, "none"):
        findings.append(
            _finding(
                f"{location}/nbest_score_semantics",
                "E_CAPABILITY_MISMATCH",
                "supports_nbest=false이면 nbest_score_semantics는 none이어야 한다",
            )
        )
    return findings


def _check_empty_supported_list(
    capability: Mapping[str, Any], location: str, field: str
) -> list[Finding]:
    """빈 지원 언어 목록의 의미를 계약대로 고정한다 (§4.3).

    §4.3은 "알 수 없으면 빈 배열과 **명시적 limitation**"이라고 정했다. 빈 배열만 두면
    "모든 언어 지원"인지 "미상"인지 "미지원"인지 읽는 쪽이 고를 수 있게 된다.
    빈 배열은 **미상**이며 그 사실을 `limitations`에 적어야 한다 (REVIEW-024 H-03).
    """

    value = capability.get(field)
    if not isinstance(value, list) or value:
        return []
    limitations = capability.get("limitations")
    if isinstance(limitations, list) and limitations:
        return []
    return [
        _finding(
            f"{location}/{field}",
            "E_CAPABILITY_MISMATCH",
            "빈 지원 언어 목록은 '미상'이며 명시적 limitation이 함께 있어야 한다",
        )
    ]


def _transcript_languages(transcript: Mapping[str, Any]) -> set[str]:
    """Transcript가 **실제로 낸** 언어 증거. `und`는 명시적 미상이라 제외한다."""

    languages: set[str] = set()
    for stream in transcript.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        for segment in stream.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            dominant = segment.get("dominant_language")
            if isinstance(dominant, str):
                languages.add(dominant)
            for span in segment.get("language_spans") or []:
                if isinstance(span, dict) and isinstance(span.get("language"), str):
                    languages.add(span["language"])
    return {language for language in languages if language != UNDETERMINED_LANGUAGE}


def _check_declared_languages(
    supported: Any, emitted: set[str], location: str, *, subject: str
) -> list[Finding]:
    """실제 산출 언어가 선언한 지원 언어 밖이면 거부한다 (REVIEW-024 H-03).

    빈 목록은 `_check_empty_supported_list`가 다루는 '미상'이므로 여기서는 판정하지 않는다.
    """

    if not isinstance(supported, list) or not supported:
        return []
    unsupported = sorted(emitted - {tag for tag in supported if isinstance(tag, str)})
    if not unsupported:
        return []
    return [
        _finding(
            location,
            "E_CAPABILITY_MISMATCH",
            f"{subject} 결과에 선언한 지원 언어 밖의 언어가 있다",
        )
    ]


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
    findings.extend(
        _check_capability_provenance(
            capability, transcript.get("provenance"), capability_location
        )
    )
    findings.extend(_check_capability_implications(capability, capability_location))
    findings.extend(
        _check_empty_supported_list(
            capability, capability_location, "supported_languages"
        )
    )
    findings.extend(
        _check_declared_languages(
            capability.get("supported_languages"),
            _transcript_languages(transcript),
            f"{capability_location}/supported_languages",
            subject="ASR",
        )
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
        # stream-level label도 adapter가 낸 것이면 같은 증거로 센다 (REVIEW-023 B-02).
        "speaker_diarization": any(
            segment.node.get("speaker_label_source") == "adapter" for segment in segments
        )
        or any(
            isinstance(stream, dict) and stream.get("speaker_label_source") == "adapter"
            for stream in (transcript.get("streams") or [])
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


def _check_capability_provenance(
    capability: Mapping[str, Any], provenance: Any, capability_location: str
) -> list[Finding]:
    """capability snapshot은 **그 실행을 낸 adapter의 것**이어야 한다 (REVIEW-023 B-02).

    snapshot과 provenance의 adapter identity가 어긋나면 다른 adapter의 능력으로 결과를
    정당화하게 된다.
    """

    findings: list[Finding] = []
    if not isinstance(provenance, dict):
        return findings
    for field in ("adapter_id", "adapter_version"):
        if field not in capability or field not in provenance:
            continue
        if capability[field] != provenance[field]:
            findings.append(
                _finding(
                    f"{capability_location}/{field}",
                    "E_CAPABILITY_MISMATCH",
                    f"capability snapshot의 {field}가 산출물 provenance와 다르다",
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

    findings.extend(
        _check_document_ref_shape(
            document.get("source_transcript"), f"{location}/source_transcript"
        )
    )
    findings.extend(check_translation_capability_binding(document, location, transcript))

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

    # index 구축 **전에** 번역 stream/segment ID 중복을 거른다 (REVIEW-023 B-01).
    translated_streams = [
        (index, stream)
        for index, stream in enumerate(document.get("streams") or [])
        if isinstance(stream, dict)
    ]
    _check_duplicate_ids(
        [
            (stream.get("stream_id"), f"{location}/streams/{index}/stream_id")
            for index, stream in translated_streams
        ],
        findings,
        what="TranslatedTranscript stream_id",
    )
    _check_duplicate_ids(
        [
            (
                segment.get("segment_id"),
                f"{location}/streams/{index}/segments/{position}/segment_id",
            )
            for index, stream in translated_streams
            for position, segment in enumerate(stream.get("segments") or [])
            if isinstance(segment, dict)
        ],
        findings,
        what="TranslatedTranscript segment_id",
    )

    source_segments = _transcript_segments(transcript, "transcript")
    #: 첫 등장이 이긴다 — 중복은 Transcript 검사가 이미 보고했다.
    source_index: dict[str, _TranscriptSegment] = {}
    source_order: dict[str, int] = {}
    for position, segment in enumerate(source_segments):
        if segment.segment_id and segment.segment_id not in source_index:
            source_index[segment.segment_id] = segment
            source_order[segment.segment_id] = position
    source_streams = {segment.stream_id for segment in source_segments}

    for stream_index, stream in translated_streams:
        if stream.get("stream_id") not in source_streams:
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

        previous_key: tuple[int, int] | None = None
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
            if segment.stream_id and source.stream_id and segment.stream_id != source.stream_id:
                findings.append(
                    _finding(
                        f"{spot}/source_segment_id",
                        "E_STREAM_REF",
                        "번역 segment의 stream이 참조한 원문 segment의 stream과 다르다",
                    )
                )
            bounds = _check_fragment_range(fragment, source.text, spot, findings)
            if bounds is None:
                continue
            start, end = bounds
            # 원문 순서 보존 — 같은 source 안에서는 offset, 여러 source를 참조하는
            # merged에서는 **원문 Transcript의 segment 순서**를 지켜야 한다 (REVIEW-023 B-01).
            current_key = (source_order.get(source_id, 0), end)
            if previous_key is not None and (
                current_key[0] < previous_key[0]
                or (current_key[0] == previous_key[0] and start < previous_key[1])
            ):
                findings.append(
                    _finding(
                        f"{spot}/char_start",
                        "E_OFFSET_ORDER",
                        "source fragment가 원문 순서·비중첩이 아니다",
                    )
                )
            previous_key = current_key
            resolved.append((start, end, source_id, spot))
            coverage.setdefault(source_id, []).append(
                _Range(start=start, end=end, location=f"{spot}/char_start",
                       order=(order_counter,), group="covered")
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
            _Range(start=start, end=end, location=f"{spot}/char_start", order=(order,),
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
    for segment_id in sorted(source_index):
        source = source_index[segment_id]
        if source.text is None:
            continue
        # gap의 위치는 **덮이지 않은 원문 segment 자신**이다. 식별자를 message에 넣지
        # 않고도 어느 segment인지 가리킨다 (REVIEW-023 B-02).
        _check_partition(
            coverage.get(segment_id, []),
            len(source.text),
            gap_location=f"{source.location}/text",
            coverage_code="E_SOURCE_COVERAGE",
            subject="원문 segment의 번역 coverage",
            findings=findings,
        )
    return findings


def _language_spans_by_segment(
    transcript: Mapping[str, Any]
) -> dict[str, list[Mapping[str, Any]]]:
    spans: dict[str, list[Mapping[str, Any]]] = {}
    for stream in transcript.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        for segment in stream.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            segment_id = segment.get("segment_id")
            if not isinstance(segment_id, str) or segment_id in spans:
                continue
            spans[segment_id] = [
                span for span in (segment.get("language_spans") or []) if isinstance(span, dict)
            ]
    return spans


def _fragment_language_evidence(
    fragment: Mapping[str, Any], spans: Sequence[Mapping[str, Any]]
) -> tuple[set[str], bool]:
    """한 source fragment **범위 안에** 실제로 들어 있는 언어와 intra-sentential 전환.

    전체 Transcript가 아니라 **그 번역 단위가 실제로 받은 범위**만 본다 (REVIEW-025 R-03).
    """

    start, end = fragment.get("char_start"), fragment.get("char_end")
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool):
        return set(), False
    languages: set[str] = set()
    switched = False
    for span in spans:
        span_start, span_end = span.get("char_start"), span.get("char_end")
        if not isinstance(span_start, int) or not isinstance(span_end, int):
            continue
        if not _overlaps(start, end, span_start, span_end):
            continue
        language = span.get("language")
        if isinstance(language, str) and language != UNDETERMINED_LANGUAGE:
            languages.add(language)
        # 전환 경계가 이 fragment **안쪽**에 있으면 한 번의 입력에 전환이 들어 있다.
        if span.get("switch_kind") == "intra_sentential" and start < span_start < end:
            switched = True
    return languages, switched


def _check_code_switching_input(
    document: Mapping[str, Any],
    transcript: Mapping[str, Any],
    capability: Mapping[str, Any],
    capability_location: str,
    location: str,
) -> list[Finding]:
    """한 번의 번역 입력 단위가 code-switching을 담고 있으면 그 능력을 요구한다.

    이전 판은 `supports_code_switching_input`을 실제 입력과 결박하지 않아, JA/EN 문장 내
    전환이 있는 문자열 전체를 한 단위로 번역하면서 `false`라고 보고해도 통과했다
    (REVIEW-025 R-03).

    **언어별로 분할 호출한 뒤 합성한 경우**는 여기서 추론하지 않는다. 그 사실을 표현할
    provenance/processing 계약이 아직 없으므로 §16.7의 오너 결정 항목으로 남긴다.
    """

    spans_by_segment = _language_spans_by_segment(transcript)
    for segment in _translation_segments(document, location):
        languages: set[str] = set()
        switched = False
        for fragment in segment.node.get("source_fragments") or []:
            if not isinstance(fragment, dict):
                continue
            spans = spans_by_segment.get(fragment.get("source_segment_id"))
            if not spans:
                continue
            fragment_languages, fragment_switch = _fragment_language_evidence(fragment, spans)
            languages |= fragment_languages
            switched = switched or fragment_switch
        if (len(languages) > 1 or switched) and capability.get(
            "supports_code_switching_input"
        ) is not True:
            return [
                _finding(
                    f"{capability_location}/supports_code_switching_input",
                    "E_CAPABILITY_MISMATCH",
                    "한 번역 입력 단위가 여러 언어 또는 문장 내 전환을 담고 있는데 "
                    "supports_code_switching_input=false다",
                )
            ]
    return []


def check_translation_capability_binding(
    document: Mapping[str, Any],
    location: str = "translated_transcript",
    transcript: Mapping[str, Any] | None = None,
) -> list[Finding]:
    """TranslationCapabilityReport ↔ feature_status ↔ 결과 필드 결박 (§4.4).

    `transcript`를 주면 **실제 번역한 원문 언어**를 선언한 지원 언어와 대조한다.
    """

    findings: list[Finding] = []
    capability = document.get("capability_report")
    if not isinstance(capability, dict):
        return findings
    capability_location = f"{location}/capability_report"

    for key in ("supported_source_languages", "supported_target_languages"):
        _check_language_tags(capability.get(key), f"{capability_location}/{key}", findings)
        findings.extend(_check_empty_supported_list(capability, capability_location, key))
    findings.extend(
        _check_capability_provenance(capability, document.get("provenance"), capability_location)
    )
    if transcript is not None:
        findings.extend(
            _check_declared_languages(
                capability.get("supported_source_languages"),
                _transcript_languages(transcript),
                f"{capability_location}/supported_source_languages",
                subject="번역 입력",
            )
        )
        findings.extend(
            _check_code_switching_input(
                document, transcript, capability, capability_location, location
            )
        )

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


# ---------------------------------------------------------------------------
# ArtifactRef 계보 결박 (REVIEW-024 H-01)
# ---------------------------------------------------------------------------

#: 이 계약의 상류 입력(Transcript·TranslatedTranscript)은 전부 JSON 문서다.
#: `kind=video`처럼 문서가 아닌 artifact를 "입력 transcript"로 가리키는 것은 계보 위반이다.
DOCUMENT_REF_KIND = "text"
DOCUMENT_REF_MEDIA_TYPE = "application/json"

#: 검증 입력 집합에 함께 넣는 **문서 자신의 ArtifactRef**.
#:
#: 문서 안에 self ArtifactRef를 둘 수는 없다. `content_hash`는 그 문서 바이트의 해시라서
#: 문서 안에 적으면 순환이 된다. 그래서 "이 문서가 실제로 어떤 artifact인가"는 문서가 아니라
#: **검증 컨텍스트**로 받는다.
#:
#: **선택이 아니다.** 계보 identity를 검사해야 하는 문서 조합(번역·자막)에서는 필수이며,
#: 없거나 불완전하면 조용히 건너뛰지 않고 `E_SOURCE_REF`로 거부한다 (REVIEW-025 R-01).
REF_CONTEXT_KEY = "document_refs"

#: 컨텍스트가 담을 수 있는 role. 다른 문서 종류의 self ref는 이 계약에서 쓰이지 않는다.
REF_CONTEXT_ROLES = ("transcript", "translated_transcript")

#: **identity** — 이 두 field가 "같은 artifact인가"를 정한다 (ARCHITECTURE §2.1).
ARTIFACT_IDENTITY_FIELDS = ("artifact_id", "content_hash")

#: 같은 `artifact_id`를 가리키는 모든 ref가 **반드시 일치해야 하는** immutable metadata.
#: 바이트가 정해지면 함께 정해지는 값들이다. 하나라도 어긋나면 같은 ID가 서로 다른
#: artifact를 가리키는 것이고, 그 순간 `artifact_id` 유일성(§2.1)이 깨진다.
ARTIFACT_IMMUTABLE_FIELDS = (
    "schema_version",
    "content_hash",
    "kind",
    "media_type",
    "byte_size",
    "is_estimate",
)

#: **비교하지 않는 field.** 캐시 재사용·외부 입력에서 같은 artifact가 다른 값을 가질 수
#: 있는지 정한 계약이 아직 없다. 임의로 정하지 않고 오너 결정으로 남긴다
#: (TASK-029 §17.7, REVIEW-025 R-01 8번).
ARTIFACT_UNCOMPARED_FIELDS = ("uri", "produced_by", "created_at", "parent_refs", "timebase_ref")


def _ref_identity(ref: Any) -> tuple[str, str] | None:
    if not isinstance(ref, Mapping):
        return None
    artifact_id, content_hash = ref.get("artifact_id"), ref.get("content_hash")
    if isinstance(artifact_id, str) and isinstance(content_hash, str):
        return (artifact_id, content_hash)
    return None


def _check_document_ref_shape(ref: Any, location: str) -> list[Finding]:
    """상류 문서 ArtifactRef가 실제로 **문서 artifact**를 가리키는지."""

    if not isinstance(ref, Mapping):
        return []
    findings: list[Finding] = []
    if ref.get("kind") != DOCUMENT_REF_KIND:
        findings.append(
            _finding(
                f"{location}/kind",
                "E_SOURCE_REF",
                f"상류 문서 ArtifactRef의 kind는 {DOCUMENT_REF_KIND!r}여야 한다",
            )
        )
    media_type = ref.get("media_type")
    essence = (
        media_type.split(";")[0].strip().lower() if isinstance(media_type, str) else None
    )
    if essence != DOCUMENT_REF_MEDIA_TYPE:
        findings.append(
            _finding(
                f"{location}/media_type",
                "E_SOURCE_REF",
                f"상류 문서 ArtifactRef의 media_type은 {DOCUMENT_REF_MEDIA_TYPE!r}여야 한다",
            )
        )
    return findings


def required_ref_roles(documents: Mapping[str, Any]) -> set[str]:
    """이 문서 조합에서 **반드시 있어야 하는** 컨텍스트 role.

    번역·자막 문서를 검증하려면 "이 Transcript가 어떤 artifact인가"를 알아야 한다.
    모르면 계보 identity를 확인할 방법이 없고, 확인하지 못한 것을 통과로 보고할 수 없다
    (REVIEW-025 R-01).
    """

    roles: set[str] = set()
    subtitle = documents.get("subtitle_document")
    if isinstance(documents.get("translated_transcript"), Mapping):
        roles.add("transcript")
    if isinstance(subtitle, Mapping):
        if subtitle.get("text_axis") == "target":
            roles.update(("transcript", "translated_transcript"))
        else:
            roles.add("transcript")
    return roles


def check_document_ref_identity(
    documents: Mapping[str, Any], refs: Mapping[str, Any]
) -> list[Finding]:
    """직접 입력 ref가 **실제로 제공된 문서**를 가리키는지 (REVIEW-024 H-01 3~5).

    컨텍스트가 없거나 필요한 role이 빠졌으면 조용히 건너뛰지 않고 그 사실 자체를
    `E_SOURCE_REF`로 보고한다. "검증하지 못했다"를 `VALID`로 돌려주지 않는다
    (REVIEW-025 R-01). 위치는 언제나 그 검사가 붙는 실제 문서 field다.
    """

    findings: list[Finding] = []
    transcript_ref = _ref_identity(refs.get("transcript"))
    translated_ref = _ref_identity(refs.get("translated_transcript"))
    translated = documents.get("translated_transcript")
    subtitle = documents.get("subtitle_document")
    axis = subtitle.get("text_axis") if isinstance(subtitle, Mapping) else None

    # 어떤 문서 field가 어떤 컨텍스트 role을 필요로 하는지 **한 곳에** 모은다.
    requirements: list[tuple[str, str]] = []
    if isinstance(translated, Mapping):
        requirements.append(("transcript", "translated_transcript/source_transcript"))
    if isinstance(subtitle, Mapping):
        requirements.append(
            (
                "translated_transcript" if axis == "target" else "transcript",
                "subtitle_document/input_document_ref",
            )
        )
        if axis == "target" and "source_transcript_ref" in subtitle:
            requirements.append(("transcript", "subtitle_document/source_transcript_ref"))

    missing = "검증 컨텍스트(document_refs)에 필요한 문서 identity가 없어 계보를 확인할 수 없다"
    absent = [
        (role, location)
        for role, location in requirements
        if _ref_identity(refs.get(role)) is None
    ]
    for _role, location in absent:
        findings.append(_finding(location, "E_SOURCE_REF", missing))

    if isinstance(translated, Mapping) and transcript_ref is not None:
        if _ref_identity(translated.get("source_transcript")) != transcript_ref:
            findings.append(
                _finding(
                    "translated_transcript/source_transcript",
                    "E_SOURCE_REF",
                    "번역 문서의 source_transcript가 실제 검증 대상 Transcript를 가리키지 않는다",
                )
            )

    if isinstance(subtitle, Mapping):
        expected = translated_ref if axis == "target" else transcript_ref
        if expected is not None:
            if _ref_identity(subtitle.get("input_document_ref")) != expected:
                findings.append(
                    _finding(
                        "subtitle_document/input_document_ref",
                        "E_SOURCE_REF",
                        "자막 문서의 input_document_ref가 실제 직접 입력 문서를 가리키지 않는다",
                    )
                )
        if (
            axis == "target"
            and "source_transcript_ref" in subtitle
            and transcript_ref is not None
            and _ref_identity(subtitle.get("source_transcript_ref")) != transcript_ref
        ):
            findings.append(
                _finding(
                    "subtitle_document/source_transcript_ref",
                    "E_SOURCE_REF",
                    "자막 문서의 source_transcript_ref가 실제 검증 대상 Transcript를 가리키지 않는다",
                )
            )

    # 서로 다른 문서가 같은 artifact로 붕괴하면 계보가 무너진다 (REVIEW-025 R-01 7번).
    if (
        transcript_ref is not None
        and translated_ref is not None
        and transcript_ref == translated_ref
    ):
        findings.append(
            _finding(
                f"{REF_CONTEXT_KEY}/translated_transcript",
                "E_SOURCE_REF",
                "Transcript와 TranslatedTranscript가 같은 artifact identity로 붕괴했다",
            )
        )
    return findings


def _collect_artifact_refs(
    node: Any, location: str, found: list[tuple[str, Mapping[str, Any]]]
) -> None:
    """문서 집합 어디에 있든 ArtifactRef처럼 생긴 객체를 위치와 함께 모은다."""

    if isinstance(node, Mapping):
        if all(field in node for field in ARTIFACT_IDENTITY_FIELDS) and "kind" in node:
            found.append((location, node))
        for key, value in node.items():
            _collect_artifact_refs(value, f"{location}/{key}" if location else str(key), found)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _collect_artifact_refs(item, f"{location}/{index}", found)


def check_artifact_consistency(documents: Mapping[str, Any]) -> list[Finding]:
    """같은 `artifact_id`는 같은 artifact여야 한다 (ARCHITECTURE §2.1).

    `artifact_id`는 프로젝트 안에서 고유하므로 같은 ID를 쓰는 모든 ref는 immutable
    metadata가 일치해야 한다. 같은 ID·같은 hash인데 `byte_size`가 다르면 둘 중 하나는
    거짓이다 (REVIEW-025 R-01 6번).

    `uri`·`produced_by`·`created_at`·`parent_refs`·`timebase_ref`는 **비교하지 않는다.**
    캐시 재사용에서 같은 artifact가 다른 값을 가질 수 있는지 정한 계약이 없다
    (§17.7 오너 결정).
    """

    collected: list[tuple[str, Mapping[str, Any]]] = []
    _collect_artifact_refs(documents, "", collected)

    findings: list[Finding] = []
    first: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for location, ref in collected:
        artifact_id = ref.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        if artifact_id not in first:
            first[artifact_id] = (location, ref)
            continue
        _, original = first[artifact_id]
        for field in ARTIFACT_IMMUTABLE_FIELDS:
            if ref.get(field) != original.get(field):
                findings.append(
                    _finding(
                        f"{location}/{field}",
                        "E_SOURCE_REF",
                        "같은 artifact_id를 가리키는 ArtifactRef의 immutable metadata가 다르다",
                    )
                )
    return findings


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
    findings.extend(
        _check_document_ref_shape(
            document.get("input_document_ref"), f"{location}/input_document_ref"
        )
    )
    findings.extend(
        _check_document_ref_shape(
            document.get("source_transcript_ref"), f"{location}/source_transcript_ref"
        )
    )
    # target 축 자막의 원본 Transcript ref는 번역 문서가 실제로 입력받은 것과 같아야 한다.
    # 문서 집합 안에서 확인 가능한 동일성이므로 컨텍스트 없이도 강제한다.
    if axis == "target" and isinstance(translated, Mapping) and "source_transcript_ref" in document:
        if _ref_identity(document.get("source_transcript_ref")) != _ref_identity(
            translated.get("source_transcript")
        ):
            findings.append(
                _finding(
                    f"{location}/source_transcript_ref",
                    "E_SOURCE_REF",
                    "자막 문서의 source_transcript_ref가 번역 문서의 source_transcript와 다르다",
                )
            )
    findings.extend(_check_resolved_style(document, location))
    findings.extend(_check_cue_times(document, location))
    findings.extend(_check_unsupported_features(document, location))

    # index 구축 **전에** cue ID 중복을 거른다 (REVIEW-023 B-01).
    _check_duplicate_ids(
        [
            (cue.get("cue_id"), f"{location}/cues/{index}/cue_id")
            for index, cue in enumerate(document.get("cues") or [])
            if isinstance(cue, dict)
        ],
        findings,
        what="SubtitleDocument cue_id",
    )

    expected_timebase = _input_timebase(axis, transcript, translated)
    if expected_timebase is not None and document.get("timebase_ref") != expected_timebase:
        findings.append(
            _finding(
                f"{location}/timebase_ref",
                "E_SOURCE_REF",
                "자막 문서의 timebase_ref가 직접 입력 문서의 시간축과 다르다",
            )
        )

    direct, other = _axis_indexes(axis, transcript, translated)
    if direct is None:
        return findings
    findings.extend(_check_cue_lineage(document, location, direct, other))
    return findings


@dataclass(frozen=True)
class _InputSegment:
    """자막이 직접 재분할하는 입력 segment 하나."""

    text: str
    stream_id: str
    location: str


def _axis_indexes(
    axis: Any,
    transcript: Mapping[str, Any] | None,
    translated: Mapping[str, Any] | None,
) -> tuple[dict[str, _InputSegment] | None, dict[str, _InputSegment]]:
    """(직접 입력 segment_id -> 입력, 반대 축 segment_id -> 입력).

    **첫 등장이 이긴다.** 중복 ID는 각 문서의 uniqueness 검사가 이미 보고했고, 여기서
    last-write-wins로 lineage가 조용히 다른 segment에 결박되면 안 된다 (REVIEW-023 B-01).
    """

    source_map: dict[str, _InputSegment] = {}
    if isinstance(transcript, dict):
        for segment in _transcript_segments(transcript, "transcript"):
            if segment.segment_id and segment.text is not None:
                source_map.setdefault(
                    segment.segment_id,
                    _InputSegment(segment.text, segment.stream_id, f"{segment.location}/text"),
                )
    target_map: dict[str, _InputSegment] = {}
    if isinstance(translated, dict):
        for segment in _translation_segments(translated, "translated_transcript"):
            if segment.segment_id and segment.target_text is not None:
                target_map.setdefault(
                    segment.segment_id,
                    _InputSegment(
                        segment.target_text, segment.stream_id, f"{segment.location}/target_text"
                    ),
                )

    if axis == "source":
        return (source_map if isinstance(transcript, dict) else None), target_map
    if axis == "target":
        return (target_map if isinstance(translated, dict) else None), source_map
    return None, {}


def _input_timebase(
    axis: Any, transcript: Mapping[str, Any] | None, translated: Mapping[str, Any] | None
) -> Any:
    """자막이 결박돼야 할 직접 입력 문서의 시간축."""

    if axis == "source" and isinstance(transcript, dict):
        return transcript.get("timebase_ref")
    if axis == "target" and isinstance(translated, dict):
        return translated.get("timebase_ref")
    return None


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
        if not (_finite(low) and _finite(high) and high <= low):
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
        usable.append((index, cue_id, stream_id, start, end, concurrent))
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
    direct: Mapping[str, _InputSegment],
    other: Mapping[str, _InputSegment],
) -> list[Finding]:
    """cue lineage의 ID·범위·exact text·line 결합 동치와 입력 scalar partition (§4.5).

    순서 검사는 **fragment 배열 순서가 아니라 실제 렌더링 순서**로 한다. 렌더링 순서는
    `(cue 순서, 줄 위치, 줄 안 위치)`이며, 줄 사이의 `line_break_whitespace`가 그 두 줄
    사이에 놓인다. 배열만 그대로 두고 `line_index`를 바꿔 줄을 뒤집은 문서도 여기서
    잡힌다 (REVIEW-023 B-01).
    """

    findings: list[Finding] = []
    cues = document.get("cues")
    cues = cues if isinstance(cues, list) else []
    coverage: dict[str, list[_Range]] = {}

    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            continue
        where = f"{location}/cues/{index}"
        lines = cue.get("lines")
        lines = lines if isinstance(lines, list) else []
        for line_index, line in enumerate(lines):
            _scalar_text(line, f"{where}/lines/{line_index}", findings)

        assembled: dict[int, list[str]] = {}
        cue_stream = cue.get("stream_id")
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
            bounds = _resolve_input_fragment(
                fragment, spot, direct, other, findings, field="text", cue_stream=cue_stream
            )
            if bounds is None:
                continue
            start, end, segment_id = bounds
            slot = assembled.setdefault(line_index, [])
            slot.append(fragment.get("text") or "")
            coverage.setdefault(segment_id, []).append(
                _Range(
                    start=start,
                    end=end,
                    location=f"{spot}/char_start",
                    # 렌더링 순서: 줄은 2*line_index, 줄 사이 whitespace는 2*line_index+1.
                    order=(index, 2 * line_index, len(slot) - 1),
                    group="rendered",
                )
            )

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
            bounds = _resolve_input_fragment(
                gap, spot, direct, other, findings, field="text", cue_stream=cue_stream
            )
            if bounds is None:
                continue
            start, end, segment_id = bounds
            coverage.setdefault(segment_id, []).append(
                _Range(
                    start=start,
                    end=end,
                    location=f"{spot}/char_start",
                    order=(index, 2 * after + 1, position),
                    group="rendered",
                )
            )

    for segment_id in sorted(direct):
        entry = direct[segment_id]
        # gap의 위치는 **덮이지 않은 입력 segment 자신**이다 (REVIEW-023 B-02).
        _check_partition(
            coverage.get(segment_id, []),
            len(entry.text),
            gap_location=entry.location,
            coverage_code="E_LINEAGE",
            subject="입력 segment의 cue lineage",
            findings=findings,
        )
    return findings


def _resolve_input_fragment(
    fragment: Mapping[str, Any],
    spot: str,
    direct: Mapping[str, _InputSegment],
    other: Mapping[str, _InputSegment],
    findings: list[Finding],
    *,
    field: str,
    cue_stream: Any = None,
) -> tuple[int, int, str] | None:
    """lineage fragment의 입력 segment·stream·scalar 범위·exact substring을 확인한다."""

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

    entry = direct[segment_id]
    text = entry.text
    if isinstance(cue_stream, str) and entry.stream_id and cue_stream != entry.stream_id:
        findings.append(
            _finding(
                f"{spot}/input_segment_id",
                "E_STREAM_REF",
                "cue의 stream이 참조한 입력 segment의 stream과 다르다",
            )
        )
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


#: schema 층 message를 **입력 값과 무관한 고정 문구**로 바꾸는 표.
#: `schema_core`는 `enum 밖의 값: {instance!r}`처럼 실제 값을 message에 담는다. 그 모듈은
#: TASK-029에서 수정 금지이므로 여기 boundary에서 정규화·비식별화한다 (REVIEW-023 B-02).
#: 판정 계약은 message가 아니라 `(code, location)`이므로 이 정규화는 계약을 바꾸지 않는다.
_SCHEMA_MESSAGE_RULES: tuple[tuple[str, str], ...] = (
    ("enum 밖의 값", "허용된 enum 값이 아니다"),
    ("const 불일치", "고정된 const 값이 아니다"),
    ("type 불일치", "선언된 type이 아니다"),
    ("필수 필드 누락", "필수 필드가 없다"),
    ("허용되지 않은 추가 필드", "닫힌 객체에 허용되지 않은 추가 필드가 있다"),
    ("uniqueItems 위반", "uniqueItems 위반이다"),
    ("minLength", "minLength를 만족하지 않는다"),
    ("maxLength", "maxLength를 만족하지 않는다"),
    ("pattern 불일치", "선언된 pattern과 맞지 않는다"),
    ("minItems", "minItems를 만족하지 않는다"),
    ("maxItems", "maxItems를 만족하지 않는다"),
    ("minimum", "minimum을 만족하지 않는다"),
    ("maximum", "maximum을 만족하지 않는다"),
    ("exclusiveMinimum", "exclusiveMinimum을 만족하지 않는다"),
    ("exclusiveMaximum", "exclusiveMaximum을 만족하지 않는다"),
    ("finite 숫자가 아니다", "finite 숫자가 아니다"),
    ("RFC 3339 UTC timestamp가 아니다", "RFC 3339 UTC timestamp가 아니다"),
)

_REDACTED_SCHEMA_MESSAGE = "schema 계약 위반"


def redact_schema_message(message: str) -> str:
    """schema 층 message를 결정론적 고정 문구로 바꾼다. 실제 값은 남기지 않는다.

    누락 필드 이름처럼 schema가 선언한 이름은 남길 수 있지만, 그 이름과 값을 구분해
    유지하려면 `schema_core`의 문자열 포맷을 파싱해야 한다. 파싱은 갈라지기 쉬우므로
    **어떤 instance 파생 조각도 남기지 않는** 쪽을 택했다. 위치가 필드를 가리킨다.
    """

    for prefix, replacement in _SCHEMA_MESSAGE_RULES:
        if message.startswith(prefix):
            return replacement
    return _REDACTED_SCHEMA_MESSAGE


def redact_schema_findings(findings: Sequence[Finding]) -> list[Finding]:
    """schema validator가 낸 finding의 `code`는 그대로 두고 message·location을 정규화한다.

    location도 대상이다. `schema_core`는 dynamic key를 pointer 구간에 그대로 넣으므로
    message만 씻으면 같은 값이 location으로 샌다 (REVIEW-024 H-06).
    """

    return [
        Finding(location=safe_location(finding.location), code=finding.code,
                message=redact_schema_message(finding.message))
        for finding in findings
    ]


def dedupe_findings(findings: Sequence[Finding]) -> list[Finding]:
    """같은 `(location, code)`를 여러 번 보고하지 않는다.

    판정 계약은 `(code, location)`이므로 같은 쌍을 두 번 내는 것은 소비자에게 정보가 아니라
    잡음이다. 두 경로가 같은 결함을 서로 다른 문장으로 설명할 수 있는데(예: 문서 집합 안의
    동일성 검사와 검증 컨텍스트 identity 검사), 계약 축에서는 구분되지 않는다.
    `sort_findings` 뒤에 적용하므로 남는 쪽이 결정적이다.

    같은 부모 아래 dynamic key 위반이 여러 개일 때 `safe_location`이 같은 위치로 접는 것도
    여기서 하나로 모인다 (REVIEW-024 H-06).
    """

    seen: set[tuple[str, str]] = set()
    kept: list[Finding] = []
    for finding in findings:
        key = (finding.location, finding.code)
        if key in seen:
            continue
        seen.add(key)
        kept.append(finding)
    return kept


def _check_ref_context(value: Any, validator: Any = None) -> list[Finding]:
    """검증 컨텍스트의 모양. **role을 닫고, 값은 공통 ArtifactRef 계약으로 검사한다.**

    이전 판은 `artifact_id`·`content_hash`가 문자열인지만 봤다. 그래서 `kind=video`,
    임의 추가 field, 쓰이지 않는 role이 모두 통과했다 (REVIEW-025 R-01). 지금은
    `common-v1.schema.json#/$defs/ArtifactRef`를 그대로 재사용한다 — 느슨한 사본을 두지 않는다.
    """

    if not isinstance(value, Mapping):
        return [_finding(REF_CONTEXT_KEY, "E_SCHEMA", f"{REF_CONTEXT_KEY}는 객체여야 한다")]
    findings: list[Finding] = []
    for name in sorted(value):
        spot = f"{REF_CONTEXT_KEY}/{name}"
        if name not in REF_CONTEXT_ROLES:
            findings.append(
                _finding(
                    spot,
                    "E_SCHEMA",
                    f"{REF_CONTEXT_KEY}의 role은 {' | '.join(REF_CONTEXT_ROLES)}뿐이다",
                )
            )
            continue
        if validator is not None:
            findings.extend(
                redact_schema_findings(
                    validator.validate(
                        value[name], COMMON_SCHEMA_FILE, spot, pointer="/$defs/ArtifactRef"
                    )
                )
            )
        # 상류 문서 ref와 같은 종류 결박 — 문서가 아닌 artifact를 문서 identity로 쓸 수 없다.
        findings.extend(_check_document_ref_shape(value[name], spot))
    return findings


def _finalize(findings: Sequence[Finding], documents: Mapping[str, Any]) -> ValidationResult:
    """모든 반환 경로가 지나는 **단일 정규화 지점**.

    location에서 사용자 제어 key를 접고, 정렬한 뒤 같은 `(location, code)`를 하나로 모은다.
    조기 반환 경로가 이 단계를 건너뛰면 dynamic key가 그대로 새어 나간다 (REVIEW-025 R-05).
    """

    resolved = [
        Finding(location=safe_location(finding.location, documents), code=finding.code,
                message=finding.message)
        for finding in findings
    ]
    return ValidationResult(findings=tuple(dedupe_findings(sort_findings(resolved))))


def _check_containers(documents: Mapping[str, Any], validator: Any = None) -> list[Finding]:
    findings: list[Finding] = []
    for key in sorted(documents):
        if key == REF_CONTEXT_KEY:
            findings.extend(_check_ref_context(documents[key], validator))
            continue
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

    container_findings = _check_containers(documents, SchemaValidator(schemas))
    if container_findings:
        # 조기 반환도 **같은 정규화**를 지난다 (REVIEW-025 R-05).
        return _finalize(container_findings, documents)

    validator = SchemaValidator(schemas)
    findings: list[Finding] = []
    schema_failed: set[str] = set()

    segments = documents.get("speech_segments") or []
    for index, segment in enumerate(segments):
        location = f"speech_segments/{index}"
        result = redact_schema_findings(
            validator.validate(segment, DOCUMENT_KEYS["speech_segments"], location)
        )
        if result:
            schema_failed.add("speech_segments")
            findings.extend(result)
    for key in ("transcript", "translated_transcript", "subtitle_document"):
        if key not in documents:
            continue
        result = redact_schema_findings(
            validator.validate(documents[key], DOCUMENT_KEYS[key], key)
        )
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

    refs = documents.get(REF_CONTEXT_KEY)
    findings.extend(
        check_document_ref_identity(documents, refs if isinstance(refs, Mapping) else {})
    )
    findings.extend(check_artifact_consistency(documents))

    return _finalize(findings, documents)


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
EXPECTED_CASE_IDS = tuple(f"K-{index:02d}" for index in range(1, 160))


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
