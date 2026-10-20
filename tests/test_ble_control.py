import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from ble_control import BLEControl, CommandError


class FakeWorker:
    def __init__(self):
        self.terminal, self.exit_code = None, None
        self.stops, self.kills, self.closed = 0, 0, False

    def poll(self):
        return [], self.exit_code

    def terminate(self):
        self.stops += 1

    def kill(self):
        self.kills += 1

    def close(self):
        self.closed = True


class BLEControlTests(unittest.TestCase):
    def setUp(self):
        self.now, self.workers = 0.0, []
        self.control = BLEControl("123456", self.worker, confirmed=True, clock=lambda: self.now)
        self.client = str(uuid.uuid4())

    def worker(self):
        worker = FakeWorker()
        self.workers.append(worker)
        return worker

    def raw(self, action, code=None, client=None, request=None):
        value = dict(version=1, request_id=request or str(uuid.uuid4()), client_id=client or self.client, action=action)
        if code is not None:
            value["code"] = code
        return json.dumps(value).encode()

    def send(self, action, code=None, device="phone", client=None):
        return self.control.command(self.raw(action, code, client), device, True)

    def claim(self):
        return self.send("session.claim", "123456")

    def test_connect_status_and_claim_never_open_hardware(self):
        self.send("session.status")
        self.claim()
        self.assertEqual(self.workers, [])

    def test_full_read_preserves_claim_confirmation_without_renewing_lease(self):
        claimed = self.claim()
        self.now = 1
        self.send("session.status")
        self.now = 2
        read = self.control.snapshot()
        self.assertEqual(read["request_id"], claimed["request_id"])
        self.assertTrue(read["control_granted"])
        self.assertEqual(self.control.heartbeat, 1)
        self.now = 4
        self.control.tick()
        self.assertIsNone(self.control.owner)
        self.assertEqual(self.workers, [])

    def test_locked_default_refuses_dance(self):
        self.control.confirmed = False
        self.claim()
        with self.assertRaises(CommandError):
            self.send("dance.start")
        self.assertEqual(self.workers, [])

    def test_claim_pairing_rate_limit_and_one_owner(self):
        with self.assertRaises(CommandError):
            self.control.command(self.raw("session.claim", "123456"), "phone", False)
        for unused in range(5):
            self.assertFalse(self.send("session.claim", "000000")["control_granted"])
        self.assertFalse(self.claim()["control_granted"])
        self.now = 61
        self.assertTrue(self.claim()["control_granted"])
        other = str(uuid.uuid4())
        result = self.send("session.claim", "123456", "other", other)
        self.assertEqual(result["controller_id"], self.client)
        with self.assertRaises(CommandError):
            self.send("dance.start", device="other", client=other)

    def test_unicode_and_oversized_and_unknown_commands(self):
        self.assertFalse(self.send("session.claim", "１２３４５６")["control_granted"])
        for value in (b"x" * 513, b"{}", self.raw("servo.move")):
            with self.assertRaises(CommandError):
                self.control.command(value, "phone", True)

    def test_duplicate_start_and_stop_never_repeat_motion(self):
        self.claim()
        raw = self.raw("dance.start")
        self.control.command(raw, "phone", True)
        self.control.command(raw, "phone", True)
        self.assertEqual(len(self.workers), 1)
        with self.assertRaises(CommandError):
            self.send("dance.start")
        self.send("session.stop")
        self.send("session.stop")
        self.assertEqual(self.workers[0].stops, 1)
        self.assertEqual(self.control.state, "stopping")

    def test_other_phone_authentication_cannot_replace_active_motion_response(self):
        self.claim()
        started = self.send("dance.start")
        self.send("session.claim", "123456", device="other", client=str(uuid.uuid4()))
        self.assertEqual(self.control.snapshot()["request_id"], started["request_id"])
        self.assertEqual(self.control.state, "starting")
        self.assertEqual(len(self.workers), 1)

    def test_terminal_requires_successful_worker_exit(self):
        self.claim()
        self.send("dance.start")
        worker = self.workers[0]
        worker.terminal = dict(state="completed", phase="goodbye", progress=1)
        self.control.tick()
        self.assertEqual(self.control.state, "starting")
        worker.exit_code = 1
        self.control.tick()
        self.assertEqual(self.control.state, "error")

    def test_confirmed_stop_then_new_manual_start(self):
        self.claim()
        self.send("dance.start")
        self.send("session.stop")
        worker = self.workers[0]
        worker.terminal = dict(state="stopped", phase="idle", progress=0)
        worker.exit_code = 0
        self.control.tick()
        self.assertEqual(self.control.state, "stopped")
        self.send("dance.start")
        self.assertEqual(len(self.workers), 2)

    def test_nonowner_status_does_not_renew_watchdog(self):
        self.claim()
        self.send("dance.start")
        self.now = 2
        self.send("session.status", device="other", client=str(uuid.uuid4()))
        self.now = 3
        self.control.tick()
        self.assertEqual(self.workers[0].stops, 1)
        self.assertIsNone(self.control.owner)
        self.assertEqual(len(self.workers), 1)

    def test_disconnect_stops_without_auto_return_or_restart(self):
        self.claim()
        self.send("dance.start")
        self.control.disconnected("phone")
        self.assertEqual(self.control.state, "stopping")
        self.assertIsNone(self.control.owner)
        self.assertEqual(len(self.workers), 1)

    def test_stop_timeout_never_claims_stopped(self):
        self.claim()
        self.send("dance.start")
        self.send("session.stop")
        self.now = 6
        self.control.tick()
        self.assertEqual(self.control.state, "error")
        self.assertEqual(self.workers[0].kills, 1)


if __name__ == "__main__":
    unittest.main()
