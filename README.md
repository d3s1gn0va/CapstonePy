# Capstone Robot Project

Raspberry Pi 4, Arduino Mega 2560, PCA9685를 사용하는 캡스톤디자인 로봇 프로젝트의 Mac 기준 저장소입니다.

## 저장소 기준

이 Mac 프로젝트가 원본 저장소입니다. Raspberry Pi의 `/home/hyunwoo/robot_demo`는 실제 실행본이며, 배포 스크립트를 통해 이 저장소의 Raspberry Pi 코드를 복사해 실행 환경에 반영합니다.

Raspberry Pi의 기존 `~/robot_demo` 폴더는 import할 때 읽기 전용 원본처럼 취급합니다. 이 저장소에서 작업한 뒤 검사를 통과한 내용만 배포합니다.

WAV 파일은 현재 시연에 필요하므로 `raspberry_pi/robot_demo/` 아래에 가져온 오디오 파일은 임의로 삭제하지 않습니다. 다만 로그, `.env`, SSH 키, 토큰, 비밀번호는 Git에 포함하지 않습니다.

## Python 설정 수정 흐름

1. `raspberry_pi/robot_demo/config.py`에서 각도, 이동 시간, 포트 등 설정을 수정합니다.
2. `scripts/check_python.sh`로 Python 문법 검사를 실행합니다.
3. 문제가 없으면 `scripts/deploy_pi.sh`로 Raspberry Pi에 배포합니다.
4. 필요할 때 `scripts/restart_robot.sh`로 실행 프로그램을 재시작합니다.
5. `scripts/status_robot.sh`와 `scripts/logs_robot.sh`로 상태와 로그를 확인합니다.

## Arduino 펌웨어 수정 흐름

1. `arduino/servo_controller/servo_controller.ino`를 수정합니다.
2. 안전 범위 확장, 펄스 폭 변경, 큰 각도 테스트는 먼저 충돌과 과부하 위험을 검토합니다.
3. `scripts/build_arduino_remote.sh`로 컴파일까지만 확인합니다.
4. 실제 Arduino Mega 업로드는 사용자가 `Arduino 업로드 승인`이라고 명확히 말한 경우에만 진행합니다.
5. 업로드 스크립트는 `scripts/flash_arduino_remote.sh`이지만, 이 작업은 항상 별도 승인이 필요합니다.

## 주요 스크립트

* `scripts/import_from_pi.sh`: Raspberry Pi의 기존 `~/robot_demo/`를 Mac 프로젝트로 가져옵니다.
* `scripts/check_python.sh`: Raspberry Pi Python 코드 문법을 검사합니다.
* `scripts/deploy_pi.sh`: Python 코드를 Raspberry Pi 실행 폴더로 배포합니다.
* `scripts/restart_robot.sh`: Raspberry Pi 로봇 실행 프로그램을 재시작합니다.
* `scripts/stop_robot.sh`: Raspberry Pi 로봇 실행 프로그램만 중지합니다.
* `scripts/status_robot.sh`: 실행 상태, Arduino USB Serial 후보, 최근 로그를 확인합니다.
* `scripts/logs_robot.sh`: Raspberry Pi 로봇 로그를 실시간으로 확인합니다.
* `scripts/setup_pi_runtime.sh`: Raspberry Pi 런타임 패키지 설치 명령을 실행합니다.
* `scripts/setup_pi_autostart.sh`: Desktop Autologin 이후 사용자 자동 실행 구성을 준비합니다.
* `scripts/build_arduino_remote.sh`: Raspberry Pi에서 Arduino CLI로 펌웨어를 컴파일합니다.
* `scripts/flash_arduino_remote.sh`: Arduino Mega에 펌웨어를 업로드합니다. 반드시 명시적 승인 후에만 실행합니다.

## 폴더 구성

* `AGENTS.md`: 작업 시 지켜야 할 Raspberry Pi, Arduino, 서보 안전 규칙.
* `README.md`: 프로젝트 구조와 파일 역할 설명.
* `.gitignore`: Git에 포함하지 않을 로컬 설정, 캐시, 로그 파일 목록.
* `raspberry_pi/robot_demo/`: Raspberry Pi에서 실행되는 Python 코드와 WAV 오디오 파일.
* `arduino/servo_controller/servo_controller.ino`: Arduino Mega 2560에서 PCA9685를 제어하는 서보 컨트롤러 펌웨어.
* `scripts/`: 가져오기, 검사, 배포, 상태 확인, Arduino 빌드/업로드 스크립트.
* `docs/`: 초기 import 점검, 배포 가이드, 하드웨어 안전 규칙 문서.
