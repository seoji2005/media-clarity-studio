"""TASK-006 평가 계약 테스트.

이 테스트는 fixture의 `expected`를 그대로 통과시키지 않는다. production document를
실제 schema·semantic validator에 넣은 결과와 비교하고, 계약을 어기는 mutation이
반드시 실패하는지 확인한다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from media_clarity.eval_contracts import (
    DEFAULT_SCHEMA_DIR,
    ERROR_CODES,
    EXPECTED_CASE_IDS,
    Finding,
    SCHEMA_DIALECT,
    SCHEMA_FILES,
    SCHEMA_VERSION,
    SUPPORTED_KEYWORDS,
    JsonInputError,
    SchemaContractError,
    SchemaSet,
    check_document_containers,
    discover_fixtures,
    evaluate_fixture,
    load_fixture,
    loads_strict,
    metric_status_map,
    portable_relative_path_error,
    sort_findings,
    utc_timestamp_error,
    validate_documents,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "eval_contracts"
SCHEMAS = SchemaSet(DEFAULT_SCHEMA_DIR)


def documents_of(case: str) -> dict[str, Any]:
    number = int(case.split("-")[1])
    fixture = load_fixture(FIXTURE_DIR / f"h-{number:02d}.json")
    return copy.deepcopy(fixture["documents"])


def codes_for(documents: dict[str, Any]) -> tuple[str, ...]:
    return validate_documents(documents, SCHEMAS).codes


def findings_for(documents: dict[str, Any]) -> tuple[Finding, ...]:
    return validate_documents(documents, SCHEMAS).findings


def assert_rejected(
    case: unittest.TestCase, documents: dict[str, Any], code: str, location: str
) -> None:
    """반례가 기대 코드와 **정확한 JSON Pointer**로 거부되는지 확인한다."""

    findings = findings_for(documents)
    case.assertTrue(findings, f"{code} 반례가 통과했다")
    hits = [f for f in findings if f.code == code and f.location == location]
    case.assertTrue(
        hits,
        f"{code} @ {location} 없음. 실제: {[(f.code, f.location) for f in findings]}",
    )


def previous_versions_of(documents: dict[str, Any]) -> list[dict[str, Any]]:
    return documents["eval_run_manifest"]["resume"]["previous_metric_versions"]


def plan_entry(documents: dict[str, Any], axis: str, metric_id: str) -> dict[str, Any]:
    for entry in documents["eval_run_manifest"]["metric_plan"]:
        if entry["axis"] == axis and entry["metric_id"] == metric_id:
            return entry
    raise AssertionError(f"metric plan에 ({axis}, {metric_id})가 없다")


class SchemaFileContractTests(unittest.TestCase):
    def test_all_seven_schema_files_exist(self) -> None:
        for name in SCHEMA_FILES:
            self.assertTrue((DEFAULT_SCHEMA_DIR / name).is_file(), name)
        self.assertEqual(len(SCHEMA_FILES), 7)

    def test_roots_declare_draft_2020_12_and_stable_id(self) -> None:
        for name, document in SCHEMAS.documents.items():
            self.assertEqual(document["$schema"], SCHEMA_DIALECT, name)
            self.assertTrue(document["$id"].endswith(name), name)

    def test_schema_version_is_pinned_to_1_0_0(self) -> None:
        common = SCHEMAS.documents["common-v1.schema.json"]
        self.assertEqual(common["$defs"]["schema_version"]["const"], "1.0.0")
        self.assertEqual(SCHEMA_VERSION, "1.0.0")
        for name in SCHEMA_FILES:
            if name == "common-v1.schema.json":
                continue
            document = SCHEMAS.documents[name]
            self.assertIn("schema_version", document["required"], name)

    def test_production_root_objects_are_closed(self) -> None:
        for name in SCHEMA_FILES:
            if name == "common-v1.schema.json":
                continue
            self.assertIs(SCHEMAS.documents[name].get("additionalProperties"), False, name)

    def test_common_definitions_are_reused_by_relative_ref(self) -> None:
        raw = (DEFAULT_SCHEMA_DIR / "reference-bundle-v1.schema.json").read_text(encoding="utf-8")
        self.assertIn('"$ref": "common-v1.schema.json#/$defs/ArtifactRef"', raw)
        self.assertIn('"$ref": "common-v1.schema.json#/$defs/Timebase"', raw)

    def test_report_schema_has_no_aggregate_field(self) -> None:
        report = SCHEMAS.documents["eval-report-v1.schema.json"]
        for banned in ("overall_score", "aggregate_score", "combined_score", "total_score"):
            self.assertNotIn(banned, report["properties"], banned)

    def test_paired_observation_cannot_declare_promotion(self) -> None:
        report = SCHEMAS.documents["eval-report-v1.schema.json"]
        observation = report["properties"]["paired_observation"]["properties"]["observation"]
        self.assertNotIn("promote", observation["enum"])
        self.assertIn("blocked_by_open_thresholds", observation["enum"])

    def test_validator_refuses_schemas_outside_its_keyword_subset(self) -> None:
        """Draft 2020-12 전체 구현이라고 주장하지 않는다 — 미지원 keyword는 거부한다."""

        with self.subTest("if/then은 지원 목록에 없다"):
            self.assertNotIn("if", SUPPORTED_KEYWORDS)
            self.assertNotIn("then", SUPPORTED_KEYWORDS)
        broken = DEFAULT_SCHEMA_DIR
        temp = SchemaSet(broken)
        injected = copy.deepcopy(temp.documents["common-v1.schema.json"])
        injected["$defs"]["seconds"]["multipleOf"] = 0.5
        with self.assertRaises(SchemaContractError):
            temp._assert_supported(injected, "common-v1.schema.json#")


class JsonHardeningTests(unittest.TestCase):
    def test_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaises(JsonInputError):
            loads_strict('{"run_id": "a", "run_id": "b"}')

    def test_nan_and_infinity_are_rejected(self) -> None:
        for text in ('{"value": NaN}', '{"value": Infinity}', '{"value": -Infinity}'):
            with self.subTest(text=text), self.assertRaises(JsonInputError):
                loads_strict(text)

    def test_finite_numbers_still_load(self) -> None:
        self.assertEqual(loads_strict('{"value": 0.5}'), {"value": 0.5})


class PortablePathTests(unittest.TestCase):
    def test_relative_posix_paths_are_accepted(self) -> None:
        for value in ("evals/dev/run-1/report.json", "a", "a/b/c.jsonl"):
            self.assertIsNone(portable_relative_path_error(value), value)

    def test_non_portable_paths_are_rejected(self) -> None:
        rejected = [
            "/etc/passwd",
            "C:/runs/report.json",
            "c:\\runs\\report.json",
            "\\\\server\\share\\report.json",
            "//server/share/report.json",
            "../outside/report.json",
            "evals/../../etc/passwd",
            "evals/./report.json",
            "evals//report.json",
            " evals/report.json",
            "",
        ]
        for value in rejected:
            with self.subTest(value=value):
                self.assertIsNotNone(portable_relative_path_error(value))

    def test_artifact_ref_uri_is_not_restricted(self) -> None:
        """일반 ArtifactRef.uri는 외부 입력 URI를 표현할 수 있으므로 같은 제한을 적용하지 않는다."""

        documents = documents_of("H-01")
        documents["reference_bundles"][0]["source_media"]["uri"] = "file:///Volumes/media/in.mkv"
        self.assertEqual(codes_for(documents), ())


class FixtureDiscoveryTests(unittest.TestCase):
    def test_exactly_fourteen_fixtures_are_discovered(self) -> None:
        paths = discover_fixtures(FIXTURE_DIR)
        self.assertEqual(len(paths), 14)
        self.assertEqual([p.name for p in paths], [f"h-{i:02d}.json" for i in range(1, 15)])

    def test_each_case_id_appears_exactly_once(self) -> None:
        case_ids = [load_fixture(path)["case_id"] for path in discover_fixtures(FIXTURE_DIR)]
        self.assertEqual(case_ids, list(EXPECTED_CASE_IDS))
        self.assertEqual(len(set(case_ids)), 14)

    def test_every_fixture_is_executed_and_matches_recomputed_result(self) -> None:
        executed: list[str] = []
        for path in discover_fixtures(FIXTURE_DIR):
            outcome = evaluate_fixture(path, SCHEMAS)
            executed.append(outcome.case_id)
            with self.subTest(case=outcome.case_id):
                self.assertTrue(outcome.passed, outcome.mismatches)
                # expected를 읽어 그대로 통과시키지 않는다 — 문서를 다시 검증해 비교한다.
                fixture = load_fixture(path)
                recomputed = validate_documents(fixture["documents"], SCHEMAS)
                self.assertEqual(
                    recomputed.codes, tuple(sorted(fixture["expected"].get("error_codes") or []))
                )
                self.assertEqual(recomputed.valid, bool(fixture["expected"]["valid"]))
        self.assertEqual(executed, list(EXPECTED_CASE_IDS))

    def test_validator_does_not_modify_fixture_files(self) -> None:
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in discover_fixtures(FIXTURE_DIR)
        }
        for path in discover_fixtures(FIXTURE_DIR):
            evaluate_fixture(path, SCHEMAS)
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in discover_fixtures(FIXTURE_DIR)
        }
        self.assertEqual(before, after)

    def test_findings_order_is_deterministic(self) -> None:
        documents = documents_of("H-01")
        documents["eval_run_manifest"]["artifacts"]["report_path"] = "/abs/report.json"
        documents["eval_run_manifest"]["artifacts"]["events_path"] = "../events.jsonl"
        first = validate_documents(documents, SCHEMAS).findings
        second = validate_documents(copy.deepcopy(documents), SCHEMAS).findings
        self.assertEqual(first, second)
        self.assertEqual(list(first), sort_findings(first))


class AxisSeparationTests(unittest.TestCase):
    def test_h01_reports_both_axes_without_any_aggregate(self) -> None:
        documents = documents_of("H-01")
        self.assertEqual(codes_for(documents), ())
        report = documents["eval_report"]
        self.assertIn("source", report["metrics_by_axis"])
        self.assertIn("target", report["metrics_by_axis"])
        flat = json.dumps(report, ensure_ascii=False)
        for banned in ("overall_score", "aggregate_score", "combined_score", "promote"):
            self.assertNotIn(banned, flat, banned)

    def test_adding_overall_score_to_report_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["overall_score"] = 0.87
        self.assertIn("E_SCHEMA", codes_for(documents))

    def test_aggregate_named_metric_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["metrics"]["overall_score"] = {
            "schema_version": "1.0.0",
            "metric_id": "overall_score",
            "status": "computed",
            "value": 0.9,
        }
        self.assertIn("E_AGGREGATE_FORBIDDEN", codes_for(documents))

    def test_metric_placed_in_the_wrong_axis_bucket_is_rejected(self) -> None:
        documents = documents_of("H-01")
        source = documents["eval_report"]["metrics_by_axis"]["source"]
        documents["eval_report"]["metrics_by_axis"]["target"]["cer"] = source["cer"]
        self.assertIn("E_AXIS_MISMATCH", codes_for(documents))

    def test_reference_hypothesis_axis_mismatch_is_rejected(self) -> None:
        documents = documents_of("H-04")
        self.assertEqual(codes_for(documents), ("E_AXIS_MISMATCH",))

    def test_source_only_reference_keeps_target_unsupported_not_zero(self) -> None:
        documents = documents_of("H-02")
        self.assertEqual(codes_for(documents), ())
        status = metric_status_map(documents)
        self.assertEqual(status["target"]["chrf2"], "unsupported")
        self.assertNotIn("value", documents["eval_report"]["metrics_by_axis"]["target"]["chrf2"])

    def test_scoring_an_absent_target_axis_as_zero_is_rejected(self) -> None:
        documents = documents_of("H-02")
        documents["eval_report"]["metrics_by_axis"]["target"]["chrf2"] = {
            "schema_version": "1.0.0",
            "metric_id": "chrf2",
            "status": "computed",
            "value": 0,
        }
        self.assertIn("E_METRIC_CAPABILITY", codes_for(documents))


class TargetLanguageTests(unittest.TestCase):
    def test_non_ko_target_language_is_rejected(self) -> None:
        documents = documents_of("H-03")
        self.assertEqual(codes_for(documents), ("E_TARGET_LANGUAGE",))

    def test_missing_target_language_is_rejected(self) -> None:
        documents = documents_of("H-01")
        del documents["reference_bundles"][0]["target_language"]
        self.assertIn("E_TARGET_LANGUAGE", codes_for(documents))

    def test_source_only_bundle_cannot_claim_a_target_language(self) -> None:
        documents = documents_of("H-02")
        documents["reference_bundles"][0]["target_language"] = "ko"
        self.assertIn("E_TARGET_LANGUAGE", codes_for(documents))


class MetricResultTests(unittest.TestCase):
    def test_unsupported_metric_with_value_zero_is_rejected(self) -> None:
        documents = documents_of("H-02")
        documents["eval_report"]["metrics_by_axis"]["target"]["chrf2"]["value"] = 0
        self.assertIn("E_METRIC_VALUE_FORBIDDEN", codes_for(documents))

    def test_insufficient_n_requires_n_and_forbids_value(self) -> None:
        documents = documents_of("H-08")
        self.assertEqual(codes_for(documents), ())
        cer = documents["eval_report"]["metrics_by_axis"]["source"]["cer"]
        self.assertEqual(cer["status"], "insufficient_n")
        self.assertNotIn("value", cer)
        self.assertIn("n", cer)

        with_value = documents_of("H-08")
        with_value["eval_report"]["metrics_by_axis"]["source"]["cer"]["value"] = 0
        self.assertIn("E_METRIC_VALUE_FORBIDDEN", codes_for(with_value))

        without_n = documents_of("H-08")
        del without_n["eval_report"]["metrics_by_axis"]["source"]["cer"]["n"]
        self.assertIn("E_METRIC_VALUE_REQUIRED", codes_for(without_n))

    def test_failed_metric_with_value_is_rejected(self) -> None:
        documents = documents_of("H-10")
        documents["eval_report"]["metrics_by_axis"]["source"]["wer"]["value"] = 0
        self.assertIn("E_METRIC_VALUE_FORBIDDEN", codes_for(documents))

    def test_computed_metric_without_value_is_rejected(self) -> None:
        documents = documents_of("H-01")
        del documents["eval_report"]["metrics_by_axis"]["source"]["cer"]["value"]
        self.assertIn("E_METRIC_VALUE_REQUIRED", codes_for(documents))


class RunStatusAndArtifactTests(unittest.TestCase):
    def test_partial_report_keeps_other_metrics_and_diagnostics(self) -> None:
        documents = documents_of("H-10")
        self.assertEqual(codes_for(documents), ())
        report = documents["eval_report"]
        self.assertEqual(report["document_kind"], "partial")
        self.assertEqual(report["run_status"], "partial")
        status = metric_status_map(documents)
        self.assertEqual(status["source"]["wer"], "failed")
        self.assertEqual(status["source"]["cer"], "computed")
        self.assertTrue(report["diagnostics"])
        self.assertEqual(report["diagnostics"][0]["metric_id"], "wer")

    def test_declaring_a_non_completed_run_as_final_is_rejected(self) -> None:
        documents = documents_of("H-10")
        documents["eval_report"]["document_kind"] = "final"
        self.assertIn("E_FINAL_STATUS", codes_for(documents))

    def test_every_non_completed_status_is_rejected_as_final(self) -> None:
        for status in ("planned", "invalid", "running", "partial", "failed", "aborted"):
            with self.subTest(status=status):
                documents = documents_of("H-01")
                documents["eval_report"]["run_status"] = status
                self.assertIn("E_FINAL_STATUS", codes_for(documents))

    def test_absolute_windows_and_traversal_output_paths_are_rejected(self) -> None:
        cases = {
            "/var/evals/report.json": "POSIX 절대",
            "C:/evals/report.json": "Windows drive",
            "\\\\host\\share\\report.json": "UNC",
            "../../etc/report.json": "traversal",
        }
        for value in cases:
            with self.subTest(path=value):
                documents = documents_of("H-01")
                documents["eval_run_manifest"]["artifacts"]["report_path"] = value
                self.assertIn("E_ARTIFACT_PATH", codes_for(documents))


class SplitAndPairingTests(unittest.TestCase):
    def test_dev_test_source_leakage_is_rejected(self) -> None:
        documents = documents_of("H-09")
        self.assertEqual(codes_for(documents), ("E_SPLIT_LEAKAGE",))

    def test_dev_test_speaker_leakage_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["eval_run_manifest"]["split_evidence"]["test_speaker_ids"] = ["spk-01"]
        self.assertIn("E_SPLIT_LEAKAGE", codes_for(documents))

    def test_baseline_candidate_sample_mismatch_is_rejected(self) -> None:
        documents = documents_of("H-14")
        self.assertEqual(codes_for(documents), ("E_PAIRED_SAMPLE_SET",))

    def test_matching_paired_samples_are_accepted(self) -> None:
        documents = documents_of("H-14")
        paired = documents["eval_run_manifest"]["paired_comparison"]
        paired["candidate_sample_ids"] = list(paired["baseline_sample_ids"])
        for hypothesis in documents["eval_run_manifest"]["hypotheses"]:
            if hypothesis["hypothesis_id"] == "hyp-candidate":
                hypothesis["sample_ids"] = list(paired["baseline_sample_ids"])
        self.assertEqual(codes_for(documents), ())

    def test_paired_observation_never_declares_promotion(self) -> None:
        documents = documents_of("H-14")
        documents["eval_report"]["paired_observation"]["observation"] = "promote"
        self.assertIn("E_SCHEMA", codes_for(documents))


class ResumeTests(unittest.TestCase):
    def test_identical_fingerprints_and_shards_allow_reuse(self) -> None:
        documents = documents_of("H-11")
        self.assertEqual(codes_for(documents), ())
        shards = documents["eval_run_manifest"]["resume"]["completed_shards"]
        self.assertEqual(len({s["shard_id"] for s in shards}), len(shards))

    def test_changed_fingerprint_is_rejected(self) -> None:
        documents = documents_of("H-12")
        self.assertEqual(codes_for(documents), ("E_RESUME_FINGERPRINT",))

    def test_each_fingerprint_component_is_checked(self) -> None:
        for key in ("dataset", "reference", "hypothesis", "metric_plan", "config"):
            with self.subTest(fingerprint=key):
                documents = documents_of("H-11")
                previous = documents["eval_run_manifest"]["resume"]["previous_fingerprints"]
                previous[key] = "sha256:" + "ff" * 32
                self.assertIn("E_RESUME_FINGERPRINT", codes_for(documents))

    def test_changed_metric_implementation_version_is_rejected(self) -> None:
        documents = documents_of("H-11")
        for entry in previous_versions_of(documents):
            if entry["axis"] == "source" and entry["metric_id"] == "cer":
                entry["implementation_version"] = "cer/9.9.9"
        self.assertIn("E_RESUME_FINGERPRINT", codes_for(documents))

    def test_duplicate_completed_shard_is_rejected(self) -> None:
        documents = documents_of("H-11")
        shards = documents["eval_run_manifest"]["resume"]["completed_shards"]
        shards.append({"shard_id": "shard-000", "content_hash": "sha256:" + "ab" * 32})
        self.assertIn("E_SHARD_DUPLICATE", codes_for(documents))

    def test_duplicate_shard_content_hash_is_rejected(self) -> None:
        documents = documents_of("H-11")
        shards = documents["eval_run_manifest"]["resume"]["completed_shards"]
        shards.append({"shard_id": "shard-002", "content_hash": shards[0]["content_hash"]})
        self.assertIn("E_SHARD_DUPLICATE", codes_for(documents))


class TimeContractTests(unittest.TestCase):
    def test_zero_length_and_reversed_cue_ranges_are_rejected(self) -> None:
        for start, end in ((2.5, 2.5), (2.5, 0.5)):
            with self.subTest(start=start, end=end):
                documents = documents_of("H-01")
                cue = documents["reference_bundles"][0]["reference_cues"][0]
                cue["start_seconds"] = start
                cue["end_seconds"] = end
                self.assertIn("E_TIME_RANGE", codes_for(documents))

    def test_negative_time_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["reference_bundles"][0]["reference_cues"][0]["start_seconds"] = -1.0
        self.assertIn("E_SCHEMA", codes_for(documents))

    def test_degraded_timebase_without_mapping_is_rejected(self) -> None:
        documents = documents_of("H-06")
        del documents["reference_bundles"][0]["time_mapping"]
        self.assertIn("E_TIME_MAPPING", codes_for(documents))

    def test_non_monotonic_mapping_is_rejected(self) -> None:
        documents = documents_of("H-06")
        documents["reference_bundles"][0]["time_mapping"]["is_monotonic"] = False
        self.assertIn("E_TIME_MAPPING", codes_for(documents))

    def test_out_of_order_segments_are_rejected(self) -> None:
        documents = documents_of("H-06")
        mapping = documents["reference_bundles"][0]["time_mapping"]
        mapping["segments"] = [
            {"from_start": 3.0, "from_end": 6.0, "to_start": 4.0, "to_end": 7.0, "scale": 1.0},
            {"from_start": 0.0, "from_end": 3.0, "to_start": 0.0, "to_end": 3.0, "scale": 1.0},
        ]
        self.assertIn("E_TIME_MAPPING", codes_for(documents))

    def test_invertible_claim_with_inserted_spans_is_rejected(self) -> None:
        documents = documents_of("H-06")
        documents["reference_bundles"][0]["time_mapping"]["is_invertible"] = True
        self.assertIn("E_TIME_MAPPING", codes_for(documents))

    def test_non_invertible_mapping_keeps_text_but_not_timing(self) -> None:
        documents = documents_of("H-05")
        self.assertEqual(codes_for(documents), ())
        status = metric_status_map(documents)
        self.assertEqual(status["source"]["cer"], "computed")
        self.assertEqual(status["source"]["timing.start_error_median"], "unsupported")
        self.assertEqual(status["target"]["chrf2"], "computed")
        self.assertEqual(status["target"]["timing.start_error_median"], "unsupported")

    def test_computing_timing_under_non_invertible_mapping_is_rejected(self) -> None:
        documents = documents_of("H-05")
        documents["eval_report"]["metrics_by_axis"]["source"]["timing.start_error_median"] = {
            "schema_version": "1.0.0",
            "metric_id": "timing.start_error_median",
            "status": "computed",
            "value": 0.05,
        }
        self.assertIn("E_TIME_MAPPING", codes_for(documents))

    def test_inserted_silence_must_be_attributed_to_both_axes(self) -> None:
        documents = documents_of("H-06")
        self.assertEqual(codes_for(documents), ())
        del documents["eval_report"]["metrics_by_axis"]["target"][
            "silence.hallucination_chars_per_min"
        ]
        self.assertIn("E_SILENCE_ATTRIBUTION", codes_for(documents))


class OverlapAndReferenceIntegrityTests(unittest.TestCase):
    def test_overlapping_speaker_reference_is_representable(self) -> None:
        documents = documents_of("H-01")
        bundle = documents["reference_bundles"][0]
        self.assertEqual(codes_for(documents), ())
        self.assertGreaterEqual(len(bundle["speaker_streams"]), 2)
        self.assertTrue(bundle["speech_mask"]["overlap_spans"])
        self.assertEqual(
            bundle["speech_mask"]["overlap_spans"][0]["speaker_ids"], ["spk-01", "spk-02"]
        )

    def test_single_stream_hypothesis_makes_only_cpwer_unsupported(self) -> None:
        documents = documents_of("H-07")
        self.assertEqual(codes_for(documents), ())
        status = metric_status_map(documents)
        self.assertEqual(status["source"]["cpwer"], "unsupported")
        self.assertEqual(status["source"]["overlap_coverage"], "computed")
        self.assertEqual(status["source"]["cer"], "computed")

    def test_computing_cpwer_on_a_single_stream_hypothesis_is_rejected(self) -> None:
        documents = documents_of("H-07")
        documents["eval_report"]["metrics_by_axis"]["source"]["cpwer"] = {
            "schema_version": "1.0.0",
            "metric_id": "cpwer",
            "status": "computed",
            "value": 0.3,
        }
        self.assertIn("E_METRIC_CAPABILITY", codes_for(documents))

    def test_dangling_speaker_reference_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["reference_bundles"][0]["reference_cues"][0]["speaker_id"] = "spk-missing"
        self.assertIn("E_REFERENCE_ID", codes_for(documents))

    def test_dangling_overlap_speaker_is_rejected(self) -> None:
        documents = documents_of("H-01")
        span = documents["reference_bundles"][0]["speech_mask"]["overlap_spans"][0]
        span["speaker_ids"] = ["spk-01", "spk-ghost"]
        self.assertIn("E_REFERENCE_ID", codes_for(documents))

    def test_run_id_mismatch_between_manifest_and_report_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["run_id"] = "run-other"
        self.assertIn("E_DOCUMENT_LINK", codes_for(documents))


class GuardrailTests(unittest.TestCase):
    def test_untranslated_target_leaves_guardrail_and_review_sample(self) -> None:
        documents = documents_of("H-13")
        self.assertEqual(codes_for(documents), ())
        guardrail = documents["eval_report"]["guardrails"][0]
        self.assertEqual(guardrail["guardrail_id"], "source_copy_untranslated")
        self.assertTrue(guardrail["flagged_sample_ids"])
        review = documents["human_review_records"][0]
        self.assertEqual(review["trigger"], "guardrail_flagged")
        self.assertIn(review["sample_id"], guardrail["flagged_sample_ids"])

    def test_guardrail_without_human_review_sample_is_rejected(self) -> None:
        documents = documents_of("H-13")
        documents["human_review_records"] = []
        self.assertIn("E_DOCUMENT_LINK", codes_for(documents))

    def test_guardrails_are_not_metric_scores(self) -> None:
        report_schema = SCHEMAS.documents["eval-report-v1.schema.json"]
        guardrail = report_schema["properties"]["guardrails"]["items"]
        self.assertNotIn("value", guardrail["properties"])
        self.assertNotIn("score", guardrail["properties"])


class ErrorCodeTests(unittest.TestCase):
    def test_task_006_minimum_codes_are_defined(self) -> None:
        required = {
            "E_SCHEMA",
            "E_TARGET_LANGUAGE",
            "E_AXIS_MISMATCH",
            "E_SPLIT_LEAKAGE",
            "E_RESUME_FINGERPRINT",
            "E_PAIRED_SAMPLE_SET",
            "E_FINAL_STATUS",
            "E_METRIC_VALUE_FORBIDDEN",
            "E_TIME_RANGE",
            "E_TIME_MAPPING",
        }
        self.assertTrue(required.issubset(set(ERROR_CODES)))

    def test_every_reported_code_is_a_declared_code(self) -> None:
        seen: set[str] = set()
        for path in discover_fixtures(FIXTURE_DIR):
            fixture = load_fixture(path)
            seen.update(validate_documents(fixture["documents"], SCHEMAS).codes)
        self.assertTrue(seen.issubset(set(ERROR_CODES)), seen - set(ERROR_CODES))

    def test_findings_expose_code_and_location(self) -> None:
        documents = documents_of("H-09")
        findings = validate_documents(documents, SCHEMAS).findings
        self.assertTrue(findings)
        finding = findings[0]
        self.assertEqual(finding.code, "E_SPLIT_LEAKAGE")
        self.assertTrue(finding.location.startswith("eval_run_manifest/split_evidence/"))
        self.assertIn("E_SPLIT_LEAKAGE", finding.as_line())


class ReviewM01ReferenceIntegrityTests(unittest.TestCase):
    """REVIEW-014 M-01 — artifact·timebase 참조 무결성."""

    def test_dangling_cue_timebase_ref_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["reference_bundles"][0]["reference_cues"][0]["timebase_ref"] = "tb-ghost"
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/reference_cues/0/timebase_ref",
        )

    def test_dangling_utterance_timebase_ref_is_rejected(self) -> None:
        documents = documents_of("H-01")
        stream = documents["reference_bundles"][0]["speaker_streams"][0]
        stream["utterances"][0]["timebase_ref"] = "tb-ghost"
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/speaker_streams/0/utterances/0/timebase_ref",
        )

    def test_dangling_speech_mask_timebase_ref_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["reference_bundles"][0]["speech_mask"]["timebase_ref"] = "tb-ghost"
        assert_rejected(
            self, documents, "E_REFERENCE_ID", "reference_bundles/0/speech_mask/timebase_ref"
        )

    def test_dangling_origin_artifact_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["reference_bundles"][0]["source_timebase"]["origin_artifact"] = "artifact-ghost"
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/source_timebase/origin_artifact",
        )

    def test_source_timebase_must_point_at_source_media(self) -> None:
        """존재하는 artifact라도 source_media가 아니면 거부한다."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["source_timebase"]["origin_artifact"] = bundle["degraded_media"]["artifact_id"]
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/source_timebase/origin_artifact",
        )

    def test_degraded_timebase_link_is_checked(self) -> None:
        documents = documents_of("H-06")
        documents["reference_bundles"][0]["degraded_timebase"]["origin_artifact"] = "artifact-ghost"
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/degraded_timebase/origin_artifact",
        )

    def test_degraded_timebase_without_degraded_media_is_rejected(self) -> None:
        documents = documents_of("H-06")
        del documents["reference_bundles"][0]["degraded_media"]
        assert_rejected(
            self, documents, "E_REFERENCE_ID", "reference_bundles/0/degraded_media"
        )

    def test_time_mapping_endpoints_must_be_real_timebases(self) -> None:
        for key in ("from_timebase", "to_timebase"):
            with self.subTest(endpoint=key):
                documents = documents_of("H-06")
                documents["reference_bundles"][0]["time_mapping"][key] = "tb-ghost"
                assert_rejected(
                    self,
                    documents,
                    "E_REFERENCE_ID",
                    f"reference_bundles/0/time_mapping/{key}",
                )

    def test_artifact_ref_timebase_ref_is_checked(self) -> None:
        documents = documents_of("H-01")
        documents["reference_bundles"][0]["source_media"]["timebase_ref"] = "tb-ghost"
        assert_rejected(
            self, documents, "E_REFERENCE_ID", "reference_bundles/0/source_media/timebase_ref"
        )

    def test_valid_timebase_refs_are_accepted(self) -> None:
        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["reference_cues"][0]["timebase_ref"] = "tb-source"
        bundle["source_media"]["timebase_ref"] = "tb-source"
        bundle["degraded_media"]["timebase_ref"] = "tb-degraded"
        self.assertEqual(codes_for(documents), ())


