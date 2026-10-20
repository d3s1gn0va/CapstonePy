#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <string.h>
#include <stdlib.h>

/*
  Raspberry Pi 4 + Arduino Mega 2560 + PCA9685
  1차 심사 워킹 프로토타입용 서보 제어 코드

  PCA9685 Channel 0: 고개 SG92R
  PCA9685 Channel 1: 로봇 기준 오른쪽 어깨 X축 SG90 (교체)
  PCA9685 Channel 2: 카메라 좌우 회전 서보
  PCA9685 Channel 3: 오른쪽 어깨 Y축 SG92R
  PCA9685 Channel 4/5: 왼쪽 어깨 X/Y축 SG92R

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
const uint8_t CAMERA_CHANNEL = 2;

// User-specified command angles, 2026-10-13; Pi verification gates remain closed.
// Each channel has its own target and interpolation direction.
const int GROUP_SAFE_MIN_DEG[6] = {45, 0, 45, 0, 0, 135};
const int GROUP_SAFE_MAX_DEG[6] = {135, 180, 135, 45, 180, 180};
const int GROUP_NEUTRAL_DEG[6] = {90, 45, 90, 0, 135, 180};

// 일반적인 아날로그 서보 구동 주파수
const float SERVO_FREQUENCY_HZ = 50.0f;

// 초기 캘리브레이션용 보수적인 펄스 폭 범위
// 기구물 테스트 후 필요할 때만 조금씩 넓힐 것
const uint16_t SERVO_MIN_PULSE_US = 1000;
const uint16_t SERVO_MAX_PULSE_US = 2000;

// 처음에는 좁은 안전 범위만 허용
// 기구물 간섭이 없음을 확인한 후 5도씩 조금씩 넓힐 것
const int HEAD_SAFE_MIN_DEG = 45;
const int HEAD_SAFE_MAX_DEG = 135;

const int ARM_SAFE_MIN_DEG = 0;
const int ARM_SAFE_MAX_DEG = 180;

const int CAMERA_SAFE_MIN_DEG = 45;
const int CAMERA_SAFE_MAX_DEG = 135;

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

ServoMotion cameraServo = {
  CAMERA_CHANNEL,
  CENTER_DEG,
  CENTER_DEG,
  CENTER_DEG,
  0,
  0,
  0,
  false,
  false
};

ServoMotion rightYServo = {3, CENTER_DEG, CENTER_DEG, CENTER_DEG, 0, 0, 0, false, false};
ServoMotion leftXServo = {4, CENTER_DEG, CENTER_DEG, CENTER_DEG, 0, 0, 0, false, false};
ServoMotion leftYServo = {5, CENTER_DEG, CENTER_DEG, CENTER_DEG, 0, 0, 0, false, false};
ServoMotion *groupServos[6] = {&headServo, &armServo, &cameraServo,
                              &rightYServo, &leftXServo, &leftYServo};

enum class PendingCommand {
  NONE,
  MOVE_HEAD,
  MOVE_ARM,
  MOVE_CAMERA,
  MOVE_BOTH,
  MOVE_GROUP,
  TEST_CENTER_90,
  TEST_ZERO_0,
  TEST_HOME_POSE,
  TEST_ARM_X_PAIR,
  TEST_ARM_X_HOLD,
  TEST_ARM_Y_PAIR,
  TEST_LEFT_Y_PAIR,
  CENTER
};

PendingCommand pendingCommand = PendingCommand::NONE;
bool centerTestUsed[6] = {false, false, false, false, false, false};
bool zeroTestUsed[6] = {false, false, false, false, false, false};
bool homeTestUsed[3] = {false, false, false};
bool rightYTestUsed = false;
bool armXPairTestUsed[2] = {false, false};
bool armXHoldTestUsed = false;
uint8_t armYTestStage = 0;
uint8_t leftYTestStage = 0;
uint8_t centerTestChannel = 0;

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

bool isCameraAngleSafe(int angleDeg) {
  return angleDeg >= CAMERA_SAFE_MIN_DEG &&
         angleDeg <= CAMERA_SAFE_MAX_DEG;
}

bool isBusy() {
  return headServo.moving ||
         armServo.moving ||
         cameraServo.moving ||
         rightYServo.moving ||
         leftXServo.moving ||
         leftYServo.moving ||
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

    case PendingCommand::MOVE_CAMERA:
      if (!cameraServo.moving) {
        Serial.println("DONE,MOVE_CAMERA");
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

    case PendingCommand::MOVE_GROUP:
      for (uint8_t channel = 0; channel < 6; channel++) {
        if (groupServos[channel]->moving) {
          return;
        }
      }
      Serial.println("DONE,MOVE_GROUP");
      pendingCommand = PendingCommand::NONE;
      return;

    case PendingCommand::TEST_LEFT_Y_PAIR:
      if (!leftYServo.moving) {
        Serial.print("DONE,TEST_LEFT_Y_PAIR,");
        Serial.println(leftYServo.targetDeg);
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::TEST_ARM_Y_PAIR:
      if (!rightYServo.moving && !leftYServo.moving) {
        Serial.print("DONE,TEST_ARM_Y_PAIR,");
        Serial.println(rightYServo.targetDeg);
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::TEST_ARM_X_HOLD:
      if (!armServo.moving && !leftXServo.moving) {
        Serial.println("DONE,TEST_ARM_X_HOLD,1:0,4:180");
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::TEST_ARM_X_PAIR:
      if (!armServo.moving && !leftXServo.moving) {
        Serial.print("DONE,TEST_ARM_X_PAIR,");
        Serial.println(armServo.targetDeg);
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::TEST_HOME_POSE:
      if (!groupServos[centerTestChannel]->moving) {
        Serial.print("DONE,TEST_HOME_POSE,");
        Serial.print(centerTestChannel);
        Serial.print(',');
        Serial.println(GROUP_NEUTRAL_DEG[centerTestChannel]);
        pendingCommand = PendingCommand::NONE;
      }
      return;

    case PendingCommand::TEST_CENTER_90:
    case PendingCommand::TEST_ZERO_0:
      if (!groupServos[centerTestChannel]->moving) {
        const bool zeroTest = pendingCommand == PendingCommand::TEST_ZERO_0;
        Serial.print(zeroTest ? "DONE,TEST_ZERO_0," : "DONE,TEST_CENTER_90,");
        Serial.print(centerTestChannel);
        Serial.println(zeroTest ? ",0" : ",90");
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
  Serial.print(armServo.moving ? "MOVING" : "IDLE");

  Serial.print(",CAMERA,");
  Serial.print(cameraServo.currentDeg);
  Serial.print(",");
  Serial.print(cameraServo.enabled ? "ENABLED" : "DISABLED");
  Serial.print(",");
  Serial.println(cameraServo.moving ? "MOVING" : "IDLE");
}

void printHelp() {
  Serial.println("COMMANDS:");
  Serial.println("  PING");
  Serial.println("  STATUS");
  Serial.println("  CAPS");
  Serial.println("  STATUS_GROUP");
  Serial.println("  MOVE_GROUP,<duration_ms>,<channel>,<angle>[,<channel>,<angle>...]");
  Serial.println("  HELP");
  Serial.println("  CENTER,<duration_ms>");
  Serial.println("  MOVE_HEAD,<angle_deg>,<duration_ms>");
  Serial.println("  MOVE_ARM,<angle_deg>,<duration_ms>");
  Serial.println("  MOVE_CAMERA,<angle_deg>,<duration_ms>");
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
  const size_t inputLength = strlen(line);
  const bool emptyGroupField = strstr(line, ",,") != nullptr ||
                              (inputLength > 0 && line[inputLength - 1] == ',');
  char *command = strtok(line, ",");

  if (command == nullptr) {
    return;
  }

  // Historical endpoint experiments bypass the now-confirmed assembly limits.
  // Keep their source for reference, but never expose them in the current firmware.
  if (strncmp(command, "TEST_", 5) == 0) {
    Serial.println("ERR,CALIBRATION_TEST_DISABLED");
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

  if (strcmp(command, "CAPS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,CAPS,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.print("CAPS,MOVE_GROUP");
    for (uint8_t channel = 0; channel < 6; channel++) {
      Serial.print(',');
      Serial.print(channel);
      Serial.print(':');
      Serial.print(GROUP_SAFE_MIN_DEG[channel]);
      Serial.print(':');
      Serial.print(GROUP_SAFE_MAX_DEG[channel]);
      Serial.print(':');
      Serial.print(GROUP_NEUTRAL_DEG[channel]);
    }
    Serial.println();
    return;
  }

  if (strcmp(command, "TEST_CENTER_CAPS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_CENTER_CAPS,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.println("CAPS,TEST_CENTER_90,90,ONCE_PER_CHANNEL");
    return;
  }

  if (strcmp(command, "TEST_ZERO_CAPS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_ZERO_CAPS,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.println("CAPS,TEST_ZERO_0,0,ONCE_PER_CHANNEL");
    return;
  }

  if (strcmp(command, "TEST_HOME_CAPS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_HOME_CAPS,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.println("CAPS,TEST_HOME_POSE,0:45,1:180,2:45,FROM_CONFIRMED_ZERO");
    return;
  }

  if (strcmp(command, "TEST_RIGHT_Y_CAPS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_RIGHT_Y_CAPS,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.println("CAPS,TEST_RIGHT_Y_45,3:45,ONCE_PER_BOOT");
    return;
  }

  if (strcmp(command, "TEST_ARM_X_PAIR_CAPS") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_ARM_X_PAIR_CAPS,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.println("CAPS,TEST_ARM_X_PAIR,1:4,180_THEN_0,ONCE_PER_BOOT");
    return;
  }

  if (strcmp(command, "STATUS_GROUP") == 0) {
    if (hasUnexpectedExtraToken()) {
      Serial.println("ERR,STATUS_GROUP,TOO_MANY_ARGUMENTS");
      return;
    }
    Serial.print("STATUS_GROUP");
    for (uint8_t channel = 0; channel < 6; channel++) {
      ServoMotion &servo = *groupServos[channel];
      Serial.print(',');
      Serial.print(channel);
      Serial.print(':');
      Serial.print(servo.currentDeg);
      Serial.print(servo.enabled ? ":ENABLED:" : ":DISABLED:");
      Serial.print(servo.moving ? "MOVING" : "IDLE");
    }
    Serial.println();
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
    cameraServo.moving = false;
    rightYServo.moving = false;
    leftXServo.moving = false;
    leftYServo.moving = false;
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
    disableServo(cameraServo);
    disableServo(rightYServo);
    disableServo(leftXServo);
    disableServo(leftYServo);
    pendingCommand = PendingCommand::NONE;

    Serial.println("ACK,DISABLE");
    return;
  }

  // 새로운 이동 명령은 기존 이동이 끝난 후에만 허용
  if (isBusy()) {
    Serial.println("ERR,BUSY");
    return;
  }

  // User-requested left-only experiment, separate from unverified group limits.
  if (strcmp(command, "TEST_LEFT_Y_PAIR") == 0) {
    long angle;
    char *angleText = strtok(nullptr, ",");
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || !parseLong(angleText, angle) || (angle != 135 && angle != 180) ||
        confirmation == nullptr || strcmp(confirmation, "CONFIRM_FROM_LAST_ZERO") != 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_LEFT_Y_PAIR,INVALID_REQUEST");
      return;
    }
    if (leftYTestStage >= 2 || angle != (leftYTestStage == 0 ? 135 : 180)) {
      Serial.println("ERR,TEST_LEFT_Y_PAIR,SEQUENCE_REQUIRED");
      return;
    }
    if ((leftYTestStage == 0 && leftYServo.enabled && leftYServo.currentDeg != 0) ||
        (leftYTestStage == 1 && (!leftYServo.enabled || leftYServo.currentDeg != 135))) {
      Serial.println("ERR,TEST_LEFT_Y_PAIR,START_REQUIRED");
      return;
    }
    if (leftYTestStage == 0) {
      // Last completed command was zero; this is not measured shaft position.
      leftYServo.currentDeg = 0;
    }
    leftYTestStage++;
    startMotion(leftYServo, static_cast<int>(angle), angle == 135 ? 5000 : 3000);
    pendingCommand = PendingCommand::TEST_LEFT_Y_PAIR;
    Serial.print("ACK,TEST_LEFT_Y_PAIR,");
    Serial.println(angle);
    return;
  }

  // Explicit bounded Y experiment: initialize zero, then 45, then zero once.
  if (strcmp(command, "TEST_ARM_Y_PAIR") == 0) {
    long angle;
    char *angleText = strtok(nullptr, ",");
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || !parseLong(angleText, angle) || (angle != 0 && angle != 45) ||
        confirmation == nullptr || strcmp(confirmation, "CONFIRM_0_45_0") != 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_ARM_Y_PAIR,INVALID_REQUEST");
      return;
    }
    if (armYTestStage >= 3 || angle != (armYTestStage == 1 ? 45 : 0)) {
      Serial.println("ERR,TEST_ARM_Y_PAIR,SEQUENCE_REQUIRED");
      return;
    }
    if (armYTestStage == 0 && (rightYServo.enabled || leftYServo.enabled)) {
      Serial.println("ERR,TEST_ARM_Y_PAIR,FRESH_DISABLED_REQUIRED");
      return;
    }
    armYTestStage++;
    if (armYTestStage == 1) {
      // No feedback on startup; do not emit an unrequested guessed 90 first.
      writeServoAngle(rightYServo, 0);
      writeServoAngle(leftYServo, 0);
    }
    const unsigned long sharedStart = millis();
    startMotion(rightYServo, static_cast<int>(angle), 3000);
    startMotion(leftYServo, static_cast<int>(angle), 3000);
    rightYServo.startTimeMs = leftYServo.startTimeMs = sharedStart;
    pendingCommand = PendingCommand::TEST_ARM_Y_PAIR;
    Serial.print("ACK,TEST_ARM_Y_PAIR,");
    Serial.println(angle);
    return;
  }

  // Fixed hold from the last commanded zero, not measured position feedback.
  if (strcmp(command, "TEST_ARM_X_HOLD") == 0) {
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || confirmation == nullptr ||
        strcmp(confirmation, "CONFIRM_FROM_ZERO") != 0 || hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_ARM_X_HOLD,INVALID_REQUEST");
      return;
    }
    if (armXHoldTestUsed) {
      Serial.println("ERR,TEST_ARM_X_HOLD,ALREADY_USED");
      return;
    }
    if ((armServo.enabled && armServo.currentDeg != 0) ||
        (leftXServo.enabled && leftXServo.currentDeg != 0)) {
      Serial.println("ERR,TEST_ARM_X_HOLD,ZERO_REQUIRED");
      return;
    }
    armXHoldTestUsed = true;
    armServo.currentDeg = leftXServo.currentDeg = 0;
    const unsigned long sharedStart = millis();
    startMotion(armServo, 0, 5000);
    startMotion(leftXServo, 180, 5000);
    armServo.startTimeMs = leftXServo.startTimeMs = sharedStart;
    pendingCommand = PendingCommand::TEST_ARM_X_HOLD;
    Serial.println("ACK,TEST_ARM_X_HOLD,1:0,4:180");
    return;
  }

  // Explicit endpoint experiment only; do not unlock production shoulder limits.
  if (strcmp(command, "TEST_ARM_X_PAIR") == 0) {
    long angle, durationMs;
    char *angleText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || !parseLong(angleText, angle) || (angle != 0 && angle != 180) ||
        !parseLong(durationText, durationMs) || durationMs < 5000 || durationMs > 10000 ||
        confirmation == nullptr || strcmp(confirmation, "CONFIRM_ENDPOINTS") != 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_ARM_X_PAIR,INVALID_REQUEST");
      return;
    }
    const uint8_t index = angle == 180 ? 0 : 1;
    if (armXPairTestUsed[index]) {
      Serial.println("ERR,TEST_ARM_X_PAIR,ALREADY_USED");
      return;
    }
    if (angle == 0 && (!armXPairTestUsed[0] || !armServo.enabled || !leftXServo.enabled ||
                      armServo.currentDeg != 180 || leftXServo.currentDeg != 180)) {
      Serial.println("ERR,TEST_ARM_X_PAIR,FIRST_COMPLETE_180");
      return;
    }
    armXPairTestUsed[index] = true;
    const unsigned long sharedStart = millis();
    startMotion(armServo, static_cast<int>(angle), static_cast<unsigned long>(durationMs));
    startMotion(leftXServo, static_cast<int>(angle), static_cast<unsigned long>(durationMs));
    armServo.startTimeMs = leftXServo.startTimeMs = sharedStart;
    pendingCommand = PendingCommand::TEST_ARM_X_PAIR;
    Serial.print("ACK,TEST_ARM_X_PAIR,");
    Serial.println(angle);
    return;
  }

  // No position feedback: issue only the requested 45, not an assumed start pose.
  if (strcmp(command, "TEST_RIGHT_Y_45") == 0) {
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || confirmation == nullptr || strcmp(confirmation, "CONFIRM_45") != 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_RIGHT_Y_45,INVALID_REQUEST");
      return;
    }
    if (rightYTestUsed) {
      Serial.println("ERR,TEST_RIGHT_Y_45,ALREADY_USED");
      return;
    }
    rightYTestUsed = true;
    writeServoAngle(rightYServo, 45);
    Serial.println("ACK,TEST_RIGHT_Y_45,3,45");
    Serial.println("DONE,TEST_RIGHT_Y_45,3,45");
    return;
  }

  // One-shot calibration from the user's last zero test, not position feedback.
  if (strcmp(command, "TEST_HOME_POSE") == 0) {
    long channel, durationMs;
    char *channelText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || !parseLong(channelText, channel) || channel < 0 || channel > 2 ||
        !parseLong(durationText, durationMs) || durationMs < 5000 || durationMs > 10000 ||
        (channel == 1 && durationMs != 10000) || confirmation == nullptr ||
        strcmp(confirmation, "CONFIRM_FROM_0") != 0 || hasUnexpectedExtraToken()) {
      Serial.println("ERR,TEST_HOME_POSE,INVALID_REQUEST");
      return;
    }
    ServoMotion &servo = *groupServos[channel];
    if (homeTestUsed[channel] || servo.enabled) {
      Serial.println("ERR,TEST_HOME_POSE,FRESH_DISABLED_CHANNEL_REQUIRED");
      return;
    }
    homeTestUsed[channel] = true;
    centerTestChannel = static_cast<uint8_t>(channel);
    servo.currentDeg = 0;
    startMotion(servo, GROUP_NEUTRAL_DEG[channel], static_cast<unsigned long>(durationMs));
    pendingCommand = PendingCommand::TEST_HOME_POSE;
    Serial.print("ACK,TEST_HOME_POSE,");
    Serial.print(centerTestChannel);
    Serial.print(',');
    Serial.println(GROUP_NEUTRAL_DEG[channel]);
    return;
  }

  // Fixed-target experiments are separate from unverified production limits.
  if (strcmp(command, "TEST_CENTER_90") == 0 || strcmp(command, "TEST_ZERO_0") == 0) {
    const bool zeroTest = strcmp(command, "TEST_ZERO_0") == 0;
    const int target = zeroTest ? 0 : CENTER_DEG;
    bool *used = zeroTest ? zeroTestUsed : centerTestUsed;
    long channel, durationMs;
    char *channelText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");
    char *confirmation = strtok(nullptr, ",");
    if (emptyGroupField || !parseLong(channelText, channel) || channel < 0 || channel > 5 ||
        !parseLong(durationText, durationMs) || durationMs < 1000 || durationMs > 10000 ||
        confirmation == nullptr || strcmp(confirmation, zeroTest ? "CONFIRM_0" : "CONFIRM_90") != 0 ||
        hasUnexpectedExtraToken()) {
      Serial.print("ERR,");
      Serial.print(command);
      Serial.println(",INVALID_REQUEST");
      return;
    }
    if (used[channel]) {
      Serial.print("ERR,");
      Serial.print(command);
      Serial.println(",ALREADY_USED");
      return;
    }
    used[channel] = true;
    centerTestChannel = static_cast<uint8_t>(channel);
    startMotion(*groupServos[channel], target, static_cast<unsigned long>(durationMs));
    pendingCommand = zeroTest ? PendingCommand::TEST_ZERO_0 : PendingCommand::TEST_CENTER_90;
    Serial.print("ACK,");
    Serial.print(command);
    Serial.print(',');
    Serial.print(centerTestChannel);
    Serial.println(zeroTest ? ",0" : ",90");
    return;
  }

  if (strcmp(command, "MOVE_GROUP") == 0) {
    long durationMs;
    if (emptyGroupField || !parseLong(strtok(nullptr, ","), durationMs) ||
        durationMs < 1 || durationMs > 60000) {
      Serial.println("ERR,MOVE_GROUP,INVALID_DURATION_OR_FIELDS");
      return;
    }
    bool selected[6] = {false, false, false, false, false, false};
    int targets[6] = {0, 0, 0, 0, 0, 0};
    uint8_t count = 0;
    char *channelText;
    while ((channelText = strtok(nullptr, ",")) != nullptr) {
      long channel, angle;
      if (!parseLong(channelText, channel) || channel < 0 || channel > 5 ||
          selected[channel] || !parseLong(strtok(nullptr, ","), angle) || angle < 0 || angle > 180) {
        Serial.println("ERR,MOVE_GROUP,INVALID_TARGET");
        return;
      }
      const int low = GROUP_SAFE_MIN_DEG[channel];
      const int high = GROUP_SAFE_MAX_DEG[channel];
      const int neutral = GROUP_NEUTRAL_DEG[channel];
      if (low < 0 || high > 180 || low > high || neutral < low || neutral > high) {
        Serial.println("ERR,MOVE_GROUP,CALIBRATION_REQUIRED");
        return;
      }
      if (angle < low || angle > high) {
        Serial.println("ERR,MOVE_GROUP,SAFE_RANGE");
        return;
      }
      if (!groupServos[channel]->enabled && angle != neutral) {
        Serial.println("ERR,MOVE_GROUP,NEUTRAL_REQUIRED");
        return;
      }
      selected[channel] = true;
      targets[channel] = static_cast<int>(angle);
      count++;
    }
    if (count == 0) {
      Serial.println("ERR,MOVE_GROUP,NO_TARGETS");
      return;
    }
    // Validate the entire group before enabling any output.
    const unsigned long sharedStart = millis();
    for (uint8_t channel = 0; channel < 6; channel++) {
      if (!selected[channel]) {
        continue;
      }
      ServoMotion &servo = *groupServos[channel];
      if (!servo.enabled) {
        writeServoAngle(servo, GROUP_NEUTRAL_DEG[channel]);
      }
      startMotion(servo, targets[channel], static_cast<unsigned long>(durationMs));
      servo.startTimeMs = sharedStart;
    }
    pendingCommand = PendingCommand::MOVE_GROUP;
    Serial.println("ACK,MOVE_GROUP");
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
  // MOVE_CAMERA,<angle_deg>,<duration_ms>
  // -----------------------------
  if (strcmp(command, "MOVE_CAMERA") == 0) {
    char *angleText = strtok(nullptr, ",");
    char *durationText = strtok(nullptr, ",");

    long angleDeg = 0;
    long durationMs = 0;

    if (!parseLong(angleText, angleDeg) ||
        !parseLong(durationText, durationMs) ||
        durationMs <= 0 ||
        hasUnexpectedExtraToken()) {
      Serial.println(
        "ERR,MOVE_CAMERA,USE:MOVE_CAMERA,<angle_deg>,<duration_ms>"
      );
      return;
    }

    if (!isCameraAngleSafe(angleDeg)) {
      Serial.print("ERR,MOVE_CAMERA,SAFE_RANGE,");
      Serial.print(CAMERA_SAFE_MIN_DEG);
      Serial.print(",");
      Serial.println(CAMERA_SAFE_MAX_DEG);
      return;
    }

    startMotion(
      cameraServo,
      static_cast<int>(angleDeg),
      static_cast<unsigned long>(durationMs)
    );

    pendingCommand = PendingCommand::MOVE_CAMERA;

    Serial.println("ACK,MOVE_CAMERA");
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
  // 여섯 채널의 PWM 출력을 끈 상태로 시작한다.
  pwm.setPin(HEAD_CHANNEL, 0);
  pwm.setPin(ARM_CHANNEL, 0);
  pwm.setPin(CAMERA_CHANNEL, 0);
  pwm.setPin(3, 0);
  pwm.setPin(4, 0);
  pwm.setPin(5, 0);

  Serial.println("READY,SERVO_CONTROLLER");
  Serial.println("SAFE_MODE,OUTPUTS_DISABLED");
  Serial.println("TYPE,HELP");
}

void loop() {
  readSerialInput();

  updateMotion(headServo);
  updateMotion(armServo);
  updateMotion(cameraServo);
  updateMotion(rightYServo);
  updateMotion(leftXServo);
  updateMotion(leftYServo);

  reportCompletionIfNeeded();
}
