"""Native modal discovery is isolated from all player/package/trash actions."""
from pathlib import Path
import unittest


class DiscoveryWorkflowTests(unittest.TestCase):
    def test_linux_qt_runtime_is_installed_before_fixture_tests(self):
        path = Path(__file__).resolve().parents[2] / '.github/workflows/modal-fixture-observe.yml'
        text = path.read_text()
        self.assertIn('sudo apt-get install -y --no-install-recommends libegl1', text)
        self.assertLess(text.index('sudo apt-get install'), text.index('unittest discover'))

    def test_isolated_discovery_keeps_blocked_exit_and_always_uploads(self):
        path = Path(__file__).resolve().parents[2] / '.github/workflows/modal-fixture-observe.yml'
        self.assertTrue(path.exists(), 'missing isolated discovery workflow')
        text = path.read_text()
        for required in ("branches: ['test/windows-player-inspection']", 'persist-credentials: false',
                         'runs-on: windows-2022', 'runs-on: ubuntu-22.04', 'timeout-minutes: 5',
                         'PySide6==6.8.2', 'psutil==7.0.0', 'pywinauto==0.6.9',
                         "unittest discover -s tools/modal-cancel-fixture -p 'test_*.py'",
                         'python tools/modal-cancel-fixture/controller.py --evidence-root modal-observation',
                         'exit $LASTEXITCODE', 'if: always()', 'retention-days: 7'):
            self.assertIn(required, text)
        for forbidden in ('continue-on-error:', 'if ($LASTEXITCODE', 'download-artifact', 'trash-probe', 'package-windows', 'secrets.'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
