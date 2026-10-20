"""
Arduino Mega USB Serial 통신 모듈

Arduino 코드에서 지원하는 텍스트 명령:
- PING
- STATUS
- MOVE_HEAD,<angle_deg>,<duration_ms>
- MOVE_ARM,<angle_deg>,<duration_ms>
- MOVE_CAMERA,<angle_deg>,<duration_ms>
- MOVE_BOTH,<head_angle_deg>,<arm_angle_deg>,<duration_ms>
- STOP
- DISABLE
"""

from __future__ import annotations

from dataclasses import dataclass
from glob import glob
from pathlib import Path
import time
from typing import Iterable, List, Optional

import serial

import config


class SerialControllerError(RuntimeError):
    """Arduino USB Serial 통신 오류."""


@dataclass(frozen=True)
class PendingMotion:
    done_message: str
    duration_ms: int


def _existing_paths(patterns: Iterable[str]) -> List[str]:
    results: List[str] = []
    for pattern in patterns:
        results.extend(sorted(glob(pattern)))
    return [path for path in results if Path(path).exists()]


def find_serial_port(explicit_port: Optional[str] = None) -> str:
    """
    Arduino USB Serial 장치 경로를 찾습니다.

    우선순위:
    1. config.py에 직접 지정한 SERIAL_PORT
    2. /dev/serial/by-id/*
    3. /dev/ttyACM*
    4. /dev/ttyUSB*
    """
    if explicit_port:
        if not Path(explicit_port).exists():
            raise SerialControllerError(
                f"설정한 Serial 포트를 찾을 수 없습니다: {explicit_port}"
            )
        return explicit_port

    candidates = _existing_paths(
        [
            "/dev/serial/by-id/*",
            "/dev/ttyACM*",
            "/dev/ttyUSB*",
        ]
    )

    # 같은 장치가 심볼릭 링크와 tty 경로로 중복 검출될 수 있으므로
    # 첫 번째 by-id 경로를 우선 사용합니다.
    if not candidates:
        raise SerialControllerError(
            "Arduino USB Serial 장치를 찾지 못했습니다. "
            "USB 데이터 케이블 연결을 확인하고 "
            "`ls -l /dev/serial/by-id/` 또는 "
            "`ls /dev/ttyACM* /dev/ttyUSB*`를 실행해 보세요."
        )

    return candidates[0]


