#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <string.h>
#include <stdlib.h>

/*
  Raspberry Pi 4 + Arduino Mega 2560 + PCA9685
  1차 심사 워킹 프로토타입용 서보 제어 코드

  PCA9685 Channel 0: 고개 SG92R
  PCA9685 Channel 1: 로봇 기준 오른팔 MG996R

  초기 목적:
  - Raspberry Pi 연결 전 Arduino IDE 시리얼 모니터에서 단독 시험
  - 서보혼을 분리한 상태로 중앙값 맞추기
  - 실제 기구물 조립 후 안전 각도 캘리브레이션
  - 지정 시간 동안 부드럽게 이동
*/

// ============================================================
// 1. 사용자가 조정할 설정값
// ============================================================

// PCA9685 기본 I2C 주소
// Adafruit 라이브러리 내부 매크로와 충돌하지 않도록
// 별도의 이름을 사용한다.
const uint8_t PCA9685_BOARD_ADDRESS = 0x40;

// PCA9685 채널
const uint8_t HEAD_CHANNEL = 0;
const uint8_t ARM_CHANNEL  = 1;

// 일반적인 아날로그 서보 구동 주파수
const float SERVO_FREQUENCY_HZ = 50.0f;

// 초기 캘리브레이션용 보수적인 펄스 폭 범위
// 기구물 테스트 후 필요할 때만 조금씩 넓힐 것
const uint16_t SERVO_MIN_PULSE_US = 1000;
const uint16_t SERVO_MAX_PULSE_US = 2000;

// 처음에는 좁은 안전 범위만 허용
// 기구물 간섭이 없음을 확인한 후 5도씩 조금씩 넓힐 것
const int HEAD_SAFE_MIN_DEG = 0;
const int HEAD_SAFE_MAX_DEG = 180;

const int ARM_SAFE_MIN_DEG = 60;
const int ARM_SAFE_MAX_DEG = 120;

// 서보혼을 장착하기 전 중앙 정렬 기준값
const int CENTER_DEG = 90;

// PWM 갱신 간격
const unsigned long UPDATE_INTERVAL_MS = 20;

// USB Serial 통신 속도
const unsigned long SERIAL_BAUDRATE = 115200;

// 입력 명령 최대 길이
const size_t LINE_BUFFER_SIZE = 96;


// ============================================================
// 2. 내부 상태
// ============================================================

Adafruit_PWMServoDriver pwm(PCA9685_BOARD_ADDRESS);

struct ServoMotion {
  uint8_t channel;

  int currentDeg;
  int startDeg;
  int targetDeg;

  unsigned long startTimeMs;
  unsigned long durationMs;
  unsigned long lastUpdateMs;

  bool enabled;
  bool moving;
};

ServoMotion headServo = {
  HEAD_CHANNEL,
  CENTER_DEG,
  CENTER_DEG,
  CENTER_DEG,
  0,
  0,
  0,
  false,
  false
};

ServoMotion armServo = {
  ARM_CHANNEL,
  CENTER_DEG,
  CENTER_DEG,
  CENTER_DEG,
  0,
  0,
  0,
  false,
  false
};

enum class PendingCommand {
  NONE,
  MOVE_HEAD,
  MOVE_ARM,
  MOVE_BOTH,
  CENTER
};

PendingCommand pendingCommand = PendingCommand::NONE;

char lineBuffer[LINE_BUFFER_SIZE];
size_t lineLength = 0;


// ============================================================
// 3. PWM 변환 및 출력 함수
// ============================================================

uint16_t microsecondsToTicks(uint16_t pulseUs) {
  const float periodUs = 1000000.0f / SERVO_FREQUENCY_HZ;
  const float ticks = (pulseUs * 4096.0f) / periodUs;

  return static_cast<uint16_t>(ticks + 0.5f);
}

uint16_t angleToTicks(int angleDeg) {
  angleDeg = constrain(angleDeg, 0, 180);

  const long pulseUs = map(
    angleDeg,
    0,
    180,
    SERVO_MIN_PULSE_US,
    SERVO_MAX_PULSE_US
  );

  return microsecondsToTicks(static_cast<uint16_t>(pulseUs));
}

void writeServoAngle(ServoMotion &servo, int angleDeg) {
  const uint16_t ticks = angleToTicks(angleDeg);

  pwm.setPWM(servo.channel, 0, ticks);

  servo.currentDeg = angleDeg;
  servo.enabled = true;
}

