"""Standalone CUVO OLED eye test; never opens Arduino serial or robot GPIO."""

import argparse
from pathlib import Path
import time


EXPRESSIONS = ("open", "happy", "closed")


def eye_image(expression, size=(128, 128)):
    from PIL import Image, ImageDraw

    image = Image.new("1", size, 0)
    draw = ImageDraw.Draw(image)
    width, height = size
    margin_y = round(height * 0.08)
    left, right = 0, width - 1
    stroke = 6
    if expression == "open":
        draw.ellipse((left, margin_y, right, height - 1 - margin_y),
                     outline=1, width=stroke)
    elif expression == "happy":
        radius = (stroke - 1) / 2
        start, end = left + radius, right - radius
        # Sample a shallow arch densely so the stroke stays connected.
        points = [
            (round(start + (end - start) * i / 64),
             round(height * (0.38 + 0.22 * (2 * i / 64 - 1) ** 2)))
            for i in range(65)
        ]
        draw.line(points, fill=1, width=stroke, joint="curve")
        for cap_left, (_, y) in ((left, points[0]), (right - stroke + 1, points[-1])):
            top = y - stroke // 2
            draw.ellipse((cap_left, top, cap_left + stroke - 1, top + stroke - 1),
                         fill=1)
    elif expression == "closed":
        top = (height - stroke) // 2
        draw.rounded_rectangle((left, top, right, top + stroke - 1),
                               radius=stroke // 2, fill=1)
    else:
        raise ValueError(f"Unknown expression: {expression}")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", choices=("sh1107", "sh1106"), default="sh1107",
                        help="SH1107: panel 1, 128x128; SH1106: panel 3 trial, 128x64")
    parser.add_argument("--rotate", type=int, choices=range(4), default=0,
                        help="Quarter-turns clockwise (0, 1, 2, 3)")
    parser.add_argument("--cycles", type=int, choices=range(1, 6), default=2,
                        help="Each cycle lasts six seconds; default: 2")
    parser.add_argument("--preview-dir", type=Path,
                        help="Save PNGs without accessing any hardware")
    args = parser.parse_args()
    panel_size = (128, 128 if args.controller == "sh1107" else 64)
    logical_size = panel_size[::-1] if args.rotate % 2 else panel_size

    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        for expression in EXPRESSIONS:
            frame = eye_image(expression, logical_size)
            frame.rotate(-90 * args.rotate, expand=True).save(
                args.preview_dir / f"{expression}.png")
        print(f"Saved three previews to {args.preview_dir}")
        return

    if not Path("/dev/spidev0.0").exists():
        parser.exit(1, "SPI device /dev/spidev0.0 is missing. Enable SPI first.\n")

    from luma.core.interface.serial import spi
    from luma.oled.device import sh1106, sh1107

    serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25,
                 bus_speed_hz=1000000)
    display = None
    try:
        driver = sh1107 if args.controller == "sh1107" else sh1106
        display = driver(serial, width=panel_size[0], height=panel_size[1],
                         rotate=args.rotate)
        display.contrast(255)
        print("OLED only: SPI0 CE0, DC=GPIO24, RST=GPIO25. No servo commands.",
              flush=True)
        for _ in range(args.cycles):
            for expression in EXPRESSIONS:
                print(f"Eye: {expression}", flush=True)
                display.display(eye_image(expression, display.size))
                time.sleep(2)
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
    finally:
        if display is not None:
            display.cleanup()
        else:
            serial.cleanup()
    print("Finished; display cleared. Confirm the visible result on the panel.",
          flush=True)


if __name__ == "__main__":
    main()
