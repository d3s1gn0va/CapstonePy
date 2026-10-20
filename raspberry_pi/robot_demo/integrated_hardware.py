"""Hardware adapter for the opt-in runner; one thread owns all devices."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import subprocess


class HardwareBackend:
    def __init__(self, profile, eye_config, include_demo_poses=True):
        self.profile, self.eye_config = profile, eye_config
        self.stack = None
        self.audio_processes = set()
        self.rx = bytearray()
        self.include_demo_poses = include_demo_poses

    def _require_ready(self):
        self.profile.require_ready(include_poses=self.include_demo_poses)

    def __enter__(self):
        self._require_ready()
        import fcntl
        import config
        from gpiozero import LED
        from oled_controller import EyeController
        from oled_renderer import EyeRenderer, load_aperture, DEFAULT_CONFIG
        from serial_controller import SerialController, find_serial_port

        stack = ExitStack()
        try:
            lock = stack.enter_context(Path("/tmp/cuvo-integrated.lock").open("a"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            port = find_serial_port(config.SERIAL_PORT)
            if not shutil.which("fuser"):
                raise RuntimeError("fuser is required to check serial ownership")
            owners = subprocess.run(["fuser", port], capture_output=True, text=True)
            if owners.returncode != 1 or owners.stdout.strip() or owners.stderr.strip():
                raise RuntimeError("Serial port is busy or ownership cannot be checked; stop the old demo first")
            self.controller = stack.enter_context(SerialController(port))
            self.controller.ping()
            firmware = self.controller.group_capabilities()
            expected = {axis["channel"]: (axis["minimum"], axis["maximum"], axis["neutral"])
                        for axis in self.profile.data["axes"].values()}
            if firmware != expected:
                raise RuntimeError("Pi profile and Arduino group safety/neutral settings do not match")
            self.controller.serial.timeout = 0
            aperture = load_aperture(DEFAULT_CONFIG.parent / self.eye_config["aperture_file"], self.eye_config)
            self.eyes = stack.enter_context(EyeController(EyeRenderer(self.eye_config, aperture), swap=True))
            self.camera_led = stack.enter_context(LED(config.CAMERA_LED_GPIO))
            self.camera_led.off()
        except BaseException:
            stack.close()
            raise
        self.stack = stack
        return self

    def __exit__(self, *exception):
        try:
            try:
                self.stop()
            finally:
                self.abort_audio()
                self.led(False)
        finally:
            self.stack.close()

    def start_motion(self, targets, duration_ms):
        self.rx.clear()
        ser = self.controller.serial
        previous_timeout = ser.timeout
        try:
            ser.timeout = 0.10
            return self.controller.move_group(targets, duration_ms, wait=False)
        finally:
            ser.timeout = previous_timeout

    def motion_done(self, pending):
        ser = self.controller.serial
        self.rx.extend(ser.read(ser.in_waiting))
        if len(self.rx) > 4096:
            raise RuntimeError("Unexpected serial input size")
        done = False
        while b"\n" in self.rx:
            raw, _, rest = self.rx.partition(b"\n")
            self.rx = bytearray(rest)
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("ERR"):
                raise RuntimeError(line)
            if line == pending.done_message:
                done = True
        return done

    def play_audio(self, path):
        from audio_player import play_wav_async
        process = play_wav_async(path)
        self.audio_processes.add(process)
        return process

    def audio_done(self, process):
        if process.poll() is None:
            return False
        _, error = process.communicate()
        self.audio_processes.discard(process)
        if process.returncode:
            raise RuntimeError(f"Audio failed: {error}")
        return True

    def abort_audio(self):
        for process in tuple(self.audio_processes):
            try:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=1)
            finally:
                self.audio_processes.discard(process)

    def stop(self):
        self.rx.clear()
        ser = self.controller.serial
        previous_timeout = ser.timeout
        try:
            ser.timeout = 0.10
            self.controller.stop()
        finally:
            ser.timeout = previous_timeout
        return True

    def led(self, value):
        self.camera_led.on() if value else self.camera_led.off()

    def show_eye(self, pose):
        self.eyes.show(pose)
