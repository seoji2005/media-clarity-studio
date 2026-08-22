from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "mcs.synthetic-slice.verify/v1"
STAGING_ENV = "MCS_ICLOUD_STAGING_DIR"
GENERATED_SRT = (
    b"1\n"
    b"00:00:00,500 --> 00:00:02,500\n"
    b"[fixture cue 1]\n"
    b"\n"
    b"2\n"
    b"00:00:03,000 --> 00:00:05,500\n"
    b"[fixture cue 2]\n"
    b"\n"
)
GENERATED_SRT_SHA256 = "c2ed5960b423ee3d00c23d4d4f61dc62371fdb22e0fa090766bbb8262120eb97"
TIME_RE = re.compile(
    r"^(?P<sh>\d{2,}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})"
    r" --> "
    r"(?P<eh>\d{2,}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})$"
)


class SliceError(RuntimeError):
    """Expected, user-actionable pipeline failure."""


class VerificationError(SliceError):
    def __init__(self, message: str, **details: Any):
        self.details = details
        super().__init__(message)


class CommandError(SliceError):
    def __init__(self, phase: str, command: Sequence[str], returncode: int, stderr: str):
        self.phase = phase
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"{phase} 명령 실패(exit {returncode}): {stderr.strip() or '(stderr 없음)'}"
        )


@dataclass(frozen=True)
class Cue:
    index: str
    start_ms: int
    end_ms: int
    timecode: str
    text: tuple[str, ...]


@dataclass(frozen=True)
class SlicePaths:
    source: Path
    work_dir: Path
    staging_dir: Path
    srt: Path
    output: Path
    extracted: Path
    report: Path
    export: Path
    generated: bool


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_ms(match: re.Match[str], prefix: str) -> int:
    hours = int(match.group(f"{prefix}h"))
    minutes = int(match.group(f"{prefix}m"))
    seconds = int(match.group(f"{prefix}s"))
    millis = int(match.group(f"{prefix}ms"))
    if minutes > 59 or seconds > 59:
        raise SliceError("SRT timestamp의 분·초는 00..59여야 합니다")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def parse_srt(data: bytes, duration_seconds: float) -> list[Cue]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SliceError(f"SRT가 유효한 UTF-8이 아닙니다: {exc}") from exc

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line == "":
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    if not blocks:
        raise SliceError("SRT cue가 없습니다")

    cues: list[Cue] = []
    duration_ms = round(duration_seconds * 1000)
    seen_indexes: set[str] = set()
    for block in blocks:
        if len(block) < 3:
            raise SliceError("각 SRT cue에는 번호, 시각줄, 텍스트가 필요합니다")
        index, timecode, *cue_text = block
        if not index.isdigit():
            raise SliceError(f"SRT cue 번호가 숫자가 아닙니다: {index!r}")
        if index in seen_indexes:
            raise SliceError(f"SRT cue 번호가 중복됩니다: {index}")
        match = TIME_RE.fullmatch(timecode)
        if match is None:
            raise SliceError(f"SRT 시각줄 형식이 잘못되었습니다: {timecode!r}")
        start_ms = _timestamp_ms(match, "s")
        end_ms = _timestamp_ms(match, "e")
        if start_ms >= end_ms:
            raise SliceError(f"SRT 구간이 역전되었거나 길이가 0입니다: cue {index}")
        if end_ms > duration_ms:
            raise SliceError(
                f"SRT cue {index}가 입력 duration을 벗어납니다: {end_ms}ms > {duration_ms}ms"
            )
        if cues and start_ms < cues[-1].end_ms:
            raise SliceError(f"SRT cue가 겹치거나 시간순이 아닙니다: cue {index}")
        seen_indexes.add(index)
        cues.append(Cue(index, start_ms, end_ms, timecode, tuple(cue_text)))
    return cues


