"""Alternating-arm dance planning; no serial, GPIO, BLE or sound playback."""

import json
import math
from pathlib import Path
import wave

from motion_profile import ProfileError
from oled_motion import EyePose, head_gaze_pose, blink_duration

DEFAULT_DANCE_CONFIG = Path(__file__).with_name("dance_config.json")
AUDIO_DIR = Path(__file__).with_name("audio")
DANCE_AUDIO = tuple(AUDIO_DIR / name for name in
                   ("cuvo_look_here.wav", "cuvo_follow_me.wav", "cuvo_goodbye.wav"))


def load_dance_config(path=DEFAULT_DANCE_CONFIG):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def build_dance_steps(profile, eye_config, settings):
    from integrated_sequence import Step

    if isinstance(settings, dict) and settings.get("schema_version") == 2:
        from choreography import build_choreography_steps
        return build_choreography_steps(profile, eye_config, settings)

    keys = {"schema_version", "arm_x_min_relative_deg", "arm_x_max_relative_deg",
            "arm_y_raise_relative_deg", "head_left_deg", "head_right_deg",
            "swing_duration_ms", "raise_duration_ms", "return_duration_ms", "cycles",
            "gaze_horizontal_px", "gaze_down_px", "response_hold_seconds"}
    if not isinstance(settings, dict) or set(settings) != keys or settings["schema_version"] != 1:
        raise ProfileError("Unsupported dance settings")
    for key in keys - {"response_hold_seconds"}:
        if type(settings[key]) is not int:
            raise ProfileError(f"Dance setting {key} must be an integer")
    for key in ("swing_duration_ms", "raise_duration_ms", "return_duration_ms"):
        if not 1 <= settings[key] <= 60000:
            raise ProfileError(f"Dance duration {key} must be in 1..60000 ms")
    if not 1 <= settings["cycles"] <= 16:
        raise ProfileError("Dance cycles must be in 1..16")
    wait = settings["response_hold_seconds"]
    if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not math.isfinite(wait) or not 0 <= wait <= 30:
        raise ProfileError("Dance response wait must be in 0..30 seconds")
    low, high = settings["arm_x_min_relative_deg"], settings["arm_x_max_relative_deg"]
    if low >= high:
        raise ProfileError("Dance X targets must be ordered relative joint angles")
    y = settings["arm_y_raise_relative_deg"]
    raised = profile.joint_targets({"right_shoulder_y": y, "left_shoulder_y": y})
    # Alternating relative poses can have same-sign servo changes on mirrored mounts.
    phases = [profile.joint_targets({"right_shoulder_x": high, "left_shoulder_x": low}),
              profile.joint_targets({"right_shoulder_x": low, "left_shoulder_x": high})]
    neutral = profile.data["axes"]["head"]["neutral"]
    left, right = settings["head_left_deg"], settings["head_right_deg"]
    for angle in (left, right):
        profile.check_angle("head", angle)
    gaze = [head_gaze_pose(angle, neutral, left, right, settings["gaze_horizontal_px"],
                           settings["gaze_down_px"]) for angle in (left, right)]
    for path in DANCE_AUDIO:
        with wave.open(str(path), "rb") as file:
            if not file.getnframes() or file.getcomptype() != "NONE":
                raise ProfileError(f"Dance requires nonempty PCM WAV: {path.name}")
    home = profile.targets("home")
    if any(angle is None for angle in home.values()):
        raise ProfileError("Dance home pose needs all head and arm angles")
    swing, return_ms = settings["swing_duration_ms"], settings["return_duration_ms"]
    steps = [Step("dance_prepare", home, return_ms, eyes="open"),
             Step("dance_look_here", audio=DANCE_AUDIO[0], eyes="open"),
             Step("dance_follow_me", audio=DANCE_AUDIO[1], eyes="open"),
             Step("dance_raise_arms", raised, settings["raise_duration_ms"], eyes="open"),
             Step("dance_arm_offset", phases[1], swing, eyes="open")]
    previous_eye = EyePose()
    for cycle in range(1, settings["cycles"] + 1):
        for phase, angle, pose, label in zip(phases, (left, right), gaze, ("left", "right")):
            steps.append(Step(f"dance_{cycle}_{label}", {**phase, 0: angle}, swing,
                              eyes="transition", eye_from=previous_eye, eye_to=pose))
            previous_eye = pose
    steps.extend([Step("dance_return_home", home, return_ms, eyes="transition",
                       eye_from=previous_eye, eye_to=EyePose()),
                  Step("dance_response_wait", hold=wait, eyes="open"),
                  Step("dance_goodbye", audio=DANCE_AUDIO[2], eyes="open"),
                  Step("dance_finish_blink", hold=blink_duration(eye_config), eyes="blink")])
    return steps
