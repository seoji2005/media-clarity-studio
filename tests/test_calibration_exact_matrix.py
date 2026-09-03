"""TASK-031 exact 8-cell/12-stage synthetic coverage and mutation matrix."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from media_clarity.calibration.spine import (
    MATRIX_CELL_ORDER,
    validate_calibration_report,
)
from media_clarity.job_runtime import canonical_hash

from task031_matrix_fixture import (
    MEASUREMENT_PROJECTION_FIELDS,
    ExactMatrixFixtureBuilder,
)


class ExactMatrixValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = TemporaryDirectory(prefix="mcs-task031-exact-matrix-")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.builder = ExactMatrixFixtureBuilder(self.root)
        self.fixture = self.builder.build()

    def codes(self, report: Any) -> set[str]:
        return {
            finding.code for finding in validate_calibration_report(report, self.root)
        }

    def entry(self, report: dict[str, Any], cell_id: str) -> dict[str, Any]:
        return next(
            entry for entry in report["runs"] if entry["matrix_cell_id"] == cell_id
        )

    def replace_manifest(
        self,
        report: dict[str, Any],
        cell_id: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        entry = self.entry(report, cell_id)
        manifest = self.builder.load_json_ref(entry["manifest_ref"])
        mutate(manifest)
        entry["manifest_ref"] = self.builder.store_json(
            f"mutated-manifest-{cell_id}.json", manifest
        )
        entry["measurement_ids"] = [
            stage["measurement_id"] for stage in manifest["candidate_stages"]
        ]
        entry["performance_measurement_refs"] = [
            stage["performance_measurement_ref"]
            for stage in manifest["candidate_stages"]
        ]
        return manifest

    def test_exact_eight_cells_and_twelve_candidate_stages_are_accepted(self) -> None:
        report = self.fixture.report
        self.assertEqual(
            [entry["matrix_cell_id"] for entry in report["runs"]],
            list(MATRIX_CELL_ORDER),
        )
        self.assertEqual(len(report["runs"]), 8)
        self.assertEqual(
            sum(len(entry["measurement_ids"]) for entry in report["runs"]), 12
        )
        attempt_identities: list[tuple[str, str, str]] = []
        attempt_record_refs: list[str] = []
        for entry in report["runs"]:
            manifest = self.builder.load_json_ref(entry["manifest_ref"])
            expected_stage_count = 2 if manifest["run_kind"] == "end_to_end" else 1
            self.assertEqual(len(manifest["candidate_stages"]), expected_stage_count)
            for stage in manifest["candidate_stages"]:
                for identity in stage["runtime_identities"]:
                    attempt_identities.append(
                        (
                            identity["job_id"],
                            identity["runtime_stage_id"],
                            identity["attempt_id"],
                        )
                    )
                    attempt_record_refs.append(identity["attempt_record_ref"])
        self.assertEqual(len(attempt_identities), 12)
        self.assertEqual(len(set(attempt_identities)), 12)
        self.assertEqual(len(set(attempt_record_refs)), 12)
        self.assertEqual(validate_calibration_report(report, self.root), [])

    def test_matrix_cell_coverage_mutations_fail_closed(self) -> None:
        mutations: tuple[
            tuple[str, Callable[[dict[str, Any]], None], str], ...
        ] = (
            (
                "missing_cell",
                lambda report: report["runs"].pop(),
                "E_CALIBRATION_STATUS",
            ),
            (
                "extra_cell",
                lambda report: report["runs"].append(
                    copy.deepcopy(report["runs"][0])
                ),
                "E_SCHEMA",
            ),
            (
                "reordered_cells",
                lambda report: report["runs"].__setitem__(
                    slice(0, 2), list(reversed(report["runs"][:2]))
                ),
                "E_MATRIX_COVERAGE",
            ),
            (
                "duplicate_replaces_cell",
                lambda report: report["runs"].__setitem__(
                    -1, copy.deepcopy(report["runs"][0])
                ),
                "E_MATRIX_COVERAGE",
            ),
        )
        for name, mutate, expected_code in mutations:
            with self.subTest(name=name):
                report = copy.deepcopy(self.fixture.report)
                mutate(report)
                self.assertIn(expected_code, self.codes(report))

    def test_candidate_stage_coverage_mutations_fail_closed(self) -> None:
        report = copy.deepcopy(self.fixture.report)
        self.replace_manifest(
            report,
            "e2e-faster-whisper__madlad",
            lambda manifest: manifest["candidate_stages"].pop(),
        )
        codes = self.codes(report)
        self.assertIn("E_MANIFEST_IDENTITY", codes)
        self.assertIn("E_CALIBRATION_STATUS", codes)

        report = copy.deepcopy(self.fixture.report)

        def append_duplicate(manifest: dict[str, Any]) -> None:
            manifest["candidate_stages"].append(
                copy.deepcopy(manifest["candidate_stages"][0])
            )

        self.replace_manifest(report, "asr-faster-whisper", append_duplicate)
        codes = self.codes(report)
        self.assertIn("E_SCHEMA", codes)

        report = copy.deepcopy(self.fixture.report)
        self.replace_manifest(
            report,
            "e2e-faster-whisper__qwen3.5",
            lambda manifest: manifest["candidate_stages"].reverse(),
        )
        self.assertIn("E_MANIFEST_IDENTITY", self.codes(report))

    def test_foreign_manifest_and_measurement_refs_fail_closed(self) -> None:
        report = copy.deepcopy(self.fixture.report)
        source = report["runs"][0]
        target = report["runs"][1]
        target["manifest_ref"] = copy.deepcopy(source["manifest_ref"])
        codes = self.codes(report)
        self.assertIn("E_MATRIX_COVERAGE", codes)
        self.assertIn("E_EVIDENCE_LINK", codes)

        report = copy.deepcopy(self.fixture.report)
        source_entry = self.entry(report, "asr-faster-whisper")
        target_cell = "asr-qwen3-asr"
        source_manifest = self.builder.load_json_ref(source_entry["manifest_ref"])
        source_measurement_ref = source_manifest["candidate_stages"][0][
            "performance_measurement_ref"
        ]

        def use_foreign_measurement(manifest: dict[str, Any]) -> None:
            manifest["candidate_stages"][0]["performance_measurement_ref"] = (
                copy.deepcopy(source_measurement_ref)
            )

        self.replace_manifest(report, target_cell, use_foreign_measurement)
        codes = self.codes(report)
        self.assertIn("E_EVIDENCE_LINK", codes)
        self.assertIn("E_MEASUREMENT_REUSE", codes)

    def test_measurement_stage_and_attempt_reuse_fail_closed(self) -> None:
        report = copy.deepcopy(self.fixture.report)
        source_cell = "asr-faster-whisper"
        target_cell = "asr-qwen3-asr"
        source_entry = self.entry(report, source_cell)
        source_manifest = self.builder.load_json_ref(source_entry["manifest_ref"])
        source_stage = source_manifest["candidate_stages"][0]
        source_measurement = self.builder.load_json_ref(
            source_stage["performance_measurement_ref"]
        )

        def reuse_stage_id(manifest: dict[str, Any]) -> None:
            target_stage = manifest["candidate_stages"][0]
            target_measurement = self.builder.load_json_ref(
                target_stage["performance_measurement_ref"]
            )
            target_stage["candidate_stage_id"] = source_stage["candidate_stage_id"]
            target_measurement["candidate_stage_id"] = source_stage[
                "candidate_stage_id"
            ]
            target_stage["performance_measurement_ref"] = self.builder.store_json(
                "reused-stage-id-measurement.json", target_measurement
            )

        self.replace_manifest(report, target_cell, reuse_stage_id)
        self.assertIn("E_MEASUREMENT_REUSE", self.codes(report))

        report = copy.deepcopy(self.fixture.report)
        source_entry = self.entry(report, source_cell)
        source_manifest = self.builder.load_json_ref(source_entry["manifest_ref"])
        source_stage = source_manifest["candidate_stages"][0]
        source_measurement = self.builder.load_json_ref(
            source_stage["performance_measurement_ref"]
        )

        def reuse_attempt(manifest: dict[str, Any]) -> None:
            target_stage = manifest["candidate_stages"][0]
            target_measurement = self.builder.load_json_ref(
                target_stage["performance_measurement_ref"]
            )
            for field in MEASUREMENT_PROJECTION_FIELDS:
                target_measurement[field] = copy.deepcopy(source_measurement[field])
                target_stage[field] = copy.deepcopy(source_measurement[field])
            target_stage["performance_measurement_ref"] = self.builder.store_json(
                "reused-attempt-measurement.json", target_measurement
            )

        self.replace_manifest(report, target_cell, reuse_attempt)
        self.assertIn("E_ATTEMPT_REUSE", self.codes(report))

    def test_report_measurement_projection_order_is_exact(self) -> None:
        report = copy.deepcopy(self.fixture.report)
        entry = self.entry(report, "e2e-qwen3-asr__madlad")
        entry["measurement_ids"].reverse()
        entry["performance_measurement_refs"].reverse()
        self.assertIn("E_EVIDENCE_LINK", self.codes(report))

    def test_candidate_hashes_are_bound_to_runtime_stage_spec(self) -> None:
        candidate_fields = (
            "config_hash",
            "backend_identity_hash",
            "weight_hash",
        )
        for candidate_field in candidate_fields:
            with self.subTest(candidate_field=candidate_field):
                report = copy.deepcopy(self.fixture.report)

                def forge_candidate_identity(manifest: dict[str, Any]) -> None:
                    stage = manifest["candidate_stages"][0]
                    measurement = self.builder.load_json_ref(
                        stage["performance_measurement_ref"]
                    )
                    forged_hash = canonical_hash(
                        {"forged_candidate_field": candidate_field}
                    )
                    stage["candidate_identity"][candidate_field] = forged_hash
                    measurement["candidate_identity"] = copy.deepcopy(
                        stage["candidate_identity"]
                    )
                    chain_hash = canonical_hash(
                        [
                            {
                                "adapter_role": stage["adapter_role"],
                                **stage["candidate_identity"],
                            }
                        ]
                    )
                    manifest["candidate_chain_hash"] = chain_hash
                    measurement["candidate_chain_hash"] = chain_hash
                    manifest["candidate_config_hash"] = canonical_hash(
                        [
                            {
                                "adapter_role": stage["adapter_role"],
                                "config_hash": stage["candidate_identity"][
                                    "config_hash"
                                ],
                            }
                        ]
                    )
                    stage["performance_measurement_ref"] = self.builder.store_json(
                        f"forged-{candidate_field}-measurement.json", measurement
                    )

                self.replace_manifest(
                    report, "asr-faster-whisper", forge_candidate_identity
                )
                self.assertIn("E_CANDIDATE_STAGE_BINDING", self.codes(report))


if __name__ == "__main__":
    unittest.main()
