#!/usr/bin/env python3
"""Blink the calibrated eye pair indefinitely; never import servo/audio control."""

import signal
import sys
import time

from oled_controller import EyeController
from oled_motion import EyePose, blink_openness
from oled_renderer import DEFAULT_CONFIG, EyeRenderer, load_aperture, load_calibration


def main():
    stopping = False

    def stop(*unused):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    try:
        config = load_calibration()
        aperture = load_aperture(DEFAULT_CONFIG.parent / config["aperture_file"], config)
        if stopping:
            return 0
        with EyeController(EyeRenderer(config, aperture), swap=True) as eyes:
            started = time.monotonic()
            print("[CUVO eyes] standby blink READY", file=sys.stderr, flush=True)
            while not stopping:
                eyes.show(EyePose(openness=blink_openness(config, time.monotonic() - started)))
                time.sleep(1 / config["fps"])
        print("[CUVO eyes] standby released", file=sys.stderr, flush=True)
        return 0
    except Exception as error:
        print(f"[CUVO eyes] {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
