#!/usr/bin/env python3
"""One cancellable preset per isolated process, with optional real recording."""

from contextlib import redirect_stdout
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class ExhibitWorker:
    """Nonblocking parent transport. Only the worker owns serial/OLED/audio."""
    def __init__(self, specification):
        self.process = subprocess.Popen([sys.executable, "-u", str(Path(__file__))],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        start_new_session=True)
        self.process.stdin.write(json.dumps(specification, ensure_ascii=False).encode())
        self.process.stdin.close()
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer, self.terminal = bytearray(), None

    def poll(self):
        try:
            self.buffer.extend(os.read(self.process.stdout.fileno(), 8192))
        except BlockingIOError:
            pass
        exit_code = self.process.poll()
        if exit_code is not None:
            # The child can write its terminal line between read() and poll().
            while True:
                chunk = os.read(self.process.stdout.fileno(), 8192)
                if not chunk:
                    break
                self.buffer.extend(chunk)
                if len(self.buffer) > 8192:
                    raise ValueError("Worker output too large")
        if len(self.buffer) > 8192:
            raise ValueError("Worker output too large")
        events = []
        while b"\n" in self.buffer:
            raw, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            event = json.loads(raw)
            if (not isinstance(event, dict) or set(event) - {"state", "phase", "progress", "recording", "latest_record"}
                    or event.get("state") not in ("running", "completed", "stopped", "error")
                    or event.get("phase") not in ("idle", "greeting", "prepare", "dance", "return", "goodbye", "observe", "play", "saving")):
                raise ValueError("Invalid exhibit worker event")
            progress = event.get("progress")
            if type(progress) not in (int, float) or not math.isfinite(progress) or not 0 <= progress <= 1:
                raise ValueError("Invalid exhibit progress")
            if event["state"] != "running":
                self.terminal = event
            events.append(event)
        return events, exit_code

    def terminate(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)

    def kill(self):
        # Camera/ffmpeg inherit this group, so a stuck finalizer cannot orphan them.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def close(self):
        self.process.wait(timeout=1)
        self.process.stdout.close()


def main():
    output, stopping = sys.stdout, False

    def stop_signal(*unused):
        nonlocal stopping
        stopping = True

    def emit(state, phase="idle", progress=0, **extra):
        output.write(json.dumps(dict(state=state, phase=phase, progress=progress, **extra), separators=(",", ":")) + "\n")
        output.flush()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop_signal)
    records = None
    try:
        spec = json.loads(sys.stdin.buffer.read(4096))
        with redirect_stdout(sys.stderr):
            from exhibit_media import RecordManager, MediaError
            from exhibit_sequences import ExhibitCatalog
            from integrated_hardware import HardwareBackend
            from integrated_sequence import IntegratedSequence
            from motion_profile import load_profile, ProfileError
            from oled_renderer import load_calibration
            from dance_sequence import load_dance_config
            from test_dance_once import DanceTestBackend, validate_test
            profile, eyes = load_profile(), load_calibration()
            if spec.get("play_id") == "dance":
                settings = load_dance_config()
                steps = validate_test(profile, eyes, settings, spec.get("dance_confirmed") is True)
                backend = DanceTestBackend(profile, eyes, settings, confirmed=True)
            else:
                catalog = ExhibitCatalog(profile, eyes, spec.get("exhibit_confirmed") is True)
                steps = catalog.build(spec.get("play_id"), spec.get("scene_id"), spec.get("name"), spec.get("reset", False))

                class PresetBackend(HardwareBackend):
                    def _require_ready(self):
                        catalog.validate(steps)
                        self.approved = [(dict(step.targets), step.duration_ms) for step in steps if step.targets]
                        self.next_motion = 0

                    def start_motion(self, targets, duration_ms):
                        if self.next_motion >= len(self.approved) or (targets, duration_ms) != self.approved[self.next_motion]:
                            raise ProfileError("Motion outside compiled exhibit preset")
                        self.next_motion += 1
                        return super().start_motion(targets, duration_ms)

                backend = PresetBackend(profile, eyes, include_demo_poses=False)
            recording = {"state": "disabled", "error": None}
            if spec.get("recording_enabled") and not spec.get("reset"):
                records = RecordManager(spec["record_root"], enabled=True, child_new_session=False)
            if stopping:
                emit("stopped")
                return 0
            with backend:
                if records:
                    try:
                        records.start(spec["run_id"], spec.get("play_id") or "scene_" + spec["scene_id"])
                        recording = {"state": "recording", "error": None}
                    except MediaError as error:
                        recording = {"state": "error", "error": str(error)}
                runner = IntegratedSequence(backend, profile, eyes)
                started, previous = time.monotonic(), None
                if not stopping:
                    runner.start_steps("camera" if spec.get("scene_id") == "02" else "exhibit", steps)
                while runner.state == "running":
                    if stopping or time.monotonic() - started >= 35:
                        runner.stop()
                        break
                    runner.tick(time.monotonic())
                    if runner.state == "running" and runner.stage != previous:
                        previous = runner.stage
                        phase = "dance" if spec.get("play_id") == "dance" else "play"
                        emit("running", phase, runner.index / len(steps), recording=recording)
                    time.sleep(1 / eyes["fps"])
                if runner.state == "error":
                    raise RuntimeError("Preset STOP or execution failed")
                terminal = "completed" if runner.state == "completed" and not stopping else "stopped"
            # STOP is acknowledged and hardware is released before potentially slow MP4 finalization.
            latest = None
            if records and records.active_record_id:
                if terminal == "stopped":
                    records.abort()
                    recording = {"state": "idle", "error": None}
                else:
                    emit("running", "saving", 1, recording={"state": "saving", "error": None})
                    try:
                        latest = records.finish()
                        recording = {"state": "saved", "error": None}
                    except MediaError as error:
                        recording = {"state": "error", "error": str(error)}
            if stopping:
                terminal = "stopped"
            emit(terminal, "goodbye" if terminal == "completed" else "idle",
                 1 if terminal == "completed" else 0, recording=recording, latest_record=latest)
            return 0
    except Exception as error:
        # No child name or payload is logged.
        print(f"[CUVO exhibit] {type(error).__name__}: execution failed", file=sys.stderr, flush=True)
        emit("error", recording={"state": "error", "error": "worker_execution_failed"})
        return 1
    finally:
        if records:
            records.abort()


if __name__ == "__main__":
    raise SystemExit(main())
