# 05 Hardware Wiring

## 최신 구성과 계획

2026-10-05 사용자 설명 기준 서보는 모두 SG92R이며 고개 1개, 정수리 회전 1개, 양팔 어깨 X/Y 4개로 총 6개다. OLED 두 장, CSI 카메라, USB 전원/AUX 스피커를 포함한 최신 핀맵과 전원 계획은 [16_FULL_SYSTEM_WIRING_PLAN.md](16_FULL_SYSTEM_WIRING_PLAN.md)를 따른다.

실제 Pi에는 아래의 기존 3채널 프로그램이 남아 있으나 최신 서보 시험을 위해 중지했다. Mega에는 승인 후 6축 그룹/90도·0도 고정 시험 펌웨어를 업로드했고 마지막 CH0~CH5 0도 명령 완료/출력 유지 상태를 확인했다. Mac의 별도 통합 코드와 미확정 팔 그룹 실행은 아직 잠겨 있다. 실제 팔 자세/안전 확인과 배선 변경을 뜻하지 않는다. 과거 MG996R 모델 표기나 일반적인 서보 전원 설명을 최신 SG92R의 확정 사양으로 취급하지 않는다. 트리거의 최대 5A와 현재 어댑터의 5V 3A 출력도 구분한다.

## 현재 3채널 코드와 이전 하드웨어 기록

아래는 실제 Pi에 남아 있는 기존 구성의 기록이다. 사용자는 최신 6축 표대로 배선했다고 확인했다. 통합 전시 실행은 팔 초기·안전 각도가 미확정이라 잠겨 있다. 90도 시험 펌웨어 업로드와 실제 순차 시험의 최신 결과는 [통합 상태](19_ROBOT_INTEGRATION.md)를 따른다.

* Raspberry Pi 4
* Arduino Mega 2560
* PCA9685 PWM servo driver
* 고개 SG92R 서보
* 오른팔 서보 (과거 MG996R, 사용자 최신 지정은 SG92R)
* 카메라 좌우 회전 서보
* 전시 버튼
* 전원 OFF 버튼
* 카메라 움직임 버튼
* WAV 재생용 Raspberry Pi 오디오 출력 환경

## 확인된 연결 정보

Raspberry Pi:

* 전시 버튼 GPIO: BCM `17`, 물리 핀 11번
* 전원 OFF 버튼 GPIO: BCM `27`, 물리 핀 13번
* 카메라 움직임 버튼 GPIO: BCM `22`, 물리 핀 15번
* 카메라 LED GPIO: BCM `23`, 물리 핀 16번
* Arduino와 USB Serial 연결

Arduino / PCA9685:

* PCA9685 I2C 주소: `0x40`
* PCA9685 Channel 0: 고개 SG92R
* PCA9685 Channel 1: 로봇 기준 오른팔 기존 한 축
* PCA9685 Channel 2: 카메라 좌우 회전 서보
* PWM 주파수: `50.0 Hz`

Serial:

* Baudrate: `115200`

## Raspberry Pi 버튼 배선

현재 Python 코드는 `gpiozero.Button(..., pull_up=True)`를 사용한다. 따라서 각 버튼은 누르지 않았을 때 GPIO가 내부 풀업으로 HIGH이고, 버튼을 누르면 GND로 연결되어 LOW가 되는 방식이다.

외부 저항은 우선 필요하지 않다. 버튼을 3.3V나 5V에 연결하지 않는다.

### 사용할 Raspberry Pi 핀

Raspberry Pi 40핀 헤더에서 물리 핀 번호 기준으로 연결한다.

* 물리 11번, BCM GPIO17: 기존 전시 시퀀스 버튼
* 물리 13번, BCM GPIO27: Raspberry Pi 안전 종료 버튼
* 물리 15번, BCM GPIO22: 카메라 좌우 움직임 버튼
* 물리 6번, 9번, 14번, 20번, 25번, 30번, 34번, 39번 중 하나: GND

### 브레드보드에 버튼 꽂는 방법

택트 스위치는 다리 4개가 있는 작은 푸쉬스위치 기준이다.

1. 스위치가 브레드보드 중앙 홈을 가로지르도록 꽂는다.
2. Raspberry Pi의 GND 핀 하나를 브레드보드의 파란색 또는 `-` 레일에 연결한다.
3. 각 스위치의 한쪽 다리를 브레드보드 GND 레일에 연결한다.
4. 각 스위치의 반대쪽 다리를 해당 GPIO 핀에 연결한다.
5. 스위치를 누르면 GPIO 핀과 GND가 연결된다.

버튼별 연결은 아래처럼 한다.

* 전시 시퀀스 버튼: GPIO17 물리 11번 -> 스위치 한쪽, 스위치 반대쪽 -> GND 레일
* 전원 OFF 버튼: GPIO27 물리 13번 -> 스위치 한쪽, 스위치 반대쪽 -> GND 레일
* 카메라 버튼: GPIO22 물리 15번 -> 스위치 한쪽, 스위치 반대쪽 -> GND 레일

