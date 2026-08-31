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
from decimal import Decimal
from pathlib import Path
from typing import Any

from media_clarity.schema_core import SCHEMA_DIALECT, SUPPORTED_KEYWORDS, SchemaContractError
from media_clarity.subtitle_contracts import (
    ALLOWED_LINE_BREAK_SCALARS,
    DOCUMENT_KEYS,
    ERROR_CODES,
    EXPECTED_CASE_IDS,
    LID_GRID_INTERVAL_SECONDS,
    LID_GRID_ORIGIN_SECONDS,
    LID_METRIC_IDS,
    LID_NONFINITE_MESSAGE,
    LID_UNSUPPORTED_REASON,
    SCHEMA_FILES,
    TARGET_LANGUAGE,
    ZERO_DENOMINATOR_REASON,
    SchemaSet,
    check_speech_segments,
    discover_fixtures,
    evaluate_fixture,
    lid_frame_bounds,
    lid_frame_languages,
    lid_frame_midpoint,
    lid_frame_range,
    lid_has_simultaneous_conflict,
    lid_scoring_result,
    load_fixture,
    load_strict,
    normalize_language_spans,
    validate_documents,
    zero_denominator_result,
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

        # validator가 개별 field를 **읽는** 것은 복제가 아니다. 금지하는 것은 Python 쪽에
        # field set 자체를 다시 선언하는 것이다. 그래서 상수 선언을 직접 본다.
        import ast

        fields = set(
            load_strict(SCHEMA_DIR / "translated-transcript-v1.schema.json")["$defs"][
                "TranslationCapabilityReport"
            ]["properties"]
        )
        duplicated: list[str] = []
        for path in sorted((REPO_ROOT / "src" / "media_clarity").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                    continue
                names = {
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                }
                if len(names & fields) >= 3:
                    duplicated.append(f"{path.name}:{node.lineno}")
        self.assertEqual(duplicated, [], "Python 상수가 capability field set을 복제했다")

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
        """모든 finding 위치는 선행 `/` 없이 실제 입력에서 해석돼야 한다.

        빈 문자열은 RFC 6901의 **root pointer**이며 문서 집합 전체를 가리킨다. 사용자 제어
        최상위 key가 안전하지 않을 때만 나온다 (REVIEW-024 H-06).
        """

        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            for finding in validate_documents(documents, self.schemas).findings:
                with self.subTest(case=path.name, location=finding.location):
                    self.assertFalse(finding.location.startswith("/"))
                    if finding.location == "":
                        continue
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
        """key 자체가 사용자 제어 값이므로 root로 접는다 (REVIEW-025 R-05)."""

        result = validate_documents({"forced_alignment": {}}, self.schemas)
        self.assertEqual(result.pairs, (("E_SCHEMA", ""),))

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
            "__future__", "argparse", "functools", "inspect", "json", "math", "shutil",
            "subprocess", "sys", "tempfile", "dataclasses", "decimal", "pathlib", "typing",
            "media_clarity", "media_clarity.schema_core",
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


# ---------------------------------------------------------------------------
# REVIEW-024 H-06 — dynamic key가 error location으로 새지 않는다
# ---------------------------------------------------------------------------


class LocationSafetyTests(ContractCase):
    def _with_override(self, key: str) -> Any:
        documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        documents["subtitle_document"]["resolved_style"]["language_overrides"][key] = {}
        return validate_documents(documents, self.schemas)

    def test_dynamic_keys_never_reach_the_location(self) -> None:
        for key in (
            "/home/patient/secret.mp4",
            "C:\\Users\\patient\\secret.mp4",
            "a/b",
            "~0",
            "~1",
            "日",
            "환",
        ):
            with self.subTest(key=key):
                result = self._with_override(key)
                self.assertEqual(
                    result.pairs,
                    (("E_SCHEMA", "subtitle_document/resolved_style/language_overrides"),),
                )
                for finding in result.findings:
                    self.assertNotIn(key, finding.location)
                    self.assertNotIn(key, finding.message)

    def test_only_declared_vocabulary_stays_in_the_location(self) -> None:
        """모양이 안전해 보여도 사용자 제어 key는 접는다 (REVIEW-025 R-05).

        남는 것은 정본이 **그 자리에서** 선언한 고정 field 이름뿐이다 (REVIEW-026 R-01).
        """

        for key in ("x", "X9", "patient_name", "John_Doe"):
            with self.subTest(folded=key):
                self.assertEqual(
                    self._with_override(key).pairs,
                    (("E_SCHEMA", "subtitle_document/resolved_style/language_overrides"),),
                )

        # 정본이 선언한 것은 `language_overrides`까지다. 그 아래 key는 입력이 정하므로
        # 정상 `ko` override의 결함도 부모로 접힌다 (REVIEW-026 R-01 2번).
        documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        documents["subtitle_document"]["resolved_style"]["language_overrides"]["ko"] = {
            "max_duration_seconds": 1.0,
            "min_duration_seconds": 2.0,
        }
        self.assertIn(
            ("E_TIME_RANGE", "subtitle_document/resolved_style/language_overrides"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_field_names_legal_elsewhere_do_not_survive_here(self) -> None:
        """다른 위치의 정본 field 이름이라는 사실은 이 위치의 노출 근거가 아니다.

        REVIEW-026 R-01의 표를 그대로 고정한다.
        """

        for key in ("uri", "text", "artifact_id"):
            with self.subTest(top_level=key):
                documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
                documents[key] = "MCS-SENSITIVE-PROBE-VALUE"
                result = validate_documents(documents, self.schemas)
                self.assertEqual(result.pairs, (("E_SCHEMA", ""),))
                for finding in result.findings:
                    self.assertNotIn(key, finding.location)

        for key in ("uri", "speaker_label", "artifact_id"):
            with self.subTest(document_refs=key):
                documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
                documents["document_refs"][key] = "MCS-SENSITIVE-PROBE-VALUE"
                result = validate_documents(documents, self.schemas)
                self.assertEqual(result.pairs, (("E_SCHEMA", "document_refs"),))

    def test_language_tag_shape_is_not_a_deidentification_basis(self) -> None:
        """BCP-47·private-use 모양에도 임의 문자열을 넣을 수 있다 (REVIEW-026 R-01)."""

        for key in ("patient", "password", "en-John-Doe", "en-x-secret", "ko"):
            with self.subTest(override=key):
                documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
                documents["subtitle_document"]["resolved_style"]["language_overrides"][key] = {
                    "max_cps": -1
                }
                result = validate_documents(documents, self.schemas)
                self.assertEqual(
                    result.pairs,
                    (("E_SCHEMA", "subtitle_document/resolved_style/language_overrides"),),
                )
                for finding in result.findings:
                    self.assertNotIn(key, finding.location)

    def test_public_check_entry_points_apply_the_same_contract(self) -> None:
        """`validate_documents()`만 접으면 공개 함수 소비자에게 raw key가 그대로 간다."""

        from media_clarity.subtitle_contracts import (
            check_artifact_consistency,
            check_document_ref_identity,
            check_subtitle_document,
        )

        documents = load_fixture(FIXTURE_DIR / "k-01.json")["documents"]
        subtitle = documents["subtitle_document"]
        subtitle["resolved_style"]["language_overrides"]["en-x-secret"] = {"max_cps": -1}
        refs = dict(documents["document_refs"])
        refs["speaker_label"] = "MCS-SENSITIVE-PROBE-VALUE"
        leaky = dict(documents)
        leaky["document_refs"] = refs

        calls = (
            lambda: check_subtitle_document(
                subtitle, documents["transcript"], documents["translated_transcript"]
            ),
            lambda: check_document_ref_identity(leaky, refs),
            lambda: check_artifact_consistency(leaky),
        )
        for index, call in enumerate(calls):
            with self.subTest(entry_point=index):
                for finding in call():
                    self.assertNotIn("en-x-secret", finding.location)
                    self.assertNotIn("speaker_label", finding.location.split("/"))

    def test_unknown_top_level_key_never_starts_with_a_slash(self) -> None:
        result = validate_documents({"/home/patient/secret.mp4": {}}, self.schemas)
        self.assertEqual(result.pairs, (("E_SCHEMA", ""),))
        for finding in result.findings:
            self.assertFalse(finding.location.startswith("/"))
            self.assertNotIn("/home/", finding.as_line())

    def test_every_finding_location_resolves_in_the_input(self) -> None:
        from media_clarity.subtitle_contracts import _MISSING, _step

        for path in discover_fixtures(FIXTURE_DIR):
            documents = load_fixture(path)["documents"]
            for finding in validate_documents(documents, self.schemas).findings:
                node: Any = documents
                if finding.location == "":
                    continue
                for segment in finding.location.split("/"):
                    node = _step(node, segment)
                    self.assertIsNot(
                        node, _MISSING, f"{path.name}: {finding.location}"
                    )


# ---------------------------------------------------------------------------
# REVIEW-024 H-01·H-02·H-03 — 계보·label 값·capability 내부 논리
# ---------------------------------------------------------------------------


class BindingTests(ContractCase):
    def _base(self) -> Any:
        return load_fixture(FIXTURE_DIR / "k-01.json")["documents"]

    def test_subtitle_source_ref_must_match_the_translation_source(self) -> None:
        documents = self._base()
        documents["subtitle_document"]["source_transcript_ref"]["artifact_id"] = "art-other"
        self.assertIn(
            ("E_SOURCE_REF", "subtitle_document/source_transcript_ref"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_upstream_refs_must_point_at_document_artifacts(self) -> None:
        documents = self._base()
        documents["translated_transcript"]["source_transcript"]["kind"] = "video"
        documents["translated_transcript"]["source_transcript"]["media_type"] = "video/mp4"
        pairs = validate_documents(documents, self.schemas).pairs
        self.assertIn(("E_SOURCE_REF", "translated_transcript/source_transcript/kind"), pairs)
        self.assertIn(
            ("E_SOURCE_REF", "translated_transcript/source_transcript/media_type"), pairs
        )

    def test_direct_input_ref_identity_requires_validation_context(self) -> None:
        """컨텍스트가 없으면 **조용히 통과시키지 않는다** (REVIEW-025 R-01).

        identity를 추측하지도 않고, 확인하지 못한 것을 유효로 보고하지도 않는다.
        """

        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY

        documents = self._base()
        documents["subtitle_document"]["input_document_ref"]["artifact_id"] = "art-other"
        without = dict(documents)
        without.pop(REF_CONTEXT_KEY)
        self.assertIn(
            ("E_SOURCE_REF", "subtitle_document/input_document_ref"),
            validate_documents(without, self.schemas).pairs,
        )
        self.assertIn(
            ("E_SOURCE_REF", "subtitle_document/input_document_ref"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_input_speaker_label_must_equal_the_actual_input_label(self) -> None:
        documents = self._base()
        segment = documents["transcript"]["streams"][0]["segments"][0]
        segment["speaker_label_source"] = "input"
        segment["speaker_label"] = "SPK-B"
        self.assertIn(
            ("E_CAPABILITY_MISMATCH", "transcript/streams/0/segments/0/speaker_label"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_ambiguous_input_labels_are_not_silently_resolved(self) -> None:
        documents = self._base()
        stream = documents["transcript"]["streams"][0]
        stream["speaker_label"] = "CH-L"
        stream["speaker_label_source"] = "input"
        for segment in documents["speech_segments"]:
            if segment["segment_id"] == "sp-3":
                segment["speaker_label"] = "CH-Z"
        self.assertIn(
            ("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_capability_internal_implications(self) -> None:
        mini = load_fixture(FIXTURE_DIR / "k-02.json")["documents"]
        cases = (
            ({"supports_intra_sentential_lid": True}, "supports_intra_sentential_lid"),
            ({"language_confidence_semantics": "model_score"}, "language_confidence_semantics"),
            ({"nbest_score_semantics": "model_score"}, "nbest_score_semantics"),
        )
        for patch, field in cases:
            with self.subTest(field=field):
                documents = json.loads(json.dumps(mini))
                documents["transcript"]["capability_report"].update(patch)
                self.assertIn(
                    ("E_CAPABILITY_MISMATCH", f"transcript/capability_report/{field}"),
                    validate_documents(documents, self.schemas).pairs,
                )

    def test_empty_supported_languages_needs_an_explicit_limitation(self) -> None:
        documents = load_fixture(FIXTURE_DIR / "k-02.json")["documents"]
        documents["transcript"]["capability_report"]["supported_languages"] = []
        documents["transcript"]["capability_report"]["limitations"] = []
        self.assertIn(
            ("E_CAPABILITY_MISMATCH", "transcript/capability_report/supported_languages"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_emitted_languages_must_be_declared(self) -> None:
        documents = self._base()
        documents["transcript"]["capability_report"]["supported_languages"] = ["en"]
        self.assertIn(
            ("E_CAPABILITY_MISMATCH", "transcript/capability_report/supported_languages"),
            validate_documents(documents, self.schemas).pairs,
        )


# ---------------------------------------------------------------------------
# REVIEW-024 H-04·H-05 — 감사 분모의 완전성과 exit 조건
# ---------------------------------------------------------------------------


class AuditGateTests(ContractCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.verify = _load_verify_script()

    def test_every_schema_defense_is_covered_by_a_real_mutation(self) -> None:
        rows = self.verify.run_schema_defense_inventory(FIXTURE_DIR, SCHEMA_DIR)
        self.assertGreaterEqual(len(rows), 250)
        failures = [f"{row['defense_id']}: {row['note']}" for row in rows if not row["passed"]]
        self.assertEqual(failures, [])
        self.assertTrue(any(row["root_required"] for row in rows))

    def test_no_two_mutants_declare_the_same_transformation(self) -> None:
        self.assertEqual(self.verify.duplicate_transformations(), [])
        counts = self.verify.unique_transformation_count(SCHEMA_DIR)
        self.assertEqual(counts["schema_declared"], counts["schema_unique"])
        self.assertEqual(counts["validator_declared"], counts["validator_unique"])
        self.assertEqual(counts["defense_declared"], counts["defense_unique"])
        self.assertEqual(counts["duplicate_groups"], 0)

    def test_every_root_required_field_has_a_killing_mutation(self) -> None:
        """새 root required 필드가 생기면 분모가 늘고, 죽이지 못하면 감사가 실패한다."""

        defenses = self.verify.collect_schema_defenses(SCHEMA_DIR)
        root_required = [defense for defense in defenses if defense.is_root_required]
        self.assertGreaterEqual(len(root_required), 40)
        for name in self.verify.INVENTORY_FILES:
            document = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
            declared = {
                defense.kind.split(":", 1)[1]
                for defense in root_required
                if defense.schema_file == name
            }
            self.assertEqual(declared, set(document["required"]), name)

    def test_sentinel_failures_are_part_of_the_success_predicate(self) -> None:
        """JSON 출력의 sentinel 수치와 process 성공 조건이 같은 predicate를 쓴다."""

        payload = {
            "fixtures": [{"case_id": "K-01", "passed": True, "sentinel_ok": True}],
            "mutations": [{"mutation_id": "IM-01", "passed": True, "sentinel_ok": True}],
            "leaks": [{"leak_id": "K-01", "passed": True, "sentinel_ok": True}],
            "depth_probes": [{"probe_id": "DP-01", "passed": True}],
        }
        self.assertTrue(self.verify._all_passed(payload))
        self.assertEqual(self.verify.bad_sentinels(payload), [])

        payload["mutations"][0]["sentinel_ok"] = False
        self.assertEqual(self.verify.bad_sentinels(payload), ["mutations:IM-01"])
        self.assertFalse(self.verify._all_passed(payload))

        payload["mutations"][0]["sentinel_ok"] = True
        payload["depth_probes"][0]["passed"] = False
        self.assertFalse(self.verify._all_passed(payload))

    def test_depth_probes_run_inside_the_check_only_payload(self) -> None:
        """depth 방어를 지운 mutant가 죽으려면 depth probe가 사본에서도 돌아야 한다."""

        payload = self.verify._check_only(FIXTURE_DIR, SCHEMA_DIR)
        self.assertIn("depth_probes", payload)
        self.assertTrue(payload["depth_probes"])
        self.assertTrue(all(row["passed"] for row in payload["depth_probes"]))
        self.assertIn("leaks", payload)
        self.assertTrue(all(row["passed"] for row in payload["leaks"]))


# ---------------------------------------------------------------------------
# REVIEW-025 R-01 — 검증 컨텍스트 fail-open과 ArtifactRef 일관성
# ---------------------------------------------------------------------------


class RefContextTests(ContractCase):
    def _base(self) -> Any:
        return load_fixture(FIXTURE_DIR / "k-01.json")["documents"]

    def test_missing_context_is_invalid_not_silently_valid(self) -> None:
        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY

        documents = self._base()
        documents.pop(REF_CONTEXT_KEY)
        documents["subtitle_document"]["input_document_ref"]["artifact_id"] = "art-other"
        pairs = validate_documents(documents, self.schemas).pairs
        self.assertIn(("E_SOURCE_REF", "subtitle_document/input_document_ref"), pairs)
        self.assertIn(("E_SOURCE_REF", "translated_transcript/source_transcript"), pairs)

    def test_partial_context_is_invalid(self) -> None:
        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY

        documents = self._base()
        documents[REF_CONTEXT_KEY].pop("translated_transcript")
        self.assertIn(
            ("E_SOURCE_REF", "subtitle_document/input_document_ref"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_required_roles_follow_the_document_combination(self) -> None:
        from media_clarity.subtitle_contracts import required_ref_roles

        documents = self._base()
        self.assertEqual(
            required_ref_roles(documents), {"transcript", "translated_transcript"}
        )
        self.assertEqual(required_ref_roles({"speech_segments": []}), set())

    def test_context_values_reuse_the_common_artifact_ref_contract(self) -> None:
        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY

        documents = self._base()
        documents[REF_CONTEXT_KEY]["transcript"]["x_extra"] = 1
        self.assertIn(
            ("E_SCHEMA", "document_refs/transcript"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_context_roles_are_closed(self) -> None:
        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY, REF_CONTEXT_ROLES

        self.assertEqual(REF_CONTEXT_ROLES, ("transcript", "translated_transcript"))
        documents = self._base()
        documents[REF_CONTEXT_KEY]["subtitle_document"] = json.loads(
            json.dumps(documents[REF_CONTEXT_KEY]["transcript"])
        )
        # role 이름이 아닌 key는 `document_refs`로 접힌다 — 다른 위치의 정본 문서 key여도
        # 이 자리에서는 입력이 정한 이름이다 (REVIEW-026 R-01).
        self.assertIn(
            ("E_SCHEMA", "document_refs"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_documents_may_not_collapse_to_one_identity(self) -> None:
        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY

        documents = self._base()
        documents[REF_CONTEXT_KEY]["translated_transcript"] = json.loads(
            json.dumps(documents[REF_CONTEXT_KEY]["transcript"])
        )
        self.assertIn(
            ("E_SOURCE_REF", "document_refs/translated_transcript"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_same_artifact_id_must_agree_on_immutable_metadata(self) -> None:
        from media_clarity.subtitle_contracts import (
            ARTIFACT_IMMUTABLE_FIELDS,
            ARTIFACT_UNCOMPARED_FIELDS,
            REF_CONTEXT_KEY,
        )

        self.assertIn("byte_size", ARTIFACT_IMMUTABLE_FIELDS)
        self.assertIn("content_hash", ARTIFACT_IMMUTABLE_FIELDS)
        self.assertIn("uri", ARTIFACT_UNCOMPARED_FIELDS)
        self.assertIn("produced_by", ARTIFACT_UNCOMPARED_FIELDS)
        self.assertEqual(
            set(ARTIFACT_IMMUTABLE_FIELDS) & set(ARTIFACT_UNCOMPARED_FIELDS), set()
        )

        documents = self._base()
        documents[REF_CONTEXT_KEY]["transcript"]["byte_size"] = 4096
        self.assertIn(
            ("E_SOURCE_REF", "document_refs/transcript/byte_size"),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_uncompared_fields_do_not_create_findings(self) -> None:
        """`uri`·`produced_by` 동일성 의미는 계약이 없다 — 임의로 거부하지 않는다."""

        from media_clarity.subtitle_contracts import REF_CONTEXT_KEY

        documents = self._base()
        documents[REF_CONTEXT_KEY]["transcript"]["uri"] = "/absolute/elsewhere/transcript.json"
        self.assertEqual(validate_documents(documents, self.schemas).findings, ())


# ---------------------------------------------------------------------------
# REVIEW-025 R-02·R-03 — lineage 시간 겹침과 code-switch capability
# ---------------------------------------------------------------------------


class LineageEvidenceTests(ContractCase):
    def _base(self) -> Any:
        return load_fixture(FIXTURE_DIR / "k-01.json")["documents"]

    def test_non_overlapping_source_cannot_lend_a_speaker_label(self) -> None:
        documents = self._base()
        for segment in documents["speech_segments"]:
            if segment["segment_id"] == "sp-4":
                segment.pop("speaker_label", None)
        target = documents["transcript"]["streams"][0]["segments"][2]
        target["speaker_label"] = "CH-L"
        target["speaker_label_source"] = "input"
        target["source_speech_segment_ids"] = ["sp-4", "sp-1"]
        pairs = validate_documents(documents, self.schemas).pairs
        self.assertIn(
            ("E_TIME_RANGE", "transcript/streams/0/segments/2/source_speech_segment_ids/1"),
            pairs,
        )
        self.assertIn(
            ("E_CAPABILITY_MISMATCH", "transcript/streams/0/segments/2/speaker_label_source"),
            pairs,
        )

    def test_unlabeled_covering_source_blocks_a_single_input_label(self) -> None:
        documents = self._base()
        for segment in documents["speech_segments"]:
            if segment["segment_id"] in ("sp-3", "sp-4"):
                segment.pop("speaker_label", None)
        stream = documents["transcript"]["streams"][0]
        stream["speaker_label"] = "CH-L"
        stream["speaker_label_source"] = "input"
        self.assertIn(
            ("E_CAPABILITY_MISMATCH", "transcript/streams/0/speaker_label"),
            validate_documents(documents, self.schemas).pairs,
        )

    def _split_units(self, documents: Any, cuts: Any) -> None:
        source = "今日はsunnyですね"
        stream = documents["translated_transcript"]["streams"][0]
        template = next(
            item for item in stream["segments"] if item["segment_id"] == "tl-1"
        )
        rest = [item for item in stream["segments"] if item["segment_id"] != "tl-1"]
        units = []
        for index, (start, end) in enumerate(cuts):
            unit = json.loads(json.dumps(template))
            unit["segment_id"] = f"tl-1{chr(97 + index)}"
            unit["alignment_kind"] = "split"
            unit["target_text"] = f"조각{index}"
            unit["source_fragments"] = [
                {
                    "source_segment_id": "tr-1",
                    "char_start": start,
                    "char_end": end,
                    "source_text": source[start:end],
                }
            ]
            units.append(unit)
        stream["segments"] = units + rest

    def test_mixed_language_unit_requires_code_switching_capability(self) -> None:
        documents = self._base()
        documents["translated_transcript"]["capability_report"][
            "supports_code_switching_input"
        ] = False
        self.assertIn(
            (
                "E_CAPABILITY_MISMATCH",
                "translated_transcript/capability_report/supports_code_switching_input",
            ),
            validate_documents(documents, self.schemas).pairs,
        )

    def test_single_language_units_do_not_require_code_switching(self) -> None:
        """정상 경로 — 언어 경계에 맞춰 나눈 입력은 미지원 adapter로도 유효하다."""

        documents = self._base()
        documents["translated_transcript"]["capability_report"][
            "supports_code_switching_input"
        ] = False
        self._split_units(documents, [(0, 3), (3, 8), (8, 11)])
        # 자막 cue lineage는 원래 `tl-1`을 가리키므로 이 검사에서는 번역 계층까지만 본다.
        documents.pop("subtitle_document")
        self.assertEqual(validate_documents(documents, self.schemas).findings, ())

    def test_unit_crossing_a_language_boundary_requires_the_capability(self) -> None:
        documents = self._base()
        documents["translated_transcript"]["capability_report"][
            "supports_code_switching_input"
        ] = False
        self._split_units(documents, [(0, 5), (5, 11)])
        self.assertIn(
            (
                "E_CAPABILITY_MISMATCH",
                "translated_transcript/capability_report/supports_code_switching_input",
            ),
            validate_documents(documents, self.schemas).pairs,
        )


# ---------------------------------------------------------------------------
# REVIEW-025 R-04 — 임의 정밀도 JSON 숫자
# ---------------------------------------------------------------------------


class RawJsonInputContractTests(ContractCase):
    """raw JSON 입력 경계 (REVIEW-026 R-02). in-memory 객체로는 재현되지 않는 축이다."""

    def _fixture(self, documents_literal: str) -> str:
        return (
            '{"case_id":"K-01","title":"t","expected":{"valid":true,"findings":[]},'
            f'"documents":{documents_literal}}}'
        )

    def test_over_limit_integers_are_a_stable_input_error(self) -> None:
        from media_clarity.subtitle_contracts import (
            NUMBER_MAX_INTEGER_DIGITS,
            NumberProfileError,
            loads_documents,
        )

        self.assertEqual(NUMBER_MAX_INTEGER_DIGITS, 4300)
        # 경계 안쪽은 그대로 통과한다 — "큰 수는 무조건 거부"가 아니다.
        loads_documents(self._fixture('{"speech_segments":[%s]}' % ("1" * 4300)))
        for digits in (4301, 10000):
            for sign in ("", "-"):
                with self.subTest(digits=digits, sign=sign or "+"):
                    text = self._fixture(
                        '{"speech_segments":[%s%s]}' % (sign, "1" * digits)
                    )
                    with self.assertRaises(NumberProfileError):
                        loads_documents(text)

    def test_lossy_decimals_are_rejected_not_silently_rounded(self) -> None:
        from media_clarity.subtitle_contracts import NumberProfileError, loads_documents

        for literal in ("1.0000000000000001", "-1e-400", "1e-400", "1e400"):
            with self.subTest(literal=literal):
                with self.assertRaises(NumberProfileError):
                    loads_documents(self._fixture('{"transcript":{"x":%s}}' % literal))

    def test_ordinary_decimals_pass_the_profile(self) -> None:
        from media_clarity.subtitle_contracts import loads_documents

        for literal in ("0.1", "0.30000000000000004", "1.5", "1E2", "-0.0", "0"):
            with self.subTest(literal=literal):
                loads_documents(self._fixture('{"transcript":{"x":%s}}' % literal))

    def test_every_raw_failure_is_a_json_input_error(self) -> None:
        from media_clarity.schema_core import JsonInputError
        from media_clarity.subtitle_contracts import loads_documents

        for text in ('{"a": ', '{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(text=text):
                with self.assertRaises(JsonInputError):
                    loads_documents(text)

    def test_non_object_document_root_is_a_stable_finding(self) -> None:
        for root in ([], None, 7, "x"):
            with self.subTest(root=repr(root)):
                self.assertEqual(
                    validate_documents(root, self.schemas).pairs, (("E_SCHEMA", ""),)
                )

    def test_cli_reports_a_profile_violation_without_a_traceback(self) -> None:
        import subprocess
        import tempfile

        from media_clarity import subtitle_contracts

        with tempfile.TemporaryDirectory(prefix="mcs-029-raw-") as tmp:
            fixtures = Path(tmp) / "fixtures"
            fixtures.mkdir()
            (fixtures / "k-01.json").write_text(
                self._fixture('{"speech_segments":[%s]}' % ("1" * 4301)), encoding="utf-8"
            )
            proc = subprocess.run(
                [
                    sys.executable, "-m", "media_clarity.subtitle_contracts",
                    "--fixtures", str(fixtures), "--schemas", str(SCHEMA_DIR),
                ],
                cwd=REPO_ROOT, capture_output=True, text=True,
                env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin", "HOME": tmp,
                     "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("E_JSON", proc.stderr)
        self.assertIn(subtitle_contracts.NUMBER_PROFILE_ID, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class ArbitraryPrecisionNumberTests(ContractCase):
    HUGE = 10 ** 400

    def _base(self) -> Any:
        return load_fixture(FIXTURE_DIR / "k-01.json")["documents"]

    def test_huge_integers_return_findings_instead_of_crashing(self) -> None:
        cases = (
            ("segment start", lambda d: d["transcript"]["streams"][0]["segments"][0]
             .__setitem__("start_seconds", self.HUGE)),
            ("segment start negative", lambda d: d["transcript"]["streams"][0]["segments"][0]
             .__setitem__("start_seconds", -self.HUGE)),
            ("token confidence", lambda d: d["transcript"]["streams"][0]["segments"][0]
             ["tokens"][0].__setitem__("confidence", self.HUGE)),
            ("speech start", lambda d: d["speech_segments"][0]
             .__setitem__("start_seconds", self.HUGE)),
            ("cue end", lambda d: d["subtitle_document"]["cues"][0]
             .__setitem__("end_seconds", self.HUGE)),
            ("style max_cps", lambda d: d["subtitle_document"]["resolved_style"]
             .__setitem__("max_cps", -self.HUGE)),
            ("fragment offset", lambda d: d["translated_transcript"]["streams"][0]
             ["segments"][0]["source_fragments"][0].__setitem__("char_end", self.HUGE)),
            ("boundary float", lambda d: d["transcript"]["streams"][0]["segments"][0]
             .__setitem__("end_seconds", 1.7976931348623157e308)),
        )
        for name, patch in cases:
            with self.subTest(case=name):
                documents = self._base()
                patch(documents)
                result = validate_documents(documents, self.schemas)
                self.assertTrue(result.findings, f"{name}: finding이 없다")
                for finding in result.findings:
                    self.assertIn(finding.code, ERROR_CODES)

    def test_finite_never_converts_int_to_float(self) -> None:
        from media_clarity.subtitle_contracts import _as_number, _finite

        self.assertTrue(_finite(self.HUGE))
        self.assertTrue(_finite(-self.HUGE))
        self.assertIs(_as_number(self.HUGE), self.HUGE)
        self.assertFalse(_finite(float("nan")))
        self.assertFalse(_finite(float("inf")))
        self.assertIsNone(_as_number(float("inf")))

    def test_cli_returns_stable_codes_for_huge_numbers(self) -> None:
        """CLI fixture 경로도 traceback 없이 안정 code/location을 낸다."""

        import subprocess
        import tempfile

        documents = self._base()
        documents["transcript"]["streams"][0]["segments"][0]["start_seconds"] = self.HUGE
        fixture = {
            "case_id": "K-99999",
            "title": "임의 정밀도 정수",
            "expected": {
                "valid": False,
                "findings": [
                    {
                        "code": "E_TIME_RANGE",
                        "location": "transcript/streams/0/segments/0/end_seconds",
                    }
                ],
            },
            "documents": {
                key: documents[key]
                for key in ("speech_segments", "transcript", "document_refs")
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "k-99.json"
            path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable, "-m", "media_clarity.subtitle_contracts",
                    "--fixtures", tmp,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin", "HOME": tmp,
                     "PYTHONIOENCODING": "utf-8"},
                timeout=120,
            )
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


# ---------------------------------------------------------------------------
# REVIEW-025 R-06 — 고정 defense manifest
# ---------------------------------------------------------------------------


class DefenseManifestTests(ContractCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.verify = _load_verify_script()

    def test_manifest_matches_the_current_schema_defenses(self) -> None:
        rows = self.verify.run_manifest_check(SCHEMA_DIR)
        failures = [f"{row['check_id']}: {row['note']}" for row in rows if not row["passed"]]
        self.assertEqual(failures, [])

    def test_manifest_is_a_separate_frozen_file(self) -> None:
        path = self.verify.DEFENSE_MANIFEST_PATH
        self.assertTrue(path.is_file())
        self.assertNotIn("schemas", path.parts, "manifest가 production schema 안에 있으면 안 된다")
        manifest = self.verify.load_defense_manifest()
        self.assertTrue(manifest["digest"].startswith("sha256:"))
        self.assertGreaterEqual(len(manifest["killable"]), 250)
        self.assertTrue(manifest["equivalent"])
        for entry in manifest["killable"] + manifest["equivalent"]:
            with self.subTest(defense=entry["defense_id"]):
                self.assertTrue(entry["fingerprint"])

    def test_removing_a_production_defense_is_drift_not_a_smaller_denominator(self) -> None:
        import copy

        manifest = self.verify.load_defense_manifest()
        declared = {
            entry["defense_id"]: entry["fingerprint"]
            for entry in manifest["killable"] + manifest["equivalent"]
        }
        observed = {
            defense.defense_id: defense.fingerprint
            for defense in self.verify.collect_schema_defenses(SCHEMA_DIR)
        }
        # 좌표만이 아니라 **의미값**까지 같아야 한다 (REVIEW-026 R-03).
        self.assertEqual(declared, observed)

        shrunk = copy.deepcopy(observed)
        shrunk.pop("speech-segment#/|required:source_track_index")
        self.assertNotEqual(declared, shrunk, "삭제가 drift로 드러나야 한다")
        widened = copy.deepcopy(observed)
        key = "subtitle-document#/$defs/StyleOverride/properties/line_break_policy|enum"
        widened[key] = widened[key][:-1] + ',"x_new_policy"]'
        self.assertNotEqual(declared, widened, "enum 확장이 drift로 드러나야 한다")

    def test_equivalent_allowlist_records_a_reason(self) -> None:
        for entry in self.verify.load_defense_manifest()["equivalent"]:
            with self.subTest(defense=entry["defense_id"]):
                self.assertTrue(entry["reason"].strip())
                self.assertIn("pattern", entry["reason"])

    def test_semantic_drift_is_caught_without_a_manifest_diff(self) -> None:
        """enum 확장·범위 완화·pattern 변경이 좌표만 같으면 통과하던 구멍을 막는다."""

        import json as _json
        import tempfile

        cases = (
            ("enum 확장", "subtitle-document-v1.schema.json",
             ("$defs", "StyleOverride", "properties", "line_break_policy"),
             lambda node: node.__setitem__("enum", list(node["enum"]) + ["x_new_policy"])),
            ("범위 완화", "speech-segment-v1.schema.json",
             ("properties", "source_track_index"),
             lambda node: node.__setitem__("minimum", -1)),
            ("pattern 변경", "transcript-v1.schema.json", ("$defs", "extension_id"),
             lambda node: node.__setitem__("pattern", "^.*$")),
        )
        for title, name, pointer, mutate in cases:
            with self.subTest(case=title), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp) / "schemas"
                work.mkdir()
                for schema_name in SCHEMA_FILES:
                    (work / schema_name).write_bytes((SCHEMA_DIR / schema_name).read_bytes())
                document = _json.loads((work / name).read_text(encoding="utf-8"))
                node = document
                for token in pointer:
                    node = node[token]
                mutate(node)
                (work / name).write_text(
                    _json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                rows = self.verify.run_manifest_check(work)
                self.assertFalse(
                    all(row["passed"] for row in rows),
                    f"{title}이 manifest diff 없이 통과했다",
                )
                self.assertFalse(
                    next(row for row in rows if row["check_id"] == "MF-06")["passed"]
                )

    def test_manifest_sections_must_be_unique_and_disjoint(self) -> None:
        import copy
        import json as _json
        import tempfile

        manifest = self.verify.load_defense_manifest()
        mutations = {
            "killable 중복": lambda m: m.__setitem__(
                "killable", m["killable"] + [copy.deepcopy(m["killable"][0])]
            ),
            "equivalent 중복": lambda m: m.__setitem__(
                "equivalent", m["equivalent"] + [copy.deepcopy(m["equivalent"][0])]
            ),
            "두 절의 교집합": lambda m: m.__setitem__(
                "killable",
                m["killable"] + [{
                    "defense_id": m["equivalent"][0]["defense_id"],
                    "fingerprint": m["equivalent"][0]["fingerprint"],
                }],
            ),
        }
        for title, mutate in mutations.items():
            with self.subTest(case=title), tempfile.TemporaryDirectory() as tmp:
                broken = copy.deepcopy(manifest)
                mutate(broken)
                path = Path(tmp) / "defense-manifest.json"
                path.write_text(
                    _json.dumps(broken, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
                )
                rows = self.verify.run_manifest_check(SCHEMA_DIR, path)
                self.assertFalse(all(row["passed"] for row in rows), title)

    def test_writer_computes_the_digest_from_what_it_writes(self) -> None:
        """갱신 도구가 stale digest 파일을 만들 수 없다 (REVIEW-026 R-03 2번)."""

        import json as _json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "schemas"
            work.mkdir()
            for schema_name in SCHEMA_FILES:
                (work / schema_name).write_bytes((SCHEMA_DIR / schema_name).read_bytes())
            path = Path(tmp) / "defense-manifest.json"
            path.write_bytes(self.verify.DEFENSE_MANIFEST_PATH.read_bytes())

            # equivalent 방어 하나를 지운다 — 이전 판이 stale digest를 쓰던 바로 그 경로다.
            name = "transcript-v1.schema.json"
            document = _json.loads((work / name).read_text(encoding="utf-8"))
            document["$defs"]["extension_id"].pop("minLength")
            (work / name).write_text(
                _json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            # 지운 직후에는 drift로 막혀야 한다.
            self.assertFalse(
                all(row["passed"] for row in self.verify.run_manifest_check(work, path))
            )
            # 명시적 갱신 뒤에는 파일 자체가 일관되어야 한다.
            _, self_check = self.verify.write_defense_manifest(work, path)
            self.assertTrue(all(row["passed"] for row in self_check), self_check)
            self.assertTrue(
                all(row["passed"] for row in self.verify.run_manifest_check(work, path))
            )
            self.assertEqual(
                _json.loads(path.read_text(encoding="utf-8"))["digest"],
                self.verify._manifest_digest(
                    _json.loads(path.read_text(encoding="utf-8"))["killable"],
                    _json.loads(path.read_text(encoding="utf-8"))["equivalent"],
                ),
            )

    def test_duplicate_required_makes_declared_and_unique_differ(self) -> None:
        import json as _json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "schemas"
            work.mkdir()
            for schema_name in SCHEMA_FILES:
                (work / schema_name).write_bytes((SCHEMA_DIR / schema_name).read_bytes())
            name = "transcript-v1.schema.json"
            document = _json.loads((work / name).read_text(encoding="utf-8"))
            document["required"] = list(document["required"]) + ["transcript_id"]
            (work / name).write_text(
                _json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            counts = self.verify.unique_transformation_count(work)
            self.assertNotEqual(counts["defense_declared"], counts["defense_unique"])
            rows = self.verify.run_manifest_check(work)
            self.assertFalse(
                next(row for row in rows if row["check_id"] == "MF-08")["passed"]
            )

    def test_killable_and_equivalent_denominators_are_separated(self) -> None:
        rows = self.verify.run_schema_defense_inventory(FIXTURE_DIR, SCHEMA_DIR)
        killable = [row for row in rows if not row.get("equivalent")]
        equivalent = [row for row in rows if row.get("equivalent")]
        self.assertTrue(equivalent)
        self.assertTrue(all(row["passed"] for row in killable))
        self.assertTrue(all(row["passed"] for row in equivalent))
        self.assertTrue(all(not row.get("subsumed") for row in killable))
        self.assertTrue(all(row.get("subsumed") for row in equivalent))


# ---------------------------------------------------------------------------
# LID 채점 미지원 계약과 고정 격자 경계 (REVIEW-026 D-04, 오너 결정 option 3)
# ---------------------------------------------------------------------------


class LidScoringContract(unittest.TestCase):
    """공식 LID 정확도 채점은 미지원이며, 그 경계는 지금 고정한다."""

    def test_grid_origin_and_interval_are_frozen(self) -> None:
        self.assertEqual(LID_GRID_ORIGIN_SECONDS, "0")
        self.assertEqual(LID_GRID_INTERVAL_SECONDS, "0.1")
        # origin은 첫 발화가 아니라 timebase의 0초다. 실행마다 격자가 밀리지 않는다.
        self.assertEqual(lid_frame_bounds(0), (Decimal("0"), Decimal("0.1")))
        self.assertEqual(lid_frame_bounds(3), (Decimal("0.3"), Decimal("0.4")))

    def test_frames_are_half_open_and_contiguous(self) -> None:
        for index in range(0, 40):
            start, end = lid_frame_bounds(index)
            self.assertEqual(end - start, Decimal(LID_GRID_INTERVAL_SECONDS))
            self.assertEqual(lid_frame_bounds(index + 1)[0], end)
            self.assertEqual(lid_frame_midpoint(index), (start + end) / 2)

    def test_tail_frame_uses_the_midpoint_rule(self) -> None:
        # [0.00, 0.25) — 꼬리 격자 2는 중점 0.25가 구간 밖이라 빠진다.
        self.assertEqual(list(lid_frame_range(0.0, 0.25)), [0, 1])
        # 조금만 더 길어지면 그 격자가 들어온다. 부분 가중치는 없다.
        self.assertEqual(list(lid_frame_range(0.0, 0.26)), [0, 1, 2])
        # 시작 쪽 중점은 포함이다 (반개구간).
        self.assertEqual(list(lid_frame_range(0.05, 0.25)), [0, 1])
        self.assertEqual(list(lid_frame_range(0.06, 0.25)), [1])

    def test_grid_membership_does_not_depend_on_binary64_drift(self) -> None:
        # 0.25 / 0.1 은 binary64에서 2.4999…다. 십진 산술로 고정하지 않으면 흔들린다.
        self.assertEqual(list(lid_frame_range(0.0, 0.25)), list(lid_frame_range(0, 0.25)))
        self.assertEqual(list(lid_frame_range(0.1, 0.3)), [1, 2])
        self.assertEqual(list(lid_frame_range(0.7, 0.9)), [7, 8])

    def test_empty_and_reversed_intervals_cover_nothing(self) -> None:
        self.assertEqual(list(lid_frame_range(1.0, 1.0)), [])
        self.assertEqual(list(lid_frame_range(1.0, 0.5)), [])

    def test_nonfinite_time_is_a_stable_error_without_the_value(self) -> None:
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.assertRaises(ValueError) as caught:
                lid_frame_range(value, 1.0)
            self.assertEqual(str(caught.exception), LID_NONFINITE_MESSAGE)
            self.assertNotIn(repr(value), str(caught.exception))
        with self.assertRaises(ValueError):
            lid_frame_range("0.1", 1.0)

    def test_simultaneous_streams_keep_every_language(self) -> None:
        intervals = [(0.0, 0.5, "ko"), (0.2, 0.9, "en")]
        # 겹치는 격자에서 언어를 하나로 접지 않는다 — 고를 규칙이 없기 때문이다.
        self.assertEqual(lid_frame_languages(intervals, 3), frozenset({"ko", "en"}))
        self.assertEqual(lid_frame_languages(intervals, 0), frozenset({"ko"}))
        self.assertEqual(lid_frame_languages(intervals, 8), frozenset({"en"}))
        self.assertTrue(lid_has_simultaneous_conflict(intervals))
        # 같은 시각에 같은 언어면 충돌이 아니다.
        self.assertFalse(lid_has_simultaneous_conflict([(0.0, 0.5, "ko"), (0.2, 0.9, "ko")]))
        # 이어 붙은 다른 언어도 동시가 아니다.
        self.assertFalse(lid_has_simultaneous_conflict([(0.0, 0.5, "ko"), (0.5, 0.9, "en")]))

    def test_lid_metrics_are_unsupported_regardless_of_data(self) -> None:
        for metric_id in LID_METRIC_IDS:
            result = lid_scoring_result(metric_id)
            self.assertEqual(result["status"], "unsupported")
            self.assertEqual(result["reason"], LID_UNSUPPORTED_REASON)
            # 미지원은 0점도 100점도 아니다.
            self.assertNotIn("value", result)
        with self.assertRaises(ValueError):
            lid_scoring_result("wer")

    def test_zero_denominator_is_explicit_and_never_a_number(self) -> None:
        result = zero_denominator_result("lid_accuracy")
        self.assertEqual(result["status"], "insufficient_n")
        self.assertEqual(result["reason"], ZERO_DENOMINATOR_REASON)
        self.assertEqual(result["n"], 0)
        self.assertNotIn("value", result)
        with self.assertRaises(ValueError):
            zero_denominator_result("")

    def test_metric_results_match_the_common_v1_metric_status_vocabulary(self) -> None:
        common = json.loads((SCHEMA_DIR / "common-v1.schema.json").read_text(encoding="utf-8"))
        allowed = common["$defs"]["metric_status"]["enum"]
        self.assertIn(lid_scoring_result("lid_accuracy")["status"], allowed)
        self.assertIn(zero_denominator_result("lid_accuracy")["status"], allowed)

    def test_adjacent_same_language_spans_normalize_to_one(self) -> None:
        spans = [
            {"char_start": 0, "char_end": 3, "language": "ja"},
            {"char_start": 3, "char_end": 5, "language": "en", "switch_kind": "intra_sentential"},
            {"char_start": 5, "char_end": 8, "language": "en", "switch_kind": "intra_sentential"},
            {"char_start": 8, "char_end": 11, "language": "ja", "switch_kind": "intra_sentential"},
        ]
        self.assertEqual(
            normalize_language_spans(spans),
            [
                {"char_start": 0, "char_end": 3, "language": "ja"},
                {"char_start": 3, "char_end": 8, "language": "en",
                 "switch_kind": "intra_sentential"},
                {"char_start": 8, "char_end": 11, "language": "ja",
                 "switch_kind": "intra_sentential"},
            ],
        )
        # 정규형은 고정점이다.
        self.assertEqual(
            normalize_language_spans(normalize_language_spans(spans)),
            normalize_language_spans(spans),
        )

    def test_normalization_does_not_close_gaps(self) -> None:
        # 맞닿지 않은 같은 언어 span은 합치지 않는다 — 사이의 gap은 별도 계약이다.
        spans = [
            {"char_start": 0, "char_end": 3, "language": "en"},
            {"char_start": 5, "char_end": 8, "language": "en", "switch_kind": "unknown"},
        ]
        self.assertEqual(normalize_language_spans(spans), spans)

    def test_documents_must_already_be_in_the_normal_form(self) -> None:
        """정규형이 아닌 문서는 validator가 직접 거부한다 (K-170·K-171)."""

        schemas = SchemaSet(SCHEMA_DIR)
        for case, location in (
            ("k-170.json", "transcript/streams/0/segments/0/language_spans/2/language"),
            ("k-171.json", "transcript/streams/1/segments/0/language_spans/1/language"),
        ):
            documents = load_fixture(FIXTURE_DIR / case)["documents"]
            result = validate_documents(documents, schemas)
            self.assertFalse(result.valid)
            self.assertIn(("E_OFFSET_ORDER", location), result.pairs)


if __name__ == "__main__":
    unittest.main()
