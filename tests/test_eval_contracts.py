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


def previous_version_index(documents: dict[str, Any], axis: str, metric_id: str) -> int:
    for index, entry in enumerate(previous_versions_of(documents)):
        if entry["axis"] == axis and entry["metric_id"] == metric_id:
            return index
    raise AssertionError(f"이전 버전 목록에 ({axis}, {metric_id})가 없다")


_MISSING = object()


def resolve_location(documents: dict[str, Any], location: str) -> Any:
    """finding location을 입력에 JSON Pointer로 적용한다. 해석 실패면 `_MISSING`."""

    node: Any = documents
    for token in location.split("/"):
        if isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                return _MISSING
            node = node[int(token)]
        elif isinstance(node, dict):
            if token not in node:
                return _MISSING
            node = node[token]
        else:
            return _MISSING
    return node


def assert_location_resolves(
    case: unittest.TestCase, documents: dict[str, Any], location: str
) -> Any:
    value = resolve_location(documents, location)
    case.assertIsNot(value, _MISSING, f"입력에서 해석되지 않는 위치: {location}")
    return value


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
        index = previous_version_index(documents, "source", "cer")
        previous_versions_of(documents)[index]["normalization_version"] = "norm-v1/9.9.9"
        location = (
            f"eval_run_manifest/resume/previous_metric_versions/{index}/normalization_version"
        )
        assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "norm-v1/9.9.9")

    def test_missing_normalization_version_is_rejected(self) -> None:
        documents = documents_of("H-11")
        index = previous_version_index(documents, "source", "cer")
        previous_versions_of(documents)[index].pop("normalization_version")
        # 필드가 없으므로 실제로 존재하는 부모 entry를 가리킨다.
        location = f"eval_run_manifest/resume/previous_metric_versions/{index}"
        assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
        entry = assert_location_resolves(self, documents, location)
        self.assertNotIn("normalization_version", entry)

    def test_added_normalization_version_is_rejected(self) -> None:
        documents = documents_of("H-11")
        index = previous_version_index(documents, "source", "cpwer")
        previous_versions_of(documents)[index]["normalization_version"] = "norm-v1/0.1.0-draft"
        location = (
            f"eval_run_manifest/resume/previous_metric_versions/{index}/normalization_version"
        )
        assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
        assert_location_resolves(self, documents, location)

    def test_single_axis_implementation_version_change_is_rejected(self) -> None:
        for axis in ("source", "target"):
            with self.subTest(axis=axis):
                documents = documents_of("H-11")
                index = previous_version_index(documents, axis, "timing.start_error_median")
                previous_versions_of(documents)[index][
                    "implementation_version"
                ] = "timing/9.9.9"
                location = (
                    "eval_run_manifest/resume/previous_metric_versions/"
                    f"{index}/implementation_version"
                )
                assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
                self.assertEqual(
                    assert_location_resolves(self, documents, location), "timing/9.9.9"
                )

    def test_missing_previous_entry_is_rejected(self) -> None:
        documents = documents_of("H-11")
        entries = previous_versions_of(documents)
        entries.remove(next(e for e in entries if e["metric_id"] == "chrf2"))
        # entry 자체가 없으므로 실제로 존재하는 부모 배열을 가리킨다.
        location = "eval_run_manifest/resume/previous_metric_versions"
        assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
        self.assertIsInstance(assert_location_resolves(self, documents, location), list)

    def test_unknown_previous_entry_is_rejected(self) -> None:
        documents = documents_of("H-11")
        entries = previous_versions_of(documents)
        entries.append(
            {"axis": "source", "metric_id": "ghost", "implementation_version": "ghost/1.0.0"}
        )
        location = f"eval_run_manifest/resume/previous_metric_versions/{len(entries) - 1}"
        assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
        entry = assert_location_resolves(self, documents, location)
        self.assertEqual(entry["metric_id"], "ghost")

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


