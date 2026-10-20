"""Explicit CH0/1/2 home test from the previously commanded zero pose."""

import argparse
import signal
import subprocess
import time

from test_servo_center_90 import Session, find_port

CAPABILITY = "CAPS,TEST_HOME_POSE,0:45,1:180,2:45,FROM_CONFIRMED_ZERO"
STATUS = ("STATUS_GROUP,0:45:ENABLED:IDLE,1:180:ENABLED:IDLE,2:45:ENABLED:IDLE"
          ",3:90:DISABLED:IDLE,4:90:DISABLED:IDLE,5:90:DISABLED:IDLE")


def run_test(session, pause=time.sleep):
    session.command("PING", ["ACK,PING"])
    session.command("TEST_HOME_CAPS", [CAPABILITY])
    try:
        for channel, target, duration in ((0, 45, 5000), (1, 180, 10000), (2, 45, 5000)):
            session.command(f"TEST_HOME_POSE,{channel},{duration},CONFIRM_FROM_0",
                            [f"ACK,TEST_HOME_POSE,{channel},{target}",
                             f"DONE,TEST_HOME_POSE,{channel},{target}"], timeout=duration / 1000 + 3)
            pause(0.5)
        session.command("STATUS_GROUP", [STATUS])
    except BaseException:
        try:
            session.command("STOP", ["ACK,STOP"], timeout=2)
        except Exception as error:
            print("STOP was not confirmed:", error, flush=True)
        raise
    print("CH0=45 CH1=180 CH2=45 commanded; CH3/4/5 not driven. No position feedback.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="One-shot home test; no demo restart or automatic repeat.")
    parser.add_argument("--confirm-home-pose-from-0", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_home_pose_from_0:
        print("Refused: --confirm-home-pose-from-0 required before opening Serial.")
        return 2
    print("WARNING: collision/overload possible; initial 0 assumes the last zero test, not a measurement.", flush=True)

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        import serial
        port = find_port()
        owners = subprocess.run(["fuser", port], capture_output=True, text=True, timeout=3)
        if owners.returncode != 1 or owners.stdout.strip() or owners.stderr.strip():
            raise RuntimeError("Serial port busy or ownership unknown")
        print("Serial port:", port, flush=True)
        with serial.Serial(port, 115200, timeout=0.2, write_timeout=2, exclusive=True) as connection:
            time.sleep(2.5)
            run_test(Session(connection))
    except (Exception, KeyboardInterrupt) as error:
        print("TEST FAILED:", type(error).__name__, str(error), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
