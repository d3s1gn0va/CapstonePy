#pragma once
#include <cstdint>

struct Adafruit_PWMServoDriver {
  unsigned int writes = 0;
  explicit Adafruit_PWMServoDriver(uint8_t) {}
  bool begin() { return true; }
  void setPWMFreq(float) {}
  uint8_t setPWM(uint8_t, uint16_t, uint16_t) { writes++; return 0; }
  void setPin(uint8_t, uint16_t) { writes++; }
};
