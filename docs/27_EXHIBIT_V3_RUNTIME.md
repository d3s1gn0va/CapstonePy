# 전시 앱 v3 / 촬영 런타임 구현

2026-10-20 로컬 구현이다. Pi 접속·배포·서보/OLED/카메라 실물 시험·Arduino 업로드를 수행하지 않았다. 기존 `robot_motion_profile.json`, PWM, 펌웨어, 축 검증 플래그와 기존 제한 춤을 바꾸지 않았다. 새 씬은 기구에서 검증된 동작으로 표시하지 않는다.

## 구성과 실행 정책

`cuvo_ble.py`의 기존 BlueZ 서비스 UUID·GATT 핸들·암호화 쓰기·페어링·기기 결합 토큰·3초 heartbeat lease를 유지한다. `ExhibitControl`은 인증 후 고정 명령만 해석한다. 하나의 `ExhibitWorker` 프로세스가 기존 `IntegratedSequence`와 6축/OLED/오디오 드라이버를 소유한다. 앱 연결, 이름 저장, 화면 복귀, 재접속은 로봇 동작을 시작하지 않는다.

`session.stop`과 연결 손실은 작업 종료를 요청하고 STOP ACK와 worker 정상 종료를 확인한다. 중단 뒤 자동 홈 이동·재개를 하지 않는다. 6초 안에 정지 확인이 안 되면 프로세스 그룹을 종료하고 오류로 표시한다. 이미 큐에 있던 완료보다 중단을 우선한다. 일반 실행 35초, 녹화 마감 포함 부모 감시 60초로 제한한다. 명령 UUID 중복은 다시 실행하지 않는다.

볼륨/기록 목록 작업은 별도 실행기에 둬 STOP/heartbeat를 막지 않는다. 늦게 끝난 설정 요청이 더 최근 STOP/종료 응답을 덮어쓰지 않는다. 앱의 60초 화면 복귀는 UI 기능이며 Pi 타이머가 아니다.

## v1 호환 명령

봉투는 `{version:1, request_id:UUID, client_id:UUID, action:String, payload?:Object}`이다. 기존 claim/resume의 `code`/`token` 필드와 모든 기존 명령을 유지한다. 전체 명령은 최대 512바이트다.

| action | payload | 결과/조건 |
|---|---|---|
| `play.start` | `play_id`: `yogicok`, `name_call`, `dance` | 한 놀이만 실행. 선택 자체는 실행하지 않음 |
| `scene.start` | `scene_id`: `01`, `02`, `03`, `04`, `05_06`, `09` | 고정 콘티 프리셋만 실행 |
| `pose.reset` | 없음 | 별도로 요청한 6축 원점 복귀. 중단 복귀와 분리 |
| `profile.set` | `child_name`, `profile_id`: UUID | 공백 제거/NFC 정규화, 최대 30글자. 빈 이름은 초기화 |
| `audio.volume.set` | `volume`: 정수 0…100 | PipeWire 기본 출력에 적용하고 실제 값을 읽어 응답 |
| `system.shutdown` | 없음 | 정지/정상 정리 후 OS 정상 종료 요청 |
| `records.list` | `offset`: 기본 0, `limit`: 기본 1/최대 3 | 실제 완성된 기록 메타데이터 |
| `records.get` | `record_id`: UUID | 특정 실제 기록 메타데이터 |

상태 확장: `run_id`, `play_id`, `scene_id`, `command_result:{request_id,action,ok,message}`, `profile:{profile_id,voice_ready}`, `volume:{percent,muted,available,backend,error}`, `recording:{state,error}`, `latest_record`, `records`, `media`, `shutdown_requested`.

`capabilities`에는 `actions`, `plays`, `scenes`, `exhibit_ready`, `recording_supported`, `media_supported`가 있다. `plays/scenes`는 지원하는 식별자다. 준비됨을 보장하지 않는다. 기존 춤은 `motion_ready`, 새 놀이/씬은 `exhibit_ready`, 이름 사용 씬은 추가로 `voice_ready`를 확인한다. 빠진 음성은 시작 요청에 실패 응답을 반환한다.

`command_result.ok=true`는 시작/중단/종료 요청을 받았다는 뜻이며 실제 완료는 후속 상태로 확인한다. 볼륨은 실제 읽기 이후에만 성공 응답한다. heartbeat는 마지막 명령 결과를 지우지 않는다. `run_id`는 매 실행의 UUID로 명령 요청 UUID와 분리한다.

원시 이름은 RAM과 worker의 비공개 stdin에만 전달한다. 공개 read/notify 상태와 기록 파일명·로그에는 이름·등록 토큰을 넣지 않는다. 앱은 자신이 만든 불투명 `profile_id`로 이름 확인을 대응한다.

