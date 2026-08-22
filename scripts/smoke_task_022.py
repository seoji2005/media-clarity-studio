from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from media_clarity.synthetic_slice import GENERATED_SRT_SHA256


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr}"
        )
    return completed


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    for tool in ("ffmpeg", "ffprobe"):
        run([tool, "-version"])

    with tempfile.TemporaryDirectory(prefix="mcs-task022-") as raw:
        root = Path(raw)
        source = root / "fixture-source.mkv"
        work = root / "work"
        staging = root / "staging"
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=30:duration=6",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=6",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                "-c:v",
                "ffv1",
                "-level:v",
                "3",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "1",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                "-metadata",
                "creation_time=1970-01-01T00:00:00Z",
                os.fspath(source),
            ]
        )
        source_before = digest(source)

        missing_env = os.environ.copy()
        missing_env.pop("MCS_ICLOUD_STAGING_DIR", None)
        missing = subprocess.run(
            [
                sys.executable,
                "-m",
                "media_clarity",
                "--input",
                os.fspath(source),
                "--generate-fixture-srt",
                "--work-dir",
                os.fspath(work),
            ],
            capture_output=True,
            text=True,
            env=missing_env,
            check=False,
        )
        if missing.returncode == 0 or work.exists() or staging.exists():
            raise AssertionError("unset staging guard did not fail before filesystem mutation")

        env = os.environ.copy()
        env["MCS_ICLOUD_STAGING_DIR"] = os.fspath(staging)
        completed = run(
            [
                sys.executable,
                "-m",
                "media_clarity",
                "--input",
                os.fspath(source),
                "--generate-fixture-srt",
                "--work-dir",
                os.fspath(work),
            ],
            env=env,
        )
        report = json.loads(completed.stdout)
        output = work / "fixture-source-softsub.mkv"
        exported = staging / output.name
        generated = work / "fixture-source.generated.srt"
        manifest = work / "fixture-source.verify.json"
        if report["status"] != "complete" or not manifest.is_file():
            raise AssertionError("complete verification manifest was not produced")
        if digest(source) != source_before:
            raise AssertionError("source changed")
        if digest(output) != digest(exported):
            raise AssertionError("staging export hash mismatch")
        if digest(generated) != GENERATED_SRT_SHA256:
            raise AssertionError("generated SRT bytes do not match Gate S")
        if not report["subtitle"]["canonical_equal"] or not report["subtitle"]["raw_equal"]:
            raise AssertionError("subtitle round-trip failed")

        output_before = output.read_bytes()
        second = subprocess.run(
            [
                sys.executable,
                "-m",
                "media_clarity",
                "--input",
                os.fspath(source),
                "--generate-fixture-srt",
                "--work-dir",
                os.fspath(work),
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if second.returncode == 0 or output.read_bytes() != output_before:
            raise AssertionError("existing output was overwritten")

        occupied_staging = root / "occupied-staging"
        occupied_staging.mkdir()
        occupied_target = occupied_staging / output.name
        occupied_target.write_bytes(b"keep-staging")
        occupied_work = root / "occupied-work"
        occupied_env = os.environ.copy()
        occupied_env["MCS_ICLOUD_STAGING_DIR"] = os.fspath(occupied_staging)
        occupied = subprocess.run(
            [
                sys.executable,
                "-m",
                "media_clarity",
                "--input",
                os.fspath(source),
                "--generate-fixture-srt",
                "--work-dir",
                os.fspath(occupied_work),
            ],
            capture_output=True,
            text=True,
            env=occupied_env,
            check=False,
        )
        if (
            occupied.returncode == 0
            or occupied_work.exists()
            or occupied_target.read_bytes() != b"keep-staging"
        ):
            raise AssertionError("existing staging target was overwritten or work started")

        shape_work = root / "shape-work"
        shape_staging = root / "shape-staging"
        shape_srt = root / "shape.srt"
        shape_srt.write_bytes(generated.read_bytes()[:-1])
        shape_env = os.environ.copy()
        shape_env["MCS_ICLOUD_STAGING_DIR"] = os.fspath(shape_staging)
        shape = subprocess.run(
            [
                sys.executable,
                "-m",
                "media_clarity",
                "--input",
                os.fspath(source),
                "--srt",
                os.fspath(shape_srt),
                "--work-dir",
                os.fspath(shape_work),
            ],
            capture_output=True,
            text=True,
            env=shape_env,
            check=False,
        )
        shape_failures = list(shape_work.glob("*.failure-*.json"))
        if shape.returncode == 0 or len(shape_failures) != 1 or shape_staging.exists():
            raise AssertionError("raw byte-shape violation did not fail before export")
        shape_failure = json.loads(shape_failures[0].read_text(encoding="utf-8"))
        if shape_failure.get("details") != {
            "canonical_equal": True,
            "raw_equal": False,
            "classification": "byte_shape_violation",
        }:
            raise AssertionError("raw and canonical outcomes were not recorded separately")
        if (shape_work / "fixture-source-softsub.mkv").exists():
            raise AssertionError("byte-shape failure was promoted to a completed output")

        command_work = root / "command-work"
        command_staging = root / "command-staging"
        command_env = os.environ.copy()
        command_env["MCS_ICLOUD_STAGING_DIR"] = os.fspath(command_staging)
        command_failure = subprocess.run(
            [
                sys.executable,
                "-m",
                "media_clarity",
                "--input",
                os.fspath(source),
                "--generate-fixture-srt",
                "--work-dir",
                os.fspath(command_work),
                "--ffmpeg",
                os.fspath(root / "missing-ffmpeg"),
            ],
            capture_output=True,
            text=True,
            env=command_env,
            check=False,
        )
        command_failures = list(command_work.glob("*.failure-*.json"))
        if (
            command_failure.returncode == 0
            or len(command_failures) != 1
            or command_staging.exists()
            or (command_work / "fixture-source.verify.json").exists()
        ):
            raise AssertionError("FFmpeg failure was not preserved as a failed, non-exported run")
        if digest(source) != source_before:
            raise AssertionError("source changed during failure injection")

        evidence = {
            "status": "PASS",
            "source_sha256": source_before,
            "srt_sha256": digest(generated),
            "output_sha256": digest(output),
            "export_sha256": digest(exported),
            "source_unchanged": digest(source) == source_before,
            "canonical_equal": report["subtitle"]["canonical_equal"],
            "raw_equal": report["subtitle"]["raw_equal"],
            "existing_output_preserved": output.read_bytes() == output_before,
            "existing_staging_preserved": occupied_target.read_bytes() == b"keep-staging",
            "unset_guard_no_filesystem_change": True,
            "raw_violation_classified_before_export": True,
            "ffmpeg_failure_recorded_before_export": True,
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
