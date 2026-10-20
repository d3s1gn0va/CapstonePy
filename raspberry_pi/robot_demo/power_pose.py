"""Opt-in six-axis parking for clean startup/shutdown, never emergency STOP."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from motion_profile import ProfileError


@contextmanager
def connect_controller(profile):
    import fcntl
    import config
    from serial_controller import SerialController, find_serial_port

    with Path("/tmp/cuvo-integrated.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        port = find_serial_port(config.SERIAL_PORT)
        if not shutil.which("fuser"):
            raise RuntimeError("fuser is required before parking")
        owners = subprocess.run(["fuser", port], capture_output=True, text=True, timeout=3)
        if owners.returncode != 1 or owners.stdout.strip() or owners.stderr.strip():
            raise RuntimeError("Serial ownership is not clear; parking refused")
        with SerialController(port) as controller:
            yield controller


def park_home(profile, confirmed=False, connect=connect_controller):
    if confirmed is not True:
        raise ProfileError("Power pose requires explicit 5V/clearance confirmation")
    targets = profile.targets("startup")
    if set(targets) != set(range(6)) or any(type(value) is not int for value in targets.values()):
        raise ProfileError("Parking requires six calibrated neutral positions")
    expected = {axis["channel"]: (axis["minimum"], axis["maximum"], axis["neutral"])
                for axis in profile.data["axes"].values()}
    with connect(profile) as controller:
        controller.ping()
        if controller.group_capabilities() != expected:
            raise RuntimeError("Parking refused: firmware calibration differs from Pi profile")
        controller.stop()
        try:
            controller.move_group(targets, 3000, wait=True)
        finally:
            controller.stop()
    return targets


class PowerPose:
    def __init__(self, profile, marker, confirmed=False, parker=park_home, boot_id=None):
        self.profile, self.marker = profile, Path(marker)
        self.confirmed, self.parker, self.prepared = confirmed, parker, False
        self.boot_id = boot_id or Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        self.fingerprint = hashlib.sha256(json.dumps(profile.data["axes"], sort_keys=True).encode()).hexdigest()

    def _mark(self, status):
        descriptor = os.open(self.marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as file:
            os.fchmod(file.fileno(), 0o600)
            json.dump(dict(boot=self.boot_id, profile=self.fingerprint, status=status), file)

    def prepare(self):
        if self.confirmed is not True:
            raise ProfileError("Power pose is not confirmed")
        if self.marker.exists():
            previous = json.loads(self.marker.read_text())
            if previous.get("boot") == self.boot_id and previous.get("profile") == self.fingerprint:
                if previous.get("status") != "ready":
                    raise RuntimeError("Previous startup parking failed; no automatic motion retry")
                self.prepared = True
                return
        # Claim before opening Serial so a daemon restart cannot repeat a failed move.
        self._mark("attempted")
        self.parker(self.profile, confirmed=True)
        self._mark("ready")
        self.prepared = True

    def finish(self):
        if not self.prepared:
            raise RuntimeError("Startup parking was not completed")
        try:
            return self.parker(self.profile, confirmed=True)
        except Exception:
            self._mark("shutdown_failed")
            raise
