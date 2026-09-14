"""Guard the exact native bounded-context entry point and evidence path."""
from pathlib import Path
import unittest


class ContextWorkflowTests(unittest.TestCase):
    def test_native_context_step_is_pinned_and_preserves_evidence(self):
        workflow = Path(__file__).resolve().parents[2] / '.github/workflows/player-inspection.yml'
        text = workflow.read_text(encoding='utf-8')
        steps = text.split('      - ')
        matches = [step for step in steps if '--bounded-context-menu' in step]
        self.assertEqual(len(matches), 1, 'one explicit bounded context step must run')
        step = matches[0]
        self.assertIn('shell: pwsh', step)
        self.assertIn('if ($packages.Count -ne 1)', step)
        self.assertIn('--output evidence-bounded-context', step)
        self.assertIn('--source-sha 9e1b3f060e649a64c698b2a5981dbfca1d741b84', step)
        self.assertIn('--archive-sha256 5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833', step)
        self.assertIn('exit $LASTEXITCODE', step)
        for flag in ('--allow-owned-pointer-input', '--inspect-context-menu', '--bounded-read-only'):
            self.assertNotIn(flag, step)
        upload = next(step for step in steps if 'uses: actions/upload-artifact@' in step)
        self.assertIn('if: always()', upload)
        self.assertIn('            evidence-bounded-context/', upload)
        self.assertIn('retention-days: 14', upload)
        self.assertIn('run-id: 34572047079', text)
        self.assertNotIn('continue-on-error', step)


if __name__ == '__main__':
    unittest.main()
