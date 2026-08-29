"""TASK-028 content-addressed artifact store 테스트.

fixture의 expected를 그대로 통과시키지 않는다. 실제 임시 project root에서 production
API를 호출하고, 계약을 어기는 mutation이 반드시 실패하는지 확인한다.
"""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from media_clarity.artifact_store import (
    CAS_ROOT,
    CHUNK_BYTES,
    ERROR_CODES,
    INCOMING_ROOT,
    ArtifactStore,
    ContractViolation,
    FailureInjection,
    cas_relative_uri,
    content_hash_of,
    digest_of,
    existing_temp_paths,
    hash_file,
    opaque_identity_error,
    path_segment_error,
    relative_path_error,
    resolve_inside_root,
)


class StoreCase(unittest.TestCase):
    """임시 project root를 소유하는 base. 정리는 테스트 소유 자원에만 적용된다."""

    def setUp(self) -> None:
        self._temporary = TemporaryDirectory(prefix="mcs-store-")
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.store = ArtifactStore(self.root)

    def write_source(self, name: str, text: str) -> Path:
        path = self.root / "input" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def add(self, source: Path, **kwargs: Any):
        kwargs.setdefault("job_id", "job-a")
        kwargs.setdefault("stage_id", "extract")
        return self.store.add_file(source, **kwargs)

    def assert_violation(self, code: str, callable_: Any, *args: Any, **kwargs: Any) -> ContractViolation:
        with self.assertRaises(ContractViolation) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception


class ErrorCodeTests(unittest.TestCase):
    def test_codes_are_stable_and_unique(self) -> None:
        self.assertEqual(len(ERROR_CODES), len(set(ERROR_CODES)))
        for code in ERROR_CODES:
            self.assertRegex(code, r"^E_[A-Z_]+$")

    def test_undeclared_code_is_rejected(self) -> None:
        """오류 코드는 선언된 목록에서만 나온다."""

        with self.assertRaises(AssertionError):
            ContractViolation("E_NOT_DECLARED", "x", "y")


class ContentAddressingTests(StoreCase):
    def test_uri_is_portable_relative_cas_path(self) -> None:
        source = self.write_source("a.txt", "hello")
        written = self.add(source)
        digest = hashlib.sha256(b"hello").hexdigest()
        self.assertEqual(written.ref["uri"], f"{CAS_ROOT}/{digest[:2]}/{digest}")
        self.assertIsNone(relative_path_error(written.ref["uri"]))
        self.assertEqual(written.ref["content_hash"], f"sha256:{digest}")
        self.assertEqual(written.ref["byte_size"], 5)

    def test_uri_never_contains_the_external_input_path(self) -> None:
        source = self.write_source("secret-name.txt", "hello")
        written = self.add(source)
        self.assertNotIn("secret-name", written.ref["uri"])
        self.assertNotIn(str(self.root), written.ref["uri"])

    def test_hash_is_streamed_in_chunks(self) -> None:
        """입력 전체를 RAM에 올리지 않는다 — chunk hook 호출 횟수로 확인한다."""

        payload = "x" * (CHUNK_BYTES * 2 + 7)
        source = self.write_source("big.txt", payload)
        seen: list[int] = []
        written = self.add(source, injection=FailureInjection(on_chunk=seen.append))
        self.assertEqual(seen, [0, 1, 2])
        self.assertEqual(written.ref["byte_size"], len(payload))
        self.assertEqual(
            written.ref["content_hash"], content_hash_of(hashlib.sha256(payload.encode()).hexdigest())
        )

    def test_hash_file_matches_hashlib(self) -> None:
        source = self.write_source("a.txt", "hello")
        self.assertEqual(hash_file(source), (hashlib.sha256(b"hello").hexdigest(), 5))

    def test_digest_round_trip_rejects_malformed_hashes(self) -> None:
        digest = hashlib.sha256(b"hello").hexdigest()
        self.assertEqual(digest_of(content_hash_of(digest)), digest)
        self.assert_violation("E_ARTIFACT_CORRUPT", digest_of, "sha1:" + digest)
        self.assert_violation("E_ARTIFACT_CORRUPT", digest_of, "sha256:" + digest.upper())
        self.assert_violation("E_ARTIFACT_CORRUPT", cas_relative_uri, "nothex")


