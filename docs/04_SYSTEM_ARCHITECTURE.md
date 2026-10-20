# 04 System Architecture

## 최신 통합 개발 단계

2026-10-05 Mac에 별도 `integrated_demo.py`와 타임라인/하드웨어 어댑터/안전 프로필을 추가했다. 승인된 눈과 두 WAV, 6축을 단일 소유로 관리하며 Arduino 그룹 명령과 완료 응답을 사용한다. **실제 Pi는 기존 프로그램, Mega는 기존 펌웨어다.** 새 팔의 안전/초기/몸짓 각도와 전원 확인이 빠져 실물 실행은 잠겨 있다. 앱/카메라 인식은 이번 구현에서 제외한다. [통합 구현](19_ROBOT_INTEGRATION.md)을 따른다.

## 역할 분리

Raspberry Pi:

* 버튼 입력 처리
* WAV 음성 재생
* 시연 타임라인 관리
* Arduino와 USB Serial 통신
* 목표 각도와 동작 시간 설정 관리

Arduino Mega:

* USB Serial 텍스트 명령 수신
* 명령 검증과 안전 범위 검사
* PCA9685 제어
* 고개/오른팔/카메라 서보의 부드러운 이동 처리

PCA9685:

* Arduino 명령에 따라 PWM 서보 신호 출력
* I2C 주소: `0x40`
* 주파수: `50.0 Hz`

## 통신

Raspberry Pi Python 코드와 Arduino 펌웨어는 USB Serial 텍스트 명령으로 통신한다.

Serial 속도:

* Raspberry Pi `config.py`: `SERIAL_BAUDRATE = 115200`
* Arduino `servo_controller.ino`: `SERIAL_BAUDRATE = 115200`

Raspberry Pi는 Serial 포트를 다음 순서로 탐색한다.

1. `config.SERIAL_PORT` 직접 지정값
2. `/dev/serial/by-id/*`
3. `/dev/ttyACM*`
4. `/dev/ttyUSB*`

## Arduino Serial 명령

지원 명령:

* `PING`
* `STATUS`
* `HELP`
* `CENTER,<duration_ms>`
* `MOVE_HEAD,<angle_deg>,<duration_ms>`
* `MOVE_ARM,<angle_deg>,<duration_ms>`
* `MOVE_BOTH,<head_angle_deg>,<arm_angle_deg>,<duration_ms>`
* `STOP`
* `DISABLE`

주요 응답:

* `ACK,PING`
* `ACK,MOVE_HEAD`
* `DONE,MOVE_HEAD`
* `ACK,MOVE_ARM`
* `DONE,MOVE_ARM`
* `ACK,MOVE_BOTH`
* `DONE,MOVE_BOTH`
* `ACK,CENTER`
* `DONE,CENTER`

## 소프트웨어 레이어

* `raspberry_pi/robot_demo/main.py`: 전시 시연 메인 프로그램
* `raspberry_pi/robot_demo/config.py`: 목표 각도, 안전 범위, 시간, 오디오 파일 경로, Serial 설정
* `raspberry_pi/robot_demo/serial_controller.py`: Arduino Serial 연결과 명령 전송
* `raspberry_pi/robot_demo/audio_player.py`: WAV 재생, `pw-play` 우선 사용
* `arduino/servo_controller/servo_controller.ino`: PCA9685와 서보 제어 펌웨어

## 위험 작업

아래는 자동 실행하면 안 된다.

* Arduino Mega 실제 업로드
* 서보 PWM 펄스 폭 변경
* 서보 안전 범위 확대
* 고개 0도에서 180도 전체 범위 이동
* Raspberry Pi 프로그램 재시작 또는 자동 실행 활성화
