#!/usr/bin/env python3
"""One explicitly authorized dance. Terminal status follows confirmed cleanup."""

import argparse
from contextlib import redirect_stdout
import json
import signal
import sys
import time

from dance_sequence import load_dance_config
from integrated_sequence import IntegratedSequence
from motion_profile import load_profile
from oled_renderer import load_calibration
from test_dance_once import DanceTestBackend, MAX_TEST_SECONDS, validate_test


def phase_for(stage):
    if "look_here" in stage or "follow_me" in stage:
        return "greeting"
    if "return" in stage or "response" in stage:
        return "return"
    if "goodbye" in stage or "finish" in stage:
        return "goodbye"
    if "prepare" in stage or "raise" in stage or "offset" in stage:
        return "prepare"
    return "dance"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-5v-and-clear", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_5v_and_clear:
        return 2
    output = sys.stdout

    def emit(state, phase, progress):
        output.write(json.dumps(dict(state=state, phase=phase, progress=progress), separators=(",", ":")) + "\n")
        output.flush()

    stopping = False

    def stop_signal(*unused):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop_signal)
    try:
        with redirect_stdout(sys.stderr):
            profile, eyes, settings = load_profile(), load_calibration(), load_dance_config()
            steps = validate_test(profile, eyes, settings, True)
            if stopping:
                emit("stopped", "idle", 0)
                return 0
            with DanceTestBackend(profile, eyes, settings, confirmed=True) as backend:
                runner = IntegratedSequence(backend, profile, eyes, settings)
                started, previous = time.monotonic(), None
                if not stopping:
                    runner.start("dance")
                while runner.state == "running":
                    if stopping or time.monotonic() - started >= MAX_TEST_SECONDS:
                        runner.stop()
                        break
                    runner.tick(time.monotonic())
                    if runner.state == "running" and runner.stage != previous:
                        previous = runner.stage
                        completed = next((i for i, step in enumerate(steps) if step.name == runner.stage), 0)
                        emit("running", phase_for(runner.stage), completed / len(steps))
                    time.sleep(1 / eyes["fps"])
                if runner.state == "error":
                    raise RuntimeError(runner.error)
                terminal = "completed" if runner.state == "completed" else "stopped"
            # HardwareBackend.__exit__ must finish ACK,STOP/audio cleanup first.
            emit(terminal, "goodbye" if terminal == "completed" else "idle", 1 if terminal == "completed" else 0)
            return 0
    except Exception as error:
        print(f"[CUVO worker] {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        emit("error", "idle", 0)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
