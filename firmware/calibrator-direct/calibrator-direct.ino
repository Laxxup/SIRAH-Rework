#include <Arduino.h>
#include <ctype.h>
#include <string.h>

#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "This pin selection is for the classic ESP32 only."
#endif

// SG90 nominal command scale, NOT calibrated travel or safe mechanical limits.
// Zero overrides disable movement. See README for the control reference.
#ifndef CALIBRATOR_PULSE_0_US
#define CALIBRATOR_PULSE_0_US 1000
#endif
#ifndef CALIBRATOR_PULSE_180_US
#define CALIBRATOR_PULSE_180_US 2000
#endif
#ifndef CALIBRATOR_FREQUENCY_HZ
#define CALIBRATOR_FREQUENCY_HZ 50
#endif

constexpr uint8_t SIGNAL_PIN = 18;
constexpr uint8_t PWM_BITS = 14;
constexpr uint32_t PULSE_0_US = CALIBRATOR_PULSE_0_US;
constexpr uint32_t PULSE_180_US = CALIBRATOR_PULSE_180_US;
constexpr uint32_t FREQUENCY_HZ = CALIBRATOR_FREQUENCY_HZ;
const char *const SERVO_NAMES[] = {"X", "Y", "SD", "ID", "SI", "II"};

bool pwmAttached = false;
int lastServo = -1;
int lastAngle = -1;
uint32_t lastPulseUs = 0;
char lineBuffer[48];
size_t lineLength = 0;
bool discardLine = false;

bool pulseConfigValid() {
  return FREQUENCY_HZ > 0 && FREQUENCY_HZ <= 1000000 &&
         PULSE_0_US > 0 && PULSE_180_US > PULSE_0_US &&
         static_cast<uint64_t>(PULSE_180_US) * FREQUENCY_HZ < 1000000;
}

bool stopPWM() {
  if (pwmAttached) {
    // Stop the waveform before disconnecting the peripheral from the pin.
    ledcWrite(SIGNAL_PIN, 0);
    if (!ledcDetach(SIGNAL_PIN)) {
      Serial.println("ERR PWM_DETACH_FAILED; cut servo power");
      return false;
    }
    pwmAttached = false;
  }
  pinMode(SIGNAL_PIN, OUTPUT);
  digitalWrite(SIGNAL_PIN, LOW);
  return true;
}

void printHelp() {
  Serial.println("X|Y|SD|ID|SI|II <0..180> (integer); help; status; off");
  Serial.println("All names use GPIO18. One connected servo only.");
  Serial.println("Degrees are an interface, not measured or safe mechanical angles.");
}

void printStatus() {
  Serial.printf("GPIO: %u\nPWM: %s\nCONFIG: %s\n", SIGNAL_PIN,
                pwmAttached ? "ACTIVE" : "OFF",
                pulseConfigValid() ? "SET; NOT MECHANICAL LIMITS" : "UNCONFIGURED");
  Serial.printf("FREQUENCY_HZ: %lu\nPULSE_0_US: %lu\nPULSE_180_US: %lu\n",
                static_cast<unsigned long>(FREQUENCY_HZ),
                static_cast<unsigned long>(PULSE_0_US),
                static_cast<unsigned long>(PULSE_180_US));
  if (lastServo >= 0) {
    Serial.printf("LAST_SERVO: %s\nLAST_ANGLE: %d\nLAST_PULSE_US: %lu\n",
                  SERVO_NAMES[lastServo], lastAngle,
                  static_cast<unsigned long>(lastPulseUs));
  }
}

void handleCommand(char *line) {
  char *save = nullptr;
  char *name = strtok_r(line, " \t", &save);
  if (name == nullptr) {
    return;
  }
  char *argument = strtok_r(nullptr, " \t", &save);
  if (strtok_r(nullptr, " \t", &save) != nullptr) {
    Serial.println("ERR EXTRA_ARGUMENTS");
    return;
  }
  for (char *p = name; *p; ++p) {
    *p = static_cast<char>(toupper(static_cast<unsigned char>(*p)));
  }
  if (!strcmp(name, "HELP") || !strcmp(name, "STATUS") || !strcmp(name, "OFF")) {
    if (argument != nullptr) {
      Serial.println("ERR EXTRA_ARGUMENTS");
    } else if (!strcmp(name, "HELP")) {
      printHelp();
    } else if (!strcmp(name, "STATUS")) {
      printStatus();
    } else if (stopPWM()) {
      Serial.println("PWM: OFF");
    }
    return;
  }

  int servo = -1;
  for (size_t i = 0; i < sizeof(SERVO_NAMES) / sizeof(SERVO_NAMES[0]); ++i) {
    if (!strcmp(name, SERVO_NAMES[i])) {
      servo = static_cast<int>(i);
      break;
    }
  }
  if (servo < 0) {
    Serial.println("ERR UNKNOWN_SERVO");
    return;
  }
  int angle = 0;
  if (argument == nullptr) {
    Serial.println("ERR ANGLE_REQUIRED");
    return;
  }
  for (const char *p = argument; *p; ++p) {
    if (*p < '0' || *p > '9' || (angle = angle * 10 + (*p - '0')) > 180) {
      Serial.println("ERR ANGLE_OUT_OF_RANGE 0..180 integer");
      return;
    }
  }
  if (!pulseConfigValid()) {
    Serial.println("ERR PULSE_CONFIG_REQUIRED; PWM remains off");
    return;
  }

  const uint32_t pulseUs = PULSE_0_US +
      (static_cast<uint64_t>(PULSE_180_US - PULSE_0_US) * angle + 90) / 180;
  const uint32_t duty = (static_cast<uint64_t>(pulseUs) * FREQUENCY_HZ *
                        (1UL << PWM_BITS) + 500000) / 1000000;
  if (duty == 0 || duty >= (1UL << PWM_BITS) - 1) {
    Serial.println("ERR PWM_RESOLUTION");
    return;
  }
  // Attach only here, after a complete, validated explicit movement command.
  if (!pwmAttached) {
    if (!ledcAttach(SIGNAL_PIN, FREQUENCY_HZ, PWM_BITS)) {
      stopPWM();
      Serial.println("ERR PWM_ATTACH_FAILED");
      return;
    }
    pwmAttached = true;
  }
  if (!ledcWrite(SIGNAL_PIN, duty)) {
    stopPWM();
    Serial.println("ERR PWM_WRITE_FAILED");
    return;
  }
  lastServo = servo;
  lastAngle = angle;
  lastPulseUs = pulseUs;
  Serial.printf("SERVO: %s\nANGLE: %d\nPULSE_US: %lu\n",
                SERVO_NAMES[servo], angle, static_cast<unsigned long>(pulseUs));
}

void setup() {
  stopPWM();
  Serial.begin(115200);
  Serial.println("CALIBRATOR DIRECT; PWM OFF");
  printHelp();
  printStatus();
}

void loop() {
  while (Serial.available()) {
    const int c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (discardLine) {
        Serial.println("ERR INVALID_OR_TOO_LONG_LINE");
      } else {
        lineBuffer[lineLength] = '\0';
        handleCommand(lineBuffer);
      }
      lineLength = 0;
      discardLine = false;
    } else if (!discardLine) {
      if ((c < 32 && c != '\t') || c > 126 || lineLength >= sizeof(lineBuffer) - 1) {
        // Never execute a valid-looking prefix or suffix of a damaged line.
        discardLine = true;
      } else {
        lineBuffer[lineLength++] = static_cast<char>(c);
      }
    }
  }
}
