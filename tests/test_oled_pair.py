import copy
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry_pi/robot_demo"))
import oled_controller as hardware
import oled_motion as motion
import oled_renderer as graphics


class EyeTests(unittest.TestCase):
    def setUp(self):
        self.config = graphics.load_calibration()
        self.profile = graphics.load_aperture(
            graphics.DEFAULT_CONFIG.parent / self.config["aperture_file"], self.config)
        self.renderer = graphics.EyeRenderer(self.config, self.profile)

    def test_va_to_aa_mapping_and_independent_pupil_bounds(self):
        self.assertEqual(graphics.mm_to_pixel(self.config, 1), -0.5)
        self.assertAlmostEqual(graphics.mm_to_pixel(self.config, 27.86), 127.5)
        self.assertEqual(self.config["iris_bounds_px"], [29, 7, 122, 125])

    def test_pupil_preserves_dimensions_stroke_and_hole(self):
        pupil = self.renderer.pupil()
        self.assertEqual(pupil.getbbox(), (29, 7, 123, 126))
        self.assertFalse(pupil.getpixel((75, 66)))
        self.assertTrue(all(pupil.getpixel((x, 66)) for x in range(29, 39)))
        self.assertFalse(pupil.getpixel((39, 66)))
        closed = self.renderer.pupil(0).getbbox()
        self.assertEqual(closed[3] - closed[1], 10)
        self.assertEqual(closed[2] - closed[0], 94)

    def test_default_blink_timing_unchanged(self):
        for seconds, expected in ((0, 1), (3.06, 0.5), (3.16, 0), (3.31, 0.5), (3.42, 1)):
            self.assertAlmostEqual(motion.blink_openness(self.config, seconds), expected)

    def test_aperture_is_asymmetric_with_wider_lower_left(self):
        mask = self.renderer.masks[0]
        old = Image.new("1", (128, 128))
        box = tuple(graphics.mm_to_pixel(self.config, value)
                    for value in (6.39, 1.744, 27.509, 28.187))
        ImageDraw.Draw(old).ellipse(box, fill=1)
        self.assertTrue(mask.getpixel((35, 110)))
        self.assertFalse(old.getpixel((35, 110)))
        self.assertEqual(self.renderer.masks[1].tobytes(),
                         mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())

    def test_frames_clip_full_pupil_only_after_translation(self):
        for openness in (0, 0.5, 1):
            raw = self.renderer.pupil(openness)
            originals = (raw, raw.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
            for offset in (-28, -14, 0, 14, 28):
                frames = self.renderer.frames(openness, offset)
                for source, frame, mask in zip(originals, frames, self.renderer.masks):
                    self.assertEqual(frame.size, (128, 128))
                    self.assertEqual(frame.mode, "1")
                    self.assertTrue(frame.getbbox())
                    for y in range(128):
                        for x in range(128):
                            sx = x - offset
                            expected = (0 <= sx < 128 and bool(source.getpixel((sx, y)))
                                        and bool(mask.getpixel((x, y))))
                            self.assertEqual(bool(frame.getpixel((x, y))), expected)

    def test_circular_expansion_is_three_pixels_without_wrapping(self):
        for cx, cy in ((64, 64), (0, 0), (127, 127)):
            mask = Image.new("1", (128, 128))
            mask.putpixel((cx, cy), 1)
            expanded = graphics.expand_mask(mask, 3)
            for y in range(128):
                for x in range(128):
                    self.assertEqual(bool(expanded.getpixel((x, y))),
                                     (x - cx) ** 2 + (y - cy) ** 2 <= 9)
            self.assertEqual(graphics.expand_mask(mask, 0).tobytes(), mask.tobytes())

    def test_expansion_preserves_cad_pupil_and_mirrors(self):
        original_profile = copy.deepcopy(self.profile)
        base = graphics.EyeRenderer(dict(self.config, aperture_expand_px=0), self.profile)
        self.assertEqual(self.config["aperture_expand_px"], 3)
        self.assertEqual(self.renderer.pupil().tobytes(), base.pupil().tobytes())
        self.assertEqual(self.profile, original_profile)
        expected = graphics.expand_mask(base.masks[0], 3)
        self.assertEqual(self.renderer.masks[0].tobytes(), expected.tobytes())
        self.assertEqual(self.renderer.masks[1].tobytes(),
                         expected.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())
        before = sum(bool(base.masks[0].getpixel((x, y))) for y in range(128) for x in range(128))
        after = sum(bool(expected.getpixel((x, y))) for y in range(128) for x in range(128))
        self.assertGreater(after, before)
        for y in range(128):
            for x in range(128):
                if base.masks[0].getpixel((x, y)):
                    self.assertTrue(expected.getpixel((x, y)))

    def test_remapping_does_not_change_pupil_and_can_reveal_hidden_pixels(self):
        profile = copy.deepcopy(self.profile)
        profile["left_points_mm"] = [[10, 1], [20, 1], [20, 27], [10, 27]]
        renderer = graphics.EyeRenderer(self.config, profile)
        self.assertEqual(renderer.pupil().tobytes(), self.renderer.pupil().tobytes())
        self.assertFalse(renderer.frames()[0].getpixel((29, 66)))
        self.assertTrue(renderer.frames(offset_x=28)[0].getpixel((57, 66)))

    def test_center_frames_remain_mirrored_for_all_blink_states(self):
        for step in range(51):
            left, right = self.renderer.frames(step / 50)
            self.assertTrue(left.getbbox())
            self.assertEqual(right.tobytes(), left.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())

    def test_gaze_distance_timing_return_and_blink(self):
        self.assertEqual(motion.gaze_distance(self.config), 28)
        self.assertAlmostEqual(motion.gaze_period(self.config), 5.24)
        for seconds, offset, openness in (
                (0, 0, 1), (1.1, -14, 1), (1.2, -28, 1), (1.9, -28, 1),
                (2.1, -14, 1), (2.2, 0, 1), (2.26, 0, 0.5), (2.36, 0, 0),
                (2.51, 0, 0.5), (2.62, 0, 1), (3.72, 14, 1), (3.82, 28, 1),
                (4.72, 14, 1), (4.88, 0, 0.5), (4.98, 0, 0), (5.24, 0, 1)):
            pose = motion.gaze_pose(self.config, seconds)
            self.assertEqual(pose.offset_x, offset)
            self.assertAlmostEqual(pose.openness, openness)
        for tick in range(1501):
            pose = motion.gaze_pose(self.config, tick / 100)
            self.assertTrue(-28 <= pose.offset_x <= 28)
            self.assertTrue(0 <= pose.openness <= 1)
            if pose.openness < 1:
                self.assertEqual(pose.offset_x, 0)
            if pose.offset_x:
                self.assertEqual(pose.openness, 1)

    def test_gaze_both_eyes_move_in_same_direction(self):
        def center_x(frame):
            points = [x for y in range(128) for x in range(128) if frame.getpixel((x, y))]
            return sum(points) / len(points)
        # A clipped ring's visible centroid is not its gaze direction. Use an unclipped marker.
        marker = Image.new("1", (128, 128))
        ImageDraw.Draw(marker).rectangle((60, 60, 68, 68), fill=1)
        with patch.object(self.renderer, "pupil", return_value=marker):
            neutral = [center_x(frame) for frame in self.renderer.frames()]
            for offset in (-28, 28):
                for before, frame in zip(neutral, self.renderer.frames(offset_x=offset)):
                    self.assertAlmostEqual(center_x(frame) - before, offset)
        left, right = self.renderer.frames(offset_x=-28)
        opposite_left, opposite_right = self.renderer.frames(offset_x=28)
        self.assertEqual(right.tobytes(), opposite_left.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())
        self.assertEqual(left.tobytes(), opposite_right.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())

    def test_invalid_config_is_rejected(self):
        changes = (("aa_side_mm", 0), ("iris_bounds_px", [29, 7, 12, 125]),
                   ("stroke_px", 0), ("contrast", 256), ("close_seconds", 0),
                   ("fps", float("nan")), ("fps", True), ("aperture_file", ""),
                   ("gaze_width_ratio", -0.1), ("gaze_width_ratio", 1.1),
                   ("gaze_move_seconds", 0), ("gaze_hold_seconds", 0), ("gaze_center_seconds", 0),
                   ("aperture_expand_px", -1), ("aperture_expand_px", 17),
                   ("aperture_expand_px", 1.5), ("aperture_expand_px", True))
        for key, value in changes:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps(dict(self.config, **{key: value})), encoding="utf-8")
                with self.assertRaises(ValueError):
                    graphics.load_calibration(path)

    def test_invalid_aperture_is_rejected(self):
        changes = (("units", "pixels"), ("va_side_mm", 10), ("right_mirrors_left", False),
                   ("left_points_mm", [[0, 0], [10, 10]]),
                   ("left_points_mm", [[0, 0], [10, 0], [10, 0], [10, 10], [0, 10]]),
                   ("left_points_mm", [[0, 0], [10, 10], [0, 10], [12, 0]]),
                   ("left_points_mm", [[0, 0], [40, 0], [10, 10]]),
                   ("left_points_mm", [[0, 0], [10, float("nan")], [10, 10]]))
        for key, value in changes:
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "aperture.json"
                path.write_text(json.dumps(dict(self.profile, **{key: value})), encoding="utf-8")
                with self.assertRaises(ValueError):
                    graphics.load_aperture(path, self.config)

    def test_invalid_pose_is_rejected(self):
        for value in (-0.1, 1.1, float("nan"), True):
            with self.assertRaises(ValueError):
                self.renderer.frames(openness=value)
        for value in (-129, 129, float("nan"), True):
            with self.assertRaises(ValueError):
                self.renderer.frames(offset_x=value)
            with self.assertRaises(ValueError):
                self.renderer.frames(offset_y=value)

    def test_diagonal_translation_keeps_fixed_cad_mask(self):
        for dx, dy in ((10, 8), (-10, 8), (0, 0)):
            pupil = self.renderer.pupil()
            for source, frame, mask in zip((pupil, pupil.transpose(Image.Transpose.FLIP_LEFT_RIGHT)),
                                           self.renderer.frames(offset_x=dx, offset_y=dy), self.renderer.masks):
                self.assertTrue(frame.getbbox())
                for y in range(128):
                    for x in range(128):
                        sx, sy = x - dx, y - dy
                        expected = (0 <= sx < 128 and 0 <= sy < 128
                                    and bool(source.getpixel((sx, sy))) and bool(mask.getpixel((x, y))))
                        self.assertEqual(bool(frame.getpixel((x, y))), expected)

    def test_head_direction_is_robot_relative_not_viewer_relative(self):
        left = motion.head_gaze_pose(60, 90, 60, 120, 10, 8)
        right = motion.head_gaze_pose(120, 90, 60, 120, 10, 8)
        self.assertEqual((left.offset_x, left.offset_y), (10, 8))
        self.assertEqual((right.offset_x, right.offset_y), (-10, 8))
        self.assertEqual(motion.head_gaze_pose(90, 90, 60, 120, 10, 8), motion.EyePose())
        midpoint = motion.interpolate_gaze(motion.EyePose(), left, 0.325, 0.65)
        self.assertEqual((midpoint.offset_x, midpoint.offset_y), (5, 4))
        for args in ((60, 90, 90, 120, 10, 8), (60, 90, 60, 120, True, 8),
                     (0, 90, 60, 120, 10, 8), (60, 90, 60, 120, 10, -1)):
            with self.assertRaises(ValueError):
                motion.head_gaze_pose(*args)

    def test_pin_assignment_and_cleanup(self):
        serials, displays = [Mock(), Mock()], [Mock(), Mock()]
        serial_factory, factory = Mock(side_effect=serials), Mock(side_effect=displays)
        with ExitStack() as stack:
            self.assertEqual(hardware.open_displays(stack, self.config, factory, serial_factory), displays)
        for display in displays:
            display.contrast.assert_called_once_with(255)
            display.cleanup.assert_called_once()
        assignments = [call.kwargs for call in serial_factory.call_args_list]
        self.assertEqual([(a["device"], a["gpio_DC"], a["gpio_RST"]) for a in assignments],
                         [(0, 24, 25), (1, 4, 18)])

    def test_second_init_failure_cleans_both_resources(self):
        serials, display = [Mock(), Mock()], Mock()
        with self.assertRaises(RuntimeError), ExitStack() as stack:
            hardware.open_displays(stack, self.config, Mock(side_effect=[display, RuntimeError("init")]),
                                   Mock(side_effect=serials))
        display.cleanup.assert_called_once()
        serials[1].cleanup.assert_called_once()

    def test_controller_pose_swap_lock_and_cleanup(self):
        displays = [Mock(), Mock()]
        open_original = hardware.open_displays
        def fake_open(stack, config):
            return open_original(stack, config, Mock(side_effect=displays), Mock(side_effect=[Mock(), Mock()]))
        controller = hardware.EyeController(self.renderer, swap=True)
        with patch.object(hardware, "open_displays", side_effect=fake_open):
            with controller:
                pose = motion.EyePose(offset_x=28)
                controller.show(pose)
                expected = self.renderer.frames(offset_x=28)[::-1]
                for display, frame in zip(displays, expected):
                    self.assertEqual(display.display.call_args.args[0].tobytes(), frame.tobytes())
                with self.assertRaises(RuntimeError):
                    with hardware.EyeController(self.renderer):
                        self.fail("Duplicate controller acquired the lock")
                for display in displays:
                    display.display.reset_mock()
                with self.assertRaises(ValueError):
                    controller.show(motion.EyePose(openness=float("nan")))
                for display in displays:
                    display.display.assert_not_called()
        for display in displays:
            display.cleanup.assert_called_once()
        with self.assertRaises(RuntimeError):
            controller.show(motion.EyePose())


if __name__ == "__main__":
    unittest.main()
