"""Contract tests for the native issue-test runner (no fake C++ results)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import json
import shutil

spec = importlib.util.spec_from_file_location("runner", Path(__file__).with_name("run-native.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerContract(unittest.TestCase):
    def test_discovers_only_numeric_issue_harnesses_in_number_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("255", "11", "helpers", "236"):
                folder = root / "tests" / "upstream" / name
                folder.mkdir(parents=True)
                (folder / "CMakeLists.txt").write_text("# fixture\n")
            (root / "tests" / "upstream" / "129").mkdir()
            self.assertEqual([p.name for p in runner.discover(root)], ["11", "236", "255"])

    def test_absent_test_root_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(runner.discover(Path(temp)), [])

    def test_symlink_harness_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "external"
            target.mkdir()
            (target / "CMakeLists.txt").write_text("# fixture\n")
            tests = root / "tests" / "upstream"
            tests.mkdir(parents=True)
            try:
                (tests / "255").symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            self.assertEqual(runner.discover(root), [])

    def test_steps_are_configure_build_test_with_bounded_parallelism(self):
        steps = runner.commands(Path("tests/upstream/255"), Path("build/255"))
        self.assertEqual(steps[0], ["cmake", "-S", str(Path("tests/upstream/255")), "-B", str(Path("build/255")), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release"])
        self.assertEqual(steps[1], ["cmake", "--build", str(Path("build/255")), "--parallel", "1"])
        self.assertEqual(steps[2], ["ctest", "--test-dir", str(Path("build/255")), "--output-on-failure", "--no-tests=error", "--timeout", "180"])

    @unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja"), "Native runner tools absent")
    def test_reused_output_cannot_execute_deleted_test_registrations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            harness = source / "tests" / "upstream" / "255"
            harness.mkdir(parents=True)
            base = "cmake_minimum_required(VERSION 3.24)\nproject(ReuseFixture NONE)\n"
            registration = "enable_testing()\nadd_test(NAME obsolete COMMAND ${CMAKE_COMMAND} -E true)\n"
            config = harness / "CMakeLists.txt"
            config.write_text(base + registration)
            args = [sys.executable, str(Path(runner.__file__)), "--source", str(source),
                    "--output", str(root / "build")]
            first = subprocess.run(args, capture_output=True, text=True, timeout=60)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            config.write_text(base)
            second = subprocess.run(args, capture_output=True, text=True, timeout=60)
            self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
            results = json.loads((root / "build" / "results.json").read_text())
            self.assertFalse(results[0]["passed"])

    @unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja"), "Native runner tools absent")
    def test_real_ctest_failures_and_empty_tests_are_not_green(self):
        for behavior, expected in (("true", 0), ("false", 1), (None, 1)):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / "source"
                harness = source / "tests" / "upstream" / "255"
                harness.mkdir(parents=True)
                cmake = "cmake_minimum_required(VERSION 3.24)\nproject(RunnerFixture NONE)\nenable_testing()\n"
                if behavior:
                    cmake += "add_test(NAME fixture COMMAND ${CMAKE_COMMAND} -E " + behavior + ")\n"
                (harness / "CMakeLists.txt").write_text(cmake)
                result = subprocess.run([sys.executable, str(Path(runner.__file__)),
                                         "--source", str(source), "--output", str(root / "build")],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                evidence = json.loads((root / "build" / "results.json").read_text())
                self.assertEqual(len(evidence), 1)
                self.assertEqual(evidence[0]["passed"], expected == 0)


if __name__ == "__main__":
    unittest.main()
