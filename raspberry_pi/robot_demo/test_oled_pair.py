"""Bounded CUVO eye test and previews; production eye modules are separate."""

import argparse
import math
from pathlib import Path
import signal
import time

from PIL import Image, ImageDraw

from oled_controller import EyeController, PANELS
from oled_motion import EyePose, blink_openness, blink_period, gaze_distance, gaze_period, gaze_pose
from oled_renderer import DEFAULT_CONFIG, SIZE, EyeRenderer, load_aperture, load_calibration


def pair_preview(renderer, pose):
    preview = Image.new("RGB", (SIZE * 2 + 16, SIZE), "#303030")
    for index, frame in enumerate(renderer.frames(pose.openness, pose.offset_x)):
        preview.paste(frame.convert("RGB"), (index * (SIZE + 16), 0))
    return preview.resize((816, 384), Image.Resampling.NEAREST)


def save_preview(renderer, directory, gaze=False):
    config = renderer.config
    directory.mkdir(parents=True, exist_ok=True)
    pair_preview(renderer, EyePose()).save(directory / "open.png")
    pair_preview(renderer, EyePose(openness=0)).save(directory / "closed.png")
    period = gaze_period(config) if gaze else blink_period(config)
    times = [i / 25 for i in range(math.ceil(period * 25))]
    poses = ([gaze_pose(config, t) for t in times] if gaze else
             [EyePose(openness=blink_openness(config, t)) for t in times])
    frames = [pair_preview(renderer, pose) for pose in poses]
    frames[0].save(directory / ("gaze.gif" if gaze else "blink.gif"), save_all=True,
                   append_images=frames[1:], duration=40, loop=0, optimize=False)
    if gaze:
        for name, direction in (("left", -1), ("right", 1)):
            pair_preview(renderer, EyePose(offset_x=direction * gaze_distance(config))).save(
                directory / f"look_{name}.png")
    for side, mask in zip(("left", "right"), renderer.masks):
        mask.save(directory / f"aperture_{side}.png")

    scale, pad = 12, 32
    side = round(config["va_side_mm"] * scale)
    diagram = Image.new("RGB", (side + pad * 2, side + pad * 2), "#202020")
    draw = ImageDraw.Draw(diagram)
    border = (config["va_side_mm"] - config["aa_side_mm"]) / 2
    draw.rectangle((pad, pad, pad + side, pad + side), outline="#dddddd", width=2)
    aa_box = (pad + border * scale, pad + border * scale,
              pad + (border + config["aa_side_mm"]) * scale,
              pad + (border + config["aa_side_mm"]) * scale)
    aa_side = round(config["aa_side_mm"] * scale)
    rendered = renderer.frames()[0].convert("RGB").resize((aa_side, aa_side), Image.Resampling.NEAREST)
    diagram.paste(rendered, (round(aa_box[0]), round(aa_box[1])))
    draw.rectangle(aa_box, outline="#00bfc4", width=2)
    points = [(pad + x * scale, pad + y * scale) for x, y in renderer.aperture["left_points_mm"]]
    draw.line(points + points[:1], fill="#ef9a48", width=2)
    diagram.save(directory / "calibration.png")


def run_animation(controller, config, seconds, gaze=False):
    started = time.monotonic()
    count = 0
    while time.monotonic() - started < seconds:
        frame_start = time.monotonic()
        elapsed = frame_start - started
        pose = gaze_pose(config, elapsed) if gaze else EyePose(openness=blink_openness(config, elapsed))
        controller.show(pose)
        count += 1
        remaining = seconds - (time.monotonic() - started)
        time.sleep(max(0, min(remaining, 1 / config["fps"] - (time.monotonic() - frame_start))))
    elapsed = time.monotonic() - started
    print(f"Finished: {count} paired frames, {elapsed:.1f}s, {count / elapsed:.1f} fps.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--aperture", type=Path, help="Override the eye-opening profile for calibration")
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--gaze", action="store_true", help="Look left/right and blink after returning to centre")
    parser.add_argument("--swap-displays", action="store_true", help="Use CE1 as viewer-left")
    parser.add_argument("--preview-dir", type=Path, help="Generate PNG/GIF without GPIO/SPI access")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 120:
        parser.error("--seconds must be in (0, 120]")
    config = load_calibration(args.config)
    aperture_path = args.aperture or args.config.parent / config["aperture_file"]
    renderer = EyeRenderer(config, load_aperture(aperture_path, config))
    if args.preview_dir:
        save_preview(renderer, args.preview_dir, args.gaze)
        print(f"Preview saved to {args.preview_dir}")
        return
    for device, _, _ in PANELS:
        if not Path(f"/dev/spidev0.{device}").exists():
            parser.error(f"Missing /dev/spidev0.{device}")

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        with EyeController(renderer, swap=args.swap_displays) as controller:
            mapping = "CE1=left, CE0=right" if args.swap_displays else "CE0=left, CE1=right"
            print(f"Two SH1107 eyes: {mapping} (viewer coordinates).", flush=True)
            print(f"Pupil={config['iris_bounds_px']}, aperture={renderer.aperture.get('status')}, "
                  f"contrast={config['contrast']}, no servo commands.", flush=True)
            if args.gaze:
                print(f"Gaze: +/-{gaze_distance(config)}px, move/return={config['gaze_move_seconds']}s, "
                      f"hold={config['gaze_hold_seconds']}s; blink after each return.", flush=True)
            run_animation(controller, config, args.seconds, args.gaze)
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
    print("Both displays cleared; physical aperture alignment needs user confirmation.", flush=True)


if __name__ == "__main__":
    main()
