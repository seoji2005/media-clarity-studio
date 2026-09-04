"""TASK-032 closed preflight, frozen input, and recovery fixture tests."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from media_clarity.artifact_store import ArtifactStore
from media_clarity.asr_screen.contracts import (
    CANDIDATE_ORDER,
    ERROR_CODES,
    load_pack_ref,
    expected_preflight_blockers,
    readiness_findings,
    validate_decision_rule,
    validate_pack_manifest,
    validate_preflight,
    validate_recovery_fixture_report,
    validate_work_cpu_receipt,
)
from media_clarity.asr_screen.fixtures import (
    build_contract_fixture,
    run_recovery_fixture,
)
from media_clarity.asr_screen.preflight import (
    DEFAULT_PREFLIGHT_PATH,
    probe_work_cpu,
)
from media_clarity.schema_core import load_strict


class Task032PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preflight = load_strict(DEFAULT_PREFLIGHT_PATH)

    @staticmethod
    def codes(findings):
        return [finding.code for finding in findings]

    def test_error_codes_are_unique_and_stable_shape(self) -> None:
        self.assertEqual(len(ERROR_CODES), len(set(ERROR_CODES)))
        self.assertTrue(all(code.startswith("E_") for code in ERROR_CODES))

    def test_repository_preflight_is_valid_and_honestly_blocked(self) -> None:
        self.assertEqual(validate_preflight(self.preflight), [])
        findings = readiness_findings(self.preflight)
        self.assertEqual(len(findings), 12)
        self.assertEqual(self.codes(findings).count("E_ACCESS_RECEIPT"), 3)
        self.assertEqual(self.codes(findings).count("E_MODEL_RECEIPT_PENDING"), 3)
        self.assertIn("E_CONFIGURATION_PENDING", self.codes(findings))
        self.assertEqual(self.codes(findings).count("E_PACK_PENDING"), 2)
        self.assertIn("E_DECISION_RULE_PENDING", self.codes(findings))
        self.assertIn("E_DEPENDENCY_LOCK_PENDING", self.codes(findings))
        self.assertIn("E_WORK_CPU_EVIDENCE_PENDING", self.codes(findings))

    def test_candidate_identity_and_order_are_not_self_declared(self) -> None:
        mutated = copy.deepcopy(self.preflight)
        mutated["candidate_order"][0], mutated["candidate_order"][2] = (
            mutated["candidate_order"][2],
            mutated["candidate_order"][0],
        )
        mutated["candidates"][0], mutated["candidates"][2] = (
            mutated["candidates"][2],
            mutated["candidates"][0],
        )
        self.assertIn("E_CANDIDATE_IDENTITY", self.codes(validate_preflight(mutated)))

        mutated = copy.deepcopy(self.preflight)
        mutated["candidates"][1]["revision"] = "0" * 40
        self.assertIn("E_CANDIDATE_IDENTITY", self.codes(validate_preflight(mutated)))

    def test_execution_and_cost_policy_mutation_fails_closed(self) -> None:
        for field, value in (
            ("paid_provider_allowed", True),
            ("spending_cap_usd", 1),
            ("private_media_allowed", True),
            ("target_windows_compatibility", "supported"),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.preflight)
                mutated["execution_policy"][field] = value
                self.assertIn("E_SCREEN_POLICY", self.codes(validate_preflight(mutated)))

    def test_blockers_are_recomputed_and_cannot_be_removed(self) -> None:
        mutated = copy.deepcopy(self.preflight)
        mutated["blockers"] = []
        mutated["status"] = "ready_for_candidate_output"
        self.assertIn("E_PREFLIGHT_STATE", self.codes(validate_preflight(mutated)))

    def test_gated_access_cannot_be_accepted_without_receipt(self) -> None:
        mutated = copy.deepcopy(self.preflight)
        mutated["candidates"][1]["access_status"] = "accepted"
        self.assertIn("E_ACCESS_RECEIPT", self.codes(validate_preflight(mutated)))

    def test_gated_candidate_remains_blocked_until_access_is_accepted(self) -> None:
        mutated = copy.deepcopy(self.preflight)
        mutated["candidates"][1]["access_license_receipt_status"] = "verified"
        self.assertIn(
            ("E_ACCESS_RECEIPT", "cohere-transcribe-03-2026"),
            expected_preflight_blockers(mutated),
        )

    def test_pending_evidence_cannot_carry_an_unverified_ref(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-slot-") as temporary:
            fixture = build_contract_fixture(Path(temporary))
            mutated = copy.deepcopy(self.preflight)
            mutated["evidence"]["primary_pack"]["ref"] = fixture["primary_pack_ref"]
            self.assertIn("E_EVIDENCE_SLOT", self.codes(validate_preflight(mutated)))

    def test_first_slice_cannot_be_forged_into_candidate_output_authorization(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-no-output-auth-") as temporary:
            root = Path(temporary)
            fixture = build_contract_fixture(root)
            store = ArtifactStore(root)
            receipt_ref = fixture["decision_rule_ref"]
            mutated = copy.deepcopy(self.preflight)
            for candidate in mutated["candidates"]:
                candidate["access_license_receipt_status"] = "verified"
                candidate["access_license_receipt_ref"] = receipt_ref
                candidate["model_receipt_status"] = "verified"
                candidate["model_receipt_ref"] = receipt_ref
            mutated["candidates"][1]["access_status"] = "accepted"
            for name in mutated["configuration_status"]:
                mutated["configuration_status"][name] = "frozen"
            for slot in mutated["evidence"].values():
                slot["status"] = "verified"
                slot["ref"] = receipt_ref
            mutated["blockers"] = []
            self.assertEqual(validate_preflight(mutated, store=store), [])
            self.assertEqual(self.codes(readiness_findings(mutated, store=store)), ["E_PREFLIGHT_STATE"])

    def test_unknown_field_and_nonfinite_json_fail_at_schema_or_parser(self) -> None:
        mutated = copy.deepcopy(self.preflight)
        mutated["unexpected"] = True
        self.assertEqual(self.codes(validate_preflight(mutated)), ["E_SCHEMA"])

    def test_work_cpu_probe_is_honest_and_closed(self) -> None:
        receipt = probe_work_cpu()
        self.assertEqual(validate_work_cpu_receipt(receipt), [])
        self.assertFalse(receipt["claims"]["candidate_output_generated"])
        self.assertEqual(receipt["claims"]["paid_cost_usd"], 0)
        self.assertEqual(receipt["claims"]["target_windows_compatibility"], "not_evaluated")
        self.assertEqual(receipt["claims"]["target_gpu_compatibility"], "not_evaluated")

        mutated = copy.deepcopy(receipt)
        mutated["claims"]["target_windows_compatibility"] = "supported"
        self.assertIn("E_SCHEMA", self.codes(validate_work_cpu_receipt(mutated)))


class Task032FrozenContractTests(unittest.TestCase):
    @staticmethod
    def codes(findings):
        return [finding.code for finding in findings]

    def _fixture(self, root: Path):
        contract = build_contract_fixture(root)
        store = ArtifactStore(root)
        primary, primary_findings = load_pack_ref(
            contract["primary_pack_ref"], store=store, location="primary_ref"
        )
        reserve, reserve_findings = load_pack_ref(
            contract["reserve_pack_ref"], store=store, location="reserve_ref"
        )
        rule, rule_findings = load_pack_ref(
            contract["decision_rule_ref"], store=store, location="rule_ref"
        )
        self.assertEqual(primary_findings + reserve_findings + rule_findings, [])
        return contract, store, primary, reserve, rule

    def test_small_contract_fixture_is_cas_bound_and_not_a_candidate_run(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-contract-") as temporary:
            contract, store, primary, reserve, rule = self._fixture(Path(temporary))
            self.assertEqual(validate_pack_manifest(primary, store=store), [])
            self.assertEqual(validate_pack_manifest(reserve, store=store), [])
            self.assertEqual(
                validate_decision_rule(
                    rule,
                    primary_pack_ref=contract["primary_pack_ref"],
                    reserve_pack_ref=contract["reserve_pack_ref"],
                ),
                [],
            )
            self.assertFalse(contract["candidate_output_generated"])
            self.assertEqual(contract["target_windows_compatibility"], "not_evaluated")

    def test_pack_duration_and_audio_hash_mutations_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-pack-mutation-") as temporary:
            _, store, primary, _, _ = self._fixture(Path(temporary))
            mutated = copy.deepcopy(primary)
            mutated["total_duration_seconds"] += 1
            self.assertIn("E_PACK_STRUCTURE", self.codes(validate_pack_manifest(mutated, store=store)))

            mutated = copy.deepcopy(primary)
            mutated["clips"][0]["original_hash"] = "sha256:" + "0" * 64
            self.assertIn("E_PACK_BINDING", self.codes(validate_pack_manifest(mutated, store=store)))

            mutated = copy.deepcopy(primary)
            mutated["clips"][1]["evaluated_audio_ref"] = copy.deepcopy(
                mutated["clips"][0]["evaluated_audio_ref"]
            )
            mutated["clips"][1]["evaluated_hash"] = mutated["clips"][0]["evaluated_hash"]
            self.assertIn("E_PACK_STRUCTURE", self.codes(validate_pack_manifest(mutated, store=store)))

    def test_tampered_pack_cas_object_is_rejected(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-pack-cas-") as temporary:
            root = Path(temporary)
            contract, store, _, _, _ = self._fixture(root)
            ref = contract["primary_pack_ref"]
            store.absolute(ref["uri"], "primary_ref/uri").write_bytes(b"tampered")
            loaded, findings = load_pack_ref(ref, store=store, location="primary_ref")
            self.assertIsNone(loaded)
            self.assertIn("E_PACK_ARTIFACT", self.codes(findings))

    def test_rule_policy_and_binding_mutations_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-rule-") as temporary:
            contract, _, _, _, rule = self._fixture(Path(temporary))
            mutated = copy.deepcopy(rule)
            mutated["bootstrap"]["seed"] = 1
            self.assertIn("E_DECISION_RULE_POLICY", self.codes(validate_decision_rule(mutated)))

            mutated = copy.deepcopy(rule)
            mutated["tier_order"][0], mutated["tier_order"][1] = (
                mutated["tier_order"][1],
                mutated["tier_order"][0],
            )
            self.assertIn("E_DECISION_RULE_POLICY", self.codes(validate_decision_rule(mutated)))

            mutated = copy.deepcopy(rule)
            mutated["primary_pack_hash"] = "sha256:" + "f" * 64
            self.assertIn(
                "E_DECISION_RULE_BINDING",
                self.codes(
                    validate_decision_rule(
                        mutated,
                        primary_pack_ref=contract["primary_pack_ref"],
                        reserve_pack_ref=contract["reserve_pack_ref"],
                    )
                ),
            )


class Task032RecoveryFixtureTests(unittest.TestCase):
    @staticmethod
    def codes(findings):
        return [finding.code for finding in findings]

    def test_all_three_candidates_interrupt_once_and_resume_exactly(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-recovery-") as temporary:
            report = run_recovery_fixture(Path(temporary))
        self.assertEqual(validate_recovery_fixture_report(report), [])
        self.assertEqual(report["candidate_order"], list(CANDIDATE_ORDER))
        self.assertEqual([item["interruption_count"] for item in report["candidates"]], [1, 1, 1])
        self.assertTrue(
            all(
                item["unit_001_attempt_id_before"] == item["unit_001_attempt_id_after"]
                for item in report["candidates"]
            )
        )

    def test_resume_projection_mutations_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-recovery-mutation-") as temporary:
            report = run_recovery_fixture(Path(temporary))
        mutations = []
        changed = copy.deepcopy(report)
        changed["candidates"][0]["interruption_count"] = 0
        mutations.append(changed)
        changed = copy.deepcopy(report)
        changed["candidates"][1]["unit_001_attempt_id_after"] = "a9999"
        mutations.append(changed)
        changed = copy.deepcopy(report)
        changed["candidates"][2]["unit_002_attempt_statuses"] = ["completed"]
        mutations.append(changed)
        changed = copy.deepcopy(report)
        changed["candidate_order"] = list(reversed(CANDIDATE_ORDER))
        mutations.append(changed)
        for index, mutated in enumerate(mutations):
            with self.subTest(index=index):
                self.assertIn(
                    "E_RESUME_EVIDENCE",
                    self.codes(validate_recovery_fixture_report(mutated)),
                )


if __name__ == "__main__":
    unittest.main()