def canonical_srt(data: bytes, duration_seconds: float) -> bytes:
    cues = parse_srt(data, duration_seconds)
    rows = [
        "CUE\t{}\t{}\t{}".format(cue.index, cue.timecode, "\\n".join(cue.text))
        for cue in cues
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def _run(command: Sequence[str], phase: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as exc:
        raise CommandError(phase, command, 127, str(exc)) from exc
    if completed.returncode != 0:
        raise CommandError(phase, command, completed.returncode, completed.stderr[-8000:])
    return completed


def probe_media(path: Path, ffprobe: str) -> dict[str, Any]:
    completed = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            os.fspath(path),
        ],
        "probe",
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SliceError(f"ffprobe JSON을 해석할 수 없습니다: {exc}") from exc


def _duration(probe: dict[str, Any]) -> float:
    try:
        return float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SliceError("입력 duration을 probe 결과에서 찾을 수 없습니다") from exc


def _streams(probe: dict[str, Any], codec_type: str) -> list[dict[str, Any]]:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise SliceError("probe 결과에 streams 배열이 없습니다")
    return [stream for stream in streams if stream.get("codec_type") == codec_type]


def validate_source_profile(probe: dict[str, Any]) -> float:
    duration = _duration(probe)
    if abs(duration - 6.0) > 0.001:
        raise SliceError(f"합성 fixture duration은 6.000초여야 합니다: {duration:.6f}")
    videos = _streams(probe, "video")
    audios = _streams(probe, "audio")
    if len(videos) != 1 or len(audios) != 1:
        raise SliceError("합성 fixture는 video 1개와 audio 1개여야 합니다")
    video = videos[0]
    audio = audios[0]
    if (
        video.get("codec_name") != "ffv1"
        or video.get("width") != 640
        or video.get("height") != 360
        or Fraction(video.get("r_frame_rate", "0/1")) != Fraction(30, 1)
    ):
        raise SliceError("video profile은 ffv1 640x360 30 fps여야 합니다")
    if (
        audio.get("codec_name") != "pcm_s16le"
        or str(audio.get("sample_rate")) != "48000"
        or audio.get("channels") != 1
    ):
        raise SliceError("audio profile은 pcm_s16le 48 kHz mono여야 합니다")
    return duration


def validate_output_profile(probe: dict[str, Any]) -> None:
    validate_source_profile(probe)
    subtitles = _streams(probe, "subtitle")
    if len(subtitles) != 1 or subtitles[0].get("codec_name") != "subrip":
        raise SliceError("soft-sub output에는 subrip subtitle stream이 정확히 1개여야 합니다")


def _is_filesystem_root(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    return resolved == Path(resolved.anchor)


def _require_new(paths: Sequence[Path]) -> None:
    existing = [os.fspath(path) for path in paths if path.exists()]
    if existing:
        raise SliceError("기존 파일을 덮어쓰지 않습니다: " + ", ".join(existing))


def plan_paths(args: argparse.Namespace, environ: dict[str, str]) -> SlicePaths:
    raw_staging = environ.get(STAGING_ENV)
    if raw_staging is None or not raw_staging.strip():
        raise SliceError(f"{STAGING_ENV}를 비어 있지 않은 로컬 staging 경로로 설정하세요")

    source = Path(args.input).expanduser().resolve(strict=False)
    work_dir = Path(args.work_dir).expanduser().resolve(strict=False)
    staging_dir = Path(raw_staging).expanduser().resolve(strict=False)
    if _is_filesystem_root(work_dir) or _is_filesystem_root(staging_dir):
        raise SliceError("work/staging 경로로 filesystem root를 사용할 수 없습니다")
    if work_dir == staging_dir:
        raise SliceError("work와 staging은 서로 다른 디렉터리여야 합니다")
    if not source.is_file() or source.stat().st_size == 0:
        raise SliceError("입력은 존재하는 non-empty 일반 파일이어야 합니다")
    if work_dir.exists() and not work_dir.is_dir():
        raise SliceError("work 경로가 디렉터리가 아닙니다")
    if staging_dir.exists() and not staging_dir.is_dir():
        raise SliceError("staging 경로가 디렉터리가 아닙니다")

    stem = source.stem
    output = work_dir / f"{stem}-softsub.mkv"
    extracted = work_dir / f"{stem}.extracted.srt"
    report = work_dir / f"{stem}.verify.json"
    export = staging_dir / output.name
    if args.generate_fixture_srt:
        srt = work_dir / f"{stem}.generated.srt"
        generated = True
    else:
        srt = Path(args.srt).expanduser().resolve(strict=False)
        generated = False
        if not srt.is_file() or srt.stat().st_size == 0:
            raise SliceError("--srt는 존재하는 non-empty 일반 파일이어야 합니다")

    if source in {output, extracted, report, export, srt}:
        raise SliceError("입력과 산출물 경로가 충돌합니다")
    planned = [output, extracted, report, export]
    if generated:
        planned.append(srt)
    _require_new(planned)
    return SlicePaths(source, work_dir, staging_dir, srt, output, extracted, report, export, generated)


def _partial_path(target: Path) -> Path:
    suffix = "".join(target.suffixes)
    base = target.name[: -len(suffix)] if suffix else target.name
    return target.parent / f".{base}.partial-{uuid.uuid4().hex}{suffix}"


def _promote_new(partial: Path, target: Path) -> None:
    try:
        os.link(partial, target)
    except FileExistsError as exc:
        raise SliceError(f"경쟁 실행이 만든 기존 파일을 덮어쓰지 않습니다: {target}") from exc
    except OSError as exc:
        raise SliceError(
            f"안전한 no-replace 승격을 지원하지 않는 filesystem입니다: {target}: {exc}"
        ) from exc
    partial.unlink()


def _write_new_bytes(target: Path, data: bytes) -> None:
    partial = _partial_path(target)
    with partial.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _promote_new(partial, target)


def _copy_new_verified(source: Path, target: Path, expected_hash: str) -> str:
    partial = _partial_path(target)
    with source.open("rb") as reader, partial.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    copied_hash = sha256_path(partial)
    if copied_hash != expected_hash:
        raise SliceError("staging partial copy의 SHA-256이 output과 다릅니다")
    _promote_new(partial, target)
    return copied_hash


def _tool_version(binary: str) -> str:
    return _run([binary, "-version"], "tool-version").stdout.splitlines()[0]


def _probe_summary(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "duration_seconds": _duration(probe),
        "format_name": probe.get("format", {}).get("format_name"),
        "streams": [
            {
                key: stream.get(key)
                for key in (
                    "index",
                    "codec_type",
                    "codec_name",
                    "width",
                    "height",
                    "r_frame_rate",
                    "sample_rate",
                    "channels",
                )
                if stream.get(key) is not None
            }
            for stream in probe.get("streams", [])
        ],
    }


def _write_failure(paths: SlicePaths, phase: str, error: BaseException) -> Path | None:
    if not paths.work_dir.exists():
        return None
    failure = paths.work_dir / f"{paths.source.stem}.failure-{uuid.uuid4().hex}.json"
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "phase": phase,
        "error_type": type(error).__name__,
        "message": str(error),
    }
    if isinstance(error, CommandError):
        payload.update(
            {
                "command": error.command,
                "returncode": error.returncode,
                "stderr": error.stderr,
            }
        )
    if isinstance(error, VerificationError):
        payload["details"] = error.details
    _write_new_bytes(
        failure,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return failure


def execute_slice(
    paths: SlicePaths,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    phase = "prepare"
    paths.work_dir.mkdir(parents=True, exist_ok=True)
    try:
        source_hash_before = sha256_path(paths.source)
        phase = "probe-source"
        source_probe = probe_media(paths.source, ffprobe)
        duration = validate_source_profile(source_probe)

        phase = "prepare-srt"
        if paths.generated:
            if len(GENERATED_SRT) != 98 or hashlib.sha256(GENERATED_SRT).hexdigest() != GENERATED_SRT_SHA256:
                raise SliceError("내장 fixture SRT 상수가 Gate S 바이트 규약과 다릅니다")
            _write_new_bytes(paths.srt, GENERATED_SRT)
        srt_bytes = paths.srt.read_bytes()
        cues = parse_srt(srt_bytes, duration)

        phase = "soft-sub"
        output_partial = _partial_path(paths.output)
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-i",
                os.fspath(paths.source),
                "-i",
                os.fspath(paths.srt),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-map",
                "1:0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "srt",
                "-metadata:s:s:0",
                "title=fixture captions",
                "-metadata",
                "creation_time=1970-01-01T00:00:00Z",
                "-fflags",
                "+bitexact",
                os.fspath(output_partial),
            ],
            phase,
        )

        phase = "verify-output-profile"
        output_probe = probe_media(output_partial, ffprobe)
        validate_output_profile(output_probe)

        phase = "extract-srt"
        extracted_partial = _partial_path(paths.extracted)
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-i",
                os.fspath(output_partial),
                "-map",
                "0:s:0",
                "-c:s",
                "srt",
                os.fspath(extracted_partial),
            ],
            phase,
        )

        phase = "verify-srt"
        extracted_bytes = extracted_partial.read_bytes()
        canonical_equal = canonical_srt(srt_bytes, duration) == canonical_srt(
            extracted_bytes, duration
        )
        raw_equal = srt_bytes == extracted_bytes
        if not canonical_equal:
            raise VerificationError(
                "subtitle canonical round-trip이 일치하지 않습니다",
                canonical_equal=False,
                raw_equal=raw_equal,
                classification="cue_mismatch",
            )
        if not raw_equal:
            raise VerificationError(
                "subtitle 의미는 같지만 raw bytes가 다릅니다(byte_shape_violation)",
                canonical_equal=True,
                raw_equal=False,
                classification="byte_shape_violation",
            )

        phase = "verify-source-unchanged"
        source_hash_after = sha256_path(paths.source)
        if source_hash_after != source_hash_before:
            raise SliceError("원본 입력 SHA-256이 실행 중 변경되었습니다")

        phase = "promote-local-artifacts"
        _promote_new(output_partial, paths.output)
        _promote_new(extracted_partial, paths.extracted)
        output_hash = sha256_path(paths.output)

        phase = "staging-export"
        paths.staging_dir.mkdir(parents=True, exist_ok=True)
        export_hash = _copy_new_verified(paths.output, paths.export, output_hash)

        phase = "final-source-check"
        final_source_hash = sha256_path(paths.source)
        if final_source_hash != source_hash_before:
            raise SliceError("staging export 뒤 원본 입력 SHA-256이 변경되었습니다")

        phase = "write-report"
        report = {
            "schema_version": SCHEMA_VERSION,
            "status": "complete",
            "input": {
                "path": os.fspath(paths.source),
                "size_bytes": paths.source.stat().st_size,
                "sha256_before": source_hash_before,
                "sha256_after": final_source_hash,
                "unchanged": True,
                "probe": _probe_summary(source_probe),
            },
            "subtitle": {
                "path": os.fspath(paths.srt),
                "generated": paths.generated,
                "size_bytes": len(srt_bytes),
                "sha256": hashlib.sha256(srt_bytes).hexdigest(),
                "cue_count": len(cues),
                "canonical_equal": canonical_equal,
                "raw_equal": raw_equal,
            },
            "output": {
                "path": os.fspath(paths.output),
                "size_bytes": paths.output.stat().st_size,
                "sha256": output_hash,
                "probe": _probe_summary(output_probe),
            },
            "export": {
                "path": os.fspath(paths.export),
                "size_bytes": paths.export.stat().st_size,
                "sha256": export_hash,
                "matches_output": export_hash == output_hash,
            },
            "tools": {
                "ffmpeg": _tool_version(ffmpeg),
                "ffprobe": _tool_version(ffprobe),
            },
        }
        _write_new_bytes(
            paths.report,
            (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        return report
    except BaseException as exc:
        try:
            _write_failure(paths, phase, exc)
        except BaseException as failure_error:
            print(f"실패 기록 작성도 실패했습니다: {failure_error}", file=sys.stderr)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gate S 합성 media plumbing vertical slice를 실행합니다."
    )
    parser.add_argument("--input", required=True, help="6초 합성 fixture MKV")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--srt", help="기존 UTF-8 SRT")
    group.add_argument(
        "--generate-fixture-srt",
        action="store_true",
        help="Gate S의 정확한 98-byte SRT를 생성",
    )
    parser.add_argument("--work-dir", required=True, help="새 로컬 산출물 디렉터리")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        paths = plan_paths(args, dict(os.environ))
        report = execute_slice(paths, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    except SliceError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
