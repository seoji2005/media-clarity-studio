"""Deterministic TASK-031 exact-matrix fixture builder.

The fixture uses the production TASK-028 runtime and artifact store.  It creates
eight distinct logical runs and twelve distinct measured candidate-stage
attempts without claiming Windows, model, timing, correction, interruption, or
NVML evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from media_clarity.calibration.evidence import store_stage_spec_identity
from media_clarity.calibration.spine import MATRIX_CELL_ORDER
from media_clarity.job_runtime import (
    RUNTIME_VERSION,
    JobRuntime,
    JobSpec,
    StageContext,
    StageOutput,
    StageSpec,
    canonical_hash,
    canonical_json_bytes,
)
from media_clarity.schema_core import SCHEMA_VERSION, load_strict


MODEL_REVISIONS = {
    "Systran/faster-whisper-large-v3": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
    "Qwen/Qwen3-ASR-1.7B": "7278e1e70fe206f11671096ffdd38061171dd6e5",
    "google/madlad400-3b-mt": "fa184c675da0b5c9e1c8694fccd4e12e2d422094",
    "Qwen/Qwen3.5-4B": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
}

CELL_CANDIDATES = {
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

MEASUREMENT_PROJECTION_FIELDS = (
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


def emit_text(name: str, text: str):
    def run(context: StageContext) -> Sequence[StageOutput]:
        target = context.workspace / name
        target.write_text(text, encoding="utf-8")
        return [StageOutput(name=name, path=target)]

    return run


@dataclass(frozen=True)
class ExactMatrixFixture:
    report: dict[str, Any]
    manifests: dict[str, dict[str, Any]]
    measurements: dict[str, dict[str, Any]]


class ExactMatrixFixtureBuilder:
    """Build an honest incomplete report with exact 8-cell/12-stage coverage."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.runtime = JobRuntime(self.root)
        self._stored_document_count = 0

    def store_bytes(
        self,
        label: str,
        payload: bytes,
        *,
        kind: str = "text",
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        self._stored_document_count += 1
        source = (
            self.root
            / "fixture-sources"
            / f"{self._stored_document_count:04d}-{label}"
        )
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        return self.runtime.store.add_file(
            source,
            job_id="task031-exact-matrix-fixture",
            stage_id="fixture-evidence",
            kind=kind,
            media_type=media_type,
        ).ref

    def store_json(self, label: str, document: Any) -> dict[str, Any]:
        return self.store_bytes(
            label,
            canonical_json_bytes(document),
            kind="text",
            media_type="application/json",
        )

    def load_json_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        document = load_strict(self.runtime.store.absolute(ref["uri"], "fixture/ref"))
        if not isinstance(document, dict):
            raise AssertionError("fixture JSON root must be an object")
        return document

    def build(self) -> ExactMatrixFixture:
        environment_ref = self.store_json(
            "environment.json", {"kind": "synthetic_fixture", "pending": True}
        )
        pack_audio_ref = self.store_bytes(
            "pack.wav", b"synthetic-task031-pack", kind="audio", media_type="audio/wav"
        )
        pack_manifest_ref = self.store_json(
            "pack-manifest.json",
            {"kind": "synthetic_fixture", "duration_ns": 600000000000},
        )
        pipeline_id = "task031-exact-matrix-fixture"
        style_hash = canonical_hash({"style": "calibration-only"})
        chunk_stitch_hash = canonical_hash({"chunk_stitch": "synthetic-v1"})
        manifests: dict[str, dict[str, Any]] = {}
        measurements: dict[str, dict[str, Any]] = {}
        report_runs: list[dict[str, Any]] = []

        for cell_id in MATRIX_CELL_ORDER:
            run_kind, candidates = CELL_CANDIDATES[cell_id]
            run_id = f"run-{cell_id}"
            job_id = f"job-{cell_id}"
            source_stage = StageSpec(
                stage_id="source",
                implementation_version="matrix-source/1.0.0",
                config_hash=canonical_hash({"cell": cell_id, "source": True}),
            )
            stages = [source_stage]
            stage_records: list[dict[str, Any]] = []
            dependency_stage_id = source_stage.stage_id

            for role, model_id in candidates:
                weight_hash = canonical_hash(
                    {
                        "fixture_weight": model_id,
                        "revision": MODEL_REVISIONS[model_id],
                    }
                )
                config_hash = canonical_hash(
                    {"cell": cell_id, "role": role, "model": model_id}
                )
                backend_identity_hash = canonical_hash(
                    {"fixture_backend": role}
                )
                runtime_stage_id = role
                stage = StageSpec(
                    stage_id=runtime_stage_id,
                    implementation_version=f"matrix-{role}/1.0.0",
                    depends_on=(dependency_stage_id,),
                    config_hash=config_hash,
                    dependency_fingerprint=backend_identity_hash,
                    model_hash=weight_hash,
                    random_seed=31,
                    reproducibility_tier="T2",
                )
                stages.append(stage)
                stage_records.append(
                    {
                        "role": role,
                        "model_id": model_id,
                        "weight_hash": weight_hash,
                        "backend_identity_hash": backend_identity_hash,
                        "config_hash": config_hash,
                        "stage": stage,
                        "dependency_stage_id": dependency_stage_id,
                    }
                )
                dependency_stage_id = runtime_stage_id

            spec = JobSpec(
                job_id=job_id,
                pipeline_id=pipeline_id,
                source_identity=f"synthetic-source-{cell_id}",
                stages=tuple(stages),
            )
            for record in stage_records:
                digest, ref = store_stage_spec_identity(
                    self.runtime.store, spec, record["stage"]
                )
                record["stage_spec_digest"] = digest
                record["stage_spec_document_ref"] = ref

            callables = {
                "source": emit_text("source.txt", f"source:{cell_id}"),
                **{
                    record["role"]: emit_text(
                        f"raw-{record['role']}.json",
                        f'{{"cell":"{cell_id}","role":"{record["role"]}"}}',
                    )
                    for record in stage_records
                },
            }
            result = self.runtime.run_job(spec, callables)
            candidate_identities: list[dict[str, Any]] = []
            for record in stage_records:
                candidate_identities.append(
                    {
                        "official_model_id": record["model_id"],
                        "model_revision": MODEL_REVISIONS[record["model_id"]],
                        "weight_hash": record["weight_hash"],
                        "backend_identity_hash": record["backend_identity_hash"],
                        "precision": "float16",
                        "quantization": "none",
                        "config_hash": record["config_hash"],
                    }
                )
            candidate_chain_hash = canonical_hash(
                [
                    {"adapter_role": record["role"], **identity}
                    for record, identity in zip(
                        stage_records, candidate_identities, strict=True
                    )
                ]
            )
            candidate_config_hash = canonical_hash(
                [
                    {
                        "adapter_role": record["role"],
                        "config_hash": identity["config_hash"],
                    }
                    for record, identity in zip(
                        stage_records, candidate_identities, strict=True
                    )
                ]
            )
            candidate_stages: list[dict[str, Any]] = []

            for record, candidate_identity in zip(
                stage_records, candidate_identities, strict=True
            ):
                role = record["role"]
                outcome = result.outcome(role)
                dependency_outcome = result.outcome(record["dependency_stage_id"])
                attempt = load_strict(self.root / outcome.attempt_path)
                runtime_identity = {
                    "job_id": job_id,
                    "runtime_stage_id": role,
                    "attempt_id": outcome.attempt_id,
                    "attempt_record_ref": outcome.attempt_path,
                    "cache_key": outcome.cache_key,
                    "stage_spec_digest": record["stage_spec_digest"],
                    "stage_spec_document_ref": record["stage_spec_document_ref"],
                    "input_ref_tuple": attempt["inputs"],
                    "output_ref_tuple": attempt["outputs"],
                    "dependency_cache_keys": {
                        record["dependency_stage_id"]: dependency_outcome.cache_key
                    },
                }
                candidate_stage_id = f"candidate-{cell_id}-{role}"
                measurement_id = f"measurement-{cell_id}-{role}"
                aggregate_ref = self.store_json(
                    f"aggregate-{cell_id}-{role}.json",
                    {
                        "kind": "synthetic_aggregate",
                        "cell": cell_id,
                        "role": role,
                    },
                )
                measurement = {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "PerformanceMeasurement/v1",
                    "status": "incomplete",
                    "incomplete_reasons": [
                        "environment",
                        "model_snapshot",
                        "materialization",
                        "timing",
                        "nvml",
                    ],
                    "measurement_id": measurement_id,
                    "run_id": run_id,
                    "matrix_cell_id": cell_id,
                    "candidate_stage_id": candidate_stage_id,
                    "adapter_role": role,
                    "candidate_identity": candidate_identity,
                    "candidate_chain_hash": candidate_chain_hash,
                    "attempt_record_mode": "canonical_path",
                    "pipeline_id": pipeline_id,
                    "environment_runtime_version": RUNTIME_VERSION,
                    "environment_schema_version": SCHEMA_VERSION,
                    "environment_ref": environment_ref,
                    "unit_ids": [f"unit-{cell_id}-{role}"],
                    "stage_spec_digests": [record["stage_spec_digest"]],
                    "stage_spec_document_refs": [
                        record["stage_spec_document_ref"]
                    ],
                    "attempt_ids": [outcome.attempt_id],
                    "cache_keys": [outcome.cache_key],
                    "input_ref_tuples": [attempt["inputs"]],
                    "output_ref_tuples": [attempt["outputs"]],
                    "raw_output_refs": [attempt["outputs"][0]],
                    "runtime_identities": [runtime_identity],
                    "aggregate_normalized_output_ref": aggregate_ref,
                }
                measurement_ref = self.store_json(
                    f"{measurement_id}.json", measurement
                )
                measurements[measurement_id] = measurement
                candidate_stage = {
                    "candidate_stage_id": candidate_stage_id,
                    "adapter_role": role,
                    "candidate_identity": candidate_identity,
                    **{
                        field: measurement[field]
                        for field in MEASUREMENT_PROJECTION_FIELDS
                    },
                    "aggregate_normalized_output_ref": aggregate_ref,
                    "measurement_id": measurement_id,
                    "performance_measurement_ref": measurement_ref,
                }
                candidate_stages.append(candidate_stage)

            incomplete_reasons = [
                "environment",
                "model_snapshot",
                "corrections",
            ]
            if run_kind == "end_to_end":
                incomplete_reasons.extend(("interruption", "final_outputs"))
            incomplete_reasons.extend(("materialization", "timing", "nvml"))
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "kind": "CalibrationRunManifest/v1",
                "run_id": run_id,
                "run_kind": run_kind,
                "matrix_cell_id": cell_id,
                "created_at": "2026-09-03T00:00:00Z",
                "status": "incomplete",
                "candidate_chain_hash": candidate_chain_hash,
                "pipeline_id": pipeline_id,
                "pipeline_source_commit": "3" * 40,
                "attempt_record_mode": "canonical_path",
                "environment_runtime_version": RUNTIME_VERSION,
                "environment_schema_version": SCHEMA_VERSION,
                "environment_ref": environment_ref,
                "pack_manifest_ref": pack_manifest_ref,
                "pack_audio_ref": pack_audio_ref,
                "pack_hash": pack_manifest_ref["content_hash"],
                "pack_duration_ns": 600000000000,
                "candidate_config_hash": candidate_config_hash,
                "style_hash": style_hash,
                "chunk_stitch_hash": chunk_stitch_hash,
                "candidate_stages": candidate_stages,
                "correction_record_refs": [],
                "incomplete_reasons": incomplete_reasons,
            }
            manifest_ref = self.store_json(f"manifest-{cell_id}.json", manifest)
            manifests[cell_id] = manifest
            report_runs.append(
                {
                    "run_id": run_id,
                    "matrix_cell_id": cell_id,
                    "manifest_ref": manifest_ref,
                    "measurement_ids": [
                        stage["measurement_id"] for stage in candidate_stages
                    ],
                    "performance_measurement_refs": [
                        stage["performance_measurement_ref"]
                        for stage in candidate_stages
                    ],
                }
            )

        report = {
            "schema_version": SCHEMA_VERSION,
            "kind": "CalibrationReport/v1",
            "report_id": "task031-exact-matrix-fixture",
            "created_at": "2026-09-03T00:10:00Z",
            "status": "incomplete",
            "pack_hash": pack_manifest_ref["content_hash"],
            "runs": report_runs,
            "unsupported_metrics": ["lid_accuracy", "chrf2"],
            "incomplete_reasons": [
                "environment",
                "model_snapshot",
                "corrections",
                "interruption",
                "materialization",
                "timing",
                "nvml",
                "final_outputs",
            ],
        }
        return ExactMatrixFixture(
            report=report,
            manifests=manifests,
            measurements=measurements,
        )
