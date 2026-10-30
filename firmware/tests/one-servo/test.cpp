// Exercise shipped SG90 defaults, or explicitly disabled configuration.
#ifdef TEST_UNCONFIGURED
#define CALIBRATOR_PULSE_0_US 0
#define CALIBRATOR_PULSE_180_US 0
#define CALIBRATOR_FREQUENCY_HZ 0
#endif
#include "../../calibrator-direct/calibrator-direct.ino"

void send(const std::string &input) {
  Serial.output.clear();
  Serial.input += input;
  loop();
}

void contains(const char *text) {
  assert(Serial.output.find(text) != std::string::npos);
}

int main() {
  setup();
  assert(Serial.baud == 115200);
  assert(!attached && !pwmAttached && attachCalls == 0 && nonzeroWrites == 0);
  send("help\r\nstatus\noff\n");
  assert(attachCalls == 0);
  for (const auto &input : {"X\n", "XB 90\n", "YB 90\n", "X -1\n",
                            "X +1\n", "X 181\n", "X 90.0\n", "X nan\n",
                            "X 9999999999999999999999999\n", "X 90 extra\n",
                            "off 90\n", "help extra\n", "status extra\n"}) {
    send(input);
    contains("ERR");
    assert(attachCalls == 0 && nonzeroWrites == 0);
  }
  send("X 90" + std::string(60, ' ') + "SI 90\n");
  contains("ERR INVALID_OR_TOO_LONG_LINE");
  assert(attachCalls == 0);
  send(std::string("X 90\0", 5) + "SI 90\n");
  contains("ERR INVALID_OR_TOO_LONG_LINE");
  assert(attachCalls == 0);
  send("X 9");
  assert(attachCalls == 0 && Serial.output.empty());
  send("0\n");

#ifndef TEST_UNCONFIGURED
  assert(attached && pwmAttached && attachCalls == 1 && nonzeroWrites == 1);
  contains("SERVO: X\nANGLE: 90\nPULSE_US: 1500\n");
  assert(currentDuty == 1229);
  for (const char *name : SERVO_NAMES) {
    send(std::string(name) + " 0\n");
    assert(lastPulseUs == 1000 && lastAngle == 0);
    assert(currentDuty == 819);
    send(std::string(name) + " 180\n");
    assert(lastPulseUs == 2000 && lastAngle == 180);
    assert(currentDuty == 1638);
  }
  assert(attachCalls == 1);
  const int writes = nonzeroWrites;
  const uint32_t duty = currentDuty;
  send("status\nhelp\nX 181\noff extra\n");
  assert(attached && currentDuty == duty && nonzeroWrites == writes);
  send("off\r\n");
  contains("PWM: OFF");
  assert(!attached && !pwmAttached && currentDuty == 0);
  send("off\n");
  assert(!attached);
  send("  si\t75  \r\n");
  contains("SERVO: SI\nANGLE: 75\nPULSE_US: 1417\n");
  assert(attachCalls == 2);
  send("X 60\n");
  contains("SERVO: X\nANGLE: 60\nPULSE_US: 1333\n");
  send("SD 20\n");
  contains("SERVO: SD\nANGLE: 20\nPULSE_US: 1111\n");
  send("status\n");
  contains("PWM: ACTIVE");
  contains("FREQUENCY_HZ: 50\nPULSE_0_US: 1000\nPULSE_180_US: 2000\n");
  failDetach = true;
  send("off\n");
  contains("ERR PWM_DETACH_FAILED");
  assert(attached && pwmAttached && currentDuty == 0);
  failDetach = false;
  send("off\n");
  assert(!attached && !pwmAttached);
  failAttach = true;
  send("X 90\n");
  contains("ERR PWM_ATTACH_FAILED");
  assert(!attached && !pwmAttached);
  failAttach = false;
  failWrite = true;
  send("X 90\n");
  contains("ERR PWM_WRITE_FAILED");
  assert(!attached && !pwmAttached && currentDuty == 0);
  puts("PASS: SG90 defaults, all six labels on GPIO18, mapping, PWM lifecycle and failures");
#else
  contains("ERR PULSE_CONFIG_REQUIRED");
  assert(!attached && !pwmAttached && attachCalls == 0 && nonzeroWrites == 0);
  for (const char *name : SERVO_NAMES) {
    send(std::string(name) + " 90\n");
    contains("ERR PULSE_CONFIG_REQUIRED");
  }
  send("status\n");
  contains("CONFIG: UNCONFIGURED");
  assert(attachCalls == 0 && nonzeroWrites == 0);
  puts("PASS: boot, parser, helpers and unconfigured movement rejection (no PWM)");
#endif
}