class DedupeAndNoOverwriteTests(StoreCase):
    def test_identical_bytes_dedupe_without_touching_the_existing_object(self) -> None:
        first = self.add(self.write_source("a.txt", "same bytes"))
        target = self.store.absolute(first.ref["uri"], "uri")
        before = os.stat(target)

        second = self.add(self.write_source("b.txt", "same bytes"))
        after = os.stat(target)

        self.assertEqual(first.ref["uri"], second.ref["uri"])
        self.assertFalse(first.deduped)
        self.assertTrue(second.deduped)
        self.assertEqual(before.st_ino, after.st_ino)
        self.assertEqual(before.st_size, after.st_size)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
        self.assertEqual(target.read_text(encoding="utf-8"), "same bytes")

    def test_existing_object_with_different_bytes_is_a_collision(self) -> None:
        """최종 CAS 경로 덮어쓰기 시도는 거부된다 — 기존 파일은 그대로 남는다."""

        written = self.add(self.write_source("a.txt", "original"))
        target = self.store.absolute(written.ref["uri"], "uri")
        target.write_text("corrupted", encoding="utf-8")

        error = self.assert_violation(
            "E_ARTIFACT_COLLISION", self.add, self.write_source("again.txt", "original")
        )
        self.assertEqual(error.location, written.ref["uri"])
        self.assertEqual(target.read_text(encoding="utf-8"), "corrupted")

    def test_every_cas_file_name_equals_its_own_digest(self) -> None:
        """CAS object가 덮어쓰기로 오염되지 않았음을 store 전체에서 확인한다."""

        for text in ("one", "two", "three"):
            self.add(self.write_source(f"{text}.txt", text))
        cas = self.root / CAS_ROOT
        names = [path for path in cas.rglob("*") if path.is_file()]
        self.assertEqual(len(names), 3)
        for path in names:
            digest, _ = hash_file(path)
            self.assertEqual(path.name, digest)
            self.assertEqual(path.parent.name, digest[:2])

    def test_corrupted_object_is_rejected_by_verify(self) -> None:
        written = self.add(self.write_source("a.txt", "original"))
        target = self.store.absolute(written.ref["uri"], "uri")

        target.write_text("tampered", encoding="utf-8")
        self.assert_violation("E_ARTIFACT_CORRUPT", self.store.verify_ref, written.ref, "outputs/0")

        target.unlink()
        self.assert_violation("E_ARTIFACT_MISSING", self.store.verify_ref, written.ref, "outputs/0")

    def test_size_mismatch_alone_is_rejected(self) -> None:
        written = self.add(self.write_source("a.txt", "original"))
        tampered = dict(written.ref)
        tampered["byte_size"] = written.ref["byte_size"] + 1
        self.assert_violation("E_ARTIFACT_CORRUPT", self.store.verify_ref, tampered, "outputs/0")

    def test_promoted_bytes_are_re_verified_before_the_ref_is_returned(self) -> None:
        """승격 후 재검증이 실제로 동작하는지 — 승격 직후 파일을 손상시켜 관측한다.

        이 검사가 없으면 승격 직후 손상된 바이트로도 `ArtifactRef`가 만들어진다.
        """

        source = self.write_source("a.txt", "original")

        def corrupt(uri: str) -> None:
            (self.root / uri).write_text("corrupted right after promotion", encoding="utf-8")

        error = self.assert_violation(
            "E_ARTIFACT_CORRUPT",
            self.add,
            source,
            injection=FailureInjection(after_promote=corrupt),
        )
        self.assertTrue(error.location.startswith(CAS_ROOT + "/"))
        self.assertEqual(source.read_text(encoding="utf-8"), "original", "입력이 바뀌었다")

    def test_verify_accepts_an_intact_artifact(self) -> None:
        written = self.add(self.write_source("a.txt", "original"))
        self.assertEqual(self.store.verify_ref(written.ref, "outputs/0"), 8)


class InputMutationTests(StoreCase):
    def test_input_changed_during_copy_produces_no_artifact(self) -> None:
        """flaky sleep/thread 대신 chunk hook으로 결정적으로 재현한다."""

        source = self.write_source("a.txt", "x" * (CHUNK_BYTES + 16))

        def mutate(index: int) -> None:
            if index == 0:
                with open(source, "r+b") as handle:
                    handle.write(b"Y")
                os.utime(source, (0, 0))

        error = self.assert_violation(
            "E_INPUT_CHANGED", self.add, source, injection=FailureInjection(on_chunk=mutate)
        )
        self.assertEqual(error.location, "stage_output")
        cas = self.root / CAS_ROOT
        promoted = [path for path in cas.rglob("*") if path.is_file()] if cas.is_dir() else []
        self.assertEqual(promoted, [])

    def test_unchanged_input_is_accepted(self) -> None:
        source = self.write_source("a.txt", "x" * (CHUNK_BYTES + 16))
        written = self.add(source, injection=FailureInjection(on_chunk=lambda index: None))
        self.assertTrue(self.store.absolute(written.ref["uri"], "uri").is_file())

    def test_missing_stage_output_is_reported_without_a_path(self) -> None:
        error = self.assert_violation("E_ARTIFACT_MISSING", self.add, self.root / "nope.txt")
        self.assertEqual(error.location, "stage_output")
        self.assertNotIn(str(self.root), str(error))


