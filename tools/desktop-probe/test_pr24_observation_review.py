import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pr24_playback as p

class ReviewTests(unittest.TestCase):
    def test_case_runner_accepts_explicit_runtime_factory(self):
        import inspect
        self.assertIn('runtime_factory', inspect.signature(p.run_case).parameters)

    def test_trace_path_identity_resolves_short_long_aliases(self):
        with patch.object(p.os.path,'samefile',return_value=True):
            self.assertTrue(hasattr(p,'same_message'),'path identity comparator missing')
            self.assertTrue(p.same_message('C:/Users/RUNNER~1/a.wav','C:/Users/runneradmin/a.wav'))
        with patch.object(p.os.path,'samefile',side_effect=OSError()):
            self.assertFalse(p.same_message('C:/a.wav','C:/b.wav'))
        self.assertTrue(p.same_message('--next','--next'))
        self.assertFalse(p.same_message('--next','--stop'))

    def test_restored_cases_cover_all_preferences_and_states(self):
        specs=[p.CASE_SPECS[name] for name in p.CASES_BY_GROUP['restored']]
        self.assertEqual({(s.enqueue,s.play_enqueued,s.initial_state) for s in specs},
                         {(a,b,state) for a in (False,True) for b in (False,True)
                          for state in ('playing','paused','stopped')})

    def test_fixture_sets_share_directory_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'fixtures'
            first=p.make_long_fixtures(folder,1,'seed')
            second=p.make_long_fixtures(folder,1,'open')
            self.assertTrue(first[0].is_file())
            self.assertTrue(second[0].is_file())
            with self.assertRaises(FileExistsError):
                p.make_long_fixtures(folder,1,'seed')

    def test_state_observer_does_not_classify_before_three_samples(self):
        runner=object.__new__(p.PlaybackCaseRun)
        with patch.object(runner,'_direct_observation', side_effect=[
            dict(current_media='seed.wav',position=x,monotonic=x,title='seed.wav')
            for x in (10.,11.,12.)]), patch.object(p.time,'sleep'):
            observed=runner._observe_state('playing',['seed.wav'],'seed.wav')
        self.assertEqual(observed['state'],'playing')
        self.assertEqual(len(observed['samples']),3)

    def test_visible_indices_are_checked_not_discarded(self):
        self.assertTrue(hasattr(p,'indexed_rows'),'strict indexed-row parser missing')
        self.assertEqual(p.indexed_rows(['1 - a.wav','2 - b.wav']),['a.wav','b.wav'])
        with self.assertRaises(p.ContractError):
            p.indexed_rows(['1 - a.wav','1 - b.wav'])
        with self.assertRaises(p.ContractError):
            p.indexed_rows(['1','2','3'])  # actual first-run raw Qt UIA labels

    def test_position_preservation_rejects_reset_and_paused_drift(self):
        self.assertTrue(hasattr(p,'validate_preserved_position'),'position contract missing')
        p.validate_preserved_position(46,48,'playing',3)
        p.validate_preserved_position(46,46,'paused',3)
        for state,after in [('playing',0),('paused',0),('paused',49),('playing',99)]:
            with self.subTest(state=state,after=after), self.assertRaises(p.ContractError):
                p.validate_preserved_position(46,after,state,3)

    def test_ini_trackinfo_is_real_qsettings_section(self):
        settings=p.playback_settings(enqueue=True,play_enqueued=False,restore=True,start_paused=True)
        self.assertIn('[TrackInfo]\n',settings)
        self.assertIn('MiddleRight=%T',settings)
        self.assertNotIn('TrackInfo/BottomRight=',settings)

if __name__=='__main__': unittest.main()
