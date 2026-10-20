# 12 Button And Servo Wiring

이 문서는 현재 코드 기준으로 버튼 3개와 서보 3개를 연결하는 방법을 정리한다. Raspberry Pi GPIO 번호는 BCM 번호와 물리 핀 번호를 함께 적는다.

## 전체 역할

* 전시 시퀀스 버튼: 기존 시연 흐름 실행
* 전원 OFF 버튼: Raspberry Pi 안전 종료 요청
* 카메라 버튼: 고개와 팔은 그대로 두고 카메라 서보만 천천히 좌우 이동
* 카메라 LED: 카메라 서보가 움직이는 동안 켜짐
* 고개 서보: PCA9685 Channel 0
* 오른팔 서보: PCA9685 Channel 1
* 카메라 서보: PCA9685 Channel 2

## Raspberry Pi 버튼 연결

Python 코드는 내부 풀업 입력을 사용한다.

```python
Button(..., pull_up=True)
```

따라서 버튼은 GPIO와 GND 사이에 연결한다. 버튼을 3.3V나 5V에 연결하지 않는다.

| 버튼 | BCM GPIO | Raspberry Pi 물리 핀 | 반대쪽 |
| --- | ---: | ---: | --- |
| 전시 시퀀스 | GPIO17 | 11번 | GND |
| 전원 OFF | GPIO27 | 13번 | GND |
| 카메라 움직임 | GPIO22 | 15번 | GND |

GND는 Raspberry Pi 물리 6번, 9번, 14번, 20번, 25번, 30번, 34번, 39번 중 하나를 사용할 수 있다.

## 카메라 LED 연결

카메라 LED는 GPIO23을 사용한다. GPIO23은 Raspberry Pi 물리 핀 16번이다.

LED는 반드시 저항을 직렬로 넣어서 연결한다. 3V 규격 LED라도 Raspberry Pi GPIO에 저항 없이 직접 연결하면 LED나 Raspberry Pi GPIO가 손상될 수 있다.

권장 연결:

```text
Raspberry Pi GPIO23, 물리 핀 16번
  -> 220Ω 또는 330Ω 저항
  -> LED 긴 다리, +
  -> LED 짧은 다리, -
  -> Raspberry Pi GND
```

LED가 켜지지 않으면 LED 방향을 반대로 꽂았을 가능성이 있다. 전원을 끄고 LED 긴 다리와 짧은 다리 방향을 다시 확인한다.

## 브레드보드와 푸쉬스위치 연결

1. Raspberry Pi GND 핀 하나를 브레드보드의 `-` 레일에 연결한다.
2. 푸쉬스위치를 브레드보드 중앙 홈을 가로질러 꽂는다.
3. 스위치 한쪽 다리를 브레드보드 `-` 레일에 점퍼선으로 연결한다.
4. 스위치 반대쪽 다리를 Raspberry Pi GPIO 핀에 연결한다.
5. 같은 방식으로 버튼 3개를 각각 GPIO17, GPIO27, GPIO22에 연결한다.

택트 스위치는 같은 방향의 두 다리가 내부적으로 연결되어 있다. 버튼이 계속 눌린 것처럼 보이거나 전혀 반응하지 않으면 스위치 방향을 90도 돌려 중앙 홈을 가로지르게 꽂는다.

## PCA9685 서보 연결

서보 3개는 PCA9685의 0, 1, 2번 채널에 꽂는다.

| PCA9685 채널 | 역할 | 코드 상수 |
| ---: | --- | --- |
| Channel 0 | 고개 서보 | `HEAD_CHANNEL` |
| Channel 1 | 오른팔 서보 | `ARM_CHANNEL` |
| Channel 2 | 카메라 좌우 서보 | `CAMERA_CHANNEL` |

서보 커넥터 방향:

* 갈색 또는 검정색: `GND`
* 빨간색: `V+`
* 주황색, 노란색 또는 흰색: `PWM`, `S`, Signal

보드에 적힌 `GND`, `V+`, `PWM/S` 표기를 우선해서 맞춘다. 반대로 꽂으면 서보가 움직이지 않거나 과열될 수 있으므로 전원을 넣기 전에 색상 방향을 다시 확인한다.

## Arduino Mega와 PCA9685 연결

일반적인 Arduino Mega 2560 I2C 연결은 아래와 같다.

| Arduino Mega | PCA9685 |
| --- | --- |
| 20 SDA | SDA |
| 21 SCL | SCL |
| 5V | VCC |
| GND | GND |

Arduino Mega는 Raspberry Pi와 USB 케이블로 연결한다. Raspberry Pi Python 프로그램이 USB Serial로 Arduino에 명령을 보낸다.

## 서보 전원

서보 전원은 Raspberry Pi나 Arduino 5V에서 직접 공급하지 않는다.

* 외부 5V 전원 `+` -> PCA9685 `V+`
* 외부 5V 전원 `-` -> PCA9685 `GND`
* Raspberry Pi GND, Arduino GND, PCA9685 GND, 외부 전원 GND를 공통 연결

서보가 3개로 늘었기 때문에 전류 용량이 부족하면 서보 떨림, Raspberry Pi 재부팅, Arduino USB 끊김이 생길 수 있다.

## 전원 OFF 버튼 주의

전원 OFF 버튼은 `sudo shutdown -h now`를 실행한다. Raspberry Pi에서 아래 설정을 한 번 해 두어야 버튼으로 안전 종료가 가능하다.

```bash
bash scripts/setup_pi_shutdown_permission.sh
```

이 스크립트는 Raspberry Pi에 `hyunwoo` 사용자가 `/usr/sbin/shutdown -h now`만 비밀번호 없이 실행할 수 있는 sudoers 규칙을 설치한다. 실제 설치에는 Raspberry Pi sudo 비밀번호가 필요할 수 있다.

## 안전 확인

* 서보 혼을 분리한 상태에서 처음 각도 테스트를 한다.
* 카메라 서보는 현재 `30`도에서 `150`도 사이만 허용한다.
* 고개와 팔의 기존 기구물에 카메라 서보 또는 케이블이 걸리지 않는지 확인한다.
* Arduino Mega 실제 업로드는 사용자가 `Arduino 업로드 승인`이라고 명시한 뒤에만 진행한다.