class EvidenceRetentionTests(StoreCase):
    def test_failed_temp_file_is_kept_as_evidence_and_is_not_an_artifact(self) -> None:
        """자동 삭제·GC가 없다. 실패한 임시 파일은 CAS lookup 대상이 아니다."""

        source = self.write_source("a.txt", "x" * (CHUNK_BYTES + 4))
        self.assert_violation(
            "E_INPUT_CHANGED",
            self.add,
            source,
            injection=FailureInjection(on_chunk=lambda index: os.utime(source, (0, 0))),
        )
        leftovers = existing_temp_paths(self.root)
        self.assertEqual(len(leftovers), 1)
        self.assertTrue(leftovers[0].startswith(INCOMING_ROOT + "/"))
        self.assertNotIn(CAS_ROOT, leftovers[0])
        self.assertTrue((self.root / leftovers[0]).is_file())

    def test_successful_write_leaves_no_temp_file_behind(self) -> None:
        self.add(self.write_source("a.txt", "hello"))
        self.assertEqual(existing_temp_paths(self.root), [])

    def test_store_never_deletes_an_existing_cas_object(self) -> None:
        written = self.add(self.write_source("a.txt", "keep me"))
        target = self.store.absolute(written.ref["uri"], "uri")
        for _ in range(3):
            self.add(self.write_source("again.txt", "keep me"))
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")


class PathSafetyTests(StoreCase):
    def test_unsafe_relative_paths_are_rejected(self) -> None:
        cases = {
            "/etc/passwd": "POSIX 절대 경로",
            "C:/Windows": "Windows drive 경로",
            "//server/share": "UNC 경로",
            "../outside": "'..' 구간",
            "a//b": "빈 경로 구간",
            "a/./b": "'.' 구간",
            "a\\b": "역슬래시 (Windows 경로 구분자)",
            " a": "앞뒤 공백",
            "a\x00b": "NUL 문자",
            "": "빈 경로",
        }
        for value, expected in cases.items():
            with self.subTest(path=value):
                self.assertEqual(relative_path_error(value), expected)

    def test_safe_relative_path_is_accepted(self) -> None:
        self.assertIsNone(relative_path_error("jobs/job-a/manifest.json"))
        self.assertIsNone(relative_path_error("artifacts/sha256/ab/" + "a" * 64))

    def test_windows_hostile_segments_are_rejected(self) -> None:
        cases = {
            "with:colon": "허용 문자 밖 (A-Za-z0-9로 시작하고 A-Za-z0-9._- 만 허용)",
            "trailing.": "마지막 문자가 dot 또는 space (Windows 비호환)",
            "trailing ": "허용 문자 밖 (A-Za-z0-9로 시작하고 A-Za-z0-9._- 만 허용)",
            "CON": "Windows 예약 장치명",
            "con.txt": "Windows 예약 장치명",
            "LPT9": "Windows 예약 장치명",
            "NUL": "Windows 예약 장치명",
            ".hidden": "허용 문자 밖 (A-Za-z0-9로 시작하고 A-Za-z0-9._- 만 허용)",
            "": "빈 식별자",
            "a" * 129: "128자 초과",
        }
        for value, expected in cases.items():
            with self.subTest(segment=value):
                self.assertEqual(path_segment_error(value), expected)

    def test_common_identifier_colon_is_not_trusted_as_a_path_segment(self) -> None:
        """공통 identifier는 ':'을 허용하지만 filesystem segment로는 거부한다."""

        self.assertIsNotNone(path_segment_error("stage:extract"))
        self.assert_violation(
            "E_UNSAFE_PATH", self.add, self.write_source("a.txt", "x"), stage_id="stage:extract"
        )

    def test_safe_segments_are_accepted(self) -> None:
        for value in ("job-a", "stage_1", "a.b.c", "A0"):
            with self.subTest(segment=value):
                self.assertIsNone(path_segment_error(value))

    def test_symlink_escape_is_rejected(self) -> None:
        outside = Path(self._temporary.name).parent / f"outside-{os.getpid()}"
        outside.mkdir(exist_ok=True)
        self.addCleanup(lambda: outside.rmdir() if outside.is_dir() else None)
        try:
            (self.root / "escape").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):  # pragma: no cover - symlink 미지원 환경
            self.skipTest("이 환경은 symlink를 만들 수 없다")
        self.assert_violation(
            "E_UNSAFE_PATH", resolve_inside_root, self.root, "escape/leak.txt", "target"
        )

    def test_paths_inside_root_resolve(self) -> None:
        resolved = resolve_inside_root(self.root, "jobs/job-a/manifest.json", "target")
        self.assertTrue(str(resolved).startswith(str(self.root)))

    def test_missing_project_root_is_rejected(self) -> None:
        self.assert_violation("E_UNSAFE_PATH", ArtifactStore, self.root / "nope")


