# 10 Decision Log

## 확인된 결정

### Mac 저장소를 기준으로 개발한다

Mac 프로젝트가 기준 저장소이며 Raspberry Pi의 `/home/hyunwoo/robot_demo`는 실행본으로 다룬다.

### Raspberry Pi가 시연 타임라인을 담당한다

`main.py`가 버튼 입력, Serial 명령, 오디오 재생, 시퀀스 흐름을 관리한다.

### Arduino Mega가 서보 제어를 담당한다

`servo_controller.ino`가 Serial 명령을 받아 PCA9685로 고개/오른팔/카메라 서보를 제어한다.

## 2026-06-07 로컬 작업 결정

카메라 좌우 회전 서보는 PCA9685 Channel 2로 추가한다.

Raspberry Pi 버튼은 내부 풀업 입력을 사용하며, 버튼은 GPIO와 GND 사이에 연결한다.

버튼 역할은 GPIO17 기존 전시 시퀀스, GPIO27 Raspberry Pi 안전 종료, GPIO22 카메라 좌우 움직임으로 둔다.

카메라 서보의 현재 안전 범위는 30..150도이고, 카메라 버튼 시퀀스는 30도, 150도, 90도 순서로 이동한다.

팔 서보의 현재 상승 목표는 180도이고, 전시 시퀀스에서 고개 70도 이동과 동시에 시작한다. 고개와 팔의 이동 시간은 모두 1200ms로 맞춘다.

### 오디오는 `pw-play`를 우선 사용한다

`audio_player.py`는 `pw-play`를 먼저 찾고, 없을 때만 `aplay`를 사용한다.

### 버튼 GPIO는 BCM 17이다

`config.py`에서 `BUTTON_GPIO = 17`로 설정되어 있다.

### USB Serial 속도는 115200이다

Raspberry Pi와 Arduino 모두 `115200`을 사용한다.

### PCA9685 채널 배정

Arduino 코드 주석과 상수 기준:

* Channel 0: 고개 SG92R
* Channel 1: 로봇 기준 오른팔 MG996R

### Arduino 업로드는 명시적 승인 후에만 한다

`AGENTS.md`, `README.md`, 스크립트 주석 기준으로 Arduino Mega 실제 업로드는 사용자가 `Arduino 업로드 승인`이라고 명시한 경우에만 진행한다.

### 고개 전체 범위 테스트는 전시 기능이 아니다

고개 0도에서 180도 이동은 개발 시험 항목이며 최종 전시 동작으로 확정하지 않는다.

## 확인 필요 결정

아래는 아직 결정으로 기록하지 않는다.

* 최종 자동 실행 방식
* 최종 제품 외형
* 최종 배선 핀맵
* WAV 파일 공개 저장소 포함 여부
