"""Exhibit presets compiled against the unchanged calibrated six-axis profile.

These new gestures are locally prepared, not physically verified. The separate
exhibit confirmation is deliberately not implied by the old dance-only flag.
"""

from pathlib import Path
import unicodedata
import wave

from dance_sequence import build_dance_steps, load_dance_config
from integrated_sequence import Step
from motion_profile import CHANNELS, ProfileError
from oled_motion import blink_duration

AUDIO = Path(__file__).with_name("audio")
PLAYS = ("yogicok", "name_call", "dance")
SCENES = ("01", "02", "03", "04", "05_06", "09")
# This is the previously confirmed fixed-name recording, not a TTS placeholder.
KNOWN_NAMES = {"지우": AUDIO / "01_name_call.wav"}
CUES = {"invite": AUDIO / "02_lets_play.wav",
        "eyes": AUDIO / "cuvo_where_eyes.wav",
        "hands": AUDIO / "cuvo_show_hands.wav",
        "farewell": AUDIO / "cuvo_see_you.wav"}


def normalize_name(value):
    if not isinstance(value, str):
        raise ValueError("child_name must be text")
    value = unicodedata.normalize("NFC", value.strip())
    if len(value) > 30 or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("child_name must be at most 30 visible characters")
    return value


def valid_wav(path):
    try:
        with wave.open(str(path), "rb") as source:
            return source.getcomptype() == "NONE" and source.getnframes() > 0
    except (OSError, EOFError, wave.Error):
        return False


class ExhibitCatalog:
    def __init__(self, profile, eyes, confirmed=False, names=None, cues=None):
        self.profile, self.eyes, self.confirmed = profile, eyes, confirmed
        self.names = dict(KNOWN_NAMES if names is None else names)
        self.cues = dict(CUES if cues is None else cues)

    def voice_ready(self, name):
        return bool(name and name in self.names and valid_wav(self.names[name]))

    def requirements(self, play_id=None, scene_id=None):
        if play_id not in (*PLAYS, None) or scene_id not in (*SCENES, None):
            raise ValueError("Unknown preset")
        named = play_id == "name_call" or scene_id in ("04", "05_06")
        cues = []
        if named:
            cues.append("invite")
        if play_id == "yogicok" or scene_id in ("04", "05_06"):
            cues += ["eyes", "hands"]
        if scene_id == "09":
            cues.append("farewell")
        return named, cues

    def missing_assets(self, play_id=None, scene_id=None, name=None):
        named, cues = self.requirements(play_id, scene_id)
        missing = [key for key in cues if key not in self.cues or not valid_wav(self.cues[key])]
        if named and not self.voice_ready(name):
            missing.append("child_name_voice")
        return missing

    def build(self, play_id=None, scene_id=None, name=None, reset=False):
        if reset:
            steps = [Step("return_home", self.profile.targets("startup"), 3000, eyes="open")]
        elif play_id == "dance":
            return build_dance_steps(self.profile, self.eyes, load_dance_config())
        else:
            if not ((play_id in PLAYS and scene_id is None) or (scene_id in SCENES and play_id is None)):
                raise ValueError("Select exactly one known preset")
            missing = self.missing_assets(play_id, scene_id, name)
            if missing:
                raise ValueError("필요한 음성이 준비되지 않았어요: " + ", ".join(missing))
            home = self.profile.targets("home")
            # Keep arm/head motions within the existing limited dance envelope.
            raise_right = self.profile.joint_targets({"right_shoulder_x": 60, "right_shoulder_y": 30})
            raise_left = self.profile.joint_targets({"left_shoulder_x": 60, "left_shoulder_y": 30})
            steps = []
            if scene_id == "01":
                steps = [Step("eyes_open", hold=1, eyes="open"),
                         Step("eyes_blink", hold=blink_duration(self.eyes), eyes="blink")]
            elif scene_id == "02":
                steps = [Step("camera_left", {0: 75, 2: 105}, 1200, eyes="gaze"),
                         Step("camera_right", {0: 105, 2: 75}, 1600, eyes="gaze"),
                         Step("camera_center", {0: self.profile.data["axes"]["head"]["neutral"],
                                                2: self.profile.data["axes"]["crown"]["neutral"]}, 1200),
                         Step("eyes_blink", hold=blink_duration(self.eyes), eyes="blink")]
            elif scene_id == "03":
                steps = [Step("greeting_raise", raise_right, 1200),
                         Step("greeting_wave_low", self.profile.joint_targets({"right_shoulder_y": 15}), 600),
                         Step("greeting_wave_high", self.profile.joint_targets({"right_shoulder_y": 30}), 600),
                         Step("greeting_hold", hold=1, eyes="open"), Step("return_home", home, 1800)]
            elif scene_id == "09":
                steps = [Step("goodbye", raise_right, 1200, self.cues["farewell"]),
                         Step("goodbye_wave_low", self.profile.joint_targets({"right_shoulder_y": 15}), 600),
                         Step("goodbye_wave_high", self.profile.joint_targets({"right_shoulder_y": 30}), 600),
                         Step("goodbye_wait", hold=1), Step("return_home", home, 1800),
                         Step("eyes_close", hold=1, eyes="closed")]
            else:
                named, _ = self.requirements(play_id, scene_id)
                if named:
                    steps += [Step("name_call", {**raise_right, 0: 70}, 1200, self.names[name]),
                              Step("response_wait", hold=2, eyes="open"),
                              Step("invitation", raise_left, 1200, self.cues["invite"])]
                if play_id == "yogicok" or scene_id in ("04", "05_06"):
                    steps += [Step("yogicok_eyes", audio=self.cues["eyes"], eyes="blink"),
                              Step("response_wait_eyes", hold=3, eyes="open"),
                              Step("yogicok_hands", {**raise_right, **raise_left}, 1500, self.cues["hands"]),
                              Step("response_wait_hands", hold=3, eyes="open")]
                if scene_id == "05_06":
                    steps += [Step("greeting_wave_low", self.profile.joint_targets({"right_shoulder_y": 15}), 600),
                              Step("greeting_wave_high", self.profile.joint_targets({"right_shoulder_y": 30}), 600)]
                steps += [Step("return_home", home, 1800),
                          Step("finish_blink", hold=blink_duration(self.eyes), eyes="blink")]
        self.validate(steps)
        return steps

    def validate(self, steps):
        if not self.confirmed:
            raise ProfileError("New exhibit presets require --confirm-exhibit-scenes-and-clear")
        unknown = [field for field in self.profile.missing(include_poses=False)
                   if field != "power_verified" and not field.endswith(".verified")]
        if unknown:
            raise ProfileError("Exhibit calibration missing: " + ", ".join(unknown))
        by_channel = {channel: name for name, channel in CHANNELS.items()}
        for step in steps:
            if step.targets:
                if not 1 <= step.duration_ms <= 3000:
                    raise ProfileError("Exhibit movement duration outside 1..3000 ms")
                for channel, angle in step.targets.items():
                    if channel not in by_channel or angle is None:
                        raise ProfileError("Unknown exhibit target")
                    self.profile.check_angle(by_channel[channel], angle)