void disableServo(ServoMotion &servo) {
  // 해당 채널의 PWM 출력을 완전히 끈다.
  pwm.setPin(servo.channel, 0);

  servo.enabled = false;
  servo.moving = false;
}


// ============================================================
// 4. 안전 범위 검사
// ============================================================

bool isHeadAngleSafe(int angleDeg) {
  return angleDeg >= HEAD_SAFE_MIN_DEG &&
         angleDeg <= HEAD_SAFE_MAX_DEG;
}

bool isArmAngleSafe(int angleDeg) {
  return angleDeg >= ARM_SAFE_MIN_DEG &&
         angleDeg <= ARM_SAFE_MAX_DEG;
}

bool isBusy() {
  return headServo.moving ||
         armServo.moving ||
         pendingCommand != PendingCommand::NONE;
}


// ============================================================
// 5. 부드러운 이동
// ============================================================

void startMotion(
  ServoMotion &servo,
  int targetDeg,
  unsigned long durationMs
) {
  /*
    출력이 꺼져 있었으면 현재 저장된 각도로 PWM을 활성화한다.
    처음 실행 시 currentDeg는 CENTER_DEG인 90도로 설정되어 있다.
  */
  if (!servo.enabled) {
    writeServoAngle(servo, servo.currentDeg);
  }

  servo.startDeg = servo.currentDeg;
  servo.targetDeg = targetDeg;
  servo.startTimeMs = millis();
  servo.durationMs = max(durationMs, 1UL);
  servo.lastUpdateMs = 0;
  servo.moving = true;
}

void updateMotion(ServoMotion &servo) {
  if (!servo.moving) {
    return;
  }

  const unsigned long now = millis();
  const unsigned long elapsed = now - servo.startTimeMs;

  if (elapsed >= servo.durationMs) {
    writeServoAngle(servo, servo.targetDeg);
    servo.moving = false;
    return;
  }

  if (now - servo.lastUpdateMs < UPDATE_INTERVAL_MS) {
    return;
  }

  servo.lastUpdateMs = now;

  const float progress =
    static_cast<float>(elapsed) /
    static_cast<float>(servo.durationMs);

  const float interpolated =
    servo.startDeg +
    (servo.targetDeg - servo.startDeg) * progress;

  const int nextAngle =
    static_cast<int>(
      interpolated + (interpolated >= 0 ? 0.5f : -0.5f)
    );

  if (nextAngle != servo.currentDeg) {
    writeServoAngle(servo, nextAngle);
  }
}

