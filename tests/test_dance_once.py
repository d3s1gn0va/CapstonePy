import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))

from dance_sequence import load_dance_config
from integrated_demo import audio_lengths
from integrated_hardware import HardwareBackend
from integrated_sequence import SimulatedBackend
from motion_profile import ProfileError, load_profile
from oled_renderer import load_calibration
from test_dance_once import DanceTestBackend, main, run_once, validate_test


class DanceOnceTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.eyes, self.settings = load_profile(), load_calibration(), load_dance_config()

    def test_no_confirmation_never_opens_hardware(self):
        with patch("test_dance_once.DanceTestBackend") as hardware:
            self.assertEqual(main([]), 2)
            hardware.assert_not_called()
        with self.assertRaises(ProfileError):
            validate_test(self.profile, self.eyes, self.settings, False)

    def test_bench_scope_does_not_change_normal_verification(self):
        before = copy.deepcopy(self.profile.data)
        validate_test(self.profile, self.eyes, self.settings, True)
        self.assertEqual(self.profile.data, before)
        with self.assertRaises(ProfileError):
            HardwareBackend(self.profile, self.eyes)._require_ready()
        for key, value in (("cycles", 5), ("head_left_deg", 45),
                           ("arm_x_max_relative_deg", 81), ("arm_y_raise_relative_deg", 46)):
            with self.subTest(key=key), self.assertRaises(ProfileError):
                validate_test(self.profile, self.eyes, dict(self.settings, **{key: value}), True)

    def test_exact_motion_order_and_no_crown_or_replay(self):
        backend = DanceTestBackend(self.profile, self.eyes, self.settings, confirmed=True)
        backend._require_ready()
        with patch.object(HardwareBackend, "start_motion", return_value="pending") as motion:
            with self.assertRaises(ProfileError):
                backend.start_motion({2: 90}, 1800)
            motion.assert_not_called()
            for targets, duration in backend.approved_motions:
                self.assertNotIn(2, targets)
                backend.start_motion(targets, duration)
            self.assertEqual(motion.call_count, len(backend.approved_motions))
            with self.assertRaises(ProfileError):
                backend.start_motion(*backend.approved_motions[0])

    def test_once_completes_and_deadline_stops_without_home(self):
        backend = SimulatedBackend(audio_lengths("dance"))

        def advance(delay):
            backend.now += delay

        self.assertEqual(run_once(backend, self.profile, self.eyes, self.settings,
                                 clock=lambda: backend.now, sleeper=advance), 0)
        self.assertEqual(len([c for c in backend.commands if c[0] == "audio"]), 3)
        backend = SimulatedBackend(audio_lengths("dance"))
        self.assertEqual(run_once(backend, self.profile, self.eyes, self.settings,
                                 clock=lambda: backend.now, sleeper=lambda delay: setattr(backend, "now", 36)), 1)
        self.assertEqual(backend.commands[-1], ("STOP",))
        self.assertEqual(len([c for c in backend.commands if c[0] == "motion"]), 1)


if __name__ == "__main__":
    unittest.main()
