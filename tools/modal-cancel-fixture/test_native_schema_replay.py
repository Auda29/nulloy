"""Replay actual Qt 6.8.2 observation fields; no native actions."""
import json
from pathlib import Path
import unittest
from test_worker_cancel import worker, Wrapper, Info
from test_controller_cancel import controller

HERE = Path(__file__).resolve().parent
CAPTURE = json.loads((HERE / 'fixtures/qt682-native-observation.json').read_text())


def wrap(record):
    return Wrapper(Info(name=record['name'], pid=record['process_id'],
                        runtime=record['runtime_id'], hwnd=record['hwnd'],
                        class_name=record['class_name'], control_type=record['control_type'],
                        automation_id=record['automation_id']))


class NativeSchemaReplayTests(unittest.TestCase):
    def test_fresh_body_and_both_buttons_must_have_owned_pid(self):
        import copy
        for role in ('body', 'Cancel', 'Yes'):
            with self.subTest(role=role):
                obs = copy.deepcopy(CAPTURE['observations'])
                record = obs[role] if role == 'body' else obs['buttons'][role]
                record['process_id'] = 999
                match = (wrap(obs['dialog']), {'body': wrap(obs['body']),
                         'buttons': {name: wrap(row) for name, row in obs['buttons'].items()}})
                with self.assertRaises(ValueError):
                    worker._strict_shape(wrap(obs['root']), match, CAPTURE['nonce'],
                                         obs['root']['process_id'], obs['root']['hwnd'])

    def test_actual_native_shape_reaches_worker_action_identity_gate(self):
        obs = CAPTURE['observations']
        match = (wrap(obs['dialog']), {'body': wrap(obs['body']),
                 'buttons': {name: wrap(row) for name, row in obs['buttons'].items()}})
        error = None
        try:
            worker._strict_shape(wrap(obs['root']), match, CAPTURE['nonce'],
                                 obs['root']['process_id'], obs['root']['hwnd'])
        except ValueError as exc:
            error = str(exc)
        self.assertIsNone(error, error)

    def test_actual_worker_observation_schema_is_accepted_by_parent(self):
        obs = CAPTURE['observations']
        state = {'main_title': obs['root']['name'], 'dialog_title': obs['dialog']['name'],
                 'pid': obs['root']['process_id'], 'hwnd': obs['root']['hwnd']}
        error = None
        try:
            controller._validate_worker_observations({'observations': obs}, state, CAPTURE['nonce'])
        except ValueError as exc:
            error = str(exc)
        self.assertIsNone(error, error)


if __name__ == '__main__':
    unittest.main()
