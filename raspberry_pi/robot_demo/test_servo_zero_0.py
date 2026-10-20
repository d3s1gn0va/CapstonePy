"""Explicit physical-0 experiment; not the robot's calibrated home pose."""

from test_servo_center_90 import main


if __name__ == "__main__":
    raise SystemExit(main(target=0))
