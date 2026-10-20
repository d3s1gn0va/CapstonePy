"""Timestamp-based eye poses, independent of drawing, GPIO and robot commands."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class EyePose:
    openness: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0


def head_gaze_pose(angle, neutral, left, right, horizontal_px, down_px):
    """Robot-left is viewer-right; downward screen coordinates are positive."""
    values = (angle, neutral, left, right, horizontal_px, down_px)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in values):
        raise ValueError("Head gaze requires finite numeric values")
    if not left < neutral < right or not left <= angle <= right:
        raise ValueError("Head gaze angles must fit the configured span")
    if not 0 <= horizontal_px <= 128 or not 0 <= down_px <= 128:
        raise ValueError("Head gaze offsets must fit one screen")
    relative = angle - neutral
    fraction = relative / (right - neutral if relative >= 0 else neutral - left)
    return EyePose(offset_x=round(-fraction * horizontal_px), offset_y=round(abs(fraction) * down_px))


def interpolate_gaze(start, end, elapsed, duration):
    if not math.isfinite(elapsed) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Gaze transition needs a positive duration and finite time")
    fraction = min(1.0, max(0.0, elapsed / duration))
    return EyePose(openness=start.openness + (end.openness - start.openness) * fraction,
                   offset_x=start.offset_x + (end.offset_x - start.offset_x) * fraction,
                   offset_y=start.offset_y + (end.offset_y - start.offset_y) * fraction)


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def blink_duration(config):
    return sum(config[k] for k in ("close_seconds", "closed_seconds", "reopen_seconds"))


def blink_once(config, elapsed):
    if elapsed < 0 or elapsed >= blink_duration(config):
        return 1.0
    if elapsed < config["close_seconds"]:
        return 1 - _smooth(elapsed / config["close_seconds"])
    elapsed -= config["close_seconds"]
    if elapsed < config["closed_seconds"]:
        return 0.0
    return _smooth((elapsed - config["closed_seconds"]) / config["reopen_seconds"])


def blink_period(config):
    return config["open_seconds"] + blink_duration(config)


def blink_openness(config, elapsed):
    return blink_once(config, elapsed % blink_period(config) - config["open_seconds"])


def gaze_distance(config):
    left, _, right, _ = config["iris_bounds_px"]
    return round((right - left + 1) * config["gaze_width_ratio"])


def gaze_period(config):
    return 2 * (config["gaze_center_seconds"] + 2 * config["gaze_move_seconds"]
                + config["gaze_hold_seconds"] + blink_duration(config))


def gaze_pose(config, elapsed):
    half_period = gaze_period(config) / 2
    phase = elapsed % (2 * half_period)
    direction = -1 if phase < half_period else 1
    phase = phase % half_period - config["gaze_center_seconds"]
    if phase < 0:
        return EyePose()
    move, hold = config["gaze_move_seconds"], config["gaze_hold_seconds"]
    distance = direction * gaze_distance(config)
    if phase < move:
        return EyePose(offset_x=round(distance * _smooth(phase / move)))
    if phase < move + hold:
        return EyePose(offset_x=distance)
    if phase < 2 * move + hold:
        return EyePose(offset_x=round(distance * (1 - _smooth((phase - move - hold) / move))))
    # Blink only after returning to centre; both eyes share this pose.
    return EyePose(openness=blink_once(config, phase - 2 * move - hold))
