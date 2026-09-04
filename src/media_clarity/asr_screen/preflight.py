"""CLI and honest Work-CPU environment receipt for TASK-032."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
from pathlib import Path
from typing import Sequence

from media_clarity.artifact_store import content_hash_of, utc_now
from media_clarity.job_runtime import canonical_json_bytes
from media_clarity.schema_core import REPO_ROOT, JsonInputError, load_strict

from .contracts import readiness_findings, validate_preflight, validate_work_cpu_receipt


DEFAULT_PREFLIGHT_PATH = REPO_ROOT / "config" / "task-032-preflight.json"


def _total_memory_bytes() -> int:
    page_size = os.sysconf("SC_PAGE_SIZE")
    page_count = os.sysconf("SC_PHYS_PAGES")
    total = int(page_size) * int(page_count)
    if total < 1:
        raise RuntimeError("host physical memory could not be measured")
    return total


def probe_implementation_hash() -> str:
    payload = Path(__file__).read_bytes()
    return content_hash_of(hashlib.sha256(payload).hexdigest())


def probe_work_cpu() -> dict[str, object]:
    logical_count = os.cpu_count()
    if logical_count is None or logical_count < 1:
        raise RuntimeError("host logical CPU count could not be measured")
    receipt: dict[str, object] = {
        "schema_version": "1.0.0",
        "kind": "AsrScreenWorkCpuReceipt/v1",
        "captured_at": utc_now(),
        "probe_implementation_hash": probe_implementation_hash(),
        "host": {
            "os": platform.system().lower(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        "python": {
            "implementation": sys.implementation.name,
            "version": platform.python_version(),
        },
        "cpu": {"logical_count": logical_count},
        "memory": {"total_bytes": _total_memory_bytes()},
        "claims": {
            "candidate_output_generated": False,
            "paid_cost_usd": 0,
            "target_windows_compatibility": "not_evaluated",
            "target_gpu_compatibility": "not_evaluated",
        },
    }
    findings = validate_work_cpu_receipt(receipt)
    if findings:
        raise AssertionError(findings[0].as_line())
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-032 free Work-CPU preflight")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate the checked-in preparation document")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_PREFLIGHT_PATH)
    validate.add_argument("--require-ready", action="store_true")
    subparsers.add_parser("probe-work-cpu", help="print a non-persistent, non-GPU compatibility receipt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "probe-work-cpu":
        sys.stdout.buffer.write(canonical_json_bytes(probe_work_cpu()) + b"\n")
        return 0
    try:
        document = load_strict(args.manifest)
    except (OSError, JsonInputError, UnicodeDecodeError) as error:
        print(f"E_JSON preflight {type(error).__name__}", file=sys.stderr)
        return 2
    findings = validate_preflight(document)
    if not findings and args.require_ready:
        findings = readiness_findings(document)
    if findings:
        for finding in findings:
            print(finding.as_line(), file=sys.stderr)
        return 1
    print(f"valid TASK-032 preflight: status={document['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
