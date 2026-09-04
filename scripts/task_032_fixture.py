"""Run TASK-032 contract and controlled-resume fixtures in a temporary root."""

from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from media_clarity.asr_screen.fixtures import (
    build_contract_fixture,
    build_preparation_fixture,
    run_recovery_fixture,
)
from media_clarity.asr_screen.preflight import DEFAULT_PREFLIGHT_PATH
from media_clarity.schema_core import load_strict


def main() -> int:
    with TemporaryDirectory(prefix="mcs-task032-fixture-") as temporary:
        root = Path(temporary)
        contract = build_contract_fixture(root / "contract")
        preparation = build_preparation_fixture(
            root / "preparation", load_strict(DEFAULT_PREFLIGHT_PATH)
        )
        recovery = run_recovery_fixture(root / "recovery")
    print(
        "TASK-032 synthetic fixtures passed: "
        f"contract={contract['kind']}, preparation={preparation['preflight']['status']}, "
        f"candidates={len(recovery['candidates'])}, "
        "interruptions=3, target_windows_compatibility=not_evaluated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
