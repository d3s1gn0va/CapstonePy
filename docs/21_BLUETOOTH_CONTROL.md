# CUVO 기본 앱과 BLE 춤 실행

## 2026-10-13 전원 전환 자세 배포

새 팔 원점/범위와 정상 부팅·서비스 종료 원점 복귀를 Pi/Arduino에 설치했다. 업로드 검증/PING/CAPS와 첫 6축 원점 명령 완료, 정상 서비스 종료 복귀의 성공 종료 및 대기 재시작/10초 유지/NRestarts=0 확인. 실제 자세 관찰과 전체 OS 재부팅/종료 검증은 남아 있다. 최신 상태와 조건은 [현재 상태](09_CURRENT_STATE.md), [새 원점/안전](08_CALIBRATION_AND_SAFETY.md)을 따른다. `--home-on-start-stop`은 부팅 준비/정상 종료에만 6축을 원점으로 이동하며, 연결/앱 STOP/통신 오류는 추가 이동을 하지 않는다.

2026-10-06 기준. 앱은 인접 KeepEye 프로젝트이며 표시 이름은 CUVO다. 전시 체험모드 대신 기본 로봇 연결/놀이 화면이다. Pi와 휴대폰의 BLE 통신에는 학교 Wi-Fi가 필요하지 않다. 개발 중 원격 배포에는 기존 SSH 접속이 필요하다.

## 현재 구현과 구분

**눈 대기 추가(2026-10-06):** 정상 춤 완료 후 정면에서 지속 깜박이고 다음 시작 버튼을 기다린다. 기존 눈 매핑/선/밝기를 유지한다. `idle_eyes.py`가 OLED 전용 실행부를 관리하고 다음 춤 시작 전에 종료/잠금 해제를 기다린다. 눈 대기에는 Serial/서보/음성을 사용하지 않는다. 35초 제한은 춤에만 적용하며 눈 대기 때문에 앱을 계속 실행 중 상태로 두지 않는다. 정상 완료 후 연결이 끊겨도 깜박임은 유지한다. 중단/오류를 정상 완료로 간주하거나 춤을 자동 재실행하지 않는다.

깜박임 설정은 `oled_pair_calibration.json`을 공용으로 사용한다. 열림 3초/닫기 0.12초/닫힌 상태 0.08초/다시 열기 0.22초, 전체 반복 3.42초다. 비공개 임시 runtime의 `idle-eyes-enabled`는 정상 완료 후 눈 대기 표시이며 운동 명령이나 인증 정보가 아니다. 다음 시작 전 제거하고 같은 부팅의 서비스 재시작에서만 대기를 복원한다. Pi 전원 재부팅 뒤에는 정상 완료 전 눈 대기를 새로 켜지 않는다. 종료 시 눈을 정리하고, 눈 실행부 오류는 자동 재시도하지 않는다. 현재 배포의 눈 대기 실행 유지와 Serial 비점유는 확인했으며 화면 관찰/다음 실제 춤 전환은 사용자 확인이 필요하다.

**최신(2026-10-06): 학교용 부팅 자동 대기/등록 폰 재연결이 배포됐다.** 사용자 실제 Pi 재부팅 뒤 부팅 약 16초에 새 서비스가 시작됐고, 앱을 다시 열어 코드 입력 없이 제어권/idle/갱신 유지 확인. Linger=yes/서비스 enabled, 옛 전시 autostart는 비활성 원본 보존 상태다. 앱 로직 26개/Python 90개 중 86개 통과·기존 CAD 4개 건너뜀. 이하의 임시 코드 반복/자동 실행 미활성/춤 잠금 상태는 당시 기록이며 최신 운용은 다음 절을 따른다.

## 학교용 오프라인 운용

전원 연결 → Pi 자동 부팅·Bluetooth 대기 → 앱 열기 → 등록된 CUVO 재인증 → 준비 확인 → 사용자가 놀이 시작. 연결이 유지되는 것이 아니라 저장된 등록 정보를 이용해 새 연결/제어권을 얻는다. 부팅/연결만으로 서보를 움직이거나 이전 춤을 재개하지 않는다. 앱의 검색·재연결은 전면에서만 하며 자동 시도는 세 번으로 제한한다. 부팅이 오래 걸려 시도가 끝났다면 앱을 다시 열거나 CUVO 찾기를 누른다.