def valid_paired_documents() -> dict[str, Any]:
    """독립된 **유효한** paired 문서.

    H-14는 다른 이유로 이미 invalid이므로 positive base로 쓰지 않는다
    (REVIEW-015 M-04-R1). 유효한 H-01에 baseline/candidate 가설과 paired
    comparison을 더해 다섯 sample 집합이 정확히 같은 문서를 만든다.
    """

    documents = documents_of("H-01")
    manifest = documents["eval_run_manifest"]
    samples = list(manifest["dataset"]["sample_ids"])
    for role, seed in (("baseline", "aa"), ("candidate", "bb")):
        manifest["hypotheses"].append(
            {
                "hypothesis_id": f"hyp-{role}",
                "content_hash": "sha256:" + seed * 32,
                "reference_axis": "target",
                "target_language": "ko",
                "role": role,
                "sample_ids": list(samples),
            }
        )
    manifest["paired_comparison"] = {
        "baseline_hypothesis_id": "hyp-baseline",
        "candidate_hypothesis_id": "hyp-candidate",
        "baseline_sample_ids": list(samples),
        "candidate_sample_ids": list(samples),
    }
    documents["eval_report"]["paired_observation"] = {
        "baseline_hypothesis_id": "hyp-baseline",
        "candidate_hypothesis_id": "hyp-candidate",
        "n_pairs": len(samples),
        "observation": "blocked_by_open_thresholds",
    }
    return documents


def hypothesis_index(documents: dict[str, Any], hypothesis_id: str) -> int:
    for index, entry in enumerate(documents["eval_run_manifest"]["hypotheses"]):
        if entry["hypothesis_id"] == hypothesis_id:
            return index
    raise AssertionError(f"가설 {hypothesis_id!r}가 없다")


class ReviewM01R1MediaTimebaseRoleTests(unittest.TestCase):
    """REVIEW-015 M-01-R1 — 역할별 media↔timebase 연결."""

    def test_correct_source_and_degraded_links_are_accepted(self) -> None:
        """positive를 먼저 고정한다."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["source_media"]["timebase_ref"] = bundle["source_timebase"]["timebase_id"]
        bundle["degraded_media"]["timebase_ref"] = bundle["degraded_timebase"]["timebase_id"]
        self.assertEqual(codes_for(documents), ())

    def test_source_media_pointing_at_degraded_timebase_is_rejected(self) -> None:
        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["source_media"]["timebase_ref"] = bundle["degraded_timebase"]["timebase_id"]
        location = "reference_bundles/0/source_media/timebase_ref"
        assert_rejected(self, documents, "E_REFERENCE_ID", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "tb-degraded")

    def test_degraded_media_pointing_at_source_timebase_is_rejected(self) -> None:
        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["degraded_media"]["timebase_ref"] = bundle["source_timebase"]["timebase_id"]
        location = "reference_bundles/0/degraded_media/timebase_ref"
        assert_rejected(self, documents, "E_REFERENCE_ID", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "tb-source")

    def test_both_directions_swapped_is_rejected(self) -> None:
        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        source_id = bundle["source_timebase"]["timebase_id"]
        degraded_id = bundle["degraded_timebase"]["timebase_id"]
        bundle["source_media"]["timebase_ref"] = degraded_id
        bundle["degraded_media"]["timebase_ref"] = source_id
        findings = findings_for(documents)
        locations = {f.location for f in findings if f.code == "E_REFERENCE_ID"}
        self.assertIn("reference_bundles/0/source_media/timebase_ref", locations)
        self.assertIn("reference_bundles/0/degraded_media/timebase_ref", locations)

    def test_role_counterpart_missing_is_rejected(self) -> None:
        """연결을 검증할 수 없는 구성도 거부한다."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["degraded_media"]["timebase_ref"] = bundle["degraded_timebase"]["timebase_id"]
        del bundle["degraded_timebase"]
        codes = codes_for(documents)
        self.assertIn("E_REFERENCE_ID", codes)

    def test_membership_check_is_still_applied(self) -> None:
        documents = documents_of("H-06")
        documents["reference_bundles"][0]["source_media"]["timebase_ref"] = "tb-ghost"
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/source_media/timebase_ref",
        )

    def test_absent_timebase_ref_stays_optional(self) -> None:
        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        self.assertNotIn("timebase_ref", bundle["source_media"])
        self.assertEqual(codes_for(documents), ())


