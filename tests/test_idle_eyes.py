from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from idle_eyes import IdleEyes
from oled_motion import blink_openness, blink_period
from oled_renderer import load_calibration


class FakeEyes:
    def __init__(self):
        self.code, self.closed = None, False

    def poll(self):
        return self.code

    def close(self):
        self.closed = True


class IdleEyesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workers = []
        self.marker = Path(self.temp.name) / "enabled"
        self.eyes = IdleEyes(self.marker, self.factory, boot_id="test-boot")

    def factory(self):
        worker = FakeEyes()
        self.workers.append(worker)
        return worker

    def test_boot_and_connection_do_not_start_eyes(self):
        self.eyes.sync("idle")
        self.eyes.sync("starting", busy=True)
        self.eyes.sync("running", busy=True)
        self.assertEqual(self.workers, [])

    def test_completed_blinks_until_next_explicit_start(self):
        self.eyes.sync("completed")
        for unused in range(100):
            self.eyes.sync("completed")
        self.eyes.sync("stopped")  # Idle phone disconnect is not a motion command.
        self.assertEqual(len(self.workers), 1)
        self.assertTrue(self.marker.exists())
        self.eyes.before_dance()
        self.assertTrue(self.workers[0].closed)
        self.assertFalse(self.marker.exists())
        self.eyes.sync("running", busy=True)
        self.eyes.sync("completed")
        self.assertEqual(len(self.workers), 2)

    def test_cleanup_failure_refuses_handoff(self):
        self.eyes.sync("completed")
        def fail():
            raise RuntimeError("Not released")
        self.workers[0].close = fail
        with self.assertRaises(RuntimeError):
            self.eyes.before_dance()

    def test_error_and_shutdown_release_without_dance(self):
        self.eyes.sync("completed")
        self.eyes.sync("error")
        self.assertTrue(self.workers[0].closed)
        self.assertEqual(len(self.workers), 1)
        self.eyes.sync("completed", shutting_down=True)
        self.assertEqual(len(self.workers), 1)

    def test_worker_failure_does_not_loop_or_trigger_motion(self):
        self.eyes.sync("completed")
        self.workers[0].code = 1
        with self.assertRaises(RuntimeError):
            self.eyes.sync("completed")
        self.eyes.sync("completed")
        self.assertEqual(len(self.workers), 1)
        self.assertFalse(self.marker.exists())

    def test_only_successful_completion_survives_service_restart(self):
        self.eyes.sync("completed")
        self.eyes.sync("completed", shutting_down=True)
        restarted = IdleEyes(self.marker, self.factory, boot_id="test-boot")
        restarted.sync("idle")
        self.assertEqual(len(self.workers), 2)
        restarted.before_dance()
        IdleEyes(self.marker, self.factory, boot_id="test-boot").sync("idle")
        self.assertEqual(len(self.workers), 2)

    def test_previous_boot_marker_cannot_enable_eyes(self):
        self.eyes.sync("completed")
        self.eyes.pause()
        IdleEyes(self.marker, self.factory, boot_id="new-boot").sync("idle")
        self.assertEqual(len(self.workers), 1)

    def test_configured_blink_repeats_at_centre(self):
        config = load_calibration()
        period = blink_period(config)
        self.assertAlmostEqual(period, 3.42)
        for cycle in (0, 1, 1000):
            self.assertEqual(blink_openness(config, cycle * period + 1), 1)
            self.assertAlmostEqual(blink_openness(config, cycle * period + 3.15), 0)

    def test_real_worker_loop_uses_only_centred_eye_poses_and_cleans_up(self):
        import idle_eye_worker
        poses, handlers = [], {}
        class Displays:
            def __enter__(self):
                return self
            def show(self, pose):
                poses.append(pose)
            def __exit__(self, *unused):
                poses.append("released")
        def sleep(unused):
            if len(poses) >= 3:
                handlers[idle_eye_worker.signal.SIGTERM]()
        with patch.object(idle_eye_worker.signal, "signal", side_effect=lambda sig, fn: handlers.update({sig: fn})), \
             patch.object(idle_eye_worker, "EyeController", return_value=Displays()), \
             patch.object(idle_eye_worker.time, "monotonic", side_effect=[0, 0, 3.15, 3.42]), \
             patch.object(idle_eye_worker.time, "sleep", side_effect=sleep):
            self.assertEqual(idle_eye_worker.main(), 0)
        self.assertEqual(poses[-1], "released")
        self.assertEqual([pose.openness for pose in poses[:-1]], [1, 0, 1])
        self.assertTrue(all(pose.offset_x == pose.offset_y == 0 for pose in poses[:-1]))


if __name__ == "__main__":
    unittest.main()
