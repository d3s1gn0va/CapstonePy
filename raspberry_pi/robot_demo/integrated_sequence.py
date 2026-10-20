"""Single-owner, cancellable timeline. No GPIO, serial or audio imports."""

from dataclasses import dataclass

import config
from oled_motion import EyePose, blink_once, blink_openness, blink_duration, gaze_pose, gaze_period, interpolate_gaze


@dataclass(frozen=True)
class Step:
    name: str
    targets: object = None
    duration_ms: int = 0
    audio: object = None
    hold: float = 0
    eyes: str = "idle"
    eye_from: object = None
    eye_to: object = None


class IntegratedSequence:
    def __init__(self, backend, profile, eye_config, dance_settings=None):
        self.backend, self.profile, self.eye_config = backend, profile, eye_config
        self.state, self.stage, self.error = "idle", "ready", None
        self.steps, self.index, self.started = [], 0, None
        self.motion = self.audio = None
        self.action = None
        self.events = []
        self.dance_settings = dance_settings

    def start(self, action="demo"):
        if self.state not in {"idle", "completed"}:
            return False
        if action == "dance":
            from dance_sequence import build_dance_steps, load_dance_config
            settings = self.dance_settings if self.dance_settings is not None else load_dance_config()
            self.steps = build_dance_steps(self.profile, self.eye_config, settings)
        elif action == "demo":
            self.steps = [
                Step("look_and_blink", hold=gaze_period(self.eye_config) / 2, eyes="gaze"),
                Step("name_call", self.profile.targets("greeting"), config.HEAD_TURN_DURATION_MS,
                     config.AUDIO_NAME_CALL),
                Step("pause", hold=config.AFTER_HEAD_TURN_PAUSE_SEC + config.BETWEEN_AUDIO_PAUSE_SEC),
                Step("invitation", self.profile.targets("invitation"), config.ARM_RAISE_DURATION_MS,
                     config.AUDIO_LETS_PLAY),
                Step("hold", hold=config.AFTER_AUDIO_HOLD_SEC),
                Step("return_home", self.profile.targets("home"), config.RETURN_DURATION_MS),
                Step("finish_blink", hold=blink_duration(self.eye_config), eyes="blink"),
            ]
        elif action == "camera":
            crown = self.profile.data["axes"]["crown"]
            for angle in (crown["minimum"], crown["maximum"], crown["neutral"]):
                self.profile.check_angle("crown", angle)
            self.steps = [Step("camera_left", {2: crown["minimum"]}, config.CAMERA_SWEEP_DURATION_MS),
                          Step("camera_right", {2: crown["maximum"]}, config.CAMERA_SWEEP_DURATION_MS),
                          Step("camera_center", {2: crown["neutral"]}, config.CAMERA_RETURN_DURATION_MS)]
        elif action == "startup":
            self.steps = [Step("startup_home", self.profile.targets("startup"), config.STARTUP_HOME_DURATION_MS)]
        else:
            raise ValueError("Unknown action")
        self.action, self.state, self.index, self.started = action, "running", 0, None
        self.error = None
        return True

    def _abort(self, error=None):
        stop_error = None
        try:
            if self.backend.stop() is not True:
                raise RuntimeError("STOP acknowledgement not confirmed")
        except Exception as exc:
            stop_error = str(exc)
        finally:
            try:
                self.backend.abort_audio()
            except Exception as exc:
                stop_error = stop_error or str(exc)
            try:
                self.backend.led(False)
            except Exception as exc:
                stop_error = stop_error or str(exc)
            try:
                self.backend.show_eye(EyePose())
            except Exception as exc:
                stop_error = stop_error or str(exc)
        self.error = "; ".join(str(e) for e in (error, stop_error) if e) or None
        self.state = "error" if self.error else "stopped"
        self.stage = self.state
        self.steps = []
        self.events.append(self.stage)

    def stop(self):
        if self.state == "running":
            self._abort()

    def tick(self, now):
        if self.state == "error":
            return
        try:
            if self.state != "running":
                pose = EyePose() if self.state == "stopped" else EyePose(openness=blink_openness(self.eye_config, now))
                self.backend.show_eye(pose)
                return
            step = self.steps[self.index]
            if self.started is None:
                self.started, self.stage = now, step.name
                self.events.append(self.stage)
                self.backend.led(self.action == "camera")
                self.motion = self.backend.start_motion(step.targets, step.duration_ms) if step.targets else None
                self.audio = self.backend.play_audio(step.audio) if step.audio else None
            elapsed = now - self.started
            if step.eyes == "gaze":
                pose = gaze_pose(self.eye_config, elapsed)
            elif step.eyes == "blink":
                pose = EyePose(openness=blink_once(self.eye_config, elapsed))
            elif step.eyes == "transition":
                pose = interpolate_gaze(step.eye_from, step.eye_to, elapsed, step.duration_ms / 1000)
            elif step.eyes == "open":
                pose = EyePose()
            else:
                pose = EyePose(openness=blink_openness(self.eye_config, now))
            self.backend.show_eye(pose)
            motion_done = self.motion is None or self.backend.motion_done(self.motion)
            audio_done = self.audio is None or self.backend.audio_done(self.audio)
            if motion_done:
                self.motion = None
            if audio_done:
                self.audio = None
            if not motion_done and elapsed > step.duration_ms / 1000 + config.SERIAL_DONE_MARGIN_SEC:
                raise RuntimeError("Motion DONE timeout: " + step.name)
            if not audio_done and elapsed > 30:
                raise RuntimeError("Audio completion timeout: " + step.name)
            if motion_done and audio_done and elapsed >= step.hold:
                self.index += 1
                self.started = None
                if self.index == len(self.steps):
                    self.backend.led(False)
                    self.state, self.stage = "completed", "completed"
                    self.events.append("completed")
        except Exception as exc:
            self._abort(str(exc))


class SimulatedBackend:
    """Virtual acknowledgements only; no physical-device access."""

    def __init__(self, audio_lengths):
        self.audio_lengths, self.now, self.commands = audio_lengths, 0.0, []
        self.led_on, self.audio_aborted = False, False

    def start_motion(self, targets, duration_ms):
        self.commands.append(("motion", dict(targets), duration_ms))
        return self.now + duration_ms / 1000

    def motion_done(self, deadline):
        return self.now >= deadline

    def play_audio(self, path):
        self.commands.append(("audio", path.name))
        return self.now + self.audio_lengths[path.name]

    def audio_done(self, deadline):
        return self.now >= deadline

    def stop(self):
        self.commands.append(("STOP",))
        return True

    def abort_audio(self):
        self.audio_aborted = True

    def led(self, value):
        self.led_on = value

    def show_eye(self, pose):
        self.last_eye = pose
