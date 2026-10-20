"""Shared fixed-angle test runner; this entry point defaults to physical 90."""

import argparse
import glob
import os
import signal
import subprocess
import time

STATUS_90 = "STATUS_GROUP" + "".join(f",{channel}:90:ENABLED:IDLE" for channel in range(6))


def find_port():
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates = {os.path.realpath(path): path for path in sorted(glob.glob(pattern))
                      if os.path.exists(path)}
        if len(candidates) > 1:
            raise RuntimeError("Multiple serial devices; refusing to guess an Arduino")
        if candidates:
            return next(iter(candidates.values()))
    raise RuntimeError("Arduino serial device not found")


class Session:
    def __init__(self, port):
        self.port = port
        self.buffer = bytearray()

    def command(self, command, replies, timeout=8):
        print("Pi -> Arduino:", command, flush=True)
        self.port.write((command + "\n").encode("ascii"))
        self.port.flush()
        remaining = list(replies)
        deadline = time.monotonic() + timeout
        while remaining and time.monotonic() < deadline:
            self.buffer.extend(self.port.read(self.port.in_waiting or 1))
            if len(self.buffer) > 4096:
                raise RuntimeError("Serial input exceeded size limit")
            while b"\n" in self.buffer:
                raw, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                line = raw.decode("utf-8", errors="replace").strip()
                print("Arduino -> Pi:", line, flush=True)
                if line.startswith("ERR"):
                    raise RuntimeError(line)
                if remaining and line == remaining[0]:
                    remaining.pop(0)
        if remaining:
            raise RuntimeError("Missing response: " + remaining[0])


def run_test(session, pause=time.sleep, *, target=90):
    if type(target) is not int or target not in (0, 90):
        raise ValueError("Only explicit fixed targets 0 or 90 are supported")
    command = "TEST_ZERO_0" if target == 0 else "TEST_CENTER_90"
    capability = "TEST_ZERO_CAPS" if target == 0 else "TEST_CENTER_CAPS"
    duration = 5000 if target == 0 else 3000
    status = "STATUS_GROUP" + "".join(f",{channel}:{target}:ENABLED:IDLE" for channel in range(6))
    session.command("PING", ["ACK,PING"])
    session.command(capability, [f"CAPS,{command},{target},ONCE_PER_CHANNEL"])
    try:
        for channel in range(6):
            session.command(f"{command},{channel},{duration},CONFIRM_{target}",
                            [f"ACK,{command},{channel},{target}", f"DONE,{command},{channel},{target}"])
            pause(0.5)
        session.command("STATUS_GROUP", [status])
    except BaseException:
        try:
            session.command("STOP", ["ACK,STOP"], timeout=2)
        except Exception as error:
            print("STOP was not confirmed:", error, flush=True)
        raise
    print(f"Six commanded angles are {target}; physical positions are not measured. PWM remains enabled.", flush=True)


def main(argv=None, *, target=90):
    if type(target) is not int or target not in (0, 90):
        raise ValueError("Only explicit fixed targets 0 or 90 are supported")
    parser = argparse.ArgumentParser(description=f"Explicit physical-{target} experiment; no home/profile writes or demo restart.")
    parser.add_argument(f"--confirm-physical-{target}", action="store_true")
    args = parser.parse_args(argv)
    if not getattr(args, f"confirm_physical_{target}"):
        print(f"Refused: explicit --confirm-physical-{target} required; collision/overload risk.")
        return 2
    print(f"WARNING: physical {target} may collide; first PWM activation can move abruptly.", flush=True)
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        import serial
        port = find_port()
        owners = subprocess.run(["fuser", port], capture_output=True, text=True, timeout=3)
        if owners.returncode != 1 or owners.stdout.strip() or owners.stderr.strip():
            raise RuntimeError("Serial port busy or ownership unknown; stop the robot demo first")
        print("Serial port:", port, flush=True)
        with serial.Serial(port, 115200, timeout=0.2, write_timeout=2, exclusive=True) as connection:
            time.sleep(2.5)
            run_test(Session(connection), target=target)
    except (Exception, KeyboardInterrupt) as error:
        print("TEST FAILED:", type(error).__name__, str(error), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