void reportCompletionIfNeeded() {
  switch (pendingCommand) {
    case PendingCommand::NONE:
      return;

    case PendingCommand::MOVE_HEAD:
      if (!headServo.moving) {
        Serial.println("DONE,MOVE_HEAD");
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::MOVE_ARM:
      if (!armServo.moving) {
        Serial.println("DONE,MOVE_ARM");
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::MOVE_BOTH:
      if (!headServo.moving && !armServo.moving) {
        Serial.println("DONE,MOVE_BOTH");
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::CENTER:
      if (!headServo.moving && !armServo.moving) {
        Serial.println("DONE,CENTER");
        pendingCommand = PendingCommand::NONE;
      }
      return;
  }
}


// ============================================================
// 6. 명령 파싱 보조 함수
// ============================================================

bool parseLong(const char *text, long &value) {
  if (text == nullptr || *text == '\0') {
    return false;
  }

  char *endPointer = nullptr;
  value = strtol(text, &endPointer, 10);

  return endPointer != text && *endPointer == '\0';
}

bool hasUnexpectedExtraToken() {
  return strtok(nullptr, ",") != nullptr;
}

void printStatus() {
  Serial.print("STATUS,HEAD,");
  Serial.print(headServo.currentDeg);
  Serial.print(",");
  Serial.print(headServo.enabled ? "ENABLED" : "DISABLED");
  Serial.print(",");
  Serial.print(headServo.moving ? "MOVING" : "IDLE");

  Serial.print(",ARM,");
  Serial.print(armServo.currentDeg);
  Serial.print(",");
  Serial.print(armServo.enabled ? "ENABLED" : "DISABLED");
  Serial.print(",");
  Serial.println(armServo.moving ? "MOVING" : "IDLE");
}

void printHelp() {
  Serial.println("COMMANDS:");
  Serial.println("  PING");
  Serial.println("  STATUS");
  Serial.println("  HELP");
  Serial.println("  CENTER,<duration_ms>");
  Serial.println("  MOVE_HEAD,<angle_deg>,<duration_ms>");
  Serial.println("  MOVE_ARM,<angle_deg>,<duration_ms>");
  Serial.println(
    "  MOVE_BOTH,<head_angle_deg>,<arm_angle_deg>,<duration_ms>"
  );
  Serial.println("  STOP");
  Serial.println("  DISABLE");
}


// ============================================================
// 7. 명령 처리
// ============================================================

void handleCommand(char *line) {
  char *command = strtok(line, ",");

  if (command == nullptr) {
    return;
  }

  // -----------------------------
  // PING
  // -----------------------------
  if (strcmp(command, "PING") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,PING,TOO_MANY_ARGUMENTS");
      return;
    }

    Serial.println("ACK,PING");
    return;
  }

  // -----------------------------
  // STATUS
  // -----------------------------
  if (strcmp(command, "STATUS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,STATUS,TOO_MANY_ARGUMENTS");
      return;
    }

    printStatus();
    return;
  }

  // -----------------------------
  // HELP
  // -----------------------------
  if (strcmp(command, "HELP") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,HELP,TOO_MANY_ARGUMENTS");
      return;
    }

    printHelp();
    return;
  }

  // -----------------------------
  // STOP
  // 현재 위치에서 이동만 중지하고 PWM은 유지
  // -----------------------------
  if (strcmp(command, "STOP") == 0) {
    headServo.moving = false;
    armServo.moving = false;
    pendingCommand = PendingCommand::NONE;

    Serial.println("ACK,STOP");
    return;
  }

  // -----------------------------
  // DISABLE
  // PWM 출력 OFF
  // -----------------------------
  if (strcmp(command, "DISABLE") == 0) {
    disableServo(headServo);
    disableServo(armServo);
    pendingCommand = PendingCommand::NONE;

    Serial.println("ACK,DISABLE");
    return;
  }

  // 새로운 이동 명령은 기존 이동이 끝난 후에만 허용
  if (isBusy()) {
    Serial.println("ERR,BUSY");
    return;
  }

  // -----------------------------
  // CENTER,<duration_ms>
  // -----------------------------
  if (strcmp(command, "CENTER") == 0) {
    char *durationText = strtok(nullptr, ",");

    long durationMs = 0;

    if (!parseLong(durationText, durationMs) ||
        durationMs <= 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println("ERR,CENTER,USE:CENTER,<duration_ms>");
      return;
    }

    startMotion(headServo, CENTER_DEG, durationMs);
    startMotion(armServo, CENTER_DEG, durationMs);

    pendingCommand = PendingCommand::CENTER;

    Serial.println("ACK,CENTER");
    return;
  }

  // -----------------------------
  // MOVE_HEAD,<angle_deg>,<duration_ms>
  // -----------------------------
  if (strcmp(command, "MOVE_HEAD") == 0) {
    char *angleText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");

    long angleDeg = 0;
    long durationMs = 0;

    if (!parseLong(angleText, angleDeg) ||
        !parseLong(durationText, durationMs) ||
        durationMs <= 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println(
        "ERR,MOVE_HEAD,USE:MOVE_HEAD,<angle_deg>,<duration_ms>"
      );
      return;
    }

    if (!isHeadAngleSafe(angleDeg)) {
      Serial.print("ERR,MOVE_HEAD,SAFE_RANGE,");
      Serial.print(HEAD_SAFE_MIN_DEG);
      Serial.print(",");
      Serial.println(HEAD_SAFE_MAX_DEG);
      return;
    }

    startMotion(
      headServo,
      static_cast<int>(angleDeg),
      static_cast<unsigned long>(durationMs)
    );

    pendingCommand = PendingCommand::MOVE_HEAD;

    Serial.println("ACK,MOVE_HEAD");
    return;
  }

  // -----------------------------
  // MOVE_ARM,<angle_deg>,<duration_ms>
  // -----------------------------
  if (strcmp(command, "MOVE_ARM") == 0) {
    char *angleText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");

    long angleDeg = 0;
    long durationMs = 0;

    if (!parseLong(angleText, angleDeg) ||
        !parseLong(durationText, durationMs) ||
        durationMs <= 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println(
        "ERR,MOVE_ARM,USE:MOVE_ARM,<angle_deg>,<duration_ms>"
      );
      return;
    }

    if (!isArmAngleSafe(angleDeg)) {
      Serial.print("ERR,MOVE_ARM,SAFE_RANGE,");
      Serial.print(ARM_SAFE_MIN_DEG);
      Serial.print(",");
      Serial.println(ARM_SAFE_MAX_DEG);
      return;
    }

    startMotion(
      armServo,
      static_cast<int>(angleDeg),
      static_cast<unsigned long>(durationMs)
    );

    pendingCommand = PendingCommand::MOVE_ARM;

    Serial.println("ACK,MOVE_ARM");
    return;
  }

  // -----------------------------
  // MOVE_BOTH,<head_angle_deg>,<arm_angle_deg>,<duration_ms>
  // -----------------------------
  if (strcmp(command, "MOVE_BOTH") == 0) {
    char *headAngleText = strtok(nullptr, ",");
    char *armAngleText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");

    long headAngleDeg = 0;
    long armAngleDeg = 0;
    long durationMs = 0;

    if (!parseLong(headAngleText, headAngleDeg) ||
        !parseLong(armAngleText, armAngleDeg) ||
        !parseLong(durationText, durationMs) ||
        durationMs <= 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println(
        "ERR,MOVE_BOTH,USE:MOVE_BOTH,"
        "<head_angle_deg>,<arm_angle_deg>,<duration_ms>"
      );
      return;
    }

    if (!isHeadAngleSafe(headAngleDeg)) {
      Serial.print("ERR,MOVE_BOTH,HEAD_SAFE_RANGE,");
      Serial.print(HEAD_SAFE_MIN_DEG);
      Serial.print(",");
      Serial.println(HEAD_SAFE_MAX_DEG);
      return;
    }

    if (!isArmAngleSafe(armAngleDeg)) {
      Serial.print("ERR,MOVE_BOTH,ARM_SAFE_RANGE,");
      Serial.print(ARM_SAFE_MIN_DEG);
      Serial.print(",");
      Serial.println(ARM_SAFE_MAX_DEG);
      return;
    }

    startMotion(
      headServo,
      static_cast<int>(headAngleDeg),
      static_cast<unsigned long>(durationMs)
    );

    startMotion(
      armServo,
      static_cast<int>(armAngleDeg),
      static_cast<unsigned long>(durationMs)
    );

    pendingCommand = PendingCommand::MOVE_BOTH;

    Serial.println("ACK,MOVE_BOTH");
    return;
  }

  Serial.print("ERR,UNKNOWN_COMMAND,");
  Serial.println(command);
}


