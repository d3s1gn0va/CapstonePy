import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(1, str(ROOT / "raspberry_pi/robot_demo"))
from integrated_hardware import HardwareBackend

# Inject the transport only for this module load; never open a physical port.
spec = importlib.util.spec_from_file_location("group_serial_under_test",
                                            ROOT / "raspberry_pi/robot_demo/serial_controller.py")
serial_module = importlib.util.module_from_spec(spec)
fake_serial = types.SimpleNamespace(Serial=Mock(), SerialException=OSError)
with patch.dict(sys.modules, {spec.name: serial_module, "serial": fake_serial}):
    spec.loader.exec_module(serial_module)


class GroupSerialTests(unittest.TestCase):
    def setUp(self):
        self.controller = serial_module.SerialController.__new__(serial_module.SerialController)
        self.controller._start_motion = Mock(return_value="pending")
        self.controller.wait_for_done = Mock()

    def test_sorted_group_command(self):
        self.assertEqual(self.controller.move_group({5: 95, 0: 70, 3: 90}, 1200, wait=False), "pending")
        self.controller._start_motion.assert_called_once_with(
            "MOVE_GROUP,1200,0,70,3,90,5,95", "ACK,MOVE_GROUP", "DONE,MOVE_GROUP", 1200)
        self.controller.wait_for_done.assert_not_called()

    def test_invalid_group_never_sends(self):
        for targets, duration in (({}, 1), ({0: None}, 1), ({0: True}, 1), ({True: 90}, 1),
                                  ({6: 90}, 1), ({0: 181}, 1), ({0: 90}, 0),
                                  ({0: 90}, 60001), ({0: 90}, True)):
            with self.subTest(targets=targets, duration=duration), self.assertRaises(ValueError):
                self.controller.move_group(targets, duration)
        self.controller._start_motion.assert_not_called()

    def test_legacy_move_both_unchanged(self):
        self.controller.move_both(70, 180, 1200, wait=False)
        self.assertEqual(self.controller._start_motion.call_args.kwargs["command"], "MOVE_BOTH,70,180,1200")

    def test_capabilities_include_locked_channels(self):
        self.controller._drain_input = Mock()
        self.controller._write_line = Mock()
        self.controller._read_nonempty_line_until = Mock(return_value=
            "CAPS,MOVE_GROUP,0:0:180:0,1:-1:-1:-1,2:30:150:90,3:-1:-1:-1,4:-1:-1:-1,5:-1:-1:-1")
        self.assertEqual(self.controller.group_capabilities()[1], (-1, -1, -1))

    def test_old_or_invalid_firmware_rejected(self):
        self.controller._drain_input = Mock()
        self.controller._write_line = Mock()
        for response in ("ERR,UNKNOWN_COMMAND,CAPS", "CAPS,MOVE_GROUP,0:0:180:0", None):
            self.controller._read_nonempty_line_until = Mock(return_value=response)
            with self.assertRaises(serial_module.SerialControllerError):
                self.controller.group_capabilities()

    def backend(self, chunks):
        backend = HardwareBackend.__new__(HardwareBackend)
        backend.rx = bytearray()
        backend.controller = Mock()
        backend.controller.serial.timeout = 0
        backend.controller.serial.in_waiting = 32
        backend.controller.serial.read.side_effect = chunks
        return backend

    def test_fragmented_done_response_preserved(self):
        backend = self.backend([b"DONE,MO", b"VE_GROUP\r", b"\n"])
        pending = types.SimpleNamespace(done_message="DONE,MOVE_GROUP")
        self.assertFalse(backend.motion_done(pending))
        self.assertFalse(backend.motion_done(pending))
        self.assertTrue(backend.motion_done(pending))

    def test_error_response_raises(self):
        backend = self.backend([b"ERR,BUSY\n"])
        with self.assertRaises(RuntimeError):
            backend.motion_done(types.SimpleNamespace(done_message="DONE,MOVE_GROUP"))

    def test_ack_temporarily_uses_blocking_read_and_restores_timeout(self):
        backend = self.backend([])
        def motion(*args, **kwargs):
            self.assertEqual(backend.controller.serial.timeout, 0.1)
            return "pending"
        backend.controller.move_group.side_effect = motion
        self.assertEqual(backend.start_motion({0: 0}, 100), "pending")
        self.assertEqual(backend.controller.serial.timeout, 0)
        backend.controller.stop.side_effect = RuntimeError("STOP failed")
        with self.assertRaises(RuntimeError):
            backend.stop()
        self.assertEqual(backend.controller.serial.timeout, 0)


if __name__ == "__main__":
    unittest.main()
