"""
Raspberry Pi 4 워킹 프로토타입 설정 파일

중요:
- 실제 기구물을 조립한 뒤 calibrate_servos.py로 네 개의 각도를 찾으세요.
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

# 택트 스위치 바운스 방지 시간
BUTTON_BOUNCE_SEC = 0.05

# ============================================================
# 2. Arduino USB Serial 설정
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
# 3. 서보 각도 설정
# ============================================================

# 아래 네 값은 실제 기구물 조립 후 calibrate_servos.py로 찾습니다.
# 반드시 안전 범위 안의 정수로 교체하세요.
HEAD_NEUTRAL_DEG = 90  # 고개 정면
HEAD_LEFT_DEG = 70     # 로봇 기준 왼쪽으로 고개 회전

ARM_DOWN_DEG = 90      # 오른팔 초기 자세
ARM_UP_DEG = 70        # 오른팔 상승 자세

# Arduino 코드의 초기 안전 범위와 동일하게 맞춥니다.
# Arduino 쪽 범위를 바꾸면 여기 값도 같이 바꾸세요.
HEAD_SAFE_MIN_DEG = 70
HEAD_SAFE_MAX_DEG = 110

ARM_SAFE_MIN_DEG = 70
ARM_SAFE_MAX_DEG = 110

# ============================================================
# 4. 동작 시간 설정
# ============================================================

# 단위: ms
HEAD_TURN_DURATION_MS = 400
ARM_RAISE_DURATION_MS = 500
RETURN_DURATION_MS = 600
STARTUP_HOME_DURATION_MS = 800

# 단위: sec
AFTER_HEAD_TURN_PAUSE_SEC = 0.15
BETWEEN_AUDIO_PAUSE_SEC = 0.25
AFTER_AUDIO_HOLD_SEC = 0.50

# ============================================================
# 5. 오디오 설정
# ============================================================

AUDIO_NAME_CALL = BASE_DIR / "audio" / "01_name_call.wav"
AUDIO_LETS_PLAY = BASE_DIR / "audio" / "02_lets_play.wav"

# Raspberry Pi OS의 기본 ALSA 출력 장치를 사용하려면 None으로 둡니다.
# 특정 출력 장치를 지정해야 할 때만 예: "plughw:0,0"
APLAY_DEVICE = None
