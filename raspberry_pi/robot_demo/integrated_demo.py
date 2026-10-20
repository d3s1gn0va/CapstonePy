#!/usr/bin/env python3
"""Opt-in CUVO integration. Default simulation never opens physical devices."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import signal
import subprocess
import time
import wave

import config
from integrated_sequence import IntegratedSequence, SimulatedBackend
from motion_profile import DEFAULT_PROFILE, load_profile


def audio_lengths(action="demo", paths=None):
    result = {}
    if paths is None:
        if action == "dance":
            from dance_sequence import DANCE_AUDIO
            paths = DANCE_AUDIO
        else:
            paths = (config.AUDIO_NAME_CALL, config.AUDIO_LETS_PLAY)
    for path in paths:
        with wave.open(str(path), "rb") as file:
            result[path.name] = file.getnframes() / file.getframerate()
    return result


def simulate(profile, eye_config, action, dance_settings=None):
    paths = None
    if action == "dance" and dance_settings is not None:
        from dance_sequence import build_dance_steps
        paths = {step.audio for step in build_dance_steps(profile, eye_config, dance_settings) if step.audio}
    backend = SimulatedBackend(audio_lengths(action, paths))
    runner = IntegratedSequence(backend, profile, eye_config, dance_settings)
    runner.start(action)
    for frame in range(60 * 30):
        backend.now = frame / 30
        runner.tick(backend.now)
        if runner.state != "running":
            break
    print(json.dumps({"mode": "simulation_only", "state": runner.state,
                      "elapsed_virtual_seconds": backend.now, "stages": runner.events,
                      "commands": backend.commands, "unconfirmed": profile.missing(include_poses=action != "dance"),
                      "error": runner.error}, ensure_ascii=False, indent=2))
    return 0 if runner.state == "completed" else 1


def run_hardware(profile, eye_config, button_action="demo", dance_settings=None):
    # Fail before opening USB serial: opening the port can reset the Mega.
    profile.require_ready(include_poses=button_action != "dance")
    from gpiozero import Button
    from integrated_hardware import HardwareBackend

    with ExitStack() as stack:
        backend = stack.enter_context(HardwareBackend(profile, eye_config, include_demo_poses=button_action != "dance"))
        buttons = [stack.enter_context(Button(pin, pull_up=True, bounce_time=config.BUTTON_BOUNCE_SEC))
                   for pin in (config.BUTTON_GPIO, config.CAMERA_BUTTON_GPIO, config.POWER_OFF_BUTTON_GPIO)]
        runner = IntegratedSequence(backend, profile, eye_config, dance_settings)
        runner.start("startup")
        previous = [button.is_pressed for button in buttons]
        stopping = False

        def shutdown_signal(*unused):
            nonlocal stopping
            stopping = True

        old_handlers = {sig: signal.signal(sig, shutdown_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
        for sig, old in old_handlers.items():
            stack.callback(signal.signal, sig, old)
        print("[CUVO] Integrated runtime; single serial/OLED owner. No camera recording.")
        last_stage = None
        while not stopping:
            pressed = [button.is_pressed for button in buttons]
            rising = [current and not old for current, old in zip(pressed, previous)]
            previous = pressed
            if rising[2]:
                runner.stop()
                # Keep PWM holding; never auto-return or DISABLE when shutting down.
                backend.stop()
                backend.abort_audio()
                backend.led(False)
                result = subprocess.run(["sudo", "-n", "shutdown", "-h", "now"])
                if result.returncode:
                    print("[CUVO] Shutdown permission failure; runtime is stopping")
                return result.returncode
            if rising[0]:
                runner.start(button_action)
            elif rising[1]:
                runner.start("camera")
            runner.tick(time.monotonic())
            if runner.stage != last_stage:
                print(f"[CUVO] {runner.state}: {runner.stage}")
                last_stage = runner.stage
            if runner.state == "error":
                print(f"[CUVO] Error; no automatic return: {runner.error}")
                return 1
            time.sleep(1 / eye_config["fps"])
        runner.stop()
        return 0 if runner.state != "error" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulate", action="store_true", help="No physical-device access (default)")
    mode.add_argument("--hardware", action="store_true", help="Requires calibrated axes and matching firmware")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--action", choices=("demo", "camera", "startup", "dance"), default="demo",
                        help="Simulation action; on hardware dance selects the exhibition button action")
    parser.add_argument("--dance-config", type=Path, help="Explicit choreography JSON; default exhibition dance is unchanged")
    args = parser.parse_args(argv)
    try:
        profile = load_profile(args.profile)
        with Path(__file__).with_name("oled_pair_calibration.json").open(encoding="utf-8") as file:
            eye_config = json.load(file)
        settings = None
        if args.dance_config:
            if args.action != "dance":
                raise ValueError("--dance-config requires --action dance")
            from dance_sequence import load_dance_config
            settings = load_dance_config(args.dance_config)
        if args.hardware:
            if args.action == "dance":
                from dance_sequence import build_dance_steps, load_dance_config
                build_dance_steps(profile, eye_config, settings if settings is not None else load_dance_config())
            profile.require_ready(include_poses=args.action != "dance")
            from oled_renderer import load_calibration
            eye_config = load_calibration()
            if args.action == "dance":
                return run_hardware(profile, eye_config, button_action="dance", dance_settings=settings)
            return run_hardware(profile, eye_config)
        return simulate(profile, eye_config, args.action, settings)
    except (ValueError, RuntimeError, OSError, wave.Error) as error:
        print(f"[CUVO refused] {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
