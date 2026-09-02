from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from media_clarity.calibration.evidence import store_stage_spec_identity
from media_clarity.calibration.spine import (
    CALIBRATION_REPORT_SCHEMA_FILE,
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


if __name__ == "__main__":
    unittest.main()
