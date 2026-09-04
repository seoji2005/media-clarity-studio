"""TASK-032 frozen-pack, decision-rule, and preflight contracts.

This module is deliberately stdlib-only.  It validates immutable screening
inputs, typed preparation evidence, and honest blockers; it does not download a
model, transcribe audio, or claim target Windows/GPU compatibility.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from media_clarity.artifact_store import (
    ArtifactStore,
    ContractViolation,
    cas_relative_uri,
    digest_of,
)
from media_clarity.job_runtime import canonical_hash, canonical_json_bytes
from media_clarity.schema_core import (
    COMMON_SCHEMA_FILE,
    DEFAULT_SCHEMA_DIR,
    Finding,
    JsonInputError,
    SchemaSet,
    SchemaValidator,
    loads_strict,
    sort_findings,
)


PREFLIGHT_SCHEMA_FILE = "asr-screen-preflight-v1.schema.json"
PACK_SCHEMA_FILE = "asr-screen-pack-manifest-v1.schema.json"
DECISION_RULE_SCHEMA_FILE = "asr-screen-decision-rule-v1.schema.json"
PREPARATION_SCHEMA_FILE = "asr-screen-preparation-v1.schema.json"
SCHEMA_FILES = (
    COMMON_SCHEMA_FILE,
    PREFLIGHT_SCHEMA_FILE,
    PACK_SCHEMA_FILE,
    DECISION_RULE_SCHEMA_FILE,
    PREPARATION_SCHEMA_FILE,
)
WORK_CPU_RECEIPT_POINTER = "/$defs/work_cpu_receipt"
SCREEN_CONFIGURATION_POINTER = "/$defs/screen_configuration"
ACCESS_LICENSE_RECEIPT_POINTER = "/$defs/access_license_receipt"
MODEL_RECEIPT_POINTER = "/$defs/model_receipt"
DEPENDENCY_LOCK_POINTER = "/$defs/dependency_lock"

CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "qwen3-asr-1.7b",
        "official_model_id": "Qwen/Qwen3-ASR-1.7B",
        "revision": "7278e1e70fe206f11671096ffdd38061171dd6e5",
        "observed_license": "Apache-2.0",
        "gated": False,
    },
    {
        "candidate_id": "cohere-transcribe-03-2026",
        "official_model_id": "CohereLabs/cohere-transcribe-03-2026",
        "revision": "b1eacc2686a3d08ceaae5f24a88b1d519620bc09",
        "observed_license": "Apache-2.0",
        "gated": True,
    },
    {
        "candidate_id": "faster-whisper-large-v3",
        "official_model_id": "Systran/faster-whisper-large-v3",
        "revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
        "observed_license": "MIT",
        "gated": False,
    },
)
CANDIDATE_ORDER = tuple(item["candidate_id"] for item in CANDIDATES)

TIER_ORDER = (
    "fatal_rate_and_safety_cells",
    "human_correction_seconds_per_audio_minute",
    "japanese_cer_and_english_wer",
    "mixed_and_names_numbers_terms_error_rate",
)

STRATA = (
    "clean_japanese",
    "clean_english",
    "code_switch_names_numbers_terms",
    "fast_conversation_weak_overlap",
    "music_noise_compression",
    "silence_non_speech",
)
PRIMARY_STRATUM_SECONDS = {
    "clean_japanese": 180.0,
    "clean_english": 180.0,
    "code_switch_names_numbers_terms": 240.0,
    "fast_conversation_weak_overlap": 180.0,
    "music_noise_compression": 180.0,
    "silence_non_speech": 120.0,
}

ERROR_CODES = (
    "E_SCHEMA",
    "E_CANDIDATE_IDENTITY",
    "E_SCREEN_POLICY",
    "E_PREFLIGHT_STATE",
    "E_EVIDENCE_SLOT",
    "E_PACK_STRUCTURE",
    "E_PACK_ARTIFACT",
    "E_PACK_BINDING",
    "E_DECISION_RULE_POLICY",
    "E_DECISION_RULE_BINDING",
    "E_WORK_CPU_RECEIPT",
    "E_PREPARATION_ARTIFACT",
    "E_CONFIGURATION_POLICY",
    "E_CONFIGURATION_BINDING",
    "E_ACCESS_RECEIPT_BINDING",
    "E_MODEL_RECEIPT_BINDING",
    "E_DEPENDENCY_LOCK_BINDING",
    "E_RESUME_EVIDENCE",
    "E_ACCESS_RECEIPT",
    "E_CONFIGURATION_PENDING",
    "E_DECISION_RULE_PENDING",
    "E_DEPENDENCY_LOCK_PENDING",
    "E_MODEL_RECEIPT_PENDING",
    "E_PACK_PENDING",
    "E_WORK_CPU_EVIDENCE_PENDING",
)


def asr_screen_schema_set(directory: Path | None = None) -> SchemaSet:
    return SchemaSet(directory or DEFAULT_SCHEMA_DIR, SCHEMA_FILES)


def _validator(directory: Path | None = None) -> SchemaValidator:
    return SchemaValidator(asr_screen_schema_set(directory))


def _finding(location: str, code: str, message: str) -> Finding:
    if code not in ERROR_CODES:
        raise AssertionError(f"undeclared TASK-032 error code: {code}")
    return Finding(location=location, code=code, message=message)


def _schema_findings(
    document: Any,
    schema_file: str,
    location: str,
    *,
    pointer: str = "",
    schema_dir: Path | None = None,
) -> list[Finding]:
    return _validator(schema_dir).validate(document, schema_file, location, pointer)


def _ref_key(ref: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        ref.get("artifact_id"),
        ref.get("content_hash"),
        ref.get("uri"),
        ref.get("byte_size"),
        ref.get("kind"),
        ref.get("media_type"),
    )


def _verify_cas_ref(
    ref: Any,
    *,
    store: ArtifactStore,
    location: str,
    expected_kind: str | None = None,
    expected_media_type: str | None = None,
    error_code: str = "E_PACK_ARTIFACT",
) -> list[Finding]:
    findings = _schema_findings(
        ref,
        COMMON_SCHEMA_FILE,
        location,
        pointer="/$defs/ArtifactRef",
    )
    if findings or not isinstance(ref, Mapping):
        return findings
    try:
        expected_uri = cas_relative_uri(digest_of(ref["content_hash"]))
    except (ContractViolation, KeyError, TypeError):
        return [_finding(location, error_code, "content hash cannot form a canonical CAS URI")]
    if ref.get("uri") != expected_uri:
        findings.append(_finding(f"{location}/uri", error_code, "not a canonical CAS URI"))
        return sort_findings(findings)
    cursor = store.project_root
    for segment in Path(expected_uri).parts:
        cursor /= segment
        if cursor.is_symlink():
            findings.append(_finding(f"{location}/uri", error_code, "CAS path contains a symbolic-link alias"))
            return sort_findings(findings)
    try:
        store.verify_ref(ref, location)
    except (ContractViolation, KeyError, TypeError) as error:
        findings.append(_finding(location, error_code, str(error)))
        return sort_findings(findings)
    if expected_kind is not None and ref.get("kind") != expected_kind:
        findings.append(_finding(f"{location}/kind", error_code, f"kind must be {expected_kind}"))
    if expected_media_type is not None and ref.get("media_type") != expected_media_type:
        findings.append(
            _finding(f"{location}/media_type", error_code, f"media type must be {expected_media_type}")
        )
    return sort_findings(findings)


def _load_json_ref(
    ref: Any,
    *,
    store: ArtifactStore,
    location: str,
    error_code: str = "E_PACK_ARTIFACT",
) -> tuple[Mapping[str, Any] | None, list[Finding]]:
    findings = _verify_cas_ref(
        ref,
        store=store,
        location=location,
        expected_kind="text",
        expected_media_type="application/json",
        error_code=error_code,
    )
    if findings or not isinstance(ref, Mapping):
        return None, findings
    try:
        payload = store.absolute(ref["uri"], f"{location}/uri").read_bytes()
        document = loads_strict(payload.decode("utf-8"))
    except (ContractViolation, JsonInputError, UnicodeDecodeError, OSError, KeyError, TypeError):
        return None, [_finding(location, error_code, "JSON CAS evidence cannot be read strictly")]
    if not isinstance(document, Mapping):
        return None, [_finding(location, error_code, "JSON CAS evidence root must be an object")]
    try:
        if payload != canonical_json_bytes(document):
            return None, [_finding(location, error_code, "JSON CAS evidence is not canonical")]
    except (TypeError, ValueError, UnicodeEncodeError):
        return None, [_finding(location, error_code, "JSON CAS evidence cannot be canonicalized")]
    return document, []


def validate_pack_manifest(
    document: Any,
    *,
    store: ArtifactStore | None = None,
    location: str = "pack",
    schema_dir: Path | None = None,
) -> list[Finding]:
    """Validate one pack and, when supplied, every referenced CAS object."""

    findings = _schema_findings(document, PACK_SCHEMA_FILE, location, schema_dir=schema_dir)
    if findings or not isinstance(document, Mapping):
        return sort_findings(findings)

    clips = document["clips"]
    clip_ids = [clip["clip_id"] for clip in clips]
    duplicates = sorted(item for item, count in Counter(clip_ids).items() if count > 1)
    if duplicates:
        findings.append(_finding(f"{location}/clips", "E_PACK_STRUCTURE", "clip_id values must be unique"))

    duration_sum = math.fsum(float(clip["duration_seconds"]) for clip in clips)
    if not math.isclose(duration_sum, float(document["total_duration_seconds"]), rel_tol=0, abs_tol=1e-9):
        findings.append(
            _finding(f"{location}/total_duration_seconds", "E_PACK_STRUCTURE", "total does not equal clip durations")
        )

    strata = Counter(clip["stratum"] for clip in clips)
    if set(strata) != set(STRATA):
        findings.append(_finding(f"{location}/clips", "E_PACK_STRUCTURE", "pack must cover the exact six strata"))
    evaluated_hashes = [clip["evaluated_hash"] for clip in clips]
    if len(set(evaluated_hashes)) != len(evaluated_hashes):
        findings.append(
            _finding(f"{location}/clips", "E_PACK_STRUCTURE", "evaluated clip content hashes must be unique")
        )

    if document["purpose"] == "frozen_evaluation":
        expected_total = 1080.0 if document["role"] == "primary" else 720.0
        if not math.isclose(float(document["total_duration_seconds"]), expected_total, rel_tol=0, abs_tol=1e-9):
            findings.append(
                _finding(
                    f"{location}/total_duration_seconds",
                    "E_PACK_STRUCTURE",
                    f"{document['role']} frozen evaluation duration must be {expected_total:g} seconds",
                )
            )
        if document["role"] == "primary":
            actual = {
                stratum: math.fsum(
                    float(clip["duration_seconds"])
                    for clip in clips
                    if clip["stratum"] == stratum
                )
                for stratum in STRATA
            }
            if actual != PRIMARY_STRATUM_SECONDS:
                findings.append(
                    _finding(f"{location}/clips", "E_PACK_STRUCTURE", "primary stratum durations do not match TASK-032")
                )
            for stratum in ("clean_japanese", "clean_english"):
                if not any(
                    clip["stratum"] == stratum and clip["source_kind"] == "real_human"
                    for clip in clips
                ):
                    findings.append(
                        _finding(f"{location}/clips", "E_PACK_STRUCTURE", f"{stratum} must include real human speech")
                    )

    for index, clip in enumerate(clips):
        where = f"{location}/clips/{index}"
        tts_engine = clip["tts_engine_id"]
        if (clip["source_kind"] == "tts") != bool(tts_engine):
            findings.append(
                _finding(f"{where}/tts_engine_id", "E_PACK_STRUCTURE", "tts_engine_id must be present only for TTS")
            )
        if clip["source_kind"] == "real_human" and clip["source_class"] == "synthetic_non_sensitive":
            findings.append(
                _finding(
                    f"{where}/source_class",
                    "E_PACK_STRUCTURE",
                    "real human speech cannot be classified as synthetic",
                )
            )
        if clip["original_hash"] != clip["original_audio_ref"].get("content_hash"):
            findings.append(_finding(f"{where}/original_hash", "E_PACK_BINDING", "original hash does not bind its ref"))
        if clip["evaluated_hash"] != clip["evaluated_audio_ref"].get("content_hash"):
            findings.append(_finding(f"{where}/evaluated_hash", "E_PACK_BINDING", "evaluated hash does not bind its ref"))
        if store is not None:
            for field in ("original_audio_ref", "evaluated_audio_ref"):
                findings.extend(
                    _verify_cas_ref(
                        clip[field],
                        store=store,
                        location=f"{where}/{field}",
                        expected_kind="audio",
                    )
                )
            for field in ("reference_transcript_ref", "language_spans_ref", "item_annotations_ref"):
                findings.extend(
                    _verify_cas_ref(
                        clip[field],
                        store=store,
                        location=f"{where}/{field}",
                        expected_kind="text",
                        expected_media_type="application/json",
                    )
                )
            if "speech_mask_ref" in clip:
                findings.extend(
                    _verify_cas_ref(
                        clip["speech_mask_ref"],
                        store=store,
                        location=f"{where}/speech_mask_ref",
                        expected_kind="text",
                        expected_media_type="application/json",
                    )
                )
    return sort_findings(findings)


def validate_pack_pair(
    primary: Any,
    reserve: Any,
    *,
    store: ArtifactStore | None = None,
    location: str = "packs",
) -> list[Finding]:
    findings = validate_pack_manifest(primary, store=store, location=f"{location}/primary")
    findings.extend(validate_pack_manifest(reserve, store=store, location=f"{location}/reserve"))
    if findings or not isinstance(primary, Mapping) or not isinstance(reserve, Mapping):
        return sort_findings(findings)
    if primary["role"] != "primary" or reserve["role"] != "reserve":
        findings.append(_finding(location, "E_PACK_STRUCTURE", "pack roles must be primary then reserve"))
    if primary["purpose"] != reserve["purpose"]:
        findings.append(_finding(location, "E_PACK_STRUCTURE", "primary and reserve purposes must match"))
    combined = list(primary["clips"]) + list(reserve["clips"])
    tts_engines = {clip["tts_engine_id"] for clip in combined if clip["source_kind"] == "tts"}
    if primary["purpose"] == "frozen_evaluation" and not any(
        clip["source_kind"] == "real_human" for clip in combined
    ):
        findings.append(_finding(location, "E_PACK_STRUCTURE", "combined production pack must include real human speech"))
    if len(tts_engines) < 2:
        findings.append(_finding(location, "E_PACK_STRUCTURE", "combined pack must include at least two TTS engines"))
    primary_ids = {clip["clip_id"] for clip in primary["clips"]}
    reserve_ids = {clip["clip_id"] for clip in reserve["clips"]}
    if primary_ids & reserve_ids:
        findings.append(_finding(location, "E_PACK_STRUCTURE", "primary and reserve clip IDs must be disjoint"))
    primary_audio = {clip["evaluated_hash"] for clip in primary["clips"]}
    reserve_audio = {clip["evaluated_hash"] for clip in reserve["clips"]}
    if primary_audio & reserve_audio:
        findings.append(
            _finding(location, "E_PACK_STRUCTURE", "primary and reserve evaluated audio must be disjoint")
        )
    primary_sources = {clip["source_id"] for clip in primary["clips"]}
    reserve_sources = {clip["source_id"] for clip in reserve["clips"]}
    if primary_sources & reserve_sources:
        findings.append(
            _finding(location, "E_PACK_STRUCTURE", "primary and reserve source IDs must be disjoint")
        )
    for role, pack in (("primary", primary), ("reserve", reserve)):
        source_metadata: dict[str, tuple[Any, ...]] = {}
        for clip in pack["clips"]:
            identity = (
                clip["source_class"],
                clip["source_kind"],
                clip["license_id"],
                clip["tts_engine_id"],
            )
            prior = source_metadata.setdefault(clip["source_id"], identity)
            if prior != identity:
                findings.append(
                    _finding(
                        f"{location}/{role}/clips",
                        "E_PACK_STRUCTURE",
                        "one source_id cannot describe conflicting source metadata",
                    )
                )
    return sort_findings(findings)


def validate_decision_rule(
    document: Any,
    *,
    primary_pack_ref: Mapping[str, Any] | None = None,
    reserve_pack_ref: Mapping[str, Any] | None = None,
    location: str = "decision_rule",
    schema_dir: Path | None = None,
) -> list[Finding]:
    """Validate policy constants and bind the rule to both frozen pack refs."""

    findings = _schema_findings(document, DECISION_RULE_SCHEMA_FILE, location, schema_dir=schema_dir)
    if not isinstance(document, Mapping):
        return sort_findings(findings)
    if findings:
        policy_roots = (
            f"{location}/bootstrap",
            f"{location}/mpe",
            f"{location}/pairwise_policy",
            f"{location}/reserve_policy",
            f"{location}/primary_metric",
            f"{location}/denominator",
            f"{location}/source_cluster_key",
        )
        if any(finding.location.startswith(policy_roots) for finding in findings):
            findings.append(
                _finding(location, "E_DECISION_RULE_POLICY", "decision rule constants differ from TASK-032")
            )
        return sort_findings(findings)
    if tuple(document["candidate_order"]) != CANDIDATE_ORDER:
        findings.append(
            _finding(f"{location}/candidate_order", "E_DECISION_RULE_POLICY", "candidate order differs from TASK-032")
        )
    if tuple(document["tier_order"]) != TIER_ORDER:
        findings.append(
            _finding(f"{location}/tier_order", "E_DECISION_RULE_POLICY", "tier order differs from TASK-032")
        )
    refs = (("primary_pack_hash", primary_pack_ref), ("reserve_pack_hash", reserve_pack_ref))
    for field, ref in refs:
        if ref is not None and document[field] != ref.get("content_hash"):
            findings.append(_finding(f"{location}/{field}", "E_DECISION_RULE_BINDING", "pack hash does not bind its ref"))
    if document["primary_pack_hash"] == document["reserve_pack_hash"]:
        findings.append(
            _finding(location, "E_DECISION_RULE_BINDING", "primary and reserve pack hashes must be distinct")
        )
    return sort_findings(findings)


def _expected_candidate(candidate_id: str) -> Mapping[str, Any] | None:
    return next((candidate for candidate in CANDIDATES if candidate["candidate_id"] == candidate_id), None)


def validate_screen_configuration(
    document: Any,
    *,
    location: str = "screen_configuration",
    schema_dir: Path | None = None,
) -> list[Finding]:
    findings = _schema_findings(
        document,
        PREPARATION_SCHEMA_FILE,
        location,
        pointer=SCREEN_CONFIGURATION_POINTER,
        schema_dir=schema_dir,
    )
    if findings or not isinstance(document, Mapping):
        return sort_findings(findings)
    if tuple(document["candidate_order"]) != CANDIDATE_ORDER:
        findings.append(
            _finding(f"{location}/candidate_order", "E_CONFIGURATION_BINDING", "candidate order differs from TASK-032")
        )

    vad = document["vad"]
    expected_boundary = "whole_clip" if vad["mode"] == "disabled" else "pack_speech_mask"
    if vad["boundary_source"] != expected_boundary:
        findings.append(
            _finding(f"{location}/vad/boundary_source", "E_CONFIGURATION_POLICY", "VAD mode and boundary source disagree")
        )

    hint = document["language_hint"]
    if hint["mode"] == "none":
        valid_hint = hint["value_source"] == "none" and hint["allowed_tags"] == []
    else:
        valid_hint = (
            hint["value_source"] == "pack_clip_language_hint"
            and hint["allowed_tags"] == ["ja", "en"]
        )
    if not valid_hint:
        findings.append(
            _finding(f"{location}/language_hint", "E_CONFIGURATION_POLICY", "language-hint fields do not form a closed policy")
        )

    chunking = document["chunking"]
    if chunking["mode"] == "one_clip_per_unit":
        valid_chunking = chunking["overlap_seconds"] == 0 and chunking["stitching"] == "none"
    else:
        valid_chunking = (
            chunking["overlap_seconds"] < chunking["max_clip_seconds"]
            and chunking["stitching"] == "frozen_overlap_dedup"
        )
    if not valid_chunking:
        findings.append(
            _finding(f"{location}/chunking", "E_CONFIGURATION_POLICY", "chunking fields do not form a closed policy")
        )
    return sort_findings(findings)


def validate_configuration_pack_binding(
    configuration: Mapping[str, Any],
    primary: Mapping[str, Any],
    reserve: Mapping[str, Any],
    *,
    location: str = "configuration_pack_binding",
) -> list[Finding]:
    findings: list[Finding] = []
    clips = list(primary["clips"]) + list(reserve["clips"])
    hint_mode = configuration["language_hint"]["mode"]
    for index, clip in enumerate(clips):
        where = f"{location}/clips/{index}"
        has_hint = "language_hint" in clip
        if hint_mode == "none" and has_hint:
            findings.append(_finding(f"{where}/language_hint", "E_CONFIGURATION_BINDING", "hint is forbidden by frozen configuration"))
        if hint_mode == "per_clip_dominant":
            if clip["source_kind"] == "non_speech" and has_hint:
                findings.append(_finding(f"{where}/language_hint", "E_CONFIGURATION_BINDING", "non-speech clip must not carry a language hint"))
            if clip["source_kind"] != "non_speech" and not has_hint:
                findings.append(_finding(f"{where}/language_hint", "E_CONFIGURATION_BINDING", "speech clip requires a frozen dominant-language hint"))
        if configuration["vad"]["mode"] == "frozen_common_boundaries" and "speech_mask_ref" not in clip:
            findings.append(_finding(f"{where}/speech_mask_ref", "E_CONFIGURATION_BINDING", "common VAD requires a frozen speech mask"))
        if (
            configuration["chunking"]["mode"] == "one_clip_per_unit"
            and clip["duration_seconds"] > configuration["chunking"]["max_clip_seconds"]
        ):
            findings.append(_finding(f"{where}/duration_seconds", "E_CONFIGURATION_BINDING", "clip exceeds one-unit duration limit"))
    return sort_findings(findings)


def validate_access_license_receipt(
    document: Any,
    *,
    candidate_id: str | None = None,
    store: ArtifactStore | None = None,
    location: str = "access_license_receipt",
    schema_dir: Path | None = None,
) -> list[Finding]:
    findings = _schema_findings(
        document,
        PREPARATION_SCHEMA_FILE,
        location,
        pointer=ACCESS_LICENSE_RECEIPT_POINTER,
        schema_dir=schema_dir,
    )
    if findings or not isinstance(document, Mapping):
        return sort_findings(findings)
    expected = _expected_candidate(candidate_id or document["candidate_id"])
    if expected is None:
        findings.append(_finding(f"{location}/candidate_id", "E_ACCESS_RECEIPT_BINDING", "unknown candidate"))
        return sort_findings(findings)
    for field in ("candidate_id", "official_model_id", "revision", "observed_license", "gated"):
        if document[field] != expected[field]:
            findings.append(_finding(f"{location}/{field}", "E_ACCESS_RECEIPT_BINDING", "receipt identity differs from TASK-032"))
    source_uri = document["source_uri"]
    if (
        not source_uri.startswith("https://huggingface.co/")
        or expected["official_model_id"] not in source_uri
        or expected["revision"] not in source_uri
    ):
        findings.append(_finding(f"{location}/source_uri", "E_ACCESS_RECEIPT_BINDING", "receipt source does not bind model and revision"))
    if expected["gated"]:
        valid_state = (
            (document["access_status"] == "accepted" and document["acceptance_status"] == "owner_accepted")
            or (document["access_status"] == "blocked_access" and document["acceptance_status"] == "not_accepted")
        )
    else:
        valid_state = (
            document["access_status"] == "public_metadata_only"
            and document["acceptance_status"] == "not_required"
        )
    if not valid_state:
        findings.append(
            _finding(f"{location}/access_status", "E_ACCESS_RECEIPT_BINDING", "access and acceptance states are inconsistent")
        )
    if document["metadata_hash"] != document["metadata_ref"].get("content_hash"):
        findings.append(
            _finding(f"{location}/metadata_hash", "E_ACCESS_RECEIPT_BINDING", "metadata hash does not bind metadata ref")
        )
    if store is None:
        findings.append(
            _finding(f"{location}/metadata_ref", "E_ACCESS_RECEIPT_BINDING", "metadata snapshot requires CAS verification")
        )
    else:
        findings.extend(
            _verify_cas_ref(
                document["metadata_ref"],
                store=store,
                location=f"{location}/metadata_ref",
                expected_kind="text",
                expected_media_type="application/json",
                error_code="E_PREPARATION_ARTIFACT",
            )
        )
    return sort_findings(findings)


def validate_model_receipt(
    document: Any,
    *,
    candidate_id: str | None = None,
    access_receipt_ref: Mapping[str, Any] | None = None,
    location: str = "model_receipt",
    schema_dir: Path | None = None,
) -> list[Finding]:
    findings = _schema_findings(
        document,
        PREPARATION_SCHEMA_FILE,
        location,
        pointer=MODEL_RECEIPT_POINTER,
        schema_dir=schema_dir,
    )
    if findings or not isinstance(document, Mapping):
        return sort_findings(findings)
    expected = _expected_candidate(candidate_id or document["candidate_id"])
    if expected is None:
        findings.append(_finding(f"{location}/candidate_id", "E_MODEL_RECEIPT_BINDING", "unknown candidate"))
        return sort_findings(findings)
    for field in ("candidate_id", "official_model_id", "revision"):
        if document[field] != expected[field]:
            findings.append(_finding(f"{location}/{field}", "E_MODEL_RECEIPT_BINDING", "receipt identity differs from TASK-032"))
    source_uri = document["source_uri"]
    if (
        not source_uri.startswith("https://huggingface.co/")
        or expected["official_model_id"] not in source_uri
        or expected["revision"] not in source_uri
    ):
        findings.append(_finding(f"{location}/source_uri", "E_MODEL_RECEIPT_BINDING", "snapshot source does not bind model and revision"))
    if access_receipt_ref is not None and document["access_receipt_hash"] != access_receipt_ref.get("content_hash"):
        findings.append(
            _finding(f"{location}/access_receipt_hash", "E_MODEL_RECEIPT_BINDING", "model receipt does not bind access receipt")
        )
    files = document["files"]
    paths = [item["relative_path"] for item in files]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        findings.append(_finding(f"{location}/files", "E_MODEL_RECEIPT_BINDING", "model file paths must be unique and sorted"))
    for index, path in enumerate(paths):
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or "\\" in path
            or path in (".", "")
            or path != parsed.as_posix()
        ):
            findings.append(
                _finding(f"{location}/files/{index}/relative_path", "E_MODEL_RECEIPT_BINDING", "model file path is not portable")
            )
    if document["file_count"] != len(files):
        findings.append(_finding(f"{location}/file_count", "E_MODEL_RECEIPT_BINDING", "file count does not match inventory"))
    if document["total_bytes"] != sum(item["byte_size"] for item in files):
        findings.append(_finding(f"{location}/total_bytes", "E_MODEL_RECEIPT_BINDING", "byte total does not match inventory"))
    if document["file_manifest_hash"] != canonical_hash(files):
        findings.append(_finding(f"{location}/file_manifest_hash", "E_MODEL_RECEIPT_BINDING", "file inventory hash mismatch"))
    if document["offline_load_status"] == "verified" and not document["download_complete"]:
        findings.append(
            _finding(f"{location}/offline_load_status", "E_MODEL_RECEIPT_BINDING", "offline verification requires a complete snapshot")
        )
    return sort_findings(findings)


def validate_dependency_lock(
    document: Any,
    *,
    store: ArtifactStore | None = None,
    work_cpu_receipt: Mapping[str, Any] | None = None,
    location: str = "dependency_lock",
    schema_dir: Path | None = None,
) -> list[Finding]:
    findings = _schema_findings(
        document,
        PREPARATION_SCHEMA_FILE,
        location,
        pointer=DEPENDENCY_LOCK_POINTER,
        schema_dir=schema_dir,
    )
    if findings or not isinstance(document, Mapping):
        return sort_findings(findings)
    if tuple(document["candidate_order"]) != CANDIDATE_ORDER:
        findings.append(
            _finding(f"{location}/candidate_order", "E_DEPENDENCY_LOCK_BINDING", "candidate order differs from TASK-032")
        )
    for index, (actual, expected) in enumerate(zip(document["candidates"], CANDIDATES, strict=True)):
        where = f"{location}/candidates/{index}"
        if actual["candidate_id"] != expected["candidate_id"] or actual["revision"] != expected["revision"]:
            findings.append(_finding(where, "E_DEPENDENCY_LOCK_BINDING", "dependency candidate identity differs from TASK-032"))
        names = [package["name"].lower().replace("_", "-") for package in actual["direct_packages"]]
        if names != sorted(names) or len(names) != len(set(names)):
            findings.append(_finding(f"{where}/direct_packages", "E_DEPENDENCY_LOCK_BINDING", "direct packages must be unique and sorted"))
        for package_index, package in enumerate(actual["direct_packages"]):
            if package["artifact_hashes"] != sorted(package["artifact_hashes"]):
                findings.append(
                    _finding(
                        f"{where}/direct_packages/{package_index}/artifact_hashes",
                        "E_DEPENDENCY_LOCK_BINDING",
                        "package artifact hashes must be sorted",
                    )
                )
    if store is None:
        findings.append(_finding(f"{location}/lock_file_ref", "E_DEPENDENCY_LOCK_BINDING", "lock file requires CAS verification"))
    else:
        findings.extend(
            _verify_cas_ref(
                document["lock_file_ref"],
                store=store,
                location=f"{location}/lock_file_ref",
                expected_kind="text",
                expected_media_type="text/plain",
                error_code="E_PREPARATION_ARTIFACT",
            )
        )
    if work_cpu_receipt is not None:
        expected_platform = (
            work_cpu_receipt["python"]["version"],
            work_cpu_receipt["host"]["os"],
            work_cpu_receipt["host"]["architecture"],
        )
        actual_platform = (
            document["python_version"],
            document["platform_system"],
            document["platform_architecture"],
        )
        if actual_platform != expected_platform:
            findings.append(_finding(location, "E_DEPENDENCY_LOCK_BINDING", "lock target does not match Work CPU receipt"))
    return sort_findings(findings)


def _slot_findings(
    slot: Mapping[str, Any],
    *,
    store: ArtifactStore | None,
    location: str,
) -> list[Finding]:
    has_ref = "ref" in slot
    if slot["status"] == "pending" and has_ref:
        return [_finding(location, "E_EVIDENCE_SLOT", "pending evidence must not carry a ref")]
    if slot["status"] == "verified" and not has_ref:
        return [_finding(location, "E_EVIDENCE_SLOT", "verified evidence requires a ref")]
    if slot["status"] == "verified":
        if store is None:
            return [_finding(location, "E_EVIDENCE_SLOT", "verified evidence requires CAS verification")]
        return _verify_cas_ref(slot["ref"], store=store, location=f"{location}/ref")
    return []


def expected_preflight_blockers(document: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    blockers: set[tuple[str, str]] = set()
    for candidate in document["candidates"]:
        candidate_id = candidate["candidate_id"]
        if candidate["access_license_receipt_status"] != "verified" or (
            candidate["gated"] and candidate["access_status"] != "accepted"
        ):
            blockers.add(("E_ACCESS_RECEIPT", candidate_id))
        if candidate["model_receipt_status"] != "verified":
            blockers.add(("E_MODEL_RECEIPT_PENDING", candidate_id))
    if (
        any(value != "frozen" for value in document["configuration_status"].values())
        or document["evidence"]["screen_configuration"]["status"] != "verified"
    ):
        blockers.add(("E_CONFIGURATION_PENDING", "screen-configuration"))
    evidence_codes = {
        "primary_pack": ("E_PACK_PENDING", "primary-pack"),
        "reserve_pack": ("E_PACK_PENDING", "reserve-pack"),
        "decision_rule": ("E_DECISION_RULE_PENDING", "decision-rule"),
        "dependency_lock": ("E_DEPENDENCY_LOCK_PENDING", "work-cpu-lock"),
        "work_cpu_environment": ("E_WORK_CPU_EVIDENCE_PENDING", "work-cpu-environment"),
    }
    for name, blocker in evidence_codes.items():
        if document["evidence"][name]["status"] != "verified":
            blockers.add(blocker)
    return tuple(sorted(blockers))


def validate_preflight(
    document: Any,
    *,
    store: ArtifactStore | None = None,
    location: str = "preflight",
    schema_dir: Path | None = None,
) -> list[Finding]:
    findings = _schema_findings(document, PREFLIGHT_SCHEMA_FILE, location, schema_dir=schema_dir)
    if not isinstance(document, Mapping):
        return sort_findings(findings)
    if findings:
        if any(finding.location.startswith(f"{location}/execution_policy") for finding in findings):
            findings.append(_finding(f"{location}/execution_policy", "E_SCREEN_POLICY", "execution policy differs from TASK-032"))
        return sort_findings(findings)

    if tuple(document["candidate_order"]) != CANDIDATE_ORDER:
        findings.append(_finding(f"{location}/candidate_order", "E_CANDIDATE_IDENTITY", "candidate order differs from TASK-032"))
    for index, (actual, expected) in enumerate(zip(document["candidates"], CANDIDATES, strict=True)):
        where = f"{location}/candidates/{index}"
        for field, expected_value in expected.items():
            if actual[field] != expected_value:
                findings.append(_finding(f"{where}/{field}", "E_CANDIDATE_IDENTITY", "candidate identity differs from TASK-032"))
        if actual["candidate_id"] != document["candidate_order"][index]:
            findings.append(_finding(f"{where}/candidate_id", "E_CANDIDATE_IDENTITY", "candidate list/order mismatch"))
        for prefix in ("access_license_receipt", "model_receipt"):
            status = actual[f"{prefix}_status"]
            ref_name = f"{prefix}_ref"
            slot = {"status": status}
            if ref_name in actual:
                slot["ref"] = actual[ref_name]
            findings.extend(_slot_findings(slot, store=store, location=f"{where}/{prefix}"))
        if actual["gated"] and actual["access_status"] == "accepted" and actual["access_license_receipt_status"] != "verified":
            findings.append(_finding(f"{where}/access_status", "E_ACCESS_RECEIPT", "gated acceptance requires a verified receipt"))
        if actual["gated"] and actual["access_status"] == "public_metadata_only":
            findings.append(_finding(f"{where}/access_status", "E_ACCESS_RECEIPT", "gated candidate cannot be treated as public"))

        access_document: Mapping[str, Any] | None = None
        model_document: Mapping[str, Any] | None = None
        if store is not None and actual["access_license_receipt_status"] == "verified":
            access_document, access_findings = _load_json_ref(
                actual["access_license_receipt_ref"],
                store=store,
                location=f"{where}/access_license_receipt_ref",
                error_code="E_PREPARATION_ARTIFACT",
            )
            findings.extend(access_findings)
            if access_document is not None:
                findings.extend(
                    validate_access_license_receipt(
                        access_document,
                        candidate_id=actual["candidate_id"],
                        store=store,
                        location=f"{where}/access_license_receipt",
                    )
                )
                if access_document.get("access_status") != actual["access_status"]:
                    findings.append(
                        _finding(
                            f"{where}/access_status",
                            "E_ACCESS_RECEIPT_BINDING",
                            "preflight access status differs from receipt",
                        )
                    )
        if store is not None and actual["model_receipt_status"] == "verified":
            model_document, model_findings = _load_json_ref(
                actual["model_receipt_ref"],
                store=store,
                location=f"{where}/model_receipt_ref",
                error_code="E_PREPARATION_ARTIFACT",
            )
            findings.extend(model_findings)
            if model_document is not None:
                access_ref = actual.get("access_license_receipt_ref")
                findings.extend(
                    validate_model_receipt(
                        model_document,
                        candidate_id=actual["candidate_id"],
                        access_receipt_ref=access_ref if isinstance(access_ref, Mapping) else None,
                        location=f"{where}/model_receipt",
                    )
                )
                if not model_document.get("download_complete") or model_document.get("offline_load_status") != "verified":
                    findings.append(
                        _finding(
                            f"{where}/model_receipt",
                            "E_MODEL_RECEIPT_BINDING",
                            "verified model slot requires a complete offline-load-verified snapshot",
                        )
                    )
    for name, slot in document["evidence"].items():
        findings.extend(_slot_findings(slot, store=store, location=f"{location}/evidence/{name}"))

    evidence_documents: dict[str, Mapping[str, Any]] = {}
    if store is not None:
        for name, slot in document["evidence"].items():
            if slot["status"] != "verified":
                continue
            loaded, load_findings = _load_json_ref(
                slot["ref"],
                store=store,
                location=f"{location}/evidence/{name}/ref",
                error_code="E_PREPARATION_ARTIFACT",
            )
            findings.extend(load_findings)
            if loaded is not None:
                evidence_documents[name] = loaded

    configuration = evidence_documents.get("screen_configuration")
    configuration_valid = False
    if configuration is not None:
        configuration_findings = validate_screen_configuration(
            configuration, location=f"{location}/screen_configuration"
        )
        findings.extend(configuration_findings)
        configuration_valid = not configuration_findings
        if configuration_valid and (configuration.get("status") != "frozen" or any(
            value != "frozen" for value in document["configuration_status"].values()
        )):
            findings.append(
                _finding(
                    f"{location}/configuration_status",
                    "E_CONFIGURATION_BINDING",
                    "verified screen configuration and status flags must all be frozen",
                )
            )

    primary = evidence_documents.get("primary_pack")
    reserve = evidence_documents.get("reserve_pack")
    packs_valid = False
    if primary is not None and reserve is not None:
        pack_findings = validate_pack_pair(primary, reserve, store=store, location=f"{location}/packs")
        findings.extend(pack_findings)
        packs_valid = not pack_findings
        if configuration_valid and packs_valid:
            findings.extend(
                validate_configuration_pack_binding(
                    configuration,
                    primary,
                    reserve,
                    location=f"{location}/configuration_pack_binding",
                )
            )

    decision_rule = evidence_documents.get("decision_rule")
    if decision_rule is not None:
        primary_slot = document["evidence"]["primary_pack"]
        reserve_slot = document["evidence"]["reserve_pack"]
        primary_ref = primary_slot.get("ref") if primary_slot["status"] == "verified" else None
        reserve_ref = reserve_slot.get("ref") if reserve_slot["status"] == "verified" else None
        findings.extend(
            validate_decision_rule(
                decision_rule,
                primary_pack_ref=primary_ref if isinstance(primary_ref, Mapping) else None,
                reserve_pack_ref=reserve_ref if isinstance(reserve_ref, Mapping) else None,
                location=f"{location}/decision_rule",
            )
        )

    work_cpu = evidence_documents.get("work_cpu_environment")
    work_cpu_valid = False
    if work_cpu is not None:
        work_cpu_findings = validate_work_cpu_receipt(work_cpu, location=f"{location}/work_cpu_environment")
        findings.extend(work_cpu_findings)
        work_cpu_valid = not work_cpu_findings

    dependency_lock = evidence_documents.get("dependency_lock")
    if dependency_lock is not None:
        findings.extend(
            validate_dependency_lock(
                dependency_lock,
                store=store,
                work_cpu_receipt=work_cpu if work_cpu_valid else None,
                location=f"{location}/dependency_lock",
            )
        )

    declared = tuple(sorted((item["code"], item["subject"]) for item in document["blockers"]))
    expected = expected_preflight_blockers(document)
    if declared != expected:
        findings.append(_finding(f"{location}/blockers", "E_PREFLIGHT_STATE", "declared blockers do not equal recomputed blockers"))
    # Typed preparation evidence is validated above, but candidate-run adapters are
    # intentionally absent.  Therefore no collection of preparation receipts can
    # authorize the first candidate output in this slice.
    if document["status"] != "blocked":
        findings.append(
            _finding(
                f"{location}/status",
                "E_PREFLIGHT_STATE",
                "preflight has no candidate-run authorization",
            )
        )
    return sort_findings(findings)


def readiness_findings(document: Any, *, store: ArtifactStore | None = None) -> list[Finding]:
    validation = validate_preflight(document, store=store)
    if validation or not isinstance(document, Mapping):
        return validation
    blockers = [
        _finding(f"preflight/blockers/{index}", code, f"not ready: {subject}")
        for index, (code, subject) in enumerate(expected_preflight_blockers(document))
    ]
    if not blockers:
        blockers.append(
            _finding(
                "preflight/candidate_output_authorization",
                "E_PREFLIGHT_STATE",
                "candidate-output authorization is not implemented in this slice",
            )
        )
    return blockers


def validate_work_cpu_receipt(
    document: Any,
    *,
    location: str = "work_cpu_receipt",
    schema_dir: Path | None = None,
) -> list[Finding]:
    return sort_findings(
        _schema_findings(
            document,
            PREFLIGHT_SCHEMA_FILE,
            location,
            pointer=WORK_CPU_RECEIPT_POINTER,
            schema_dir=schema_dir,
        )
    )


def load_pack_ref(
    ref: Mapping[str, Any],
    *,
    store: ArtifactStore,
    location: str,
) -> tuple[Mapping[str, Any] | None, list[Finding]]:
    """Public helper used by the fixture and later screening spine."""

    return _load_json_ref(ref, store=store, location=location)


def ref_identity(ref: Mapping[str, Any]) -> tuple[Any, ...]:
    """Stable comparison key for tests and later cross-reference checks."""

    return _ref_key(ref)


def validate_recovery_fixture_report(
    document: Any,
    *,
    location: str = "recovery_fixture",
) -> list[Finding]:
    """Validate the exact projection emitted by the synthetic resume harness."""

    findings: list[Finding] = []
    root_keys = {
        "schema_version",
        "kind",
        "candidate_order",
        "candidates",
        "candidate_output_generated",
        "target_windows_compatibility",
    }
    candidate_keys = {
        "candidate_id",
        "interruption_count",
        "ordered_units",
        "unit_001_attempt_id_before",
        "unit_001_attempt_id_after",
        "unit_001_cache_status_after",
        "unit_002_attempt_statuses",
        "unit_002_completed_attempt_id",
    }
    if not isinstance(document, Mapping) or set(document) != root_keys:
        return [_finding(location, "E_RESUME_EVIDENCE", "recovery fixture root is not the closed shape")]
    expected_root = {
        "schema_version": "1.0.0",
        "kind": "AsrScreenSyntheticRecoveryFixture/v1",
        "candidate_order": list(CANDIDATE_ORDER),
        "candidate_output_generated": False,
        "target_windows_compatibility": "not_evaluated",
    }
    for field, expected in expected_root.items():
        if document.get(field) != expected:
            findings.append(_finding(f"{location}/{field}", "E_RESUME_EVIDENCE", "recovery fixture root invariant differs"))
    candidates = document.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or len(candidates) != 3:
        findings.append(_finding(f"{location}/candidates", "E_RESUME_EVIDENCE", "exactly three candidate records are required"))
        return sort_findings(findings)
    for index, (candidate, expected_id) in enumerate(zip(candidates, CANDIDATE_ORDER, strict=True)):
        where = f"{location}/candidates/{index}"
        if not isinstance(candidate, Mapping) or set(candidate) != candidate_keys:
            findings.append(_finding(where, "E_RESUME_EVIDENCE", "candidate recovery record is not the closed shape"))
            continue
        checks = (
            (candidate["candidate_id"] == expected_id, "candidate_id"),
            (candidate["interruption_count"] == 1, "interruption_count"),
            (candidate["ordered_units"] == ["unit-001", "unit-002"], "ordered_units"),
            (
                candidate["unit_001_attempt_id_before"] == candidate["unit_001_attempt_id_after"],
                "unit_001_attempt_id_after",
            ),
            (candidate["unit_001_cache_status_after"] == "hit", "unit_001_cache_status_after"),
            (
                candidate["unit_002_attempt_statuses"] == ["interrupted", "completed"],
                "unit_002_attempt_statuses",
            ),
            (candidate["unit_002_completed_attempt_id"] == "a0002", "unit_002_completed_attempt_id"),
        )
        for passed, field in checks:
            if not passed:
                findings.append(_finding(f"{where}/{field}", "E_RESUME_EVIDENCE", "controlled-resume invariant differs"))
    return sort_findings(findings)
