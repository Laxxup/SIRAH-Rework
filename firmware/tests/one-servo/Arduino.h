#pragma once

#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <string>

#define CONFIG_IDF_TARGET_ESP32 1
constexpr int OUTPUT = 1;
constexpr int LOW = 0;

inline bool attached = false;
inline bool failAttach = false;
inline bool failWrite = false;
inline bool failDetach = false;
inline int attachCalls = 0;
inline int nonzeroWrites = 0;
inline uint32_t currentDuty = 0;

struct TestSerial {
  std::string input;
  std::string output;
  unsigned long baud = 0;
  void begin(unsigned long value) { baud = value; }
  int available() { return !input.empty(); }
  int read() {
    const unsigned char c = input.front();
    input.erase(0, 1);
    return c;
  }
  void println(const char *text) { output += std::string(text) + "\n"; }
  void printf(const char *format, ...) {
    char buffer[512];
    va_list args;
    va_start(args, format);
    const int length = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    assert(length >= 0 && static_cast<size_t>(length) < sizeof(buffer));
    output += buffer;
  }
};
inline TestSerial Serial;

inline void pinMode(uint8_t pin, int mode) {
  assert(pin == 18 && mode == OUTPUT && !attached);
}
inline void digitalWrite(uint8_t pin, int value) {
  assert(pin == 18 && value == LOW && !attached);
}
inline bool ledcAttach(uint8_t pin, uint32_t frequency, uint8_t bits) {
  assert(pin == 18 && frequency == 50 && bits == 14 && !attached);
  ++attachCalls;
  attached = !failAttach;
  return attached;
}
inline bool ledcWrite(uint8_t pin, uint32_t duty) {
  assert(pin == 18 && attached);
  if (failWrite && duty != 0) {
    return false;
  }
  currentDuty = duty;
  if (duty != 0) {
    ++nonzeroWrites;
  }
  return true;
}
inline bool ledcDetach(uint8_t pin) {
  assert(pin == 18 && attached && currentDuty == 0);
  if (failDetach) {
    return false;
  }
  attached = false;
  return true;
}