택트 스위치는 같은 방향의 두 다리가 내부에서 이미 연결되어 있는 경우가 많다. 스위치를 눌러도 반응이 없으면 스위치를 90도 돌려서 브레드보드 중앙 홈을 가로지르게 다시 꽂는다.

전원 OFF 버튼은 Raspberry Pi OS에서 `hyunwoo` 사용자가 `sudo shutdown -h now`를 비밀번호 없이 실행할 수 있어야 동작한다. 이 권한은 `scripts/setup_pi_shutdown_permission.sh`로 한 번만 설정한다.

## PCA9685와 서보 배선

기존 고개와 오른팔 서보 배선은 유지한다. 새 카메라 서보만 PCA9685의 Channel 2에 추가한다.

PCA9685 서보 단자 한 줄은 보통 `GND`, `V+`, `PWM/S` 순서로 구성된다. 보드 인쇄가 다르면 보드에 적힌 글자를 우선한다.

* 서보 갈색 또는 검정색 선: `GND`
* 서보 빨간색 선: `V+`
* 서보 주황색, 노란색 또는 흰색 선: `PWM` 또는 `S`

채널 연결:

* PCA9685 Channel 0: 고개 서보
* PCA9685 Channel 1: 오른팔 서보
* PCA9685 Channel 2: 카메라 좌우 회전 서보

일부 PCA9685 보드는 서보 단자를 사람이 보기 쉽게 `1`, `2`, `3`처럼 표시할 수 있다. 코드의 Channel 2는 0부터 세는 세 번째 채널이다. 즉 보드가 1부터 표시되어 있다면 세 번째 서보 자리일 가능성이 높다.

## Arduino Mega와 PCA9685

현재 코드는 Arduino Mega의 I2C로 PCA9685를 제어한다. 일반적인 Arduino Mega I2C 핀은 아래와 같다.

* Arduino Mega 20번 핀 SDA -> PCA9685 `SDA`
* Arduino Mega 21번 핀 SCL -> PCA9685 `SCL`
* Arduino Mega 5V -> PCA9685 `VCC`
* Arduino Mega GND -> PCA9685 `GND`

Raspberry Pi와 Arduino Mega는 USB 케이블로 연결한다. Python 코드는 USB Serial을 통해 Arduino에 명령을 보낸다.

## 전원 및 접지 원칙

기존 안전 문서에서 확인되는 원칙:

* MG996R 같은 고토크 서보는 Raspberry Pi나 Arduino 5V 핀에서 직접 전원을 공급하지 않는다.
* 서보에는 충분한 전류를 낼 수 있는 외부 5V 전원을 사용한다.
* Raspberry Pi, Arduino Mega, PCA9685, 서보 외부 전원은 GND를 공통으로 연결한다.
* PCA9685 `VCC`는 로직 전원, `V+`는 서보 전원 입력이다.
* 서보 전원은 5V 기준을 유지한다.
* 서보 전원 공급 장치의 `+`는 PCA9685 `V+`에, `-`는 PCA9685 `GND`에 연결한다.
* Raspberry Pi GND, Arduino GND, PCA9685 GND, 외부 서보 전원 GND는 공통으로 묶는다.

서보가 3개가 되었으므로 외부 5V 전원 공급 장치의 전류 용량이 충분한지 확인해야 한다. 전류가 부족하면 Raspberry Pi 재부팅, Arduino 연결 끊김, 서보 떨림이 발생할 수 있다.

## 미확정 배선 정보

저장소만으로는 아래를 확정할 수 없다.

* Raspberry Pi와 Arduino의 실제 USB 포트 위치
* PCA9685 VCC 전압
* 서보 외부 전원 용량
* 전원 스위치, 퓨즈, 분배 보드 구성
* 새 카메라 서보 모델명과 실제 기구물 회전 가능 범위

## 자료 위치

배선 사진, 회로도, 전원 구성 자료는 `docs/assets/wiring/`에 추가한다.

## OLED 두 눈 추가 (2026-09-29)

1번 제품 SH1107 128x128 두 장은 Pi의 SPI0를 공유하며 CS/DC/RST를 각각 분리한다.
Pi 물리 핀 번호와 치수 정렬 가정은 [두 눈 시험 배선표](14_DUAL_OLED_EYES.md#두-패널-배선)를 따른다.
PCA9685와 Arduino 서보 배선은 변경하지 않는다. 기존 LED는 사용자 확인상 물리 16번 GPIO23과 14번 GND를 사용한다.

2026-10-05 CE1 변경 기준: DC 물리 7번(BCM4), RST 물리 12번(BCM18), GND 물리 9번. 기존 36/37/30번에서 이 세 선만 옮긴다. Mac 코드와 문서만 변경했으며 Pi 배포와 실물 재배선/시험 완료는 확인되지 않았다. Pi와 서보 전원을 분리한 상태에서 재배선하고, Pi의 OLED 시험 코드도 새 DC/RST 설정으로 반영한 뒤 실행한다.
