"""TASK-006 평가 계약 validator.

이 모듈은 두 층을 함께 검사한다.

1. `schemas/*.schema.json`을 **실제로 읽어** 정적 구조를 검사한다. 별도 하드코딩
   검증기를 만들지 않는다.
2. JSON Schema로 표현할 수 없는 교차 문서·시간축·재개 불변식을 검사한다.

Python 3.12 표준 라이브러리만 사용한다. 외부 jsonschema package를 추가하지 않는다.

**공용 schema 검사기는 `schema_core`에 있다** (TASK-028 §3.6에서 추출). JSON 로딩,
`SchemaSet`, `SchemaValidator`, timestamp·portable path 의미 검사는 이 모듈과
`job_runtime`이 **같은 구현**을 쓴다. keyword 해석을 복제해 두 구현이 갈라지게 하지
않는다. 아래 재수출은 기존 TASK-006 공개 이름을 그대로 유지하기 위한 것이며 동작을
바꾸지 않는다.

**Draft 2020-12 전체 구현이 아니다.** `SUPPORTED_KEYWORDS`에 나열한 부분집합만
정확히 검사하고, 그 밖의 keyword가 schema에 나타나면 데이터 오류가 아니라
계약 결함으로 보고 `SchemaContractError`를 던진다. `pattern`은 ECMA-262가 아니라
Python `re`로 해석하므로, schema에는 두 문법에서 뜻이 같은 표현만 쓴다.

이 모듈은 **읽기 전용**이다. 검증 실패에서 입력이나 기존 artifact를 수정·삭제하지 않는다.
"""

from __future__ import annotations

import argparse
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
    SEMANTIC_CHECKS,
    SUPPORTED_KEYWORDS,
    Finding,
    JsonInputError,
    SchemaContractError,
    SchemaValidator,
    load_strict,
    loads_strict,
    portable_relative_path_error,
    sort_findings,
    utc_timestamp_error,
)
from media_clarity.schema_core import SchemaSet as _CoreSchemaSet


__all__ = [
    "DEFAULT_SCHEMA_DIR",
    "ERROR_CODES",
    "EXPECTED_CASE_IDS",
    "Finding",
    "JsonInputError",
    "REPO_ROOT",
    "SCHEMA_DIALECT",
    "SCHEMA_FILES",
    "SCHEMA_VERSION",
    "SEMANTIC_CHECKS",
    "SUPPORTED_KEYWORDS",
    "SchemaContractError",
    "SchemaSet",
    "SchemaValidator",
    "check_document_containers",
    "discover_fixtures",
    "evaluate_fixture",
    "load_fixture",
    "load_strict",
    "loads_strict",
    "metric_status_map",
    "portable_relative_path_error",
    "sort_findings",
    "utc_timestamp_error",
    "validate_documents",
]


SCHEMA_FILES = (
    "common-v1.schema.json",
    "reference-bundle-v1.schema.json",
    "eval-run-manifest-v1.schema.json",
    "eval-report-v1.schema.json",
    "eval-event-v1.schema.json",
    "per-source-metric-record-v1.schema.json",
    "human-review-record-v1.schema.json",
)


class SchemaSet(_CoreSchemaSet):
    """TASK-006의 7개 schema 파일 묶음. 검사 의미는 `schema_core`와 동일하다."""

    def __init__(self, directory: Path):
        super().__init__(directory, SCHEMA_FILES)


TARGET_LANGUAGE = "ko"

#: 두 축을 합치는 이름. 지표 이름으로 나타나면 거부한다 (ADR-0015, T-3).
FORBIDDEN_AGGREGATE_NAMES = frozenset(
    {
        "overall",
        "overall_score",
        "aggregate",
        "aggregate_score",
        "combined",
        "combined_score",
        "composite",
        "composite_score",
        "total",
        "total_score",
        "final_score",
        "weighted_score",
    }
)

TIMING_METRIC_PREFIX = "timing."
SILENCE_METRIC_PREFIX = "silence."
CPWER_METRIC_ID = "cpwer"


# ---------------------------------------------------------------------------
# 오류 코드 — 메시지 문구가 아니라 이 코드와 위치가 테스트 계약이다.
# ---------------------------------------------------------------------------

ERROR_CODES = (
    "E_JSON",
    "E_SCHEMA",
    "E_TIMESTAMP",
    "E_TARGET_LANGUAGE",
    "E_AXIS_MISMATCH",
    "E_SPLIT_LEAKAGE",
    "E_RESUME_FINGERPRINT",
    "E_SHARD_DUPLICATE",
    "E_PAIRED_SAMPLE_SET",
    "E_FINAL_STATUS",
    "E_REQUIRED_METRIC",
    "E_METRIC_PLAN_DUPLICATE",
    "E_METRIC_ID_MISMATCH",
    "E_METRIC_VALUE_FORBIDDEN",
    "E_METRIC_VALUE_REQUIRED",
    "E_METRIC_CAPABILITY",
    "E_AGGREGATE_FORBIDDEN",
    "E_ARTIFACT_PATH",
    "E_TIME_RANGE",
    "E_TIME_MAPPING",
    "E_REFERENCE_ID",
    "E_SILENCE_ATTRIBUTION",
    "E_DOCUMENT_LINK",
)


# ---------------------------------------------------------------------------
# 문서 묶음
# ---------------------------------------------------------------------------

DOCUMENT_SCHEMA = {
    "reference_bundles": "reference-bundle-v1.schema.json",
    "eval_run_manifest": "eval-run-manifest-v1.schema.json",
    "eval_report": "eval-report-v1.schema.json",
    "per_source_records": "per-source-metric-record-v1.schema.json",
    "event_records": "eval-event-v1.schema.json",
    "human_review_records": "human-review-record-v1.schema.json",
}

LIST_DOCUMENTS = frozenset(
    {"reference_bundles", "per_source_records", "event_records", "human_review_records"}
)


def check_document_containers(documents: Mapping[str, Any]) -> list[Finding]:
    """알려진 document key의 container type을 강제한다.

    잘못된 container를 조용히 건너뛰면 `reference_bundles = {}` 같은 입력이
    아무 검사도 받지 않고 통과한다 (REVIEW-014 M-04).
    """

    findings: list[Finding] = []
    for key in sorted(documents):
        if key not in DOCUMENT_SCHEMA:
            continue
        value = documents[key]
        if key in LIST_DOCUMENTS:
            if not isinstance(value, list):
                findings.append(
                    Finding(
                        key,
                        "E_SCHEMA",
                        f"{key}는 배열이어야 한다 ({type(value).__name__} 발견)",
                    )
                )
        elif not isinstance(value, dict):
            findings.append(
                Finding(
                    key,
                    "E_SCHEMA",
                    f"{key}는 객체여야 한다 ({type(value).__name__} 발견)",
                )
            )
    return findings


def _iter_documents(
    documents: Mapping[str, Any], skip: frozenset[str] = frozenset()
) -> Iterable[tuple[str, str, Any]]:
    """(schema 파일, 위치, 인스턴스) 순회. 위치는 결정적 순서로 만든다."""

    for key in sorted(documents):
        schema_file = DOCUMENT_SCHEMA.get(key)
        if schema_file is None or key in skip:
            continue
        value = documents[key]
        if key in LIST_DOCUMENTS:
            for index, item in enumerate(value):
                yield schema_file, f"{key}/{index}", item
        else:
            yield schema_file, key, value


# ---------------------------------------------------------------------------
# 의미 불변식
# ---------------------------------------------------------------------------


def _check_time_range(
    obj: Any, location: str, findings: list[Finding], start_key: str = "start_seconds", end_key: str = "end_seconds"
) -> None:
    if not isinstance(obj, dict):
        return
    start = obj.get(start_key)
    end = obj.get(end_key)
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        return
    if not isinstance(end, (int, float)) or isinstance(end, bool):
        return
    if not math.isfinite(start) or not math.isfinite(end):
        findings.append(Finding(location, "E_TIME_RANGE", "시간 값이 finite가 아니다"))
        return
    if start < 0:
        findings.append(Finding(location, "E_TIME_RANGE", "start_seconds < 0"))
    if end <= start:
        findings.append(Finding(location, "E_TIME_RANGE", "end_seconds <= start_seconds"))


