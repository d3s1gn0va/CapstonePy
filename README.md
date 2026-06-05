# Capstone Robot Project

Raspberry Pi 4, Arduino Mega 2560, PCA9685를 사용하는 캡스톤디자인 로봇 프로젝트의 Mac 기준 저장소입니다.

## 기준 경로

* Mac 프로젝트 루트: `/Users/hyunwoo/Documents/capstone design/capstone-robot-project`
* Raspberry Pi SSH 주소: `hyunwoo@192.168.0.39`
* SSH 개인키 경로: `~/.ssh/robotpi_ed25519`
* Raspberry Pi 실행 코드 경로: `/home/hyunwoo/robot_demo`
* Arduino 원격 빌드 임시 경로: `/home/hyunwoo/capstone-robot-build/servo_controller`
* Arduino Mega FQBN: `arduino:avr:mega`

이 Mac 프로젝트가 원본 저장소입니다. Raspberry Pi의 `/home/hyunwoo/robot_demo`는 실제 실행본이며, 배포 스크립트를 통해 이 저장소의 Raspberry Pi 코드를 복사해 실행 환경에 반영합니다.

WAV 파일은 현재 시연에 필요하므로 `raspberry_pi/robot_demo/audio/` 아래에 포함합니다. 로그, `.env`, SSH 키, 토큰, 비밀번호, macOS 메타데이터 파일은 Git에 포함하지 않습니다.

오디오는 Raspberry Pi OS의 현재 출력 설정을 따르도록 `pw-play`를 우선 사용합니다. `audio_player.py`는 `pw-play`가 없을 때만 `aplay`로 fallback합니다.

## Python 설정 수정 흐름

1. `raspberry_pi/robot_demo/config.py`에서 목표 각도, 이동 시간, 시리얼 설정을 수정합니다.
2. `scripts/check_python.sh`로 Python 문법 검사를 실행합니다.
3. 문제가 없으면 `scripts/deploy_pi.sh`로 Raspberry Pi에 배포합니다.
4. 필요할 때 `scripts/restart_robot.sh`로 실행 프로그램을 재시작합니다.
5. `scripts/status_robot.sh`와 `scripts/logs_robot.sh`로 상태와 로그를 확인합니다.

`deploy_pi.sh`는 `check_python.sh`를 먼저 실행하고, `.env`, 로그, `__pycache__`, `.DS_Store`, `._*` 파일을 제외한 뒤 `/home/hyunwoo/robot_demo/`로 rsync합니다. Arduino 업로드는 하지 않습니다.

## Arduino 펌웨어 수정 흐름

1. `arduino/servo_controller/servo_controller.ino`를 수정합니다.
2. 안전 범위 확장, 펄스 폭 변경, 큰 각도 테스트는 먼저 충돌과 과부하 위험을 검토합니다.
3. `scripts/build_arduino_remote.sh`로 Raspberry Pi에 Arduino 코드를 복사하고 컴파일까지만 확인합니다.
4. 실제 Arduino Mega 업로드는 사용자가 별도로 `Arduino 업로드 승인`이라고 명확히 말한 경우에만 진행합니다.
5. 업로드 스크립트는 `scripts/flash_arduino_remote.sh`입니다. 실행 시에도 정확한 승인 문구를 다시 입력해야 합니다.

Arduino USB 포트는 고정하지 않고 `/dev/serial/by-id/*`, `/dev/ttyACM*`, `/dev/ttyUSB*` 순서로 탐색합니다.

## 주요 스크립트

* `scripts/import_from_pi.sh`: Raspberry Pi의 기존 `~/robot_demo/`를 Mac 프로젝트로 가져옵니다.
* `scripts/check_python.sh`: Raspberry Pi Python 코드 문법을 검사합니다. macOS AppleDouble `._*` 파일은 건너뜁니다.
* `scripts/deploy_pi.sh`: Python 코드와 오디오 파일을 Raspberry Pi 실행 폴더로 배포합니다.
* `scripts/restart_robot.sh`: Raspberry Pi 로봇 실행 프로그램을 재시작합니다.
* `scripts/stop_robot.sh`: Raspberry Pi 로봇 실행 프로그램만 중지합니다.
* `scripts/status_robot.sh`: 실행 상태, `pw-play` 존재 여부, Arduino USB Serial 후보, 최근 로그를 확인합니다.
* `scripts/logs_robot.sh`: Raspberry Pi 로봇 로그를 실시간으로 확인합니다.
* `scripts/setup_pi_runtime.sh`: Raspberry Pi 런타임 패키지 설치 명령을 실행합니다.
* `scripts/setup_pi_autostart.sh`: Desktop Autologin 이후 사용자 자동 실행 구성을 준비합니다.
* `scripts/build_arduino_remote.sh`: Arduino 코드를 `/home/hyunwoo/capstone-robot-build/servo_controller`로 복사하고 `arduino:avr:mega` 대상으로 컴파일합니다. 업로드는 하지 않습니다.
* `scripts/flash_arduino_remote.sh`: 위험 경고와 승인 문구 확인 후 Arduino Mega에 업로드합니다. 업로드 전 로봇 프로그램을 중지하고, 업로드 후 `PING` 응답 `ACK,PING`을 확인한 뒤 재시작 절차를 안내합니다.

## 폴더 구성

* `AGENTS.md`: 작업 시 지켜야 할 Raspberry Pi, Arduino, 서보 안전 규칙.
* `README.md`: 프로젝트 구조와 파일 역할 설명.
* `.gitignore`: Git에 포함하지 않을 로컬 설정, 캐시, 로그, 비밀 파일 목록.
* `raspberry_pi/robot_demo/`: Raspberry Pi에서 실행되는 Python 코드와 WAV 오디오 파일.
* `arduino/servo_controller/servo_controller.ino`: Arduino Mega 2560에서 PCA9685를 제어하는 서보 컨트롤러 펌웨어.
* `scripts/`: 가져오기, 검사, 배포, 상태 확인, Arduino 빌드/업로드 스크립트.
* `docs/`: 초기 import 점검, 배포 가이드, 하드웨어 안전 규칙 문서.
