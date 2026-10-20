import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

PATH = Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo/test_servo_center_90.py"
SPEC = importlib.util.spec_from_file_location("center_90_test_runner", PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class CenterTests(unittest.TestCase):
    def test_explicit_flag_required_without_hardware_access(self):
        with patch.object(runner, "find_port", side_effect=AssertionError("hardware access")):
            self.assertEqual(runner.main([]), 2)

    def test_only_six_sequential_fixed_90_commands(self):
        session = Mock()
        pause = Mock()
        runner.run_test(session, pause)
        calls = session.command.call_args_list
        self.assertEqual(calls[0].args, ("PING", ["ACK,PING"]))
        self.assertEqual(calls[1].args, ("TEST_CENTER_CAPS", ["CAPS,TEST_CENTER_90,90,ONCE_PER_CHANNEL"]))
        for channel, call in enumerate(calls[2:8]):
            self.assertEqual(call.args, (f"TEST_CENTER_90,{channel},3000,CONFIRM_90",
                                        [f"ACK,TEST_CENTER_90,{channel},90", f"DONE,TEST_CENTER_90,{channel},90"]))
        self.assertEqual(calls[-1].args, ("STATUS_GROUP", [runner.STATUS_90]))
        self.assertEqual(pause.call_count, 6)
        self.assertEqual(len(calls), 9)

    def test_missing_done_stops_without_running_other_channels(self):
        session = Mock()
        session.command.side_effect = [None, None, RuntimeError("Missing DONE"), None]
        with self.assertRaisesRegex(RuntimeError, "Missing DONE"):
            runner.run_test(session, Mock())
        self.assertEqual(session.command.call_args.args, ("STOP", ["ACK,STOP"]))
        self.assertEqual(session.command.call_count, 4)

    def test_fragmented_replies_preserved(self):
        class Port:
            in_waiting = 0
            def __init__(self):
                self.chunks = iter([b"ACK,TE", b"ST_CENTER_90,0,90\nDONE,TEST_", b"CENTER_90,0,90\n"])
            def write(self, data):
                self.sent = data
            def flush(self):
                pass
            def read(self, size):
                return next(self.chunks)
        port = Port()
        runner.Session(port).command("TEST_CENTER_90,0,3000,CONFIRM_90",
                                     ["ACK,TEST_CENTER_90,0,90", "DONE,TEST_CENTER_90,0,90"])
        self.assertEqual(port.sent, b"TEST_CENTER_90,0,3000,CONFIRM_90\n")

    def test_zero_flag_required_without_hardware_access(self):
        with patch.object(runner, "find_port", side_effect=AssertionError("hardware access")):
            self.assertEqual(runner.main([], target=0), 2)

    def test_zero_test_sends_only_six_fixed_zero_commands(self):
        session, pause = Mock(), Mock()
        runner.run_test(session, pause, target=0)
        calls = session.command.call_args_list
        self.assertEqual(calls[1].args, ("TEST_ZERO_CAPS", ["CAPS,TEST_ZERO_0,0,ONCE_PER_CHANNEL"]))
        for channel, call in enumerate(calls[2:8]):
            self.assertEqual(call.args, (f"TEST_ZERO_0,{channel},5000,CONFIRM_0",
                                        [f"ACK,TEST_ZERO_0,{channel},0", f"DONE,TEST_ZERO_0,{channel},0"]))
        self.assertEqual(calls[-1].args, ("STATUS_GROUP", ["STATUS_GROUP" + "".join(
            f",{channel}:0:ENABLED:IDLE" for channel in range(6))]))
        self.assertEqual(pause.call_count, 6)
        self.assertEqual(len(calls), 9)

    def test_arbitrary_targets_never_send_anything(self):
        for target in (-1, 1, 180, True):
            session = Mock()
            with self.subTest(target=target), self.assertRaises(ValueError):
                runner.run_test(session, target=target)
            session.command.assert_not_called()

    def test_zero_failure_stops_before_next_channel(self):
        session = Mock()
        session.command.side_effect = [None, None, RuntimeError("Missing DONE"), None]
        with self.assertRaisesRegex(RuntimeError, "Missing DONE"):
            runner.run_test(session, Mock(), target=0)
        self.assertEqual(session.command.call_args.args, ("STOP", ["ACK,STOP"]))
        self.assertEqual(session.command.call_count, 4)


if __name__ == "__main__":
    unittest.main()
