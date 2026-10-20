import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from ble_credentials import CredentialStore
from ble_control import BLEControl, CommandError


class PersistentBLETests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private/controller.json"
        self.credentials = CredentialStore(self.path)
        self.client = str(uuid.uuid4())
        self.device = "/org/bluez/hci0/dev_TEST"
        self.token = "ab" * 32
        self.workers = []
        self.now = 0
        self.control = self.controller()

    def controller(self):
        return BLEControl("123456", lambda: self.workers.append("unexpected motion"), confirmed=True,
                          clock=lambda: self.now, credentials=CredentialStore(self.path))

    def send(self, action, control=None, device=None, token=None, paired=True):
        value = dict(version=1, request_id=str(uuid.uuid4()), client_id=self.client,
                     action=action, token=self.token if token is None else token)
        if action == "session.claim": value["code"] = "123456"
        return (control or self.control).command(json.dumps(value).encode(), device or self.device, paired)

    def test_first_registration_and_resume_after_restart_without_code_or_motion(self):
        result = self.send("session.claim")
        self.assertTrue(result["control_granted"])
        self.assertNotIn(self.token, self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        restarted = self.controller()
        self.assertIsNone(restarted.owner)
        self.now = 901
        resumed = self.send("session.resume", control=restarted)
        self.assertTrue(resumed["control_granted"])
        self.assertEqual(resumed["state"], "idle")
        self.assertEqual(self.workers, [])

    def test_resume_requires_paired_device_token_and_registered_identity(self):
        self.send("session.claim")
        restarted = self.controller()
        with self.assertRaises(CommandError): self.send("session.resume", control=restarted, paired=False)
        self.assertFalse(self.send("session.resume", control=restarted, token="cd" * 32)["control_granted"])
        self.assertFalse(self.send("session.resume", control=restarted, device="/org/bluez/hci0/dev_OTHER")["control_granted"])
        self.client = str(uuid.uuid4())
        self.assertFalse(self.send("session.resume", control=restarted)["control_granted"])
        self.assertEqual(self.workers, [])

    def test_resume_read_and_status_do_not_start_and_nonowner_cannot_renew(self):
        self.send("session.claim")
        restarted = self.controller()
        result = self.send("session.resume", control=restarted)
        self.assertEqual(restarted.snapshot()["request_id"], result["request_id"])
        self.now = 2
        self.send("session.status", control=restarted, device="/org/bluez/hci0/dev_OTHER")
        restarted.snapshot()
        self.now = 3
        restarted.tick()
        self.assertIsNone(restarted.owner)
        self.assertEqual(self.workers, [])

    def test_missing_hardware_blocks_start_even_for_registered_owner(self):
        self.send("session.claim")
        self.control.hardware_ready = lambda: False
        self.assertFalse(self.control.snapshot()["motion_ready"])
        with self.assertRaises(CommandError): self.send("dance.start")
        self.assertEqual(self.workers, [])

    def test_invalid_code_reply_survives_full_read(self):
        value = dict(version=1, request_id=str(uuid.uuid4()), client_id=self.client,
                     action="session.claim", token=self.token, code="000000")
        self.control.command(json.dumps(value).encode(), self.device, True)
        read = self.control.snapshot()
        self.assertEqual(read["request_id"], value["request_id"])
        self.assertIsNotNone(read["message"])
        self.assertFalse(read["control_granted"])

    def test_private_store_rejects_world_readable_file_and_symlink(self):
        self.send("session.claim")
        os.chmod(self.path, 0o644)
        with self.assertRaises(ValueError): CredentialStore(self.path)
        os.chmod(self.path, 0o600)
        link = self.path.with_name("link.json")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError): CredentialStore(link)
