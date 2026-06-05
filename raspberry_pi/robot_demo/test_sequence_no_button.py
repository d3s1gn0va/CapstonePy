#!/usr/bin/env python3
"""
버튼 없이 전체 시퀀스를 한 번만 시험합니다.

config.py에 실제 캘리브레이션 각도를 입력한 뒤 사용하세요.
버튼 배선을 연결하기 전에 전체 동작과 오디오를 확인할 수 있습니다.
"""

from main import run_demo_sequence, validate_runtime_config
import config
from serial_controller import SerialController


def main() -> None:
    validate_runtime_config()

    with SerialController() as controller:
        print(f"[Sequence test] Arduino 연결 포트: {controller.port}")
        controller.ping()

        print("[Sequence test] 초기 자세로 이동")
        controller.move_both(
            config.HEAD_NEUTRAL_DEG,
            config.ARM_DOWN_DEG,
            config.STARTUP_HOME_DURATION_MS,
        )

        input(
            "\n전체 시퀀스를 한 번 실행합니다. "
            "손을 즉시 전원에서 뺄 수 있는 상태인지 확인한 뒤 Enter를 누르세요. "
        )

        run_demo_sequence(controller)

        print("[Sequence test] 완료")


if __name__ == "__main__":
    main()
