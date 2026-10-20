# Deployment Guide

## 공통 전제

* Mac 프로젝트 루트: `/Users/hyunwoo/Documents/capstone design/capstone-robot-project`
* Raspberry Pi SSH 주소: `hyunwoo@192.168.0.39`
* SSH 개인키 경로: `~/.ssh/robotpi_ed25519`
* Raspberry Pi 실행 코드 경로: `/home/hyunwoo/robot_demo`
* Arduino 원격 빌드 임시 경로: `/home/hyunwoo/capstone-robot-build/servo_controller`
* Arduino Mega FQBN: `arduino:avr:mega`

Raspberry Pi 배포, 프로그램 재시작, 자동 실행 활성화, Arduino 업로드는 각각 별도 작업으로 취급한다.

2026-10-05 최신 사용자 지시: "업로드 승인. 앞으로 그냥 바로 너가 업로드 해". 요청한 이 프로젝트의 코드 변경에 필요한 Arduino 업로드는 매번 재승인을 묻지 않고 진행할 수 있다. 검사/컴파일, 프로그램 중지/포트 소유 확인, 업로드 검증과 PING 확인, 결과 보고를 유지한다. 요청하지 않은 실물 동작/전시 재시작/자동 실행 전환과 PWM 펄스 폭 변경까지 위임된 것은 아니다. `AGENTS.md`와 최신 현재 상태를 우선한다.

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
5. 컴파일과 관련 검사가 성공하면 사용자 요청에 필요한 업로드를 최신 위임 범위에서 진행할 수 있다. 빌드 전용 스크립트 자체는 여전히 컴파일만 수행한다.

`build_arduino_remote.sh`는 원격 빌드 경로 `/home/hyunwoo/capstone-robot-build/servo_controller`만 사용한다. Raspberry Pi 실행 코드 경로 `/home/hyunwoo/robot_demo`를 수정하지 않는다.

## 3. Arduino 업로드가 필요한 경우

Arduino Mega 실제 업로드는 보드 리셋/출력 변화 위험이 있다. 최신 사용자 위임 범위에서는 재승인을 묻지 않되 필요한 검사와 프로그램 중지/포트 확인을 생략하지 않는다. 업로드는 `--verify`로 검증하고 실패 시 추가 동작을 하지 않는다.

업로드 스크립트:

```bash
scripts/flash_arduino_remote.sh
```

아래 스크립트에는 기존 수동 승인 입력이 아직 남아 있다. 그 입력은 수동 실행 보호 장치이며 Codex가 사용자에게 재승인을 요구해야 한다는 최신 규칙은 아니다. Codex는 프로그램/포트/소스와 컴파일 결과를 직접 확인한 뒤 검증된 CLI 업로드 절차를 사용할 수 있다. 승인 입력을 우회하려고 확인/중지 절차까지 생략하지 않는다.

기존 수동 스크립트 동작:

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
