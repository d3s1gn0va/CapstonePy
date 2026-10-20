import copy
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry_pi/robot_demo"))

from choreography import CHOREOGRAPHY_DIR
from dance_sequence import build_dance_steps, load_dance_config
from export_simulation import RecordingBackend, record_dance
from integrated_demo import audio_lengths, main
from integrated_sequence import IntegratedSequence
from motion_profile import load_profile, ProfileError
from oled_renderer import DEFAULT_CONFIG, EyeRenderer, load_aperture, load_calibration


class ChoreographyPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile, cls.eyes = load_profile(), load_calibration()
        cls.settings = load_dance_config(CHOREOGRAPHY_DIR / "cuvo_groove.json")
        cls.renderer = EyeRenderer(cls.eyes, load_aperture(DEFAULT_CONFIG.parent / cls.eyes["aperture_file"], cls.eyes))
        cls.recording = record_dance(cls.profile, cls.eyes, cls.renderer, cls.settings)

    def test_six_real_axes_and_sixteen_beats_with_no_elbow_commands(self):
        steps = build_dance_steps(self.profile, self.eyes, self.settings)
        self.assertEqual(len(steps), 18)
        self.assertEqual([step["beat"] for step in self.settings["steps"] if "beat" in step], list(range(1, 17)))
        for step in steps:
            self.assertEqual(set(step.targets), set(range(6)))
            for channel, angle in step.targets.items():
                low, high = self.profile.limits()[channel]
                self.assertLessEqual(low, angle)
                self.assertLessEqual(angle, high)
        self.assertEqual(steps[1].targets[1], 100)
        self.assertEqual(steps[1].targets[4], 125)
        self.assertEqual(steps[-1].targets, self.profile.targets("startup"))
        self.assertEqual(self.settings["passive_elbows"]["mechanism"], "manual_freestop")

    def test_recording_uses_the_same_runner_commands_and_eye_poses(self):
        steps = build_dance_steps(self.profile, self.eyes, self.settings)
        backend = RecordingBackend(self.profile, audio_lengths(paths={step.audio for step in steps if step.audio}))
        runner = IntegratedSequence(backend, self.profile, self.eyes, self.settings)
        runner.start("dance")
        for sample in self.recording["samples"]:
            backend.now = sample[0] / 1000
            runner.tick(backend.now)
            self.assertEqual(backend.sample_pose(), sample[1])
            self.assertEqual([round(value, 6) for value in (backend.last_eye.openness, backend.last_eye.offset_x, backend.last_eye.offset_y)], sample[4])
        self.assertEqual(runner.state, "completed")
        motions = [entry for entry in backend.commands if entry[0] == "motion"]
        self.assertEqual([(entry[1], entry[2]) for entry in motions], [(step.targets, step.duration_ms) for step in steps])
        self.assertLessEqual(self.recording["duration_ms"], 15000)
        self.assertEqual(self.recording["samples"][-1][1], [90, 45, 90, 0, 135, 180])

    def test_atlas_pixels_match_the_actual_oled_renderer(self):
        import base64
        atlas = Image.open(BytesIO(base64.b64decode(self.recording["eye_atlas"]["source"].split(",")[1])))
        for sample in self.recording["samples"][::29]:
            index, (openness, x, y) = sample[2], sample[4]
            expected = self.renderer.frames(openness, x, y)
            for side, image in enumerate(expected):
                left, top = (index % 8) * 256 + side * 128, (index // 8) * 128
                actual = atlas.crop((left, top, left + 128, top + 128)).convert("1")
                self.assertEqual(actual.tobytes(), image.tobytes())

    def test_linear_firmware_rounding_not_browser_easing(self):
        backend = RecordingBackend(self.profile, {})
        backend.start_motion({1: 100, 4: 125}, 600)
        backend.now = .15
        self.assertEqual(backend.sample_pose()[1], 59)
        self.assertEqual(backend.sample_pose()[4], 133)

    def test_bad_choreography_never_reaches_a_backend(self):
        cases = []
        for field, value in (("right_elbow", 150), ("head", 46), ("crown", -46),
                             ("right_shoulder_y", 46), ("left_shoulder_x", 136),
                             ("right_shoulder_x", True)):
            config = copy.deepcopy(self.settings)
            config["steps"][1]["relative"][field] = value
            cases.append(config)
        config = copy.deepcopy(self.settings)
        config["steps"][1]["sound"] = "../../anything"
        cases.append(config)
        config = copy.deepcopy(self.settings)
        config["steps"][-1]["relative"]["head"] = 1
        cases.append(config)
        for settings in cases:
            with self.assertRaises((ProfileError, ValueError)):
                build_dance_steps(self.profile, self.eyes, settings)

    def test_new_configuration_still_cannot_bypass_physical_verification(self):
        with patch("integrated_demo.run_hardware") as hardware:
            self.assertEqual(main(["--hardware", "--action", "dance", "--dance-config",
                                   str(CHOREOGRAPHY_DIR / "cuvo_groove.json")]), 2)
            hardware.assert_not_called()
        self.assertFalse(self.profile.data["power_verified"])
        self.assertTrue(all(not axis["verified"] for axis in self.profile.data["axes"].values()))

    def test_same_configuration_runs_through_the_local_simulation_entrypoint(self):
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--simulate", "--action", "dance", "--dance-config",
                           str(CHOREOGRAPHY_DIR / "cuvo_groove.json")])
        self.assertEqual(result, 0)
        trace = json.loads(output.getvalue())
        self.assertEqual(trace["mode"], "simulation_only")
        self.assertEqual(trace["state"], "completed")
        self.assertIn("groove_16", trace["stages"])
        self.assertEqual(len([item for item in trace["commands"] if item[0] == "audio"]), 16)


if __name__ == "__main__":
    unittest.main()
