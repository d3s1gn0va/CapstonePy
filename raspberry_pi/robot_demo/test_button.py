#!/usr/bin/env python3
"""GPIO17에 연결한 4핀 택트 스위치만 시험합니다."""

from datetime import datetime

from gpiozero import Button

import config


def main() -> None:
    button = Button(
        config.BUTTON_GPIO,
        pull_up=True,
        bounce_time=config.BUTTON_BOUNCE_SEC,
    )

    print("[Button test] GPIO17 버튼 입력 대기")
    print("[Button test] 종료하려면 Ctrl+C를 누르세요.")

    try:
        while True:
            button.wait_for_press()
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[Button test] 눌림 감지: {timestamp}")

            # 버튼을 길게 누른 상태에서 중복 감지되지 않도록
            # 손을 뗄 때까지 기다립니다.
            button.wait_for_release()

    except KeyboardInterrupt:
        print("\n[Button test] 종료")

    finally:
        button.close()


if __name__ == "__main__":
    main()
