import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(1, str(ROOT / "raspberry_pi/robot_demo"))

import config
from integrated_demo import audio_lengths, main
from integrated_sequence import IntegratedSequence, SimulatedBackend
from motion_profile import MotionProfile, ProfileError, load_profile


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        with (ROOT / "raspberry_pi/robot_demo/oled_pair_calibration.json").open() as file:
            self.eye_config = json.load(file)
        self.backend = SimulatedBackend(audio_lengths())
        self.runner = IntegratedSequence(self.backend, self.profile, self.eye_config)

    def run_to_finish(self, limit=30):
        for frame in range(limit * 30):
            self.backend.now = frame / 30
            self.runner.tick(self.backend.now)
            if self.runner.state != "running":
                return
        self.fail("Timeline did not finish")

    def test_unset_profile_refuses_hardware(self):
        self.assertIn("right_shoulder_x.verified", self.profile.missing())
        self.assertIn("invitation.left_shoulder_y", self.profile.missing())
        with self.assertRaises(ProfileError):
            self.profile.require_ready()
        with patch("integrated_demo.run_hardware", side_effect=lambda p, e: p.require_ready()):
            self.assertEqual(main(["--hardware"]), 2)

    def test_approved_fixture_profile_checks_limits_not_real_calibration(self):
        data = copy.deepcopy(self.profile.data)
        data["power_verified"] = True
        for name, axis in data["axes"].items():
            axis["verified"] = True
            if "shoulder" in name:
                axis.update(minimum=85, maximum=95, neutral=90)
                axis.pop("joint", None)
        for targets in data["poses"].values():
            for name in targets:
                if "shoulder" in name:
                    targets[name] = 95
        profile = MotionProfile(data)
        profile.require_ready()
        data["poses"]["greeting"]["right_shoulder_x"] = 96
        with self.assertRaises(ProfileError):
            MotionProfile(data)

    def test_invalid_profiles_rejected(self):
        for field, value in (("minimum", True), ("neutral", 181), ("maximum", -1),
                             ("verified", 1), ("channel", True)):
            data = copy.deepcopy(self.profile.data)
            data["axes"]["head"][field] = value
            with self.subTest(field=field), self.assertRaises(ProfileError):
                MotionProfile(data)
        data = copy.deepcopy(self.profile.data)
        data["poses"]["invitation"]["crown"] = 90
        with self.assertRaises(ProfileError):
            MotionProfile(data)

    def test_latest_user_calibration_maps_each_arm_independently(self):
        axis = self.profile.data["axes"]["right_shoulder_x"]
        self.assertEqual(axis["neutral"], 45)
        self.assertEqual(self.profile.servo_angle("right_shoulder_x", 0), 45)
        self.assertEqual(self.profile.servo_angle("right_shoulder_x", 45), 90)
        self.assertEqual(self.profile.servo_angle("right_shoulder_x", -45), 0)
        with self.assertRaises(ProfileError):
            self.profile.servo_angle("right_shoulder_x", -46)
        for name, limits in (("right_shoulder_y", (0, 45)), ("left_shoulder_y", (0, 45))):
            axis = self.profile.data["axes"][name]
            self.assertEqual((axis["joint"]["minimum"], axis["joint"]["maximum"]), limits)
            self.assertEqual(axis["joint"]["neutral"], 0)
            self.assertEqual(self.profile.targets("startup")[axis["channel"]], axis["neutral"])
        self.assertEqual(self.profile.servo_angle("left_shoulder_x", 0), 135)
        self.assertEqual(self.profile.servo_angle("left_shoulder_x", 45), 90)
        self.assertEqual(self.profile.servo_angle("left_shoulder_x", -45), 180)
        self.assertEqual(self.profile.joint_targets({"right_shoulder_y": 30, "left_shoulder_y": 30}),
                         {3: 30, 5: 150})
        for bad in ({}, {"unknown": 0}, {"right_shoulder_x": -46}, {"left_shoulder_y": 46}):
            with self.assertRaises(ProfileError):
                self.profile.joint_targets(bad)

    def test_relative_conversion_requires_consistent_physical_limits(self):
        # These offsets are fixtures only, not measured robot settings.
        for direction in (-1, 1):
            data = copy.deepcopy(self.profile.data)
            axis = data["axes"]["right_shoulder_x"]
            axis.update(minimum=45, maximum=135, neutral=90)
            axis["joint"].update(minimum=-45, maximum=45, servo_zero=90, direction=direction)
            profile = MotionProfile(data)
            for angle in (-45, 0, 45):
                self.assertEqual(profile.servo_angle("right_shoulder_x", angle), 90 + direction * angle)
            for angle in (-46, 46, True):
                with self.assertRaises(ProfileError):
                    profile.servo_angle("right_shoulder_x", angle)
            axis["neutral"] = 180
            with self.assertRaises(ProfileError):
                MotionProfile(data)

    def test_bad_or_impossible_joint_calibrations_rejected(self):
        for key, value in (("servo_zero", True), ("direction", True), ("direction", 0),
                           ("minimum", True), ("minimum", 136), ("neutral", 136)):
            data = copy.deepcopy(self.profile.data)
            data["axes"]["right_shoulder_x"]["joint"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ProfileError):
                MotionProfile(data)
        for direction in (-1, 1):
            data = copy.deepcopy(self.profile.data)
            data["axes"]["right_shoulder_x"]["joint"].update(minimum=-45, servo_zero=0, direction=direction)
            with self.assertRaises(ProfileError):
                MotionProfile(data)

    def test_demo_uses_confirmed_channels_without_inventing_angles(self):
        self.assertTrue(self.runner.start())
        self.run_to_finish()
        self.assertEqual(self.runner.state, "completed")
        motions = [entry for entry in self.backend.commands if entry[0] == "motion"]
        self.assertEqual(motions[0], ("motion", {0: 70, 1: None, 3: None}, 1200))
        self.assertEqual(motions[1], ("motion", {4: None, 5: None}, 1200))
        self.assertEqual(set(motions[2][1]), {0, 1, 3, 4, 5})
        self.assertEqual(motions[2][2], 1800)
        audios = [entry for entry in self.backend.commands if entry[0] == "audio"]
        self.assertEqual(audios, [("audio", "01_name_call.wav"), ("audio", "02_lets_play.wav")])
        self.assertEqual(self.runner.events[-2:], ["finish_blink", "completed"])

    def test_startup_includes_six_axes(self):
        self.runner.start("startup")
        self.run_to_finish()
        self.assertEqual(set(self.backend.commands[0][1]), set(range(6)))

    def test_duplicate_button_press_is_not_queued(self):
        self.runner.start()
        self.assertFalse(self.runner.start("camera"))
        self.run_to_finish()
        self.assertTrue(self.runner.start("camera"))

    def test_camera_moves_only_crown_and_led_clears(self):
        self.runner.start("camera")
        self.runner.tick(0)
        self.assertTrue(self.backend.led_on)
        self.run_to_finish()
        motions = [entry for entry in self.backend.commands if entry[0] == "motion"]
        self.assertEqual(motions, [("motion", {2: 45}, 2000), ("motion", {2: 135}, 2000),
                                   ("motion", {2: 90}, 1500)])
        self.assertFalse(self.backend.led_on)

    def test_stop_never_returns_home_or_disables_pwm(self):
        self.runner.start("camera")
        self.runner.tick(0)
        self.runner.stop()
        self.assertEqual(self.runner.state, "stopped")
        self.assertFalse(self.runner.start())
        self.assertEqual(self.backend.commands[-1], ("STOP",))
        self.assertEqual(len(self.backend.commands), 2)
        self.assertFalse(self.backend.led_on)
        self.assertTrue(self.backend.audio_aborted)

    def test_stop_ack_failure_is_error_not_stopped(self):
        self.runner.start()
        with patch.object(self.backend, "stop", return_value=False):
            self.runner.stop()
        self.assertEqual(self.runner.state, "error")
        self.assertIn("acknowledgement", self.runner.error)

    def test_audio_failure_stops_without_advancing(self):
        self.runner.start()
        for frame in range(90):
            self.backend.now = frame / 30
            self.runner.tick(self.backend.now)
            if self.runner.stage == "name_call":
                break
        with patch.object(self.backend, "audio_done", side_effect=RuntimeError("audio failure")):
            self.runner.tick(self.backend.now + 0.1)
        self.assertEqual(self.runner.state, "error")
        self.assertNotIn("invitation", self.runner.events)
        self.assertEqual(self.backend.commands[-1], ("STOP",))

    def test_done_event_consumed_once_waits_for_audio(self):
        self.runner.start("startup")
        self.runner.tick(0)
        # A DONE line is an event, not a continuously repeated signal.
        self.runner.audio = object()
        with patch.object(self.backend, "motion_done", side_effect=[True, False]) as poll, \
                patch.object(self.backend, "audio_done", return_value=False):
            self.runner.tick(1.8)
            self.runner.tick(1.9)
        self.assertEqual(poll.call_count, 1)
        self.assertIsNone(self.runner.motion)
        self.assertEqual(self.runner.state, "running")

    def test_missing_motion_done_times_out_and_led_clears(self):
        self.runner.start("camera")
        self.runner.tick(0)
        with patch.object(self.backend, "motion_done", return_value=False):
            self.runner.tick(4.1)
        self.assertEqual(self.runner.state, "error")
        self.assertIn("DONE timeout", self.runner.error)
        self.assertFalse(self.backend.led_on)

    def test_eye_output_failure_stops_once(self):
        self.runner.start()
        with patch.object(self.backend, "show_eye", side_effect=RuntimeError("OLED")):
            self.runner.tick(0)
            self.runner.tick(1)
        self.assertEqual(self.backend.commands, [("STOP",)])
        self.assertEqual(self.runner.state, "error")


if __name__ == "__main__":
    unittest.main()
