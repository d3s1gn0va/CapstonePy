import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo"))
from exhibit_worker import ExhibitWorker


class WorkerTransportTests(unittest.TestCase):
    def worker(self):
        worker = ExhibitWorker.__new__(ExhibitWorker)
        worker.process = SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 9), poll=lambda: 0)
        worker.buffer, worker.terminal = bytearray(), None
        return worker

    def test_terminal_written_between_read_and_exit_is_drained(self):
        worker = self.worker()
        event = {"state": "stopped", "phase": "idle", "progress": 0}
        with patch("exhibit_worker.os.read", side_effect=[BlockingIOError(), json.dumps(event).encode() + b"\n", b""]):
            events, code = worker.poll()
        self.assertEqual(code, 0)
        self.assertEqual(worker.terminal, event)
        self.assertEqual(events, [event])

    def test_untrusted_worker_output_rejected(self):
        for event in ({"state": "completed", "phase": "idle", "progress": float("nan")},
                      {"state": "completed", "phase": "idle", "progress": 1, "shell": "ignored"}):
            worker = self.worker()
            with patch("exhibit_worker.os.read", side_effect=[json.dumps(event).encode() + b"\n", b""]), self.assertRaises(ValueError):
                worker.poll()


if __name__ == "__main__":
    unittest.main()
