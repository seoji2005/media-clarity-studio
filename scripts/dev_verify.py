"""make 없이 실행하는 개발 검증. 제품 출시·모델 품질 판정을 대신하지 않는다."""
from __future__ import annotations

import argparse
import compileall
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest


class VerificationInputError(ValueError):
    """실행 전에 고쳐야 하는 경로·검증 범위 오류."""


def run_checks(root: Path, *, full: bool, test_files: list[str]) -> int:
    """신뢰하는 checkout에서 실행한다. 테스트 코드를 격리하는 sandbox가 아니다."""
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        raise VerificationInputError("tests 디렉터리가 없습니다")
    names = list(dict.fromkeys(test_files))
    for name in names:
        if not re.fullmatch(r"test_[A-Za-z0-9_]+\.py", name):
            raise VerificationInputError("--test에는 tests 아래의 정확한 test_*.py 파일명만 지정하세요")
        path = tests_dir / name
        if not path.is_file() or path.is_symlink():
            raise VerificationInputError(f"테스트 파일이 없거나 symlink입니다: {name}")
    if not full and not names:
        raise VerificationInputError("focused 검증에는 테스트 파일이 필요합니다")
    smoke = root / "scripts" / "smoke_task_022.py"
    if full:
        for directory in ("src", "tests", "scripts"):
            if not (root / directory).is_dir():
                raise VerificationInputError(f"전체 검증 경로가 없습니다: {directory}")
        if not smoke.is_file():
            raise VerificationInputError("전체 검증에는 scripts/smoke_task_022.py가 필요합니다")
        for directory in ("src", "tests", "scripts"):
            if not compileall.compile_dir(root / directory, quiet=1):
                print("E_STATIC: 문법 검사가 실패했습니다", file=sys.stderr)
                return 1
    sys.path.insert(0, str(root / "src"))
    os.chdir(root)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for pattern in (["test_*.py"] if full else names):
        suite.addTests(loader.discover(str(tests_dir), pattern=pattern))
    if suite.countTestCases() == 0:
        print("E_EMPTY_TESTS: 발견한 테스트가 0개이므로 성공으로 처리하지 않습니다", file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        print("E_TESTS: 테스트가 실패했습니다", file=sys.stderr)
        return 1
    if result.testsRun == len(result.skipped):
        print("E_ALL_SKIPPED: 모든 테스트가 skip되어 실행 증거가 없습니다", file=sys.stderr)
        return 2
    if full:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        env["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(smoke)], cwd=root, env=env, check=False
        )
        if completed.returncode != 0:
            print("E_SMOKE: TASK-022 smoke가 실패했습니다", file=sys.stderr)
            return 1
    mode = "full" if full else "focused"
    print(f"검증 통과: scope={mode}, tests={result.testsRun}, skipped={len(result.skipped)}")
    print("이 결과는 개발 검증이며 실제 ASR·영상 품질·Windows/RTX 출시 적합성 판정이 아닙니다")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--full", action="store_true", help="compile + 전체 unittest + TASK-022 smoke")
    scope.add_argument("--test", action="append", default=[], help="정확한 테스트 파일명; 반복 지정 가능")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        return run_checks(root, full=args.full, test_files=args.test)
    except (VerificationInputError, OSError, ImportError) as error:
        print(f"E_VERIFY_INPUT: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
