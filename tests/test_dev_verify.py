"""새 검증 진입점의 CLI 회귀 검사. 실제 모델·GPU·네트워크를 사용하지 않는다."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "dev_verify.py"
PASSING = "import unittest\nclass Probe(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n"


class DevVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "한글 checkout"
        for directory in ("scripts", "tests", "src"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUNNER, self.root / "scripts" / "dev_verify.py")
        self.write("tests/test_probe.py", PASSING)
        self.write("scripts/smoke_task_022.py", "print('FIXTURE_SMOKE')\n")

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def run_cli(self, *args):
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(self.root / "scripts" / "dev_verify.py"), *args],
            cwd=self.temp.name, env=env, capture_output=True, text=True,
            encoding="utf-8", timeout=20, check=False,
        )

    def test_focused_pass_and_no_smoke(self):
        result = self.run_cli("--test", "test_probe.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scope=focused, tests=1", result.stdout)
        self.assertNotIn("FIXTURE_SMOKE", result.stdout)

    def test_full_includes_smoke(self):
        result = self.run_cli("--full")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FIXTURE_SMOKE", result.stdout)
        self.assertIn("scope=full", result.stdout)

    def test_duplicate_selection_does_not_duplicate_execution(self):
        result = self.run_cli("--test", "test_probe.py", "--test", "test_probe.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tests=1", result.stdout)

    def test_multiple_exact_files(self):
        self.write("tests/test_other.py", PASSING)
        result = self.run_cli("--test", "test_probe.py", "--test", "test_other.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tests=2", result.stdout)

    def test_missing_test_and_unsafe_patterns_fail(self):
        for name in ("test_missing.py", "../test_probe.py", "test_*.py", "test_probe.py;echo"):
            with self.subTest(name=name):
                result = self.run_cli("--test", name)
                self.assertEqual(result.returncode, 2)
                self.assertIn("E_VERIFY_INPUT", result.stderr)

    def test_empty_selected_file_is_not_success(self):
        self.write("tests/test_probe.py", "# no test\n")
        result = self.run_cli("--test", "test_probe.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("E_EMPTY_TESTS", result.stderr)

    def test_empty_full_suite_is_not_success(self):
        self.write("tests/test_probe.py", "# no test\n")
        result = self.run_cli("--full")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("FIXTURE_SMOKE", result.stdout)

    def test_all_skipped_is_not_success(self):
        self.write("tests/test_probe.py", PASSING.replace("self.assertTrue(True)", "self.skipTest('no hardware')"))
        result = self.run_cli("--test", "test_probe.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("E_ALL_SKIPPED", result.stderr)

    def test_failure_blocks_smoke(self):
        self.write("tests/test_probe.py", PASSING.replace("self.assertTrue(True)", "self.assertTrue(False)"))
        result = self.run_cli("--full")
        self.assertEqual(result.returncode, 1)
        self.assertIn("E_TESTS", result.stderr)
        self.assertNotIn("FIXTURE_SMOKE", result.stdout)

    def test_import_failure_is_not_success(self):
        self.write("tests/test_probe.py", "raise RuntimeError('fixture import failure')\n")
        result = self.run_cli("--test", "test_probe.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("E_TESTS", result.stderr)

    def test_syntax_failure_blocks_tests(self):
        self.write("src/broken.py", "def broken(\n")
        result = self.run_cli("--full")
        self.assertEqual(result.returncode, 1)
        self.assertIn("E_STATIC", result.stderr)
        self.assertNotIn("FIXTURE_SMOKE", result.stdout)

    def test_missing_smoke_is_not_success(self):
        (self.root / "scripts" / "smoke_task_022.py").unlink()
        result = self.run_cli("--full")
        self.assertEqual(result.returncode, 2)
        self.assertIn("E_VERIFY_INPUT", result.stderr)

    def test_smoke_failure_is_not_success(self):
        self.write("scripts/smoke_task_022.py", "raise SystemExit(7)\n")
        result = self.run_cli("--full")
        self.assertEqual(result.returncode, 1)
        self.assertIn("E_SMOKE", result.stderr)
        self.assertNotIn("검증 통과", result.stdout)

    def test_src_import_works_outside_repo_cwd(self):
        self.write("src/local_probe.py", "VALUE = 1\n")
        self.write("tests/test_probe.py", PASSING.replace("import unittest", "import unittest\nimport local_probe"))
        result = self.run_cli("--test", "test_probe.py")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scope_is_required_and_exclusive(self):
        for args in ((), ("--full", "--test", "test_probe.py")):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)


if __name__ == "__main__":
    unittest.main()
