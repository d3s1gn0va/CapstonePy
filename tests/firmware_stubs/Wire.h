#pragma once
#include <algorithm>
#include <cstdint>
#include <sstream>
#include <string>

struct FakeWire { void begin() {} };
inline FakeWire Wire;
struct FakeSerial {
  std::string output;
  void begin(unsigned long) {}
  int available() { return 0; }
  int read() { return -1; }
  template <typename T> void print(T value) {
    std::ostringstream stream;
    stream << value;
    output += stream.str();
  }
  void print(uint8_t value) { print(static_cast<unsigned int>(value)); }
  template <typename T> void println(T value) { print(value); output += "\n"; }
  void println() { output += "\n"; }
};
inline FakeSerial Serial;
inline unsigned long fakeNow = 0;
inline unsigned long millis() { return fakeNow; }
inline void delay(unsigned long value) { fakeNow += value; }
template <typename T> T constrain(T value, T low, T high) { return std::max(low, std::min(value, high)); }
using std::max;
inline long map(long value, long low, long high, long outLow, long outHigh) {
  return (value - low) * (outHigh - outLow) / (high - low) + outLow;
}
