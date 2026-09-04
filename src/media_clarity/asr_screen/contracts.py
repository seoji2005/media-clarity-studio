"""TASK-032 frozen-pack, decision-rule, and preflight contracts.

This first slice is deliberately stdlib-only.  It validates immutable screening
inputs and honest preparation blockers; it does not download a model, transcribe
audio, or claim target Windows/GPU compatibility.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from media_clarity.artifact_store import (
    ArtifactStore,
    ContractViolation,
    cas_relative_uri,
    digest_of,
)
from media_clarity.job_runtime import canonical_json_bytes
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
SCHEMA_FILES = (
    COMMON_SCHEMA_FILE,
    PREFLIGHT_SCHEMA_FILE,
    PACK_SCHEMA_FILE,
    DECISION_RULE_SCHEMA_FILE,
)
WORK_CPU_RECEIPT_POINTER = "/$defs/work_cpu_receipt"

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
        return [_finding(location, "E_PACK_ARTIFACT", "content hash cannot form a canonical CAS URI")]
    if ref.get("uri") != expected_uri:
        findings.append(_finding(f"{location}/uri", "E_PACK_ARTIFACT", "not a canonical CAS URI"))
        return sort_findings(findings)
    cursor = store.project_root
    for segment in Path(expected_uri).parts:
        cursor /= segment
        if cursor.is_symlink():
            findings.append(_finding(f"{location}/uri", "E_PACK_ARTIFACT", "CAS path contains a symbolic-link alias"))
            return sort_findings(findings)
    try:
        store.verify_ref(ref, location)
    except (ContractViolation, KeyError, TypeError) as error:
        findings.append(_finding(location, "E_PACK_ARTIFACT", str(error)))
        return sort_findings(findings)
    if expected_kind is not None and ref.get("kind") != expected_kind:
        findings.append(_finding(f"{location}/kind", "E_PACK_ARTIFACT", f"kind must be {expected_kind}"))
    if expected_media_type is not None and ref.get("media_type") != expected_media_type:
        findings.append(
            _finding(f"{location}/media_type", "E_PACK_ARTIFACT", f"media type must be {expected_media_type}")
        )
    return sort_findings(findings)


def _load_json_ref(
    ref: Any,
    *,
    store: ArtifactStore,
    location: str,
) -> tuple[Mapping[str, Any] | None, list[Finding]]:
    findings = _verify_cas_ref(
        ref,
        store=store,
        location=location,
        expected_kind="text",
        expected_media_type="application/json",
    )
    if findings or not isinstance(ref, Mapping):
        return None, findings
    try:
        payload = store.absolute(ref["uri"], f"{location}/uri").read_bytes()
        document = loads_strict(payload.decode("utf-8"))
    except (ContractViolation, JsonInputError, UnicodeDecodeError, OSError, KeyError, TypeError):
        return None, [_finding(location, "E_PACK_ARTIFACT", "JSON CAS evidence cannot be read strictly")]
    if not isinstance(document, Mapping):
        return None, [_finding(location, "E_PACK_ARTIFACT", "JSON CAS evidence root must be an object")]
    try:
        if payload != canonical_json_bytes(document):
            return None, [_finding(location, "E_PACK_ARTIFACT", "JSON CAS evidence is not canonical")]
    except (TypeError, ValueError, UnicodeEncodeError):
        return None, [_finding(location, "E_PACK_ARTIFACT", "JSON CAS evidence cannot be canonicalized")]
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
    if any(value != "frozen" for value in document["configuration_status"].values()):
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

    for name, slot in document["evidence"].items():
        findings.extend(_slot_findings(slot, store=store, location=f"{location}/evidence/{name}"))

    declared = tuple(sorted((item["code"], item["subject"]) for item in document["blockers"]))
    expected = expected_preflight_blockers(document)
    if declared != expected:
        findings.append(_finding(f"{location}/blockers", "E_PREFLIGHT_STATE", "declared blockers do not equal recomputed blockers"))
    # This slice validates preparation evidence but intentionally has no model/file,
    # dependency, or candidate-run adapter validator.  It therefore cannot authorize
    # the first candidate output even if a caller forges all slots to "verified".
    if document["status"] != "blocked":
        findings.append(
            _finding(
                f"{location}/status",
                "E_PREFLIGHT_STATE",
                "first-slice preflight cannot authorize candidate output",
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
