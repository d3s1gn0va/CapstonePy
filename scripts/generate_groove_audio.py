#!/usr/bin/env python3
"""Generate original short percussion cues; no downloaded music or device playback."""

from io import BytesIO
from pathlib import Path
import math
import random
import struct
import wave


def percussion(name):
    randomizer = random.Random(10418)
    rate, length = 22050, 0.24
    samples, previous_noise = [], 0.0
    for index in range(round(rate * length)):
        t = index / rate
        noise = randomizer.uniform(-1, 1)
        hat = (noise - previous_noise) * math.exp(-t * 65) * 0.10
        previous_noise = noise
        if name == "kick":
            value = math.sin(2 * math.pi * (48 * t + 1.4 * (1 - math.exp(-t * 30)))) * math.exp(-t * 22) * 0.5
        elif name == "snare":
            value = noise * math.exp(-t * 30) * 0.24 + math.sin(2 * math.pi * 160 * t) * math.exp(-t * 35) * 0.12
        elif name == "hat":
            value = 0
        else:
            raise ValueError("Unknown percussion cue")
        samples.append(struct.pack("<h", round(max(-1, min(1, value + hat)) * 32767)))
    output = BytesIO()
    with wave.open(output, "wb") as file:
        file.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        file.writeframes(b"".join(samples))
    return output.getvalue()


if __name__ == "__main__":
    folder = Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo/audio"
    for name in ("kick", "snare", "hat"):
        (folder / f"cuvo_groove_{name}.wav").write_bytes(percussion(name))
    print("Generated three original percussion cues.")
