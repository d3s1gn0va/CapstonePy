from concurrent.futures import Future
import copy
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from ble_control import CommandError
from exhibit_control import ExhibitControl
from exhibit_sequences import ExhibitCatalog, AUDIO, PLAYS, SCENES
from integrated_sequence import IntegratedSequence, SimulatedBackend
from motion_profile import load_profile, ProfileError
from oled_renderer import load_calibration


class ImmediateExecutor:
    def submit(self, operation, *args):
        future = Future()
        try:
            future.set_result(operation(*args))
        except Exception as error:
            future.set_exception(error)
        return future

    def shutdown(self, **kwargs):
        pass


class Volume:
    def snapshot(self):
        return {"volume": 37, "muted": False, "available": True, "backend": "pipewire", "error": None}

    def set_volume(self, percent):
        return dict(self.snapshot(), volume=percent)


class Records:
    root = Path("/private-test-records")

    def capability(self):
        return {"recording_supported": False, "reason": "capture_disabled"}

    def list_records(self):
        return []


class Worker:
    def __init__(self):
        self.events, self.terminal, self.exit_code = [], None, None
        self.stops = self.kills = 0

    def poll(self):
        events, self.events = self.events, []
        return events, self.exit_code

    def terminate(self):
        self.stops += 1

    def kill(self):
        self.kills += 1

    def close(self):
        pass


