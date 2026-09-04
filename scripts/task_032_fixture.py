"""Run TASK-032 contract and controlled-resume fixtures in a temporary root."""

from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from media_clarity.asr_screen.fixtures import build_contract_fixture, run_recovery_fixture


def main() -> int:
    with TemporaryDirectory(prefix="mcs-task032-fixture-") as temporary:
        root = Path(temporary)
        contract = build_contract_fixture(root / "contract")
        recovery = run_recovery_fixture(root / "recovery")
    print(
        "TASK-032 synthetic fixtures passed: "
        f"contract={contract['kind']}, candidates={len(recovery['candidates'])}, "
        "interruptions=3, target_windows_compatibility=not_evaluated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
