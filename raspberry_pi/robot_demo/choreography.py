"""Named choreography compiled to the same Steps used by the robot runtime."""

from pathlib import Path
import math
import re
import wave

from motion_profile import CHANNELS, ProfileError
from oled_motion import EyePose, blink_duration

CHOREOGRAPHY_DIR = Path(__file__).with_name("choreographies")
SOUNDS = {name: Path(__file__).with_name("audio") / f"cuvo_groove_{name}.wav"
          for name in ("kick", "snare", "hat")}


def _number(value, low, high):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and low <= value <= high)


def build_choreography_steps(profile, eye_config, settings):
    from integrated_sequence import Step

    required = {"schema_version", "id", "title", "bpm", "passive_elbows", "steps"}
    if set(settings) != required or type(settings["schema_version"]) is not int or settings["schema_version"] != 2:
        raise ProfileError("Unsupported choreography schema")
    if (not isinstance(settings["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", settings["id"])
            or not isinstance(settings["title"], str) or not settings["title"]):
        raise ProfileError("Unknown choreography")
    if not _number(settings["bpm"], 60, 140):
        raise ProfileError("Choreography BPM must be in 60..140")
    if settings["passive_elbows"] != {"minimum": 120, "maximum": 180, "preset": 150,
                                      "mechanism": "manual_freestop"}:
        raise ProfileError("Elbows are manual fixed joints, not servo channels")
    if not isinstance(settings["steps"], list) or not 1 <= len(settings["steps"]) <= 64:
        raise ProfileError("Choreography needs 1..64 steps")
    result, previous_eye, names = [], EyePose(), set()
    for item in settings["steps"]:
        required_step = {"name", "label", "duration_ms", "relative", "eye"}
        if not isinstance(item, dict) or not required_step <= set(item) or set(item) - required_step - {"sound", "beat"}:
            raise ProfileError("Invalid choreography step fields")
        if not isinstance(item["name"], str) or not item["name"] or item["name"] in names:
            raise ProfileError("Step names must be nonempty and unique")
        if not isinstance(item["label"], str) or not item["label"]:
            raise ProfileError("Each step requires a label")
        names.add(item["name"])
        duration = item["duration_ms"]
        if type(duration) is not int or not 100 <= duration <= 3000:
            raise ProfileError("Choreography durations must be 100..3000 ms")
        relative = item["relative"]
        if not isinstance(relative, dict) or set(relative) != set(CHANNELS):
            raise ProfileError("Each pose must specify exactly the six motor axes")
        targets = {}
        for name, value in relative.items():
            if type(value) is not int:
                raise ProfileError("Relative angles must be integers")
            if "joint" in profile.data["axes"][name]:
                angle = profile.servo_angle(name, value)
            else:
                angle = profile.data["axes"][name]["neutral"] + value
                profile.check_angle(name, angle)
            targets[CHANNELS[name]] = angle
        eye = item["eye"]
        if eye == "blink":
            if duration / 1000 < blink_duration(eye_config):
                raise ProfileError("Blink step is too short")
            mode, target_eye = "blink", EyePose()
        else:
            if not isinstance(eye, dict) or set(eye) != {"openness", "offset_x", "offset_y"}:
                raise ProfileError("Invalid eye pose")
            if (not _number(eye["openness"], 0, 1) or not _number(eye["offset_x"], -128, 128)
                    or not _number(eye["offset_y"], -128, 128)):
                raise ProfileError("Eye pose exceeds display limits")
            mode, target_eye = "transition", EyePose(**eye)
        if "beat" in item and (type(item["beat"]) is not int or not 1 <= item["beat"] <= 16):
            raise ProfileError("Beat must be in 1..16")
        if "beat" in item and duration != round(60000 / settings["bpm"]):
            raise ProfileError("Beat duration disagrees with the BPM")
        sound = item.get("sound")
        if sound is not None and (not isinstance(sound, str) or sound not in SOUNDS):
            raise ProfileError("Unknown choreography sound")
        audio = SOUNDS[sound] if sound else None
        if audio:
            with wave.open(str(audio), "rb") as file:
                if not file.getnframes() or file.getcomptype() != "NONE":
                    raise ProfileError("Choreography audio must be nonempty PCM WAV")
        result.append(Step(item["name"], targets, duration, audio,
                           eyes=mode, eye_from=previous_eye, eye_to=target_eye))
        previous_eye = target_eye
    if result[-1].targets != profile.targets("startup"):
        raise ProfileError("Choreography must finish at the six-axis neutral pose")
    if sum(step.duration_ms for step in result) > 14500:
        raise ProfileError("Preview choreography must fit within 15 seconds including scheduling")
    return result