class ReviewM03OpaqueIdentityTests(unittest.TestCase):
    """REVIEW-018 M-03 — 불투명 식별자와 경로처럼 보이는 값의 경계."""

    def test_path_like_values_are_rejected(self) -> None:
        cases = {
            "/var/media/a.mkv": "POSIX 절대 경로처럼 보인다",
            "C:/Users/a.mkv": "Windows drive 경로처럼 보인다",
            "//server/share/a.mkv": "UNC 경로처럼 보인다",
            "~/Movies/a.mkv": "home 확장 경로처럼 보인다",
            "media/a.mkv": "경로 구분자를 포함한다 (불투명 식별자여야 한다)",
            "C:\\Users\\a.mkv": "역슬래시 (Windows 경로 구분자)",
            "..": "traversal 구간을 포함한다",
            "a..b": "traversal 구간을 포함한다",
            "": "빈 식별자",
            " src": "앞뒤 공백",
            "a\x00b": "NUL 문자",
            "s" * 257: "256자 초과",
        }
        for value, expected in cases.items():
            with self.subTest(value=value[:24]):
                self.assertEqual(opaque_identity_error(value), expected)

    def test_opaque_identifiers_are_accepted(self) -> None:
        for value in ("src-1", "sha256-abcdef", "corpus.sample.001", "SOURCE_42"):
            with self.subTest(value=value):
                self.assertIsNone(opaque_identity_error(value))

    def test_reason_never_contains_the_value(self) -> None:
        secret = "/var/media/DO-NOT-LEAK.mkv"
        reason = opaque_identity_error(secret)
        self.assertIsNotNone(reason)
        self.assertNotIn(secret, reason)
        self.assertNotIn("DO-NOT-LEAK", reason)


class ReviewM04TempEvidenceTests(StoreCase):
    """REVIEW-018 M-04 — 실패 예외가 실제 보존 temp 경로를 싣는다."""

    def test_failure_carries_the_surviving_temp_path(self) -> None:
        source = self.write_source("a.txt", "x" * (CHUNK_BYTES + 4))

        def mutate(index: int) -> None:
            if index == 0:
                os.utime(source, (0, 0))

        error = self.assert_violation(
            "E_INPUT_CHANGED", self.add, source, injection=FailureInjection(on_chunk=mutate)
        )
        self.assertEqual(list(error.temp_paths), existing_temp_paths(self.root))
        self.assertTrue(error.temp_paths)
        for relative in error.temp_paths:
            self.assertTrue((self.root / relative).is_file())

    def test_collision_failure_carries_the_surviving_temp_path(self) -> None:
        written = self.add(self.write_source("a.txt", "original"))
        self.store.absolute(written.ref["uri"], "uri").write_text("corrupted", encoding="utf-8")
        before = set(existing_temp_paths(self.root))

        error = self.assert_violation(
            "E_ARTIFACT_COLLISION", self.add, self.write_source("again.txt", "original")
        )
        self.assertEqual(
            set(error.temp_paths), set(existing_temp_paths(self.root)) - before
        )
        self.assertTrue(error.temp_paths)

    def test_success_leaves_no_temp_evidence(self) -> None:
        self.add(self.write_source("a.txt", "hello"))
        self.assertEqual(self.store.surviving_temp_paths(existing_temp_paths(self.root)), ())

    def test_surviving_temp_paths_filters_deleted_names(self) -> None:
        """성공 뒤 정리된 이름은 증거가 아니다."""

        written = self.add(self.write_source("a.txt", "hello"))
        self.assertEqual(
            self.store.surviving_temp_paths((written.temp_relative_path,)),
            (),
            "이미 지워진 temp 경로가 증거로 남았다",
        )

    def test_default_violation_has_no_temp_paths(self) -> None:
        self.assertEqual(ContractViolation("E_SCHEMA", "x", "y").temp_paths, ())


if __name__ == "__main__":
    unittest.main()
