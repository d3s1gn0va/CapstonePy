#include <cassert>
#include <cstring>
#include <iostream>
#include "../arduino/servo_controller/servo_controller.ino"

void command(const char *value) {
  char text[LINE_BUFFER_SIZE];
  assert(std::strlen(value) < sizeof(text));
  std::strcpy(text, value);
  Serial.output.clear();
  handleCommand(text);
}

void finish(unsigned long duration) {
  Serial.output.clear();
  fakeNow += duration;
  loop();
  assert(Serial.output == "DONE,MOVE_GROUP\n");
}

int main() {
  setup();
  for (auto servo : groupServos) assert(!servo->enabled && !servo->moving);
  command("CAPS");
  assert(Serial.output == "CAPS,MOVE_GROUP,0:45:135:90,1:0:180:45,2:45:135:90,3:0:45:0,4:0:180:135,5:135:180:180\n");
  for (const char *invalid : {"TEST_ZERO_0,5,1000,CONFIRM_0", "TEST_CENTER_90,5,1000,CONFIRM_90",
                              "TEST_LEFT_Y_PAIR,180,CONFIRM_FROM_LAST_ZERO", "TEST_ARM_X_PAIR_CAPS"}) {
    const auto before = pwm.writes;
    command(invalid);
    assert(Serial.output == "ERR,CALIBRATION_TEST_DISABLED\n" && pwm.writes == before);
  }
  for (const char *invalid : {"MOVE_GROUP,1000,0,90,0,90", "MOVE_GROUP,1000,0",
                              "MOVE_GROUP,1000,,0,90", "MOVE_GROUP,1000,0,90,",
                              "MOVE_GROUP,0,0,90", "MOVE_GROUP,60001,0,90",
                              "MOVE_GROUP,1000,0,181", "MOVE_GROUP,1000,9,90",
                              "MOVE_GROUP,1000,1,-15", "MOVE_GROUP,1000,4,195",
                              "MOVE_GROUP,1000,0,90,5,134", "MOVE_GROUP,1000,1,0"}) {
    const auto before = pwm.writes;
    command(invalid);
    assert(Serial.output.find("ERR,MOVE_GROUP") == 0 && pwm.writes == before);
    for (auto servo : groupServos) assert(!servo->enabled && !servo->moving);
  }

  command("MOVE_GROUP,1000,0,90,1,45,2,90,3,0,4,135,5,180");
  assert(Serial.output == "ACK,MOVE_GROUP\n");
  for (uint8_t channel = 0; channel < 6; channel++) {
    assert(groupServos[channel]->enabled);
    assert(groupServos[channel]->currentDeg == GROUP_NEUTRAL_DEG[channel]);
    assert(groupServos[channel]->startTimeMs == headServo.startTimeMs);
  }
  finish(1000);

  // Same relative arm pose: opposite absolute servo directions at one start time.
  command("MOVE_GROUP,1000,1,90,4,90");
  assert(Serial.output == "ACK,MOVE_GROUP\n");
  assert(armServo.startTimeMs == leftXServo.startTimeMs);
  assert(armServo.startDeg == 45 && armServo.targetDeg == 90);
  assert(leftXServo.startDeg == 135 && leftXServo.targetDeg == 90);
  command("MOVE_GROUP,1000,1,0");
  assert(Serial.output == "ERR,BUSY\n");
  fakeNow += 500;
  loop();
  assert(armServo.currentDeg == 68 && leftXServo.currentDeg == 113);
  finish(500);
  assert(armServo.currentDeg == 90 && leftXServo.currentDeg == 90);

  const auto beforeInvalid = pwm.writes;
  command("MOVE_GROUP,650,1,45,5,134");
  assert(Serial.output == "ERR,MOVE_GROUP,SAFE_RANGE\n" && pwm.writes == beforeInvalid);
  assert(!armServo.moving && !leftYServo.moving);

  command("MOVE_GROUP,1200,3,30,5,150");
  assert(Serial.output == "ACK,MOVE_GROUP\n");
  assert(rightYServo.startTimeMs == leftYServo.startTimeMs);
  finish(1200);
  assert(rightYServo.currentDeg == 30 && leftYServo.currentDeg == 150);

  // Alternating relative arm poses: independent targets, not a common angle.
  command("MOVE_GROUP,550,0,60,1,105,4,135");
  assert(Serial.output == "ACK,MOVE_GROUP\n");
  assert(headServo.startTimeMs == armServo.startTimeMs && armServo.startTimeMs == leftXServo.startTimeMs);
  finish(550);
  command("MOVE_GROUP,550,0,120,1,45,4,75");
  assert(Serial.output == "ACK,MOVE_GROUP\n");
  finish(550);
  assert(headServo.currentDeg == 120 && armServo.currentDeg == 45 && leftXServo.currentDeg == 75);
  assert(cameraServo.currentDeg == 90);
  assert(rightYServo.currentDeg == 30 && leftYServo.currentDeg == 150);

  command("MOVE_GROUP,550,0,60,1,105,4,135");
  fakeNow += 100;
  loop();
  const auto beforeStop = pwm.writes;
  command("STOP");
  assert(Serial.output == "ACK,STOP\n" && pwm.writes == beforeStop);
  for (auto servo : groupServos) assert(!servo->moving && servo->enabled);
  fakeNow += 1000;
  Serial.output.clear();
  loop();
  assert(Serial.output.empty() && pwm.writes == beforeStop);
  command("DISABLE");
  assert(Serial.output == "ACK,DISABLE\n");
  for (auto servo : groupServos) assert(!servo->enabled);
  command("MOVE_HEAD,0,1000");
  assert(Serial.output == "ERR,MOVE_HEAD,SAFE_RANGE,45,135\n");
  command("MOVE_ARM,181,1000");
  assert(Serial.output == "ERR,MOVE_ARM,SAFE_RANGE,0,180\n");
  command("MOVE_CAMERA,150,1000");
  assert(Serial.output == "ERR,MOVE_CAMERA,SAFE_RANGE,45,135\n");
  assert(SERVO_MIN_PULSE_US == 1000 && SERVO_MAX_PULSE_US == 2000);
  std::cout << "Six-axis opposite-direction and alternating-arm offline checks passed; no hardware access\n";
}