class ReviewM04R1PairedSampleSetTests(unittest.TestCase):
    """REVIEW-015 M-04-R1 — paired/hypothesis/dataset 다섯 집합의 정확한 동일성."""

    def test_independent_valid_paired_document_passes(self) -> None:
        documents = valid_paired_documents()
        self.assertEqual(codes_for(documents), ())
        manifest = documents["eval_run_manifest"]
        dataset = set(manifest["dataset"]["sample_ids"])
        paired = manifest["paired_comparison"]
        self.assertEqual(set(paired["baseline_sample_ids"]), dataset)
        self.assertEqual(set(paired["candidate_sample_ids"]), dataset)
        for role in ("baseline", "candidate"):
            index = hypothesis_index(documents, f"hyp-{role}")
            self.assertEqual(set(manifest["hypotheses"][index]["sample_ids"]), dataset)

    def test_proper_subset_of_dataset_is_rejected(self) -> None:
        """다섯 집합이 서로 같아도 dataset의 진부분집합이면 거부한다."""

        documents = valid_paired_documents()
        manifest = documents["eval_run_manifest"]
        subset = manifest["dataset"]["sample_ids"][:1]
        manifest["paired_comparison"]["baseline_sample_ids"] = list(subset)
        manifest["paired_comparison"]["candidate_sample_ids"] = list(subset)
        for role in ("baseline", "candidate"):
            index = hypothesis_index(documents, f"hyp-{role}")
            manifest["hypotheses"][index]["sample_ids"] = list(subset)
        for location in (
            "eval_run_manifest/paired_comparison/baseline_sample_ids",
            "eval_run_manifest/paired_comparison/candidate_sample_ids",
        ):
            with self.subTest(location=location):
                assert_rejected(self, documents, "E_PAIRED_SAMPLE_SET", location)
                assert_location_resolves(self, documents, location)

    def test_missing_baseline_hypothesis_sample_ids_is_rejected(self) -> None:
        documents = valid_paired_documents()
        index = hypothesis_index(documents, "hyp-baseline")
        documents["eval_run_manifest"]["hypotheses"][index].pop("sample_ids")
        location = f"eval_run_manifest/hypotheses/{index}"
        assert_rejected(self, documents, "E_PAIRED_SAMPLE_SET", location)
        entry = assert_location_resolves(self, documents, location)
        self.assertNotIn("sample_ids", entry)

    def test_missing_candidate_hypothesis_sample_ids_is_rejected(self) -> None:
        documents = valid_paired_documents()
        index = hypothesis_index(documents, "hyp-candidate")
        documents["eval_run_manifest"]["hypotheses"][index].pop("sample_ids")
        assert_rejected(
            self, documents, "E_PAIRED_SAMPLE_SET", f"eval_run_manifest/hypotheses/{index}"
        )

    def test_paired_and_hypothesis_mismatch_is_rejected(self) -> None:
        documents = valid_paired_documents()
        manifest = documents["eval_run_manifest"]
        index = hypothesis_index(documents, "hyp-baseline")
        manifest["hypotheses"][index]["sample_ids"] = ["smp-001"]
        location = f"eval_run_manifest/hypotheses/{index}/sample_ids"
        assert_rejected(self, documents, "E_PAIRED_SAMPLE_SET", location)
        assert_location_resolves(self, documents, location)

    def test_hypothesis_and_dataset_mismatch_is_rejected(self) -> None:
        documents = valid_paired_documents()
        manifest = documents["eval_run_manifest"]
        manifest["dataset"]["sample_ids"] = ["smp-001", "smp-002", "smp-003"]
        codes = codes_for(documents)
        self.assertIn("E_PAIRED_SAMPLE_SET", codes)
        locations = {
            f.location for f in findings_for(documents) if f.code == "E_PAIRED_SAMPLE_SET"
        }
        self.assertIn("eval_run_manifest/paired_comparison/baseline_sample_ids", locations)
        self.assertIn("eval_run_manifest/paired_comparison/candidate_sample_ids", locations)

    def test_duplicate_sample_ids_are_blocked_by_schema(self) -> None:
        """중복은 schema의 uniqueItems가 이미 금지한다."""

        manifest_schema = SCHEMAS.documents["eval-run-manifest-v1.schema.json"]
        paired = manifest_schema["properties"]["paired_comparison"]["properties"]
        self.assertIs(paired["baseline_sample_ids"]["uniqueItems"], True)
        self.assertIs(paired["candidate_sample_ids"]["uniqueItems"], True)
        dataset = manifest_schema["properties"]["dataset"]["properties"]
        self.assertIs(dataset["sample_ids"]["uniqueItems"], True)
        hypotheses = manifest_schema["properties"]["hypotheses"]["items"]["properties"]
        self.assertIs(hypotheses["sample_ids"]["uniqueItems"], True)

        documents = valid_paired_documents()
        documents["eval_run_manifest"]["paired_comparison"]["baseline_sample_ids"].append(
            "smp-001"
        )
        assert_rejected(
            self,
            documents,
            "E_SCHEMA",
            "eval_run_manifest/paired_comparison/baseline_sample_ids/2",
        )

    def test_h14_still_fails_for_its_own_reason(self) -> None:
        self.assertEqual(codes_for(documents_of("H-14")), ("E_PAIRED_SAMPLE_SET",))


