# Initial Import Report

## 점검 요약

Mac 프로젝트 기준 경로 `/Users/hyunwoo/Documents/capstone design/capstone-robot-project`에서 실제 import된 파일을 다시 점검했다.

결론: 기존 0줄짜리 자리표시자 Python 파일들은 실제 Raspberry Pi 코드로 교체되었다. WAV 파일 2개도 존재한다.

이번 점검에서는 GitHub push, Raspberry Pi 배포, 프로그램 재시작, 자동 실행 활성화, Arduino 컴파일, Arduino 업로드를 실행하지 않았다.

## 1. Python 파일 목록과 줄 수

```text
86 raspberry_pi/robot_demo/audio_player.py
169 raspberry_pi/robot_demo/calibrate_servos.py
88 raspberry_pi/robot_demo/config.py
202 raspberry_pi/robot_demo/main.py
302 raspberry_pi/robot_demo/serial_controller.py
23 raspberry_pi/robot_demo/test_audio.py
39 raspberry_pi/robot_demo/test_button.py
39 raspberry_pi/robot_demo/test_sequence_no_button.py
21 raspberry_pi/robot_demo/test_serial.py
969 total
```

`._*.py` AppleDouble 메타데이터 파일도 rsync로 함께 들어왔지만 실제 Python 코드가 아니다. `.gitignore`에 `._*`를 추가했고, 현재 프로젝트 폴더에서는 정리했다.

## 2. WAV 파일 2개 존재 여부

아래 WAV 파일 2개가 존재한다.

```text
raspberry_pi/robot_demo/audio/01_name_call.wav
raspberry_pi/robot_demo/audio/02_lets_play.wav
```

파일 크기:

```text
126798 raspberry_pi/robot_demo/audio/01_name_call.wav
168270 raspberry_pi/robot_demo/audio/02_lets_play.wav
```

`._01_name_call.wav`, `._02_lets_play.wav` AppleDouble 메타데이터 파일도 함께 들어왔지만 현재 프로젝트 폴더에서는 정리했다. 이후 다시 들어오더라도 `.gitignore`의 `._*` 패턴으로 제외된다.

## 3. `audio_player.py`의 `pw-play` 우선 사용 여부

`audio_player.py`는 `pw-play`를 우선 사용한다.

확인 내용:

* 설명 주석에 PipeWire의 `pw-play`를 우선 사용한다고 명시되어 있다.
* `_player_command()`에서 `shutil.which("pw-play")`를 먼저 확인한다.
* `pw-play`가 있으면 `["pw-play", str(path)]`를 반환한다.
* `pw-play`를 찾지 못할 때만 `aplay` 명령을 구성한다.

## 4. `config.py`의 현재 목표 각도, 안전 범위, 이동 시간

목표 각도:

```text
HEAD_NEUTRAL_DEG = 90
HEAD_LEFT_DEG = 70
ARM_DOWN_DEG = 90
ARM_UP_DEG = 70
```

Raspberry Pi 설정의 안전 범위:

```text
HEAD_SAFE_MIN_DEG = 70
HEAD_SAFE_MAX_DEG = 110
ARM_SAFE_MIN_DEG = 70
ARM_SAFE_MAX_DEG = 110
```

이동 시간:

```text
HEAD_TURN_DURATION_MS = 400
ARM_RAISE_DURATION_MS = 500
RETURN_DURATION_MS = 600
STARTUP_HOME_DURATION_MS = 800
```

대기 시간:

```text
AFTER_HEAD_TURN_PAUSE_SEC = 0.15
BETWEEN_AUDIO_PAUSE_SEC = 0.25
AFTER_AUDIO_HOLD_SEC = 0.50
```

기타 관련 설정:

```text
SERIAL_BAUDRATE = 115200
ARDUINO_RESET_WAIT_SEC = 2.5
SERIAL_ACK_TIMEOUT_SEC = 1.5
SERIAL_DONE_MARGIN_SEC = 2.0
AUDIO_NAME_CALL = audio/01_name_call.wav
AUDIO_LETS_PLAY = audio/02_lets_play.wav
APLAY_DEVICE = None
```