최초 등록은 제한된 설정 창에서 6자리 코드로 한다. 앱이 만드는 32바이트 난수 토큰은 iPhone의 로컬 Keychain에 저장하고 Pi에는 해시만 저장한다. Pi 저장 위치는 `~/.local/state/cuvo/controller.json`(폴더 0700/파일 0600)이며 Git에 넣지 않는다. `session.resume`은 코드 없이 등록된 페어링 장치·client ID·토큰을 검증한다. 토큰은 암호화된 GATT 쓰기로만 전송하고 public 상태/광고/로그에 싣지 않는다. 기기 이름이나 주소만으로 제어권을 주지 않는다. 폰/등록 정보가 바뀌면 운영자 설정 창을 다시 열어 재등록한다. 신규 등록 코드는 시작 후 15분간 유효하지만 정상 등록 폰의 resume는 그 제한을 적용하지 않는다. Just Works의 MITM 한계는 남아 있으며 완성된 제품 보안 인증이 아니다.

서비스 파일은 `raspberry_pi/robot_demo/systemd/cuvo-ble.service`다. 기존 배포 폴더와 OLED 시험용 venv를 사용한다. 사용자 서비스/default.target/linger로 데스크톱·SSH 로그인 없이 시작하고 `network-online.target`을 기다리지 않는다. PipeWire/WirePlumber 준비 순서를 지정하고 USB/SPI/음성 소켓 존재를 확인한다. 실제 Arduino PING/명령은 사용자가 춤 시작을 승인한 뒤 실행부가 수행한다. 서비스의 승인 인수는 지정된 5축 춤 범위만 허용하며 전체 기구 검증이나 실제 전압 감지를 의미하지 않는다. 5V와 공간 확인은 매 시작 확인창에 표시한다. 서보 전원이 꺼졌다는 사용자 보고가 있으면 운영자가 서비스를 확인 인수 없이 준비해 춤을 잠근다.

서비스 실패 시 제한된 재시작을 허용하지만 이전 명령/춤은 재실행하지 않는다. 종료할 때 새 시작을 차단하고 cgroup의 실행부를 함께 정리한다. daemon/OS 장애에 독립적인 하드웨어 비상 정지를 보장하지 않는다. 옛 3축 실행부와 물리 버튼 자동 실행은 복원하지 않았다. 실제 사운드카드 재연결, 무인터넷 조건 춤/정지/링크 소실과 물리 종료 버튼 통합은 다음 검증이다.

재설치 순서: `scripts/deploy_ble_remote.sh`로 코드 복사 → 사용자 승인 후 `scripts/setup_ble_autostart_remote.sh`로 사용자 unit/linger/enable 설치. SSH 목적지와 키는 기존 로컬 환경 변수로 지정한다. 설치 스크립트는 현재 서비스를 재시작하지 않는다. 처음 준비하거나 변경판을 시작할 때는 움직임/제어권이 없는 것을 확인한 뒤 다음을 수행한다.

```bash
systemctl --user start cuvo-ble.service
systemctl --user status cuvo-ble.service
```

등록 초기화가 필요하면 서비스를 멈추고 비공개 등록 파일을 안전하게 보관한 뒤 제거하고 다시 준비한다. 활성 연결/동작 중 등록을 덮어쓰거나 모든 Bluetooth bond를 삭제하지 않는다. 앱 번들 식별자를 바꾸면 등록 저장소 접근이 달라질 수 있으므로 현재 식별자를 유지한다. 개발용 iPhone 앱 서명은 **2026-10-13 01:05 KST** 만료이며 이후 행사 전 재빌드/설치가 필요하다.

## 이전 진단 기록

