import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from exhibit_media import MediaError, RecordManager, VolumeController


def available(name):
    return "/fake/bin/" + name


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.stdout = "Volume: 0.42\n"
        self.code = 0
        self.now = 0
        self.elapsed_per_command = 0

        def run(args, **kwargs):
            self.calls.append((args, kwargs))
            self.now += self.elapsed_per_command
            return SimpleNamespace(returncode=self.code, stdout=self.stdout)

        self.volume = VolumeController(runner=run, which=available, clock=lambda: self.now)

    def test_readback_is_actual_and_uses_default_sink(self):
        result = self.volume.set_volume(80)
        self.assertEqual(result["volume"], 42)
        self.assertEqual(result["backend"], "pipewire")
        self.assertFalse(result["muted"])
        self.assertIn("@DEFAULT_AUDIO_SINK@", self.calls[0][0])
        self.assertIn("--limit", self.calls[0][0])
        self.assertEqual(self.calls[1][0][-1], "0")

    def test_clamps_range_and_zero_mutes(self):
        self.volume.set_volume(1000)
        self.assertEqual(self.calls[0][0][3], "1.0000")
        self.calls.clear()
        self.stdout = "Volume: 0.00 [MUTED]\n"
        result = self.volume.set_volume(-1)
        self.assertEqual(self.calls[0][0][3], "0.0000")
        self.assertEqual(self.calls[1][0][-1], "1")
        self.assertTrue(result["muted"])

    def test_invalid_values_never_call_subprocess(self):
        for value in (True, False, math.nan, math.inf, -math.inf, "20", None):
            with self.subTest(value=value), self.assertRaises(MediaError):
                self.volume.set_volume(value)
        self.assertEqual(self.calls, [])

    def test_missing_server_never_returns_placeholder_volume(self):
        self.code = 1
        result = self.volume.snapshot()
        self.assertFalse(result["available"])
        self.assertIsNone(result["volume"])
        self.assertEqual(result["error"], "pipewire_unavailable")
        with self.assertRaises(MediaError):
            self.volume.set_volume(50)

    def test_unavailable_binary_and_malformed_readback(self):
        volume = VolumeController(which=lambda name: None)
        self.assertFalse(volume.available())
        self.assertEqual(volume.snapshot()["error"], "wpctl_unavailable")
        self.stdout = "Volume: NaN"
        self.assertEqual(self.volume.snapshot()["error"], "invalid_volume_readback")

    def test_entire_set_operation_shares_deadline(self):
        self.elapsed_per_command = 2
        with self.assertRaisesRegex(MediaError, "volume_timeout"):
            self.volume.set_volume(50)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([call[1]["timeout"] for call in self.calls], [3, 1])

    def test_mute_readback_and_amplification_are_not_fabricated(self):
        self.stdout = "Volume: 1.25 [MUTED]"
        self.assertEqual(self.volume.set_mute(True)["volume"], 125)
        with self.assertRaises(MediaError):
            self.volume.set_mute(1)


