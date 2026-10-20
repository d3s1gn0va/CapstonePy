"""Optional exhibit media services. Importing this module never opens hardware.

Run capture/finalization and volume changes off the BLE event-loop thread. Capture
is disabled by default; a configured camera and libav-enabled rpicam installation
must be verified on the actual Pi before enabling it. Only complete, probed MP4s
and their thumbnails become visible records. No sample footage is synthesized.
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid


class MediaError(RuntimeError):
    """A media operation failed without a usable result."""


class VolumeController:
    """Read/write the same PipeWire default sink used by pw-play.

    Values returned are read back from PipeWire, never optimistic UI values.
    Setting volume also clears mute for positive values and mutes at zero.
    All subprocesses in one operation share a bounded time budget.
    """

    SINK = "@DEFAULT_AUDIO_SINK@"

    def __init__(self, runner=subprocess.run, which=shutil.which,
                 clock=time.monotonic, timeout=3.0):
        self.runner, self.which, self.clock = runner, which, clock
        self.timeout = max(0.1, min(float(timeout), 10.0))
        self._lock = threading.Lock()

    def available(self):
        return bool(self.which("wpctl"))

    def _run(self, args, deadline):
        executable = self.which("wpctl")
        if not executable:
            raise MediaError("wpctl_unavailable")
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise MediaError("volume_timeout")
        try:
            result = self.runner([executable, *args], capture_output=True,
                                 text=True, check=False, timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise MediaError("volume_timeout") from exc
        except OSError as exc:
            raise MediaError("pipewire_unavailable") from exc
        if result.returncode:
            raise MediaError("pipewire_unavailable")
        return result.stdout

    def _snapshot(self, deadline):
        output = self._run(["get-volume", self.SINK], deadline)
        match = re.fullmatch(r"\s*Volume:\s*(\d+(?:\.\d+)?)\s*(\[MUTED\])?\s*", output)
        if not match:
            raise MediaError("invalid_volume_readback")
        fraction = float(match.group(1))
        if not math.isfinite(fraction):
            raise MediaError("invalid_volume_readback")
        return {"volume": round(fraction * 100), "muted": bool(match.group(2)),
                "available": True, "backend": "pipewire", "error": None}

    def snapshot(self):
        with self._lock:
            try:
                return self._snapshot(self.clock() + self.timeout)
            except MediaError as exc:
                return {"volume": None, "muted": None, "available": False,
                        "backend": "pipewire", "error": str(exc)}

    get_volume = snapshot

    def set_volume(self, percent):
        if (isinstance(percent, bool) or not isinstance(percent, (int, float))
                or (isinstance(percent, float) and not math.isfinite(percent))):
            raise MediaError("invalid_volume")
        value = float(min(100, max(0, percent)))
        with self._lock:
            deadline = self.clock() + self.timeout
            self._run(["set-volume", self.SINK, f"{value / 100:.4f}", "--limit", "1.0"], deadline)
            self._run(["set-mute", self.SINK, "1" if value == 0 else "0"], deadline)
            return self._snapshot(deadline)

    def set_mute(self, muted):
        if type(muted) is not bool:
            raise MediaError("invalid_mute")
        with self._lock:
            deadline = self.clock() + self.timeout
            self._run(["set-mute", self.SINK, "1" if muted else "0"], deadline)
            return self._snapshot(deadline)


def _valid_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _regular_file(path):
    return not path.is_symlink() and path.is_file() and path.stat().st_size > 0


class RecordManager:
    """Private local recording store; no network server or authentication here.

    ``root`` should live outside the Git checkout, e.g. ~/.local/state/cuvo/records.
    The caller opts in with enabled=True, owns consent/retention and runs start /
    finish in a worker. Capability reports configuration, not camera validation.
    Output contains no child name, authentication data, or filesystem paths.
    Camera capture is capped at 60 seconds even if the controlling app vanishes.
    """

    FILES = {"video": "video.mp4", "thumbnail": "thumbnail.jpg"}
    METADATA_KEYS = {"id", "run_id", "play_id", "created_at", "duration_seconds",
                     "video", "thumbnail", "source", "state"}

    def __init__(self, root, enabled=False, camera_command=None,
                 runner=subprocess.run, popen=subprocess.Popen, which=shutil.which,
                 clock=time.monotonic, wall_clock=time.time, disk_usage=shutil.disk_usage,
                 max_seconds=60, minimum_free_bytes=100 * 1024 * 1024,
                 child_new_session=True):
        self.root = Path(root).expanduser().absolute()
        self.enabled = bool(enabled)
        self.child_new_session = bool(child_new_session)
        if camera_command is not None and (not isinstance(camera_command, str) or not camera_command):
            raise ValueError("camera_command must be an executable path or name")
        self.camera_command = camera_command
        self.runner, self.popen, self.which = runner, popen, which
        self.clock, self.wall_clock, self.disk_usage = clock, wall_clock, disk_usage
        if type(max_seconds) is not int or not 1 <= max_seconds <= 60:
            raise ValueError("max_seconds must be between 1 and 60")
        self.max_seconds = max_seconds
        self.minimum_free_bytes = max(0, int(minimum_free_bytes))
        self.state = "idle" if enabled else "unsupported"
        self.last_error = None
        self._active = None
        self._lock = threading.RLock()

    @property
    def active_record_id(self):
        with self._lock:
            return self._active["metadata"]["id"] if self._active else None

    def _binaries(self):
        camera = self.which(self.camera_command) if self.camera_command else (
            self.which("rpicam-vid") or self.which("libcamera-vid"))
        return camera, self.which("ffprobe"), self.which("ffmpeg")

    def capability(self):
        if not self.enabled:
            return {"recording_supported": False, "reason": "capture_disabled"}
        camera, probe, encoder = self._binaries()
        if not camera:
            return {"recording_supported": False, "reason": "camera_command_unavailable"}
        if not probe or not encoder:
            return {"recording_supported": False, "reason": "ffmpeg_unavailable"}
        return {"recording_supported": True, "reason": None}

    def _prepare_root(self):
        if self.root.is_symlink():
            raise MediaError("unsafe_record_root")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.root.is_dir() or self.root.stat().st_uid != os.getuid():
            raise MediaError("unsafe_record_root")
        self.root.chmod(0o700)

    def start(self, run_id, play_id):
        if not _valid_uuid(run_id):
            raise MediaError("invalid_run_id")
        if not isinstance(play_id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", play_id):
            raise MediaError("invalid_play_id")
        with self._lock:
            if self._active:
                raise MediaError("recording_busy")
            support = self.capability()
            if not support["recording_supported"]:
                self.state, self.last_error = "unsupported", support["reason"]
                raise MediaError(support["reason"])
            staging = None
            try:
                self._prepare_root()
                if self.disk_usage(self.root).free < self.minimum_free_bytes:
                    raise MediaError("record_storage_full")
                record_id = str(uuid.uuid4())
                staging = self.root / (".pending-" + record_id)
                staging.mkdir(mode=0o700)
                camera, probe, encoder = self._binaries()
                metadata = {
                    "id": record_id, "run_id": run_id, "play_id": play_id,
                    "created_at": datetime.fromtimestamp(self.wall_clock(), timezone.utc).isoformat(),
                    "duration_seconds": None, "video": "video.mp4", "thumbnail": "thumbnail.jpg",
                    "source": "robot", "state": "ready",
                }
                # MP4 must be requested explicitly: rpicam's default is raw H.264.
                process = self.popen([
                    camera, "--nopreview", "--timeout", str(self.max_seconds * 1000),
                    "--width", "1280", "--height", "720", "--framerate", "30",
                    "--codec", "libav", "--libav-format", "mp4",
                    "--output", str(staging / "video.mp4"),
                ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=self.child_new_session)
                self._active = {"process": process, "staging": staging, "metadata": metadata,
                                "probe": probe, "encoder": encoder, "started": self.clock()}
                if process.poll() is not None:
                    raise MediaError("camera_start_failed")
                self.state, self.last_error = "recording", None
                return record_id
            except (OSError, MediaError) as exc:
                self._active = None
                if staging:
                    shutil.rmtree(staging, ignore_errors=True)
                self.state, self.last_error = "error", str(exc) if isinstance(exc, MediaError) else "record_storage_error"
                raise MediaError(self.last_error) from exc

    def _stop_process(self, process):
        """Graceful MP4 trailer write; escalate only to avoid an orphan camera."""
        if process.poll() is not None:
            return process.returncode
        try:
            process.send_signal(signal.SIGINT)
            return process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            raise MediaError("camera_stop_timeout")
        except ProcessLookupError:
            return process.wait(timeout=1)

    def _run(self, arguments, timeout=10):
        try:
            result = self.runner(arguments, capture_output=True, text=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise MediaError("record_finalize_timeout") from exc
        except OSError as exc:
            raise MediaError("record_finalize_unavailable") from exc
        if result.returncode:
            raise MediaError("record_finalize_failed")
        return result.stdout

    def finish(self):
        with self._lock:
            if not self._active:
                raise MediaError("no_active_recording")
            active = self._active
            staging, metadata = active["staging"], active["metadata"]
            self.state = "saving"
            try:
                if self._stop_process(active["process"]) != 0:
                    raise MediaError("camera_capture_failed")
                video = staging / "video.mp4"
                if not _regular_file(video):
                    raise MediaError("record_video_missing")
                output = self._run([
                    active["probe"], "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(video),
                ])
                try:
                    info = json.loads(output)
                    duration = float(info["format"]["duration"])
                    video_stream = any(isinstance(item, dict) and item.get("codec_type") == "video"
                                       for item in info["streams"])
                except (ValueError, TypeError, KeyError) as exc:
                    raise MediaError("invalid_record_video") from exc
                if not video_stream or not math.isfinite(duration) or not 0 < duration <= self.max_seconds + 5:
                    raise MediaError("invalid_record_video")
                self._run([
                    active["encoder"], "-nostdin", "-v", "error", "-y", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=320:-2", str(staging / "thumbnail.jpg"),
                ])
                if not _regular_file(staging / "thumbnail.jpg"):
                    raise MediaError("record_thumbnail_missing")
                metadata["duration_seconds"] = max(0.001, round(duration, 3))
                for name in self.FILES.values():
                    (staging / name).chmod(0o600)
                with (staging / "metadata.json").open("x", encoding="utf-8") as output_file:
                    os.chmod(output_file.name, 0o600)
                    json.dump(metadata, output_file, ensure_ascii=False, separators=(",", ":"))
                    output_file.flush()
                    os.fsync(output_file.fileno())
                # One same-filesystem rename publishes metadata and media together.
                staging.rename(self.root / metadata["id"])
                self.state, self.last_error = "idle", None
                return dict(metadata)
            except (OSError, MediaError, subprocess.TimeoutExpired) as exc:
                self.state, self.last_error = "error", str(exc) if isinstance(exc, MediaError) else "record_storage_error"
                raise MediaError(self.last_error) from exc
            finally:
                # If the OS could not reap the camera even after kill, retain its
                # handle and staging directory so abort can retry. Never orphan
                # a still-running camera and permit an overlapping capture.
                if active["process"].poll() is not None:
                    shutil.rmtree(staging, ignore_errors=True)
                    self._active = None

    def abort(self):
        with self._lock:
            if not self._active:
                return
            active = self._active
            try:
                self._stop_process(active["process"])
            except (OSError, MediaError, subprocess.TimeoutExpired):
                self.last_error = "camera_abort_failed"
            finally:
                if active["process"].poll() is not None:
                    shutil.rmtree(active["staging"], ignore_errors=True)
                    self._active = None
                self.state = "error" if self.last_error else "idle"
            if self._active:
                raise MediaError("camera_abort_failed")

    def _read_record(self, record_id):
        if not _valid_uuid(record_id):
            raise MediaError("invalid_record_id")
        folder = self.root / record_id
        metadata_path = folder / "metadata.json"
        if (self.root.is_symlink() or folder.is_symlink() or not folder.is_dir()
                or not _regular_file(metadata_path) or metadata_path.stat().st_size > 8192):
            raise MediaError("record_not_found")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (not isinstance(metadata, dict) or set(metadata) != self.METADATA_KEYS
                    or metadata["id"] != record_id or not _valid_uuid(metadata["run_id"])
                    or metadata["source"] != "robot" or metadata["state"] != "ready"
                    or metadata["video"] != "video.mp4" or metadata["thumbnail"] != "thumbnail.jpg"
                    or not isinstance(metadata["play_id"], str)
                    or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", metadata["play_id"])
                    or isinstance(metadata["duration_seconds"], bool)
                    or not isinstance(metadata["duration_seconds"], (int, float))
                    or not math.isfinite(metadata["duration_seconds"])
                    or not 0 < metadata["duration_seconds"] <= 65):
                raise ValueError("invalid metadata")
            datetime.fromisoformat(metadata["created_at"])
            if any(not _regular_file(folder / name) for name in self.FILES.values()):
                raise ValueError("missing media")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise MediaError("record_not_found") from exc
        return metadata

    def list_records(self):
        with self._lock:
            if not self.root.is_dir() or self.root.is_symlink():
                return []
            records = []
            for entry in self.root.iterdir():
                if _valid_uuid(entry.name):
                    try:
                        records.append(self._read_record(entry.name))
                    except MediaError:
                        continue
            return sorted(records, key=lambda value: value["created_at"], reverse=True)

    def resolve_file(self, record_id, kind):
        if kind not in self.FILES:
            raise MediaError("invalid_record_file")
        with self._lock:
            self._read_record(record_id)
            return self.root / record_id / self.FILES[kind]