class SerialController:
    def __init__(self, port: Optional[str] = None) -> None:
        self.port = find_serial_port(port or config.SERIAL_PORT)
        self.serial: Optional[serial.Serial] = None

    def connect(self) -> None:
        if self.serial and self.serial.is_open:
            return

        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=config.SERIAL_BAUDRATE,
                timeout=0.10,
                write_timeout=1.0,
            )
        except serial.SerialException as exc:
            raise SerialControllerError(
                f"Serial 포트를 열 수 없습니다: {self.port}: {exc}"
            ) from exc

        # USB Serial 연결 시 Arduino가 재부팅될 수 있으므로 기다립니다.
        time.sleep(config.ARDUINO_RESET_WAIT_SEC)
        self._drain_input()

    def close(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()

    def __enter__(self) -> "SerialController":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _require_open(self) -> serial.Serial:
        if not self.serial or not self.serial.is_open:
            raise SerialControllerError("Serial 포트가 열려 있지 않습니다.")
        return self.serial

    def _drain_input(self) -> None:
        ser = self._require_open()
        time.sleep(0.03)
        while ser.in_waiting > 0:
            raw = ser.readline()
            line = raw.decode("utf-8", errors="replace").strip()
            if line and config.LOG_SERIAL_LINES:
                print(f"[Arduino startup] {line}")

    def _write_line(self, line: str) -> None:
        ser = self._require_open()
        payload = (line.strip() + "\n").encode("utf-8")
        try:
            ser.write(payload)
            ser.flush()
        except serial.SerialException as exc:
            raise SerialControllerError(
                f"Serial 송신에 실패했습니다: {exc}"
            ) from exc
        print(f"[Pi -> Arduino] {line}")

    def _read_nonempty_line_until(self, deadline: float) -> Optional[str]:
        ser = self._require_open()

        while time.monotonic() < deadline:
            try:
                raw = ser.readline()
            except serial.SerialException as exc:
                raise SerialControllerError(
                    f"Serial 수신에 실패했습니다: {exc}"
                ) from exc

            if not raw:
                continue

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if config.LOG_SERIAL_LINES:
                print(f"[Arduino -> Pi] {line}")

            return line

        return None

    def _wait_for_exact(self, expected: str, timeout_sec: float) -> str:
        deadline = time.monotonic() + timeout_sec

        while True:
            line = self._read_nonempty_line_until(deadline)

            if line is None:
                raise SerialControllerError(
                    f"Arduino 응답 시간 초과: 기다린 응답={expected!r}"
                )

            if line == expected:
                return line

            if line.startswith("ERR"):
                raise SerialControllerError(
                    f"Arduino 오류 응답: {line}"
                )

            # READY, STATUS 등 예상하지 않은 정보 줄은 로그만 남기고 계속 읽습니다.

    def ping(self) -> None:
        self._drain_input()
        self._write_line("PING")
        self._wait_for_exact("ACK,PING", config.SERIAL_ACK_TIMEOUT_SEC)

    def status(self) -> str:
        self._drain_input()
        self._write_line("STATUS")

        deadline = time.monotonic() + config.SERIAL_ACK_TIMEOUT_SEC

        while True:
            line = self._read_nonempty_line_until(deadline)
            if line is None:
                raise SerialControllerError("STATUS 응답 시간 초과")
            if line.startswith("STATUS,"):
                return line
            if line.startswith("ERR"):
                raise SerialControllerError(f"Arduino 오류 응답: {line}")

    def stop(self) -> None:
        self._drain_input()
        self._write_line("STOP")
        self._wait_for_exact("ACK,STOP", config.SERIAL_ACK_TIMEOUT_SEC)

    def disable(self) -> None:
        self._drain_input()
        self._write_line("DISABLE")
        self._wait_for_exact("ACK,DISABLE", config.SERIAL_ACK_TIMEOUT_SEC)

    def _start_motion(
        self,
        command: str,
        ack_message: str,
        done_message: str,
        duration_ms: int,
    ) -> PendingMotion:
        if duration_ms <= 0:
            raise ValueError("duration_ms는 1 이상이어야 합니다.")

        self._drain_input()
        self._write_line(command)
        self._wait_for_exact(ack_message, config.SERIAL_ACK_TIMEOUT_SEC)

        return PendingMotion(
            done_message=done_message,
            duration_ms=duration_ms,
        )

    def wait_for_done(
        self,
        pending: PendingMotion,
        extra_timeout_sec: Optional[float] = None,
    ) -> None:
        margin = (
            config.SERIAL_DONE_MARGIN_SEC
            if extra_timeout_sec is None
            else extra_timeout_sec
        )
        timeout = max(0.1, pending.duration_ms / 1000.0 + margin)
        self._wait_for_exact(pending.done_message, timeout)

    def move_head(
        self,
        angle_deg: int,
        duration_ms: int,
        wait: bool = True,
    ) -> PendingMotion:
        pending = self._start_motion(
            command=f"MOVE_HEAD,{angle_deg},{duration_ms}",
            ack_message="ACK,MOVE_HEAD",
            done_message="DONE,MOVE_HEAD",
            duration_ms=duration_ms,
        )
        if wait:
            self.wait_for_done(pending)
        return pending

    def move_arm(
        self,
        angle_deg: int,
        duration_ms: int,
        wait: bool = True,
    ) -> PendingMotion:
        pending = self._start_motion(
            command=f"MOVE_ARM,{angle_deg},{duration_ms}",
            ack_message="ACK,MOVE_ARM",
            done_message="DONE,MOVE_ARM",
            duration_ms=duration_ms,
        )
        if wait:
            self.wait_for_done(pending)
        return pending

    def move_camera(
        self,
        angle_deg: int,
        duration_ms: int,
        wait: bool = True,
    ) -> PendingMotion:
        pending = self._start_motion(
            command=f"MOVE_CAMERA,{angle_deg},{duration_ms}",
            ack_message="ACK,MOVE_CAMERA",
            done_message="DONE,MOVE_CAMERA",
            duration_ms=duration_ms,
        )
        if wait:
            self.wait_for_done(pending)
        return pending

    def move_both(
        self,
        head_angle_deg: int,
        arm_angle_deg: int,
        duration_ms: int,
        wait: bool = True,
    ) -> PendingMotion:
        pending = self._start_motion(
            command=(
                f"MOVE_BOTH,{head_angle_deg},"
                f"{arm_angle_deg},{duration_ms}"
            ),
            ack_message="ACK,MOVE_BOTH",
            done_message="DONE,MOVE_BOTH",
            duration_ms=duration_ms,
        )
        if wait:
            self.wait_for_done(pending)
        return pending

    def group_capabilities(self) -> dict[int, tuple[int, int, int]]:
        self._drain_input()
        self._write_line("CAPS")
        deadline = time.monotonic() + config.SERIAL_ACK_TIMEOUT_SEC
        while True:
            line = self._read_nonempty_line_until(deadline)
            if line is None:
                raise SerialControllerError("CAPS response timeout")
            if line.startswith("ERR"):
                raise SerialControllerError(f"Six-axis firmware required: {line}")
            if not line.startswith("CAPS,MOVE_GROUP,"):
                continue
            try:
                result = {}
                for item in line.split(",")[2:]:
                    channel, low, high, neutral = map(int, item.split(":"))
                    if channel in result:
                        raise ValueError("Duplicate channel")
                    result[channel] = (low, high, neutral)
                if set(result) != set(range(6)):
                    raise ValueError("Expected six channels")
                return result
            except ValueError as exc:
                raise SerialControllerError("Invalid CAPS response") from exc

    def move_group(self, targets: dict[int, int], duration_ms: int, wait: bool = True) -> PendingMotion:
        if not isinstance(targets, dict) or not 1 <= len(targets) <= 6:
            raise ValueError("One to six distinct channel targets are required")
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise ValueError("Group duration must be 1..60000ms")
        for channel, angle in targets.items():
            if type(channel) is not int or not 0 <= channel <= 5:
                raise ValueError("Group channel must be 0..5")
            if type(angle) is not int or not 0 <= angle <= 180:
                raise ValueError("Group angle must be 0..180")
        pairs = ",".join(f"{channel},{targets[channel]}" for channel in sorted(targets))
        pending = self._start_motion(f"MOVE_GROUP,{duration_ms},{pairs}",
                                     "ACK,MOVE_GROUP", "DONE,MOVE_GROUP", duration_ms)
        if wait:
            self.wait_for_done(pending)
        return pending
