# CUVO Robot Source Baseline

## 2026-10-20 인수인계 기준

초기 2/3축 버튼 코드만 있는 상태가 아니다. 최신 6축 펌웨어·Pi BLE 서비스·독립 OLED 두 눈·통합 실행기와 오프라인 3D 미리보기 소스를 포함한다. 앱과 로봇의 공통 기준 태그는 `cuvo-baseline-2026-10-20`이다.

| 구성 | 저장소 | 진입점 |
| --- | --- | --- |
| Pi / Mega / 시뮬레이터 | [CapstonePy](https://github.com/d3s1gn0va/CapstonePy) | 이 문서와 `AGENTS.md` |
| iPhone 앱 | [KeepEye](https://github.com/d3s1gn0va/KeepEye) (비공개) | `CURRENT_SOURCE.md`, `KeepEye.xcodeproj` |

앱은 비공개 저장소 접근 권한이 필요하다. 두 저장소의 기준 버전을 함께 가져온다. 변경 내용은 커밋/업로드 후 상대 작업 환경에서 가져와야 하며 GitHub 업로드가 Pi 자동 배포를 뜻하지 않는다.

## 먼저 읽을 문서

1. [AGENTS.md](AGENTS.md): 안전 경계와 작업 규칙.
2. [현재 상태](docs/09_CURRENT_STATE.md), [원점/범위](docs/08_CALIBRATION_AND_SAFETY.md): 최신 날짜 우선.
3. [Bluetooth 운용](docs/21_BLUETOOTH_CONTROL.md): 프로토콜 v1, 등록/재인증, 부팅 대기, 정지·통신 소실 처리.
4. [공유 안무와 미리보기](docs/22_OFFLINE_CHOREOGRAPHY_PREVIEW.md): 새 춤은 시뮬레이터 단계이며 기존 Pi 기본 춤과 구분.

루트의 `01_Project_Context.md`, `02_Reasoning_and_Questions.md`, `03_Current_Output.md`와 아래쪽 3채널 설명은 이전 기록이다. 충돌하면 과거 각도/실행 경로를 재사용하지 않는다.

## 코드 위치

아래 파일은 별도 표시가 없으면 `raspberry_pi/robot_demo/` 안에 있다.

| 영역 | 소스 |
| --- | --- |
| BLE 서비스/자동 대기 | `cuvo_ble.py`, `systemd/cuvo-ble.service` |
| 제어권/heartbeat/자격 저장 | `ble_control.py`, `ble_credentials.py` |
| 현행 제한된 실제 춤 worker | `ble_dance_worker.py`, `test_dance_once.py`, `dance_config.json` |
| 순서 실행/안무 컴파일 | `integrated_sequence.py`, `dance_sequence.py`, `choreography.py` |
| 장치 출력/Serial | `integrated_hardware.py`, `serial_controller.py` |
| 눈 매핑/그림/완료 후 깜박임 | `oled_*.py`, `oled_aperture.json`, `idle_eyes.py`, `idle_eye_worker.py` |
| 6축 원점/범위/전원 전환 자세 | `robot_motion_profile.json`, `motion_profile.py`, `power_pose.py` |
| Mega/PCA9685 | 저장소 루트 `arduino/servo_controller/servo_controller.ino` |
| 가상 기록/3D 재생 | `export_simulation.py`, 저장소 루트 `tools/servo-simulator/` |

상대 0의 명령값은 고개 CH0=90, 오른팔 X CH1=45, 정수리 CH2=90, 오른팔 Y CH3=0, 왼팔 X CH4=135, 왼팔 Y CH5=180이다. 범위/역방향은 프로필이 기준이다. 팔꿈치 120..180도는 수동 프리스탑이며 서보 채널이 아니다.

## 실제 춤과 새 미리보기

* 기존 Pi 춤: 한쪽 이동 550ms, 팔 상대 X 0..80/Y 45, 고개 60..120, 4회, 완료 후 눈 깜박임. 실물 확인 이력과 제한은 현재 상태 문서를 따른다.
* `CUVO Groove`: schema 2 JSON, 100BPM/16박, 가상 기록 약 12.3초. **미리보기 확인 단계이며 Pi/Arduino에 배포하지 않았다.** BLE 기본 춤을 자동 교체하지 않는다.
* 일반 실행기의 `verified`/`power_verified`는 false다. 제한된 과거 실물 시험을 전체 기구/전원 검증으로 취급하지 않는다.
* 옛 `main.py`/자동 실행을 임의 재시작하지 않는다. 배포/서비스 시작은 실물 동작을 유발할 수 있으므로 소스 확인만 할 때 실행하지 않는다.

## 장치 없이 검사

Pillow가 있는 Python 3를 사용한다. CAD 가져오기 검사에는 선택 의존성 `ezdxf`가 필요하다.

```sh
python3 -m unittest discover -s tests -t .
c++ -std=c++17 -Wall -Wextra -I tests/firmware_stubs \
  tests/firmware_group_test.cpp -o /tmp/cuvo-firmware-group-test
/tmp/cuvo-firmware-group-test
```

시뮬레이터는 `tools/servo-simulator/index.html`을 직접 연다. 소스를 고쳤다면 해당 폴더에서 의존성 설치 후 다시 빌드한다. [도구 안내](tools/servo-simulator/README.md)를 따른다.

2026-10-20 Python 114개 중 110개 통과/선택 CAD 4개 건너뜀, 시뮬레이터 모델 14개 통과, 가짜 PWM을 사용한 C++ 6축/교대 명령 검사 통과. 비밀키·실제 등록 토큰·페어링 DB·`scripts/local.env`·로그·캐시는 포함하지 않는다. 이번 정리는 Mac 소스 반영이며 Pi 접속/배포/서보 실행과 별개다.
