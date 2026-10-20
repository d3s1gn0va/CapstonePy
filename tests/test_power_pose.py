from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from motion_profile import ProfileError, load_profile
from power_pose import PowerPose, park_home


class PowerPoseTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.expected = {0: 90, 1: 45, 2: 90, 3: 0, 4: 135, 5: 180}
        self.controller = Mock()
        self.controller.group_capabilities.return_value = {
            axis["channel"]: (axis["minimum"], axis["maximum"], axis["neutral"])
            for axis in self.profile.data["axes"].values()}

    @contextmanager
    def connect(self, profile):
        yield self.controller

    def test_no_confirmation_opens_no_devices(self):
        connect = Mock()
        with self.assertRaises(ProfileError):
            park_home(self.profile, connect=connect)
        connect.assert_not_called()

    def test_six_axis_home_waits_for_done_and_does_not_mark_verification(self):
        self.assertEqual(park_home(self.profile, True, self.connect), self.expected)
        self.controller.move_group.assert_called_once_with(self.expected, 3000, wait=True)
        self.assertEqual(self.controller.stop.call_count, 2)
        self.assertFalse(self.profile.data["power_verified"])
        self.assertTrue(all(not axis["verified"] for axis in self.profile.data["axes"].values()))

    def test_old_firmware_refuses_motion(self):
        self.controller.group_capabilities.return_value = {}
        with self.assertRaises(RuntimeError):
            park_home(self.profile, True, self.connect)
        self.controller.move_group.assert_not_called()

    def test_motion_error_still_requests_stop(self):
        self.controller.move_group.side_effect = RuntimeError("no DONE")
        with self.assertRaises(RuntimeError):
            park_home(self.profile, True, self.connect)
        self.assertEqual(self.controller.stop.call_count, 2)

    def test_same_boot_service_restart_does_not_repeat_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "power-pose"
            parker = Mock(return_value=self.expected)
            first = PowerPose(self.profile, marker, True, parker, "boot-a")
            first.prepare()
            resumed = PowerPose(self.profile, marker, True, parker, "boot-a")
            resumed.prepare()
            self.assertEqual(parker.call_count, 1)
            resumed.finish()
            self.assertEqual(parker.call_count, 2)
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_failed_startup_is_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "power-pose"
            parker = Mock(side_effect=RuntimeError("parking failed"))
            with self.assertRaises(RuntimeError):
                PowerPose(self.profile, marker, True, parker, "boot-a").prepare()
            with self.assertRaises(RuntimeError):
                PowerPose(self.profile, marker, True, parker, "boot-a").prepare()
            self.assertEqual(parker.call_count, 1)

    def test_new_boot_parks_again(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "power-pose"
            parker = Mock(return_value=self.expected)
            for boot in ("boot-a", "boot-b"):
                PowerPose(self.profile, marker, True, parker, boot).prepare()
            self.assertEqual(parker.call_count, 2)

    def test_failed_shutdown_blocks_same_boot_restart_and_unprepared_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "power-pose"
            parker = Mock(return_value=self.expected)
            lifecycle = PowerPose(self.profile, marker, True, parker, "boot-a")
            with self.assertRaises(RuntimeError):
                lifecycle.finish()
            lifecycle.prepare()
            parker.side_effect = RuntimeError("stop failed")
            with self.assertRaises(RuntimeError):
                lifecycle.finish()
            with self.assertRaises(RuntimeError):
                PowerPose(self.profile, marker, True, parker, "boot-a").prepare()


if __name__ == "__main__":
    unittest.main()