## 5. Arduino `servo_controller.ino`의 안전 범위

Arduino 설정값:

```text
SERVO_MIN_PULSE_US = 1000
SERVO_MAX_PULSE_US = 2000
HEAD_SAFE_MIN_DEG = 0
HEAD_SAFE_MAX_DEG = 180
ARM_SAFE_MIN_DEG = 60
ARM_SAFE_MAX_DEG = 120
CENTER_DEG = 90
UPDATE_INTERVAL_MS = 20
SERIAL_BAUDRATE = 115200
```

주의: Arduino의 고개 안전 범위가 `0..180`으로 넓다. 실제 기구물 조립 상태에서는 충돌 가능성을 별도로 확인해야 한다.

## 6. Raspberry Pi 설정과 Arduino 설정 사이의 불일치

안전 범위 값은 서로 다르다.

```text
Raspberry Pi HEAD_SAFE = 70..110
Arduino HEAD_SAFE = 0..180

Raspberry Pi ARM_SAFE = 70..110
Arduino ARM_SAFE = 60..120
```

현재 Raspberry Pi의 목표 각도는 모두 Arduino 안전 범위 안에 있다.

```text
HEAD_NEUTRAL_DEG = 90  -> Arduino HEAD 0..180 안
HEAD_LEFT_DEG = 70     -> Arduino HEAD 0..180 안
ARM_DOWN_DEG = 90      -> Arduino ARM 60..120 안
ARM_UP_DEG = 70        -> Arduino ARM 60..120 안
```

따라서 현재 목표 각도 기준으로 Arduino가 명령을 거부할 불일치는 없다. 다만 안전 범위 정의 자체는 Raspberry Pi가 Arduino보다 더 좁으므로, 두 파일의 안전 범위를 같은 정책으로 맞출지 결정할 필요가 있다.

## 7. SSH 개인키, 비밀번호, 토큰, 로그 파일 포함 여부

SSH 개인키, `.env`, 토큰, 비밀번호 파일은 발견되지 않았다.

명백한 private key 본문, GitHub token, OpenAI-style API key, 토큰/비밀번호/secret 할당 형태의 값도 발견되지 않았다.

Raspberry Pi에서 가져온 실행 로그 파일 `raspberry_pi/robot_demo/robot_demo.log`는 정리했다. 이후 다시 들어오더라도 `.gitignore`의 `*.log` 패턴으로 Git 포함이 차단된다.

그 외 rsync로 함께 들어올 수 있는 로컬/메타데이터 파일도 Git 포함이 차단되어 있다.

```text
.DS_Store      -> .gitignore의 .DS_Store 패턴으로 제외
._*            -> .gitignore의 ._* 패턴으로 제외
__pycache__/   -> .gitignore의 __pycache__/ 패턴으로 제외
```

## 8. `scripts/check_python.sh` 실행 결과

초기 실행에서는 `._*.py` AppleDouble 메타데이터 파일 때문에 실패했다.

```text
ValueError: source code string cannot contain null bytes
```

`scripts/check_python.sh`가 `._*` 파일을 건너뛰도록 수정한 뒤 다시 실행했고, 성공했다.

성공 시 출력:

```text
Listing 'raspberry_pi/robot_demo'...
Listing 'raspberry_pi/robot_demo/audio'...
Listing 'raspberry_pi/robot_demo/systemd'...
```

## 추가로 import된 파일

기존 계획에 없던 Raspberry Pi 보조 파일도 함께 들어왔다.

```text
raspberry_pi/robot_demo/install_dependencies.sh
raspberry_pi/robot_demo/run_robot_demo.sh
raspberry_pi/robot_demo/systemd/robot-demo.service.example
```

이 파일들은 아직 배포, 실행, 자동 실행 활성화에 사용하지 않았다.
