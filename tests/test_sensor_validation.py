import unittest
from jace.simulator import decide_motion


class SensorValidationTests(unittest.TestCase):
    def test_unknown_and_invalid_sensor_values_halt(self):
        for observation in [None, {}, {'living_entity':False}, {'distance_m':None},
                            {'distance_m':'3.0'}, {'distance_m':True}, {'distance_m':-1},
                            {'distance_m':float('nan')}, {'distance_m':float('inf')},
                            {'distance_m':3,'uncertainty':float('nan')},
                            {'distance_m':3,'uncertainty':1.2},
                            {'distance_m':3,'living_entity':'false'},
                            {'distance_m':3,'fragile_object':0}]:
            with self.subTest(observation=observation):
                decision = decide_motion(observation)
                self.assertEqual(decision.action, 'HALT_AND_REROUTE')
                self.assertEqual(decision.velocity, 0)
                self.assertFalse(decision.executable)
                self.assertTrue(decision.requires_confirmation)

    def test_valid_clear_path_remains_proposal_only(self):
        decision = decide_motion({'distance_m':3.0,'living_entity':False,'fragile_object':False,'uncertainty':0.1})
        self.assertEqual(decision.action,'PROCEED_SLOWLY')
        self.assertFalse(decision.executable)
        self.assertTrue(decision.requires_confirmation)


if __name__ == '__main__':
    unittest.main()