### BLE 전송 크기

ATT 읽기는 `compact:true`와 기존 v1 기본 상태 + `run_id`만 반환하며 512바이트 이하다. 읽기는 revision을 올리거나 lease를 갱신하지 않는다. 전체 상태는 기존 newline JSON/20바이트 알림 조각으로 전달한다. 앱은 compact 읽기가 선택 필드를 지우지 않게 병합하고, 같은 revision의 전체 알림으로 보충한다. 3개 기록을 포함한 전체 프레임이 앱의 4096바이트 상한 안에 있는지 검사했다. 실제 세 iPhone/BlueZ MTU·알림 동작은 실물 확인 대상이다.

## 놀이·촬영 프리셋과 준비할 음성

| 식별자 | 구현된 순서 |
|---|---|
| `dance` | 현재 배포된 제한 춤 그대로. 새 CUVO Groove 미리보기로 교체하지 않음 |
| `name_call` | 이름 부르기/오른팔·고개 인사 → 2초 반응 대기 → 놀이 초대/왼팔 → 복귀/깜박임 |
| `yogicok` | 눈 찾기 음성/깜박임 → 3초 대기 → 손 찾기 음성/팔 → 3초 대기 → 복귀 |
| `01` | 승인된 눈 열기/깜박임 |
| `02` | 고개와 정수리 반대 방향 75/105도 → 가운데 → 승인된 깜박임 |
| `03` | 오른손 인사 → 복귀 |
| `04` | 앱 S04 이름 확인 → 제안 → 시작 명령에서만 이름 부르기+요기콕 |
| `05_06` | 이름 부르기+요기콕 → 손 인사 → 복귀 |
| `09` | 작별 음성/손 인사 → 복귀 → 눈 감기. 자동 대기 눈 재시작 억제 |

07/08은 앱 기록·선택 화면, 10은 편집용 로고이므로 로봇 명령이 없다. 씬 02의 별도 ‘미소’ 눈 디자인은 승인된 렌더러에 없어 구현하지 않았다. 현재 승인된 깜박임을 사용하며 실제 촬영 콘티와 표정을 확인해야 한다.

현재 `01_name_call.wav`의 확인된 **지우** 이름만 준비돼 있다. 다른 입력 이름을 지우 음성으로 대체하지 않고 `voice_ready=false`로 알린다. 임의 이름 TTS 제공자는 아직 연결되지 않았다. 다음 PCM WAV를 준비하면 프리셋 검사가 통과한다. 파일이 없거나 손상됐으면 모션 시작 전 거부한다.

- `raspberry_pi/robot_demo/audio/cuvo_where_eyes.wav`: 요기콕 눈 찾기 확정 대사
- `raspberry_pi/robot_demo/audio/cuvo_show_hands.wav`: 요기콕 손 찾기 확정 대사
- `raspberry_pi/robot_demo/audio/cuvo_see_you.wav`: ‘다음에 또 만나!’

새 프리셋의 팔/고개는 기존 제한 춤 범위 안에서 편성했고 정수리는 75…105도 범위다. `--confirm-5v-and-clear`만으로 새 씬을 허용하지 않는다. `--confirm-exhibit-scenes-and-clear`를 별도로 요구한다. 이 플래그가 프로필의 `verified=false`를 바꾸지는 않는다.

## 실제 녹화와 전달

기존 저장소에는 실제 촬영 저장 경로가 없었다. 새 `RecordManager`는 **기본 비활성**이며 예시를 방금 촬영한 기록으로 만들지 않는다. 명시적으로 켜면 `rpicam-vid` 또는 `libcamera-vid`의 libav MP4, 1280×720/30fps/최대 60초를 사용한다. 마이크/오디오 녹음은 포함하지 않는다. 카메라 프로세스 시작 실패는 녹화 오류로 알리며 로봇 모션 완료와 녹화 성공을 구분한다.

모션 STOP/장치 정리 후 ffprobe로 영상 스트림·실제 길이를 확인하고 ffmpeg로 320px 썸네일을 만든다. 둘 다 성공한 UUID 폴더만 원자적으로 게시한다. 캡처/코덱/카메라 권한이 실제로 작동하는지는 실물 확인이 필요하다. `recording_supported`는 설정/실행 파일 존재 확인이며 카메라 검증 완료 인증이 아니다.

기본 보관 위치는 Git 밖 `~/.local/state/cuvo/records`, 폴더 0700/파일 0600이다. 중단·저장 실패의 미완성 파일은 목록에 나타나지 않는다. 기기 고장으로 남은 `.pending-*` 폴더도 게시되지 않는다. 운영자가 보관 기간과 남은 용량을 관리해야 한다.

