"""TASK-029 자막 spine 계약 테스트.

fixture의 expected를 그대로 통과시키지 않는다. 실제 `schemas/`의 다섯 정본과 production
`subtitle_contracts` API를 호출하고, 계약을 어기는 변형이 반드시 잡히는지 확인한다.

`scripts/verify_task_029.py`의 input mutation manifest를 그대로 재사용한다. mutation 목록의
정본은 한 곳이며 테스트와 검증 script가 갈라지지 않는다. schema·validator code mutation은
저장소 밖 임시 사본이 필요하므로 그 script가 담당하고 여기서는 다루지 않는다.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any

from media_clarity.schema_core import SCHEMA_DIALECT, SUPPORTED_KEYWORDS, SchemaContractError
from media_clarity.subtitle_contracts import (
    ALLOWED_LINE_BREAK_SCALARS,
    DOCUMENT_KEYS,
    ERROR_CODES,
    EXPECTED_CASE_IDS,
    SCHEMA_FILES,
    TARGET_LANGUAGE,
    SchemaSet,
    check_speech_segments,
    discover_fixtures,
    evaluate_fixture,
    load_fixture,
    load_strict,
    validate_documents,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schemas"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "subtitle_contracts"

#: TASK-029 §10 기준선 rollback guard. 기존 계약이 바뀌면 즉시 실패한다.
BASELINE_HASHES = {
    "common-v1.schema.json": (
        "0d00e20511e0585547b1e0be6211270d600bff7f6196e849aa258fde0f392f33",
        "e498654fa1d4a6eb0c2bb3d09b7d50e48a1e26b0b999598d1651884881681292",
    ),
    "job-v1.schema.json": (
        "47a570efdb058dddb94228cba645d1432d675c910e5640f59e3dec5d0e395dab",
        "92f17a2284520b2523205ad685bfa4d23df087bcd7ee0d5f0cd4df4da3ba2e9e",
    ),
}

NEW_SCHEMA_FILES = (
    "speech-segment-v1.schema.json",
    "transcript-v1.schema.json",
    "adapter-capability-report-v1.schema.json",
    "translated-transcript-v1.schema.json",
    "subtitle-document-v1.schema.json",
)


def _load_verify_script():
    """`scripts/verify_task_029.py`를 모듈로 읽는다 (mutation manifest의 정본)."""

    path = REPO_ROOT / "scripts" / "verify_task_029.py"
    spec = importlib.util.spec_from_file_location("verify_task_029", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_task_029"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ContractCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = SchemaSet(SCHEMA_DIR)


# ---------------------------------------------------------------------------
# schema 정본 자체의 계약
# ---------------------------------------------------------------------------


class SchemaContractTests(ContractCase):
    def documents(self) -> dict[str, Any]:
        return {name: load_strict(SCHEMA_DIR / name) for name in NEW_SCHEMA_FILES}

    def test_schema_set_covers_exactly_the_task_files(self) -> None:
        self.assertEqual(
            SCHEMA_FILES, ("common-v1.schema.json",) + tuple(sorted(
                NEW_SCHEMA_FILES,
                key=lambda name: (
                    "speech-segment",
                    "adapter-capability-report",
                    "transcript",
                    "translated-transcript",
                    "subtitle-document",
                ).index(name.split("-v1")[0]),
            ))
        )

    def test_every_root_declares_dialect_id_and_schema_version(self) -> None:
        for name, document in self.documents().items():
            with self.subTest(schema=name):
                self.assertEqual(document["$schema"], SCHEMA_DIALECT)
                self.assertTrue(document["$id"].endswith(name), document["$id"])
                self.assertEqual(
                    document["properties"]["schema_version"]["$ref"],
                    "common-v1.schema.json#/$defs/schema_version",
                )

    def test_production_objects_are_closed(self) -> None:
        """production 객체는 전부 `additionalProperties: false`다."""

        def walk(node: Any, where: str, opened: list[str]) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object" and "properties" in node:
                    if node.get("additionalProperties") is not False:
                        opened.append(where)
                for key, value in node.items():
                    walk(value, f"{where}/{key}", opened)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{where}/{index}", opened)

        for name, document in self.documents().items():
            opened: list[str] = []
            walk(document, name, opened)
            self.assertEqual(opened, [], f"{name}: 열린 production 객체")

    def test_only_supported_keywords_are_used(self) -> None:
        """`schema_core.SUPPORTED_KEYWORDS` 밖의 keyword를 쓰지 않는다 (oneOf 등 금지)."""

        forbidden = {"oneOf", "anyOf", "allOf", "not", "if", "then", "else", "contains", "format"}
        blob = "".join(
            (SCHEMA_DIR / name).read_text(encoding="utf-8") for name in NEW_SCHEMA_FILES
        )
        for keyword in forbidden:
            self.assertNotIn(f'"{keyword}"', blob, f"{keyword}를 썼다")
        # SchemaSet 생성 자체가 SUPPORTED_KEYWORDS 밖의 keyword를 SchemaContractError로 막는다.
        self.assertIsInstance(self.schemas, SchemaSet)
        self.assertIn("enum", SUPPORTED_KEYWORDS)

    def test_no_new_x_mcs_semantic_is_introduced(self) -> None:
        for name in NEW_SCHEMA_FILES:
            self.assertNotIn(
                "x-mcs-semantic", (SCHEMA_DIR / name).read_text(encoding="utf-8"), name
            )

    def test_translation_capability_report_is_defined_exactly_once(self) -> None:
        """§3 — enum·field set을 다른 schema나 Python 상수에 복제하지 않는다."""

        definitions = [
            name
            for name, document in self.documents().items()
            if "TranslationCapabilityReport" in (document.get("$defs") or {})
        ]
        self.assertEqual(definitions, ["translated-transcript-v1.schema.json"])

        marker = "supports_code_switching_input"
        schema_hits = [
            path.name
            for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
            if marker in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(schema_hits, ["translated-transcript-v1.schema.json"])
        source_hits = [
            path.name
            for path in sorted((REPO_ROOT / "src" / "media_clarity").glob("*.py"))
            if marker in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(source_hits, [], "Python 상수가 capability field set을 복제했다")

    def test_language_tag_subset_has_a_single_type_definition(self) -> None:
        """타입 정의는 한 곳뿐이다.

        JSON Schema의 `patternProperties` **key**는 정규식 자체이므로 `$ref`로 대신할 수
        없다. 그래서 `language_overrides`의 key matcher에만 같은 정규식이 문자열로 한 번 더
        나타난다. 이 한 곳 외에 타입 정의가 복제되지 않았음을 고정한다.
        """

        pattern = "^[a-z]{2,8}(-[A-Za-z0-9]{1,8})*$"
        owners = [
            name
            for name, document in self.documents().items()
            if pattern in json.dumps(document.get("$defs") or {}, ensure_ascii=False)
        ]
        self.assertEqual(
            owners,
            ["adapter-capability-report-v1.schema.json", "subtitle-document-v1.schema.json"],
        )
        subtitle = load_strict(SCHEMA_DIR / "subtitle-document-v1.schema.json")
        occurrences = [
            location
            for location, node in (
                ("ResolvedStyle/language_overrides",
                 subtitle["$defs"]["ResolvedStyle"]["properties"]["language_overrides"]),
            )
            if pattern in node.get("patternProperties", {})
        ]
        self.assertEqual(occurrences, ["ResolvedStyle/language_overrides"])
        self.assertEqual(
            json.dumps(subtitle, ensure_ascii=False).count(pattern.replace("\\", "\\\\")),
            1,
            "subtitle schema에서 language tag 정규식이 두 번 이상 나타난다",
        )

    def test_no_style_number_is_baked_into_the_schema(self) -> None:
        """U-18 미정 — CPS·줄 길이·표시시간 기본 숫자를 schema에 박지 않는다."""

        style = load_strict(SCHEMA_DIR / "subtitle-document-v1.schema.json")["$defs"][
            "ResolvedStyle"
        ]
        blob = json.dumps(style, ensure_ascii=False)
        self.assertNotIn('"default"', blob)
        self.assertNotIn('"const"', blob)
        for field in ("max_chars_per_line", "max_lines", "max_cps"):
            self.assertNotIn("default", style["properties"][field])

    def test_baseline_schemas_are_byte_identical(self) -> None:
        """기존 계약의 raw·canonical hash가 그대로다 (§10 rollback guard)."""

        for name, (raw_expected, canonical_expected) in BASELINE_HASHES.items():
            with self.subTest(schema=name):
                raw = (SCHEMA_DIR / name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), raw_expected)
                canonical = json.dumps(
                    json.loads(raw.decode("utf-8")),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                self.assertEqual(hashlib.sha256(canonical).hexdigest(), canonical_expected)

    def test_unknown_keyword_is_a_contract_error_not_a_data_error(self) -> None:
        with self.assertRaises(SchemaContractError):
            SchemaSet(REPO_ROOT / "tests")


# ---------------------------------------------------------------------------
# fixture 실행
# ---------------------------------------------------------------------------


class FixtureTests(ContractCase):
    def test_every_expected_case_id_is_present_exactly_once(self) -> None:
        observed = [load_fixture(path)["case_id"] for path in discover_fixtures(FIXTURE_DIR)]
        self.assertEqual(sorted(observed), sorted(EXPECTED_CASE_IDS))
        self.assertEqual(len(observed), len(set(observed)))

    def test_every_fixture_matches_its_exact_code_and_location(self) -> None:
        failures = []
        for path in discover_fixtures(FIXTURE_DIR):
            outcome = evaluate_fixture(path, self.schemas)
            if not outcome.passed:
                failures.append(f"{outcome.case_id}: {'; '.join(outcome.mismatches)}")
        self.assertEqual(failures, [])

    def test_positive_fixtures_cover_the_contracted_paths(self) -> None:
        """§9의 정상 경로가 실제 fixture 안에 있는지 관측한다."""

        base = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        mini = load_fixture(FIXTURE_DIR / "k-02.json")["documents"]
        partial = load_fixture(FIXTURE_DIR / "k-03.json")["documents"]

        segments = [
            segment
            for stream in base["transcript"]["streams"]
            for segment in stream["segments"]
        ]
        kinds = {
            segment["switch_kind"]
            for segment_node in segments
            for segment in segment_node.get("language_spans", [])
            if "switch_kind" in segment
        }
        self.assertIn("intra_sentential", kinds)
        self.assertTrue(
            any(
                span["language"] == "und"
                for segment in segments
                for span in segment.get("language_spans", [])
            ),
            "explicit und span이 없다",
        )
        gapped = [
            segment
            for segment in segments
            if segment.get("language_spans")
            and sum(s["char_end"] - s["char_start"] for s in segment["language_spans"])
            < len(segment["text"])
        ]
        self.assertTrue(gapped, "language gap이 있는 segment가 없다")
        for segment in gapped:
            self.assertNotIn("dominant_language", segment)
            self.assertIn("language_unknown", segment["review_reasons"])

        alignment = {
            segment["alignment_kind"]
            for stream in base["translated_transcript"]["streams"]
            for segment in stream["segments"]
        }
        self.assertEqual(
            alignment, {"one_to_one", "merged", "split", "dropped", "unknown"}
        )

        self.assertEqual(base["subtitle_document"]["text_axis"], "target")
        self.assertEqual(base["subtitle_document"]["target_language"], TARGET_LANGUAGE)
        self.assertEqual(mini["subtitle_document"]["text_axis"], "source")
        self.assertNotIn("target_language", mini["subtitle_document"])

        capability = mini["transcript"]["capability_report"]
        self.assertEqual(capability["token_timing_units"], [])
        self.assertEqual(capability["token_confidence_semantics"], "none")
        self.assertFalse(capability["supports_language_id"])
        self.assertEqual(set(mini["transcript"]["feature_status"].values()), {"unsupported"})
        for stream in mini["transcript"]["streams"]:
            for segment in stream["segments"]:
                for absent in ("tokens", "segment_confidence", "language_spans",
                               "dominant_language", "alternatives"):
                    self.assertNotIn(absent, segment)

        self.assertEqual(partial["translated_transcript"]["coverage_status"], "partial")
        uncovered = partial["translated_transcript"]["uncovered_source_fragments"]
        self.assertTrue(uncovered)
        for fragment in uncovered:
            self.assertTrue(fragment["needs_review"])
            self.assertTrue(fragment["review_reasons"])

    def test_japanese_and_english_line_breaks_are_both_representable(self) -> None:
        mini = load_fixture(FIXTURE_DIR / "k-02.json")["documents"]
        cues = {cue["cue_id"]: cue for cue in mini["subtitle_document"]["cues"]}
        japanese = cues["cue-m1"]
        self.assertEqual(japanese["lines"], ["日", "本語"])
        self.assertEqual(japanese["line_break_whitespace"], [])
        english = cues["cue-m3"]
        self.assertEqual(english["lines"], ["Good", "morning"])
        self.assertEqual(len(english["line_break_whitespace"]), 1)
        self.assertEqual(english["line_break_whitespace"][0]["text"], " ")

    def test_emoji_and_combining_offsets_are_unicode_scalar_based(self) -> None:
        mini = load_fixture(FIXTURE_DIR / "k-02.json")["documents"]
        text = [
            segment["text"]
            for stream in mini["transcript"]["streams"]
            for segment in stream["segments"]
            if segment["segment_id"] == "tm-2"
        ][0]
        self.assertEqual(len(text), 5, "scalar 길이")
        self.assertEqual(len(text.encode("utf-16-le")) // 2, 6, "UTF-16 code unit 길이")
        cue = [c for c in mini["subtitle_document"]["cues"] if c["cue_id"] == "cue-m2"][0]
        self.assertEqual(cue["lineage_fragments"][1]["char_start"], 3)

    def test_different_stream_cue_overlap_is_accepted(self) -> None:
        base = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        cues = base["subtitle_document"]["cues"]
        pairs = [
            (a, b)
            for index, a in enumerate(cues)
            for b in cues[index + 1 :]
            if a["start_seconds"] < b["end_seconds"] and b["start_seconds"] < a["end_seconds"]
        ]
        self.assertTrue(pairs, "다른 stream 동시 cue가 없다")
        for a, b in pairs:
            self.assertNotEqual(a["stream_id"], b["stream_id"])
        self.assertEqual(validate_documents(base, self.schemas).findings, ())

    def test_findings_are_deterministic(self) -> None:
        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            first = validate_documents(documents, self.schemas).pairs
            second = validate_documents(documents, self.schemas).pairs
            self.assertEqual(first, second, path.name)

    def test_locations_are_resolvable_json_pointers(self) -> None:
        """모든 finding 위치는 선행 `/` 없이 실제 입력에서 해석돼야 한다."""

        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            for finding in validate_documents(documents, self.schemas).findings:
                with self.subTest(case=path.name, location=finding.location):
                    self.assertFalse(finding.location.startswith("/"))
                    node: Any = documents
                    for token in finding.location.split("/"):
                        if isinstance(node, list):
                            node = node[int(token)]
                        else:
                            self.assertIn(token, node, finding.location)
                            node = node[token]

    def test_every_declared_error_code_is_exercised(self) -> None:
        observed = set()
        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            observed.update(code for code, _ in validate_documents(documents, self.schemas).pairs)
        self.assertEqual(set(ERROR_CODES) - observed, set(), "쓰이지 않은 오류 코드")
        self.assertEqual(observed - set(ERROR_CODES), set(), "선언되지 않은 오류 코드")

    def test_messages_never_leak_text_or_absolute_paths(self) -> None:
        """오류 message에 source/target 원문·절대 경로·민감 값을 담지 않는다.

        4 scalar 이상의 실제 segment·cue text만 검사한다. 그보다 짧은 조각은 계약 산문과
        우연히 겹칠 수 있어 누출 신호가 되지 못한다 (예: 두 글자 단어).
        """

        secrets: set[str] = set()
        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            for stream in (documents.get("transcript") or {}).get("streams", []):
                for segment in stream["segments"]:
                    if len(segment["text"]) >= 4:
                        secrets.add(segment["text"])
            for stream in (documents.get("translated_transcript") or {}).get("streams", []):
                for segment in stream["segments"]:
                    if len(segment["target_text"]) >= 4:
                        secrets.add(segment["target_text"])
            for cue in (documents.get("subtitle_document") or {}).get("cues", []):
                secrets.update(line for line in cue["lines"] if len(line) >= 4)

        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            for finding in validate_documents(documents, self.schemas).findings:
                message = finding.message
                self.assertNotIn("/home/", message)
                self.assertNotIn(str(REPO_ROOT), message)
                for secret in secrets:
                    self.assertNotIn(secret, message, f"{path.name}: 원문 노출")


# ---------------------------------------------------------------------------
# input mutation manifest (scripts/verify_task_029.py와 같은 정본)
# ---------------------------------------------------------------------------


class InputMutationTests(ContractCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.verify = _load_verify_script()

    def test_every_required_mutation_is_detected_with_the_declared_pair(self) -> None:
        rows = self.verify.run_input_mutations(self.schemas, FIXTURE_DIR)
        self.assertGreaterEqual(len(rows), 100)
        failures = [
            f"{row['mutation_id']} {row['title']}: 기대 {row['expected']} 관측 {row['observed']}"
            for row in rows
            if not row["passed"]
        ]
        self.assertEqual(failures, [])

    def test_mutation_ids_are_unique_and_bases_are_valid(self) -> None:
        self.verify.register_mutations()
        ids = [mutation.mutation_id for mutation in self.verify.MUTATIONS]
        self.assertEqual(len(ids), len(set(ids)))
        for mutation in self.verify.MUTATIONS:
            self.assertIn(mutation.base, self.verify.BASE_CASES)
            self.assertTrue(mutation.expected, mutation.mutation_id)

    def test_source_mutant_manifests_are_well_formed(self) -> None:
        """schema·validator mutant의 anchor가 실제 production 파일에 정확히 한 번 있다."""

        for mutant in list(self.verify.schema_mutants()) + list(self.verify.validator_mutants()):
            with self.subTest(mutant=mutant.mutant_id):
                blob = (REPO_ROOT / mutant.target).read_text(encoding="utf-8")
                self.assertEqual(blob.count(mutant.old), 1, mutant.title)
                self.assertNotEqual(mutant.old, mutant.new)

    def test_untouched_base_fixtures_stay_valid(self) -> None:
        """valid-case sentinel — 변형하지 않은 base는 항상 통과해야 한다."""

        for case_id in self.verify.BASE_CASES.values():
            index = int(case_id.split("-")[1])
            documents = load_fixture(FIXTURE_DIR / f"k-{index:02d}.json")["documents"]
            self.assertEqual(validate_documents(documents, self.schemas).findings, ())


# ---------------------------------------------------------------------------
# validator 자체의 경계
# ---------------------------------------------------------------------------


class ValidatorBoundaryTests(ContractCase):
    def test_unknown_document_key_is_rejected(self) -> None:
        result = validate_documents({"forced_alignment": {}}, self.schemas)
        self.assertEqual(result.pairs, (("E_SCHEMA", "forced_alignment"),))

    def test_document_containers_must_have_the_contracted_shape(self) -> None:
        self.assertEqual(
            validate_documents({"speech_segments": {}}, self.schemas).pairs,
            (("E_SCHEMA", "speech_segments"),),
        )
        self.assertEqual(
            validate_documents({"transcript": []}, self.schemas).pairs,
            (("E_SCHEMA", "transcript"),),
        )

    def test_empty_document_set_is_valid(self) -> None:
        self.assertEqual(validate_documents({}, self.schemas).findings, ())

    def test_speech_segment_set_is_checkable_on_its_own(self) -> None:
        """§8 공개 검증 경계 — SpeechSegment 집합만으로도 검사할 수 있다."""

        documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        self.assertEqual(check_speech_segments(documents["speech_segments"]), [])

    def test_allowed_line_break_scalars_match_the_contract(self) -> None:
        expected = {
            *(chr(code) for code in range(0x0009, 0x000E)),
            " ", "", " ", " ",
            *(chr(code) for code in range(0x2000, 0x200B)),
            " ", " ", " ", " ", "　",
        }
        self.assertEqual(set(ALLOWED_LINE_BREAK_SCALARS), expected)

    def test_document_keys_map_to_real_schema_files(self) -> None:
        for key, schema_file in DOCUMENT_KEYS.items():
            self.assertIn(schema_file, SCHEMA_FILES, key)
            self.assertTrue((SCHEMA_DIR / schema_file).is_file())

    def test_no_external_dependency_is_imported(self) -> None:
        source = (REPO_ROOT / "src" / "media_clarity" / "subtitle_contracts.py").read_text(
            encoding="utf-8"
        )
        imported = set(re.findall(r"^(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)", source, re.M))
        allowed = {
            "__future__", "argparse", "json", "math", "shutil", "subprocess", "sys",
            "tempfile", "dataclasses", "pathlib", "typing", "media_clarity",
            "media_clarity.schema_core",
        }
        self.assertEqual(imported - allowed, set())

    def test_schema_core_is_reused_not_reimplemented(self) -> None:
        source = (REPO_ROOT / "src" / "media_clarity" / "subtitle_contracts.py").read_text(
            encoding="utf-8"
        )
        for name in ("SchemaValidator", "Finding", "load_strict", "sort_findings"):
            self.assertIn(f"    {name},", source, f"{name}를 schema_core에서 재사용하지 않는다")
        self.assertNotIn("class SchemaValidator", source)
        self.assertNotIn("def sort_findings", source)


# ---------------------------------------------------------------------------
# REVIEW-023 B-02 — finding message에 민감 값이 실리지 않는다
# ---------------------------------------------------------------------------


class RedactionTests(ContractCase):
    """`(code, location)`만 계약이고 message는 설명이다. message에 입력 값을 실으면
    로그·리포트가 원문 유출 경로가 된다. `schema_core`를 고치지 않고 TASK-029 경계에서
    결정적으로 비식별화한다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.verify = _load_verify_script()

    def test_schema_enum_violation_does_not_echo_the_offending_value(self) -> None:
        documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        secret = "SECRET-PATIENT-NAME"
        documents["subtitle_document"]["cues"][1]["review_reasons"] = [secret]
        result = validate_documents(documents, self.schemas)
        self.assertIn(
            ("E_SCHEMA", "subtitle_document/cues/1/review_reasons/0"), result.pairs
        )
        for finding in result.findings:
            self.assertNotIn(secret, finding.message)

    def test_no_finding_message_carries_source_or_target_text(self) -> None:
        rows = self.verify.run_leak_scan(self.schemas, FIXTURE_DIR)
        failures = [f"{row['leak_id']}: {'; '.join(row['hits'])}" for row in rows if not row["passed"]]
        self.assertEqual(failures, [])
        self.assertGreaterEqual(len(rows), len(EXPECTED_CASE_IDS))

    def test_no_finding_message_carries_an_absolute_path(self) -> None:
        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            for finding in validate_documents(documents, self.schemas).findings:
                self.assertNotIn(str(REPO_ROOT), finding.message)
                self.assertNotIn("/home/", finding.message)

    def test_redaction_is_a_total_deterministic_map(self) -> None:
        from media_clarity.subtitle_contracts import redact_schema_message

        for prefix, replacement in self.verify.contracts._SCHEMA_MESSAGE_RULES:
            with self.subTest(prefix=prefix):
                self.assertEqual(redact_schema_message(f"{prefix} — SECRET"), replacement)
        self.assertEqual(redact_schema_message("알 수 없는 설명 SECRET"), "schema 계약 위반")

    def test_error_code_and_location_survive_redaction(self) -> None:
        """비식별화는 message만 바꾼다. 계약 축은 그대로다."""

        documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        documents["transcript"]["streams"][0]["segments"][0]["review_reasons"] = ["nope"]
        subset = {key: documents[key] for key in ("speech_segments", "transcript")}
        pairs = validate_documents(subset, self.schemas).pairs
        self.assertEqual(
            pairs, (("E_SCHEMA", "transcript/streams/0/segments/0/review_reasons/0"),)
        )