class ReviewR031ResumeLocationTests(unittest.TestCase):
    """REVIEW-015 R-03-1 — resume finding이 실제 입력 노드를 가리킨다."""

    def test_no_synthetic_axis_metric_pointer_is_emitted(self) -> None:
        documents = documents_of("H-11")
        index = previous_version_index(documents, "source", "cer")
        previous_versions_of(documents)[index]["normalization_version"] = "norm-v1/9.9.9"
        locations = [f.location for f in findings_for(documents)]
        self.assertTrue(locations)
        for location in locations:
            self.assertNotIn("previous_metric_versions/source/", location)
            self.assertNotIn("previous_metric_versions/target/", location)

    def test_every_resume_finding_location_resolves(self) -> None:
        def mutate_impl(documents: dict[str, Any]) -> None:
            index = previous_version_index(documents, "target", "chrf2")
            previous_versions_of(documents)[index]["implementation_version"] = "chrf2/9.9.9"

        def mutate_norm(documents: dict[str, Any]) -> None:
            index = previous_version_index(documents, "target", "chrf2")
            previous_versions_of(documents)[index]["normalization_version"] = "norm-v1/9.9.9"

        def drop_norm(documents: dict[str, Any]) -> None:
            index = previous_version_index(documents, "source", "cer")
            previous_versions_of(documents)[index].pop("normalization_version")

        def drop_entry(documents: dict[str, Any]) -> None:
            entries = previous_versions_of(documents)
            entries.remove(next(e for e in entries if e["metric_id"] == "cpwer"))

        def add_unknown(documents: dict[str, Any]) -> None:
            previous_versions_of(documents).append(
                {"axis": "target", "metric_id": "ghost", "implementation_version": "g/1.0.0"}
            )

        for mutate in (mutate_impl, mutate_norm, drop_norm, drop_entry, add_unknown):
            with self.subTest(mutation=mutate.__name__):
                documents = documents_of("H-11")
                mutate(documents)
                findings = findings_for(documents)
                self.assertTrue(findings)
                for finding in findings:
                    self.assertEqual(finding.code, "E_RESUME_FINGERPRINT")
                    self.assertIn("previous_metric_versions", finding.location)
                    assert_location_resolves(self, documents, finding.location)

    def test_value_mismatch_points_at_the_exact_field(self) -> None:
        documents = documents_of("H-11")
        index = previous_version_index(documents, "target", "chrf2")
        previous_versions_of(documents)[index]["implementation_version"] = "chrf2/9.9.9"
        location = (
            f"eval_run_manifest/resume/previous_metric_versions/{index}/implementation_version"
        )
        assert_rejected(self, documents, "E_RESUME_FINGERPRINT", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "chrf2/9.9.9")

    def test_duplicate_entry_points_at_the_real_index(self) -> None:
        documents = documents_of("H-11")
        entries = previous_versions_of(documents)
        entries.append(copy.deepcopy(entries[0]))
        location = f"eval_run_manifest/resume/previous_metric_versions/{len(entries) - 1}"
        assert_rejected(self, documents, "E_METRIC_PLAN_DUPLICATE", location)
        assert_location_resolves(self, documents, location)

    def test_output_order_stays_deterministic(self) -> None:
        documents = documents_of("H-11")
        for entry in previous_versions_of(documents):
            entry["implementation_version"] = "x/9.9.9"
        first = findings_for(documents)
        second = findings_for(copy.deepcopy(documents))
        self.assertEqual(first, second)
        self.assertEqual(list(first), sort_findings(first))
        self.assertEqual({f.code for f in first}, {"E_RESUME_FINGERPRINT"})


def rewrite_bundle_ids(documents: dict[str, Any], replacements: dict[str, str]) -> None:
    """번들 안의 ID 문자열을 **정의와 참조 모두** 한꺼번에 바꾼다.

    정의 ID만 바꾸면 dangling reference 검사가 먼저 걸려서 정작 확인하려는
    정의 유일성 검사에 도달하지 못한다.
    """

    raw = json.dumps(documents["reference_bundles"][0])
    for old, new in replacements.items():
        raw = raw.replace(old, new)
    documents["reference_bundles"][0] = json.loads(raw)