class ReviewM02CompletedContractTests(unittest.TestCase):
    """REVIEW-014 M-02 — completed/final 양방향과 required metric 완료 조건."""

    def test_missing_required_metric_rejects_completed(self) -> None:
        documents = documents_of("H-01")
        del documents["eval_report"]["metrics_by_axis"]["source"]["cer"]
        assert_rejected(
            self, documents, "E_REQUIRED_METRIC", "eval_report/metrics_by_axis/source/cer"
        )

    def test_failed_required_metric_rejects_completed(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["metrics_by_axis"]["source"]["cer"] = {
            "schema_version": "1.0.0",
            "metric_id": "cer",
            "status": "failed",
            "reason": "tokenizer raised",
        }
        assert_rejected(
            self, documents, "E_REQUIRED_METRIC", "eval_report/metrics_by_axis/source/cer"
        )

    def test_unexpected_unsupported_required_metric_rejects_completed(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["metrics_by_axis"]["source"]["cer"] = {
            "schema_version": "1.0.0",
            "metric_id": "cer",
            "status": "unsupported",
            "reason": "norm-v1 missing rule",
        }
        assert_rejected(
            self, documents, "E_REQUIRED_METRIC", "eval_report/metrics_by_axis/source/cer"
        )

    def test_completed_declared_as_partial_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["document_kind"] = "partial"
        assert_rejected(self, documents, "E_FINAL_STATUS", "eval_report/document_kind")

    def test_final_with_non_completed_status_is_rejected(self) -> None:
        documents = documents_of("H-10")
        documents["eval_report"]["document_kind"] = "final"
        assert_rejected(self, documents, "E_FINAL_STATUS", "eval_report/document_kind")

    def test_insufficient_n_needs_explicit_plan_permission(self) -> None:
        documents = documents_of("H-08")
        entry = plan_entry(documents, "source", "cer")
        self.assertIs(entry["allow_insufficient_n"], True)
        self.assertEqual(codes_for(documents), ())

        removed = documents_of("H-08")
        plan_entry(removed, "source", "cer").pop("allow_insufficient_n")
        assert_rejected(
            self, removed, "E_REQUIRED_METRIC", "eval_report/metrics_by_axis/source/cer"
        )

        disabled = documents_of("H-08")
        plan_entry(disabled, "source", "cer")["allow_insufficient_n"] = False
        assert_rejected(
            self, disabled, "E_REQUIRED_METRIC", "eval_report/metrics_by_axis/source/cer"
        )

    def test_required_metric_in_the_wrong_bucket_is_rejected(self) -> None:
        documents = documents_of("H-01")
        by_axis = documents["eval_report"]["metrics_by_axis"]
        documents["eval_report"]["metrics"]["cer"] = by_axis["source"].pop("cer")
        codes = codes_for(documents)
        self.assertIn("E_REQUIRED_METRIC", codes)
        self.assertIn("E_AXIS_MISMATCH", codes)

    def test_non_completed_runs_keep_metrics_and_diagnostics(self) -> None:
        for status in ("partial", "failed", "aborted"):
            with self.subTest(status=status):
                documents = documents_of("H-10")
                documents["eval_report"]["run_status"] = status
                self.assertEqual(codes_for(documents), ())
                report = documents["eval_report"]
                self.assertEqual(
                    report["metrics_by_axis"]["source"]["cer"]["status"], "computed"
                )
                self.assertEqual(report["metrics_by_axis"]["source"]["wer"]["status"], "failed")
                self.assertTrue(report["diagnostics"])


class ReviewM03ResumeVersionTests(unittest.TestCase):
    """REVIEW-014 M-03 — (axis, metric_id) 단위 version 동일성."""

    def test_previous_versions_are_keyed_by_axis_and_metric(self) -> None:
        documents = documents_of("H-11")
        entries = previous_versions_of(documents)
        keys = [(e["axis"], e["metric_id"]) for e in entries]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(("source", "timing.start_error_median"), keys)
        self.assertIn(("target", "timing.start_error_median"), keys)

    def test_normalization_version_change_alone_is_rejected(self) -> None:
        documents = documents_of("H-11")
        for entry in previous_versions_of(documents):
            if entry["axis"] == "source" and entry["metric_id"] == "cer":
                entry["normalization_version"] = "norm-v1/9.9.9"
        assert_rejected(
            self,
            documents,
            "E_RESUME_FINGERPRINT",
            "eval_run_manifest/resume/previous_metric_versions/source/cer",
        )

    def test_missing_normalization_version_is_rejected(self) -> None:
        documents = documents_of("H-11")
        for entry in previous_versions_of(documents):
            if entry["axis"] == "source" and entry["metric_id"] == "cer":
                entry.pop("normalization_version")
        assert_rejected(
            self,
            documents,
            "E_RESUME_FINGERPRINT",
            "eval_run_manifest/resume/previous_metric_versions/source/cer",
        )

    def test_added_normalization_version_is_rejected(self) -> None:
        documents = documents_of("H-11")
        for entry in previous_versions_of(documents):
            if entry["axis"] == "source" and entry["metric_id"] == "cpwer":
                entry["normalization_version"] = "norm-v1/0.1.0-draft"
        assert_rejected(
            self,
            documents,
            "E_RESUME_FINGERPRINT",
            "eval_run_manifest/resume/previous_metric_versions/source/cpwer",
        )

    def test_single_axis_implementation_version_change_is_rejected(self) -> None:
        for axis in ("source", "target"):
            with self.subTest(axis=axis):
                documents = documents_of("H-11")
                for entry in previous_versions_of(documents):
                    if (
                        entry["axis"] == axis
                        and entry["metric_id"] == "timing.start_error_median"
                    ):
                        entry["implementation_version"] = "timing/9.9.9"
                assert_rejected(
                    self,
                    documents,
                    "E_RESUME_FINGERPRINT",
                    f"eval_run_manifest/resume/previous_metric_versions/{axis}/"
                    "timing.start_error_median",
                )

    def test_missing_previous_entry_is_rejected(self) -> None:
        documents = documents_of("H-11")
        entries = previous_versions_of(documents)
        removed = next(e for e in entries if e["metric_id"] == "chrf2")
        entries.remove(removed)
        assert_rejected(
            self,
            documents,
            "E_RESUME_FINGERPRINT",
            "eval_run_manifest/resume/previous_metric_versions/target/chrf2",
        )

    def test_unknown_previous_entry_is_rejected(self) -> None:
        documents = documents_of("H-11")
        previous_versions_of(documents).append(
            {"axis": "source", "metric_id": "ghost", "implementation_version": "ghost/1.0.0"}
        )
        assert_rejected(
            self,
            documents,
            "E_RESUME_FINGERPRINT",
            "eval_run_manifest/resume/previous_metric_versions/source/ghost",
        )

    def test_duplicate_metric_plan_key_is_rejected(self) -> None:
        documents = documents_of("H-11")
        plan = documents["eval_run_manifest"]["metric_plan"]
        plan.append(copy.deepcopy(plan[0]))
        assert_rejected(
            self,
            documents,
            "E_METRIC_PLAN_DUPLICATE",
            f"eval_run_manifest/metric_plan/{len(plan) - 1}",
        )

    def test_duplicate_previous_version_entry_is_rejected(self) -> None:
        documents = documents_of("H-11")
        entries = previous_versions_of(documents)
        entries.append(copy.deepcopy(entries[0]))
        assert_rejected(
            self,
            documents,
            "E_METRIC_PLAN_DUPLICATE",
            f"eval_run_manifest/resume/previous_metric_versions/{len(entries) - 1}",
        )

    def test_five_fingerprints_and_shard_checks_still_apply(self) -> None:
        for key in ("dataset", "reference", "hypothesis", "metric_plan", "config"):
            with self.subTest(fingerprint=key):
                documents = documents_of("H-11")
                documents["eval_run_manifest"]["resume"]["previous_fingerprints"][key] = (
                    "sha256:" + "ff" * 32
                )
                assert_rejected(
                    self,
                    documents,
                    "E_RESUME_FINGERPRINT",
                    f"eval_run_manifest/resume/previous_fingerprints/{key}",
                )
        documents = documents_of("H-11")
        shards = documents["eval_run_manifest"]["resume"]["completed_shards"]
        shards.append({"shard_id": "shard-000", "content_hash": "sha256:" + "cd" * 32})
        assert_rejected(
            self,
            documents,
            "E_SHARD_DUPLICATE",
            f"eval_run_manifest/resume/completed_shards/{len(shards) - 1}/shard_id",
        )


class ReviewM04DocumentGraphTests(unittest.TestCase):
    """REVIEW-014 M-04 — 문서 그래프의 자기 일관성."""

    def test_split_evidence_must_cover_dataset(self) -> None:
        for kind in ("source", "speaker"):
            with self.subTest(kind=kind):
                documents = documents_of("H-01")
                documents["eval_run_manifest"]["split_evidence"][f"dev_{kind}_ids"] = ["zzz-1"]
                assert_rejected(
                    self,
                    documents,
                    "E_DOCUMENT_LINK",
                    f"eval_run_manifest/split_evidence/dev_{kind}_ids",
                )

    def test_dataset_id_in_opposite_split_evidence_is_leakage(self) -> None:
        documents = documents_of("H-01")
        documents["eval_run_manifest"]["split_evidence"]["test_source_ids"] = ["src-001"]
        assert_rejected(
            self,
            documents,
            "E_SPLIT_LEAKAGE",
            "eval_run_manifest/split_evidence/test_source_ids",
        )

    def test_test_split_uses_the_mirrored_rule(self) -> None:
        documents = documents_of("H-01")
        manifest = documents["eval_run_manifest"]
        manifest["split"] = "test"
        documents["eval_report"]["split"] = "test"
        codes = codes_for(documents)
        self.assertIn("E_DOCUMENT_LINK", codes)
        self.assertIn("E_SPLIT_LEAKAGE", codes)

    def test_paired_hypothesis_must_exist_with_matching_role(self) -> None:
        documents = documents_of("H-14")
        documents["eval_run_manifest"]["paired_comparison"][
            "baseline_hypothesis_id"
        ] = "hyp-ghost"
        assert_rejected(
            self,
            documents,
            "E_DOCUMENT_LINK",
            "eval_run_manifest/paired_comparison/baseline_hypothesis_id",
        )

        swapped = documents_of("H-14")
        swapped["eval_run_manifest"]["paired_comparison"][
            "baseline_hypothesis_id"
        ] = "hyp-candidate"
        assert_rejected(
            self,
            swapped,
            "E_DOCUMENT_LINK",
            "eval_run_manifest/paired_comparison/baseline_hypothesis_id",
        )

    def test_paired_samples_must_match_hypothesis_samples(self) -> None:
        documents = documents_of("H-14")
        paired = documents["eval_run_manifest"]["paired_comparison"]
        paired["baseline_sample_ids"] = ["smp-001"]
        assert_rejected(
            self,
            documents,
            "E_PAIRED_SAMPLE_SET",
            "eval_run_manifest/paired_comparison/baseline_sample_ids",
        )

    def test_paired_samples_must_be_inside_the_dataset(self) -> None:
        documents = documents_of("H-14")
        paired = documents["eval_run_manifest"]["paired_comparison"]
        paired["baseline_sample_ids"] = ["smp-999"]
        paired["candidate_sample_ids"] = ["smp-999"]
        for hypothesis in documents["eval_run_manifest"]["hypotheses"]:
            if hypothesis["role"] in {"baseline", "candidate"}:
                hypothesis["sample_ids"] = ["smp-999"]
        assert_rejected(
            self,
            documents,
            "E_PAIRED_SAMPLE_SET",
            "eval_run_manifest/paired_comparison/baseline_sample_ids",
        )

    def test_metric_map_key_must_match_inner_metric_id(self) -> None:
        documents = documents_of("H-01")
        documents["eval_report"]["metrics_by_axis"]["source"]["cer"]["metric_id"] = "wer"
        assert_rejected(
            self,
            documents,
            "E_METRIC_ID_MISMATCH",
            "eval_report/metrics_by_axis/source/cer/metric_id",
        )

    def test_wrong_container_type_is_rejected_not_skipped(self) -> None:
        for key in (
            "reference_bundles",
            "per_source_records",
            "event_records",
            "human_review_records",
        ):
            with self.subTest(key=key):
                documents = documents_of("H-01")
                documents[key] = {}
                assert_rejected(self, documents, "E_SCHEMA", key)

    def test_wrong_container_type_for_single_documents_is_rejected(self) -> None:
        for key in ("eval_run_manifest", "eval_report"):
            with self.subTest(key=key):
                documents = documents_of("H-01")
                documents[key] = []
                assert_rejected(self, documents, "E_SCHEMA", key)

    def test_container_check_is_reusable_on_its_own(self) -> None:
        self.assertEqual(check_document_containers({"reference_bundles": []}), [])
        findings = check_document_containers({"event_records": "nope"})
        self.assertEqual([f.code for f in findings], ["E_SCHEMA"])
        self.assertEqual(findings[0].location, "event_records")


class ReviewR01TimestampTests(unittest.TestCase):
    """REVIEW-014 R-01 — RFC 3339 UTC의 실제 달력·시각 유효성."""

    def test_impossible_date_and_time_is_rejected(self) -> None:
        documents = documents_of("H-01")
        documents["eval_run_manifest"]["created_at"] = "2026-99-99T99:99:99Z"
        assert_rejected(self, documents, "E_TIMESTAMP", "eval_run_manifest/created_at")

    def test_month_lengths_follow_the_real_calendar(self) -> None:
        cases = {
            "2026-04-31T00:00:00Z": "4월은 30일까지",
            "2026-02-30T00:00:00Z": "2월 30일 없음",
            "2026-13-01T00:00:00Z": "13월 없음",
            "2026-00-10T00:00:00Z": "0월 없음",
            "2026-01-00T00:00:00Z": "0일 없음",
        }
        for value, why in cases.items():
            with self.subTest(value=value, why=why):
                self.assertIsNotNone(utc_timestamp_error(value), why)

    def test_leap_day_follows_the_real_calendar(self) -> None:
        self.assertIsNone(utc_timestamp_error("2024-02-29T00:00:00Z"))
        self.assertIsNone(utc_timestamp_error("2000-02-29T00:00:00Z"))
        self.assertIsNotNone(utc_timestamp_error("2027-02-29T00:00:00Z"))
        self.assertIsNotNone(utc_timestamp_error("1900-02-29T00:00:00Z"))

    def test_time_ranges_are_checked(self) -> None:
        for value in (
            "2026-08-26T24:00:00Z",
            "2026-08-26T00:60:00Z",
            "2026-08-26T00:00:60Z",
        ):
            with self.subTest(value=value):
                self.assertIsNotNone(utc_timestamp_error(value))

    def test_valid_timestamps_still_pass(self) -> None:
        for value in ("2026-08-26T00:00:00Z", "2026-08-26T23:59:59.123456Z"):
            with self.subTest(value=value):
                self.assertIsNone(utc_timestamp_error(value))

    def test_every_timestamp_field_is_checked(self) -> None:
        cases = [
            (lambda d: d["reference_bundles"][0]["source_media"], "created_at",
             "reference_bundles/0/source_media/created_at"),
            (lambda d: d["reference_bundles"][0]["provenance"], "curated_at",
             "reference_bundles/0/provenance/curated_at"),
            (lambda d: d["eval_run_manifest"], "created_at", "eval_run_manifest/created_at"),
            (lambda d: d["eval_report"], "created_at", "eval_report/created_at"),
        ]
        for pick, field, location in cases:
            with self.subTest(location=location):
                documents = documents_of("H-01")
                pick(documents)[field] = "2026-02-30T00:00:00Z"
                assert_rejected(self, documents, "E_TIMESTAMP", location)

    def test_event_record_timestamp_is_checked(self) -> None:
        documents = documents_of("H-10")
        documents["event_records"][0]["emitted_at"] = "2026-02-30T00:00:00Z"
        assert_rejected(self, documents, "E_TIMESTAMP", "event_records/0/emitted_at")

    def test_semantic_annotation_is_declared_in_the_schema(self) -> None:
        common = SCHEMAS.documents["common-v1.schema.json"]
        self.assertEqual(
            common["$defs"]["timestamp"]["x-mcs-semantic"], "utc_timestamp"
        )
        self.assertIn("x-mcs-semantic", SUPPORTED_KEYWORDS)

    def test_unknown_semantic_annotation_is_a_contract_error(self) -> None:
        injected = copy.deepcopy(SCHEMAS.documents["common-v1.schema.json"])
        injected["$defs"]["timestamp"]["x-mcs-semantic"] = "not-a-real-check"
        with self.assertRaises(SchemaContractError):
            SCHEMAS._assert_supported(injected, "common-v1.schema.json#")


if __name__ == "__main__":
    unittest.main()
