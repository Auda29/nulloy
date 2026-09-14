"""The focus diagnostic must run before, not replace, context acceptance."""
from pathlib import Path
import unittest


class FocusWorkflowTests(unittest.TestCase):
    def test_focus_diagnostic_is_isolated_before_context_gate(self):
        text = (Path(__file__).resolve().parents[2] / '.github/workflows/player-inspection.yml').read_text()
        steps = text.split('      - ')
        matching = [s for s in steps if '--bounded-focus-diagnostic' in s]
        self.assertEqual(len(matching), 1, 'one isolated focus diagnostic step required')
        step = matching[0]
        self.assertIn('--output evidence-focus-diagnostic', step)
        self.assertIn('--source-sha 9e1b3f060e649a64c698b2a5981dbfca1d741b84', step)
        self.assertIn('--archive-sha256 5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833', step)
        self.assertIn('exit $LASTEXITCODE', step)
        self.assertIn('if ($packages.Count -ne 1)', step)
        for other in ('--bounded-context-menu', '--bounded-read-only', '--inspect-context-menu', '--allow-owned-pointer-input'):
            self.assertNotIn(other, step)
        self.assertLess(text.index('--bounded-focus-diagnostic'), text.index('--bounded-context-menu'))
        upload = next(s for s in steps if 'uses: actions/upload-artifact@' in s)
        self.assertIn('if: always()', upload)
        self.assertIn('            evidence-focus-diagnostic/', upload)
        self.assertIn('retention-days: 14', upload)
        self.assertNotIn('continue-on-error', text)


if __name__ == '__main__':
    unittest.main()
