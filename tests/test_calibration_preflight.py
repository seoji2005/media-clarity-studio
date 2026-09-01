"""TASK-031 dependency/model preflight unit·mutation tests."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from media_clarity.calibration.preflight import (
    DEFAULT_MANIFEST_PATH,
    ERROR_CODES,
    MODEL_RECEIPT_NAME,
    _download_models,
    _receipt_document,
    validate_manifest,
    validate_readiness,
)
from media_clarity.job_runtime import write_json_atomic
from media_clarity.schema_core import REPO_ROOT, load_strict


class CalibrationPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_strict(DEFAULT_MANIFEST_PATH)

    def codes(self, findings):
        return [finding.code for finding in findings]

    def test_error_codes_are_unique_and_stable_shape(self) -> None:
        self.assertEqual(len(ERROR_CODES), len(set(ERROR_CODES)))
        self.assertTrue(all(code.startswith("E_") for code in ERROR_CODES))

    def test_repository_preparation_manifest_is_valid_but_not_ready(self) -> None:
        self.assertEqual(validate_manifest(self.manifest), [])
        findings = validate_readiness(self.manifest, REPO_ROOT)
        self.assertEqual(self.codes(findings).count("E_LOCK_PENDING"), 4)
        self.assertEqual(self.codes(findings).count("E_CUDA_PENDING"), 3)
        self.assertEqual(self.codes(findings).count("E_MODEL_MISSING"), 5)

    def test_unknown_field_fails_closed_at_schema_layer(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["unexpected"] = True
        findings = validate_manifest(mutated)
        self.assertEqual(self.codes(findings), ["E_SCHEMA"])

    def test_candidate_revision_mutation_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["models"][0]["revision"] = "0" * 40
        self.assertIn("E_MODEL_IDENTITY", self.codes(validate_manifest(mutated)))

    def test_dependency_digest_and_unpinned_line_are_rejected(self) -> None:
        with TemporaryDirectory(prefix="mcs-task031-") as temporary:
            root = Path(temporary)
            shutil.copytree(REPO_ROOT / "requirements", root / "requirements")
            dependency = root / self.manifest["dependency_environments"][0]["dependency_input_path"]
            dependency.write_text("huggingface-hub>=1.29.0\n", encoding="utf-8")
            findings = validate_manifest(self.manifest, repo_root=root)
            self.assertIn("E_DEPENDENCY_DIGEST", self.codes(findings))
            self.assertIn("E_DEPENDENCY_PIN", self.codes(findings))

    def test_direct_package_source_mutation_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["dependency_environments"][0]["direct_packages"][0][
            "official_source"
        ] = "https://example.invalid/huggingface-hub/"
        self.assertIn("E_DEPENDENCY_SET", self.codes(validate_manifest(mutated)))

    def test_resolved_lock_claim_without_file_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        environment = mutated["dependency_environments"][0]
        environment["lock_status"] = "windows_resolved"
        environment["lock_sha256"] = "0" * 64
        findings = validate_manifest(mutated)
        self.assertIn("E_LOCK_MISSING", self.codes(findings))

    def test_multiline_uv_hash_lock_is_accepted(self) -> None:
        with TemporaryDirectory(prefix="mcs-task031-lock-") as temporary:
            root = Path(temporary)
            shutil.copytree(REPO_ROOT / "requirements", root / "requirements")
            mutated = copy.deepcopy(self.manifest)
            environment = mutated["dependency_environments"][0]
            lock_path = root / environment["lock_path"]
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text(
                "huggingface-hub==1.29.0 \\\n"
                "    --hash=sha256:" + "1" * 64 + " \\\n"
                "    --hash=sha256:" + "2" * 64 + "\n",
                encoding="utf-8",
            )
            environment["lock_status"] = "windows_resolved"
            environment["lock_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
            environment["resolver_version"] = "0.test"
            findings = validate_manifest(mutated, repo_root=root)
            self.assertNotIn("E_LOCK_HASH", self.codes(findings))
            self.assertNotIn("E_LOCK_DIGEST", self.codes(findings))

    def test_download_refuses_network_until_download_lock_is_resolved(self) -> None:
        findings = _download_models(
            self.manifest,
            [self.manifest["models"][0]["model_id"]],
            REPO_ROOT,
            allow_network=True,
        )
        self.assertEqual(self.codes(findings), ["E_LOCK_PENDING"])

    def test_download_requires_explicit_network_flag(self) -> None:
        findings = _download_models(
            self.manifest,
            [self.manifest["models"][0]["model_id"]],
            REPO_ROOT,
            allow_network=False,
        )
        self.assertEqual(self.codes(findings), ["E_NETWORK_NOT_ALLOWED"])

    def test_model_receipt_binds_exact_tree_and_detects_tamper(self) -> None:
        with TemporaryDirectory(prefix="mcs-task031-model-") as temporary:
            model_root = Path(temporary)
            model = self.manifest["models"][0]
            target = model_root / model["local_dir"]
            target.mkdir(parents=True)
            weight = target / "weights.bin"
            weight.write_bytes(b"fixed-model-bytes")
            receipt, findings = _receipt_document(model, target)
            self.assertEqual(findings, [])
            write_json_atomic(target / MODEL_RECEIPT_NAME, receipt)

            before = validate_readiness(self.manifest, model_root)
            receipt_locations = [
                finding.location
                for finding in before
                if finding.code == "E_MODEL_RECEIPT"
            ]
            self.assertNotIn("manifest/models/0", receipt_locations)

            weight.write_bytes(b"tampered-model-bytes")
            after = validate_readiness(self.manifest, model_root)
            self.assertIn(
                "manifest/models/0",
                [finding.location for finding in after if finding.code == "E_MODEL_RECEIPT"],
            )

    def test_readiness_returns_schema_finding_without_crashing(self) -> None:
        findings = validate_readiness({"unexpected": True}, REPO_ROOT)
        self.assertTrue(findings)
        self.assertTrue(all(finding.code == "E_SCHEMA" for finding in findings))

    def test_manifest_json_is_strictly_round_trippable(self) -> None:
        text = DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")
        self.assertEqual(json.loads(text), self.manifest)


if __name__ == "__main__":
    unittest.main()
