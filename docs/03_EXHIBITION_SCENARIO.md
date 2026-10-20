# 03 Exhibition Scenario

## 관람자 앱 체험 계획

2026-10-05 사용자는 관람자가 휴대폰 앱을 직접 조작하고 기록 화면은 예시 기록을 쓰는 전시를 선택했다. [17_EXHIBITION_AND_APP_PLAN.md](17_EXHIBITION_AND_APP_PLAN.md)에 로봇의 약 15초 놀이 제안, 홈 / 기록 / 기기, 중단과 연결 실패 처리, 운영자 화면을 정리했다.

새 시나리오는 계획 단계다. 현재 3채널 코드와 약 6초 기존 시연을 새 6축 시연으로 오해하지 않는다. 로봇은 앱 없이도 물리 버튼으로 독립 작동하는 목표를 유지하고, 앱 통신용 로컬망과 인터넷 필요 여부를 구분한다. 실제 관람자 녹화/저장은 이번 체험 범위가 아니다.

## 전시 환경

현재 프로젝트 맥락:

* 산업디자인 캡스톤디자인 1차 심사용 워킹 프로토타입
* 전시 중에는 네트워크 없이 독립 작동해야 한다.
* 전원을 켜면 Raspberry Pi가 자동 부팅되고 프로그램이 실행되어 버튼 입력을 기다리는 구성이 목표다.
* 철수 시에는 Raspberry Pi 안전 종료 후 전체 전원을 끈다.

## 관람자 시연 흐름

1. 전시자가 전원을 연결한다.
2. Raspberry Pi가 부팅된다.
3. 로봇 프로그램이 실행되고 버튼 입력을 기다린다.
4. 버튼을 누른다.
5. 로봇이 고개 회전과 기존 오른팔 상승을 함께 시작하며 `01_name_call.wav`를 재생한다.
6. 이동과 첫 음성 완료 후 설정된 간격을 기다린다.
7. `02_lets_play.wav`가 재생된다.
8. 짧게 유지한다.
9. 고개와 오른팔이 초기 자세로 복귀한다.
10. 다음 버튼 입력을 기다린다.

`main.py` 주석과 코드 기준으로 시퀀스 실행 중 추가 버튼 입력은 무시된다.

## 자동 실행 관련 현재 파일

확인된 파일:

* `raspberry_pi/robot_demo/run_robot_demo.sh`
* `raspberry_pi/robot_demo/systemd/robot-demo.service.example`
* `scripts/setup_pi_autostart.sh`

`scripts/setup_pi_autostart.sh`는 Raspberry Pi OS Desktop Autologin 이후 사용자 자동 실행 구성을 준비하는 스크립트다. 이 스크립트는 `pw-play`와 Arduino USB Serial 장치가 준비될 시간을 고려한다.

## 미확정

* 실제 전시 현장에서 systemd 방식과 Desktop Autostart 방식 중 무엇을 최종 사용할지
* 자동 실행이 현장 Raspberry Pi OS 설정에서 검증되었는지
* 전시 부스의 전원 투입/철수 SOP
* 관람자가 직접 버튼을 누르는지, 전시자가 누르는지
