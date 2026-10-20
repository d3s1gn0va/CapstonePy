#!/usr/bin/env python3
"""
1차 심사용 워킹 프로토타입 전체 시퀀스

버튼 한 번:
1. 고개를 로봇 기준 왼쪽으로 회전
2. "지우야~" WAV 재생과 거의 동시에 오른팔 상승
3. "우리 같이 놀까?" WAV 재생
4. 짧게 유지
5. 고개와 오른팔을 초기 자세로 복귀

시연 중 버튼 입력은 무시합니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time
from typing import Optional

from gpiozero import Button, LED

import config
from audio_player import (
    AudioPlayerError,
    play_wav_async,
    play_wav_blocking,
    wait_for_audio,
)
from serial_controller import SerialController, SerialControllerError


class ConfigurationError(RuntimeError):
    """캘리브레이션 또는 파일 설정 오류."""


FULL_RANGE_HEAD_MIN_DEG = 0
FULL_RANGE_HEAD_MAX_DEG = 180
FULL_RANGE_START_DURATION_MS = 1000
FULL_RANGE_SWEEP_DURATION_MS = 2000
FULL_RANGE_PAUSE_SEC = 0.5

_poweroff_requested = False


def _require_angle(name: str, value: Optional[int], minimum: int, maximum: int) -> int:
    if value is None:
        raise ConfigurationError(
            f"{name} 값이 아직 None입니다. "
            "`python3 calibrate_servos.py`로 각도를 찾은 뒤 "
            "config.py에 기록하세요."
        )

    if not isinstance(value, int):
        raise ConfigurationError(f"{name} 값은 정수여야 합니다: {value!r}")

    if not minimum <= value <= maximum:
        raise ConfigurationError(
            f"{name}={value}가 안전 범위 {minimum}~{maximum} 밖입니다. "
            "Arduino 코드와 config.py의 안전 범위를 함께 확인하세요."
        )

    return value


def _require_audio(path: Path) -> None:
    if not path.exists():
        raise ConfigurationError(
            f"WAV 파일이 없습니다: {path}\n"
            "audio 폴더에 파일을 복사하세요."
        )


def validate_runtime_config() -> None:
    _require_angle(
        "HEAD_NEUTRAL_DEG",
        config.HEAD_NEUTRAL_DEG,
        config.HEAD_SAFE_MIN_DEG,
        config.HEAD_SAFE_MAX_DEG,
    )
    _require_angle(
        "HEAD_LEFT_DEG",
        config.HEAD_LEFT_DEG,
        config.HEAD_SAFE_MIN_DEG,
        config.HEAD_SAFE_MAX_DEG,
    )
    _require_angle(
        "ARM_DOWN_DEG",
        config.ARM_DOWN_DEG,
        config.ARM_SAFE_MIN_DEG,
        config.ARM_SAFE_MAX_DEG,
    )
    _require_angle(
        "ARM_UP_DEG",
        config.ARM_UP_DEG,
        config.ARM_SAFE_MIN_DEG,
        config.ARM_SAFE_MAX_DEG,
    )
    _require_angle(
        "CAMERA_CENTER_DEG",
        config.CAMERA_CENTER_DEG,
        config.CAMERA_SAFE_MIN_DEG,
        config.CAMERA_SAFE_MAX_DEG,
    )
    _require_angle(
        "CAMERA_LEFT_DEG",
        config.CAMERA_LEFT_DEG,
        config.CAMERA_SAFE_MIN_DEG,
        config.CAMERA_SAFE_MAX_DEG,
    )
    _require_angle(
        "CAMERA_RIGHT_DEG",
        config.CAMERA_RIGHT_DEG,
        config.CAMERA_SAFE_MIN_DEG,
        config.CAMERA_SAFE_MAX_DEG,
    )

    _require_audio(config.AUDIO_NAME_CALL)
    _require_audio(config.AUDIO_LETS_PLAY)


def move_home(controller: SerialController) -> None:
    print("[Sequence] 초기 자세로 복귀")
    controller.move_both(
        config.HEAD_NEUTRAL_DEG,
        config.ARM_DOWN_DEG,
        config.RETURN_DURATION_MS,
    )


def run_demo_sequence(controller: SerialController) -> None:
    """
    한 번의 전체 시연 시퀀스를 실행합니다.
    이 함수가 실행되는 동안 main loop는 새로운 버튼 입력을 읽지 않습니다.
    """
    print("\n[Sequence] 시작")

    print("[Sequence] 고개 회전 + 오른팔 상승 + 01_name_call.wav 재생")
    pending_motion = controller.move_both(
        config.HEAD_LEFT_DEG,
        config.ARM_UP_DEG,
        wait=False,
        duration_ms=config.HEAD_TURN_DURATION_MS,
    )
    audio_process = play_wav_async(config.AUDIO_NAME_CALL)

    # 고개/팔 움직임과 음성이 모두 끝난 뒤 다음 문장으로 넘어갑니다.
    controller.wait_for_done(pending_motion)
    wait_for_audio(audio_process)

    time.sleep(config.AFTER_HEAD_TURN_PAUSE_SEC)
    time.sleep(config.BETWEEN_AUDIO_PAUSE_SEC)

    print("[Sequence] 02_lets_play.wav 재생")
    play_wav_blocking(config.AUDIO_LETS_PLAY)

    time.sleep(config.AFTER_AUDIO_HOLD_SEC)

    print("[Sequence] 고개와 오른팔 원위치 복귀")
    move_home(controller)

    print("[Sequence] 완료\n")


def run_camera_sequence(controller: SerialController) -> None:
    """카메라 좌우 회전 서보만 천천히 움직입니다."""
    print("\n[Camera] 시작")

    print("[Camera] 왼쪽으로 이동")
    controller.move_camera(
        config.CAMERA_LEFT_DEG,
        config.CAMERA_SWEEP_DURATION_MS,
    )

    print("[Camera] 오른쪽으로 이동")
    controller.move_camera(
        config.CAMERA_RIGHT_DEG,
        config.CAMERA_SWEEP_DURATION_MS,
    )

    print("[Camera] 중앙으로 복귀")
    controller.move_camera(
        config.CAMERA_CENTER_DEG,
        config.CAMERA_RETURN_DURATION_MS,
    )

    print("[Camera] 완료\n")


def run_neck_sweep_once() -> None:
    """
    SSH 수동 점검용 일회성 고개 전체 범위 이동.
    팔과 카메라 서보는 움직이지 않습니다.
    """
    print("[Neck sweep] Arduino USB Serial 연결")
    with SerialController() as controller:
        print(f"[Neck sweep] Arduino 연결 포트: {controller.port}")
        controller.ping()
        print("[Neck sweep] Arduino PING 성공")

        print(
            "[Neck sweep] 경고: 고개 서보를 0도에서 180도까지 "
            "전체 범위로 움직입니다. 기구물 충돌 위험이 있습니다."
        )

        print("[Neck sweep] 고개 서보를 0도로 이동")
        controller.move_head(
            FULL_RANGE_HEAD_MIN_DEG,
            FULL_RANGE_START_DURATION_MS,
        )

        time.sleep(FULL_RANGE_PAUSE_SEC)

        print("[Neck sweep] 고개 서보를 180도로 이동")
        controller.move_head(
            FULL_RANGE_HEAD_MAX_DEG,
            FULL_RANGE_SWEEP_DURATION_MS,
        )

        print("[Neck sweep] 이동 완료 응답 확인")
        print("[Neck sweep] 완료")


def request_poweroff() -> None:
    """
    전원 OFF 버튼용 안전 종료 요청.

    Raspberry Pi에서 hyunwoo 사용자가 shutdown 명령만 비밀번호 없이
    실행할 수 있도록 sudoers 설정이 되어 있어야 합니다.
    """
    global _poweroff_requested

    if _poweroff_requested:
        return

    _poweroff_requested = True

    print("[Power] 전원 OFF 버튼 입력")
    print("[Power] Raspberry Pi 안전 종료 요청")

    try:
        subprocess.run(
            ["sudo", "-n", "shutdown", "-h", "now"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(
            "[Power] 종료 명령 실패: sudo 비밀번호 없는 shutdown 권한이 "
            f"필요합니다. 종료 코드={exc.returncode}"
        )
        _poweroff_requested = False


def wait_until_released(button: Button) -> None:
    if button.is_pressed:
        button.wait_for_release()
    time.sleep(0.10)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raspberry Pi robot demo runner",
    )
    parser.add_argument(
        "--neck-sweep-once",
        action="store_true",
        help="SSH 수동 점검용으로 고개 서보를 0도에서 180도까지 한 번만 이동",
    )
    parser.add_argument(
        "--confirm-full-range",
        action="store_true",
        help="고개 서보 전체 범위 이동 위험을 확인했음을 명시",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.neck_sweep_once:
        if not args.confirm_full_range:
            print(
                "[Neck sweep refused] --neck-sweep-once는 고개 서보를 "
                "0도에서 180도까지 움직이는 위험한 전체 범위 테스트입니다. "
                "실행하려면 --confirm-full-range를 함께 입력하세요.",
                file=sys.stderr,
            )
            return 2

        run_neck_sweep_once()
        return 0

    if args.confirm_full_range:
        print(
            "[Robot demo] --confirm-full-range는 --neck-sweep-once와 "
            "함께 사용할 때만 의미가 있습니다.",
            file=sys.stderr,
        )
        return 2

    print("[Robot demo] 설정 확인")
    validate_runtime_config()

    demo_button = Button(
        config.BUTTON_GPIO,
        pull_up=True,
        bounce_time=config.BUTTON_BOUNCE_SEC,
    )
    power_off_button = Button(
        config.POWER_OFF_BUTTON_GPIO,
        pull_up=True,
        bounce_time=config.BUTTON_BOUNCE_SEC,
    )
    camera_button = Button(
        config.CAMERA_BUTTON_GPIO,
        pull_up=True,
        bounce_time=config.BUTTON_BOUNCE_SEC,
    )
    camera_led = LED(config.CAMERA_LED_GPIO)
    camera_led.off()
    power_off_button.when_pressed = request_poweroff

    try:
        with SerialController() as controller:
            print(f"[Robot demo] Arduino 연결 포트: {controller.port}")
            controller.ping()
            print("[Robot demo] Arduino PING 성공")

            print("[Robot demo] 부팅 후 초기 자세로 이동")
            controller.move_both(
                config.HEAD_NEUTRAL_DEG,
                config.ARM_DOWN_DEG,
                config.STARTUP_HOME_DURATION_MS,
            )

            print("[Robot demo] 버튼 입력 대기")

            while True:
                if camera_button.is_pressed:
                    camera_led.on()
                    try:
                        run_camera_sequence(controller)
                    except SerialControllerError as exc:
                        print(f"[Camera error] {exc}")
                    finally:
                        camera_led.off()

                    wait_until_released(camera_button)
                    print("[Robot demo] 버튼 입력 대기")
                    continue

                if demo_button.is_pressed:
                    try:
                        run_demo_sequence(controller)

                    except (SerialControllerError, AudioPlayerError) as exc:
                        print(f"[Robot demo error] {exc}")
                        print("[Robot demo] 가능한 경우 초기 자세 복귀 시도")

                        try:
                            move_home(controller)
                        except Exception as home_exc:
                            print(f"[Robot demo] 복귀 실패: {home_exc}")

                    wait_until_released(demo_button)
                    print("[Robot demo] 버튼 입력 대기")
                    continue

                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[Robot demo] 사용자 종료")

    finally:
        demo_button.close()
        power_off_button.close()
        camera_button.close()
        camera_led.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
