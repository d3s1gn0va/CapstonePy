"""
Raspberry Pi 4 워킹 프로토타입 설정 파일

중요:
- 실제 기구물을 조립한 뒤 calibrate_servos.py로 서보 각도를 찾으세요.
- 각도를 찾기 전에는 None을 숫자로 바꾸지 말고 main.py를 실행하지 마세요.
- Arduino 코드의 안전 각도 범위도 필요에 따라 5도씩만 넓혀 다시 업로드하세요.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ============================================================
# 1. 버튼 설정
# ============================================================

# BCM GPIO 번호입니다. 물리 핀 번호 11번에 해당합니다.
BUTTON_GPIO = 17

# 추가 버튼 GPIO입니다.
# 물리 핀 번호 기준: GPIO27=13번, GPIO22=15번
POWER_OFF_BUTTON_GPIO = 27
CAMERA_BUTTON_GPIO = 22

# 택트 스위치 바운스 방지 시간
BUTTON_BOUNCE_SEC = 0.05

# ============================================================
# 2. LED 설정
# ============================================================

# 카메라 서보가 움직이는 동안 켜지는 LED입니다.
# BCM GPIO23은 Raspberry Pi 물리 핀 16번에 해당합니다.
CAMERA_LED_GPIO = 23

# ============================================================
# 3. Arduino USB Serial 설정
# ============================================================

# None이면 /dev/serial/by-id, /dev/ttyACM*, /dev/ttyUSB* 순서로 자동 탐색합니다.
# 자동 탐색이 잘 되면 None 그대로 사용하세요.
# 장치를 직접 고정하고 싶다면 예: "/dev/ttyACM0"
SERIAL_PORT = None

SERIAL_BAUDRATE = 115200

# Arduino는 USB Serial 포트를 열 때 재부팅될 수 있습니다.
ARDUINO_RESET_WAIT_SEC = 2.5

SERIAL_ACK_TIMEOUT_SEC = 1.5
SERIAL_DONE_MARGIN_SEC = 2.0

# True이면 Arduino에서 수신한 줄을 Raspberry Pi 터미널에도 표시합니다.
LOG_SERIAL_LINES = True

# ============================================================
# 4. 서보 각도 설정
# ============================================================

# 아래 네 값은 실제 기구물 조립 후 calibrate_servos.py로 찾습니다.
# 반드시 안전 범위 안의 정수로 교체하세요.
HEAD_NEUTRAL_DEG = 0    # 고개 기본 자세
HEAD_LEFT_DEG = 70      # 버튼 시퀀스에서 고개 이동 목표

ARM_DOWN_DEG = 90      # 오른팔 초기 자세
ARM_UP_DEG = 180       # 오른팔 상승 자세

CAMERA_CENTER_DEG = 90
CAMERA_LEFT_DEG = 30
CAMERA_RIGHT_DEG = 150

# Arduino 코드의 고개 안전 범위와 동일하게 맞춥니다.
# 전체 범위 이동은 실제 기구물 충돌 가능성을 확인한 뒤 사용하세요.
HEAD_SAFE_MIN_DEG = 0
HEAD_SAFE_MAX_DEG = 180

ARM_SAFE_MIN_DEG = 70
ARM_SAFE_MAX_DEG = 180

CAMERA_SAFE_MIN_DEG = 30
CAMERA_SAFE_MAX_DEG = 150

# ============================================================
# 5. 동작 시간 설정
# ============================================================

# 단위: ms
HEAD_TURN_DURATION_MS = 1200
ARM_RAISE_DURATION_MS = 1200
RETURN_DURATION_MS = 1800
STARTUP_HOME_DURATION_MS = 1800
CAMERA_SWEEP_DURATION_MS = 2000
CAMERA_RETURN_DURATION_MS = 1500

# 단위: sec
AFTER_HEAD_TURN_PAUSE_SEC = 0.15
BETWEEN_AUDIO_PAUSE_SEC = 0.25
AFTER_AUDIO_HOLD_SEC = 0.50

# ============================================================
# 6. 오디오 설정
# ============================================================

AUDIO_NAME_CALL = BASE_DIR / "audio" / "01_name_call.wav"
AUDIO_LETS_PLAY = BASE_DIR / "audio" / "02_lets_play.wav"

# Raspberry Pi OS의 기본 ALSA 출력 장치를 사용하려면 None으로 둡니다.
# 특정 출력 장치를 지정해야 할 때만 예: "plughw:0,0"
APLAY_DEVICE = None
