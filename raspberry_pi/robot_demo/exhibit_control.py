"""Authenticated exhibit extension; all hardware work remains outside GLib."""

from concurrent.futures import ThreadPoolExecutor
import json
import uuid

from ble_control import BLEControl, CommandError
from exhibit_sequences import PLAYS, SCENES, normalize_name


class ExhibitControl(BLEControl):
    actions = BLEControl.actions | {"play.start", "scene.start", "pose.reset", "profile.set",
                                    "audio.volume.set", "system.shutdown", "records.list", "records.get"}
    command_fields = BLEControl.command_fields | {"payload"}

    def __init__(self, *args, catalog, exhibit_worker_factory, volume, records,
                 allow_poweroff=False, media=None, executor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.catalog, self.exhibit_worker_factory = catalog, exhibit_worker_factory
        self.volume_service, self.records_service = volume, records
        self.allow_poweroff, self.media = allow_poweroff, media
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="cuvo-settings")
        self.jobs = []
        self.command_result = None
        self.latest_owner_request = None
        self.run_id = self.play_id = self.scene_id = None
        self.profile_id, self.child_name = None, None
        self.voice_ready = False
        self.volume = {"percent": None, "muted": None, "available": False, "backend": "pipewire", "error": None}
        self.recording_capability = records.capability()
        self.recording = {"state": "idle" if self.recording_capability["recording_supported"] else "disabled",
                          "error": self.recording_capability.get("reason")}
        self.latest_record, self.records = None, []
        self.shutdown_requested, self.shutdown_deadline = False, None
        self.on_shutdown_ready = lambda: None
        self.jobs.append((None, "audio.volume.read", self.executor.submit(volume.snapshot)))

    def snapshot(self, request_id=None, message=None):
        value = super().snapshot(request_id, message)
        value.update(run_id=self.run_id, play_id=self.play_id, scene_id=self.scene_id,
                     command_result=self.command_result,
                     capabilities={"actions": sorted(self.actions - ({"system.shutdown"} if not self.allow_poweroff else set())),
                                   "plays": list(PLAYS), "scenes": list(SCENES),
                                   "exhibit_ready": self.catalog.confirmed and self.hardware_ready(),
                                   "recording_supported": self.recording_capability["recording_supported"],
                                   "media_supported": self.media is not None},
                     profile={"profile_id": self.profile_id, "voice_ready": self.voice_ready},
                     volume=self.volume, recording=self.recording, latest_record=self.latest_record,
                     records=self.records, media=self.media() if callable(self.media) else self.media,
                     shutdown_requested=self.shutdown_requested)
        return value

    def read_snapshot(self):
        """ATT attributes max out at 512 bytes; rich state uses framed notify.

        A read neither renews ownership nor supersedes a full notification that
        is already in flight. The app can enrich a compact read at this revision.
        """
        revision = self.revision
        value = super().snapshot()
        self.revision = revision
        value.update(revision=revision, compact=True, run_id=self.run_id, message=None)
        if len(json.dumps(value, separators=(",", ":")).encode()) + 1 > 512:
            raise RuntimeError("Compact status exceeds the ATT attribute limit")
        return value

    def result(self, request_id, action, ok, message=None):
        self.command_result = dict(request_id=request_id, action=action, ok=ok, message=message)
        return self.publish(request_id, message)

    @staticmethod
    def payload(value, fields):
        payload = value.get("payload", {})
        if not isinstance(payload, dict) or set(payload) - set(fields):
            raise ValueError("지원하지 않는 명령 데이터예요.")
        return payload

    def owner_command(self, action, value, request_id):
        self.latest_owner_request = request_id
        try:
            if action == "session.stop":
                self.payload(value, ())
                self.action_id = request_id
                self.stop()
                return self.result(request_id, action, True)
            if self.shutdown_requested:
                raise ValueError("로봇 종료를 준비하고 있어요.")
            if action == "profile.set":
                payload = self.payload(value, ("child_name", "profile_id"))
                if self.worker:
                    raise ValueError("놀이가 끝난 뒤 이름을 연결해 주세요.")
                name = normalize_name(payload.get("child_name"))
                profile_id = str(uuid.UUID(payload["profile_id"])) if name else None
                self.child_name, self.profile_id = name or None, profile_id
                self.voice_ready = self.catalog.voice_ready(name)
                return self.result(request_id, action, True,
                                   None if self.voice_ready or not name else "이 이름의 음성 파일을 준비해 주세요.")
            if action == "audio.volume.set":
                payload = self.payload(value, ("volume",))
                percent = payload.get("volume")
                if type(percent) is not int or not 0 <= percent <= 100:
                    raise ValueError("소리 크기는 0에서 100 사이여야 해요.")
                if any(item[1] == action for item in self.jobs):
                    raise ValueError("소리 크기를 적용하고 있어요. 잠시 후 다시 시도해 주세요.")
                self.jobs.append((request_id, action, self.executor.submit(self.volume_service.set_volume, percent)))
                return self.publish(request_id)
            if action in ("records.list", "records.get"):
                payload = self.payload(value, ("offset", "limit") if action == "records.list" else ("record_id",))
                if len(self.jobs) >= 4:
                    raise ValueError("기록을 불러오는 중이에요.")
                if action == "records.list":
                    offset, limit = payload.get("offset", 0), payload.get("limit", 1)
                    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 3:
                        raise ValueError("기록 페이지가 올바르지 않아요.")
                    operation = lambda: self.records_service.list_records()[offset:offset + limit]
                else:
                    record_id = str(uuid.UUID(payload["record_id"]))
                    def operation():
                        found = [record for record in self.records_service.list_records() if record["id"] == record_id]
                        if not found:
                            raise ValueError("기록을 찾지 못했어요.")
                        return found
                self.jobs.append((request_id, action, self.executor.submit(operation)))
                return self.publish(request_id)
            if action == "system.shutdown":
                self.payload(value, ())
                if not self.allow_poweroff:
                    raise ValueError("운영자 전원 종료 설정이 필요해요.")
                self.shutdown_requested, self.shutdown_deadline = True, self.clock() + 2
                self.stop()
                return self.result(request_id, action, True, "동작을 멈추고 로봇 전원을 끌 준비를 하고 있어요.")
            play_id = scene_id = None
            if action == "dance.start":
                self.payload(value, ())
                play_id = "dance"
            elif action == "play.start":
                play_id = self.payload(value, ("play_id",)).get("play_id")
                if play_id not in PLAYS:
                    raise ValueError("지원하지 않는 놀이예요.")
            elif action == "scene.start":
                scene_id = self.payload(value, ("scene_id",)).get("scene_id")
                if scene_id not in SCENES:
                    raise ValueError("지원하지 않는 촬영 씬이에요.")
            elif action == "pose.reset":
                self.payload(value, ())
            else:
                raise ValueError("지원하지 않는 명령이에요.")
            if self.worker or self.state not in ("idle", "completed", "stopped") or not self.hardware_ready():
                raise ValueError("동작 중이거나 로봇 확인이 필요해요.")
            if play_id == "dance":
                if not self.confirmed:
                    raise ValueError("춤 동작 확인 설정이 필요해요.")
            else:
                self.catalog.build(play_id, scene_id, self.child_name, reset=action == "pose.reset")
            run_id = str(uuid.uuid4())
            specification = dict(run_id=run_id, play_id=play_id, scene_id=scene_id, name=self.child_name,
                                 reset=action == "pose.reset", dance_confirmed=self.confirmed,
                                 exhibit_confirmed=self.catalog.confirmed,
                                 recording_enabled=self.recording_capability["recording_supported"],
                                 record_root=str(self.records_service.root))
            worker = self.exhibit_worker_factory(specification)
            self.worker = worker
            self.run_id, self.play_id, self.scene_id = run_id, play_id, scene_id
            self.latest_record, self.records = None, []
            self.action_id, self.message, self.progress = request_id, None, 0.0
            self.worker_started, self.stop_started = self.clock(), None
            self.worker_timeout = 60
            self.state, self.phase = "starting", "prepare"
            self.recording = {"state": "idle" if specification["recording_enabled"] else "disabled",
                              "error": self.recording_capability.get("reason")}
            return self.result(request_id, action, True)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
            # Valid authenticated failures have a correlated ACK, not an optimistic success.
            message = str(error) if isinstance(error, ValueError) else "명령을 준비하지 못했어요. 로봇을 확인해 주세요."
            return self.result(request_id, action, False, message[:160])

    def worker_event(self, event):
        if isinstance(event.get("recording"), dict):
            self.recording = event["recording"]
        if isinstance(event.get("latest_record"), dict):
            self.latest_record = event["latest_record"]

    def tick(self):
        super().tick()
        if self.state == "error" and self.recording["state"] in ("recording", "saving"):
            self.recording = {"state": "error", "error": "worker_completion_unconfirmed"}
            self.publish()
        for item in self.jobs[:]:
            request_id, action, future = item
            if not future.done():
                continue
            self.jobs.remove(item)
            try:
                result = future.result()
                if action.startswith("audio.volume"):
                    self.volume = dict(result)
                    self.volume["percent"] = self.volume.pop("volume", None)
                    if not self.volume["available"] and request_id:
                        raise ValueError("로봇 소리 장치를 확인하지 못했어요.")
                else:
                    self.records = result
                if request_id and request_id == self.latest_owner_request:
                    self.result(request_id, action, True)
                else:
                    self.publish()
            except (ValueError, OSError, RuntimeError):
                if request_id and request_id == self.latest_owner_request:
                    self.result(request_id, action, False, "설정 또는 기록을 확인하지 못했어요. 다시 시도해 주세요.")
        if self.shutdown_requested and self.worker is None and self.shutdown_deadline is not None and self.clock() >= self.shutdown_deadline:
            self.shutdown_deadline = None
            if self.state == "error":
                self.shutdown_requested = False
                self.publish(message="정지를 확인하지 못해 전원을 끄지 않았어요. 현장에서 확인해 주세요.")
            else:
                self.state, self.phase = "shutting_down", "goodbye"
                self.publish()
                self.on_shutdown_ready()

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