# ---------------------------------------------------------------------------
# REVIEW-023 B-03 — 방어면 completeness guard
# ---------------------------------------------------------------------------


class DefenseCoverageTests(ContractCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.verify = _load_verify_script()

    def test_every_declared_defense_site_fires_at_least_once(self) -> None:
        """mutant 목록은 사람이 고른 표본이다. 방어면 전수는 따로 증명한다."""

        rows = self.verify.run_defense_coverage(self.schemas, FIXTURE_DIR)
        self.assertGreaterEqual(len(rows), 100)
        uncovered = [f"{row['site_id']} {row['snippet']}" for row in rows if not row["passed"]]
        self.assertEqual(uncovered, [])

    def test_depth_defenses_fire_and_are_shadowed_by_schema(self) -> None:
        rows = self.verify.run_depth_probes(self.schemas, FIXTURE_DIR)
        self.assertTrue(rows)
        failures = [row["probe_id"] for row in rows if not row["passed"]]
        self.assertEqual(failures, [])


# ---------------------------------------------------------------------------
# REVIEW-023 B-01 — 시간·stream·lineage 결박
# ---------------------------------------------------------------------------


class LineageBindingTests(ContractCase):
    """REVIEW-023이 든 반례를 manifest와 별개로 직접 고정한다."""

    def _base(self) -> dict[str, Any]:
        return load_fixture(FIXTURE_DIR / "k-01.json")["documents"]

    def test_asr_segment_may_not_span_a_gap_between_speech_segments(self) -> None:
        documents = self._base()
        segment = documents["transcript"]["streams"][0]["segments"][0]
        segment["source_speech_segment_ids"] = ["sp-1", "sp-3"]
        segment["end_seconds"] = 3.5
        pairs = validate_documents(
            {k: documents[k] for k in ("speech_segments", "transcript")}, self.schemas
        ).pairs
        self.assertIn(
            ("E_TIME_RANGE", "transcript/streams/0/segments/0/end_seconds"), pairs
        )

    def test_downstream_timebase_must_match_its_source(self) -> None:
        documents = self._base()
        documents["transcript"]["timebase_ref"] = "tb-detached"
        pairs = validate_documents(
            {k: documents[k] for k in ("speech_segments", "transcript")}, self.schemas
        ).pairs
        self.assertIn(("E_SOURCE_REF", "transcript/timebase_ref"), pairs)

    def test_duplicate_cue_ids_are_reported_before_indexing(self) -> None:
        documents = self._base()
        cues = documents["subtitle_document"]["cues"]
        cues[1]["cue_id"] = cues[0]["cue_id"]
        pairs = validate_documents(documents, self.schemas).pairs
        self.assertIn(("E_SCHEMA", "subtitle_document/cues/1/cue_id"), pairs)

    def test_cue_lineage_follows_rendered_line_order_not_array_order(self) -> None:
        """줄을 뒤집고 line_index만 맞바꾸면 배열 순서 검사는 통과한다 — 렌더 순서로 본다."""

        documents = self._base()
        target = next(
            cue
            for cue in documents["subtitle_document"]["cues"]
            if len(cue["lines"]) > 1
        )
        target["lines"] = list(reversed(target["lines"]))
        indexes = [fragment["line_index"] for fragment in target["lineage_fragments"]]
        highest = max(indexes)
        for fragment in target["lineage_fragments"]:
            fragment["line_index"] = highest - fragment["line_index"]
        codes = {code for code, _ in validate_documents(documents, self.schemas).pairs}
        self.assertTrue(codes, "줄 순서를 뒤집었는데 아무 결함도 보고되지 않았다")


if __name__ == "__main__":
    unittest.main()