// ============================================================
// 8. Serial 입력 처리
// ============================================================

void readSerialInput() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());

    // CR, LF 또는 CRLF 모두 허용
    if (incoming == '\r' || incoming == '\n') {
      if (lineLength > 0) {
        lineBuffer[lineLength] = '\0';

        handleCommand(lineBuffer);

        lineLength = 0;
      }

      continue;
    }

    if (lineLength >= LINE_BUFFER_SIZE - 1) {
      lineLength = 0;

      Serial.println("ERR,INPUT_TOO_LONG");

      continue;
    }

    lineBuffer[lineLength] = incoming;
    lineLength++;
  }
}


// ============================================================
// 9. Arduino 기본 실행 함수
// ============================================================

void setup() {
  Serial.begin(SERIAL_BAUDRATE);

  Wire.begin();

  if (!pwm.begin()) {
    Serial.println("ERR,PCA9685_NOT_FOUND");

    while (true) {
      delay(1000);
    }
  }

  pwm.setPWMFreq(SERVO_FREQUENCY_HZ);

  // 부팅 직후에는 서보를 움직이지 않는다.
  // 두 채널의 PWM 출력을 끈 상태로 시작한다.
  pwm.setPin(HEAD_CHANNEL, 0);
  pwm.setPin(ARM_CHANNEL, 0);

  Serial.println("READY,SERVO_CONTROLLER");
  Serial.println("SAFE_MODE,OUTPUTS_DISABLED");
  Serial.println("TYPE,HELP");
}

void loop() {
  readSerialInput();

  updateMotion(headServo);
  updateMotion(armServo);

  reportCompletionIfNeeded();
}