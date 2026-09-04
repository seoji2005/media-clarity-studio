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
    validate_access_license_receipt,
    validate_configuration_pack_binding,
    validate_decision_rule,
    validate_dependency_lock,
    validate_model_receipt,
    validate_pack_manifest,
    validate_pack_pair,
    validate_preflight,
    validate_recovery_fixture_report,
    validate_screen_configuration,
    validate_work_cpu_receipt,
)
from media_clarity.asr_screen.fixtures import (
    build_contract_fixture,
    build_preparation_fixture,
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
            findings = validate_preflight(mutated, store=store)
            self.assertIn("E_SCHEMA", self.codes(findings))
            self.assertNotEqual(readiness_findings(mutated, store=store), [])

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

    def test_primary_and_reserve_source_groups_cannot_leak(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-source-leak-") as temporary:
            _, store, primary, reserve, _ = self._fixture(Path(temporary))
            mutated = copy.deepcopy(reserve)
            mutated["clips"][0]["source_id"] = primary["clips"][0]["source_id"]
            self.assertIn(
                "E_PACK_STRUCTURE",
                self.codes(validate_pack_pair(primary, mutated, store=store)),
            )


class Task032PreparationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preflight = load_strict(DEFAULT_PREFLIGHT_PATH)

    @staticmethod
    def codes(findings):
        return [finding.code for finding in findings]

    def _fixture(self, root: Path):
        return build_preparation_fixture(root, self.preflight)

    def _load(self, ref, store, location):
        document, findings = load_pack_ref(ref, store=store, location=location)
        self.assertEqual(findings, [])
        self.assertIsNotNone(document)
        return document

    def test_typed_preparation_fixture_is_valid_but_still_cannot_authorize_output(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-preparation-") as temporary:
            fixture = self._fixture(Path(temporary))
            self.assertEqual(validate_preflight(fixture["preflight"], store=fixture["store"]), [])
            self.assertEqual(
                self.codes(readiness_findings(fixture["preflight"], store=fixture["store"])),
                ["E_PREFLIGHT_STATE"],
            )

    def test_typed_slot_substitution_and_candidate_swap_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-preparation-swap-") as temporary:
            fixture = self._fixture(Path(temporary))
            mutated = copy.deepcopy(fixture["preflight"])
            mutated["evidence"]["screen_configuration"]["ref"] = mutated["evidence"]["decision_rule"]["ref"]
            self.assertIn("E_SCHEMA", self.codes(validate_preflight(mutated, store=fixture["store"])))

            mutated = copy.deepcopy(fixture["preflight"])
            first = mutated["candidates"][0]["model_receipt_ref"]
            mutated["candidates"][0]["model_receipt_ref"] = mutated["candidates"][2]["model_receipt_ref"]
            mutated["candidates"][2]["model_receipt_ref"] = first
            self.assertIn("E_MODEL_RECEIPT_BINDING", self.codes(validate_preflight(mutated, store=fixture["store"])))

    def test_configuration_policy_and_pack_binding_are_closed(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-configuration-") as temporary:
            fixture = self._fixture(Path(temporary))
            store = fixture["store"]
            configuration = self._load(fixture["configuration_ref"], store, "configuration")
            mutated = copy.deepcopy(configuration)
            mutated["vad"]["boundary_source"] = "pack_speech_mask"
            self.assertIn("E_CONFIGURATION_POLICY", self.codes(validate_screen_configuration(mutated)))

            primary = self._load(fixture["preflight"]["evidence"]["primary_pack"]["ref"], store, "primary")
            reserve = self._load(fixture["preflight"]["evidence"]["reserve_pack"]["ref"], store, "reserve")
            mutated = copy.deepcopy(configuration)
            mutated["language_hint"] = {
                "mode": "per_clip_dominant",
                "value_source": "pack_clip_language_hint",
                "allowed_tags": ["ja", "en"],
                "code_switch_policy": "single-dominant-hint-only",
                "identical_across_candidates": True,
            }
            self.assertIn(
                "E_CONFIGURATION_BINDING",
                self.codes(validate_configuration_pack_binding(mutated, primary, reserve)),
            )

    def test_access_model_and_dependency_receipt_mutations_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="mcs-task032-receipts-") as temporary:
            fixture = self._fixture(Path(temporary))
            store = fixture["store"]
            cohere = self._load(fixture["access_refs"]["cohere-transcribe-03-2026"], store, "cohere-access")
            mutated_access = copy.deepcopy(cohere)
            mutated_access["acceptance_status"] = "not_accepted"
            self.assertIn(
                "E_ACCESS_RECEIPT_BINDING",
                self.codes(
                    validate_access_license_receipt(
                        mutated_access,
                        candidate_id="cohere-transcribe-03-2026",
                        store=store,
                    )
                ),
            )
            mutated_access = copy.deepcopy(cohere)
            mutated_access["source_uri"] = "https://example.invalid/wrong-source"
            self.assertIn(
                "E_ACCESS_RECEIPT_BINDING",
                self.codes(
                    validate_access_license_receipt(
                        mutated_access,
                        candidate_id="cohere-transcribe-03-2026",
                        store=store,
                    )
                ),
            )
            mutated_access = copy.deepcopy(cohere)
            mutated_access["metadata_hash"] = "sha256:" + "0" * 64
            self.assertIn(
                "E_ACCESS_RECEIPT_BINDING",
                self.codes(
                    validate_access_license_receipt(
                        mutated_access,
                        candidate_id="cohere-transcribe-03-2026",
                        store=store,
                    )
                ),
            )

            model = self._load(fixture["model_refs"]["qwen3-asr-1.7b"], store, "qwen-model")
            mutated_model = copy.deepcopy(model)
            mutated_model["files"][0]["relative_path"] = "../weights.bin"
            self.assertIn(
                "E_MODEL_RECEIPT_BINDING",
                self.codes(validate_model_receipt(mutated_model, candidate_id="qwen3-asr-1.7b")),
            )
            mutated_model = copy.deepcopy(model)
            mutated_model["file_manifest_hash"] = "sha256:" + "0" * 64
            self.assertIn(
                "E_MODEL_RECEIPT_BINDING",
                self.codes(validate_model_receipt(mutated_model, candidate_id="qwen3-asr-1.7b")),
            )

            lock = self._load(fixture["dependency_lock_ref"], store, "dependency-lock")
            work_cpu = self._load(fixture["work_cpu_ref"], store, "work-cpu")
            mutated_lock = copy.deepcopy(lock)
            mutated_lock["platform_architecture"] = "arm64"
            self.assertIn(
                "E_DEPENDENCY_LOCK_BINDING",
                self.codes(validate_dependency_lock(mutated_lock, store=store, work_cpu_receipt=work_cpu)),
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
    validate_screen_configuration,