최신 USB 복구 확인: 사용자 재부팅으로 Arduino USB 장치가 다시 인식됐고 10초 유지/현재 부팅 xHCI 장애 없음 확인. 옛 전시 자동 실행은 차단 상태로 보존한다. 사운드카드 분리/서보 전원 OFF이므로 별도 BLE 서비스는 `--confirm-5v-and-clear` 없이 idle/`motion_ready=false` 대기로 다시 준비했다. 앱 연결은 가능하나 춤 시작은 잠겨 있으며 Arduino Serial/PING/서보는 실행하지 않았다. 실제 전원·공간 재확인 없이 확인 인수를 넣어 다시 시작하지 않는다. 아래 중지/인증 대기는 이전 단계 기록이다.

USB 복구 준비 후 현재 운용: 사용자 서보 전원 OFF/사운드카드 분리 확인 아래 옛 전시 autostart 원본을 비활성 접미사 파일로 보존하고 별도 BLE daemon을 종료했다. 재부팅 요청은 Pi 관리자 인증 필요로 거부되어 아직 복구 전이다. 현재 앱 검색/연결은 서비스 재준비 전 사용할 수 없다. USB 인식 확인 후 별도 BLE 대기 서비스만 다시 준비하며, 옛 3축 전시 프로그램의 자동 실행을 임의로 복원하지 않는다.

* `ble_control.py`: 장치 독립적인 연결 코드/제어권/중복 명령/heartbeat/실행 제한.
* `cuvo_ble.py`: BlueZ GATT, 광고, 제한 시간 페어링 agent, 단일 춤 실행부 관리. 검색/연결/코드 확인만으로 서보를 시작하지 않는다. 정상 완료 후에는 OLED 전용 눈 대기를 관리한다.
* `ble_dance_worker.py`: 명시적으로 승인한 5축 춤 한 번. 기존 `DanceTestBackend`의 정확한 목표/순서/범위 검사를 사용하며 정수리 CH2를 움직이지 않는다.
* 기존 `main.py`, Arduino 펌웨어, PWM, 전체 프로필 검증 플래그 및 자동 부팅 서비스는 그대로다. 현재 구성이 최종 전시 자동 실행 배포를 완료한 것은 아니다.

사용자는 새 550ms/팔 X 상대 0..60의 5V·이동 공간을 확인했다. 이 확인은 지정된 춤만 허용하며 전체 전원 부하 계측/기구 검증 완료를 의미하지 않는다. 첫 PWM 출력은 위치 피드백이 없어 움직임이 빠를 수 있다.

## 앱 흐름

CUVO 찾기 → 기기 선택 → iOS Bluetooth 허용/필요한 페어링 → 임시 연결 코드 확인 → 준비 상태 → 춤 따라하기 시작 → 현장 공간 확인 → 실행.

코드는 Pi 운영자가 SSH로 읽는 비공개 런타임 파일에만 저장한다. 코드 유효 시간은 15분, 한 기기만 제어할 수 있고 잘못된 코드 시도는 분당 5회까지다. 앱 연결/재연결은 자동 시작하지 않는다. 정상 완료 후 다음 춤도 사용자가 따로 시작한다.

## 규격 v1

| 용도 | UUID | 속성 |
| --- | --- | --- |
| 서비스 | `C8A00001-7A1B-4F4A-9B5A-4355564F0001` | 광고 |
| 명령 | `C8A00002-7A1B-4F4A-9B5A-4355564F0001` | write / encrypt-write |
| 상태 | `C8A00003-7A1B-4F4A-9B5A-4355564F0001` | read / notify |

UTF-8 JSON 한 줄. 명령 한 번 최대 512바이트/확인 응답 쓰기. 명령은 `version=1`, `request_id` UUID, `client_id` UUID, `action`을 포함한다. 지원 action은 `session.claim`(추가 `code`), `session.status`, `dance.start`, `session.stop`이다. 임의 서보 각도를 받지 않는다.

상태는 `version`, 증가하는 `revision`, `request_id`, `state`, `phase`, `progress`, `control_granted`, `controller_id`, `motion_ready`, `message`다. 알림은 20바이트 조각으로 순서대로 보내고 앱이 줄바꿈까지 조립한다. 상태는 모든 구독자에게 공유되므로 자기 client_id와 controller_id가 일치해야 제어한다. BlueZ의 실제 장치 경로까지 소유자와 일치해야 명령을 받는다.