def check_reference_bundle(bundle: Any, location: str) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(bundle, dict):
        return findings

    cues = bundle.get("reference_cues")
    cues = cues if isinstance(cues, list) else []
    axes = {cue.get("reference_axis") for cue in cues if isinstance(cue, dict)}
    target_language = bundle.get("target_language")

    # 불변식 2·3 — target cue가 있으면 정확히 ko, 없으면 target_language를 가장하지 않는다.
    if "target" in axes:
        if target_language is None:
            findings.append(
                Finding(f"{location}/target_language", "E_TARGET_LANGUAGE", "target-axis cue가 있는데 target_language가 없다")
            )
        elif target_language != TARGET_LANGUAGE:
            findings.append(
                Finding(
                    f"{location}/target_language",
                    "E_TARGET_LANGUAGE",
                    f"target_language는 정확히 {TARGET_LANGUAGE!r}여야 한다 (발견: {target_language!r})",
                )
            )
    elif target_language is not None:
        findings.append(
            Finding(
                f"{location}/target_language",
                "E_TARGET_LANGUAGE",
                "target-axis cue가 없는데 target_language를 선언했다 (source cue가 target을 가장할 수 없다)",
            )
        )

    speaker_ids: set[str] = set()
    streams = bundle.get("speaker_streams")
    if isinstance(streams, list):
        for index, stream in enumerate(streams):
            if not isinstance(stream, dict):
                continue
            speaker_id = stream.get("speaker_id")
            if isinstance(speaker_id, str):
                speaker_ids.add(speaker_id)
            utterances = stream.get("utterances")
            if isinstance(utterances, list):
                for u_index, utterance in enumerate(utterances):
                    _check_time_range(
                        utterance, f"{location}/speaker_streams/{index}/utterances/{u_index}", findings
                    )

    for index, cue in enumerate(cues):
        cue_location = f"{location}/reference_cues/{index}"
        _check_time_range(cue, cue_location, findings)
        if isinstance(cue, dict):
            speaker_id = cue.get("speaker_id")
            if isinstance(speaker_id, str) and speaker_id not in speaker_ids:
                findings.append(
                    Finding(
                        f"{cue_location}/speaker_id",
                        "E_REFERENCE_ID",
                        f"존재하지 않는 speaker_id: {speaker_id!r}",
                    )
                )

    mask = bundle.get("speech_mask")
    if isinstance(mask, dict):
        segments = mask.get("segments")
        if isinstance(segments, list):
            for index, segment in enumerate(segments):
                _check_time_range(segment, f"{location}/speech_mask/segments/{index}", findings)
        overlaps = mask.get("overlap_spans")
        if isinstance(overlaps, list):
            for index, span in enumerate(overlaps):
                span_location = f"{location}/speech_mask/overlap_spans/{index}"
                _check_time_range(span, span_location, findings)
                if isinstance(span, dict):
                    for s_index, speaker_id in enumerate(span.get("speaker_ids") or []):
                        if speaker_id not in speaker_ids:
                            findings.append(
                                Finding(
                                    f"{span_location}/speaker_ids/{s_index}",
                                    "E_REFERENCE_ID",
                                    f"존재하지 않는 speaker_id: {speaker_id!r}",
                                )
                            )

    spans = bundle.get("language_spans")
    if isinstance(spans, list):
        for index, span in enumerate(spans):
            span_location = f"{location}/language_spans/{index}"
            _check_time_range(span, span_location, findings)
            if isinstance(span, dict):
                speaker_id = span.get("speaker_id")
                if isinstance(speaker_id, str) and speaker_id not in speaker_ids:
                    findings.append(
                        Finding(
                            f"{span_location}/speaker_id",
                            "E_REFERENCE_ID",
                            f"존재하지 않는 speaker_id: {speaker_id!r}",
                        )
                    )

    findings.extend(_check_bundle_reference_ids(bundle, location))
    findings.extend(_check_time_mapping(bundle, location))
    return findings


