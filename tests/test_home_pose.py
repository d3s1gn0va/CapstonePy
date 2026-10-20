import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(1, str(ROOT / "raspberry_pi/robot_demo"))
spec = importlib.util.spec_from_file_location("home_pose_runner", ROOT / "raspberry_pi/robot_demo/test_home_pose.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class HomePoseTests(unittest.TestCase):
    def test_missing_confirmation_refuses(self):
        self.assertEqual(runner.main([]), 2)

    def test_only_selected_axes_and_complete_replies(self):
        calls = []

        class Session:
            def command(self, command, replies, **kwargs):
                calls.append((command, replies, kwargs))

        runner.run_test(Session(), pause=lambda seconds: None)
        self.assertEqual([call[0] for call in calls], ["PING", "TEST_HOME_CAPS",
                         "TEST_HOME_POSE,0,5000,CONFIRM_FROM_0",
                         "TEST_HOME_POSE,1,10000,CONFIRM_FROM_0",
                         "TEST_HOME_POSE,2,5000,CONFIRM_FROM_0", "STATUS_GROUP"])
        self.assertEqual(calls[3][1], ["ACK,TEST_HOME_POSE,1,180", "DONE,TEST_HOME_POSE,1,180"])
        self.assertGreater(calls[3][2]["timeout"], 10)

    def test_failure_stops_without_other_axes_or_return(self):
        calls = []

        class Session:
            def command(self, command, replies, **kwargs):
                calls.append(command)
                if command.startswith("TEST_HOME_POSE,1,"):
                    raise RuntimeError("missing DONE")

        with self.assertRaises(RuntimeError):
            runner.run_test(Session(), pause=lambda seconds: None)
        self.assertEqual(calls[-1], "STOP")
        self.assertFalse(any(command.startswith("TEST_HOME_POSE,2,") for command in calls))


if __name__ == "__main__":
    unittest.main()
