import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry_pi/robot_demo"))

from dance_sequence import build_dance_steps, load_dance_config
from integrated_demo import audio_lengths, main
from integrated_sequence import IntegratedSequence, SimulatedBackend
from motion_profile import MotionProfile, ProfileError, load_profile
from oled_motion import EyePose
from oled_renderer import load_calibration


class DanceTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.settings, self.eyes = load_profile(), load_dance_config(), load_calibration()
        self.backend = SimulatedBackend(audio_lengths("dance"))
        self.runner = IntegratedSequence(self.backend, self.profile, self.eyes, self.settings)

    def advance_to(self, stage=None):
        for frame in range(45 * 30):
            self.backend.now = frame / 30
            self.runner.tick(self.backend.now)
            if self.runner.stage == stage or self.runner.state != "running":
                return
        self.fail("Dance did not reach its expected stage")

    def test_four_left_right_cycles_use_alternating_relative_arms(self):
        steps = build_dance_steps(self.profile, self.eyes, self.settings)
        swing = [s for s in steps if s.name.startswith("dance_") and s.name.endswith(("_left", "_right"))]
        self.assertEqual(len(swing), 8)
        for i, step in enumerate(swing):
            self.assertEqual(step.targets, {0: 60, 1: 125, 4: 135} if i % 2 == 0
                             else {0: 120, 1: 45, 4: 55})
            self.assertEqual(step.duration_ms, 550)
            self.assertEqual(step.eye_to.offset_x, 14 if i % 2 == 0 else -14)
            self.assertEqual(step.eye_to.offset_y, 8)
        raised = next(s for s in steps if s.name == "dance_raise_arms")
        self.assertEqual(raised.targets, {3: 45, 5: 135})
        self.assertTrue(all(2 not in (step.targets or {}) for step in steps))
        home = next(s for s in steps if s.name == "dance_return_home")
        self.assertEqual(home.targets, {0: 90, 1: 45, 3: 0, 4: 135, 5: 180})
        self.assertEqual(home.eye_to, EyePose())

    def test_new_voice_only_completes_and_all_commands_stay_safe(self):
        self.assertTrue(self.runner.start("dance"))
        self.advance_to()
        self.assertEqual(self.runner.state, "completed", self.runner.error)
        voices = [s[1] for s in self.backend.commands if s[0] == "audio"]
        self.assertEqual(voices, ["cuvo_look_here.wav", "cuvo_follow_me.wav", "cuvo_goodbye.wav"])
        limits = self.profile.limits()
        for command in self.backend.commands:
            if command[0] == "motion":
                for channel, angle in command[1].items():
                    self.assertLessEqual(limits[channel][0], angle)
                    self.assertLessEqual(angle, limits[channel][1])

    def test_invalid_choreography_is_rejected_before_any_output(self):
        changes = (("arm_x_min_relative_deg", -46), ("arm_x_max_relative_deg", 136),
                   ("arm_y_raise_relative_deg", 46), ("head_left_deg", 44),
                   ("head_right_deg", 136), ("head_left_deg", 90),
                   ("cycles", True), ("cycles", 0), ("cycles", 17),
                   ("swing_duration_ms", 0), ("swing_duration_ms", 60001),
                   ("gaze_down_px", -1), ("response_hold_seconds", float("nan")))
        for key, value in changes:
            settings = dict(self.settings, **{key: value})
            runner = IntegratedSequence(self.backend, self.profile, self.eyes, settings)
            with self.subTest(key=key), self.assertRaises((ValueError, OSError)):
                runner.start("dance")
            self.assertEqual(self.backend.commands, [])
            self.assertEqual(runner.state, "idle")
        with patch("dance_sequence.wave.open", side_effect=FileNotFoundError("missing voice")):
            with self.assertRaises(FileNotFoundError):
                self.runner.start("dance")
        self.assertEqual(self.backend.commands, [])

    def test_wait_is_silent_and_has_no_blink_or_gaze(self):
        self.runner.start("dance")
        self.advance_to("dance_response_wait")
        start = self.runner.started
        count = len(self.backend.commands)
        for fraction in (0.1, 0.5, 1, 2.9):
            self.backend.now = start + fraction
            self.runner.tick(self.backend.now)
            self.assertEqual(self.runner.stage, "dance_response_wait")
            self.assertEqual(self.backend.last_eye, EyePose())
            self.assertEqual(len(self.backend.commands), count)

    def test_eyes_interpolate_with_head_and_stop_returns_only_eyes(self):
        self.runner.start("dance")
        self.advance_to("dance_1_left")
        self.backend.now = self.runner.started + 0.275
        self.runner.tick(self.backend.now)
        self.assertAlmostEqual(self.backend.last_eye.offset_x, 7)
        self.assertAlmostEqual(self.backend.last_eye.offset_y, 4)
        self.assertEqual(self.backend.last_eye.openness, 1)
        self.assertFalse(self.runner.start("dance"))
        count = len(self.backend.commands)
        self.runner.stop()
        self.assertEqual(self.backend.commands[count:], [("STOP",)])
        self.assertEqual(self.runner.state, "stopped")
        self.assertTrue(self.backend.audio_aborted)
        self.assertEqual(self.backend.last_eye, EyePose())
        self.runner.tick(100)
        self.assertEqual(self.backend.last_eye, EyePose())

    def test_missing_verifications_still_refuse_physical_execution(self):
        with patch("integrated_demo.run_hardware") as run:
            self.assertEqual(main(["--hardware", "--action", "dance"]), 2)
            run.assert_not_called()
        data = copy.deepcopy(self.profile.data)
        data["power_verified"] = True
        for axis in data["axes"].values():
            axis["verified"] = True
        fixture = MotionProfile(data)
        fixture.require_ready(include_poses=False)
        with self.assertRaises(ProfileError):
            fixture.require_ready()


if __name__ == "__main__":
    unittest.main()
