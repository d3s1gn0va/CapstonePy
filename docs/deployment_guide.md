# Deployment Guide

## 공통 전제

* Mac 프로젝트 루트: `/Users/hyunwoo/Documents/capstone design/capstone-robot-project`
* Raspberry Pi SSH 주소: `hyunwoo@192.168.0.39`
* SSH 개인키 경로: `~/.ssh/robotpi_ed25519`
* Raspberry Pi 실행 코드 경로: `/home/hyunwoo/robot_demo`
* Arduino 원격 빌드 임시 경로: `/home/hyunwoo/capstone-robot-build/servo_controller`
* Arduino Mega FQBN: `arduino:avr:mega`

Raspberry Pi 배포, 프로그램 재시작, 자동 실행 활성화, Arduino 업로드는 각각 별도 작업으로 취급한다.

## 1. Python 설정만 바꾼 경우

1. `raspberry_pi/robot_demo/config.py` 또는 Python 파일을 수정한다.
2. `scripts/check_python.sh`를 실행해 Python 문법 검사를 통과한다.
3. `scripts/deploy_pi.sh`로 Raspberry Pi의 `/home/hyunwoo/robot_demo/`에 배포한다.
4. 필요하면 `scripts/restart_robot.sh`로 로봇 실행 프로그램을 재시작한다.
5. `scripts/status_robot.sh`로 실행 상태, Arduino USB Serial 후보, `pw-play` 존재 여부, 최근 로그를 확인한다.
6. 장시간 로그 확인이 필요하면 `scripts/logs_robot.sh`를 사용한다.

`deploy_pi.sh`는 `.env`, 로그, `__pycache__`, `.DS_Store`, `._*`를 제외하고 rsync한다. Arduino 펌웨어 컴파일이나 업로드는 수행하지 않는다.

## 2. Arduino 코드도 바꾼 경우

1. `arduino/servo_controller/servo_controller.ino`를 수정한다.
2. `SERVO_MIN_PULSE_US`, `SERVO_MAX_PULSE_US`, 안전 각도 범위 변경 여부를 검토한다.
3. 서보 안전 범위를 넓히는 경우 실제 기구물 충돌과 과부하 가능성을 먼저 경고한다.
4. `scripts/build_arduino_remote.sh`로 Raspberry Pi에 Arduino 코드를 복사하고 `arduino-cli compile --fqbn arduino:avr:mega`까지만 실행한다.
5. 컴파일이 성공해도 업로드는 자동으로 진행하지 않는다.

`build_arduino_remote.sh`는 원격 빌드 경로 `/home/hyunwoo/capstone-robot-build/servo_controller`만 사용한다. Raspberry Pi 실행 코드 경로 `/home/hyunwoo/robot_demo`를 수정하지 않는다.

## 3. Arduino 업로드가 필요한 경우

Arduino Mega 실제 업로드는 위험 작업이다. 사용자가 별도로 `Arduino 업로드 승인`이라고 명확히 말한 뒤에만 진행한다.

업로드 스크립트:

```bash
scripts/flash_arduino_remote.sh
```

스크립트 동작:

1. 위험 경고를 출력한다.
2. 실행자에게 정확한 승인 문구 `Arduino 업로드 승인` 입력을 요구한다.
3. Raspberry Pi의 로봇 실행 프로그램을 중지한다.
4. Arduino USB 포트를 `/dev/serial/by-id/*`, `/dev/ttyACM*`, `/dev/ttyUSB*` 순서로 탐색한다.
5. Arduino 코드를 다시 컴파일한다.
6. Arduino Mega에 업로드한다.
7. 3초 이상 기다려 Arduino reset이 끝나도록 한다.
8. Serial로 `PING`을 보내고 `ACK,PING` 응답을 확인한다.
9. 로봇 프로그램 재시작 명령 `scripts/restart_robot.sh`를 안내한다.

업로드 후에도 실제 서보 움직임 테스트는 작은 각도부터 진행한다.

## 4. 상태 확인

상태 확인:

```bash
scripts/status_robot.sh
```

로그 확인:

```bash
scripts/logs_robot.sh
```

`status_robot.sh`는 로봇 프로세스, systemd 상태, Arduino USB Serial 후보, `pw-play` 존재 여부, 최근 로그를 출력한다.

## 안전 메모

`SERVO_MIN_PULSE_US`, `SERVO_MAX_PULSE_US`는 명시적인 승인 없이 변경하지 않는다. 서보 안전 범위는 한 번에 5도보다 크게 넓히지 않는다. Raspberry Pi 설정 변경과 Arduino 펌웨어 변경은 반드시 구분한다.
