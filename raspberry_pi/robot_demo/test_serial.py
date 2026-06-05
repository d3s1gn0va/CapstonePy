#!/usr/bin/env python3
"""Raspberry Pi와 Arduino Mega의 USB Serial 연결만 시험합니다."""

from serial_controller import SerialController


def main() -> None:
    with SerialController() as controller:
        print(f"[Serial test] 연결된 포트: {controller.port}")

        controller.ping()
        print("[Serial test] PING 성공")

        status = controller.status()
        print(f"[Serial test] {status}")

        print("[Serial test] 완료")


if __name__ == "__main__":
    main()
