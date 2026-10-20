# 07 Remote Development

## 개발 구조

Mac 저장소를 기준으로 코드를 수정하고, 필요한 경우 Raspberry Pi 실행 폴더로 배포한다.

2026-10-05 사용자가 요청한 코드 변경에 필요한 Arduino 업로드를 앞으로 매번 재승인 없이 진행하도록 위임했다. 검사/컴파일/프로그램 중지/포트 확인/업로드 검증/PING과 결과 보고는 유지하며 실제 서보 시험/프로그램 재시작/자동 실행은 요청 범위에서 별도로 취급한다. 최신 규칙은 `AGENTS.md`와 `docs/09_CURRENT_STATE.md`를 따른다.

확인된 원격 실행 폴더:

```text
/home/hyunwoo/robot_demo
```

스크립트는 Raspberry Pi SSH 주소와 SSH 키 경로를 변수로 사용한다. SSH 키 파일 내용은 절대 저장소에 포함하지 않는다.

## 주요 스크립트

* `scripts/import_from_pi.sh`: Raspberry Pi 실행 폴더에서 Mac 프로젝트로 가져오기
* `scripts/check_python.sh`: Python 문법 검사
* `scripts/deploy_pi.sh`: Mac의 `raspberry_pi/robot_demo/`를 Raspberry Pi 실행 폴더로 rsync
* `scripts/status_robot.sh`: 프로세스, service, USB Serial 후보, `pw-play`, 최근 로그 확인
* `scripts/logs_robot.sh`: Raspberry Pi 로그 follow
* `scripts/restart_robot.sh`: 로봇 프로그램 재시작
* `scripts/stop_robot.sh`: 로봇 프로그램 중지
* `scripts/build_arduino_remote.sh`: Arduino 코드를 Raspberry Pi 빌드 폴더로 복사하고 컴파일
* `scripts/flash_arduino_remote.sh`: 위험 승인 후 Arduino Mega 업로드

## 배포 방식

`deploy_pi.sh`는 배포 전 `scripts/check_python.sh`를 실행한다. rsync 시 아래 항목을 제외한다.

* `.DS_Store`
* `._*`
* `.env`
* `.env.*`
* `*.log`
* `__pycache__/`
* `*.pyc`

`deploy_pi.sh`는 Arduino 업로드를 수행하지 않는다.

## Arduino 원격 빌드

Arduino 원격 빌드 경로:

```text
/home/hyunwoo/capstone-robot-build/servo_controller
```

FQBN:

```text
arduino:avr:mega
```

`build_arduino_remote.sh`는 컴파일까지만 수행한다.

현재 Raspberry Pi에서 확인된 `arduino-cli` 경로:

```text
/home/hyunwoo/.local/bin/arduino-cli
```

비대화형 SSH에서는 `~/.local/bin`이 PATH에 없을 수 있으므로 Arduino 빌드/업로드 스크립트는 이 절대 경로를 사용한다.

## GitHub 상태

기존 원격 저장소:

```text
https://github.com/d3s1gn0va/CapstonePy.git
```

이전 push 시도는 HTTPS 인증 문제로 실패한 기록이 있다. 인증 방식은 확인 필요다.

## 공개 저장소 주의

현재 WAV 파일 2개는 시연에 필요한 자산이며 Git 추적 대상이 될 수 있다. 공개 저장소에 포함해도 되는지 최종 확인이 필요하다.

Git에 포함하면 안 되는 것:

* SSH 키 파일 또는 키 내용
* 비밀번호
* 토큰
* `.env`
* `scripts/local.env`
* 로그 파일
* 로컬 캐시와 macOS 메타데이터
