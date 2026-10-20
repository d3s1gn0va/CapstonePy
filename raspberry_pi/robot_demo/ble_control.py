"""Device-independent BLE command authorization and bounded worker supervision."""

from collections import OrderedDict, deque
import hashlib
import hmac
import json
import time
import uuid
from ble_credentials import valid_token

SERVICE_UUID = "C8A00001-7A1B-4F4A-9B5A-4355564F0001"
COMMAND_UUID = "C8A00002-7A1B-4F4A-9B5A-4355564F0001"
STATUS_UUID = "C8A00003-7A1B-4F4A-9B5A-4355564F0001"


class CommandError(ValueError):
    pass


class BLEControl:
    actions = {"session.claim", "session.resume", "session.status", "session.stop", "dance.start"}
    command_fields = {"version", "request_id", "client_id", "action", "code", "token"}
    def __init__(self, code, worker_factory, confirmed=False, clock=time.monotonic,
                 credentials=None, hardware_ready=lambda: True):
        if len(code) != 6 or not code.isascii() or not code.isdigit():
            raise ValueError("A six-digit temporary code is required")
        self.code, self.worker_factory, self.confirmed, self.clock = code, worker_factory, confirmed, clock
        self.code_deadline = clock() + 900
        self.credentials, self.hardware_ready = credentials, hardware_ready
        self.auth_id, self.auth_message = None, None
        self.owner = None
        self.heartbeat = 0
        self.worker = None
        self.worker_started = 0
        self.worker_timeout = 35
        self.stop_started = None
        self.state, self.phase, self.progress = "idle", "idle", 0.0
        self.message, self.action_id = None, None
        self.revision = 0
        self.seen = OrderedDict()
        self.failures = deque()
        self.on_status = lambda value: None

    def snapshot(self, request_id=None, message=None):
        self.revision += 1
        return dict(version=1, revision=self.revision, request_id=request_id or self.auth_id or self.action_id,
                    state=self.state, phase=self.phase, progress=self.progress,
                    control_granted=self.owner is not None,
                    controller_id=self.owner[1] if self.owner else None,
                    motion_ready=self.confirmed and self.state != "error" and self.hardware_ready(),
                    message=message if message is not None else self.auth_message or self.message)

    def publish(self, request_id=None, message=None):
        value = self.snapshot(request_id, message)
        self.on_status(value)
        return value

    def command(self, raw, device, paired):
        if not paired or not device:
            raise CommandError("Encrypted, paired connection required")
        if not 1 <= len(raw) <= 512:
            raise CommandError("Command size must be in 1..512 bytes")
        try:
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or value.get("version") != 1 or type(value["version"]) is not int:
                raise ValueError()
            if set(value) - self.command_fields:
                raise ValueError()
            request_id, client_id = (str(uuid.UUID(value[key])) for key in ("request_id", "client_id"))
            action = value["action"]
            if action not in self.actions:
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError) as error:
            raise CommandError("Invalid CUVO v1 command") from error
        self.tick()
        identity = (device, client_id)
        if action == "session.status":
            if identity == self.owner:
                self.heartbeat = self.clock()
            return self.publish(request_id)
        key = (device, client_id, request_id)
        digest = hashlib.sha256(raw).digest()
        if key in self.seen:
            if self.seen[key] != digest:
                raise CommandError("Request ID reused with a different command")
            return self.publish(request_id)
        self.seen[key] = digest
        if len(self.seen) > 256:
            self.seen.popitem(last=False)
        if action in ("session.claim", "session.resume"):
            if self.worker or (self.owner and self.owner != identity):
                return self.publish(request_id, "다른 놀이 또는 연결이 끝나기를 기다려 주세요.")
            self.auth_id, self.auth_message = request_id, None
            while self.failures and self.clock() - self.failures[0] >= 60:
                self.failures.popleft()
            if len(self.failures) >= 5:
                self.auth_message = "잠시 후 연결을 다시 확인해 주세요."
                return self.publish(request_id)
            code = value.get("code")
            if action == "session.resume":
                allowed = self.credentials is not None and self.credentials.accepts(device, client_id, value.get("token"))
            else:
                allowed = not (self.clock() > self.code_deadline or not isinstance(code, str)
                    or len(code) != 6 or not code.isascii() or not code.isdigit()
                    or not hmac.compare_digest(code, self.code))
                if self.credentials is not None and not valid_token(value.get("token")):
                    allowed = False
            if not allowed:
                self.failures.append(self.clock())
                self.auth_message = ("등록 정보를 확인하지 못했어요. 연결 코드로 다시 등록해 주세요."
                                     if action == "session.resume" else "연결 코드가 틀렸거나 만료됐어요.")
                return self.publish(request_id)
            if action == "session.claim" and self.credentials is not None:
                self.credentials.register(device, client_id, value["token"])
            self.owner, self.heartbeat = identity, self.clock()
            # A subsequent full status read must still confirm the successful claim.
            self.action_id, self.message = request_id, None
            return self.publish(request_id)
        if identity != self.owner:
            raise CommandError("Claim this controller before sending motion commands")
        self.heartbeat = self.clock()
        self.auth_id, self.auth_message = None, None
        return self.owner_command(action, value, request_id)

    def owner_command(self, action, value, request_id):
        """Extension point after the existing encrypted-owner and replay checks."""
        if action == "session.stop":
            self.action_id = request_id
            self.stop()
            return self.publish(request_id)
        if not self.confirmed or not self.hardware_ready() or self.worker or self.state not in ("idle", "completed", "stopped"):
            raise CommandError("Dance is locked, busy, or requires operator inspection")
        self.action_id, self.message, self.progress = request_id, None, 0.0
        try:
            self.worker = self.worker_factory()
        except (OSError, RuntimeError) as error:
            self.state, self.message = "error", "춤 실행 준비에 실패했어요. 로봇을 확인해 주세요."
            self.publish(request_id)
            raise CommandError("Worker start failed") from error
        self.worker_started, self.stop_started = self.clock(), None
        self.state, self.phase = "starting", "prepare"
        return self.publish(request_id)

    def stop(self):
        if self.worker:
            if self.stop_started is None:
                self.stop_started = self.clock()
                self.worker.terminate()
            self.state = "stopping"
        elif self.state != "error":
            self.state, self.phase = "stopped", "idle"

    def disconnected(self, device):
        if self.owner and self.owner[0] == device:
            self.stop()
            self.owner = None
            self.publish(message="연결이 끊겨 놀이를 중단했어요.")

    def tick(self):
        now = self.clock()
        if self.owner and now - self.heartbeat >= 3:
            self.stop()
            self.owner = None
            self.publish(message="연결 응답이 끊겨 놀이를 중단했어요.")
        if not self.worker:
            return
        if now - self.worker_started >= self.worker_timeout and self.stop_started is None:
            self.stop()
            self.publish(message="실행 시간 제한으로 중단하고 있어요.")
        try:
            events, exit_code = self.worker.poll()
            for event in events:
                self.worker_event(event)
                if event["state"] == "running" and self.stop_started is None:
                    self.state, self.phase, self.progress = "running", event["phase"], event["progress"]
                    self.publish()
            if exit_code is not None:
                terminal = self.worker.terminal
                if exit_code == 0 and terminal and terminal["state"] in ("completed", "stopped"):
                    cancelled = self.stop_started is not None
                    self.state = "stopped" if cancelled else terminal["state"]
                    self.progress, self.phase = (0, "idle") if cancelled else (terminal["progress"], terminal["phase"])
                    self.message = None
                else:
                    self.state, self.message = "error", "정지 또는 동작 완료를 확인하지 못했어요. 현장 확인이 필요해요."
                self.worker.close()
                self.worker, self.stop_started = None, None
                self.publish()
            elif self.stop_started is not None and now - self.stop_started >= 6:
                self.worker.kill()
                self.state, self.message = "error", "정지 확인 실패. 필요하면 현장에서 서보 전원을 차단해 주세요."
                self.publish()
        except (ValueError, OSError, RuntimeError):
            self.stop()
            self.message = "실행 응답 오류. 실제 정지 여부를 확인해 주세요."
            self.publish()

    def worker_event(self, event):
        """Optional metadata from a strictly validated worker transport."""
        pass