class ExhibitTests(unittest.TestCase):
    def setUp(self):
        self.now, self.started, self.workers = 0, [], []
        self.client = str(uuid.uuid4())
        self.profile, self.eyes = load_profile(), load_calibration()
        self.catalog = ExhibitCatalog(self.profile, self.eyes, True)
        self.control = ExhibitControl("123456", lambda: None, confirmed=True, clock=lambda: self.now,
                                      catalog=self.catalog, exhibit_worker_factory=self.worker,
                                      volume=Volume(), records=Records(), executor=ImmediateExecutor(),
                                      allow_poweroff=True)
        self.send("session.claim", code="123456")

    def worker(self, specification):
        self.started.append(specification)
        worker = Worker()
        self.workers.append(worker)
        return worker

    def raw(self, action, payload=None, request_id=None, **extra):
        value = dict(version=1, request_id=request_id or str(uuid.uuid4()), client_id=self.client, action=action, **extra)
        if payload is not None:
            value["payload"] = payload
        return json.dumps(value).encode()

    def send(self, action, payload=None, **extra):
        return self.control.command(self.raw(action, payload, **extra), "phone", True)

    def test_connect_resume_status_do_not_start_or_replay(self):
        self.send("session.status")
        self.assertEqual(self.started, [])
        self.assertIsNone(self.control.snapshot()["run_id"])

    def test_opaque_profile_and_missing_name_audio(self):
        profile_id = str(uuid.uuid4())
        result = self.send("profile.set", {"child_name": "  지우  ", "profile_id": profile_id})
        self.assertTrue(result["command_result"]["ok"])
        self.assertEqual(result["profile"], {"profile_id": profile_id, "voice_ready": True})
        self.assertNotIn("지우", json.dumps(result, ensure_ascii=False))
        result = self.send("profile.set", {"child_name": "없는이름", "profile_id": str(uuid.uuid4())})
        self.assertTrue(result["command_result"]["ok"])
        self.assertFalse(result["profile"]["voice_ready"])
        result = self.send("play.start", {"play_id": "name_call"})
        self.assertFalse(result["command_result"]["ok"])
        self.assertEqual(self.started, [])
        result = self.send("profile.set", {"child_name": ""})
        self.assertIsNone(result["profile"]["profile_id"])

    def test_missing_yogicok_cues_refuse_before_worker(self):
        result = self.send("play.start", {"play_id": "yogicok"})
        self.assertFalse(result["command_result"]["ok"])
        self.assertIn("eyes", result["command_result"]["message"])
        self.assertEqual(self.started, [])

    def test_new_scope_flag_is_independent_of_existing_dance(self):
        self.catalog.confirmed = False
        result = self.send("scene.start", {"scene_id": "02"})
        self.assertFalse(result["command_result"]["ok"])
        result = self.send("dance.start")
        self.assertTrue(result["command_result"]["ok"])
        self.assertEqual(self.started[0]["play_id"], "dance")

    def test_duplicate_start_stop_once_and_no_arbitrary_motion(self):
        raw = self.raw("play.start", {"play_id": "dance"})
        first = self.control.command(raw, "phone", True)
        self.control.command(raw, "phone", True)
        self.assertEqual(len(self.started), 1)
        self.assertEqual(str(uuid.UUID(first["run_id"])), first["run_id"])
        bad = json.loads(raw)
        bad["payload"]["play_id"] = "name_call"
        with self.assertRaises(CommandError):
            self.control.command(json.dumps(bad).encode(), "phone", True)
        stop = self.raw("session.stop")
        self.control.command(stop, "phone", True)
        self.control.command(stop, "phone", True)
        self.assertEqual(self.workers[0].stops, 1)
        self.assertEqual(self.control.state, "stopping")

    def test_stop_and_disconnect_cannot_be_blocked_by_settings_job(self):
        self.send("play.start", {"play_id": "dance"})
        pending = Future()
        self.control.jobs.append((str(uuid.uuid4()), "audio.volume.set", pending))
        self.send("session.stop")
        self.assertEqual(self.workers[0].stops, 1)
        self.control.disconnected("phone")
        self.assertIsNone(self.control.owner)
        self.assertEqual(self.workers[0].stops, 1)
        self.assertEqual(len(self.started), 1)

    def test_late_setting_ack_does_not_overwrite_stop_ack(self):
        self.send("play.start", {"play_id": "dance"})
        pending = Future()
        self.control.jobs.append((str(uuid.uuid4()), "audio.volume.set", pending))
        accepted = self.send("session.stop")["command_result"]
        pending.set_result(Volume().snapshot())
        self.control.tick()
        self.assertEqual(self.control.command_result, accepted)

    def test_stop_wins_race_with_already_queued_completed_terminal(self):
        self.send("play.start", {"play_id": "dance"})
        self.send("session.stop")
        worker = self.workers[0]
        worker.terminal, worker.exit_code = {"state": "completed", "phase": "goodbye", "progress": 1}, 0
        self.control.tick()
        self.assertEqual(self.control.state, "stopped")
        self.assertEqual(self.control.progress, 0)

    def test_volume_readback_correlated_and_heartbeat_preserves_result(self):
        request = str(uuid.uuid4())
        self.send("audio.volume.set", {"volume": 63}, request_id=request)
        self.control.tick()
        value = self.send("session.status")
        self.assertEqual(value["volume"]["percent"], 63)
        self.assertEqual(value["command_result"]["request_id"], request)
        self.assertTrue(value["command_result"]["ok"])
        self.assertFalse(self.send("audio.volume.set", {"volume": True})["command_result"]["ok"])

    def test_shutdown_waits_confirmed_worker_cleanup(self):
        callbacks = []
        self.control.on_shutdown_ready = lambda: callbacks.append(True)
        self.send("play.start", {"play_id": "dance"})
        result = self.send("system.shutdown")
        self.assertTrue(result["command_result"]["ok"])
        self.now = 2.1
        self.control.tick()
        self.assertEqual(callbacks, [])
        worker = self.workers[0]
        worker.terminal, worker.exit_code = {"state": "stopped", "phase": "idle", "progress": 0}, 0
        self.control.tick()
        self.assertEqual(callbacks, [True])
        self.assertEqual(self.control.state, "shutting_down")

    def test_shutdown_refuses_unconfirmed_stop(self):
        callbacks = []
        self.control.on_shutdown_ready = lambda: callbacks.append(True)
        self.send("play.start", {"play_id": "dance"})
        self.send("system.shutdown")
        self.workers[0].exit_code = 1
        self.now = 2.1
        self.control.tick()
        self.assertEqual(callbacks, [])
        self.assertFalse(self.control.shutdown_requested)

    def test_completed_without_capture_has_no_fake_latest_record(self):
        self.send("play.start", {"play_id": "dance"})
        worker = self.workers[0]
        worker.terminal, worker.exit_code = {"state": "completed", "phase": "goodbye", "progress": 1}, 0
        self.control.tick()
        self.assertIsNone(self.control.snapshot()["latest_record"])
        self.assertFalse(self.control.snapshot()["capabilities"]["recording_supported"])

    def test_worker_failure_clears_busy_recording_without_fabricating_record(self):
        self.send("play.start", {"play_id": "dance"})
        self.control.recording = {"state": "saving", "error": None}
        self.workers[0].exit_code = 1
        self.control.tick()
        self.assertEqual(self.control.recording["state"], "error")
        self.assertIsNone(self.control.latest_record)

    def test_media_descriptor_refreshes_time(self):
        self.control.media = lambda: {"server_time": self.now}
        self.now = 1
        first = self.control.snapshot()["media"]
        self.now = 2
        self.assertNotEqual(first, self.control.snapshot()["media"])

    def test_compact_att_read_is_bounded_and_does_not_overtake_notification(self):
        self.send("play.start", {"play_id": "dance"})
        full = self.control.snapshot()
        read = self.control.read_snapshot()
        self.assertEqual(read["revision"], full["revision"])
        self.assertEqual(self.control.revision, full["revision"])
        self.assertLessEqual(len(json.dumps(read, separators=(",", ":")).encode()) + 1, 512)
        self.assertTrue(read["compact"])
        self.assertEqual(read["run_id"], full["run_id"])
        self.assertNotIn("capabilities", read)

    def test_snapshot_remains_bounded_for_three_records(self):
        sample = {"id": str(uuid.uuid4()), "run_id": str(uuid.uuid4()), "play_id": "scene_05_06",
                  "created_at": "2026-10-20T12:34:56.123456+00:00", "duration_seconds": 30.123,
                  "video": "video.mp4", "thumbnail": "thumbnail.jpg", "source": "robot", "state": "ready"}
        self.control.records = [sample] * 3
        self.control.latest_record = sample
        self.control.media = {"base_url": "http://cuvo.local:8765", "challenge": str(uuid.uuid4()),
                              "auth": "hmac-sha256-v1", "server_time": 1700000000}
        self.send("profile.set", {"child_name": "지우", "profile_id": str(uuid.uuid4())})
        self.assertLess(len(json.dumps(self.control.snapshot(), ensure_ascii=False).encode()), 4096)

    def test_all_presets_simulate_with_explicit_fixture_cues_without_changing_profile(self):
        before = copy.deepcopy(self.profile.data)
        # A test fixture only: production never substitutes the wrong spoken cue.
        catalog = ExhibitCatalog(self.profile, self.eyes, True,
                                 cues={key: AUDIO / "02_lets_play.wav" for key in ("invite", "eyes", "hands", "farewell")})
        for play, scene in [(play, None) for play in PLAYS] + [(None, scene) for scene in SCENES]:
            with self.subTest(play=play, scene=scene):
                steps = catalog.build(play, scene, "지우")
                lengths = {step.audio.name: .2 for step in steps if step.audio}
                backend = SimulatedBackend(lengths)
                sequence = IntegratedSequence(backend, self.profile, self.eyes)
                sequence.start_steps("exhibit", steps)
                for _ in range(1500):
                    sequence.tick(backend.now)
                    backend.now += .04
                    if sequence.state != "running":
                        break
                self.assertEqual(sequence.state, "completed", sequence.error)
                self.assertLess(backend.now, 35)
                # Every compiled step can be interrupted without queued return motion.
                for index in range(len(steps)):
                    backend = SimulatedBackend(lengths)
                    sequence = IntegratedSequence(backend, self.profile, self.eyes)
                    sequence.start_steps("exhibit", steps)
                    sequence.index = index
                    sequence.tick(0)
                    sequence.stop()
                    count = len(backend.commands)
                    sequence.tick(1)
                    self.assertEqual(len(backend.commands), count)
                    self.assertEqual(sequence.state, "stopped")
        self.assertEqual(self.profile.data, before)
        with self.assertRaises(ProfileError):
            self.profile.require_ready()


if __name__ == "__main__":
    unittest.main()