메타데이터: `id`, `run_id`, `play_id`, `created_at`(ISO8601), `duration_seconds`, `video:"video.mp4"`, `thumbnail:"thumbnail.jpg"`, `source:"robot"`, `state:"ready"`. 생성 시각·길이는 실제 촬영에서 가져오며 아동 이름은 저장하지 않는다.

별도 opt-in LAN 서버는 GET `/records`, `/records/{UUID}/video`, `/records/{UUID}/thumbnail`만 허용한다. 쿼리/임의 파일 경로/Range 요청을 지원하지 않는다. 앱은 인증 다운로드 후 로컬 파일을 재생한다. HTTP는 인증만 제공하므로 신뢰하는 전시 LAN에서 사용한다. BLE에 bearer 토큰을 공개하지 않는다.

`media:{base_url,challenge,auth:"hmac-sha256-v1",server_time}`에서 `server_time`은 매 전체 상태 생성 시 갱신한다. Pi의 오프라인 시계 차이를 앱이 보정한다. 서명 키는 `SHA256(등록 token의 ASCII)` 바이트이고 서명 메시지는 다음 UTF-8 줄들을 newline으로 연결한다(마지막 newline 없음).

```text
CUVO-MEDIA-V1
{challenge}
{client_id}
{integer_timestamp}
{UUID_nonce}
GET
{exact_path}
```

헤더는 `X-CUVO-Client`, `X-CUVO-Time`, `X-CUVO-Nonce`, `X-CUVO-Signature`(HMAC-SHA256 hex)다. 현재 등록 client, 일정 시간 범위, 재사용되지 않은 nonce, 경로를 검증한다. 토큰 자체를 HTTP로 보내지 않는다. 상세한 네트워크/기기 접근은 앱과 Pi가 같은 LAN에 있는 상태에서 확인한다.

## 운영 설정과 전환

다음은 **향후 실물 전환용 예시**이며 이번 작업에서 실행하지 않았다. 기존 OLED/serial 의존성이 설치된 Pi Python 환경을 사용하고 기존 BLE 서비스를 먼저 정상 정지하여 중복 실행을 방지한다. 프로필/CAPS, 전원, 움직일 공간, 오디오 출력, 이름/요기콕 음성을 먼저 확인한다.

```sh
python3 raspberry_pi/robot_demo/cuvo_ble.py \
  --confirm-5v-and-clear \
  --confirm-exhibit-scenes-and-clear \
  --home-on-start-stop
```

실제 카메라와 전시 LAN을 검증한 후 필요할 때만 아래 옵션을 추가한다. 호스트명/IP와 포트는 운영자가 정한다.

```text
--enable-recording --media-bind 0.0.0.0 --media-port 8765
--media-base-url http://cuvo.local:8765
```

전원 버튼은 `--allow-poweroff`를 추가하고 같은 실행 사용자의 logind `CanPowerOff`가 `yes`일 때만 노출한다. 권한 파일을 자동 수정하거나 강제 종료하지 않는다. 요청 후 STOP → 기존 정상 종료 원점 정리(해당 옵션 사용 시) → BLE/미디어 정리 → `systemctl --no-ask-password poweroff` 순서다. 실제 OS 거부는 오류 로그로 남기며, 버튼 ACK가 전원 꺼짐 확인은 아니다. 다시 사용하려면 앱 안내대로 콘센트를 뽑았다가 꽂는다.

## 검증

`python3 -m unittest discover -s tests -t .`와 `bash scripts/check_python.sh`로 검사한다. 가짜 하드웨어에서 명령 인증/중복, 각 프리셋 전체 실행과 매 단계 중단, 기존 프로필 불변, 종료 우선순위, 볼륨 비동기 ACK, 녹화 실패/게시, 서명/재사용/경로 제한, worker 종료 경합, BLE 크기를 검사한다. ffprobe/ffmpeg는 임시 합성 클립으로만 확인했다. 이는 실제 로봇 모션·Pi 카메라·iPhone 설치/전송 테스트를 대신하지 않는다.

이번 로컬 결과: 전체 Python 162개 통과, 문법 검사 통과. CAD 선택 의존성도 이 검사 환경에는 있어 건너뛴 검사는 없다.

구현 참고: [Raspberry Pi camera](https://www.raspberrypi.com/documentation/computers/camera_software.html), [wpctl](https://pipewire.pages.freedesktop.org/wireplumber/man/wpctl.html), [ffprobe](https://ffmpeg.org/ffprobe.html), [ffmpeg](https://ffmpeg.org/ffmpeg.html).
