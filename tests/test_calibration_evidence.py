"""TASK-031 offline evidence core unit·mutation tests."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from media_clarity.calibration.evidence import (
    STAGE_SPEC_SCHEMA_FILE,
    evidence_schema_set,
    stage_spec_identity_document,
    store_stage_spec_identity,
    validate_measurement_runtime_evidence,
    validate_measurement_runtime_evidence_set,
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
    write_json_atomic,
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


class CalibrationEvidenceCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory(prefix="mcs-task031-evidence-")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.runtime = JobRuntime(self.root)

    def spec(self, job_id: str) -> JobSpec:
        return JobSpec(
            job_id=job_id,
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
                    model_hash=canonical_hash({"model": "fixture"}),
                    random_seed=7,
                    reproducibility_tier="T2",
                ),
            ),
        )

    def build_measurement(
        self,
        *,
        job_id: str = "job-a",
        measurement_id: str = "measurement-a",
        run_id: str = "run-a",
        candidate_stage_id: str = "candidate-a",
    ) -> tuple[dict[str, Any], JobSpec, dict[str, Any]]:
        spec = self.spec(job_id)
        candidate = spec.stages[1]
        digest, document_ref = store_stage_spec_identity(self.runtime.store, spec, candidate)
        result = self.runtime.run_job(
            spec,
            {
                "source": emit_many((("b.txt", "two"), ("a.txt", "one"))),
                "candidate": emit_many((("raw.json", '{"text":"same bytes"}'),)),
            },
        )
        source_outcome = result.outcome("source")
        candidate_outcome = result.outcome("candidate")
        attempt = load_strict(self.root / candidate_outcome.attempt_path)
        identity = {
            "job_id": job_id,
            "runtime_stage_id": "candidate",
            "attempt_id": candidate_outcome.attempt_id,
            "attempt_record_ref": candidate_outcome.attempt_path,
            "cache_key": candidate_outcome.cache_key,
            "stage_spec_digest": digest,
            "stage_spec_document_ref": document_ref,
            "input_ref_tuple": attempt["inputs"],
            "output_ref_tuple": attempt["outputs"],
            "dependency_cache_keys": {"source": source_outcome.cache_key},
        }
        measurement = {
            "measurement_id": measurement_id,
            "run_id": run_id,
            "matrix_cell_id": "e2e-faster-whisper__madlad",
            "candidate_stage_id": candidate_stage_id,
            "adapter_role": "asr",
            "attempt_record_mode": "canonical_path",
            "pipeline_id": spec.pipeline_id,
            "environment_runtime_version": RUNTIME_VERSION,
            "environment_schema_version": SCHEMA_VERSION,
            "unit_ids": ["unit-0001"],
            "stage_spec_digests": [digest],
            "stage_spec_document_refs": [document_ref],
            "attempt_ids": [candidate_outcome.attempt_id],
            "cache_keys": [candidate_outcome.cache_key],
            "input_ref_tuples": [attempt["inputs"]],
            "output_ref_tuples": [attempt["outputs"]],
            "raw_output_refs": [attempt["outputs"][0]],
            "runtime_identities": [identity],
        }
        return measurement, spec, attempt

    def codes(self, measurement: dict[str, Any]) -> set[str]:
        return {
            finding.code
            for finding in validate_measurement_runtime_evidence(measurement, self.root)
        }


class StageSpecIdentityTests(CalibrationEvidenceCase):
    def test_document_has_exact_closed_shape_and_canonical_cas_bytes(self) -> None:
        spec = self.spec("job-a")
        stage = spec.stages[1]
        document = stage_spec_identity_document(spec, stage)
        self.assertEqual(
            SchemaValidator(evidence_schema_set()).validate(
                document, STAGE_SPEC_SCHEMA_FILE, "stage_spec"
            ),
            [],
        )
        digest, ref = store_stage_spec_identity(self.runtime.store, spec, stage)
        self.assertEqual(ref["content_hash"], digest)
        self.assertEqual(
            self.runtime.store.absolute(ref["uri"], "ref").read_bytes(),
            canonical_json_bytes(document),
        )

    def test_schema_rejects_missing_null_field_and_extra_field(self) -> None:
        document = stage_spec_identity_document(self.spec("job-a"), self.spec("job-a").stages[1])
        validator = SchemaValidator(evidence_schema_set())
        missing = copy.deepcopy(document)
        del missing["context_hash"]
        extra = {**document, "stage_spec_fingerprint": canonical_hash({"invented": True})}
        self.assertTrue(validator.validate(missing, STAGE_SPEC_SCHEMA_FILE, "missing"))
        self.assertTrue(validator.validate(extra, STAGE_SPEC_SCHEMA_FILE, "extra"))


class RuntimeIdentityPositiveTests(CalibrationEvidenceCase):
    def test_actual_task028_attempt_is_accepted(self) -> None:
        measurement, _, _ = self.build_measurement()
        self.assertEqual(
            validate_measurement_runtime_evidence(measurement, self.root), []
        )

    def test_distinct_attempts_may_share_cas_bytes(self) -> None:
        first, _, _ = self.build_measurement()
        second, _, _ = self.build_measurement(
            job_id="job-b",
            measurement_id="measurement-b",
            run_id="run-b",
            candidate_stage_id="candidate-b",
        )
        first_raw = first["raw_output_refs"][0]
        second_raw = second["raw_output_refs"][0]
        self.assertEqual(first_raw["content_hash"], second_raw["content_hash"])
        self.assertEqual(first_raw["uri"], second_raw["uri"])
        self.assertEqual(
            validate_measurement_runtime_evidence_set((first, second), self.root), []
        )


class RuntimeIdentityMutationTests(CalibrationEvidenceCase):
    def test_missing_projection_field_fails_closed(self) -> None:
        measurement, _, _ = self.build_measurement()
        del measurement["stage_spec_document_refs"]
        self.assertIn("E_MEASUREMENT_IDENTITY", self.codes(measurement))

    def test_independent_matrix_cell_rejects_wrong_adapter_role(self) -> None:
        measurement, _, _ = self.build_measurement()
        measurement["matrix_cell_id"] = "mt-madlad"
        measurement["adapter_role"] = "asr"
        self.assertIn("E_MEASUREMENT_IDENTITY", self.codes(measurement))

    def test_runtime_stage_alias_and_canonical_attempt_path_are_bound(self) -> None:
        measurement, _, _ = self.build_measurement()
        measurement["runtime_identities"][0]["runtime_stage_id"] = "other"
        self.assertIn("E_ATTEMPT_RECORD", self.codes(measurement))

    def test_ordered_inputs_are_exact(self) -> None:
        measurement, _, _ = self.build_measurement()
        reversed_inputs = list(reversed(measurement["input_ref_tuples"][0]))
        measurement["input_ref_tuples"][0] = reversed_inputs
        measurement["runtime_identities"][0]["input_ref_tuple"] = reversed_inputs
        self.assertIn("E_RUNTIME_IDENTITY", self.codes(measurement))

    def test_output_omission_and_raw_substitution_fail(self) -> None:
        measurement, _, _ = self.build_measurement()
        measurement["output_ref_tuples"][0] = []
        measurement["runtime_identities"][0]["output_ref_tuple"] = []
        self.assertIn("E_RUNTIME_IDENTITY", self.codes(measurement))

        measurement, _, _ = self.build_measurement(job_id="job-b")
        measurement["raw_output_refs"][0] = measurement["input_ref_tuples"][0][0]
        self.assertIn("E_OUTPUT_BINDING", self.codes(measurement))

    def test_multi_output_attempt_is_never_a_measured_unit(self) -> None:
        measurement, _, attempt = self.build_measurement()
        attempt["outputs"].append(attempt["inputs"][0])
        identity = measurement["runtime_identities"][0]
        identity["output_ref_tuple"] = attempt["outputs"]
        measurement["output_ref_tuples"][0] = attempt["outputs"]
        write_json_atomic(self.root / identity["attempt_record_ref"], attempt)
        self.assertIn("E_OUTPUT_CARDINALITY", self.codes(measurement))

    def test_document_digest_is_not_a_free_string(self) -> None:
        measurement, _, _ = self.build_measurement()
        forged = canonical_hash({"forged": True})
        measurement["stage_spec_digests"][0] = forged
        measurement["runtime_identities"][0]["stage_spec_digest"] = forged
        self.assertIn("E_STAGE_SPEC_IDENTITY", self.codes(measurement))

    def test_fingerprint_mutation_is_bound_to_attempt_record(self) -> None:
        measurement, spec, _ = self.build_measurement()
        stage = StageSpec(
            **{
                **spec.stages[1].__dict__,
                "config_hash": canonical_hash({"candidate": "forged"}),
            }
        )
        digest, ref = store_stage_spec_identity(self.runtime.store, spec, stage)
        measurement["stage_spec_digests"][0] = digest
        measurement["stage_spec_document_refs"][0] = ref
        identity = measurement["runtime_identities"][0]
        identity["stage_spec_digest"] = digest
        identity["stage_spec_document_ref"] = ref
        self.assertIn("E_STAGE_SPEC_FINGERPRINT", self.codes(measurement))

    def test_cacheable_mutation_fails_even_when_cache_key_would_match(self) -> None:
        measurement, spec, _ = self.build_measurement()
        forged_stage = StageSpec(**{**spec.stages[1].__dict__, "cacheable": False})
        digest, ref = store_stage_spec_identity(self.runtime.store, spec, forged_stage)
        measurement["stage_spec_digests"][0] = digest
        measurement["stage_spec_document_refs"][0] = ref
        identity = measurement["runtime_identities"][0]
        identity["stage_spec_digest"] = digest
        identity["stage_spec_document_ref"] = ref
        self.assertIn("E_STAGE_SPEC_CACHEABLE", self.codes(measurement))

    def test_missing_attempt_cacheable_fails_closed(self) -> None:
        measurement, _, attempt = self.build_measurement()
        identity = measurement["runtime_identities"][0]
        del attempt["cacheable"]
        write_json_atomic(self.root / identity["attempt_record_ref"], attempt)
        self.assertIn("E_STAGE_SPEC_CACHEABLE", self.codes(measurement))

    def test_depends_on_must_equal_dependency_cache_key_set(self) -> None:
        measurement, spec, _ = self.build_measurement()
        forged_stage = StageSpec(**{**spec.stages[1].__dict__, "depends_on": ()})
        digest, ref = store_stage_spec_identity(self.runtime.store, spec, forged_stage)
        measurement["stage_spec_digests"][0] = digest
        measurement["stage_spec_document_refs"][0] = ref
        identity = measurement["runtime_identities"][0]
        identity["stage_spec_digest"] = digest
        identity["stage_spec_document_ref"] = ref
        self.assertIn("E_DEPENDENCY_CACHE_KEYS", self.codes(measurement))

    def test_dependency_cache_keys_require_stage_ids_and_content_hashes(self) -> None:
        measurement, _, _ = self.build_measurement()
        measurement["runtime_identities"][0]["dependency_cache_keys"] = {
            "source": "arbitrary-version-string"
        }
        self.assertIn("E_DEPENDENCY_CACHE_KEYS", self.codes(measurement))

    def test_cache_key_is_rebuilt_from_attempt_inputs(self) -> None:
        measurement, _, _ = self.build_measurement()
        forged = canonical_hash({"cache": "forged"})
        measurement["cache_keys"][0] = forged
        measurement["runtime_identities"][0]["cache_key"] = forged
        self.assertIn("E_RUNTIME_IDENTITY", self.codes(measurement))

    def test_cache_hit_record_cannot_be_performance_evidence(self) -> None:
        measurement, _, attempt = self.build_measurement()
        identity = measurement["runtime_identities"][0]
        attempt["cache_status"] = "hit"
        attempt["cache_reason"] = "verified_checkpoint"
        attempt["callable_invoked"] = False
        write_json_atomic(self.root / identity["attempt_record_ref"], attempt)
        self.assertIn("E_ATTEMPT_EXECUTION", self.codes(measurement))

    def test_missing_attempt_record_fails_closed(self) -> None:
        measurement, _, _ = self.build_measurement()
        path = self.root / measurement["runtime_identities"][0]["attempt_record_ref"]
        path.unlink()
        self.assertIn("E_ATTEMPT_RECORD", self.codes(measurement))

    def test_attempt_identity_and_record_ref_cannot_be_reused(self) -> None:
        first, _, _ = self.build_measurement()
        second = copy.deepcopy(first)
        second["measurement_id"] = "measurement-b"
        second["run_id"] = "run-b"
        second["candidate_stage_id"] = "candidate-b"
        codes = {
            finding.code
            for finding in validate_measurement_runtime_evidence_set(
                (first, second), self.root
            )
        }
        self.assertIn("E_ATTEMPT_REUSE", codes)


if __name__ == "__main__":
    unittest.main()
