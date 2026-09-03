from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from media_clarity.calibration.evidence import store_stage_spec_identity
from media_clarity.calibration.spine import (
    CALIBRATION_REPORT_SCHEMA_FILE,
    MATRIX_CELL_ORDER,
    PERFORMANCE_MEASUREMENT_SCHEMA_FILE,
    RUN_MANIFEST_SCHEMA_FILE,
    spine_schema_set,
    validate_calibration_report,
    validate_calibration_run_manifest,
)
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
from media_clarity.schema_core import SCHEMA_VERSION, SchemaValidator, load_strict


def emit_many(names_and_text: Sequence[tuple[str, str]]):
    def run(context: StageContext) -> Sequence[StageOutput]:
        outputs: list[StageOutput] = []
        for name, text in names_and_text:
            target = context.workspace / name
            target.write_text(text, encoding="utf-8")
            outputs.append(StageOutput(name=name, path=target))
        return outputs

    return run


MATRIX_FIXTURE_CASES = (
    (
        "asr-faster-whisper",
        "independent_asr",
        (
            (
                "asr",
                "Systran/faster-whisper-large-v3",
                "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            ),
        ),
    ),
    (
        "asr-qwen3-asr",
        "independent_asr",
        (
            (
                "asr",
                "Qwen/Qwen3-ASR-1.7B",
                "7278e1e70fe206f11671096ffdd38061171dd6e5",
            ),
        ),
    ),
    (
        "mt-madlad",
        "independent_mt",
        (
            (
                "mt",
                "google/madlad400-3b-mt",
                "fa184c675da0b5c9e1c8694fccd4e12e2d422094",
            ),
        ),
    ),
    (
        "mt-qwen3.5",
        "independent_mt",
        (
            (
                "mt",
                "Qwen/Qwen3.5-4B",
                "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
            ),
        ),
    ),
    (
        "e2e-faster-whisper__madlad",
        "end_to_end",
        (
            (
                "asr",
                "Systran/faster-whisper-large-v3",
                "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            ),
            (
                "mt",
                "google/madlad400-3b-mt",
                "fa184c675da0b5c9e1c8694fccd4e12e2d422094",
            ),
        ),
    ),
    (
        "e2e-faster-whisper__qwen3.5",
        "end_to_end",
        (
            (
                "asr",
                "Systran/faster-whisper-large-v3",
                "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            ),
            (
                "mt",
                "Qwen/Qwen3.5-4B",
                "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
            ),
        ),
    ),
    (
        "e2e-qwen3-asr__madlad",
        "end_to_end",
        (
            (
                "asr",
                "Qwen/Qwen3-ASR-1.7B",
                "7278e1e70fe206f11671096ffdd38061171dd6e5",
            ),
            (
                "mt",
                "google/madlad400-3b-mt",
                "fa184c675da0b5c9e1c8694fccd4e12e2d422094",
            ),
        ),
    ),
    (
        "e2e-qwen3-asr__qwen3.5",
        "end_to_end",
        (
            (
                "asr",
                "Qwen/Qwen3-ASR-1.7B",
                "7278e1e70fe206f11671096ffdd38061171dd6e5",
            ),
            (
                "mt",
                "Qwen/Qwen3.5-4B",
                "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
            ),
        ),
    ),
)

RUNTIME_ARRAY_FIELDS = (
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


class ManifestReportCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory(prefix="mcs-task031-spine-")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.runtime = JobRuntime(self.root)

    def _store_bytes(
        self,
        name: str,
        payload: bytes,
        *,
        kind: str = "text",
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        source = self.root / "fixture-sources" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        return self.runtime.store.add_file(
            source,
            job_id="task031-spine-fixture",
            stage_id="fixture-evidence",
            kind=kind,
            media_type=media_type,
        ).ref

    def _store_json(self, name: str, document: Any) -> dict[str, Any]:
        return self._store_bytes(
            name,
            canonical_json_bytes(document),
            kind="text",
            media_type="application/json",
        )

    def build_independent_asr(self) -> tuple[dict[str, Any], dict[str, Any]]:
        spec = JobSpec(
            job_id="job-asr-faster-whisper",
            pipeline_id="task031-pipeline",
            source_identity="fixture-source",
            stages=(
                StageSpec(
                    stage_id="source",
                    implementation_version="source/1.0.0",
                    config_hash=canonical_hash({"source": 1}),
                ),
                StageSpec(
                    stage_id="candidate",
                    implementation_version="candidate/1.0.0",
                    depends_on=("source",),
                    config_hash=canonical_hash({"candidate": 1}),
                    dependency_fingerprint=canonical_hash({"dependencies": 1}),
                    model_hash=canonical_hash({"model": "faster-whisper"}),
                    random_seed=7,
                    reproducibility_tier="T2",
                ),
            ),
        )
        candidate = spec.stages[1]
        stage_spec_digest, stage_spec_ref = store_stage_spec_identity(
            self.runtime.store, spec, candidate
        )
        result = self.runtime.run_job(
            spec,
            {
                "source": emit_many((("audio-chunk.txt", "fixture audio"),)),
                "candidate": emit_many((("raw.json", '{"text":"fixture"}'),)),
            },
        )
        source_outcome = result.outcome("source")
        candidate_outcome = result.outcome("candidate")
        attempt = load_strict(self.root / candidate_outcome.attempt_path)
        runtime_identity = {
            "job_id": spec.job_id,
            "runtime_stage_id": "candidate",
            "attempt_id": candidate_outcome.attempt_id,
            "attempt_record_ref": candidate_outcome.attempt_path,
            "cache_key": candidate_outcome.cache_key,
            "stage_spec_digest": stage_spec_digest,
            "stage_spec_document_ref": stage_spec_ref,
            "input_ref_tuple": attempt["inputs"],
            "output_ref_tuple": attempt["outputs"],
            "dependency_cache_keys": {"source": source_outcome.cache_key},
        }
        aggregate_ref = self._store_json(
            "aggregate-transcript.json",
            {"kind": "fixture_transcript", "text": "fixture"},
        )
        environment_ref = self._store_json("environment.json", {"pending": True})
        candidate_identity = {
            "official_model_id": "Systran/faster-whisper-large-v3",
            "model_revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            "weight_hash": canonical_hash({"weight": "fixture"}),
            "backend_identity_hash": canonical_hash({"backend": "fixture"}),
            "precision": "float16",
            "quantization": "none",
            "config_hash": candidate.config_hash,
        }
        chain_hash = canonical_hash(
            [{"adapter_role": "asr", **candidate_identity}]
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
            "measurement_id": "measurement-asr-faster-whisper",
            "run_id": "run-asr-faster-whisper",
            "matrix_cell_id": "asr-faster-whisper",
            "candidate_stage_id": "candidate-asr-faster-whisper",
            "adapter_role": "asr",
            "candidate_identity": candidate_identity,
            "candidate_chain_hash": chain_hash,
            "attempt_record_mode": "canonical_path",
            "pipeline_id": spec.pipeline_id,
            "environment_runtime_version": RUNTIME_VERSION,
            "environment_schema_version": SCHEMA_VERSION,
            "environment_ref": environment_ref,
            "unit_ids": ["unit-0001"],
            "stage_spec_digests": [stage_spec_digest],
            "stage_spec_document_refs": [stage_spec_ref],
            "attempt_ids": [candidate_outcome.attempt_id],
            "cache_keys": [candidate_outcome.cache_key],
            "input_ref_tuples": [attempt["inputs"]],
            "output_ref_tuples": [attempt["outputs"]],
            "raw_output_refs": [attempt["outputs"][0]],
            "runtime_identities": [runtime_identity],
            "aggregate_normalized_output_ref": aggregate_ref,
        }
        measurement_ref = self._store_json("measurement-asr.json", measurement)
        candidate_stage = {
            "candidate_stage_id": measurement["candidate_stage_id"],
            "adapter_role": "asr",
            "candidate_identity": candidate_identity,
            "unit_ids": measurement["unit_ids"],
            "stage_spec_digests": measurement["stage_spec_digests"],
            "stage_spec_document_refs": measurement["stage_spec_document_refs"],
            "attempt_ids": measurement["attempt_ids"],
            "cache_keys": measurement["cache_keys"],
            "input_ref_tuples": measurement["input_ref_tuples"],
            "output_ref_tuples": measurement["output_ref_tuples"],
            "raw_output_refs": measurement["raw_output_refs"],
            "runtime_identities": measurement["runtime_identities"],
            "aggregate_normalized_output_ref": aggregate_ref,
            "measurement_id": measurement["measurement_id"],
            "performance_measurement_ref": measurement_ref,
        }
        pack_audio_ref = self._store_bytes(
            "pack.wav", b"fixture-audio", kind="audio", media_type="audio/wav"
        )
        pack_manifest_ref = self._store_json(
            "pack-manifest.json", {"duration_ns": 600000000000}
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": "CalibrationRunManifest/v1",
            "run_id": measurement["run_id"],
            "run_kind": "independent_asr",
            "matrix_cell_id": measurement["matrix_cell_id"],
            "created_at": "2026-09-02T00:00:00Z",
            "status": "incomplete",
            "candidate_chain_hash": chain_hash,
            "pipeline_id": spec.pipeline_id,
            "pipeline_source_commit": "1" * 40,
            "attempt_record_mode": "canonical_path",
            "environment_runtime_version": RUNTIME_VERSION,
            "environment_schema_version": SCHEMA_VERSION,
            "environment_ref": environment_ref,
            "pack_manifest_ref": pack_manifest_ref,
            "pack_audio_ref": pack_audio_ref,
            "pack_hash": pack_manifest_ref["content_hash"],
            "pack_duration_ns": 600000000000,
            "candidate_config_hash": canonical_hash(
                [{"adapter_role": "asr", "config_hash": candidate.config_hash}]
            ),
            "style_hash": canonical_hash({"style": "calibration-only"}),
            "chunk_stitch_hash": canonical_hash({"chunk": "fixture"}),
            "candidate_stages": [candidate_stage],
            "correction_record_refs": [],
            "incomplete_reasons": [
                "environment",
                "model_snapshot",
                "corrections",
                "materialization",
                "timing",
                "nvml",
            ],
        }
        return manifest, measurement

    def build_report(self) -> tuple[dict[str, Any], dict[str, Any]]:
        manifest, measurement = self.build_independent_asr()
        manifest_ref = self._store_json("run-manifest.json", manifest)
        stage = manifest["candidate_stages"][0]
        report = {
            "schema_version": SCHEMA_VERSION,
            "kind": "CalibrationReport/v1",
            "report_id": "task031-report",
            "created_at": "2026-09-02T00:10:00Z",
            "status": "incomplete",
            "pack_hash": manifest["pack_hash"],
            "runs": [
                {
                    "run_id": manifest["run_id"],
                    "matrix_cell_id": manifest["matrix_cell_id"],
                    "manifest_ref": manifest_ref,
                    "measurement_ids": [stage["measurement_id"]],
                    "performance_measurement_refs": [stage["performance_measurement_ref"]],
                }
            ],
            "unsupported_metrics": ["lid_accuracy", "chrf2"],
            "incomplete_reasons": [
                "matrix_coverage",
                "measurement_coverage",
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
        return report, measurement


class SpineSchemaTests(ManifestReportCase):
    def test_closed_schemas_load_and_reject_extra_fields(self) -> None:
        manifest, _ = self.build_independent_asr()
        report, _ = self.build_report()
        validator = SchemaValidator(spine_schema_set())
        self.assertEqual(
            validator.validate(manifest, RUN_MANIFEST_SCHEMA_FILE, "manifest"), []
        )
        self.assertEqual(
            validator.validate(report, CALIBRATION_REPORT_SCHEMA_FILE, "report"), []
        )
        measurement = load_strict(
            self.runtime.store.absolute(
                manifest["candidate_stages"][0]["performance_measurement_ref"]["uri"],
                "measurement",
            )
        )
        self.assertEqual(
            validator.validate(
                measurement,
                PERFORMANCE_MEASUREMENT_SCHEMA_FILE,
                "measurement",
            ),
            [],
        )
        measurement["free_peak_vram"] = 1
        self.assertTrue(
            validator.validate(
                measurement,
                PERFORMANCE_MEASUREMENT_SCHEMA_FILE,
                "measurement",
            )
        )
        manifest["free_rtf"] = 0.1
        report["free_vram_bytes"] = 1
        self.assertTrue(
            validator.validate(manifest, RUN_MANIFEST_SCHEMA_FILE, "manifest")
        )
        self.assertTrue(
            validator.validate(report, CALIBRATION_REPORT_SCHEMA_FILE, "report")
        )


class ManifestPositiveTests(ManifestReportCase):
    def test_single_incomplete_manifest_binds_actual_measurement_and_attempt(self) -> None:
        manifest, _ = self.build_independent_asr()
        self.assertEqual(validate_calibration_run_manifest(manifest, self.root), [])

    def test_incomplete_report_links_one_manifest_without_claiming_coverage(self) -> None:
        report, _ = self.build_report()
        self.assertEqual(validate_calibration_report(report, self.root), [])


class ManifestMutationTests(ManifestReportCase):
    def codes(self, manifest: Any) -> set[str]:
        return {
            finding.code
            for finding in validate_calibration_run_manifest(manifest, self.root)
        }

    def test_run_kind_role_model_and_revision_are_cell_bound(self) -> None:
        manifest, _ = self.build_independent_asr()
        manifest["run_kind"] = "independent_mt"
        self.assertIn("E_MANIFEST_IDENTITY", self.codes(manifest))

        manifest, _ = self.build_independent_asr()
        manifest["candidate_stages"][0]["adapter_role"] = "mt"
        self.assertIn("E_MANIFEST_IDENTITY", self.codes(manifest))

        manifest, _ = self.build_independent_asr()
        manifest["candidate_stages"][0]["candidate_identity"]["model_revision"] = "2" * 40
        manifest["candidate_chain_hash"] = canonical_hash(
            [
                {
                    "adapter_role": "asr",
                    **manifest["candidate_stages"][0]["candidate_identity"],
                }
            ]
        )
        self.assertIn("E_MANIFEST_IDENTITY", self.codes(manifest))

    def test_measurement_projection_mismatch_fails(self) -> None:
        manifest, measurement = self.build_independent_asr()
        forged = copy.deepcopy(measurement)
        forged["run_id"] = "foreign-run"
        manifest["candidate_stages"][0]["performance_measurement_ref"] = self._store_json(
            "foreign-measurement.json", forged
        )
        self.assertIn("E_EVIDENCE_LINK", self.codes(manifest))

    def test_malformed_referenced_measurement_returns_findings_without_exception(self) -> None:
        manifest, measurement = self.build_independent_asr()
        measurement["candidate_stage_id"] = []
        manifest["candidate_stages"][0]["performance_measurement_ref"] = self._store_json(
            "malformed-measurement.json", measurement
        )
        self.assertTrue(validate_calibration_run_manifest(manifest, self.root))

    def test_unpaired_surrogate_measurement_returns_artifact_finding(self) -> None:
        manifest, _ = self.build_independent_asr()
        manifest["candidate_stages"][0]["performance_measurement_ref"] = self._store_bytes(
            "surrogate-measurement.json",
            b'{"run_id":"\\ud800"}',
            kind="text",
            media_type="application/json",
        )
        self.assertIn("E_CALIBRATION_ARTIFACT", self.codes(manifest))

    def test_pack_hash_is_bound_to_pack_manifest(self) -> None:
        manifest, _ = self.build_independent_asr()
        manifest["pack_hash"] = manifest["pack_audio_ref"]["content_hash"]
        self.assertIn("E_EVIDENCE_LINK", self.codes(manifest))

    def test_independent_run_rejects_final_pipeline_outputs(self) -> None:
        manifest, _ = self.build_independent_asr()
        manifest["final_pipeline_output_refs"] = [manifest["pack_audio_ref"]] * 4
        self.assertIn("E_FINAL_OUTPUTS", self.codes(manifest))

    def test_completed_claim_and_unexplained_missing_evidence_fail_closed(self) -> None:
        manifest, _ = self.build_independent_asr()
        manifest["status"] = "completed"
        manifest["incomplete_reasons"] = []
        self.assertIn("E_CALIBRATION_STATUS", self.codes(manifest))

    def test_malformed_unhashable_identity_returns_schema_findings(self) -> None:
        manifest, _ = self.build_independent_asr()
        for field in ("run_id", "run_kind", "matrix_cell_id"):
            malformed = copy.deepcopy(manifest)
            malformed[field] = []
            findings = validate_calibration_run_manifest(malformed, self.root)
            self.assertTrue(findings, field)


class ReportMutationTests(ManifestReportCase):
    def codes(self, report: Any) -> set[str]:
        return {
            finding.code for finding in validate_calibration_report(report, self.root)
        }

    def test_report_projection_mismatch_and_reuse_fail(self) -> None:
        report, _ = self.build_report()
        report["runs"][0]["run_id"] = "foreign-run"
        self.assertIn("E_EVIDENCE_LINK", self.codes(report))

        report, _ = self.build_report()
        report["runs"].append(copy.deepcopy(report["runs"][0]))
        codes = self.codes(report)
        self.assertIn("E_MATRIX_COVERAGE", codes)
        self.assertIn("E_MEASUREMENT_REUSE", codes)

    def test_dangling_or_noncanonical_manifest_ref_fails(self) -> None:
        report, _ = self.build_report()
        report["runs"][0]["manifest_ref"]["uri"] = "shadow/manifest.json"
        self.assertIn("E_CALIBRATION_ARTIFACT", self.codes(report))

    def test_completed_report_is_never_enabled_by_free_numbers(self) -> None:
        report, _ = self.build_report()
        report["status"] = "completed"
        report["incomplete_reasons"] = []
        self.assertIn("E_CALIBRATION_STATUS", self.codes(report))
        report["rtf"] = 0.0
        self.assertTrue(validate_calibration_report(report, self.root))

    def test_malformed_report_entry_returns_schema_findings(self) -> None:
        report, _ = self.build_report()
        for field in ("run_id", "matrix_cell_id", "manifest_ref"):
            malformed = copy.deepcopy(report)
            malformed["runs"][0][field] = []
            self.assertTrue(validate_calibration_report(malformed, self.root), field)

    def test_malformed_referenced_manifest_returns_findings_without_exception(self) -> None:
        report, _ = self.build_report()
        malformed_manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": "CalibrationRunManifest/v1",
            "run_id": [],
        }
        report["runs"][0]["manifest_ref"] = self._store_json(
            "malformed-manifest.json", malformed_manifest
        )
        self.assertTrue(validate_calibration_report(report, self.root))

    def test_unpaired_surrogate_manifest_returns_artifact_finding(self) -> None:
        report, _ = self.build_report()
        report["runs"][0]["manifest_ref"] = self._store_bytes(
            "surrogate-manifest.json",
            b'{"run_id":"\\ud800"}',
            kind="text",
            media_type="application/json",
        )
        self.assertIn("E_CALIBRATION_ARTIFACT", self.codes(report))


class ExactMatrixReportCase(ManifestReportCase):
    @staticmethod
    def _candidate_identity(
        role: str, model_id: str, revision: str
    ) -> dict[str, Any]:
        return {
            "official_model_id": model_id,
            "model_revision": revision,
            "weight_hash": canonical_hash(
                {"fixture_weight": model_id, "revision": revision}
            ),
            "backend_identity_hash": canonical_hash(
                {"fixture_backend": role, "version": "1.0.0"}
            ),
            "precision": "float16",
            "quantization": "none",
            "config_hash": canonical_hash(
                {
                    "fixture_candidate": model_id,
                    "role": role,
                    "decoding": "deterministic",
                }
            ),
        }

    @staticmethod
    def _chain_hash(stages: Sequence[dict[str, Any]]) -> str:
        return canonical_hash(
            [
                {
                    "adapter_role": stage["adapter_role"],
                    **stage["candidate_identity"],
                }
                for stage in stages
            ]
        )

    @staticmethod
    def _config_hash(stages: Sequence[dict[str, Any]]) -> str:
        return canonical_hash(
            [
                {
                    "adapter_role": stage["adapter_role"],
                    "config_hash": stage["candidate_identity"]["config_hash"],
                }
                for stage in stages
            ]
        )

    def _install_manifest(
        self,
        report: dict[str, Any],
        run_index: int,
        manifest: dict[str, Any],
        label: str,
    ) -> None:
        manifest_ref = self._store_json(f"{label}-manifest.json", manifest)
        report["runs"][run_index] = {
            "run_id": manifest["run_id"],
            "matrix_cell_id": manifest["matrix_cell_id"],
            "manifest_ref": manifest_ref,
            "measurement_ids": [
                stage["measurement_id"] for stage in manifest["candidate_stages"]
            ],
            "performance_measurement_refs": [
                stage["performance_measurement_ref"]
                for stage in manifest["candidate_stages"]
            ],
        }

    def _install_run(
        self,
        report: dict[str, Any],
        run_index: int,
        manifest: dict[str, Any],
        measurements: Sequence[dict[str, Any]],
        label: str,
    ) -> None:
        self.assertEqual(len(manifest["candidate_stages"]), len(measurements))
        for stage_index, (stage, measurement) in enumerate(
            zip(manifest["candidate_stages"], measurements, strict=True)
        ):
            stage["performance_measurement_ref"] = self._store_json(
                f"{label}-measurement-{stage_index}.json", measurement
            )
        self._install_manifest(report, run_index, manifest, label)

    def build_exact_matrix(
        self,
    ) -> tuple[
        dict[str, Any], list[dict[str, Any]], list[list[dict[str, Any]]]
    ]:
        self.assertEqual(
            tuple(case[0] for case in MATRIX_FIXTURE_CASES), MATRIX_CELL_ORDER
        )
        environment_ref = self._store_json(
            "matrix-environment.json",
            {"kind": "fixture_environment", "pending": True},
        )
        pack_audio_ref = self._store_bytes(
            "matrix-pack.wav",
            b"synthetic calibration audio",
            kind="audio",
            media_type="audio/wav",
        )
        pack_manifest_ref = self._store_json(
            "matrix-pack-manifest.json",
            {
                "kind": "fixture_pack",
                "duration_ns": 600000000000,
                "unit_ids": ["unit-0001"],
            },
        )
        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "kind": "CalibrationReport/v1",
            "report_id": "task031-exact-matrix-report",
            "created_at": "2026-09-02T00:10:00Z",
            "status": "incomplete",
            "pack_hash": pack_manifest_ref["content_hash"],
            "runs": [],
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
        manifests: list[dict[str, Any]] = []
        all_measurements: list[list[dict[str, Any]]] = []

        for cell_id, run_kind, candidates in MATRIX_FIXTURE_CASES:
            identities = [
                self._candidate_identity(role, model_id, revision)
                for role, model_id, revision in candidates
            ]
            runtime_stages = [
                StageSpec(
                    stage_id="source",
                    implementation_version="fixture-source/1.0.0",
                    config_hash=canonical_hash({"fixture_source": cell_id}),
                )
            ]
            for candidate_index, ((role, _, _), identity) in enumerate(
                zip(candidates, identities, strict=True)
            ):
                dependency = "source" if candidate_index == 0 else candidates[0][0]
                runtime_stages.append(
                    StageSpec(
                        stage_id=role,
                        implementation_version=f"fixture-{role}/1.0.0",
                        depends_on=(dependency,),
                        config_hash=identity["config_hash"],
                        dependency_fingerprint=identity["backend_identity_hash"],
                        model_hash=identity["weight_hash"],
                        random_seed=7,
                        reproducibility_tier="T2",
                    )
                )
            spec = JobSpec(
                job_id=f"job-{cell_id}",
                pipeline_id="task031-synthetic-matrix",
                source_identity=f"fixture-source-{cell_id}",
                stages=tuple(runtime_stages),
            )
            stage_spec_evidence = {
                stage.stage_id: store_stage_spec_identity(
                    self.runtime.store, spec, stage
                )
                for stage in runtime_stages[1:]
            }
            callables = {
                "source": emit_many((("source.bin", "same synthetic source"),))
            }
            for role, _, _ in candidates:
                callables[role] = emit_many(
                    (("raw.json", '{"text":"same synthetic candidate output"}'),)
                )
            result = self.runtime.run_job(spec, callables)
            self.assertEqual(result.status, "completed")

            candidate_stages: list[dict[str, Any]] = []
            measurements: list[dict[str, Any]] = []
            chain_hash = canonical_hash(
                [
                    {"adapter_role": role, **identity}
                    for (role, _, _), identity in zip(
                        candidates, identities, strict=True
                    )
                ]
            )
            for (role, _, _), identity in zip(
                candidates, identities, strict=True
            ):
                stage = next(entry for entry in runtime_stages if entry.stage_id == role)
                outcome = result.outcome(role)
                self.assertEqual(outcome.cache_status, "miss")
                self.assertTrue(outcome.callable_invoked)
                attempt = load_strict(self.root / outcome.attempt_path)
                stage_spec_digest, stage_spec_ref = stage_spec_evidence[role]
                runtime_identity = {
                    "job_id": spec.job_id,
                    "runtime_stage_id": role,
                    "attempt_id": outcome.attempt_id,
                    "attempt_record_ref": outcome.attempt_path,
                    "cache_key": outcome.cache_key,
                    "stage_spec_digest": stage_spec_digest,
                    "stage_spec_document_ref": stage_spec_ref,
                    "input_ref_tuple": attempt["inputs"],
                    "output_ref_tuple": attempt["outputs"],
                    "dependency_cache_keys": {
                        dependency: result.outcome(dependency).cache_key
                        for dependency in stage.depends_on
                    },
                }
                aggregate_ref = self._store_json(
                    f"aggregate-{cell_id}-{role}.json",
                    {
                        "kind": "fixture_normalized_output",
                        "matrix_cell_id": cell_id,
                        "adapter_role": role,
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
                    "measurement_id": f"measurement-{cell_id}-{role}",
                    "run_id": f"run-{cell_id}",
                    "matrix_cell_id": cell_id,
                    "candidate_stage_id": f"candidate-{cell_id}-{role}",
                    "adapter_role": role,
                    "candidate_identity": identity,
                    "candidate_chain_hash": chain_hash,
                    "attempt_record_mode": "canonical_path",
                    "pipeline_id": spec.pipeline_id,
                    "environment_runtime_version": RUNTIME_VERSION,
                    "environment_schema_version": SCHEMA_VERSION,
                    "environment_ref": environment_ref,
                    "unit_ids": [f"unit-{cell_id}-{role}"],
                    "stage_spec_digests": [stage_spec_digest],
                    "stage_spec_document_refs": [stage_spec_ref],
                    "attempt_ids": [outcome.attempt_id],
                    "cache_keys": [outcome.cache_key],
                    "input_ref_tuples": [attempt["inputs"]],
                    "output_ref_tuples": [attempt["outputs"]],
                    "raw_output_refs": [attempt["outputs"][0]],
                    "runtime_identities": [runtime_identity],
                    "aggregate_normalized_output_ref": aggregate_ref,
                }
                measurement_ref = self._store_json(
                    f"measurement-{cell_id}-{role}.json", measurement
                )
                candidate_stage = {
                    "candidate_stage_id": measurement["candidate_stage_id"],
                    "adapter_role": role,
                    "candidate_identity": identity,
                    **{
                        field: measurement[field]
                        for field in RUNTIME_ARRAY_FIELDS
                    },
                    "aggregate_normalized_output_ref": aggregate_ref,
                    "measurement_id": measurement["measurement_id"],
                    "performance_measurement_ref": measurement_ref,
                }
                measurements.append(measurement)
                candidate_stages.append(candidate_stage)

            incomplete_reasons = [
                "environment",
                "model_snapshot",
                "corrections",
                "materialization",
                "timing",
                "nvml",
            ]
            if run_kind == "end_to_end":
                incomplete_reasons.extend(["interruption", "final_outputs"])
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "kind": "CalibrationRunManifest/v1",
                "run_id": f"run-{cell_id}",
                "run_kind": run_kind,
                "matrix_cell_id": cell_id,
                "created_at": "2026-09-02T00:00:00Z",
                "status": "incomplete",
                "candidate_chain_hash": chain_hash,
                "pipeline_id": spec.pipeline_id,
                "pipeline_source_commit": "1" * 40,
                "attempt_record_mode": "canonical_path",
                "environment_runtime_version": RUNTIME_VERSION,
                "environment_schema_version": SCHEMA_VERSION,
                "environment_ref": environment_ref,
                "pack_manifest_ref": pack_manifest_ref,
                "pack_audio_ref": pack_audio_ref,
                "pack_hash": pack_manifest_ref["content_hash"],
                "pack_duration_ns": 600000000000,
                "candidate_config_hash": self._config_hash(candidate_stages),
                "style_hash": canonical_hash({"style": "calibration-only"}),
                "chunk_stitch_hash": canonical_hash({"chunk": "fixture"}),
                "candidate_stages": candidate_stages,
                "correction_record_refs": [],
                "incomplete_reasons": incomplete_reasons,
            }
            manifest_ref = self._store_json(f"manifest-{cell_id}.json", manifest)
            report["runs"].append(
                {
                    "run_id": manifest["run_id"],
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
            manifests.append(manifest)
            all_measurements.append(measurements)
        return report, manifests, all_measurements

    def report_codes(self, report: dict[str, Any]) -> set[str]:
        return {
            finding.code for finding in validate_calibration_report(report, self.root)
        }


class ExactMatrixPositiveTests(ExactMatrixReportCase):
    def test_exact_eight_cells_and_twelve_actual_attempts_pass_incomplete(self) -> None:
        report, manifests, all_measurements = self.build_exact_matrix()
        stages = [
            stage for manifest in manifests for stage in manifest["candidate_stages"]
        ]
        measurements = [
            measurement
            for run_measurements in all_measurements
            for measurement in run_measurements
        ]
        runtime_identities = [
            identity
            for measurement in measurements
            for identity in measurement["runtime_identities"]
        ]

        self.assertEqual(len(report["runs"]), 8)
        self.assertEqual(len(stages), 12)
        self.assertEqual(len({stage["candidate_stage_id"] for stage in stages}), 12)
        self.assertEqual(len({stage["measurement_id"] for stage in stages}), 12)
        self.assertEqual(
            len(
                {
                    (
                        stage["performance_measurement_ref"]["uri"],
                        stage["performance_measurement_ref"]["content_hash"],
                    )
                    for stage in stages
                }
            ),
            12,
        )
        self.assertEqual(
            len(
                {
                    (
                        identity["job_id"],
                        identity["runtime_stage_id"],
                        identity["attempt_id"],
                    )
                    for identity in runtime_identities
                }
            ),
            12,
        )
        self.assertEqual(
            len({identity["attempt_record_ref"] for identity in runtime_identities}),
            12,
        )
        self.assertEqual(
            len(
                {
                    ref["content_hash"]
                    for measurement in measurements
                    for ref in measurement["raw_output_refs"]
                }
            ),
            1,
        )
        for manifest in manifests:
            self.assertEqual(validate_calibration_run_manifest(manifest, self.root), [])
        self.assertEqual(validate_calibration_report(report, self.root), [])


class ExactMatrixMutationTests(ExactMatrixReportCase):
    @staticmethod
    def _coordinates(manifests: Sequence[dict[str, Any]]) -> list[tuple[int, int]]:
        return [
            (run_index, stage_index)
            for run_index, manifest in enumerate(manifests)
            for stage_index in range(len(manifest["candidate_stages"]))
        ]

    def test_each_missing_cell_and_added_ninth_cell_fail_closed(self) -> None:
        report, _, _ = self.build_exact_matrix()
        for run_index, case in enumerate(MATRIX_FIXTURE_CASES):
            with self.subTest(missing_cell=case[0]):
                mutated = copy.deepcopy(report)
                del mutated["runs"][run_index]
                self.assertIn("E_CALIBRATION_STATUS", self.report_codes(mutated))

        added = copy.deepcopy(report)
        added["runs"].append(copy.deepcopy(added["runs"][0]))
        self.assertTrue(validate_calibration_report(added, self.root))

    def test_each_missing_or_added_candidate_stage_fails_closed(self) -> None:
        report, manifests, all_measurements = self.build_exact_matrix()
        for run_index, stage_index in self._coordinates(manifests):
            with self.subTest(
                missing_stage=(
                    manifests[run_index]["matrix_cell_id"],
                    stage_index,
                )
            ):
                mutated_report = copy.deepcopy(report)
                manifest = copy.deepcopy(manifests[run_index])
                measurements = copy.deepcopy(all_measurements[run_index])
                del manifest["candidate_stages"][stage_index]
                del measurements[stage_index]
                manifest["candidate_chain_hash"] = self._chain_hash(
                    manifest["candidate_stages"]
                )
                manifest["candidate_config_hash"] = self._config_hash(
                    manifest["candidate_stages"]
                )
                for measurement in measurements:
                    measurement["candidate_chain_hash"] = manifest[
                        "candidate_chain_hash"
                    ]
                self._install_run(
                    mutated_report,
                    run_index,
                    manifest,
                    measurements,
                    f"missing-{run_index}-{stage_index}",
                )
                self.assertTrue(
                    validate_calibration_report(mutated_report, self.root)
                )

        for run_index, manifest_source in enumerate(manifests):
            with self.subTest(added_stage=manifest_source["matrix_cell_id"]):
                mutated_report = copy.deepcopy(report)
                manifest = copy.deepcopy(manifest_source)
                measurements = copy.deepcopy(all_measurements[run_index])
                extra_stage = copy.deepcopy(manifest["candidate_stages"][0])
                extra_measurement = copy.deepcopy(measurements[0])
                extra_stage["candidate_stage_id"] += "-extra"
                extra_stage["measurement_id"] += "-extra"
                extra_measurement["candidate_stage_id"] = extra_stage[
                    "candidate_stage_id"
                ]
                extra_measurement["measurement_id"] = extra_stage["measurement_id"]
                manifest["candidate_stages"].append(extra_stage)
                measurements.append(extra_measurement)
                manifest["candidate_chain_hash"] = self._chain_hash(
                    manifest["candidate_stages"]
                )
                manifest["candidate_config_hash"] = self._config_hash(
                    manifest["candidate_stages"]
                )
                for measurement in measurements:
                    measurement["candidate_chain_hash"] = manifest[
                        "candidate_chain_hash"
                    ]
                self._install_run(
                    mutated_report,
                    run_index,
                    manifest,
                    measurements,
                    f"added-{run_index}",
                )
                self.assertTrue(
                    validate_calibration_report(mutated_report, self.root)
                )

    def test_every_adjacent_cell_swap_and_end_to_end_stage_swap_fail(self) -> None:
        report, manifests, all_measurements = self.build_exact_matrix()
        for run_index in range(len(report["runs"]) - 1):
            with self.subTest(cell_swap=run_index):
                mutated = copy.deepcopy(report)
                mutated["runs"][run_index], mutated["runs"][run_index + 1] = (
                    mutated["runs"][run_index + 1],
                    mutated["runs"][run_index],
                )
                self.assertIn("E_MATRIX_COVERAGE", self.report_codes(mutated))

        for run_index in range(4, 8):
            with self.subTest(stage_swap=manifests[run_index]["matrix_cell_id"]):
                mutated_report = copy.deepcopy(report)
                manifest = copy.deepcopy(manifests[run_index])
                measurements = copy.deepcopy(all_measurements[run_index])
                manifest["candidate_stages"].reverse()
                measurements.reverse()
                manifest["candidate_chain_hash"] = self._chain_hash(
                    manifest["candidate_stages"]
                )
                manifest["candidate_config_hash"] = self._config_hash(
                    manifest["candidate_stages"]
                )
                for measurement in measurements:
                    measurement["candidate_chain_hash"] = manifest[
                        "candidate_chain_hash"
                    ]
                self._install_run(
                    mutated_report,
                    run_index,
                    manifest,
                    measurements,
                    f"stage-swap-{run_index}",
                )
                self.assertIn(
                    "E_MANIFEST_IDENTITY", self.report_codes(mutated_report)
                )

    def test_each_foreign_manifest_and_foreign_candidate_config_fail(self) -> None:
        report, manifests, all_measurements = self.build_exact_matrix()
        for run_index, manifest in enumerate(manifests):
            with self.subTest(foreign_manifest=manifest["matrix_cell_id"]):
                mutated = copy.deepcopy(report)
                foreign_index = (run_index + 1) % len(manifests)
                mutated["runs"][run_index]["manifest_ref"] = report["runs"][
                    foreign_index
                ]["manifest_ref"]
                self.assertIn("E_EVIDENCE_LINK", self.report_codes(mutated))

        for run_index, stage_index in self._coordinates(manifests):
            with self.subTest(
                foreign_config=(
                    manifests[run_index]["matrix_cell_id"],
                    stage_index,
                )
            ):
                mutated_report = copy.deepcopy(report)
                manifest = copy.deepcopy(manifests[run_index])
                measurements = copy.deepcopy(all_measurements[run_index])
                foreign_hash = canonical_hash(
                    {
                        "foreign_config": manifest["matrix_cell_id"],
                        "stage_index": stage_index,
                    }
                )
                manifest["candidate_stages"][stage_index]["candidate_identity"][
                    "config_hash"
                ] = foreign_hash
                measurements[stage_index]["candidate_identity"][
                    "config_hash"
                ] = foreign_hash
                manifest["candidate_chain_hash"] = self._chain_hash(
                    manifest["candidate_stages"]
                )
                manifest["candidate_config_hash"] = self._config_hash(
                    manifest["candidate_stages"]
                )
                for measurement in measurements:
                    measurement["candidate_chain_hash"] = manifest[
                        "candidate_chain_hash"
                    ]
                self._install_run(
                    mutated_report,
                    run_index,
                    manifest,
                    measurements,
                    f"foreign-config-{run_index}-{stage_index}",
                )
                self.assertIn(
                    "E_STAGE_SPEC_FINGERPRINT", self.report_codes(mutated_report)
                )

    def test_each_measurement_and_attempt_reuse_fails_but_cas_dedup_does_not(self) -> None:
        report, manifests, all_measurements = self.build_exact_matrix()
        coordinates = self._coordinates(manifests)
        source_stage = manifests[0]["candidate_stages"][0]
        source_measurement = all_measurements[0][0]

        for run_index, stage_index in coordinates[1:]:
            with self.subTest(
                measurement_reuse=(
                    manifests[run_index]["matrix_cell_id"],
                    stage_index,
                )
            ):
                mutated_report = copy.deepcopy(report)
                manifest = copy.deepcopy(manifests[run_index])
                target_stage = manifest["candidate_stages"][stage_index]
                target_stage["measurement_id"] = source_stage["measurement_id"]
                target_stage["performance_measurement_ref"] = source_stage[
                    "performance_measurement_ref"
                ]
                self._install_manifest(
                    mutated_report,
                    run_index,
                    manifest,
                    f"measurement-reuse-{run_index}-{stage_index}",
                )
                self.assertIn(
                    "E_MEASUREMENT_REUSE", self.report_codes(mutated_report)
                )

            with self.subTest(
                attempt_reuse=(
                    manifests[run_index]["matrix_cell_id"],
                    stage_index,
                )
            ):
                mutated_report = copy.deepcopy(report)
                manifest = copy.deepcopy(manifests[run_index])
                measurements = copy.deepcopy(all_measurements[run_index])
                target_stage = manifest["candidate_stages"][stage_index]
                target_measurement = measurements[stage_index]
                for field in RUNTIME_ARRAY_FIELDS:
                    target_measurement[field] = copy.deepcopy(
                        source_measurement[field]
                    )
                    target_stage[field] = copy.deepcopy(source_measurement[field])
                self._install_run(
                    mutated_report,
                    run_index,
                    manifest,
                    measurements,
                    f"attempt-reuse-{run_index}-{stage_index}",
                )
                self.assertIn("E_ATTEMPT_REUSE", self.report_codes(mutated_report))

        self.assertEqual(validate_calibration_report(report, self.root), [])


if __name__ == "__main__":
    unittest.main()
