# 06 Software Behavior

## 새 통합 실행부 (2026-10-05, 미배포)

`integrated_demo.py`는 눈/음성/6축을 하나의 타임라인으로 관리하는 별도 실행부다. 기본은 가상 실행이며 `--hardware`는 초기/안전/몸짓 각도, 전원 확인, 펌웨어 설정 일치와 Serial 소유 확인을 통과해야 한다. 현재 팔 값이 미확정이라 실물 실행은 거부된다. `main.py` 기본 동작은 아래의 기존 방식으로 남아 있으나 실제 Pi 프로세스는 최신 90도 시험을 위해 중지했다. 버튼은 비활성이며 자동 실행 등록은 남아 있다.

Arduino 소스에는 `CAPS`, `MOVE_GROUP,<duration_ms>,<channel>,<angle>...`, `ACK,MOVE_GROUP`, `DONE,MOVE_GROUP`을 추가했다. 팔 4축은 그룹 명령에서 미설정으로 잠겨 있다. 기존 3축 명령/STATUS 형식은 유지하며 STOP/DISABLE은 6축에 적용된다. 이후 90도 고정 시험 명령과 6축 상태 조회를 추가하고 사용자 승인 후 실제 Mega 업로드/검증을 완료했다. 독립 시험에서 CH0~CH5 각각 90도 ACK/DONE과 마지막 상태를 확인했으며 초기 자세 프로필을 바꾸지는 않았다. [통합 동작과 검사](19_ROBOT_INTEGRATION.md)를 따른다.

## Raspberry Pi 프로그램

`main.py`의 기본 실행은 버튼 3개를 기다리는 전시용 프로그램이다.

실행:

```bash
python3 main.py
```

현재 버튼 역할:

* `BUTTON_GPIO`: 기존 전시 시퀀스 실행
* `POWER_OFF_BUTTON_GPIO`: Raspberry Pi 안전 종료 요청. 메인 루프 대기와 별개로 버튼 눌림 이벤트를 받는다.
* `CAMERA_BUTTON_GPIO`: 카메라 서보만 천천히 좌우 이동 후 중앙 복귀

고개 0도에서 70도 이동과 팔 90도에서 180도 이동은 현재 전시 시퀀스에서 동시에 시작된다. 단, 기구물 간섭 여부는 실제 조립 상태에서 계속 확인해야 한다.

## 설정값

`config.py` 기준:

```text
BUTTON_GPIO = 17
POWER_OFF_BUTTON_GPIO = 27
CAMERA_BUTTON_GPIO = 22
SERIAL_PORT = None
SERIAL_BAUDRATE = 115200
ARDUINO_RESET_WAIT_SEC = 2.5
SERIAL_ACK_TIMEOUT_SEC = 1.5
SERIAL_DONE_MARGIN_SEC = 2.0
LOG_SERIAL_LINES = True
```

서보 목표 각도:

```text
HEAD_NEUTRAL_DEG = 0
HEAD_LEFT_DEG = 70
ARM_DOWN_DEG = 90
ARM_UP_DEG = 180
CAMERA_CENTER_DEG = 90
CAMERA_LEFT_DEG = 30
CAMERA_RIGHT_DEG = 150
```

Raspberry Pi 안전 범위:

```text
HEAD_SAFE_MIN_DEG = 0
HEAD_SAFE_MAX_DEG = 180
ARM_SAFE_MIN_DEG = 70
ARM_SAFE_MAX_DEG = 180
CAMERA_SAFE_MIN_DEG = 30
CAMERA_SAFE_MAX_DEG = 150
```

동작 시간:

```text
HEAD_TURN_DURATION_MS = 1200
ARM_RAISE_DURATION_MS = 1200
RETURN_DURATION_MS = 1800
STARTUP_HOME_DURATION_MS = 1800
CAMERA_SWEEP_DURATION_MS = 2000
CAMERA_RETURN_DURATION_MS = 1500
AFTER_HEAD_TURN_PAUSE_SEC = 0.15
BETWEEN_AUDIO_PAUSE_SEC = 0.25
AFTER_AUDIO_HOLD_SEC = 0.50
```

오디오:

```text
AUDIO_NAME_CALL = audio/01_name_call.wav
AUDIO_LETS_PLAY = audio/02_lets_play.wav
APLAY_DEVICE = None
```

## 오디오 재생

`audio_player.py`는 `shutil.which("pw-play")`를 먼저 확인한다. `pw-play`가 있으면 `pw-play <wav path>`를 실행한다. `pw-play`가 없을 때만 `aplay -q`를 사용한다.

## Arduino 펌웨어

Arduino 설정:

```text
PCA9685_BOARD_ADDRESS = 0x40
HEAD_CHANNEL = 0
ARM_CHANNEL = 1
CAMERA_CHANNEL = 2
SERVO_FREQUENCY_HZ = 50.0
SERVO_MIN_PULSE_US = 1000
SERVO_MAX_PULSE_US = 2000
HEAD_SAFE_MIN_DEG = 0
HEAD_SAFE_MAX_DEG = 180
ARM_SAFE_MIN_DEG = 60
ARM_SAFE_MAX_DEG = 180
CAMERA_SAFE_MIN_DEG = 30
CAMERA_SAFE_MAX_DEG = 150
CENTER_DEG = 90
UPDATE_INTERVAL_MS = 20
SERIAL_BAUDRATE = 115200
```

## Python과 Arduino의 역할 차이

지원 Serial 명령:

```text
PING
STATUS
HELP
CENTER,<duration_ms>
MOVE_HEAD,<angle_deg>,<duration_ms>
MOVE_ARM,<angle_deg>,<duration_ms>
MOVE_CAMERA,<angle_deg>,<duration_ms>
MOVE_BOTH,<head_angle_deg>,<arm_angle_deg>,<duration_ms>
STOP
DISABLE
```

Python은 “언제 어떤 동작을 할지”를 결정한다. Arduino는 “받은 서보 명령이 안전 범위 안인지 확인하고 PWM으로 실제 이동을 수행”한다.

Raspberry Pi의 고개 안전 범위는 Arduino와 같고, 팔 안전 범위는 Arduino보다 좁다.

```text
Raspberry Pi Head: 0..180
Arduino Head: 0..180
Raspberry Pi Arm: 70..180
Arduino Arm: 60..180
Raspberry Pi Camera: 30..150
Arduino Camera: 30..150
```

현재 Raspberry Pi 목표 각도는 Arduino 안전 범위 안에 있다.
