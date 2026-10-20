"""OLED-only standby, handed off before the next explicitly requested dance."""

from pathlib import Path
import subprocess
import sys


class IdleEyeProcess:
    def __init__(self):
        self.process = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).with_name("idle_eye_worker.py"))],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    def poll(self):
        return self.process.poll()

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            code = self.process.wait(timeout=1)
        except subprocess.TimeoutExpired as error:
            self.process.kill()
            self.process.wait(timeout=1)
            raise RuntimeError("Idle eyes did not release the displays cleanly") from error
        if code != 0:
            raise RuntimeError("Idle eye cleanup failed")


class IdleEyes:
    def __init__(self, marker, factory=IdleEyeProcess, boot_id=None):
        self.marker, self.factory = Path(marker), factory
        if boot_id is None:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        self.boot_id = boot_id
        self.armed = self.marker.exists() and self.marker.read_text().strip() == boot_id
        self.process = None
        self.previous_state = None

    def before_dance(self):
        # Cleanup must finish before the dance can acquire the shared OLED lock.
        self.pause()
        self.armed = False
        self.previous_state = None
        self.marker.unlink(missing_ok=True)

    def pause(self):
        if self.process is not None:
            process, self.process = self.process, None
            process.close()

    def sync(self, state, busy=False, shutting_down=False):
        if state == "completed" and self.previous_state != "completed" and not busy:
            self.marker.touch(mode=0o600)
            self.marker.write_text(self.boot_id + "\n", encoding="ascii")
            self.armed = True
        self.previous_state = state
        if state == "error":
            self.armed = False
            self.marker.unlink(missing_ok=True)
        if shutting_down or busy or state == "error":
            self.pause()
            return
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.armed = False
            self.marker.unlink(missing_ok=True)
            raise RuntimeError("Idle eye worker exited; automatic retries are disabled")
        if self.armed and state in ("idle", "completed", "stopped") and self.process is None:
            self.process = self.factory()
