"""TASK-031 manifest/report evidence spine.

이 모듈은 Windows/GPU 측정값을 만들지 않는다. 닫힌
``CalibrationRunManifest/v1``·``CalibrationReport/v1`` 문서를 검증하고,
CAS에 저장된 manifest와 measurement runtime projection을 실제 TASK-028
attempt evidence에 연결한다.

현재 slice는 timing/materialization, NVML, correction/interruption 의미와
최종 producer ancestry를 아직 검증하지 않는다. 그러므로 ``completed`` 주장은
항상 fail-closed다. 정직한 ``incomplete`` 문서는 누락 축을 명시해야 한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from media_clarity.artifact_store import (
    ArtifactStore,
    ContractViolation,
    cas_relative_uri,
    digest_of,
)
from media_clarity.calibration.evidence import (
    MEASUREMENT_PROJECTION_FIELDS,
    STAGE_SPEC_SCHEMA_FILE,
    validate_measurement_runtime_evidence,
    validate_measurement_runtime_evidence_set,
)
from media_clarity.job_runtime import (
    ARTIFACT_REF_POINTER,
    JOB_SCHEMA_FILE,
    canonical_hash,
    canonical_json_bytes,
)
from media_clarity.schema_core import (
    COMMON_SCHEMA_FILE,
    DEFAULT_SCHEMA_DIR,
    SCHEMA_VERSION,
    Finding,
    JsonInputError,
    SchemaSet,
    SchemaValidator,
    loads_strict,
    sort_findings,
)


RUN_MANIFEST_SCHEMA_FILE = "calibration-run-manifest-v1.schema.json"
PERFORMANCE_MEASUREMENT_SCHEMA_FILE = "calibration-performance-measurement-v1.schema.json"
CALIBRATION_REPORT_SCHEMA_FILE = "calibration-report-v1.schema.json"
SPINE_SCHEMA_FILES = (
    COMMON_SCHEMA_FILE,
    JOB_SCHEMA_FILE,
    STAGE_SPEC_SCHEMA_FILE,
    RUN_MANIFEST_SCHEMA_FILE,
    PERFORMANCE_MEASUREMENT_SCHEMA_FILE,
    CALIBRATION_REPORT_SCHEMA_FILE,
)

MATRIX_CELL_ORDER = (
    "asr-faster-whisper",
    "asr-qwen3-asr",
    "mt-madlad",
    "mt-qwen3.5",
    "e2e-faster-whisper__madlad",
    "e2e-faster-whisper__qwen3.5",
    "e2e-qwen3-asr__madlad",
    "e2e-qwen3-asr__qwen3.5",
)

_MODEL_REVISIONS = {
    "Systran/faster-whisper-large-v3": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
    "Qwen/Qwen3-ASR-1.7B": "7278e1e70fe206f11671096ffdd38061171dd6e5",
    "google/madlad400-3b-mt": "fa184c675da0b5c9e1c8694fccd4e12e2d422094",
    "Qwen/Qwen3.5-4B": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
}

_CELL_SPECS = {
    "asr-faster-whisper": (
        "independent_asr",
        (("asr", "Systran/faster-whisper-large-v3"),),
    ),
    "asr-qwen3-asr": (
        "independent_asr",
        (("asr", "Qwen/Qwen3-ASR-1.7B"),),
    ),
    "mt-madlad": (
        "independent_mt",
        (("mt", "google/madlad400-3b-mt"),),
    ),
    "mt-qwen3.5": (
        "independent_mt",
        (("mt", "Qwen/Qwen3.5-4B"),),
    ),
    "e2e-faster-whisper__madlad": (
        "end_to_end",
        (
            ("asr", "Systran/faster-whisper-large-v3"),
            ("mt", "google/madlad400-3b-mt"),
        ),
    ),
    "e2e-faster-whisper__qwen3.5": (
        "end_to_end",
        (
            ("asr", "Systran/faster-whisper-large-v3"),
            ("mt", "Qwen/Qwen3.5-4B"),
        ),
    ),
    "e2e-qwen3-asr__madlad": (
        "end_to_end",
        (
            ("asr", "Qwen/Qwen3-ASR-1.7B"),
            ("mt", "google/madlad400-3b-mt"),
        ),
    ),
    "e2e-qwen3-asr__qwen3.5": (
        "end_to_end",
        (
            ("asr", "Qwen/Qwen3-ASR-1.7B"),
            ("mt", "Qwen/Qwen3.5-4B"),
        ),
    ),
}

_PARALLEL_STAGE_FIELDS = (
    "unit_ids",
    "stage_spec_digests",
    "stage_spec_document_refs",
    "attempt_ids",
    "cache_keys",
    "input_ref_tuples",
    "output_ref_tuples",
    "raw_output_refs",
    "runtime_identities",
)

_MEASUREMENT_LINK_FIELDS = tuple(
    field
    for field in MEASUREMENT_PROJECTION_FIELDS
    if field not in {"measurement_id", "run_id", "matrix_cell_id", "candidate_stage_id", "adapter_role"}
)


def spine_schema_set(directory: Path = DEFAULT_SCHEMA_DIR) -> SchemaSet:
    """manifest/report spine이 사용하는 실제 schema 묶음."""

    return SchemaSet(directory, SPINE_SCHEMA_FILES)


def _finding(location: str, code: str, message: str) -> Finding:
    return Finding(location=location, code=code, message=message)


def _ref_identity(ref: Any) -> tuple[str, str] | None:
    if not isinstance(ref, Mapping):
        return None
    uri = ref.get("uri")
    content_hash = ref.get("content_hash")
    if not isinstance(uri, str) or not isinstance(content_hash, str):
        return None
    return uri, content_hash


def _verify_cas_ref(
    ref: Any,
    *,
    store: ArtifactStore,
    validator: SchemaValidator,
    location: str,
    findings: list[Finding],
) -> bool:
    schema_findings = validator.validate(
        ref, COMMON_SCHEMA_FILE, location, ARTIFACT_REF_POINTER
    )
    findings.extend(schema_findings)
    if schema_findings or not isinstance(ref, Mapping):
        return False
    try:
        expected_uri = cas_relative_uri(digest_of(ref["content_hash"]))
    except (ContractViolation, KeyError, TypeError):
        findings.append(
            _finding(location, "E_CALIBRATION_ARTIFACT", "content hash로 canonical CAS URI를 만들 수 없다")
        )
        return False
    if ref.get("uri") != expected_uri:
        findings.append(
            _finding(f"{location}/uri", "E_CALIBRATION_ARTIFACT", "canonical CAS URI가 아니다")
        )
        return False
    cursor = store.project_root
    for segment in Path(expected_uri).parts:
        cursor /= segment
        if cursor.is_symlink():
            findings.append(
                _finding(f"{location}/uri", "E_CALIBRATION_ARTIFACT", "CAS 경로에 symbolic-link alias가 있다")
            )
            return False
    try:
        store.verify_ref(ref, location)
    except (ContractViolation, KeyError, TypeError) as error:
        findings.append(_finding(location, "E_CALIBRATION_ARTIFACT", str(error)))
        return False
    return True


def _load_json_ref(
    ref: Any,
    *,
    store: ArtifactStore,
    validator: SchemaValidator,
    location: str,
    findings: list[Finding],
) -> Mapping[str, Any] | None:
    if not _verify_cas_ref(
        ref,
        store=store,
        validator=validator,
        location=location,
        findings=findings,
    ):
        return None
    assert isinstance(ref, Mapping)
    if ref.get("kind") != "text" or ref.get("media_type") != "application/json":
        findings.append(
            _finding(location, "E_CALIBRATION_ARTIFACT", "JSON evidence는 kind=text, media_type=application/json이어야 한다")
        )
        return None
    try:
        payload = store.absolute(ref["uri"], f"{location}/uri").read_bytes()
        document = loads_strict(payload.decode("utf-8"))
    except (ContractViolation, UnicodeDecodeError, JsonInputError, KeyError, TypeError):
        findings.append(
            _finding(location, "E_CALIBRATION_ARTIFACT", "JSON evidence를 안전하게 읽거나 파싱할 수 없다")
        )
        return None
    except OSError:
        findings.append(_finding(location, "E_CALIBRATION_ARTIFACT", "JSON evidence 파일을 읽을 수 없다"))
        return None
    if not isinstance(document, Mapping):
        findings.append(_finding(location, "E_CALIBRATION_ARTIFACT", "JSON evidence root가 객체가 아니다"))
        return None
    try:
        canonical_payload = canonical_json_bytes(document)
    except (UnicodeEncodeError, TypeError, ValueError):
        findings.append(
            _finding(location, "E_CALIBRATION_ARTIFACT", "JSON evidence를 canonical serialization으로 재직렬화할 수 없다")
        )
        return None
    if payload != canonical_payload:
        findings.append(_finding(location, "E_CALIBRATION_ARTIFACT", "JSON evidence가 canonical serialization이 아니다"))
        return None
    return document


def _expected_measurement_projection(
    manifest: Mapping[str, Any], stage: Mapping[str, Any]
) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "measurement_id": stage["measurement_id"],
        "run_id": manifest["run_id"],
        "matrix_cell_id": manifest["matrix_cell_id"],
        "candidate_stage_id": stage["candidate_stage_id"],
        "adapter_role": stage["adapter_role"],
    }
    for field in _MEASUREMENT_LINK_FIELDS:
        if field == "attempt_record_mode":
            projection[field] = manifest["attempt_record_mode"]
        elif field == "pipeline_id":
            projection[field] = manifest["pipeline_id"]
        elif field == "environment_runtime_version":
            projection[field] = manifest["environment_runtime_version"]
        elif field == "environment_schema_version":
            projection[field] = manifest["environment_schema_version"]
        else:
            projection[field] = stage[field]
    return projection


def _candidate_chain_hash(stages: Sequence[Mapping[str, Any]]) -> str:
    chain = [
        {
            "adapter_role": stage["adapter_role"],
            **stage["candidate_identity"],
        }
        for stage in stages
    ]
    return canonical_hash(chain)


def _candidate_config_hash(stages: Sequence[Mapping[str, Any]]) -> str:
    return canonical_hash(
        [
            {
                "adapter_role": stage["adapter_role"],
                "config_hash": stage["candidate_identity"]["config_hash"],
            }
            for stage in stages
        ]
    )


def validate_calibration_run_manifest(
    manifest: Any,
    project_root: Path,
    location: str = "manifest",
    schemas: SchemaSet | None = None,
) -> list[Finding]:
    """한 ``CalibrationRunManifest/v1``과 연결 measurement projection을 검증한다."""

    schema_set = schemas or spine_schema_set()
    validator = SchemaValidator(schema_set)
    findings = validator.validate(manifest, RUN_MANIFEST_SCHEMA_FILE, location)
    if findings or not isinstance(manifest, Mapping):
        return sort_findings(findings)

    store = ArtifactStore(Path(project_root))
    cell_id = manifest["matrix_cell_id"]
    expected_run_kind, expected_candidates = _CELL_SPECS[cell_id]
    if manifest["run_kind"] != expected_run_kind:
        findings.append(
            _finding(f"{location}/run_kind", "E_MANIFEST_IDENTITY", "matrix cell의 고정 run_kind와 다르다")
        )

    stages = manifest["candidate_stages"]
    actual_candidates = tuple(
        (stage["adapter_role"], stage["candidate_identity"]["official_model_id"])
        for stage in stages
    )
    if actual_candidates != expected_candidates:
        findings.append(
            _finding(f"{location}/candidate_stages", "E_MANIFEST_IDENTITY", "matrix cell의 ordered role/model chain과 다르다")
        )
    for index, stage in enumerate(stages):
        stage_location = f"{location}/candidate_stages/{index}"
        identity = stage["candidate_identity"]
        expected_revision = _MODEL_REVISIONS.get(identity["official_model_id"])
        if identity["model_revision"] != expected_revision:
            findings.append(
                _finding(f"{stage_location}/candidate_identity/model_revision", "E_MANIFEST_IDENTITY", "TASK-031 frozen model revision과 다르다")
            )
        lengths = {len(stage[field]) for field in _PARALLEL_STAGE_FIELDS}
        if lengths != {len(stage["unit_ids"])}:
            findings.append(
                _finding(stage_location, "E_MANIFEST_IDENTITY", "ordered candidate-stage unit 배열 길이가 다르다")
            )
            continue
        _verify_cas_ref(
            stage["aggregate_normalized_output_ref"],
            store=store,
            validator=validator,
            location=f"{stage_location}/aggregate_normalized_output_ref",
            findings=findings,
        )
        measurement = _load_json_ref(
            stage["performance_measurement_ref"],
            store=store,
            validator=validator,
            location=f"{stage_location}/performance_measurement_ref",
            findings=findings,
        )
        if measurement is None:
            continue
        measurement_schema_findings = validator.validate(
            measurement,
            PERFORMANCE_MEASUREMENT_SCHEMA_FILE,
            f"{stage_location}/performance_measurement_ref",
        )
        findings.extend(measurement_schema_findings)
        if measurement_schema_findings:
            continue
        if measurement["incomplete_reasons"] != [
            "environment",
            "model_snapshot",
            "materialization",
            "timing",
            "nvml",
        ]:
            findings.append(
                _finding(
                    f"{stage_location}/performance_measurement_ref/incomplete_reasons",
                    "E_CALIBRATION_STATUS",
                    "runtime-only measurement의 미검증 축 목록과 다르다",
                )
            )
        expected_projection = _expected_measurement_projection(manifest, stage)
        for field, expected in expected_projection.items():
            if measurement.get(field) != expected:
                findings.append(
                    _finding(
                        f"{stage_location}/performance_measurement_ref/{field}",
                        "E_EVIDENCE_LINK",
                        "manifest와 measurement projection이 exact equality가 아니다",
                    )
                )
        if measurement.get("aggregate_normalized_output_ref") != stage["aggregate_normalized_output_ref"]:
            findings.append(
                _finding(
                    f"{stage_location}/performance_measurement_ref/aggregate_normalized_output_ref",
                    "E_EVIDENCE_LINK",
                    "aggregate normalized output ref가 manifest와 다르다",
                )
            )
        if measurement.get("candidate_identity") != stage["candidate_identity"]:
            findings.append(
                _finding(
                    f"{stage_location}/performance_measurement_ref/candidate_identity",
                    "E_EVIDENCE_LINK",
                    "candidate identity가 manifest stage와 다르다",
                )
            )
        if measurement.get("candidate_chain_hash") != manifest["candidate_chain_hash"]:
            findings.append(
                _finding(
                    f"{stage_location}/performance_measurement_ref/candidate_chain_hash",
                    "E_EVIDENCE_LINK",
                    "candidate chain hash가 manifest와 다르다",
                )
            )
        if measurement.get("environment_ref") != manifest["environment_ref"]:
            findings.append(
                _finding(
                    f"{stage_location}/performance_measurement_ref/environment_ref",
                    "E_EVIDENCE_LINK",
                    "environment ref가 manifest와 다르다",
                )
            )
        findings.extend(
            validate_measurement_runtime_evidence(
                measurement,
                project_root,
                f"{stage_location}/performance_measurement_ref",
                schema_set,
            )
        )

    if manifest["candidate_chain_hash"] != _candidate_chain_hash(stages):
        findings.append(
            _finding(f"{location}/candidate_chain_hash", "E_MANIFEST_IDENTITY", "ordered candidate identity/config hash 재계산값과 다르다")
        )
    if manifest["candidate_config_hash"] != _candidate_config_hash(stages):
        findings.append(
            _finding(f"{location}/candidate_config_hash", "E_MANIFEST_IDENTITY", "ordered candidate config hash 재계산값과 다르다")
        )

    seen_stage_ids: set[str] = set()
    seen_measurement_ids: set[str] = set()
    seen_measurement_refs: set[tuple[str, str]] = set()
    for index, stage in enumerate(stages):
        stage_id = stage["candidate_stage_id"]
        measurement_id = stage["measurement_id"]
        ref_identity = _ref_identity(stage["performance_measurement_ref"])
        if stage_id in seen_stage_ids:
            findings.append(_finding(f"{location}/candidate_stages/{index}/candidate_stage_id", "E_MEASUREMENT_REUSE", "candidate_stage_id가 run 안에서 재사용됐다"))
        seen_stage_ids.add(stage_id)
        if measurement_id in seen_measurement_ids:
            findings.append(_finding(f"{location}/candidate_stages/{index}/measurement_id", "E_MEASUREMENT_REUSE", "measurement_id가 run 안에서 재사용됐다"))
        seen_measurement_ids.add(measurement_id)
        if ref_identity is not None:
            if ref_identity in seen_measurement_refs:
                findings.append(_finding(f"{location}/candidate_stages/{index}/performance_measurement_ref", "E_MEASUREMENT_REUSE", "measurement ref가 run 안에서 재사용됐다"))
            seen_measurement_refs.add(ref_identity)

    for field in ("environment_ref", "pack_manifest_ref", "pack_audio_ref"):
        _verify_cas_ref(
            manifest[field],
            store=store,
            validator=validator,
            location=f"{location}/{field}",
            findings=findings,
        )
    if manifest["pack_hash"] != manifest["pack_manifest_ref"].get("content_hash"):
        findings.append(
            _finding(
                f"{location}/pack_hash",
                "E_EVIDENCE_LINK",
                "content-locked pack manifest digest와 다르다",
            )
        )
    for index, ref in enumerate(manifest["correction_record_refs"]):
        _verify_cas_ref(
            ref,
            store=store,
            validator=validator,
            location=f"{location}/correction_record_refs/{index}",
            findings=findings,
        )

    reasons = set(manifest["incomplete_reasons"])
    expected_corrections = 2 if expected_run_kind == "end_to_end" else 1
    if len(manifest["correction_record_refs"]) not in {0, expected_corrections}:
        findings.append(_finding(f"{location}/correction_record_refs", "E_EVIDENCE_LINK", "run kind의 correction record cardinality와 다르다"))
    if len(manifest["correction_record_refs"]) != expected_corrections and "corrections" not in reasons:
        findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "누락 correction evidence 사유가 없다"))

    final_refs = manifest.get("final_pipeline_output_refs")
    interruption_ref = manifest.get("interruption_record_ref")
    if expected_run_kind == "end_to_end":
        if final_refs is None:
            if "final_outputs" not in reasons:
                findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "누락 final outputs 사유가 없다"))
        elif len(final_refs) != 4:
            findings.append(_finding(f"{location}/final_pipeline_output_refs", "E_FINAL_OUTPUTS", "end-to-end final output은 정확히 네 원소여야 한다"))
        else:
            for index, ref in enumerate(final_refs):
                _verify_cas_ref(
                    ref,
                    store=store,
                    validator=validator,
                    location=f"{location}/final_pipeline_output_refs/{index}",
                    findings=findings,
                )
        if interruption_ref is None:
            if "interruption" not in reasons:
                findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "누락 interruption evidence 사유가 없다"))
        else:
            _verify_cas_ref(
                interruption_ref,
                store=store,
                validator=validator,
                location=f"{location}/interruption_record_ref",
                findings=findings,
            )
    else:
        if final_refs is not None:
            findings.append(_finding(f"{location}/final_pipeline_output_refs", "E_FINAL_OUTPUTS", "independent run은 final_pipeline_output_refs를 갖지 않는다"))
        if interruption_ref is not None:
            findings.append(_finding(f"{location}/interruption_record_ref", "E_EVIDENCE_LINK", "independent run은 interruption record를 갖지 않는다"))

    if manifest["status"] == "completed":
        findings.append(
            _finding(
                f"{location}/status",
                "E_CALIBRATION_STATUS",
                "timing/NVML/correction/interruption/final ancestry validator 전에는 completed를 주장할 수 없다",
            )
        )
    elif not manifest["incomplete_reasons"]:
        findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "비-completed manifest는 미완료 사유를 가져야 한다"))
    for required_pending in (
        "environment",
        "model_snapshot",
        "materialization",
        "timing",
        "nvml",
    ):
        if required_pending not in reasons:
            findings.append(
                _finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", f"현재 slice의 미검증 축 {required_pending}를 명시해야 한다")
            )

    return sort_findings(findings)


def validate_calibration_report(
    report: Any,
    project_root: Path,
    location: str = "report",
    schemas: SchemaSet | None = None,
) -> list[Finding]:
    """report→manifest→measurement evidence 링크와 전역 소유권을 검증한다."""

    schema_set = schemas or spine_schema_set()
    validator = SchemaValidator(schema_set)
    findings = validator.validate(report, CALIBRATION_REPORT_SCHEMA_FILE, location)
    if findings or not isinstance(report, Mapping):
        return sort_findings(findings)

    store = ArtifactStore(Path(project_root))
    manifests: list[Mapping[str, Any]] = []
    measurements: list[Mapping[str, Any]] = []
    seen_run_ids: set[str] = set()
    seen_cells: set[str] = set()
    seen_manifest_refs: set[tuple[str, str]] = set()
    seen_measurement_ids: set[str] = set()
    seen_measurement_refs: set[tuple[str, str]] = set()
    seen_stage_ids: set[str] = set()
    observed_cells: list[str] = []

    for index, entry in enumerate(report["runs"]):
        entry_location = f"{location}/runs/{index}"
        run_id = entry["run_id"]
        cell_id = entry["matrix_cell_id"]
        observed_cells.append(cell_id)
        if run_id in seen_run_ids:
            findings.append(_finding(f"{entry_location}/run_id", "E_MATRIX_COVERAGE", "run_id가 재사용됐다"))
        seen_run_ids.add(run_id)
        if cell_id in seen_cells:
            findings.append(_finding(f"{entry_location}/matrix_cell_id", "E_MATRIX_COVERAGE", "matrix cell이 재사용됐다"))
        seen_cells.add(cell_id)
        manifest_identity = _ref_identity(entry["manifest_ref"])
        if manifest_identity is not None:
            if manifest_identity in seen_manifest_refs:
                findings.append(_finding(f"{entry_location}/manifest_ref", "E_MATRIX_COVERAGE", "manifest ref가 재사용됐다"))
            seen_manifest_refs.add(manifest_identity)

        manifest = _load_json_ref(
            entry["manifest_ref"],
            store=store,
            validator=validator,
            location=f"{entry_location}/manifest_ref",
            findings=findings,
        )
        if manifest is None:
            continue
        manifests.append(manifest)
        manifest_schema_findings = validator.validate(
            manifest,
            RUN_MANIFEST_SCHEMA_FILE,
            f"{entry_location}/manifest_ref",
        )
        if manifest_schema_findings:
            findings.extend(manifest_schema_findings)
            continue
        findings.extend(
            validate_calibration_run_manifest(
                manifest,
                project_root,
                f"{entry_location}/manifest_ref",
                schema_set,
            )
        )
        if manifest.get("run_id") != run_id or manifest.get("matrix_cell_id") != cell_id:
            findings.append(_finding(entry_location, "E_EVIDENCE_LINK", "report entry와 manifest run/cell identity가 다르다"))
        if manifest.get("pack_hash") != report["pack_hash"]:
            findings.append(_finding(f"{entry_location}/manifest_ref/pack_hash", "E_EVIDENCE_LINK", "report pack hash와 다르다"))
        stages = manifest.get("candidate_stages")
        if not isinstance(stages, list):
            continue
        expected_ids = [stage.get("measurement_id") for stage in stages]
        expected_refs = [stage.get("performance_measurement_ref") for stage in stages]
        if entry["measurement_ids"] != expected_ids:
            findings.append(_finding(f"{entry_location}/measurement_ids", "E_EVIDENCE_LINK", "manifest measurement ID projection과 다르다"))
        if entry["performance_measurement_refs"] != expected_refs:
            findings.append(_finding(f"{entry_location}/performance_measurement_refs", "E_EVIDENCE_LINK", "manifest measurement ref projection과 다르다"))
        for stage_index, stage in enumerate(stages):
            measurement_id = stage.get("measurement_id")
            candidate_stage_id = stage.get("candidate_stage_id")
            ref = stage.get("performance_measurement_ref")
            if isinstance(measurement_id, str):
                if measurement_id in seen_measurement_ids:
                    findings.append(_finding(f"{entry_location}/measurement_ids/{stage_index}", "E_MEASUREMENT_REUSE", "measurement_id가 report에서 재사용됐다"))
                seen_measurement_ids.add(measurement_id)
            if isinstance(candidate_stage_id, str):
                if candidate_stage_id in seen_stage_ids:
                    findings.append(_finding(f"{entry_location}/manifest_ref/candidate_stages/{stage_index}", "E_MEASUREMENT_REUSE", "candidate_stage_id가 report에서 재사용됐다"))
                seen_stage_ids.add(candidate_stage_id)
            ref_identity = _ref_identity(ref)
            if ref_identity is not None:
                if ref_identity in seen_measurement_refs:
                    findings.append(_finding(f"{entry_location}/performance_measurement_refs/{stage_index}", "E_MEASUREMENT_REUSE", "measurement ref가 report에서 재사용됐다"))
                seen_measurement_refs.add(ref_identity)
            measurement = _load_json_ref(
                ref,
                store=store,
                validator=validator,
                location=f"{entry_location}/performance_measurement_refs/{stage_index}",
                findings=findings,
            )
            if measurement is not None:
                measurements.append(measurement)

    order_index = {cell: index for index, cell in enumerate(MATRIX_CELL_ORDER)}
    if observed_cells != sorted(observed_cells, key=order_index.__getitem__):
        findings.append(_finding(f"{location}/runs", "E_MATRIX_COVERAGE", "run entry가 고정 matrix 순서가 아니다"))

    reasons = set(report["incomplete_reasons"])
    exact_matrix = observed_cells == list(MATRIX_CELL_ORDER)
    exact_measurements = len(seen_measurement_ids) == 12 and len(seen_measurement_refs) == 12
    if not exact_matrix and "matrix_coverage" not in reasons:
        findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "누락 matrix coverage 사유가 없다"))
    if not exact_measurements and "measurement_coverage" not in reasons:
        findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "누락 measurement coverage 사유가 없다"))
    if exact_matrix and len(manifests) != 8:
        findings.append(_finding(f"{location}/runs", "E_MATRIX_COVERAGE", "8개 manifest를 모두 읽고 검증하지 못했다"))
    if report["unsupported_metrics"] != ["lid_accuracy", "chrf2"]:
        findings.append(_finding(f"{location}/unsupported_metrics", "E_CALIBRATION_STATUS", "unsupported metric의 고정 순서와 다르다"))
    paired_ref = report.get("paired_timestamp_diagnostic_ref")
    if paired_ref is not None:
        _verify_cas_ref(
            paired_ref,
            store=store,
            validator=validator,
            location=f"{location}/paired_timestamp_diagnostic_ref",
            findings=findings,
        )
    if report["status"] == "completed":
        findings.append(
            _finding(
                f"{location}/status",
                "E_CALIBRATION_STATUS",
                "미구현 timing/NVML/correction/interruption/final ancestry 검증 전에는 completed를 주장할 수 없다",
            )
        )
    elif not report["incomplete_reasons"]:
        findings.append(_finding(f"{location}/incomplete_reasons", "E_CALIBRATION_STATUS", "incomplete report는 미완료 사유를 가져야 한다"))
    for required_pending in (
        "environment",
        "model_snapshot",
        "corrections",
        "interruption",
        "materialization",
        "timing",
        "nvml",
        "final_outputs",
    ):
        if required_pending not in reasons:
            findings.append(
                _finding(
                    f"{location}/incomplete_reasons",
                    "E_CALIBRATION_STATUS",
                    f"현재 slice의 미검증 집계 축 {required_pending}를 명시해야 한다",
                )
            )

    findings.extend(
        validate_measurement_runtime_evidence_set(
            measurements,
            project_root,
            f"{location}/measurements",
            schema_set,
        )
    )
    return sort_findings(findings)
