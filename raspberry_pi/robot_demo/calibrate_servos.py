#!/usr/bin/env python3
"""
기구물을 조립한 뒤 안전 각도를 찾기 위한 대화형 도구입니다.

Arduino 쪽 안전 범위를 먼저 확인하세요.
처음부터 0도 또는 180도를 입력하지 마세요.
5도 정도씩만 움직이세요.
"""

from __future__ import annotations

import shlex

import config
from serial_controller import SerialController, SerialControllerError


HELP_TEXT = """
명령:
  ping
  status
  head <angle> [duration_ms]
  arm <angle> [duration_ms]
  both <head_angle> <arm_angle> [duration_ms]
  stop
  disable
  help
  quit

예시:
  head 95 400
  arm 85 500
  both 90 90 600

주의:
- 각도는 처음부터 크게 바꾸지 말고 5도씩만 조절하세요.
- 기구물이 걸리거나 서보가 떨리면 즉시 stop 또는 disable을 입력하세요.
- 최종적으로 아래 네 값을 메모하세요.
  HEAD_NEUTRAL_DEG
  HEAD_LEFT_DEG
  ARM_DOWN_DEG
  ARM_UP_DEG
""".strip()


def _parse_int(text: str, label: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label}은 정수여야 합니다: {text}") from exc


def _check_range(angle: int, minimum: int, maximum: int, label: str) -> None:
    if not minimum <= angle <= maximum:
        raise ValueError(
            f"{label} 각도는 현재 안전 범위 {minimum}~{maximum} 안에서만 "
            f"입력하세요. 입력값={angle}"
        )


def main() -> None:
    print(HELP_TEXT)

    with SerialController() as controller:
        print(f"\n[Calibration] 연결된 포트: {controller.port}")
        controller.ping()
        print("[Calibration] Arduino 응답 정상")

        while True:
            try:
                raw = input("\ncalibrate> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Calibration] 종료")
                return

            if not raw:
                continue

            parts = shlex.split(raw)
            command = parts[0].lower()

            try:
                if command in {"quit", "exit", "q"}:
                    print("[Calibration] 종료")
                    return

                if command == "help":
                    print(HELP_TEXT)
                    continue

                if command == "ping":
                    controller.ping()
                    print("[Calibration] PING 성공")
                    continue

                if command == "status":
                    print(controller.status())
                    continue

                if command == "stop":
                    controller.stop()
                    print("[Calibration] 이동 중지")
                    continue

                if command == "disable":
                    controller.disable()
                    print("[Calibration] PWM 출력 OFF")
                    continue

                if command == "head":
                    if len(parts) not in {2, 3}:
                        raise ValueError("사용법: head <angle> [duration_ms]")
                    angle = _parse_int(parts[1], "head angle")
                    duration = _parse_int(parts[2], "duration") if len(parts) == 3 else 400
                    _check_range(
                        angle,
                        config.HEAD_SAFE_MIN_DEG,
                        config.HEAD_SAFE_MAX_DEG,
                        "고개",
                    )
                    controller.move_head(angle, duration)
                    continue

                if command == "arm":
                    if len(parts) not in {2, 3}:
                        raise ValueError("사용법: arm <angle> [duration_ms]")
                    angle = _parse_int(parts[1], "arm angle")
                    duration = _parse_int(parts[2], "duration") if len(parts) == 3 else 500
                    _check_range(
                        angle,
                        config.ARM_SAFE_MIN_DEG,
                        config.ARM_SAFE_MAX_DEG,
                        "팔",
                    )
                    controller.move_arm(angle, duration)
                    continue

                if command == "both":
                    if len(parts) not in {3, 4}:
                        raise ValueError(
                            "사용법: both <head_angle> <arm_angle> [duration_ms]"
                        )
                    head_angle = _parse_int(parts[1], "head angle")
                    arm_angle = _parse_int(parts[2], "arm angle")
                    duration = _parse_int(parts[3], "duration") if len(parts) == 4 else 600
                    _check_range(
                        head_angle,
                        config.HEAD_SAFE_MIN_DEG,
                        config.HEAD_SAFE_MAX_DEG,
                        "고개",
                    )
                    _check_range(
                        arm_angle,
                        config.ARM_SAFE_MIN_DEG,
                        config.ARM_SAFE_MAX_DEG,
                        "팔",
                    )
                    controller.move_both(head_angle, arm_angle, duration)
                    continue

                print(f"[Calibration] 알 수 없는 명령: {command}")
                print("help를 입력하면 명령 목록을 볼 수 있습니다.")

            except (ValueError, SerialControllerError) as exc:
                print(f"[Calibration error] {exc}")


if __name__ == "__main__":
    main()