코드 제출 전의 상태 조회는 public read를 사용해 입력창이 인증 대기 때문에 숨겨지지 않도록 한다. 재접속 때 이미 활성화된 알림이 첫 프레임을 다시 보내지 않아도 상태를 직접 읽는다. 코드 제출부터는 암호화 명령 쓰기를 사용하며 이후 소유자 heartbeat도 인증된 `session.status` 쓰기로 갱신한다. public read는 제어권을 주거나 heartbeat를 연장하지 않는다. 전체 read 응답과 알림 조각은 서로 다른 디코더로 처리하고 Pi는 Read Blob offset 전체에 동일한 스냅샷을 반환한다.

인증 후에도 확인 응답 쓰기가 성공하면 전체 상태 read를 추가한다. 연결된 상태에서 알림 수신이 멈춰 앱 상태가 낡는 경우를 보완하며, 실제 새 스냅샷 없이 쓰기 성공만으로 freshness/시작/정지를 확인하지 않는다. 성공한 claim 요청 ID는 후속 read에서도 유지한다. 2026-10-06 수정 설치 후 사용자는 지연 문구가 사라졌다고 확인했고 Pi의 제어권/갱신도 20초 유지됐다. 같은 확인에서 춤 준비 Serial `No such device` 및 USB Serial 장치 부재가 별도로 발견돼 서비스는 error/시작 잠금이다. USB 연결을 확인하기 전 오류를 자동 초기화하거나 춤을 재실행하지 않는다.

서비스/명령/상태의 v1 GATT Handle은 `0x0100`/`0x0102`/`0x0104`로 고정한다(상태 CCC는 BlueZ가 `0x0105`에 배치). 실행할 때마다 다른 주소를 자동 할당하지 않으며 충돌 시 등록 실패로 중단한다. 기존 자동 할당판에 연결했던 iPhone은 이전 정보를 보관할 수 있다. 실제 시험에서 `CBATTErrorDomain(1): The handle is invalid.`를 확인했다. 이 경우 iPhone 설정 → Bluetooth → `pi` 또는 `CUVO` → 이 기기 지우기 후 다시 연결한다. 다른 기기의 연결 정보까지 삭제하지 않는다. 앱은 서비스 변경을 다시 읽고 invalid handle에 한 번만 재탐색하며 자동으로 춤을 재시작하지 않는다.

`CBATTErrorDomain(15): Encryption is insufficient.`는 명령이 암호화 조건을 만족하지 못했다는 뜻이다. iPhone에서 지워도 Pi에 이전 bond가 남을 수 있으므로 양쪽 상태를 확인한다. 2026-10-06 사용자의 명시 승인으로 Pi의 해당 iPhone 1건만 제거하고 키보드/마우스 3건을 보존했다. 모든 bond 삭제나 암호화 조건 제거로 우회하지 않는다. 임시 코드/페어링 창이 만료됐다면 정지·제어권 없음 확인 후 운영자가 새 창을 준비한다.

## 중단과 한계

* 앱이 전면에서 1초마다 상태를 요청한다. 소유자 응답이 3초 끊기거나 실제 BLE 연결이 끊어지면 Pi가 실행부에 중단을 요청한다.
* STOP은 미전송 시작보다 우선하며 바쁜 동안 새 시작을 큐에 쌓지 않는다. 같은 요청 ID는 저장된 중복 방지 범위에서 다시 실행하지 않는다.
* 단일 실행부가 Serial lock/기존 프로그램 점유 검사/PING/CAPS 일치 검사 후 움직인다. 상태 보고와 GATT 처리 자체는 별도라 춤 도중에도 정지 요청을 받을 수 있다.
* Arduino `ACK,STOP`/오디오 정리와 정상 실행부 종료가 확인된 뒤에만 `stopped`/`completed`를 보고한다. STOP은 PWM 유지이며 물리적 비상 전원 차단이 아니다.
* 실행부 35초 제한, 정지 응답 6초 제한. 강제 종료 시 `error`를 보고하며 실제 정지로 단정하지 않는다. 오류 뒤 자동 복귀/재시작하지 않는다.
* 페어링 agent는 운영자가 지정한 최대 15분 창에서 Just Works 연결만 받는다. 코드 확인을 추가했어도 MITM 방지·보안 인증이 완료된 것은 아니다. daemon/OS의 갑작스러운 장애까지 보호하는 독립 하드웨어 watchdog은 아직 없다.

