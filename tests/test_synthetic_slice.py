from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from media_clarity.synthetic_slice import (
    GENERATED_SRT,
    GENERATED_SRT_SHA256,
    SliceError,
    canonical_srt,
    parse_srt,
    plan_paths,
)


class SrtContractTests(unittest.TestCase):
    def test_generated_bytes_match_gate_s(self) -> None:
        self.assertEqual(len(GENERATED_SRT), 98)
        self.assertEqual(hashlib.sha256(GENERATED_SRT).hexdigest(), GENERATED_SRT_SHA256)
        self.assertEqual(GENERATED_SRT[-2:], b"\n\n")
        self.assertNotIn(b"\r", GENERATED_SRT)

    def test_canonicalization_ignores_only_serialization_shape(self) -> None:
        shaped = b"\xef\xbb\xbf" + GENERATED_SRT.replace(b"\n", b"\r\n")
        shaped = shaped.replace(b"[fixture cue 1]\r\n", b"[fixture cue 1] \t\r\n")
        self.assertEqual(canonical_srt(GENERATED_SRT, 6.0), canonical_srt(shaped, 6.0))

    def test_canonicalization_detects_semantic_changes(self) -> None:
        mutations = [
            GENERATED_SRT.replace(b"00:00:00,500", b"00:00:00,600"),
            GENERATED_SRT.replace(b"00:00:05,500", b"00:00:05,400"),
            GENERATED_SRT.replace(b"[fixture cue 2]", b"[fixture cue X]"),
            GENERATED_SRT.replace(b"\n2\n", b"\n3\n"),
            GENERATED_SRT.split(b"\n\n2\n", 1)[0] + b"\n\n",
        ]
        baseline = canonical_srt(GENERATED_SRT, 6.0)
        for mutated in mutations:
            with self.subTest(mutated=mutated):
                self.assertNotEqual(baseline, canonical_srt(mutated, 6.0))

    def test_rejects_reversed_overlap_and_duration_escape(self) -> None:
        invalid = [
            GENERATED_SRT.replace(
                b"00:00:00,500 --> 00:00:02,500",
                b"00:00:02,500 --> 00:00:00,500",
            ),
            GENERATED_SRT.replace(b"00:00:03,000", b"00:00:02,000"),
            GENERATED_SRT.replace(b"00:00:05,500", b"00:00:06,500"),
        ]
        for sample in invalid:
            with self.subTest(sample=sample), self.assertRaises(SliceError):
                parse_srt(sample, 6.0)


class PreflightTests(unittest.TestCase):
    def _args(self, root: Path) -> argparse.Namespace:
        return argparse.Namespace(
            input=str(root / "source.mkv"),
            srt=None,
            generate_fixture_srt=True,
            work_dir=str(root / "work"),
        )

    def test_unset_or_empty_staging_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source.mkv").write_bytes(b"not-empty")
            for environ in ({}, {"MCS_ICLOUD_STAGING_DIR": ""}):
                with self.subTest(environ=environ), self.assertRaises(SliceError):
                    plan_paths(self._args(root), environ)
                self.assertFalse((root / "work").exists())

    def test_existing_target_is_rejected_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source.mkv").write_bytes(b"not-empty")
            work = root / "work"
            work.mkdir()
            target = work / "source-softsub.mkv"
            target.write_bytes(b"keep")
            with self.assertRaises(SliceError):
                plan_paths(
                    self._args(root),
                    {"MCS_ICLOUD_STAGING_DIR": str(root / "staging")},
                )
            self.assertEqual(target.read_bytes(), b"keep")

    def test_rejects_filesystem_root_as_staging(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source.mkv").write_bytes(b"not-empty")
            with self.assertRaises(SliceError):
                plan_paths(self._args(root), {"MCS_ICLOUD_STAGING_DIR": os.path.abspath(os.sep)})

    def test_rejects_same_work_and_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source.mkv").write_bytes(b"not-empty")
            with self.assertRaises(SliceError):
                plan_paths(
                    self._args(root),
                    {"MCS_ICLOUD_STAGING_DIR": str(root / "work")},
                )


if __name__ == "__main__":
    unittest.main()
