#!/usr/bin/env python3
"""Contract tests for the frozen, manual PR15 package workflow."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/pr15-exact-package.yml"
SHA = "774894c4eba7b646beafb38313fe0dc73cfb4671"


def workflow_text():
    assert WORKFLOW.is_file(), f"workflow missing: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def powershell_blocks(text):
    lines = text.splitlines()
    blocks = []
    for index, line in enumerate(lines):
        if line.strip() != "shell: pwsh" or index + 1 >= len(lines) or not lines[index + 1].strip().startswith("run:"):
            continue
        body = []
        for following in lines[index + 2:]:
            if following.startswith("          "):
                body.append(following[10:])
            else:
                break
        blocks.append("\n".join(body) + "\n")
    return blocks


def validate_target_invariants(text):
    """Small mutation-resistant core for the safety-critical contract."""
    assert f"ref: {SHA}" in text
    assert "ctest --preset windows-portable-x64" in text
    assert "python tools/phase4/test-import-profile.py" in text
    assert "python tools/release/test-alpha.py" in text
    assert "matrix:" not in text
    assert "workflow_call:" not in text
    assert re.search(r"(?m)^\s*retention-days: 3\s*$", text)
    assert not re.search(r"(?i)\bsecrets\.|\beval\s*\(", text)


class PR15PackageWorkflowContract(unittest.TestCase):
    def test_embedded_metadata_requires_literal_sha_and_boolean_false(self):
        import json
        block = next(b for b in powershell_blocks(workflow_text()) if 'foreach ($metadata' in b)
        guard = block[block.index('foreach ($metadata'):block.index('$bindingDir =')]
        cases = [('valid', SHA, False, 0), ('numeric false', SHA, 0, 1), ('uppercase SHA', SHA.upper(), False, 1)]
        for label, source, dirty, expected in cases:
            model = json.dumps({'source_commit': source, 'tracked_changes': dirty})
            script = "$ErrorActionPreference='Stop'; $buildInfo = '" + model + "' | ConvertFrom-Json; $manifest=$buildInfo;\n" + guard
            with self.subTest(case=label):
                p = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True, text=True)
                self.assertEqual(p.returncode, expected, p.stdout + p.stderr)

    def test_git_failures_and_dirty_status_are_rejected(self):
        blocks = [b for b in powershell_blocks(workflow_text()) if 'git status --porcelain' in b]
        for case in ('head_error', 'status_error', 'dirty_one', 'dirty_many'):
            mock_git = '''
function git {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Values)
    $global:LASTEXITCODE = 0
    if ($Values[0] -eq 'rev-parse') {
        if ('CASE' -eq 'head_error') { $global:LASTEXITCODE = 128 }
        '774894c4eba7b646beafb38313fe0dc73cfb4671'
    } else {
        if ('CASE' -eq 'status_error') { $global:LASTEXITCODE = 128 }
        if ('CASE' -eq 'dirty_one') { ' M source.cpp' }
        if ('CASE' -eq 'dirty_many') { ' M source.cpp'; ' M other.cpp' }
    }
}
'''.replace('CASE', case)
            for block in blocks:
                with self.subTest(case=case, block=block):
                    p = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', mock_git + block], capture_output=True, text=True)
                    self.assertNotEqual(p.returncode, 0, f'accepted {case}')

    def test_clean_git_output_is_accepted_by_real_powershell(self):
        blocks = [b for b in powershell_blocks(workflow_text()) if 'git status --porcelain' in b]
        self.assertEqual(len(blocks), 2)
        mock_git = '''
function git {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Values)
    $global:LASTEXITCODE = 0
    if ($Values[0] -eq 'rev-parse') { '774894c4eba7b646beafb38313fe0dc73cfb4671' }
}
'''
        for block in blocks:
            with self.subTest(block=block):
                result = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', mock_git + block], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_manual_single_qt6_package_contract(self):
        text = workflow_text()
        validate_target_invariants(text)
        self.assertIn("name: PR15 exact Qt6 Windows package", text)
        self.assertIn("on:\n  push:\n    paths:\n      - .github/workflows/pr15-exact-package.yml\n      - tools/player-inspection/test_pr15_package_workflow.py", text)
        self.assertIn("workflow_dispatch:\n    inputs:\n      build_package:\n        description:", text)
        self.assertIn("type: boolean", text)
        self.assertIn("required: true", text)
        self.assertIn("default: false", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("workflow_call:", text)
        self.assertNotIn("matrix:", text)
        self.assertNotRegex(text, r"(?im)qt\s*5|Qt5|^\s*matrix:")

        self.assertRegex(text, r"(?ms)permissions:\n\s+contents: read\n\s*$")
        checkout_refs = re.findall(r"(?m)^\s+ref:\s*(.+)$", text)
        self.assertIn(SHA, text)
        self.assertTrue(any(SHA in ref for ref in checkout_refs))
        self.assertFalse(any("github.sha" in ref or "GITHUB_SHA" in ref for ref in checkout_refs))
        self.assertEqual(text.count("persist-credentials: false"), 2)
        self.assertNotRegex(text, r"(?i)cherry-pick|git\s+(apply|rebase|reset)\b|git\s+checkout\s+-")

        self.assertIn("runs-on: ubuntu-latest", text)
        self.assertIn("python tools/player-inspection/test_pr15_package_workflow.py", text)
        self.assertIn("runs-on: windows-2022", text)
        self.assertIn("needs: config", text)
        self.assertRegex(text, r"if:.*github\.event_name == 'workflow_dispatch'.*inputs\.build_package == true")
        self.assertIn("cmake --preset windows-portable-x64", text)
        for command in (
            "cmake --build --preset windows-portable-x64",
            "ctest --preset windows-portable-x64",
            "python tools/phase4/test-import-profile.py",
            "python tools/release/test-alpha.py",
            "python tools/phase2/package-windows.py",
            "python tools/phase2/verify-package.py",
            "--headless-audio",
            "--trace-startup --repeat 3",
            "--registry-fallback \"$mode\"",
            "tools/phase3/build-format-fixtures.py",
            "--format-fixtures .phase4/build/format-fixtures",
            "experiments/qt6-skins",
            "ctest --test-dir .phase3/skin-probe",
            "pacman -Q > .phase4/build/toolchain.txt",
        ):
            self.assertIn(command, text)
        self.assertIn("for mode in missing corrupt changed-plugin; do", text)
        self.assertEqual(text.count("--registry-fallback \"$mode\""), 1)
        self.assertIn("NULLOY_GIT_EXECUTABLE", text)
        self.assertIn("Get-Command git", text)

        for marker in (
            "build-info.json",
            "package-manifest.json",
            'source_commit',
            'tracked_changes',
            'product_source_sha',
            'workflow_source_sha = "${{ github.sha }}"',
            "source_assertion: PASS",
            "source_assertion=PASS",
            "RUNNER_TEMP",
            "acceptance-binding.json",
        ):
            self.assertIn(marker, text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertEqual(text.count("actions/upload-artifact@v4"), 2)
        self.assertIn("retention-days: 3", text)
        self.assertIn("retention-days: 7", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertIn("steps.provenance.outputs.source_assertion == 'PASS'", text)
        self.assertIn("${{ runner.temp }}/pr15-exact-package-${{ github.run_id }}/acceptance-binding.json", text)
        self.assertIn("if: always()", text)
        self.assertNotRegex(text, r"(?i)actions/(create-release|cache)|\bgh\s+(release|api)\b|\b(cleanup|delete)\b")

    def test_negative_mutations_are_rejected(self):
        text = workflow_text()
        mutations = (
            ("source SHA", text.replace(f"ref: {SHA}", "ref: " + "0" * 40)),
            ("build gate", text.replace("ctest --preset windows-portable-x64", "ctest --preset removed")),
            ("matrix", text + "\n    strategy:\n      matrix:\n        qt: [6]\n"),
            ("retention", text.replace("retention-days: 3", "retention-days: 30")),
            ("reusable", text + "\n  workflow_call:\n"),
            ("secret eval", text + "\n# eval(secrets.UNSAFE)\n"),
        )
        for label, mutated in mutations:
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    validate_target_invariants(mutated)

    def test_powerShell_payloads_are_parseable(self):
        text = workflow_text()
        blocks = powershell_blocks(text)
        self.assertGreaterEqual(len(blocks), 2)
        pwsh = shutil.which("pwsh")
        self.assertIsNotNone(pwsh, "pwsh is required for workflow payload syntax checks")
        with tempfile.TemporaryDirectory(prefix="pr15-pwsh-") as directory:
            for number, block in enumerate(blocks):
                path = Path(directory) / f"payload-{number}.ps1"
                block = re.sub(r"\$\{\{.*?\}\}", "EXPRESSION", block)
                path.write_text(block, encoding="utf-8")
                parser = (
                    "$tokens=$null; $errors=$null; "
                    f"[System.Management.Automation.Language.Parser]::ParseFile('{path.as_posix()}', "
                    "[ref]$tokens, [ref]$errors) > $null; "
                    "if ($errors.Count) { $errors | % Message; exit 1 }"
                )
                result = subprocess.run(
                    [pwsh, "-NoProfile", "-NonInteractive", "-Command", parser],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