class ReviewM01R2DefinitionIdentityTests(unittest.TestCase):
    """REVIEW-016 M-01-R2 — timebase 역할 domain과 정의 ID의 유일성."""

    def test_correct_bundle_is_accepted(self) -> None:
        """positive를 먼저 고정한다 — H-06은 source/degraded 정의가 모두 있다."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        self.assertEqual(bundle["source_timebase"]["domain"], "source")
        self.assertEqual(bundle["degraded_timebase"]["domain"], "degraded")
        self.assertNotEqual(
            bundle["source_timebase"]["timebase_id"],
            bundle["degraded_timebase"]["timebase_id"],
        )
        self.assertNotEqual(
            bundle["source_media"]["artifact_id"], bundle["degraded_media"]["artifact_id"]
        )
        self.assertEqual(codes_for(documents), ())

    def test_degraded_counterpart_absent_stays_valid(self) -> None:
        """source 정의만 있는 번들은 이 검사가 새로 거부하지 않는다."""

        documents = documents_of("H-01")
        bundle = documents["reference_bundles"][0]
        self.assertNotIn("degraded_timebase", bundle)
        self.assertEqual(bundle["source_timebase"]["domain"], "source")
        self.assertEqual(codes_for(documents), ())

    def test_domain_swap_is_rejected(self) -> None:
        """역할별 연결만 검사하면 통과하던 입력 — 두 domain만 서로 바꾼 문서."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["source_timebase"]["domain"] = "degraded"
        bundle["degraded_timebase"]["domain"] = "source"
        for key, wrong in (("source_timebase", "degraded"), ("degraded_timebase", "source")):
            with self.subTest(key=key):
                location = f"reference_bundles/0/{key}/domain"
                assert_rejected(self, documents, "E_REFERENCE_ID", location)
                self.assertEqual(assert_location_resolves(self, documents, location), wrong)

    def test_single_domain_error_is_rejected(self) -> None:
        """한쪽만 틀려도 거부한다 (두 개를 동시에 바꿔야만 걸리는 검사가 아니다)."""

        documents = documents_of("H-06")
        documents["reference_bundles"][0]["degraded_timebase"]["domain"] = "source"
        assert_rejected(
            self,
            documents,
            "E_REFERENCE_ID",
            "reference_bundles/0/degraded_timebase/domain",
        )

    def test_collapsed_timebase_definition_id_is_rejected(self) -> None:
        """두 시간축 정의를 같은 ID 하나로 합친 문서는 구분이 불가능하다."""

        documents = documents_of("H-06")
        rewrite_bundle_ids(documents, {"tb-source": "tb-shared", "tb-degraded": "tb-shared"})
        location = "reference_bundles/0/degraded_timebase/timebase_id"
        assert_rejected(self, documents, "E_REFERENCE_ID", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "tb-shared")

    def test_collapsed_artifact_definition_id_is_rejected(self) -> None:
        """서로 다른 media 정의가 같은 artifact_id를 쓰면 모호하다."""

        documents = documents_of("H-06")
        rewrite_bundle_ids(
            documents,
            {"art-source-media": "artifact-shared", "art-degraded-media": "artifact-shared"},
        )
        location = "reference_bundles/0/degraded_media/artifact_id"
        assert_rejected(self, documents, "E_REFERENCE_ID", location)
        self.assertEqual(
            assert_location_resolves(self, documents, location), "artifact-shared"
        )

    def test_identical_definition_is_not_treated_as_ambiguous(self) -> None:
        """정의가 완전히 같으면 중복일 뿐 모호하지 않다 — 검사 범위를 명시한다."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["clean_video"] = copy.deepcopy(bundle["source_media"])
        self.assertEqual(codes_for(documents), ())

    def test_reference_reusing_a_definition_id_is_not_a_duplicate(self) -> None:
        """정의 ID와 참조 ID를 구분한다 — 정상 연결을 중복으로 오인하지 않는다."""

        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        self.assertEqual(
            bundle["source_timebase"]["origin_artifact"], bundle["source_media"]["artifact_id"]
        )
        bundle["source_media"]["timebase_ref"] = bundle["source_timebase"]["timebase_id"]
        bundle["degraded_media"]["timebase_ref"] = bundle["degraded_timebase"]["timebase_id"]
        self.assertEqual(codes_for(documents), ())

    def test_definition_findings_are_deterministic(self) -> None:
        documents = documents_of("H-06")
        bundle = documents["reference_bundles"][0]
        bundle["source_timebase"]["domain"] = "degraded"
        bundle["degraded_timebase"]["domain"] = "source"
        first = findings_for(documents)
        second = findings_for(copy.deepcopy(documents))
        self.assertEqual(first, second)
        self.assertEqual(list(first), sort_findings(first))
        for finding in first:
            assert_location_resolves(self, documents, finding.location)


class ReviewM04R2HypothesisIdUniquenessTests(unittest.TestCase):
    """REVIEW-016 M-04-R2 — hypothesis_id 유일성은 그래프 해석보다 먼저다."""

    def test_unique_hypothesis_ids_are_accepted(self) -> None:
        documents = valid_paired_documents()
        ids = [h["hypothesis_id"] for h in documents["eval_run_manifest"]["hypotheses"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(codes_for(documents), ())

    def test_duplicate_baseline_id_with_different_content_is_rejected(self) -> None:
        """같은 ID를 가진 **내용이 다른** 두 번째 가설."""

        documents = valid_paired_documents()
        hypotheses = documents["eval_run_manifest"]["hypotheses"]
        hypotheses.append(
            {
                "hypothesis_id": "hyp-baseline",
                "content_hash": "sha256:" + "cc" * 32,
                "reference_axis": "target",
                "target_language": "ko",
                "role": "baseline",
                "sample_ids": ["smp-001"],
            }
        )
        location = f"eval_run_manifest/hypotheses/{len(hypotheses) - 1}/hypothesis_id"
        assert_rejected(self, documents, "E_DOCUMENT_LINK", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "hyp-baseline")

    def test_duplicate_candidate_id_is_rejected(self) -> None:
        documents = valid_paired_documents()
        hypotheses = documents["eval_run_manifest"]["hypotheses"]
        hypotheses.append(
            {
                "hypothesis_id": "hyp-candidate",
                "content_hash": "sha256:" + "dd" * 32,
                "reference_axis": "target",
                "target_language": "ko",
                "role": "candidate",
                "sample_ids": ["smp-001"],
            }
        )
        location = f"eval_run_manifest/hypotheses/{len(hypotheses) - 1}/hypothesis_id"
        assert_rejected(self, documents, "E_DOCUMENT_LINK", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "hyp-candidate")

    def test_duplicate_is_detected_when_the_order_is_reversed(self) -> None:
        """목록 순서를 바꿔도 중복은 검출된다 — 첫 객체만 고르지 않는다."""

        documents = valid_paired_documents()
        hypotheses = documents["eval_run_manifest"]["hypotheses"]
        original = hypothesis_index(documents, "hyp-baseline")
        hypotheses.insert(
            original,
            {
                "hypothesis_id": "hyp-baseline",
                "content_hash": "sha256:" + "cc" * 32,
                "reference_axis": "target",
                "target_language": "ko",
                "role": "baseline",
                "sample_ids": ["smp-001"],
            },
        )
        location = f"eval_run_manifest/hypotheses/{original + 1}/hypothesis_id"
        assert_rejected(self, documents, "E_DOCUMENT_LINK", location)
        self.assertEqual(assert_location_resolves(self, documents, location), "hyp-baseline")
        # 앞에 놓인 쪽을 조용히 채택하면 표본 판정이 뒤집힌다. 중복만 보고해야 한다.
        self.assertEqual(codes_for(documents), ("E_DOCUMENT_LINK",))

    def test_ambiguous_id_is_not_resolved_into_a_paired_object(self) -> None:
        """모호한 ID에서 표본 판정을 만들어내지 않는다 — 중복만 보고한다."""

        documents = valid_paired_documents()
        documents["eval_run_manifest"]["hypotheses"].append(
            {
                "hypothesis_id": "hyp-baseline",
                "content_hash": "sha256:" + "cc" * 32,
                "reference_axis": "target",
                "target_language": "ko",
                "role": "baseline",
                "sample_ids": ["smp-001"],
            }
        )
        self.assertEqual(codes_for(documents), ("E_DOCUMENT_LINK",))

    def test_duplicate_unrelated_to_paired_comparison_is_still_rejected(self) -> None:
        """paired comparison이 없어도 ID 유일성은 manifest 전체에 적용된다."""

        documents = documents_of("H-01")
        hypotheses = documents["eval_run_manifest"]["hypotheses"]
        self.assertNotIn("paired_comparison", documents["eval_run_manifest"])
        hypotheses.append(copy.deepcopy(hypotheses[0]))
        location = f"eval_run_manifest/hypotheses/{len(hypotheses) - 1}/hypothesis_id"
        assert_rejected(self, documents, "E_DOCUMENT_LINK", location)

    def test_duplicate_findings_are_deterministic(self) -> None:
        documents = valid_paired_documents()
        hypotheses = documents["eval_run_manifest"]["hypotheses"]
        for role in ("baseline", "candidate"):
            hypotheses.append(
                {
                    "hypothesis_id": f"hyp-{role}",
                    "content_hash": "sha256:" + "ee" * 32,
                    "reference_axis": "target",
                    "target_language": "ko",
                    "role": role,
                    "sample_ids": ["smp-001"],
                }
            )
        first = findings_for(documents)
        second = findings_for(copy.deepcopy(documents))
        self.assertEqual(first, second)
        self.assertEqual(list(first), sort_findings(first))
        self.assertEqual({f.code for f in first}, {"E_DOCUMENT_LINK"})
        self.assertEqual(len(first), 2, "중복 하나만 보고하고 멈추면 안 된다")
        for finding in first:
            assert_location_resolves(self, documents, finding.location)

    def test_review_015_paired_counterexamples_still_fail(self) -> None:
        """REVIEW-015의 핵심 반례가 유일성 검사 도입 뒤에도 그대로 거부된다."""

        subset = valid_paired_documents()
        manifest = subset["eval_run_manifest"]
        only_one = manifest["dataset"]["sample_ids"][:1]
        manifest["paired_comparison"]["baseline_sample_ids"] = list(only_one)
        manifest["paired_comparison"]["candidate_sample_ids"] = list(only_one)
        for role in ("baseline", "candidate"):
            manifest["hypotheses"][hypothesis_index(subset, f"hyp-{role}")]["sample_ids"] = list(
                only_one
            )
        assert_rejected(
            self,
            subset,
            "E_PAIRED_SAMPLE_SET",
            "eval_run_manifest/paired_comparison/baseline_sample_ids",
        )

        missing = valid_paired_documents()
        index = hypothesis_index(missing, "hyp-baseline")
        missing["eval_run_manifest"]["hypotheses"][index].pop("sample_ids")
        assert_rejected(
            self, missing, "E_PAIRED_SAMPLE_SET", f"eval_run_manifest/hypotheses/{index}"
        )

        self.assertEqual(codes_for(documents_of("H-14")), ("E_PAIRED_SAMPLE_SET",))


class ReviewR03R2RequiredFieldLocationTests(unittest.TestCase):
    """REVIEW-016 R-03-R2 — 필수 필드 누락 위치가 입력에서 해석된다.

    없는 leaf를 가리키는 pointer는 입력에 적용되지 않는다. 실제로 존재하는 부모
    객체를 가리키고, 누락된 필드 이름은 메시지에 담는다.
    """

    def test_missing_resume_implementation_version_location_resolves(self) -> None:
        documents = documents_of("H-11")
        entry = previous_versions_of(documents)[0]
        entry.pop("implementation_version")
        location = "eval_run_manifest/resume/previous_metric_versions/0"
        assert_rejected(self, documents, "E_SCHEMA", location)
        resolved = assert_location_resolves(self, documents, location)
        self.assertIs(resolved, entry)
        self.assertNotIn("implementation_version", resolved)

    def test_missing_field_name_is_reported_in_the_message(self) -> None:
        documents = documents_of("H-11")
        previous_versions_of(documents)[0].pop("implementation_version")
        messages = [
            f.message
            for f in findings_for(documents)
            if f.location == "eval_run_manifest/resume/previous_metric_versions/0"
        ]
        self.assertTrue(messages)
        self.assertTrue(
            any("implementation_version" in message for message in messages),
            f"누락 필드 이름이 메시지에 없다: {messages}",
        )

    def test_every_missing_required_field_location_resolves(self) -> None:
        cases = (
            ("eval_run_manifest", ("eval_run_manifest",), "config_hash"),
            ("dataset", ("eval_run_manifest", "dataset"), "dataset_hash"),
            (
                "fingerprints",
                ("eval_run_manifest", "fingerprints"),
                "config",
            ),
            ("bundle", ("reference_bundles", 0), "provenance"),
            (
                "source_timebase",
                ("reference_bundles", 0, "source_timebase"),
                "origin_artifact",
            ),
        )
        for name, path, field in cases:
            with self.subTest(node=name):
                documents = documents_of("H-01")
                node: Any = documents
                for token in path:
                    node = node[token]
                node.pop(field)
                findings = findings_for(documents)
                self.assertTrue(findings, f"{name}/{field} 누락이 통과했다")
                schema_findings = [f for f in findings if f.code == "E_SCHEMA"]
                self.assertTrue(schema_findings)
                for finding in schema_findings:
                    resolved = assert_location_resolves(self, documents, finding.location)
                    self.assertIsInstance(resolved, (dict, list))

    def test_present_documents_report_no_required_field_finding(self) -> None:
        self.assertEqual(codes_for(documents_of("H-01")), ())
        self.assertEqual(codes_for(documents_of("H-11")), ())


class SharedSchemaCoreTests(unittest.TestCase):
    """TASK-028 공용 helper 추출 회귀 — 두 구현이 갈라지지 않는다.

    TASK-028은 `eval_contracts`와 `job_runtime`이 **같은** schema 해석을 쓰도록
    검사기를 `schema_core`로 옮겼다. 이름만 공유하고 의미가 갈라지는 복제 구현이
    다시 생기면 이 테스트가 실패한다 (TASK-028 §3.6).
    """

    def test_public_names_are_the_shared_implementation_not_a_copy(self) -> None:
        from media_clarity import eval_contracts, schema_core

        for name in (
            "Finding",
            "JsonInputError",
            "SchemaContractError",
            "SchemaValidator",
            "loads_strict",
            "load_strict",
            "sort_findings",
            "utc_timestamp_error",
            "portable_relative_path_error",
            "SUPPORTED_KEYWORDS",
            "SEMANTIC_CHECKS",
            "SCHEMA_DIALECT",
            "SCHEMA_VERSION",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(eval_contracts, name),
                    getattr(schema_core, name),
                    f"{name}이 schema_core와 다른 객체다 — 복제 구현일 수 있다",
                )

    def test_task_006_schema_set_is_the_shared_one_narrowed_to_seven_files(self) -> None:
        from media_clarity import eval_contracts, schema_core

        self.assertTrue(issubclass(eval_contracts.SchemaSet, schema_core.SchemaSet))
        self.assertEqual(SCHEMAS.filenames, eval_contracts.SCHEMA_FILES)
        self.assertEqual(len(eval_contracts.SCHEMA_FILES), 7)
        self.assertIn(schema_core.COMMON_SCHEMA_FILE, eval_contracts.SCHEMA_FILES)

    def test_task_006_verdicts_are_unchanged_after_the_extraction(self) -> None:
        """H-01~H-14의 판정·오류 코드·순서·pointer가 그대로다."""

        expected = {
            "H-01": (),
            "H-02": (),
            "H-03": ("E_TARGET_LANGUAGE",),
            "H-04": ("E_AXIS_MISMATCH",),
            "H-05": (),
            "H-06": (),
            "H-07": (),
            "H-08": (),
            "H-09": ("E_SPLIT_LEAKAGE",),
            "H-10": (),
            "H-11": (),
            "H-12": ("E_RESUME_FINGERPRINT",),
            "H-13": (),
            "H-14": ("E_PAIRED_SAMPLE_SET",),
        }
        self.assertEqual(sorted(expected), sorted(EXPECTED_CASE_IDS))
        for case, codes in expected.items():
            with self.subTest(case=case):
                documents = documents_of(case)
                findings = findings_for(documents)
                self.assertEqual(codes_for(documents), codes)
                self.assertEqual(list(findings), sort_findings(findings))
                for finding in findings:
                    assert_location_resolves(self, documents, finding.location)

    def test_unsupported_keyword_still_stops_as_a_contract_defect(self) -> None:
        from media_clarity import schema_core

        injected = copy.deepcopy(SCHEMAS.documents["common-v1.schema.json"])
        injected["$defs"]["identifier"]["oneOf"] = []
        with self.assertRaises(schema_core.SchemaContractError):
            SCHEMAS._assert_supported(injected, "common-v1.schema.json#")

    def test_a_schema_set_without_the_common_contract_is_a_contract_defect(self) -> None:
        from media_clarity import schema_core

        with self.assertRaises(schema_core.SchemaContractError):
            schema_core.SchemaSet(DEFAULT_SCHEMA_DIR, ("eval-report-v1.schema.json",))


if __name__ == "__main__":
    unittest.main()