def _bundle_timebase_ids(bundle: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("source_timebase", "degraded_timebase"):
        node = bundle.get(key)
        if isinstance(node, dict) and isinstance(node.get("timebase_id"), str):
            ids.add(node["timebase_id"])
    return ids


def _check_bundle_reference_ids(bundle: Mapping[str, Any], location: str) -> list[Finding]:
    """artifact·timebase 참조 무결성 (TASK-006 §3.3 불변식 4, REVIEW-014 M-01).

    speaker ID만 확인하면 `timebase_ref = "tb-ghost"`나 존재하지 않는
    `origin_artifact`가 그대로 통과한다.
    """

    findings: list[Finding] = []
    artifact_ids: set[str] = set()
    for key in ("source_media", "degraded_media", "clean_video"):
        node = bundle.get(key)
        if isinstance(node, dict) and isinstance(node.get("artifact_id"), str):
            artifact_ids.add(node["artifact_id"])
    timebase_ids = _bundle_timebase_ids(bundle)

    def require_timebase(value: Any, where: str) -> None:
        if isinstance(value, str) and value not in timebase_ids:
            findings.append(
                Finding(
                    where,
                    "E_REFERENCE_ID",
                    f"존재하지 않는 timebase_id: {value!r} "
                    f"(bundle의 timebase: {', '.join(sorted(timebase_ids)) or '없음'})",
                )
            )

    def require_artifact(value: Any, where: str) -> None:
        if isinstance(value, str) and value not in artifact_ids:
            findings.append(
                Finding(
                    where,
                    "E_REFERENCE_ID",
                    f"존재하지 않는 artifact_id: {value!r} "
                    f"(bundle의 artifact: {', '.join(sorted(artifact_ids)) or '없음'})",
                )
            )

    # timebase는 자기 origin artifact와 실제로 연결되어야 한다.
    media_of_timebase = {
        "source_timebase": "source_media",
        "degraded_timebase": "degraded_media",
    }
    for timebase_key, media_key in media_of_timebase.items():
        timebase = bundle.get(timebase_key)
        if not isinstance(timebase, dict):
            continue
        origin = timebase.get("origin_artifact")
        origin_location = f"{location}/{timebase_key}/origin_artifact"
        require_artifact(origin, origin_location)
        media = bundle.get(media_key)
        if not isinstance(media, dict):
            findings.append(
                Finding(
                    f"{location}/{media_key}",
                    "E_REFERENCE_ID",
                    f"{timebase_key}가 있는데 {media_key}가 없다",
                )
            )
        elif origin != media.get("artifact_id"):
            findings.append(
                Finding(
                    origin_location,
                    "E_REFERENCE_ID",
                    f"{timebase_key}.origin_artifact가 {media_key}.artifact_id"
                    f"({media.get('artifact_id')!r})와 다르다",
                )
            )

    for key in ("source_media", "degraded_media", "clean_video"):
        node = bundle.get(key)
        if isinstance(node, dict):
            require_timebase(node.get("timebase_ref"), f"{location}/{key}/timebase_ref")

    findings.extend(_check_definition_identity(bundle, location))

    # 역할별 정확 연결 — 존재하는 **다른** timebase를 가리키면 membership 검사는 통과하지만
    # source/degraded 시간축이 조용히 뒤바뀐다 (REVIEW-015 M-01-R1).
    for media_key, timebase_key in (
        ("source_media", "source_timebase"),
        ("degraded_media", "degraded_timebase"),
    ):
        media = bundle.get(media_key)
        if not isinstance(media, dict) or "timebase_ref" not in media:
            continue
        declared = media["timebase_ref"]
        where = f"{location}/{media_key}/timebase_ref"
        if not isinstance(declared, str) or declared not in timebase_ids:
            # 알 수 없는 ID는 위의 membership 검사가 이미 보고했다.
            continue
        timebase = bundle.get(timebase_key)
        if not isinstance(timebase, dict):
            findings.append(
                Finding(
                    where,
                    "E_REFERENCE_ID",
                    f"{media_key}.timebase_ref가 있는데 {timebase_key}가 없어 역할 연결을 "
                    "검증할 수 없다",
                )
            )
            continue
        expected = timebase.get("timebase_id")
        if declared != expected:
            findings.append(
                Finding(
                    where,
                    "E_REFERENCE_ID",
                    f"{media_key}.timebase_ref는 {timebase_key}.timebase_id({expected!r})여야 "
                    f"한다 (발견: {declared!r})",
                )
            )

    for index, stream in enumerate(bundle.get("speaker_streams") or []):
        if not isinstance(stream, dict):
            continue
        for u_index, utterance in enumerate(stream.get("utterances") or []):
            if isinstance(utterance, dict):
                require_timebase(
                    utterance.get("timebase_ref"),
                    f"{location}/speaker_streams/{index}/utterances/{u_index}/timebase_ref",
                )

    for index, cue in enumerate(bundle.get("reference_cues") or []):
        if isinstance(cue, dict):
            require_timebase(
                cue.get("timebase_ref"), f"{location}/reference_cues/{index}/timebase_ref"
            )

    mask = bundle.get("speech_mask")
    if isinstance(mask, dict):
        require_timebase(mask.get("timebase_ref"), f"{location}/speech_mask/timebase_ref")

    return findings


#: timebase **정의** 슬롯과 그 역할이 요구하는 domain. 참조(ArtifactRef.timebase_ref,
#: TimeMapping.from/to 등)는 정의가 아니므로 여기에 넣지 않는다.
_TIMEBASE_DEFINITIONS = (("source_timebase", "source"), ("degraded_timebase", "degraded"))

#: artifact **정의** 슬롯. `origin_artifact`·`parent_refs` 같은 참조는 정의가 아니다.
_ARTIFACT_DEFINITIONS = ("source_media", "degraded_media", "clean_video")


def _check_definition_identity(bundle: Mapping[str, Any], location: str) -> list[Finding]:
    """timebase 역할 domain과 정의 ID의 유일성 (REVIEW-016 M-01-R2).

    역할별 `timebase_ref` 연결만으로는 다음이 통과한다.

    - 두 timebase의 `domain`만 서로 바꾼 입력
    - 두 timebase 정의를 같은 ID 하나로 합친 입력
    - 서로 다른 media 정의가 같은 `artifact_id`를 쓰는 입력

    **정의 ID와 참조 ID를 구분한다.** `ArtifactRef.timebase_ref`나
    `Timebase.origin_artifact`가 정의와 같은 ID를 쓰는 것은 정상 연결이며 중복 정의가 아니다.
    """

    findings: list[Finding] = []

    # 1. 역할이 요구하는 domain
    for key, expected_domain in _TIMEBASE_DEFINITIONS:
        timebase = bundle.get(key)
        if not isinstance(timebase, dict):
            continue
        actual = timebase.get("domain")
        if actual != expected_domain:
            findings.append(
                Finding(
                    f"{location}/{key}/domain",
                    "E_REFERENCE_ID",
                    f"{key}.domain은 {expected_domain!r}여야 한다 (발견: {actual!r})",
                )
            )

    # 2. source/degraded timebase 정의의 ID는 서로 달라야 한다.
    source_timebase = bundle.get("source_timebase")
    degraded_timebase = bundle.get("degraded_timebase")
    if isinstance(source_timebase, dict) and isinstance(degraded_timebase, dict):
        source_id = source_timebase.get("timebase_id")
        degraded_id = degraded_timebase.get("timebase_id")
        if isinstance(source_id, str) and source_id == degraded_id:
            findings.append(
                Finding(
                    f"{location}/degraded_timebase/timebase_id",
                    "E_REFERENCE_ID",
                    f"source_timebase와 degraded_timebase가 같은 timebase_id {source_id!r}를 "
                    "쓴다 — 두 시간축을 구분할 수 없다",
                )
            )

    # 3. 같은 artifact_id를 쓰는 서로 **다른** 정의는 모호하다.
    #    정의가 완전히 같으면 중복일 뿐 모호하지 않으므로 거부하지 않는다.
    seen_artifacts: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for key in _ARTIFACT_DEFINITIONS:
        node = bundle.get(key)
        if not isinstance(node, dict):
            continue
        artifact_id = node.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        previous = seen_artifacts.get(artifact_id)
        if previous is not None and previous[1] != node:
            findings.append(
                Finding(
                    f"{location}/{key}/artifact_id",
                    "E_REFERENCE_ID",
                    f"artifact_id {artifact_id!r}를 서로 다른 정의가 함께 쓴다 "
                    f"(먼저 정의된 위치: {previous[0]})",
                )
            )
            continue
        if previous is None:
            seen_artifacts[artifact_id] = (key, node)
    return findings


def _check_time_mapping(bundle: Mapping[str, Any], location: str) -> list[Finding]:
    findings: list[Finding] = []
    mapping = bundle.get("time_mapping")
    source_timebase = bundle.get("source_timebase")
    degraded_timebase = bundle.get("degraded_timebase")

    # 불변식 6 — 서로 다른 시간축이 있으면 명시적 TimeMapping이 필요하다.
    if degraded_timebase is not None and mapping is None:
        findings.append(
            Finding(
                f"{location}/time_mapping",
                "E_TIME_MAPPING",
                "degraded_timebase가 있는데 TimeMapping이 없다",
            )
        )
        return findings
    if not isinstance(mapping, dict):
        return findings

    map_location = f"{location}/time_mapping"

    # from/to는 이 bundle에 실제로 존재하는 timebase를 가리켜야 한다 (REVIEW-014 M-01).
    timebase_ids = _bundle_timebase_ids(bundle)
    for key in ("from_timebase", "to_timebase"):
        value = mapping.get(key)
        if isinstance(value, str) and value not in timebase_ids:
            findings.append(
                Finding(
                    f"{map_location}/{key}",
                    "E_REFERENCE_ID",
                    f"존재하지 않는 timebase_id: {value!r} "
                    f"(bundle의 timebase: {', '.join(sorted(timebase_ids)) or '없음'})",
                )
            )

    if isinstance(source_timebase, dict):
        source_id = source_timebase.get("timebase_id")
        if mapping.get("from_timebase") != source_id:
            findings.append(
                Finding(
                    f"{map_location}/from_timebase",
                    "E_TIME_MAPPING",
                    "from_timebase가 source_timebase와 다르다",
                )
            )
    if isinstance(degraded_timebase, dict):
        degraded_id = degraded_timebase.get("timebase_id")
        if mapping.get("to_timebase") != degraded_id:
            findings.append(
                Finding(
                    f"{map_location}/to_timebase",
                    "E_TIME_MAPPING",
                    "to_timebase가 degraded_timebase와 다르다",
                )
            )

    # 불변식 7 — segment는 단조이며 선언된 invertibility와 모순되지 않는다.
    if mapping.get("is_monotonic") is not True:
        findings.append(
            Finding(f"{map_location}/is_monotonic", "E_TIME_MAPPING", "매핑은 단조여야 한다")
        )

    segments = mapping.get("segments")
    if isinstance(segments, list):
        previous_from_end: float | None = None
        previous_to_end: float | None = None
        for index, segment in enumerate(segments):
            segment_location = f"{map_location}/segments/{index}"
            if not isinstance(segment, dict):
                continue
            _check_time_range(segment, segment_location, findings, "from_start", "from_end")
            _check_time_range(segment, segment_location, findings, "to_start", "to_end")
            from_start = segment.get("from_start")
            to_start = segment.get("to_start")
            if isinstance(from_start, (int, float)) and previous_from_end is not None:
                if from_start < previous_from_end:
                    findings.append(
                        Finding(segment_location, "E_TIME_MAPPING", "from 구간이 단조 증가하지 않는다")
                    )
            if isinstance(to_start, (int, float)) and previous_to_end is not None:
                if to_start < previous_to_end:
                    findings.append(
                        Finding(segment_location, "E_TIME_MAPPING", "to 구간이 단조 증가하지 않는다")
                    )
            if isinstance(segment.get("from_end"), (int, float)):
                previous_from_end = float(segment["from_end"])
            if isinstance(segment.get("to_end"), (int, float)):
                previous_to_end = float(segment["to_end"])

    inserted = mapping.get("inserted_spans") or []
    dropped = mapping.get("dropped_spans") or []
    for index, span in enumerate(inserted):
        _check_time_range(span, f"{map_location}/inserted_spans/{index}", findings, "to_start", "to_end")
    for index, span in enumerate(dropped):
        _check_time_range(span, f"{map_location}/dropped_spans/{index}", findings, "from_start", "from_end")

    if mapping.get("is_invertible") is True and (inserted or dropped):
        findings.append(
            Finding(
                f"{map_location}/is_invertible",
                "E_TIME_MAPPING",
                "inserted_spans 또는 dropped_spans가 있으면 역변환이 성립하지 않는다",
            )
        )
    if mapping.get("method") == "identity" and (inserted or dropped):
        findings.append(
            Finding(
                f"{map_location}/method",
                "E_TIME_MAPPING",
                "identity 매핑에는 inserted/dropped span이 있을 수 없다",
            )
        )
    return findings


def _metric_plan_versions(manifest: Mapping[str, Any]) -> dict[tuple[str, str], tuple[Any, Any]]:
    """(axis, metric_id) -> (implementation_version, normalization_version)."""

    versions: dict[tuple[str, str], tuple[Any, Any]] = {}
    for entry in manifest.get("metric_plan") or []:
        if not isinstance(entry, dict):
            continue
        axis = entry.get("axis")
        metric_id = entry.get("metric_id")
        if isinstance(axis, str) and isinstance(metric_id, str):
            versions.setdefault(
                (axis, metric_id),
                (entry.get("implementation_version"), entry.get("normalization_version")),
            )
    return versions


def check_manifest(manifest: Any, location: str) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(manifest, dict):
        return findings

    # metric plan의 (axis, metric_id)는 유일해야 한다. 중복이면 어느 버전이
    # 유효한지 결정할 수 없다 (REVIEW-014 M-03).
    seen_plan_keys: set[tuple[str, str]] = set()
    for index, entry in enumerate(manifest.get("metric_plan") or []):
        if not isinstance(entry, dict):
            continue
        axis = entry.get("axis")
        metric_id = entry.get("metric_id")
        if not isinstance(axis, str) or not isinstance(metric_id, str):
            continue
        if (axis, metric_id) in seen_plan_keys:
            findings.append(
                Finding(
                    f"{location}/metric_plan/{index}",
                    "E_METRIC_PLAN_DUPLICATE",
                    f"({axis}, {metric_id})가 metric plan에 두 번 나온다",
                )
            )
        seen_plan_keys.add((axis, metric_id))

    evidence = manifest.get("split_evidence")
    if isinstance(evidence, dict):
        for kind in ("source", "speaker"):
            dev = set(evidence.get(f"dev_{kind}_ids") or [])
            test = set(evidence.get(f"test_{kind}_ids") or [])
            shared = sorted(dev & test)
            if shared:
                findings.append(
                    Finding(
                        f"{location}/split_evidence/dev_{kind}_ids",
                        "E_SPLIT_LEAKAGE",
                        f"dev/test {kind} 교집합: {', '.join(shared)}",
                    )
                )
        findings.extend(_check_split_evidence_covers_dataset(manifest, evidence, location))

    available_axes: set[str] = set()
    for bundle in manifest.get("reference_bundles") or []:
        if isinstance(bundle, dict):
            available_axes.update(bundle.get("available_axes") or [])

    for index, hypothesis in enumerate(manifest.get("hypotheses") or []):
        if not isinstance(hypothesis, dict):
            continue
        hypothesis_location = f"{location}/hypotheses/{index}"
        axis = hypothesis.get("reference_axis")
        if axis is not None and available_axes and axis not in available_axes:
            findings.append(
                Finding(
                    f"{hypothesis_location}/reference_axis",
                    "E_AXIS_MISMATCH",
                    f"가설 축 {axis!r}에 대응하는 정답 축이 없다 (제공 축: {', '.join(sorted(available_axes))})",
                )
            )
        target_language = hypothesis.get("target_language")
        if axis == "target":
            if target_language is None:
                findings.append(
                    Finding(
                        f"{hypothesis_location}/target_language",
                        "E_TARGET_LANGUAGE",
                        "target 축 가설에 target_language가 없다",
                    )
                )
            elif target_language != TARGET_LANGUAGE:
                findings.append(
                    Finding(
                        f"{hypothesis_location}/target_language",
                        "E_TARGET_LANGUAGE",
                        f"target_language는 정확히 {TARGET_LANGUAGE!r}여야 한다 (발견: {target_language!r})",
                    )
                )
        elif target_language is not None:
            findings.append(
                Finding(
                    f"{hypothesis_location}/target_language",
                    "E_TARGET_LANGUAGE",
                    "source 축 가설이 target_language를 선언했다",
                )
            )

    # hypothesis graph를 해석하기 **전에** ID 유일성을 확정한다 (REVIEW-016 M-04-R2).
    duplicate_findings, ambiguous_hypothesis_ids = _check_hypothesis_id_uniqueness(
        manifest, location
    )
    findings.extend(duplicate_findings)
    findings.extend(_check_paired_comparison(manifest, location, ambiguous_hypothesis_ids))
    findings.extend(_check_resume(manifest, location))
    findings.extend(_check_artifact_paths(manifest, location))
    return findings


def _check_split_evidence_covers_dataset(
    manifest: Mapping[str, Any], evidence: Mapping[str, Any], location: str
) -> list[Finding]:
    """split evidence가 실제 dataset을 증명하는지 (REVIEW-014 M-04).

    dataset과 무관한 ID로 evidence를 채우면 dev/test 교집합이 비어 있어도
    분할을 증명하지 못한다.
    """

    findings: list[Finding] = []
    split = manifest.get("split")
    if split not in {"dev", "test"}:
        return findings
    other = "test" if split == "dev" else "dev"
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        return findings

    for kind in ("source", "speaker"):
        declared = set(dataset.get(f"{kind}_ids") or [])
        if not declared:
            continue
        own = set(evidence.get(f"{split}_{kind}_ids") or [])
        opposite = set(evidence.get(f"{other}_{kind}_ids") or [])
        missing = sorted(declared - own)
        if missing:
            findings.append(
                Finding(
                    f"{location}/split_evidence/{split}_{kind}_ids",
                    "E_DOCUMENT_LINK",
                    f"dataset의 {kind} ID가 {split} evidence에 없다: {', '.join(missing)}",
                )
            )
        crossed = sorted(declared & opposite)
        if crossed:
            findings.append(
                Finding(
                    f"{location}/split_evidence/{other}_{kind}_ids",
                    "E_SPLIT_LEAKAGE",
                    f"split={split}인데 dataset의 {kind} ID가 {other} evidence에도 있다: "
                    f"{', '.join(crossed)}",
                )
            )
    return findings


def _check_hypothesis_id_uniqueness(
    manifest: Mapping[str, Any], location: str
) -> tuple[list[Finding], frozenset[str]]:
    """`hypothesis_id`는 manifest 전체에서 유일해야 한다 (REVIEW-016 M-04-R2).

    중복을 조용히 `setdefault`로 첫 객체만 고르면 paired reference가 어느 정의를
    가리키는지 모호해지고, 목록 순서만 바꿔도 검증 대상이 달라진다.

    반환값의 두 번째 원소는 **모호해진 ID 집합**이다. 호출자는 이 ID에 대해
    객체 해석을 하지 않는다.
    """

    findings: list[Finding] = []
    seen: dict[str, int] = {}
    duplicated: set[str] = set()
    for index, entry in enumerate(manifest.get("hypotheses") or []):
        if not isinstance(entry, dict):
            continue
        hypothesis_id = entry.get("hypothesis_id")
        if not isinstance(hypothesis_id, str):
            continue
        if hypothesis_id in seen:
            duplicated.add(hypothesis_id)
            findings.append(
                Finding(
                    f"{location}/hypotheses/{index}/hypothesis_id",
                    "E_DOCUMENT_LINK",
                    f"hypothesis_id {hypothesis_id!r}가 중복이다 "
                    f"(먼저 정의된 위치: hypotheses/{seen[hypothesis_id]})",
                )
            )
            continue
        seen[hypothesis_id] = index
    return findings, frozenset(duplicated)


def _check_paired_comparison(
    manifest: Mapping[str, Any],
    location: str,
    ambiguous_hypothesis_ids: frozenset[str] = frozenset(),
) -> list[Finding]:
    """paired comparison이 실제 hypothesis·dataset과 연결되는지 (REVIEW-014 M-04)."""

    findings: list[Finding] = []
    paired = manifest.get("paired_comparison")
    if not isinstance(paired, dict):
        return findings
    paired_location = f"{location}/paired_comparison"

    # 유일한 ID만 객체로 해석한다. 중복 ID는 uniqueness 검사가 이미 보고했다.
    hypothesis_index: dict[str, int] = {}
    hypotheses: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(manifest.get("hypotheses") or []):
        if not isinstance(entry, dict):
            continue
        hypothesis_id = entry.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or hypothesis_id in ambiguous_hypothesis_ids:
            continue
        if hypothesis_id in hypotheses:  # pragma: no cover - uniqueness 검사가 먼저 걸러낸다
            continue
        hypotheses[hypothesis_id] = entry
        hypothesis_index[hypothesis_id] = index
    dataset = manifest.get("dataset")
    dataset_samples = (
        set(dataset.get("sample_ids") or []) if isinstance(dataset, dict) else set()
    )

    baseline_ids = paired.get("baseline_sample_ids")
    candidate_ids = paired.get("candidate_sample_ids")
    if isinstance(baseline_ids, list) and isinstance(candidate_ids, list):
        if set(baseline_ids) != set(candidate_ids):
            findings.append(
                Finding(
                    f"{paired_location}/candidate_sample_ids",
                    "E_PAIRED_SAMPLE_SET",
                    "baseline과 candidate의 표본 집합이 다르다",
                )
            )

    def compare_with_dataset(samples: Any, where: str, what: str) -> None:
        """paired 비교의 증거는 **같은 전체 dataset 표본**이다. 진부분집합도 거부한다."""

        if not isinstance(samples, list) or not dataset_samples:
            return
        actual = set(samples)
        if actual == dataset_samples:
            return
        missing = sorted(dataset_samples - actual)
        extra = sorted(actual - dataset_samples)
        detail = []
        if missing:
            detail.append(f"누락 {', '.join(missing)}")
        if extra:
            detail.append(f"dataset 밖 {', '.join(extra)}")
        findings.append(
            Finding(
                where,
                "E_PAIRED_SAMPLE_SET",
                f"{what}이 dataset sample 집합과 다르다 ({'; '.join(detail)})",
            )
        )

    for role in ("baseline", "candidate"):
        hypothesis_id = paired.get(f"{role}_hypothesis_id")
        samples = paired.get(f"{role}_sample_ids")
        id_location = f"{paired_location}/{role}_hypothesis_id"
        sample_location = f"{paired_location}/{role}_sample_ids"

        compare_with_dataset(samples, sample_location, f"{role} paired 표본 집합")

        if hypothesis_id in ambiguous_hypothesis_ids:
            # 어느 정의를 가리키는지 결정할 수 없다. 중복은 uniqueness 검사가 보고했으므로
            # 임의의 객체를 골라 검사하지 않는다 (REVIEW-016 M-04-R2).
            continue

        hypothesis = hypotheses.get(hypothesis_id)
        if hypothesis is None:
            findings.append(
                Finding(
                    id_location,
                    "E_DOCUMENT_LINK",
                    f"manifest hypotheses에 없는 {role} 가설: {hypothesis_id!r}",
                )
            )
            continue
        if hypothesis.get("role") != role:
            findings.append(
                Finding(
                    id_location,
                    "E_DOCUMENT_LINK",
                    f"{hypothesis_id!r}의 role이 {hypothesis.get('role')!r}인데 "
                    f"{role}로 지정됐다",
                )
            )
            continue

        index = hypothesis_index[hypothesis_id]
        hypothesis_samples = hypothesis.get("sample_ids")
        if not isinstance(hypothesis_samples, list):
            # 선택적으로 빠질 수 있는 집합은 paired 비교의 증거가 아니다 (REVIEW-015 M-04-R1).
            findings.append(
                Finding(
                    f"{location}/hypotheses/{index}",
                    "E_PAIRED_SAMPLE_SET",
                    f"paired {role} 가설 {hypothesis_id!r}에 sample_ids가 없다",
                )
            )
            continue

        compare_with_dataset(
            hypothesis_samples,
            f"{location}/hypotheses/{index}/sample_ids",
            f"{role} 가설 sample_ids",
        )
        if isinstance(samples, list) and set(samples) != set(hypothesis_samples):
            findings.append(
                Finding(
                    sample_location,
                    "E_PAIRED_SAMPLE_SET",
                    f"{role} 표본 집합이 가설 {hypothesis_id!r}의 sample_ids와 다르다",
                )
            )
    return findings


def _check_resume(manifest: Mapping[str, Any], location: str) -> list[Finding]:
    findings: list[Finding] = []
    resume = manifest.get("resume")
    if not isinstance(resume, dict):
        return findings

    resume_location = f"{location}/resume"
    current = manifest.get("fingerprints")
    previous = resume.get("previous_fingerprints")
    if isinstance(current, dict) and isinstance(previous, dict):
        for key in sorted(set(current) | set(previous)):
            if current.get(key) != previous.get(key):
                findings.append(
                    Finding(
                        f"{resume_location}/previous_fingerprints/{key}",
                        "E_RESUME_FINGERPRINT",
                        f"fingerprint {key} 불일치 — 기존 run에 이어 쓰지 않는다",
                    )
                )

    # 버전 비교는 (axis, metric_id) 단위다. metric_id만으로 묶으면 source와 target의
    # 같은 지표를 구분하지 못한다 (REVIEW-014 M-03).
    # 위반 위치는 **실제 입력 노드**를 가리켜야 한다. `previous_metric_versions`는 배열이므로
    # `.../<axis>/<metric_id>` 같은 합성 pointer를 만들지 않고 실제 index를 보존한다
    # (REVIEW-015 R-03-1). 값 불일치는 그 필드를, 누락은 실제 존재하는 부모 container를 가리킨다.
    planned_versions = _metric_plan_versions(manifest)
    versions_location = f"{resume_location}/previous_metric_versions"
    previous_versions: dict[tuple[str, str], tuple[int, Any, Any]] = {}
    for index, entry in enumerate(resume.get("previous_metric_versions") or []):
        if not isinstance(entry, dict):
            continue
        axis = entry.get("axis")
        metric_id = entry.get("metric_id")
        if not isinstance(axis, str) or not isinstance(metric_id, str):
            continue
        key = (axis, metric_id)
        if key in previous_versions:
            findings.append(
                Finding(
                    f"{versions_location}/{index}",
                    "E_METRIC_PLAN_DUPLICATE",
                    f"이전 버전 목록에 ({axis}, {metric_id})가 두 번 나온다",
                )
            )
            continue
        previous_versions[key] = (
            index,
            entry.get("implementation_version"),
            entry.get("normalization_version"),
        )

    for key in sorted(set(planned_versions) | set(previous_versions)):
        axis, metric_id = key
        current_entry = planned_versions.get(key)
        previous_entry = previous_versions.get(key)
        if current_entry is None:
            index = previous_entry[0]
            findings.append(
                Finding(
                    f"{versions_location}/{index}",
                    "E_RESUME_FINGERPRINT",
                    f"현재 metric plan에 없는 ({axis}, {metric_id})가 이전 버전 목록에 있다",
                )
            )
            continue
        if previous_entry is None:
            # 해당 entry 자체가 없으므로 실제로 존재하는 부모 배열을 가리킨다.
            findings.append(
                Finding(
                    versions_location,
                    "E_RESUME_FINGERPRINT",
                    f"({axis}, {metric_id})의 이전 버전 기록이 없다 — 기존 run에 이어 쓰지 않는다",
                )
            )
            continue
        index, previous_impl, previous_norm = previous_entry
        current_impl, current_norm = current_entry
        if current_impl != previous_impl:
            findings.append(
                Finding(
                    f"{versions_location}/{index}/implementation_version",
                    "E_RESUME_FINGERPRINT",
                    f"({axis}, {metric_id}) implementation_version 불일치: "
                    f"이전 {previous_impl!r} vs 현재 {current_impl!r}",
                )
            )
        # normalization version은 존재 여부까지 비교한다. 한쪽에만 있으면 불일치다.
        if current_norm != previous_norm:
            # 이전 entry에 필드가 없으면 그 필드를 가리킬 수 없으므로 entry 자체를 가리킨다.
            where = (
                f"{versions_location}/{index}/normalization_version"
                if previous_norm is not None
                else f"{versions_location}/{index}"
            )
            findings.append(
                Finding(
                    where,
                    "E_RESUME_FINGERPRINT",
                    f"({axis}, {metric_id}) normalization_version 불일치: "
                    f"이전 {previous_norm!r} vs 현재 {current_norm!r}",
                )
            )

    shards = resume.get("completed_shards")
    if isinstance(shards, list):
        seen_ids: set[str] = set()
        seen_hashes: set[str] = set()
        for index, shard in enumerate(shards):
            if not isinstance(shard, dict):
                continue
            shard_location = f"{resume_location}/completed_shards/{index}"
            shard_id = shard.get("shard_id")
            content_hash = shard.get("content_hash")
            if isinstance(shard_id, str):
                if shard_id in seen_ids:
                    findings.append(
                        Finding(f"{shard_location}/shard_id", "E_SHARD_DUPLICATE", f"shard 중복: {shard_id}")
                    )
                seen_ids.add(shard_id)
            if isinstance(content_hash, str):
                if content_hash in seen_hashes:
                    findings.append(
                        Finding(
                            f"{shard_location}/content_hash",
                            "E_SHARD_DUPLICATE",
                            "같은 shard 내용을 두 번 완료로 표시했다",
                        )
                    )
                seen_hashes.add(content_hash)
    return findings


def _check_artifact_paths(manifest: Mapping[str, Any], location: str) -> list[Finding]:
    findings: list[Finding] = []
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return findings
    for key in sorted(artifacts):
        reason = portable_relative_path_error(artifacts[key])
        if reason is not None:
            findings.append(
                Finding(
                    f"{location}/artifacts/{key}",
                    "E_ARTIFACT_PATH",
                    f"portable relative path가 아니다: {reason}",
                )
            )
    return findings


def _iter_metric_results(report: Mapping[str, Any], location: str) -> Iterable[tuple[str, str, str, Mapping[str, Any]]]:
    """(축, metric_id, 위치, MetricResult) 순회 — 결정적 순서."""

    by_axis = report.get("metrics_by_axis")
    if isinstance(by_axis, dict):
        for axis in ("source", "target"):
            bucket = by_axis.get(axis)
            if isinstance(bucket, dict):
                for metric_id in sorted(bucket):
                    result = bucket[metric_id]
                    if isinstance(result, dict):
                        yield axis, metric_id, f"{location}/metrics_by_axis/{axis}/{metric_id}", result
    axisless = report.get("metrics")
    if isinstance(axisless, dict):
        for metric_id in sorted(axisless):
            result = axisless[metric_id]
            if isinstance(result, dict):
                yield "axisless", metric_id, f"{location}/metrics/{metric_id}", result


def check_report(report: Any, location: str) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(report, dict):
        return findings

    # completed ↔ final은 양방향이다 (REVIEW-014 M-02).
    kind = report.get("document_kind")
    status = report.get("run_status")
    if kind == "final" and status != "completed":
        findings.append(
            Finding(
                f"{location}/document_kind",
                "E_FINAL_STATUS",
                f"run_status={status!r}인 실행을 final report로 선언했다",
            )
        )
    if status == "completed" and kind != "final":
        findings.append(
            Finding(
                f"{location}/document_kind",
                "E_FINAL_STATUS",
                f"run_status=completed인 실행의 document_kind가 {kind!r}다 (final이어야 한다)",
            )
        )

    for axis, metric_id, metric_location, result in _iter_metric_results(report, location):
        # map의 key가 지표의 정체다. 내부 metric_id가 다르면 저장 위치를 신뢰할 수 없다.
        inner_id = result.get("metric_id")
        if isinstance(inner_id, str) and inner_id != metric_id:
            findings.append(
                Finding(
                    f"{metric_location}/metric_id",
                    "E_METRIC_ID_MISMATCH",
                    f"map key {metric_id!r}와 MetricResult.metric_id {inner_id!r}가 다르다",
                )
            )
        if metric_id.lower() in FORBIDDEN_AGGREGATE_NAMES:
            findings.append(
                Finding(
                    metric_location,
                    "E_AGGREGATE_FORBIDDEN",
                    f"두 축을 합치는 지표 이름은 허용하지 않는다: {metric_id}",
                )
            )
        findings.extend(_check_metric_result(result, metric_location))
        if axis == "axisless" and metric_id.startswith((TIMING_METRIC_PREFIX, SILENCE_METRIC_PREFIX)):
            findings.append(
                Finding(
                    metric_location,
                    "E_AXIS_MISMATCH",
                    f"{metric_id}는 축 표기가 필요한 지표다 (EVALS §4 Y-5)",
                )
            )

    return findings


def _check_metric_result(result: Mapping[str, Any], location: str) -> list[Finding]:
    findings: list[Finding] = []
    status = result.get("status")
    has_value = "value" in result
    value = result.get("value")

    if status == "computed":
        if not has_value:
            findings.append(
                Finding(f"{location}/value", "E_METRIC_VALUE_REQUIRED", "computed에는 finite value가 필요하다")
            )
        elif isinstance(value, float) and not math.isfinite(value):
            findings.append(Finding(f"{location}/value", "E_METRIC_VALUE_REQUIRED", "value가 finite가 아니다"))
    elif status in {"unsupported", "insufficient_n", "failed"}:
        if has_value:
            findings.append(
                Finding(
                    f"{location}/value",
                    "E_METRIC_VALUE_FORBIDDEN",
                    f"status={status}에는 value를 쓰지 않는다 (0점이 아니다)",
                )
            )
        if not result.get("reason"):
            findings.append(
                Finding(f"{location}/reason", "E_METRIC_VALUE_REQUIRED", f"status={status}에는 안정 reason이 필요하다")
            )
        if status == "insufficient_n" and "n" not in result:
            findings.append(
                Finding(f"{location}/n", "E_METRIC_VALUE_REQUIRED", "insufficient_n에는 n이 필요하다")
            )
    return findings


def check_cross_document(documents: Mapping[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    manifest = documents.get("eval_run_manifest")
    report = documents.get("eval_report")
    bundles = documents.get("reference_bundles") or []
    bundles = [b for b in bundles if isinstance(b, dict)]

    manifest_is_dict = isinstance(manifest, dict)
    report_is_dict = isinstance(report, dict)

    if manifest_is_dict and report_is_dict:
        if manifest.get("run_id") != report.get("run_id"):
            findings.append(
                Finding("eval_report/run_id", "E_DOCUMENT_LINK", "manifest와 report의 run_id가 다르다")
            )
        if manifest.get("split") != report.get("split"):
            findings.append(
                Finding("eval_report/split", "E_DOCUMENT_LINK", "manifest와 report의 split이 다르다")
            )

    if manifest_is_dict and bundles:
        declared = {
            entry.get("bundle_id"): entry
            for entry in manifest.get("reference_bundles") or []
            if isinstance(entry, dict)
        }
        for index, bundle in enumerate(bundles):
            bundle_id = bundle.get("bundle_id")
            entry = declared.get(bundle_id)
            if entry is None:
                findings.append(
                    Finding(
                        f"reference_bundles/{index}/bundle_id",
                        "E_DOCUMENT_LINK",
                        f"manifest가 선언하지 않은 번들: {bundle_id!r}",
                    )
                )
                continue
            actual_axes = {
                cue.get("reference_axis")
                for cue in bundle.get("reference_cues") or []
                if isinstance(cue, dict)
            }
            declared_axes = set(entry.get("available_axes") or [])
            missing = sorted(declared_axes - actual_axes)
            if missing:
                findings.append(
                    Finding(
                        f"reference_bundles/{index}/reference_cues",
                        "E_AXIS_MISMATCH",
                        f"manifest가 선언한 축을 번들이 제공하지 않는다: {', '.join(missing)}",
                    )
                )

    if manifest_is_dict and report_is_dict:
        findings.extend(_check_metric_axis_placement(manifest, report))
        findings.extend(_check_required_metrics(manifest, report))
        findings.extend(_check_capability_unsupported(manifest, report, bundles))

    findings.extend(_check_silence_attribution(bundles, report if report_is_dict else None))
    findings.extend(_check_guardrail_review_link(documents))
    return findings


def _check_metric_axis_placement(
    manifest: Mapping[str, Any], report: Mapping[str, Any]
) -> list[Finding]:
    findings: list[Finding] = []
    # 같은 metric_id가 두 축에 계획될 수 있다 (타이밍·무음은 두 축 모두 — EVALS §4 Y-5).
    planned: dict[str, set[str]] = {}
    for entry in manifest.get("metric_plan") or []:
        if isinstance(entry, dict) and isinstance(entry.get("metric_id"), str):
            planned.setdefault(entry["metric_id"], set()).add(entry.get("axis"))
    for axis, metric_id, location, _result in _iter_metric_results(report, "eval_report"):
        allowed = planned.get(metric_id)
        if allowed is None:
            findings.append(
                Finding(location, "E_DOCUMENT_LINK", f"metric plan에 없는 지표: {metric_id}")
            )
        elif axis not in allowed:
            findings.append(
                Finding(
                    location,
                    "E_AXIS_MISMATCH",
                    f"{metric_id}의 계획 축은 {sorted(allowed)}인데 {axis!r} 칸에 담겼다",
                )
            )
    return findings


def _check_required_metrics(
    manifest: Mapping[str, Any], report: Mapping[str, Any]
) -> list[Finding]:
    """completed 실행의 required metric 완료 조건 (EVAL_HARNESS §4, REVIEW-014 M-02).

    completed는 required metric이 **전부 computed**이거나, metric plan이
    `allow_insufficient_n: true`로 **사전 허용한** insufficient_n일 때뿐이다.
    누락·`failed`·예상 밖 `unsupported`는 completed를 거부한다.
    """

    findings: list[Finding] = []
    if report.get("run_status") != "completed":
        return findings

    buckets: dict[str, Mapping[str, Any]] = {}
    by_axis = report.get("metrics_by_axis")
    if isinstance(by_axis, dict):
        for axis in ("source", "target"):
            bucket = by_axis.get(axis)
            buckets[axis] = bucket if isinstance(bucket, dict) else {}
    axisless = report.get("metrics")
    buckets["axisless"] = axisless if isinstance(axisless, dict) else {}

    seen: set[tuple[str, str]] = set()
    for entry in manifest.get("metric_plan") or []:
        if not isinstance(entry, dict) or entry.get("required") is not True:
            continue
        axis = entry.get("axis")
        metric_id = entry.get("metric_id")
        if not isinstance(axis, str) or not isinstance(metric_id, str):
            continue
        if (axis, metric_id) in seen:
            continue
        seen.add((axis, metric_id))

        where = (
            f"eval_report/metrics/{metric_id}"
            if axis == "axisless"
            else f"eval_report/metrics_by_axis/{axis}/{metric_id}"
        )
        result = buckets.get(axis, {}).get(metric_id)
        if not isinstance(result, dict):
            findings.append(
                Finding(
                    where,
                    "E_REQUIRED_METRIC",
                    f"completed 실행인데 required 지표 ({axis}, {metric_id})가 report에 없다",
                )
            )
            continue

        status = result.get("status")
        if status == "computed":
            continue
        if status == "insufficient_n":
            if entry.get("allow_insufficient_n") is True:
                continue
            findings.append(
                Finding(
                    where,
                    "E_REQUIRED_METRIC",
                    f"required 지표 ({axis}, {metric_id})의 insufficient_n을 completed로 "
                    "승격하려면 metric plan에 allow_insufficient_n: true가 있어야 한다",
                )
            )
            continue
        findings.append(
            Finding(
                where,
                "E_REQUIRED_METRIC",
                f"required 지표 ({axis}, {metric_id})가 status={status!r}인데 "
                "run_status=completed다",
            )
        )
    return findings


def _check_capability_unsupported(
    manifest: Mapping[str, Any],
    report: Mapping[str, Any],
    bundles: Sequence[Mapping[str, Any]],
) -> list[Finding]:
    """정답·능력이 없으면 computed일 수 없다. 미지원은 0점이 아니다."""

    findings: list[Finding] = []
    available_axes: set[str] = set()
    for entry in manifest.get("reference_bundles") or []:
        if isinstance(entry, dict):
            available_axes.update(entry.get("available_axes") or [])

    single_stream = any(
        isinstance(h, dict) and h.get("supports_overlap_streams") is False
        for h in manifest.get("hypotheses") or []
    )
    has_overlap_reference = any(
        (bundle.get("speech_mask") or {}).get("overlap_spans") for bundle in bundles
    )
    non_invertible = any(
        isinstance(bundle.get("time_mapping"), dict)
        and bundle["time_mapping"].get("is_invertible") is False
        for bundle in bundles
    )

    for axis, metric_id, location, result in _iter_metric_results(report, "eval_report"):
        status = result.get("status")
        if status != "computed":
            continue
        if axis in {"source", "target"} and available_axes and axis not in available_axes:
            findings.append(
                Finding(
                    location,
                    "E_METRIC_CAPABILITY",
                    f"{axis} 축 정답이 없는데 {metric_id}를 computed로 보고했다 (unsupported여야 한다)",
                )
            )
        if metric_id == CPWER_METRIC_ID and single_stream and has_overlap_reference:
            findings.append(
                Finding(
                    location,
                    "E_METRIC_CAPABILITY",
                    "single-stream 가설에서 cpWER는 unsupported여야 한다 (EVALS §4.2)",
                )
            )
        if metric_id.startswith(TIMING_METRIC_PREFIX) and non_invertible:
            findings.append(
                Finding(
                    location,
                    "E_TIME_MAPPING",
                    "is_invertible=false에서 타이밍 지표는 unsupported여야 한다 (ARCHITECTURE §2.3)",
                )
            )
    return findings


def _check_silence_attribution(
    bundles: Sequence[Mapping[str, Any]], report: Mapping[str, Any] | None
) -> list[Finding]:
    """삽입된 무음이 있으면 정답이 있는 모든 축의 무음 지표에 귀속되어야 한다."""

    findings: list[Finding] = []
    if report is None:
        return findings
    inserted_silence = False
    for bundle in bundles:
        mapping = bundle.get("time_mapping")
        if not isinstance(mapping, dict):
            continue
        for span in mapping.get("inserted_spans") or []:
            if isinstance(span, dict) and span.get("kind") == "silence":
                inserted_silence = True
    if not inserted_silence:
        return findings

    available_axes: set[str] = set()
    for bundle in bundles:
        for cue in bundle.get("reference_cues") or []:
            if isinstance(cue, dict) and cue.get("reference_axis") in {"source", "target"}:
                available_axes.add(cue["reference_axis"])

    by_axis = report.get("metrics_by_axis")
    for axis in sorted(available_axes):
        bucket = (by_axis or {}).get(axis) if isinstance(by_axis, dict) else None
        names = [name for name in (bucket or {}) if name.startswith(SILENCE_METRIC_PREFIX)]
        if not names:
            findings.append(
                Finding(
                    f"eval_report/metrics_by_axis/{axis}",
                    "E_SILENCE_ATTRIBUTION",
                    f"삽입 무음이 있는데 {axis} 축에 무음 지표가 없다 (EVALS §4.4)",
                )
            )
    return findings


def _check_guardrail_review_link(documents: Mapping[str, Any]) -> list[Finding]:
    """guardrail이 표본을 올렸으면 사람 검토 record가 실제로 있어야 한다."""

    findings: list[Finding] = []
    report = documents.get("eval_report")
    if not isinstance(report, dict):
        return findings
    reviews = documents.get("human_review_records") or []
    reviewed = {
        record.get("sample_id")
        for record in reviews
        if isinstance(record, dict) and record.get("trigger") == "guardrail_flagged"
    }
    for index, guardrail in enumerate(report.get("guardrails") or []):
        if not isinstance(guardrail, dict):
            continue
        location = f"eval_report/guardrails/{index}"
        flagged = guardrail.get("flagged_sample_ids") or []
        count = guardrail.get("count")
        if isinstance(count, int) and count > 0 and not flagged:
            findings.append(
                Finding(f"{location}/flagged_sample_ids", "E_DOCUMENT_LINK", "guardrail count>0인데 표본이 없다")
            )
        if flagged and not (set(flagged) & reviewed):
            findings.append(
                Finding(
                    f"{location}/flagged_sample_ids",
                    "E_DOCUMENT_LINK",
                    "guardrail 표본이 사람 검토 record로 이어지지 않았다 (EVAL_HARNESS §6.2)",
                )
            )
    return findings


def _check_record_links(documents: Mapping[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    manifest = documents.get("eval_run_manifest")
    run_id = manifest.get("run_id") if isinstance(manifest, dict) else None
    if run_id is None:
        return findings
    for key in ("per_source_records", "event_records", "human_review_records"):
        for index, record in enumerate(documents.get(key) or []):
            if isinstance(record, dict) and record.get("run_id") != run_id:
                findings.append(
                    Finding(f"{key}/{index}/run_id", "E_DOCUMENT_LINK", "record의 run_id가 manifest와 다르다")
                )
    for index, record in enumerate(documents.get("per_source_records") or []):
        if isinstance(record, dict) and isinstance(record.get("result"), dict):
            findings.extend(
                _check_metric_result(record["result"], f"per_source_records/{index}/result")
            )
    for index, record in enumerate(documents.get("event_records") or []):
        if not isinstance(record, dict):
            continue
        code = record.get("error_code")
        if isinstance(code, str) and code not in ERROR_CODES:
            findings.append(
                Finding(
                    f"event_records/{index}/error_code",
                    "E_DOCUMENT_LINK",
                    f"알 수 없는 오류 코드: {code}",
                )
            )
    return findings


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
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({finding.code for finding in self.findings}))


def metric_status_map(documents: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """report의 실제 metric status. fixture의 expected와 비교하기 위한 관측값이다."""

    report = documents.get("eval_report")
    status: dict[str, dict[str, str]] = {"source": {}, "target": {}, "axisless": {}}
    if not isinstance(report, dict):
        return status
    for axis, metric_id, _location, result in _iter_metric_results(report, "eval_report"):
        value = result.get("status")
        if isinstance(value, str):
            status[axis][metric_id] = value
    return status


def validate_documents(documents: Mapping[str, Any], schemas: SchemaSet) -> ValidationResult:
    """schema 검사 → 문서별 의미 불변식 → 교차 문서 불변식.

    schema 검사에서 실패하면 그 문서의 의미 검사는 건너뛴다. 구조가 깨진 문서에
    파생 오류를 쌓지 않기 위해서다.
    """

    validator = SchemaValidator(schemas)
    findings: list[Finding] = []
    schema_failed: set[str] = set()

    container_findings = check_document_containers(documents)
    if container_findings:
        # container가 깨진 문서는 파생 오류를 쌓지 않고 여기서 멈춘다.
        return ValidationResult(findings=tuple(sort_findings(container_findings)))

    for schema_file, location, instance in _iter_documents(documents):
        document_findings = validator.validate(instance, schema_file, location)
        if document_findings:
            schema_failed.add(location)
            findings.extend(document_findings)

    for index, bundle in enumerate(documents.get("reference_bundles") or []):
        location = f"reference_bundles/{index}"
        if location not in schema_failed:
            findings.extend(check_reference_bundle(bundle, location))

    if "eval_run_manifest" not in schema_failed and "eval_run_manifest" in documents:
        findings.extend(check_manifest(documents["eval_run_manifest"], "eval_run_manifest"))

    if "eval_report" not in schema_failed and "eval_report" in documents:
        findings.extend(check_report(documents["eval_report"], "eval_report"))

    if not schema_failed:
        findings.extend(check_cross_document(documents))
        findings.extend(_check_record_links(documents))

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
    observed_codes: tuple[str, ...]
    observed_metric_status: dict[str, dict[str, str]]


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = load_strict(path)
    if not isinstance(fixture, dict):
        raise JsonInputError(f"{path.name}: fixture root가 객체가 아니다")
    for key in ("case_id", "expected", "documents"):
        if key not in fixture:
            raise JsonInputError(f"{path.name}: fixture에 {key}가 없다")
    return fixture


def evaluate_fixture(path: Path, schemas: SchemaSet) -> FixtureOutcome:
    fixture = load_fixture(path)
    expected = fixture["expected"]
    documents = fixture["documents"]
    result = validate_documents(documents, schemas)
    observed_status = metric_status_map(documents)

    mismatches: list[str] = []
    expected_valid = bool(expected.get("valid"))
    if result.valid != expected_valid:
        mismatches.append(
            f"valid: 기대 {expected_valid}, 관측 {result.valid} "
            f"(코드: {', '.join(result.codes) or '없음'})"
        )
    expected_codes = tuple(sorted(expected.get("error_codes") or []))
    if expected_codes != result.codes:
        mismatches.append(
            f"error_codes: 기대 [{', '.join(expected_codes)}], 관측 [{', '.join(result.codes)}]"
        )
    for axis, wanted in (expected.get("metric_status") or {}).items():
        for metric_id, wanted_status in wanted.items():
            actual = observed_status.get(axis, {}).get(metric_id)
            if actual != wanted_status:
                mismatches.append(
                    f"metric_status[{axis}][{metric_id}]: 기대 {wanted_status}, 관측 {actual}"
                )

    return FixtureOutcome(
        case_id=str(fixture["case_id"]),
        path=path,
        passed=not mismatches,
        mismatches=tuple(mismatches),
        observed_codes=result.codes,
        observed_metric_status=observed_status,
    )


def discover_fixtures(directory: Path) -> list[Path]:
    return sorted(directory.glob("h-*.json"))


def run_fixtures(directory: Path, schemas: SchemaSet) -> list[FixtureOutcome]:
    return [evaluate_fixture(path, schemas) for path in discover_fixtures(directory)]


EXPECTED_CASE_IDS = tuple(f"H-{index:02d}" for index in range(1, 15))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m media_clarity.eval_contracts",
        description="TASK-006 평가 계약 fixture runner (읽기 전용).",
    )
    parser.add_argument(
        "--fixtures",
        required=True,
        type=Path,
        help="H-01~H-14 fixture 디렉터리",
    )
    parser.add_argument(
        "--schemas",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help="schema 디렉터리 (기본: 저장소의 schemas/)",
    )
    args = parser.parse_args(argv)

    try:
        schemas = SchemaSet(args.schemas)
    except (SchemaContractError, JsonInputError) as exc:
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

    observed_ids = tuple(outcome.case_id for outcome in outcomes)
    failures = 0

    for outcome in outcomes:
        if outcome.passed:
            print(f"PASS {outcome.case_id} {outcome.path.name} [{', '.join(outcome.observed_codes) or '유효'}]")
        else:
            failures += 1
            print(f"FAIL {outcome.case_id} {outcome.path.name}")
            for mismatch in outcome.mismatches:
                print(f"     {mismatch}")

    missing = [case_id for case_id in EXPECTED_CASE_IDS if case_id not in observed_ids]
    if missing:
        failures += 1
        print(f"FAIL 누락된 fixture: {', '.join(missing)}")
    duplicates = sorted({cid for cid in observed_ids if observed_ids.count(cid) > 1})
    if duplicates:
        failures += 1
        print(f"FAIL 중복 case_id: {', '.join(duplicates)}")

    print(f"실행 {len(outcomes)}건 / 기대 {len(EXPECTED_CASE_IDS)}건 / 실패 {failures}건")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - 진입점
    raise SystemExit(main())