class FakeCamera:
    def __init__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.returncode = None
        self.signals = []
        self.stubborn = False
        self.killed = False
        Path(args[args.index("--output") + 1]).write_bytes(b"fake MP4 for mocked ffprobe only")

    def poll(self):
        return self.returncode

    def send_signal(self, value):
        self.signals.append(value)
        if not self.stubborn:
            self.returncode = 0

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self.returncode

    def terminate(self):
        if not self.stubborn:
            self.returncode = -signal.SIGTERM

    def kill(self):
        self.killed = True
        self.returncode = -signal.SIGKILL


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "records"
        self.processes, self.calls = [], []
        self.duration = "3.5"
        self.streams = [{"codec_type": "video"}]
        self.ffmpeg_code = 0
        self.free = 1024 * 1024 * 1024
        self.run_id = str(uuid.uuid4())

        def popen(args, **kwargs):
            process = FakeCamera(args, **kwargs)
            self.processes.append(process)
            return process

        def runner(args, **kwargs):
            self.calls.append((args, kwargs))
            if args[0].endswith("ffprobe"):
                return SimpleNamespace(returncode=0, stdout=json.dumps({
                    "format": {"duration": self.duration}, "streams": self.streams}))
            if self.ffmpeg_code == 0:
                Path(args[-1]).write_bytes(b"fake JPEG")
            return SimpleNamespace(returncode=self.ffmpeg_code, stdout="")

        self.manager = RecordManager(
            self.root, enabled=True, which=available, popen=popen, runner=runner,
            wall_clock=lambda: 1700000000, disk_usage=lambda path: SimpleNamespace(free=self.free))

    def start(self):
        return self.manager.start(self.run_id, "yogicok")

    def test_capture_disabled_by_default_without_any_camera_access(self):
        manager = RecordManager(self.root)
        self.assertEqual(manager.capability(), {"recording_supported": False, "reason": "capture_disabled"})
        with self.assertRaisesRegex(MediaError, "capture_disabled"):
            manager.start(self.run_id, "yogicok")
        self.assertFalse(self.root.exists())
        self.assertEqual(self.processes, [])

    def test_missing_binaries_report_unsupported(self):
        self.manager.which = lambda name: None
        self.assertFalse(self.manager.capability()["recording_supported"])
        with self.assertRaises(MediaError):
            self.start()
        self.assertEqual(self.processes, [])

    def test_complete_record_is_published_atomically_and_has_no_private_name(self):
        record_id = self.start()
        self.assertEqual(self.manager.state, "recording")
        self.assertEqual(self.manager.active_record_id, record_id)
        self.assertEqual(self.manager.list_records(), [])
        self.assertFalse((self.root / record_id).exists())
        self.assertIn("libav", self.processes[0].args)
        self.assertIn("--libav-format", self.processes[0].args)
        self.assertIn("60000", self.processes[0].args)
        result = self.manager.finish()
        self.assertEqual(result["id"], record_id)
        self.assertEqual(result["run_id"], self.run_id)
        self.assertEqual(result["duration_seconds"], 3.5)
        self.assertEqual(result["source"], "robot")
        self.assertEqual(result["video"], "video.mp4")
        self.assertEqual(result["thumbnail"], "thumbnail.jpg")
        self.assertEqual(set(result), RecordManager.METADATA_KEYS)
        self.assertEqual(self.processes[0].signals, [signal.SIGINT])
        self.assertEqual(self.manager.list_records(), [result])
        self.assertEqual(self.manager.resolve_file(record_id, "video"), self.root / record_id / "video.mp4")
        self.assertEqual(self.manager.state, "idle")
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / record_id / "video.mp4").stat().st_mode & 0o777, 0o600)

    def test_overlapping_capture_rejected_and_abort_publishes_nothing(self):
        self.start()
        with self.assertRaisesRegex(MediaError, "recording_busy"):
            self.start()
        self.manager.abort()
        self.assertEqual(self.manager.list_records(), [])
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertIsNone(self.manager.active_record_id)
        self.start()
        self.manager.abort()

    def test_disk_full_fails_before_opening_camera(self):
        self.free = 0
        with self.assertRaisesRegex(MediaError, "record_storage_full"):
            self.start()
        self.assertEqual(self.processes, [])
        self.assertEqual(self.manager.state, "error")

    def test_bad_ids_and_traversal_are_rejected(self):
        for record_id in ("../video", "/etc/passwd", "x", str(uuid.uuid4()).upper()):
            with self.subTest(record_id=record_id), self.assertRaises(MediaError):
                self.manager.resolve_file(record_id, "video")
        for run_id in ("test", "../run", True):
            with self.assertRaises(MediaError):
                self.manager.start(run_id, "yogicok")
        for play_id in ("../play", "Child name", "", "x" * 65):
            with self.assertRaises(MediaError):
                self.manager.start(self.run_id, play_id)
        self.assertEqual(self.processes, [])

    def test_capture_process_failure_does_not_publish(self):
        self.start()
        self.processes[0].returncode = 1
        with self.assertRaisesRegex(MediaError, "camera_capture_failed"):
            self.manager.finish()
        self.assertEqual(self.manager.state, "error")
        self.assertEqual(self.manager.list_records(), [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_probe_duration_or_no_video_never_publishes(self):
        for duration in ("nan", "inf", "-2", "0", "700", "unavailable"):
            self.duration = duration
            self.start()
            with self.subTest(duration=duration), self.assertRaisesRegex(MediaError, "invalid_record_video"):
                self.manager.finish()
            self.assertEqual(self.manager.list_records(), [])
        self.duration, self.streams = "2", []
        self.start()
        with self.assertRaisesRegex(MediaError, "invalid_record_video"):
            self.manager.finish()

    def test_thumbnail_failure_does_not_leave_a_visible_record(self):
        self.ffmpeg_code = 1
        self.start()
        with self.assertRaisesRegex(MediaError, "record_finalize_failed"):
            self.manager.finish()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_stuck_capture_is_killed_boundedly_and_not_saved(self):
        self.start()
        self.processes[0].stubborn = True
        with self.assertRaisesRegex(MediaError, "camera_stop_timeout"):
            self.manager.finish()
        self.assertTrue(self.processes[0].killed)
        self.assertEqual(self.manager.list_records(), [])

    def test_unreapable_camera_keeps_handle_and_blocks_next_capture(self):
        self.start()
        process = self.processes[0]
        process.stubborn = True
        process.kill = lambda: None
        with self.assertRaises(MediaError):
            self.manager.finish()
        self.assertIsNotNone(self.manager.active_record_id)
        with self.assertRaisesRegex(MediaError, "recording_busy"):
            self.start()
        with self.assertRaisesRegex(MediaError, "camera_abort_failed"):
            self.manager.abort()
        process.returncode = -signal.SIGKILL
        self.manager.abort()
        self.assertIsNone(self.manager.active_record_id)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_or_symlinked_record_files_are_not_served(self):
        record_id = self.start()
        self.manager.finish()
        target = self.root / record_id / "video.mp4"
        target.unlink()
        target.symlink_to(Path(self.temp.name) / "elsewhere.mp4")
        target.resolve().write_bytes(b"other private file")
        self.assertEqual(self.manager.list_records(), [])
        with self.assertRaisesRegex(MediaError, "record_not_found"):
            self.manager.resolve_file(record_id, "video")

    def test_edited_metadata_cannot_select_arbitrary_file_or_expose_name(self):
        record_id = self.start()
        result = self.manager.finish()
        result["video"] = "../../private.mp4"
        (self.root / record_id / "metadata.json").write_text(json.dumps(result))
        self.assertEqual(self.manager.list_records(), [])
        with self.assertRaises(MediaError):
            self.manager.resolve_file(record_id, "video")


if __name__ == "__main__":
    unittest.main()
