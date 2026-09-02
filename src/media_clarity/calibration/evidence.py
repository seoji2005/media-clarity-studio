"""TASK-031 offline calibration evidence core.

이 모듈은 Windows/GPU 측정값을 만들지 않는다. 대신 실제 TASK-028 ``AttemptRecord``와
향후 ``PerformanceMeasurement/v1``이 공유해야 하는 runtime identity projection을
fail-closed로 검증한다.

이번 slice의 경계:

* canonical StageSpec identity document 생성·CAS 저장·재검증
* AttemptRecord의 실제 필드와 ordered input/output tuple exact equality
* fingerprints·cacheable·depends_on/dependency cache key·cache key 재계산
* measured unit output cardinality 1과 실제 실행(cache miss/callable invocation)
* 여러 measurement 사이 attempt identity 전역 유일성

RTF clock/materialization, NVML sample, exact 8-cell/12-stage coverage와 report 집계는
후속 evidence-spine validator가 이 API를 호출해 검증한다. 이 모듈의 성공만으로
``PerformanceMeasurement/v1`` 또는 TASK-031 완료를 주장할 수 없다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Mapping, Sequence

from media_clarity.artifact_store import (
    ArtifactStore,
    ContractViolation,
    path_segment_error,
)
from media_clarity.job_runtime import (
    ARTIFACT_REF_POINTER,
    ATTEMPT_RECORD_POINTER,
    JOB_SCHEMA_FILE,
    RUNTIME_VERSION,
    JobSpec,
    StageSpec,
    canonical_hash,
    canonical_json_bytes,
    check_attempt_identity,
    check_attempt_semantics,
    stage_cache_key,
)
from media_clarity.schema_core import (
    COMMON_SCHEMA_FILE,
    DEFAULT_SCHEMA_DIR,
    SCHEMA_VERSION,
    Finding,
    JsonInputError,
    SchemaSet,
    SchemaValidator,
    load_strict,
    loads_strict,
    sort_findings,
)


STAGE_SPEC_SCHEMA_FILE = "calibration-stage-spec-identity-v1.schema.json"
EVIDENCE_SCHEMA_FILES = (
    COMMON_SCHEMA_FILE,
    JOB_SCHEMA_FILE,
    STAGE_SPEC_SCHEMA_FILE,
)

MATRIX_CELL_IDS = frozenset(
    {
        "asr-faster-whisper",
        "asr-qwen3-asr",
        "mt-madlad",
        "mt-qwen3.5",
        "e2e-faster-whisper__madlad",
        "e2e-faster-whisper__qwen3.5",
        "e2e-qwen3-asr__madlad",
        "e2e-qwen3-asr__qwen3.5",
    }
)

IDENTITY_FIELDS = (
    "job_id",
    "runtime_stage_id",
    "attempt_id",
    "attempt_record_ref",
    "cache_key",
    "stage_spec_digest",
    "stage_spec_document_ref",
    "input_ref_tuple",
    "output_ref_tuple",
    "dependency_cache_keys",
)

MEASUREMENT_PROJECTION_FIELDS = (
    "measurement_id",
    "run_id",
    "matrix_cell_id",
    "candidate_stage_id",
    "adapter_role",
    "attempt_record_mode",
    "pipeline_id",
    "environment_runtime_version",
    "environment_schema_version",
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

_FINGERPRINT_FIELDS = (
    "config_hash",
    "dependency_fingerprint",
    "source_hash",
    "chunking_hash",
    "model_hash",
    "context_hash",
    "random_seed",
)

_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def evidence_schema_set(directory: Path = DEFAULT_SCHEMA_DIR) -> SchemaSet:
    """TASK-031 evidence core가 사용하는 실제 schema 묶음."""

    return SchemaSet(directory, EVIDENCE_SCHEMA_FILES)


def stage_spec_identity_document(spec: JobSpec, stage: StageSpec) -> dict[str, Any]:
    """TASK-031 §5.1.1.1의 유일한 canonical StageSpec identity 문서."""

    return {
        "kind": "task031_stage_spec_identity",
        "runtime_version": RUNTIME_VERSION,
        "schema_version": SCHEMA_VERSION,
        "pipeline_id": spec.pipeline_id,
        "stage_id": stage.stage_id,
        "implementation_version": stage.implementation_version,
        "depends_on": sorted(stage.depends_on),
        "config_hash": stage.config_hash,
        "dependency_fingerprint": stage.dependency_fingerprint,
        "source_hash": stage.source_hash,
        "chunking_hash": stage.chunking_hash,
        "model_hash": stage.model_hash,
        "context_hash": stage.context_hash,
        "random_seed": stage.random_seed,
        "reproducibility_tier": stage.reproducibility_tier,
        "cacheable": stage.cacheable,
    }


def store_stage_spec_identity(
    store: ArtifactStore,
    spec: JobSpec,
    stage: StageSpec,
) -> tuple[str, dict[str, Any]]:
    """canonical document를 기존 CAS에 기록하고 ``(digest, ArtifactRef)``를 반환한다.

    CAS object에는 trailing newline이나 pretty-print 변형을 넣지 않는다. 반환 digest는
    document의 canonical bytes와 CAS ref 양쪽에 exact equality다.
    """

    document = stage_spec_identity_document(spec, stage)
    validator = SchemaValidator(evidence_schema_set())
    findings = validator.validate(document, STAGE_SPEC_SCHEMA_FILE, "stage_spec")
    if findings:
        first = sort_findings(findings)[0]
        raise ValueError(first.as_line())

    payload = canonical_json_bytes(document)
    digest = canonical_hash(document)
    with TemporaryDirectory(prefix="mcs-task031-stage-spec-") as temporary:
        source = Path(temporary) / "stage-spec.json"
        source.write_bytes(payload)
        outcome = store.add_file(
            source,
            job_id=spec.job_id,
            stage_id=stage.stage_id,
            kind="text",
            media_type="application/json",
        )
    if outcome.ref["content_hash"] != digest:
        raise AssertionError("canonical StageSpec digest와 CAS ref digest가 다르다")
    return digest, outcome.ref


def _finding(location: str, code: str, message: str) -> Finding:
    return Finding(location=location, code=code, message=message)


def _is_list(value: Any) -> bool:
    return isinstance(value, list)


def _require_projection(
    measurement: Mapping[str, Any], location: str, findings: list[Finding]
) -> bool:
    missing = [field for field in MEASUREMENT_PROJECTION_FIELDS if field not in measurement]
    for field in missing:
        findings.append(_finding(location, "E_MEASUREMENT_IDENTITY", f"필수 필드 누락: {field}"))
    if missing:
        return False

    for field in (
        "measurement_id",
        "run_id",
        "matrix_cell_id",
        "candidate_stage_id",
        "adapter_role",
        "attempt_record_mode",
        "pipeline_id",
        "environment_runtime_version",
        "environment_schema_version",
    ):
        if not isinstance(measurement[field], str) or not measurement[field]:
            findings.append(
                _finding(f"{location}/{field}", "E_MEASUREMENT_IDENTITY", "비어 있지 않은 문자열이어야 한다")
            )

    for field in (
        "measurement_id",
        "run_id",
        "candidate_stage_id",
        "pipeline_id",
    ):
        if isinstance(measurement[field], str) and _IDENTIFIER_RE.fullmatch(measurement[field]) is None:
            findings.append(
                _finding(
                    f"{location}/{field}",
                    "E_MEASUREMENT_IDENTITY",
                    "공통 identifier 형식이 아니다",
                )
            )

    if measurement["matrix_cell_id"] not in MATRIX_CELL_IDS:
        findings.append(
            _finding(f"{location}/matrix_cell_id", "E_MEASUREMENT_IDENTITY", "고정 8-cell 집합 밖의 값")
        )
    if measurement["adapter_role"] not in {"asr", "mt"}:
        findings.append(
            _finding(f"{location}/adapter_role", "E_MEASUREMENT_IDENTITY", "asr 또는 mt여야 한다")
        )
    role_by_independent_cell = {
        "asr-faster-whisper": "asr",
        "asr-qwen3-asr": "asr",
        "mt-madlad": "mt",
        "mt-qwen3.5": "mt",
    }
    expected_role = role_by_independent_cell.get(measurement["matrix_cell_id"])
    if expected_role is not None and measurement["adapter_role"] != expected_role:
        findings.append(
            _finding(
                f"{location}/adapter_role",
                "E_MEASUREMENT_IDENTITY",
                "independent matrix cell의 candidate role과 다르다",
            )
        )
    if measurement["attempt_record_mode"] != "canonical_path":
        findings.append(
            _finding(
                f"{location}/attempt_record_mode",
                "E_ATTEMPT_RECORD",
                "이번 evidence core는 canonical_path mode만 허용한다",
            )
        )

    for field in (
        "unit_ids",
        "stage_spec_digests",
        "stage_spec_document_refs",
        "attempt_ids",
        "cache_keys",
        "input_ref_tuples",
        "output_ref_tuples",
        "raw_output_refs",
        "runtime_identities",
    ):
        if not _is_list(measurement[field]):
            findings.append(
                _finding(f"{location}/{field}", "E_MEASUREMENT_IDENTITY", "배열이어야 한다")
            )
    return not findings


def _project_fingerprints(document: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "implementation_version": document["implementation_version"]
    }
    for field in _FINGERPRINT_FIELDS:
        value = document[field]
        if value is not None:
            projected[field] = value
    return projected


def _stage_from_document(document: Mapping[str, Any]) -> StageSpec:
    return StageSpec(
        stage_id=document["stage_id"],
        implementation_version=document["implementation_version"],
        depends_on=tuple(document["depends_on"]),
        config_hash=document["config_hash"],
        dependency_fingerprint=document["dependency_fingerprint"],
        source_hash=document["source_hash"],
        chunking_hash=document["chunking_hash"],
        model_hash=document["model_hash"],
        context_hash=document["context_hash"],
        random_seed=document["random_seed"],
        reproducibility_tier=document["reproducibility_tier"],
        cacheable=document["cacheable"],
    )


def _verify_artifact_ref(
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
        store.verify_ref(ref, location)
    except (ContractViolation, KeyError, TypeError) as error:
        findings.append(_finding(location, "E_ARTIFACT_EVIDENCE", str(error)))
        return False
    return True


def _load_stage_spec_document(
    ref: Any,
    expected_digest: Any,
    *,
    store: ArtifactStore,
    validator: SchemaValidator,
    location: str,
    findings: list[Finding],
) -> Mapping[str, Any] | None:
    if not _verify_artifact_ref(
        ref, store=store, validator=validator, location=location, findings=findings
    ):
        return None
    assert isinstance(ref, Mapping)
    if ref.get("kind") != "text" or ref.get("media_type") != "application/json":
        findings.append(
            _finding(location, "E_STAGE_SPEC_IDENTITY", "kind=text, media_type=application/json이어야 한다")
        )
        return None
    try:
        payload = store.absolute(ref["uri"], f"{location}/uri").read_bytes()
        document = loads_strict(payload.decode("utf-8"))
    except (ContractViolation, UnicodeDecodeError, JsonInputError):
        findings.append(_finding(location, "E_STAGE_SPEC_IDENTITY", "문서를 안전하게 읽거나 파싱할 수 없다"))
        return None
    except OSError:
        findings.append(_finding(location, "E_STAGE_SPEC_IDENTITY", "문서 파일을 읽을 수 없다"))
        return None
    schema_findings = validator.validate(document, STAGE_SPEC_SCHEMA_FILE, location)
    findings.extend(schema_findings)
    if schema_findings or not isinstance(document, Mapping):
        return None
    canonical = canonical_json_bytes(document)
    digest = canonical_hash(document)
    if payload != canonical:
        findings.append(
            _finding(location, "E_STAGE_SPEC_IDENTITY", "CAS bytes가 canonical JSON 표현과 다르다")
        )
    if digest != expected_digest or ref.get("content_hash") != expected_digest:
        findings.append(
            _finding(location, "E_STAGE_SPEC_IDENTITY", "document/ref/stage_spec_digest가 일치하지 않는다")
        )
    return document


def _validate_unit(
    identity: Any,
    *,
    measurement: Mapping[str, Any],
    index: int,
    store: ArtifactStore,
    validator: SchemaValidator,
    location: str,
    findings: list[Finding],
) -> None:
    unit_location = f"{location}/runtime_identities/{index}"
    if not isinstance(identity, Mapping):
        findings.append(_finding(unit_location, "E_RUNTIME_IDENTITY", "객체여야 한다"))
        return
    missing = [field for field in IDENTITY_FIELDS if field not in identity]
    extras = sorted(set(identity) - set(IDENTITY_FIELDS))
    for field in missing:
        findings.append(_finding(unit_location, "E_RUNTIME_IDENTITY", f"필수 필드 누락: {field}"))
    for field in extras:
        findings.append(
            _finding(f"{unit_location}/{field}", "E_RUNTIME_IDENTITY", "허용되지 않은 추가 필드")
        )
    if missing:
        return

    parallel = (
        ("stage_spec_digests", "stage_spec_digest"),
        ("stage_spec_document_refs", "stage_spec_document_ref"),
        ("attempt_ids", "attempt_id"),
        ("cache_keys", "cache_key"),
        ("input_ref_tuples", "input_ref_tuple"),
        ("output_ref_tuples", "output_ref_tuple"),
    )
    for array_field, identity_field in parallel:
        if measurement[array_field][index] != identity[identity_field]:
            findings.append(
                _finding(
                    f"{unit_location}/{identity_field}",
                    "E_MEASUREMENT_IDENTITY",
                    f"measurement.{array_field}[{index}]와 다르다",
                )
            )

    for field in ("job_id", "runtime_stage_id", "attempt_id"):
        reason = path_segment_error(identity[field])
        if reason is not None:
            findings.append(_finding(f"{unit_location}/{field}", "E_RUNTIME_IDENTITY", reason))
            return

    expected_path = (
        f"jobs/{identity['job_id']}/stages/{identity['runtime_stage_id']}"
        f"/attempts/{identity['attempt_id']}.json"
    )
    if identity["attempt_record_ref"] != expected_path:
        findings.append(
            _finding(
                f"{unit_location}/attempt_record_ref",
                "E_ATTEMPT_RECORD",
                "TASK-028 canonical attempt_path와 다르다",
            )
        )
        return
    try:
        attempt_path = store.absolute(expected_path, f"{unit_location}/attempt_record_ref")
        attempt = load_strict(attempt_path)
    except (ContractViolation, JsonInputError):
        findings.append(
            _finding(
                f"{unit_location}/attempt_record_ref",
                "E_ATTEMPT_RECORD",
                "attempt record를 안전하게 읽거나 파싱할 수 없다",
            )
        )
        return
    except OSError:
        findings.append(
            _finding(
                f"{unit_location}/attempt_record_ref",
                "E_ATTEMPT_RECORD",
                "attempt record 파일을 읽을 수 없다",
            )
        )
        return

    schema_findings = validator.validate(
        attempt, JOB_SCHEMA_FILE, expected_path, ATTEMPT_RECORD_POINTER
    )
    findings.extend(schema_findings)
    if schema_findings or not isinstance(attempt, Mapping):
        return
    findings.extend(check_attempt_semantics(attempt, expected_path))
    findings.extend(
        check_attempt_identity(
            attempt,
            expected_path,
            job_id=identity["job_id"],
            stage_id=identity["runtime_stage_id"],
            file_stem=identity["attempt_id"],
        )
    )

    exact_fields = (
        ("job_id", "job_id"),
        ("runtime_stage_id", "stage_id"),
        ("attempt_id", "attempt_id"),
        ("cache_key", "cache_key"),
        ("input_ref_tuple", "inputs"),
        ("output_ref_tuple", "outputs"),
    )
    for identity_field, attempt_field in exact_fields:
        if identity[identity_field] != attempt.get(attempt_field):
            findings.append(
                _finding(
                    f"{unit_location}/{identity_field}",
                    "E_RUNTIME_IDENTITY",
                    f"AttemptRecord.{attempt_field}와 exact equality가 아니다",
                )
            )

    if attempt.get("status") != "completed":
        findings.append(_finding(expected_path, "E_ATTEMPT_EXECUTION", "completed attempt가 아니다"))
    if attempt.get("callable_invoked") is not True or attempt.get("cache_status") != "miss":
        findings.append(
            _finding(expected_path, "E_ATTEMPT_EXECUTION", "실제로 실행된 cache-miss attempt가 아니다")
        )

    outputs = attempt.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 1:
        findings.append(
            _finding(f"{expected_path}/outputs", "E_OUTPUT_CARDINALITY", "measured unit output은 정확히 1개여야 한다")
        )
    elif measurement["raw_output_refs"][index] != outputs[0]:
        findings.append(
            _finding(
                f"{location}/raw_output_refs/{index}",
                "E_OUTPUT_BINDING",
                "유일한 AttemptRecord output과 다르다",
            )
        )

    for tuple_name in ("inputs", "outputs"):
        refs = attempt.get(tuple_name)
        if isinstance(refs, list):
            for ref_index, ref in enumerate(refs):
                _verify_artifact_ref(
                    ref,
                    store=store,
                    validator=validator,
                    location=f"{expected_path}/{tuple_name}/{ref_index}",
                    findings=findings,
                )

    document = _load_stage_spec_document(
        identity["stage_spec_document_ref"],
        identity["stage_spec_digest"],
        store=store,
        validator=validator,
        location=f"{unit_location}/stage_spec_document_ref",
        findings=findings,
    )
    if document is None:
        return
    if document["pipeline_id"] != measurement["pipeline_id"]:
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_STAGE_SPEC_IDENTITY", "pipeline_id가 다르다")
        )
    if document["stage_id"] != attempt.get("stage_id"):
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_STAGE_SPEC_IDENTITY", "stage_id가 다르다")
        )
    if _project_fingerprints(document) != attempt.get("fingerprints"):
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_STAGE_SPEC_FINGERPRINT", "AttemptRecord.fingerprints와 다르다")
        )
    if "cacheable" not in attempt or not isinstance(attempt.get("cacheable"), bool):
        findings.append(_finding(expected_path, "E_STAGE_SPEC_CACHEABLE", "AttemptRecord.cacheable boolean이 없다"))
    elif document["cacheable"] is not attempt["cacheable"]:
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_STAGE_SPEC_CACHEABLE", "AttemptRecord.cacheable과 다르다")
        )

    dependency_keys = identity["dependency_cache_keys"]
    if not isinstance(dependency_keys, Mapping):
        findings.append(
            _finding(f"{unit_location}/dependency_cache_keys", "E_DEPENDENCY_CACHE_KEYS", "문자열 mapping이어야 한다")
        )
        return
    invalid_dependencies = [
        key
        for key, value in dependency_keys.items()
        if path_segment_error(key) is not None
        or not isinstance(value, str)
        or _CONTENT_HASH_RE.fullmatch(value) is None
    ]
    if invalid_dependencies:
        findings.append(
            _finding(
                f"{unit_location}/dependency_cache_keys",
                "E_DEPENDENCY_CACHE_KEYS",
                "key는 안전한 stage ID, value는 sha256 content hash여야 한다",
            )
        )
        return
    depends_on = document["depends_on"]
    if depends_on != sorted(depends_on) or len(depends_on) != len(set(depends_on)):
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_DEPENDENCY_CACHE_KEYS", "depends_on이 정렬·중복 없음이 아니다")
        )
    if depends_on != sorted(dependency_keys):
        findings.append(
            _finding(
                f"{unit_location}/dependency_cache_keys",
                "E_DEPENDENCY_CACHE_KEYS",
                "depends_on과 dependency_cache_keys key 집합이 다르다",
            )
        )

    if (
        document["runtime_version"] != attempt.get("runtime_version")
        or document["runtime_version"] != measurement["environment_runtime_version"]
        or document["runtime_version"] != RUNTIME_VERSION
    ):
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_STAGE_SPEC_VERSION", "runtime_version이 일치하지 않는다")
        )
    if (
        document["schema_version"] != attempt.get("schema_version")
        or document["schema_version"] != measurement["environment_schema_version"]
        or document["schema_version"] != SCHEMA_VERSION
    ):
        findings.append(
            _finding(f"{unit_location}/stage_spec_document_ref", "E_STAGE_SPEC_VERSION", "schema_version이 일치하지 않는다")
        )

    if isinstance(attempt.get("inputs"), list):
        try:
            input_hashes = [ref["content_hash"] for ref in attempt["inputs"]]
            stage = _stage_from_document(document)
            spec = JobSpec(
                job_id=identity["job_id"],
                pipeline_id=measurement["pipeline_id"],
                stages=(stage,),
            )
            rebuilt = stage_cache_key(spec, stage, input_hashes, dependency_keys)
        except (KeyError, TypeError, ValueError) as error:
            findings.append(_finding(unit_location, "E_CACHE_KEY_REBUILD", str(error)))
        else:
            if rebuilt != attempt.get("cache_key"):
                findings.append(
                    _finding(f"{unit_location}/cache_key", "E_CACHE_KEY_REBUILD", "AttemptRecord.cache_key 재계산값과 다르다")
                )


def validate_measurement_runtime_evidence(
    measurement: Any,
    project_root: Path,
    location: str = "measurement",
    schemas: SchemaSet | None = None,
) -> list[Finding]:
    """한 candidate-stage measurement의 runtime identity projection을 검증한다.

    전체 ``PerformanceMeasurement/v1``에서 이 함수가 소비하는 필드만 요구한다. timing,
    NVML 등 후속 필드가 함께 있어도 무시하지만, 이 함수의 성공은 그 필드를 검증했다는
    뜻이 아니다.
    """

    if not isinstance(measurement, Mapping):
        return [_finding(location, "E_MEASUREMENT_IDENTITY", "객체여야 한다")]
    findings: list[Finding] = []
    if not _require_projection(measurement, location, findings):
        return sort_findings(findings)

    arrays = [measurement[field] for field in MEASUREMENT_PROJECTION_FIELDS if field in {
        "unit_ids",
        "stage_spec_digests",
        "stage_spec_document_refs",
        "attempt_ids",
        "cache_keys",
        "input_ref_tuples",
        "output_ref_tuples",
        "raw_output_refs",
        "runtime_identities",
    }]
    if not all(isinstance(value, list) for value in arrays):
        return sort_findings(findings)
    lengths = {len(value) for value in arrays}
    if lengths != {len(measurement["unit_ids"])} or not measurement["unit_ids"]:
        findings.append(
            _finding(location, "E_MEASUREMENT_IDENTITY", "ordered unit 배열은 같은 non-zero 길이여야 한다")
        )
        return sort_findings(findings)
    if len(set(measurement["unit_ids"])) != len(measurement["unit_ids"]):
        findings.append(_finding(f"{location}/unit_ids", "E_MEASUREMENT_IDENTITY", "unit_id가 중복됐다"))
    for index, unit_id in enumerate(measurement["unit_ids"]):
        if not isinstance(unit_id, str) or _IDENTIFIER_RE.fullmatch(unit_id) is None:
            findings.append(
                _finding(
                    f"{location}/unit_ids/{index}",
                    "E_MEASUREMENT_IDENTITY",
                    "공통 identifier 형식이 아니다",
                )
            )

    store = ArtifactStore(Path(project_root))
    validator = SchemaValidator(schemas or evidence_schema_set())
    for index, identity in enumerate(measurement["runtime_identities"]):
        _validate_unit(
            identity,
            measurement=measurement,
            index=index,
            store=store,
            validator=validator,
            location=location,
            findings=findings,
        )
    return sort_findings(findings)


def validate_measurement_runtime_evidence_set(
    measurements: Sequence[Any],
    project_root: Path,
    location: str = "measurements",
    schemas: SchemaSet | None = None,
) -> list[Finding]:
    """여러 measurement를 검증하고 attempt identity 재사용을 전역 거부한다.

    output CAS digest의 중복은 정상 dedup이므로 유일성 기준에 넣지 않는다.
    """

    findings: list[Finding] = []
    schema_set = schemas or evidence_schema_set()
    seen_measurements: dict[Any, int] = {}
    seen_stages: dict[tuple[Any, Any], int] = {}
    seen_attempts: dict[tuple[Any, Any, Any], tuple[int, int]] = {}
    seen_refs: dict[Any, tuple[int, int]] = {}

    for measurement_index, measurement in enumerate(measurements):
        measurement_location = f"{location}/{measurement_index}"
        findings.extend(
            validate_measurement_runtime_evidence(
                measurement, project_root, measurement_location, schema_set
            )
        )
        if not isinstance(measurement, Mapping):
            continue
        measurement_id = measurement.get("measurement_id")
        if measurement_id in seen_measurements:
            findings.append(
                _finding(f"{measurement_location}/measurement_id", "E_MEASUREMENT_REUSE", "measurement_id가 재사용됐다")
            )
        else:
            seen_measurements[measurement_id] = measurement_index
        stage_identity = (measurement.get("run_id"), measurement.get("candidate_stage_id"))
        if stage_identity in seen_stages:
            findings.append(
                _finding(measurement_location, "E_MEASUREMENT_REUSE", "run/candidate stage identity가 재사용됐다")
            )
        else:
            seen_stages[stage_identity] = measurement_index
        identities = measurement.get("runtime_identities")
        if not isinstance(identities, list):
            continue
        for unit_index, identity in enumerate(identities):
            if not isinstance(identity, Mapping):
                continue
            triple = (
                identity.get("job_id"),
                identity.get("runtime_stage_id"),
                identity.get("attempt_id"),
            )
            record_ref = identity.get("attempt_record_ref")
            unit_location = f"{measurement_location}/runtime_identities/{unit_index}"
            if triple in seen_attempts:
                findings.append(_finding(unit_location, "E_ATTEMPT_REUSE", "attempt identity가 재사용됐다"))
            else:
                seen_attempts[triple] = (measurement_index, unit_index)
            if record_ref in seen_refs:
                findings.append(_finding(unit_location, "E_ATTEMPT_REUSE", "attempt_record_ref가 재사용됐다"))
            else:
                seen_refs[record_ref] = (measurement_index, unit_index)
    return sort_findings(findings)


def findings_as_json(findings: Iterable[Finding]) -> str:
    """검증 결과를 로그/fixture에서 결정적으로 비교할 수 있는 JSON으로 직렬화한다."""

    return json.dumps(
        [finding.__dict__ for finding in sort_findings(findings)],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
