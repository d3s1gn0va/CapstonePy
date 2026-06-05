# Initial Import Report

## Import 상태

Raspberry Pi import는 시도했지만 완료되지 않았다.

* 실행한 스크립트: `scripts/import_from_pi.sh`
* 결과: 실패
* 오류: `ssh: connect to host 192.168.0.39 port 22: No route to host`
* 영향: Raspberry Pi의 기존 `~/robot_demo/` 원본 코드는 Mac 프로젝트로 복사되지 않았다.
* 안전 확인: Raspberry Pi 원본 폴더를 수정하거나 삭제하지 않았고, 배포와 재시작도 실행하지 않았다.

Arduino 코드는 Mac 원본에서 프로젝트로 복사했다.

* 원본: `/Users/hyunwoo/Documents/Arduino/servo_controller/servo_controller.ino`
* 복사본: `arduino/servo_controller/servo_controller.ino`
* 비교 결과: 원본과 복사본이 동일하다.

## Raspberry Pi Python 파일 목록

현재 아래 파일들이 존재하지만, Raspberry Pi import 실패로 인해 모두 0줄짜리 자리표시자 파일이다.

* `raspberry_pi/robot_demo/audio_player.py`
* `raspberry_pi/robot_demo/calibrate_servos.py`
* `raspberry_pi/robot_demo/config.py`
* `raspberry_pi/robot_demo/main.py`
* `raspberry_pi/robot_demo/serial_controller.py`
* `raspberry_pi/robot_demo/test_audio.py`
* `raspberry_pi/robot_demo/test_button.py`
* `raspberry_pi/robot_demo/test_sequence_no_button.py`
* `raspberry_pi/robot_demo/test_serial.py`

## WAV 파일 목록

현재 `raspberry_pi/robot_demo/` 아래에서 확인된 WAV 파일은 없다.

Raspberry Pi import가 성공하면 시연에 필요한 WAV 파일은 임의로 삭제하지 않는다.

## `audio_player.py` 점검

`audio_player.py`가 현재 빈 파일이므로 `pw-play` 우선 사용 여부를 확인할 수 없다.

Raspberry Pi에서 실제 파일을 가져온 뒤 `pw-play`를 우선 사용하고, `aplay`에 의존하지 않는지 다시 점검해야 한다.

## `config.py` 점검

`config.py`가 현재 빈 파일이므로 목표 각도, 안전 범위, 이동 시간 설정값을 확인할 수 없다.

## Arduino 안전 설정값

`arduino/servo_controller/servo_controller.ino`에서 확인한 값은 다음과 같다.

* `SERVO_FREQUENCY_HZ = 50.0`
* `SERVO_MIN_PULSE_US = 1000`
* `SERVO_MAX_PULSE_US = 2000`
* `HEAD_SAFE_MIN_DEG = 0`
* `HEAD_SAFE_MAX_DEG = 180`
* `ARM_SAFE_MIN_DEG = 60`
* `ARM_SAFE_MAX_DEG = 120`
* `CENTER_DEG = 90`
* `UPDATE_INTERVAL_MS = 20`
* `SERIAL_BAUDRATE = 115200`

## Raspberry Pi 설정과 Arduino 설정 불일치 여부

Raspberry Pi의 `config.py`가 비어 있어 Arduino 설정과 비교할 수 없다.

Raspberry Pi import가 성공한 뒤 Python 쪽 목표 각도와 Arduino 쪽 안전 범위가 일치하는지 다시 확인해야 한다.

## `servo_controller.ino` 존재 여부

`arduino/servo_controller/servo_controller.ino`가 존재한다.

## 비밀정보와 로그 파일 점검

프로젝트 안에서 다음 항목은 발견되지 않았다.

* SSH 개인키 파일
* `.env` 파일
* `*.log` 파일
* 명백한 private key 본문
* 명백한 비밀번호, 토큰, secret 값

문서와 스크립트에는 `.env`를 제외하거나 Git에 포함하지 말라는 설명만 포함되어 있다.
