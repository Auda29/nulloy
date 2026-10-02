from pathlib import Path
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[2]

class WorkflowContract(unittest.TestCase):
    def test_exact_original_package_and_ipc_only(self):
        path=ROOT/'.github/workflows/pr24-ipc-acceptance.yml'
        self.assertTrue(path.exists(),'dedicated IPC workflow missing')
        data=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(data['permissions'],{'contents':'read','actions':'read'})
        self.assertEqual(data['on']['push']['branches'],['test/pr24-playback-acceptance'])
        steps=data['jobs']['windows']['steps']
        dl=next(s for s in steps if s.get('uses','').startswith('actions/download-artifact@'))
        self.assertEqual(dl['with']['run-id'],'36843804143')
        self.assertEqual(dl['with']['name'],'Nulloy-Qt6-windows-x64')
        commands='\n'.join(s.get('run','') for s in steps)
        self.assertIn('pr24_ipc.py',commands)
        self.assertIn('--case all',commands)
        self.assertIn('039c21768668d69649ee6950b9039f16b6fde0ec0835e2f8f8278ba3a79fe9be',commands)
        self.assertNotIn('cmake',commands)
        upload=next(s for s in steps if s.get('uses','').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['if'],'always()')
        self.assertEqual(upload['with']['path'],'evidence/')
        self.assertEqual(upload['with']['retention-days'],'7')

if __name__=='__main__': unittest.main()
