# AGENTS.md

이 저장소에서 작업할 때는 아래 안전 규칙을 따른다.

* Raspberry Pi 설정 변경과 Arduino 펌웨어 변경을 반드시 구분한다.
* Raspberry Pi 접속 주소는 `hyunwoo@192.168.0.39`이다.
* SSH 개인키, 비밀번호, 토큰, `.env`, 로그 파일은 Git에 포함하지 않는다.
* `config.py`의 목표 각도와 시간 변경은 Python 검사 후 Raspberry Pi 배포와 프로그램 재시작까지 진행할 수 있다.
* `servo_controller.ino`를 수정한 경우 Arduino 컴파일까지만 자동으로 진행한다.
* Arduino Mega에 실제 펌웨어를 업로드하기 전에는 반드시 사용자에게 명시적인 승인을 요청한다.
* 사용자가 `Arduino 업로드 승인`이라고 명확하게 말한 경우에만 Arduino 업로드를 실행한다.
* 서보 안전 범위를 넓힐 때는 실제 기구물 충돌과 과부하 가능성을 먼저 경고한다.
* 한 번의 변경으로 서보 안전 범위를 5도보다 크게 넓히지 않는다.
* `SERVO_MIN_PULSE_US`, `SERVO_MAX_PULSE_US`는 명시적인 승인 없이 변경하지 않는다.
* 실제 서보를 움직이는 테스트는 한 번에 큰 각도를 사용하지 않는다.
* Raspberry Pi에 배포한 뒤에는 실행 상태와 최근 로그를 확인한다.
* 스크립트 안에 SSH 개인키 파일 내용이나 비밀번호를 기록하지 않는다.
* SSH 접속에는 `~/.ssh/robotpi_ed25519` 경로만 참조한다.
