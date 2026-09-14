"""Contract tests for the manual PR15 bounded characterization workflow."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/pr15-player-characterize.yml"
SOURCE_SHA = "774894c4eba7b646beafb38313fe0dc73cfb4671"
RUN_ID = "34878321503"
ARTIFACT_ID = "10362585867"
OUTER_SHA = "ce1d7aad25d939902669e0150ec81a38befe7031644c47b01b2cde0b0ff185a0"
INNER_SHA = "23b3e646ac0f8a69d4d8e434c4441a0b3d06101f56940211caba28b2385f05b0"


def workflow_text():
    assert WORKFLOW.is_file(), f"workflow missing: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def powershell_blocks(text):
    lines = text.splitlines()
    blocks = []
    for index, line in enumerate(lines):
        if line.strip() != "shell: pwsh" or index + 1 >= len(lines):
            continue
        if not lines[index + 1].strip().startswith("run:"):
            continue
        body = []
        for following in lines[index + 2:]:
            if following.startswith("          "):
                body.append(following[10:])
            else:
                break
        blocks.append("\n".join(body) + "\n")
    return blocks


class PR15CharacterizationWorkflowContract(unittest.TestCase):
    def test_registration_push_can_only_run_contract_tests(self):
        text = workflow_text()
        self.assertIn("  push:\n    branches: ['test/windows-player-inspection']", text)
        self.assertIn("'.github/workflows/pr15-player-characterize.yml'", text)
        self.assertIn("'tools/player-inspection/test_pr15_characterization_workflow.py'", text)
        jobs = text.split('jobs:\n', 1)[1]
        self.assertEqual(re.findall(r'(?m)^  ([a-z_-]+):', jobs), ['contract', 'characterize'])
        contract, characterize = jobs.split('  characterize:', 1)
        self.assertIn('runs-on: ubuntu-latest', contract)
        self.assertIn('test_pr15_characterization_workflow.py', contract)
        for forbidden in ('windows-', 'download-artifact', 'upload-artifact', 'inspect_player.py', 'secrets.'):
            self.assertNotIn(forbidden, contract)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.characterize_package == true", characterize)
        self.assertIn('needs: contract', characterize)

    def test_is_manual_opt_in_and_has_no_build_or_publication_route(self):
        text = workflow_text()
        self.assertIn("name: PR15 bounded player characterization", text)
        self.assertIn("on:\n  workflow_dispatch:\n    inputs:\n      characterize_package:", text)
        self.assertIn("type: boolean", text)
        self.assertIn("default: false", text)
        self.assertNotRegex(text, r"(?m)^\s+(pull_request|schedule|workflow_call):")
        self.assertNotIn("package-windows", text)
        self.assertNotIn("actions/upload-artifact@v4\n        with:\n          name: Nulloy", text)
        self.assertNotRegex(text, r"(?i)create-release|gh\s+(release|api)\s+upload|Invoke-WebRequest.*zip")

    def test_routes_only_explicit_true_to_windows_and_pins_exact_artifact(self):
        text = workflow_text()
        self.assertIn("runs-on: windows-2022", text)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.characterize_package == true", text)
        for literal in (SOURCE_SHA, RUN_ID, ARTIFACT_ID, OUTER_SHA, INNER_SHA):
            self.assertIn(literal, text)
        self.assertIn("artifact-ids: 10362585867", text)
        self.assertIn("run-id: 34878321503", text)
        self.assertIn("repository: Auda29/nulloy", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertNotIn("github.event.inputs", text)
        self.assertNotRegex(text, r"(?m)^\s*[-a-zA-Z_]+:\s*\$\{\{\s*inputs\.")

    def test_helper_compatibility_precedes_two_separate_bounded_modes(self):
        text = workflow_text()
        self.assertIn("extract_and_validate", text)
        helper = text.index("extract_and_validate")
        readonly = text.index("--bounded-read-only")
        context = text.index("--bounded-context-menu")
        self.assertLess(helper, readonly)
        self.assertLess(readonly, context)
        self.assertIn("--package $package.FullName", text)
        self.assertIn("--output evidence-bounded-read-only", text)
        self.assertIn("--output evidence-bounded-context-menu", text)
        self.assertEqual(text.count("--bounded-read-only"), 1)
        self.assertEqual(text.count("--bounded-context-menu"), 1)
        for forbidden in (
            "--inspect-context-menu",
            "--allow-owned-pointer-input",
            "--bounded-focus-diagnostic",
            "trash-probe",
            "Move To Trash",
            "Remove From Playlist",
            "--package-upload",
            "retention-days: 30",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("retention-days: 7", text)

    def test_fixed_dependencies_and_evidence_only_upload_are_explicit(self):
        text = workflow_text()
        for dependency in (
            "pywinauto==0.6.9",
            "psutil==7.0.0",
            "Pillow==11.1.0",
        ):
            self.assertIn(dependency, text)
        self.assertEqual(text.count("actions/upload-artifact@v4"), 1)
        upload = next(step for step in text.split("      - ") if "actions/upload-artifact@v4" in step)
        self.assertIn("if: always()", upload)
        self.assertIn("retention-days: 7", upload)
        self.assertIn("evidence-bounded-read-only/", upload)
        self.assertIn("evidence-bounded-context-menu/", upload)
        self.assertNotIn("package-archive/", upload)

    def test_powershell_payloads_are_parseable(self):
        blocks = powershell_blocks(workflow_text())
        self.assertGreaterEqual(len(blocks), 3)
        pwsh = shutil.which("pwsh")
        self.assertIsNotNone(pwsh, "pwsh is required for workflow payload syntax checks")
        with tempfile.TemporaryDirectory(prefix="pr15-characterize-pwsh-") as directory:
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
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
