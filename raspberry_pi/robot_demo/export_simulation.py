#!/usr/bin/env python3
"""Record the real sequence runner with virtual devices, never opening hardware."""

import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import wave

from PIL import Image

from choreography import CHOREOGRAPHY_DIR
from dance_sequence import build_dance_steps, load_dance_config
from integrated_sequence import IntegratedSequence, SimulatedBackend
from motion_profile import load_profile
from oled_motion import EyePose
from oled_renderer import DEFAULT_CONFIG, EyeRenderer, load_aperture, load_calibration

ROOT = Path(__file__).parent
TICK_MS = 20
LEGACY_LABELS = {"dance_prepare": "준비", "dance_look_here": "여길 봐", "dance_follow_me": "따라 해 봐",
                 "dance_raise_arms": "팔 올리기", "dance_arm_offset": "교대 준비",
                 "dance_return_home": "기본 자세", "dance_response_wait": "기다리기",
                 "dance_goodbye": "마지막 인사", "dance_finish_blink": "깜박임"}


class RecordingBackend(SimulatedBackend):
    def __init__(self, profile, audio_lengths):
        super().__init__(audio_lengths)
        self.pose = {axis["channel"]: axis["neutral"] for axis in profile.data["axes"].values()}
        self.movement = None
        self.audio_events = []
        self.last_eye = EyePose()

    def sample_pose(self):
        if self.movement:
            started, duration, source, target = self.movement
            fraction = min(1.0, max(0.0, (self.now - started) / duration))
            # Match the Mega's linear command interpolation and positive rounding.
            for channel, angle in target.items():
                self.pose[channel] = math.floor(source[channel] + (angle - source[channel]) * fraction + 0.5)
        return [self.pose[channel] for channel in range(6)]

    def start_motion(self, targets, duration_ms):
        self.sample_pose()
        self.movement = (self.now, duration_ms / 1000, dict(self.pose), dict(targets))
        return super().start_motion(targets, duration_ms)

    def play_audio(self, path):
        self.audio_events.append({"time_ms": round(self.now * 1000), "sound": path.name,
                                  "duration_ms": round(self.audio_lengths[path.name] * 1000)})
        return super().play_audio(path)


def record_dance(profile, eyes, renderer, settings):
    steps = build_dance_steps(profile, eyes, settings)
    audio = {step.audio.name: step.audio for step in steps if step.audio}
    lengths = {}
    for name, path in audio.items():
        with wave.open(str(path), "rb") as file:
            lengths[name] = file.getnframes() / file.getframerate()
    backend = RecordingBackend(profile, lengths)
    runner = IntegratedSequence(backend, profile, eyes, settings)
    runner.start("dance")
    labels = {item["name"]: item for item in settings.get("steps", [])}
    stages = [{"name": step.name, "label": labels.get(step.name, {}).get("label", LEGACY_LABELS.get(step.name, "교대 스윙")),
               "beat": labels.get(step.name, {}).get("beat"), "start_ms": None}
              for step in steps]
    stage_indexes = {stage["name"]: index for index, stage in enumerate(stages)}
    pairs, pair_indexes, samples = [], {}, []
    for time_ms in range(0, 60001, TICK_MS):
        backend.now = time_ms / 1000
        runner.tick(backend.now)
        if runner.state == "error":
            raise RuntimeError(runner.error)
        stage = stage_indexes.get(runner.stage, len(stages) - 1)
        if stages[stage]["start_ms"] is None:
            stages[stage]["start_ms"] = time_ms
        eye = backend.last_eye
        frames = renderer.frames(eye.openness, eye.offset_x, eye.offset_y)
        key = tuple(frame.tobytes() for frame in frames)
        if key not in pair_indexes:
            pair_indexes[key] = len(pairs)
            pairs.append(frames)
        samples.append([time_ms, backend.sample_pose(), pair_indexes[key], stage,
                        [round(eye.openness, 6), round(eye.offset_x, 6), round(eye.offset_y, 6)]])
        if runner.state == "completed":
            break
    else:
        raise RuntimeError("Simulation exceeded its 60-second recording limit")
    if settings.get("schema_version") == 2 and samples[-1][0] > 15000:
        raise RuntimeError("New choreography recording exceeds the 15-second preview scope")
    columns = 8
    atlas = Image.new("RGB", (columns * 256, math.ceil(len(pairs) / columns) * 128))
    for index, frames in enumerate(pairs):
        for side, frame in enumerate(frames):
            atlas.paste(frame.convert("RGB"), ((index % columns) * 256 + side * 128,
                                                (index // columns) * 128))
    encoded = BytesIO()
    atlas.save(encoded, format="PNG", optimize=True)
    return {
        "id": settings.get("id", "legacy_dance"),
        "title": settings.get("title", "기존 교대 춤"),
        "bpm": settings.get("bpm"), "duration_ms": samples[-1][0],
        "tick_ms": TICK_MS, "initial_pose": samples[0][1],
        "passive_elbows": settings.get("passive_elbows", {"minimum": 120, "maximum": 180,
                                                           "preset": 150, "mechanism": "manual_freestop"}),
        "stages": stages, "samples": samples,
        "audio_events": backend.audio_events,
        "audio_assets": {name: "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
                         for name, path in audio.items()},
        "eye_atlas": {"columns": columns, "count": len(pairs),
                      "source": "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")},
        "commands": [[entry[0], *[value if not isinstance(value, Path) else value.name for value in entry[1:]]]
                     for entry in backend.commands],
        "terminal_state": runner.state,
    }


def build_export():
    profile, eyes = load_profile(), load_calibration()
    renderer = EyeRenderer(eyes, load_aperture(ROOT / eyes["aperture_file"], eyes))
    settings = [load_dance_config(CHOREOGRAPHY_DIR / "cuvo_groove.json"), load_dance_config()]
    dances = [record_dance(profile, eyes, renderer, item) for item in settings]
    sources = [ROOT / name for name in ("choreography.py", "dance_sequence.py", "integrated_sequence.py",
               "motion_profile.py", "oled_motion.py", "oled_renderer.py", "export_simulation.py",
               "robot_motion_profile.json", "dance_config.json", DEFAULT_CONFIG.name, eyes["aperture_file"])]
    sources += [CHOREOGRAPHY_DIR / "cuvo_groove.json"]
    sources += sorted({step.audio for config in settings for step in build_dance_steps(profile, eyes, config) if step.audio})
    hashes = {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in sources}
    masks = Image.new("RGB", (256, 128))
    for side, mask in enumerate(renderer.masks):
        masks.paste(mask.convert("RGB"), (side * 128, 0))
    encoded = BytesIO()
    masks.save(encoded, format="PNG")
    return {"schema_version": 1, "mode": "simulation_only", "profile": profile.data,
            "source_hash": sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            "source_files": hashes, "eye_calibration": eyes,
            "eye_layout": {"viewer_left": "CE1", "viewer_right": "CE0"},
            "eye_mask_source": "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode("ascii"),
            "dances": dances}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = build_export()
    content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(json.dumps({"mode": result["mode"], "source_hash": result["source_hash"],
                          "dances": [{"id": dance["id"], "duration_ms": dance["duration_ms"],
                                      "frames": len(dance["samples"]), "state": dance["terminal_state"]}
                                     for dance in result["dances"]]}))
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
