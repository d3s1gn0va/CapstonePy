# Deployment Guide

## 1. Python 설정만 바꾼 경우

1. `raspberry_pi/robot_demo/config.py` 또는 Python 파일을 수정한다.
2. `scripts/check_python.sh`를 실행해 Python 문법 검사를 통과한다.
3. `scripts/deploy_pi.sh`로 Raspberry Pi의 `/home/hyunwoo/robot_demo/`에 배포한다.
4. 필요하면 `scripts/restart_robot.sh`로 로봇 실행 프로그램을 재시작한다.
5. `scripts/status_robot.sh`와 `scripts/logs_robot.sh`로 실행 상태와 최근 로그를 확인한다.

Python 설정 변경은 Arduino 펌웨어 변경과 구분한다. 서보 목표 각도와 이동 시간만 바꾼 경우에도 실제 기구물 충돌 가능성을 먼저 생각한다.

## 2. Arduino 코드도 바꾼 경우

1. `arduino/servo_controller/servo_controller.ino`를 수정한다.
2. 안전 범위, 펄스 폭, 서보 채널 변경 사항을 검토한다.
3. `scripts/build_arduino_remote.sh`로 Raspberry Pi에서 Arduino CLI 컴파일까지만 실행한다.
4. Arduino Mega 실제 업로드가 필요하면 사용자에게 위험성을 설명하고 명시적인 승인을 받는다.
5. 사용자가 `Arduino 업로드 승인`이라고 말한 경우에만 `scripts/flash_arduino_remote.sh`를 실행한다.
6. 업로드 후 최소 3초 이상 기다린 뒤 Arduino 응답과 로봇 프로그램 재시작 절차를 확인한다.

`SERVO_MIN_PULSE_US`, `SERVO_MAX_PULSE_US`는 명시적인 승인 없이 변경하지 않는다. 서보 안전 범위는 한 번에 5도보다 크게 넓히지 않는다.
