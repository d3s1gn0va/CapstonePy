#!/usr/bin/env python3
"""Explicit, bounded five-axis bench test; never marks production verification true."""

import argparse
import signal
import time

from dance_sequence import build_dance_steps, load_dance_config
from integrated_hardware import HardwareBackend
from integrated_sequence import IntegratedSequence
from motion_profile import ProfileError, load_profile

TEST_LIMITS = {0: (60, 120), 1: (45, 125), 3: (0, 45), 4: (55, 135), 5: (135, 180)}
MAX_TEST_SECONDS = 35


def validate_test(profile, eye_config, settings, confirmed):
    if confirmed is not True:
        raise ProfileError("Dance test refused: --confirm-5v-and-clear is required")
    unknown = [field for field in profile.missing(include_poses=False)
               if field != "power_verified" and not field.endswith(".verified")]
    if unknown:
        raise ProfileError("Dance test calibration missing: " + ", ".join(unknown))
    steps = build_dance_steps(profile, eye_config, settings)
    if settings["cycles"] > 4 or not 500 <= settings["swing_duration_ms"] <= 800:
        raise ProfileError("Bench test is limited to four cycles and 500..800 ms swings")
    for step in steps:
        if step.targets:
            if not 1 <= step.duration_ms <= 3000:
                raise ProfileError("Bench motion must be no longer than 3000 ms")
            for channel, angle in step.targets.items():
                if channel not in TEST_LIMITS or not TEST_LIMITS[channel][0] <= angle <= TEST_LIMITS[channel][1]:
                    raise ProfileError("Motion exceeds the confirmed five-axis dance test scope")
    return steps


class DanceTestBackend(HardwareBackend):
    def __init__(self, profile, eye_config, settings, confirmed=False):
        super().__init__(profile, eye_config, include_demo_poses=False)
        self.settings, self.confirmed = settings, confirmed
        self.motion_index = 0

    def _require_ready(self):
        steps = validate_test(self.profile, self.eye_config, self.settings, self.confirmed)
        self.approved_motions = [(dict(step.targets), step.duration_ms)
                                 for step in steps if step.targets]

    def start_motion(self, targets, duration_ms):
        if self.motion_index >= len(self.approved_motions):
            raise ProfileError("The single approved dance motion plan is exhausted")
        if (targets, duration_ms) != self.approved_motions[self.motion_index]:
            raise ProfileError("Unexpected motion outside the approved dance plan")
        self.motion_index += 1
        return super().start_motion(targets, duration_ms)


def run_once(backend, profile, eye_config, settings, clock=time.monotonic,
             sleeper=time.sleep, should_stop=lambda: False):
    runner = IntegratedSequence(backend, profile, eye_config, settings)
    started, previous = clock(), None
    runner.start("dance")
    try:
        while runner.state == "running":
            now = clock()
            if should_stop() or now - started >= MAX_TEST_SECONDS:
                runner.stop()
                print("[CUVO dance] interrupted or 35-second deadline reached; no automatic return", flush=True)
                return 1
            runner.tick(now)
            if runner.stage != previous:
                print(f"[CUVO dance] {runner.state}: {runner.stage}", flush=True)
                previous = runner.stage
            sleeper(1 / eye_config["fps"])
        print(f"[CUVO dance] result={runner.state}, elapsed={clock() - started:.2f}s, error={runner.error}", flush=True)
        return 0 if runner.state == "completed" else 1
    finally:
        runner.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-5v-and-clear", action="store_true",
                        help="Physical test only: user confirmed 5V and the specified motion clearance")
    args = parser.parse_args(argv)
    if not args.confirm_5v_and_clear:
        print("[CUVO refused] --confirm-5v-and-clear is required; no devices opened")
        return 2
    stopping = False

    def stop_signal(*unused):
        nonlocal stopping
        stopping = True

    old = {sig: signal.signal(sig, stop_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        from oled_renderer import load_calibration
        profile, eyes, settings = load_profile(), load_calibration(), load_dance_config()
        validate_test(profile, eyes, settings, True)
        print("[CUVO dance] one physical test; crown excluded; production verification unchanged", flush=True)
        with DanceTestBackend(profile, eyes, settings, confirmed=True) as backend:
            return run_once(backend, profile, eyes, settings, should_stop=lambda: stopping)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"[CUVO refused] {error}", flush=True)
        return 2
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