## Pi에서 다시 준비하기

현재 개발 배포 위치는 `~/capstone-robot-build/ble_control_20261006/robot_demo/`다. 기존 `~/robot_demo/`와 혼동하지 않는다. Python은 필요한 dbus/GI/luma/serial가 있는 기존 `~/cuvo_oled_test/.venv/bin/python`을 사용한다. 다음은 **Pi에서 실행하는 명령**이다.

```bash
cd ~/capstone-robot-build/ble_control_20261006/robot_demo
~/cuvo_oled_test/.venv/bin/python cuvo_ble.py --confirm-5v-and-clear --pairing-seconds 120
```

전원/기구 확인 인수 없이 실행하면 BLE 연결 시험만 가능하고 춤은 잠긴다. 동시에 하나의 daemon만 허용한다. 재시작 전에 기존 실행부가 멈췄는지 확인하며 오래된 전시 프로그램은 켜지 않는다. Ctrl+C는 진행 중 춤을 중단/정리하고 광고와 agent를 해제한다. 현재 배포는 자동 실행을 활성화하지 않았으므로 Pi 재부팅 후에는 다시 준비해야 한다.

```bash
cat /tmp/cuvo-ble-$(id -u)/connection-code
cat /tmp/cuvo-ble-$(id -u)/status.json
```

코드·실제 장치 주소·로그는 문서/Git에 옮기지 않는다. Mac의 `scripts/deploy_ble_remote.sh`는 승인된 `PI_HOST`/`SSH_KEY` 환경값을 받아 WAV/루트 Python/JSON만 허용 목록으로 복사하고 `.DS_Store`, `._*`, 키/환경 파일/로그/캐시를 제외한다. `--delete`는 사용하지 않는다. 이 스크립트는 서비스 시작/서보 실행/업로드/자동 실행 변경을 하지 않는다.

## 검증 상태

Python 문법 통과. 앱 로직 19개 통과. Python 82개 중 78개 통과/기존 CAD 가져오기 4개는 ezdxf 부재로 건너뜀. 고정 주소/속성/UTF-8 분할/Read Blob 및 전체 read·알림 교차 검사를 포함한다. iOS 서명 없는 검사 빌드, 개발 서명 빌드와 iPhone 설치 성공. Pi preflight/광고 등록/idle/Serial 비점유/최근 로그 확인 완료. 이전 GATT 주소 오류와 입력창 소실 문제를 수정한 뒤 실제 iPhone에서 검색/선택/코드 입력창 **15초 유지 검사 1개 통과**. 인증 후 지속 연결과 춤은 별도 확인한다. 최신 코드와 Pi 배포 해시를 별도로 대조한다.

후속 실물 인증: 이전 Pi iPhone bond 제거 후 사용자가 새 코드로 연결했다. Pi에서 Paired/Bonded/Connected와 제어권을 확인하고 **20초 동안 1초 간격 heartbeat 및 idle 유지**를 관찰했다. 최종 상태도 제어권/준비 true였다. 인증·지속 연결은 완료됐으며 새 춤/정지 시험과는 구분한다.

**아직 확인할 것:** 두 눈/음성/팔 연동 관찰, 새 춤 완료, 도중 정지, 앱 비활성/연결 끊김의 실물 중단, 두 번째 기기 제어권 거부. 가상 검사·설치·광고·인증 성공을 실물 춤 성공으로 기록하지 않는다.

API 근거: [BlueZ GATT](https://github.com/bluez/bluez/blob/master/doc/org.bluez.GattCharacteristic.rst), [Agent](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Agent.rst), [Advertisement](https://github.com/bluez/bluez/blob/master/doc/org.bluez.LEAdvertisement.rst).
