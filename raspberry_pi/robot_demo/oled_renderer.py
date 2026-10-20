"""Pure pupil rendering and fixed eye-opening calibration; no hardware access."""

import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

SIZE = 128
DEFAULT_CONFIG = Path(__file__).with_name("oled_pair_calibration.json")


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def load_calibration(path=DEFAULT_CONFIG):
    with Path(path).open(encoding="utf-8") as source:
        config = json.load(source)
    if config.get("schema_version") != 2:
        raise ValueError("Eye calibration schema_version must be 2")
    required = ("va_side_mm", "aa_side_mm", "stroke_px", "contrast", "fps",
                "open_seconds", "close_seconds", "closed_seconds", "reopen_seconds",
                "gaze_width_ratio", "gaze_move_seconds", "gaze_hold_seconds", "gaze_center_seconds")
    for key in required:
        if not _finite(config.get(key)):
            raise ValueError(f"{key} must be a finite number")
    if not 0 < config["aa_side_mm"] <= config["va_side_mm"]:
        raise ValueError("AA must fit within VA")
    for key, low, high in (("stroke_px", 1, 16), ("contrast", 0, 255), ("fps", 10, 60)):
        if not isinstance(config[key], int) or not low <= config[key] <= high:
            raise ValueError(f"{key} must be an integer in {low}..{high}")
    if not 0 <= config["gaze_width_ratio"] <= 1:
        raise ValueError("Gaze width ratio must be in 0..1")
    for key in ("open_seconds", "close_seconds", "closed_seconds", "reopen_seconds",
                "gaze_move_seconds", "gaze_hold_seconds", "gaze_center_seconds"):
        if config[key] <= 0:
            raise ValueError(f"{key} must be positive")
    box = config.get("iris_bounds_px")
    if not isinstance(box, list) or len(box) != 4 or any(
            isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < SIZE for v in box):
        raise ValueError("iris_bounds_px must be four integer screen coordinates")
    if min(box[2] - box[0], box[3] - box[1]) <= 2 * config["stroke_px"]:
        raise ValueError("Pupil bounds are reversed or too small for the stroke")
    if not isinstance(config.get("aperture_file"), str) or not config["aperture_file"]:
        raise ValueError("aperture_file must name the independent eye-opening profile")
    padding = config.get("aperture_expand_px", 0)
    if isinstance(padding, bool) or not isinstance(padding, int) or not 0 <= padding <= 16:
        raise ValueError("aperture_expand_px must be an integer in 0..16")
    return config


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    if (max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0])
            or max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1])):
        return False
    return _cross(a, b, c) * _cross(a, b, d) <= 0 and _cross(c, d, a) * _cross(c, d, b) <= 0


def load_aperture(path, config):
    with Path(path).open(encoding="utf-8") as source:
        profile = json.load(source)
    if profile.get("schema_version") != 1 or profile.get("units") != "va_mm":
        raise ValueError("Aperture must use schema 1 with va_mm coordinates")
    side = profile.get("va_side_mm")
    if not _finite(side) or not math.isclose(side, config["va_side_mm"], abs_tol=1e-6):
        raise ValueError("Aperture VA size does not match the display calibration")
    if profile.get("right_mirrors_left") is not True:
        raise ValueError("This mapping requires the right aperture to mirror the left")
    points = profile.get("left_points_mm")
    if not isinstance(points, list) or not 3 <= len(points) <= 512:
        raise ValueError("Aperture needs 3..512 ordered boundary points")
    for point in points:
        if not isinstance(point, list) or len(point) != 2 or any(
                not _finite(v) or not 0 <= v <= side for v in point):
            raise ValueError("Aperture points must be finite coordinates within VA")
    edges = list(zip(points, points[1:] + points[:1]))
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)) / 2
    if area < 1:
        raise ValueError("Aperture area is too small")
    for i, (a, b) in enumerate(edges):
        if a == b:
            raise ValueError("Duplicate adjacent aperture points")
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue
            if _intersects(a, b, *edges[j]):
                raise ValueError("Aperture boundary must not cross itself")
    return profile


def mm_to_pixel(config, value):
    border = (config["va_side_mm"] - config["aa_side_mm"]) / 2
    return (value - border) * SIZE / config["aa_side_mm"] - 0.5


def expand_mask(mask, radius):
    """Dilate by a circular pixel radius, without wrapping at screen edges."""
    expanded = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if (dx == 0 and dy == 0) or dx * dx + dy * dy > radius * radius:
                continue
            shifted = Image.new("1", mask.size, 0)
            shifted.paste(mask, (dx, dy))
            expanded = ImageChops.logical_or(expanded, shifted)
    return expanded


class EyeRenderer:
    def __init__(self, config, aperture):
        self.config = config
        self.aperture = aperture
        points = [(mm_to_pixel(config, x), mm_to_pixel(config, y))
                  for x, y in aperture["left_points_mm"]]
        left = Image.new("1", (SIZE, SIZE), 0)
        ImageDraw.Draw(left).polygon(points, fill=1)
        if not left.getbbox():
            raise ValueError("Aperture does not intersect the active display")
        left = expand_mask(left, config.get("aperture_expand_px", 0))
        self.masks = (left, left.transpose(Image.Transpose.FLIP_LEFT_RIGHT))

    def pupil(self, openness=1.0):
        """Draw the unchanged pupil WITHOUT an aperture mask."""
        if not _finite(openness) or not 0 <= openness <= 1:
            raise ValueError("Openness must be in 0..1")
        image = Image.new("1", (SIZE, SIZE), 0)
        draw = ImageDraw.Draw(image)
        left, top, right, bottom = self.config["iris_bounds_px"]
        stroke = self.config["stroke_px"]
        full_height = bottom - top + 1
        height = round(stroke + (full_height - stroke) * openness)
        y = top + (full_height - height) // 2
        box = (left, y, right, y + height - 1)
        if height <= 2 * stroke:
            draw.rounded_rectangle(box, radius=height // 2, fill=1)
        else:
            draw.ellipse(box, outline=1, width=stroke)
        return image

    def frames(self, openness=1.0, offset_x=0, offset_y=0):
        if not _finite(offset_x) or abs(offset_x) > SIZE:
            raise ValueError("Horizontal offset must be finite and within one screen width")
        if not _finite(offset_y) or abs(offset_y) > SIZE:
            raise ValueError("Vertical offset must be finite and within one screen height")
        left = self.pupil(openness)
        pupils = (left, left.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
        frames = []
        # Move the full pupil, then apply the fixed opening exactly once.
        for pupil, mask in zip(pupils, self.masks):
            shifted = Image.new("1", (SIZE, SIZE), 0)
            shifted.paste(pupil, (round(offset_x), round(offset_y)))
            frames.append(ImageChops.logical_and(shifted, mask))
        return tuple(frames)
