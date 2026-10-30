#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

#include "../sirah/calibration.h"

// SIRAH PCA calibrator: manual tool to move X/Y/SD/ID/SI/II through the PCA9685
// on the assembled robot and run a deterministic blink + gaze diagnostic.
//
// Canonical channel map (must match firmware/sirah and config/eyes-calibration.toml):
//   X=CH0 Y=CH1 SD=CH2 ID=CH3 SI=CH4 II=CH5
// Canonical command scale: 50 Hz, 0 deg = 1000 us, 180 deg = 2000 us, so any
// angle found here transfers 1:1 to the production firmware. Record ANGLE and
// PULSE_US next to each finding. This is NOT production firmware: it never
// speaks the Go protocol. TEST uses only canonical calibrated positions.

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;
constexpr uint8_t PCA9685_ADDRESS = 0x40;
constexpr uint16_t SERVO_FREQUENCY_HZ = 50;

// Canonical scale, not a guard: identical to production mapping.
constexpr int PULSE_0_US = 1000;
constexpr int PULSE_180_US = 2000;

const char *const SERVO_NAMES[6] = {"X", "Y", "SD", "ID", "SI", "II"};
const uint8_t SERVO_CHANNELS[6] = {0, 1, 2, 3, 4, 5};

Adafruit_PWMServoDriver pwm(PCA9685_ADDRESS);
bool pcaOk = false;
bool armed = false;

void printHelp() {
  Serial.println("Commands:");
  Serial.println("  help");
  Serial.println("  status");
  Serial.println("  show");
  Serial.println("  arm");
  Serial.println("  off");
  Serial.println("  blink   (canonical eyelid close/open)");
  Serial.println("  gaze    (center/right/left + center/up/down)");
  Serial.println("  test    (blink, then gaze)");
  Serial.println("  <servo> <angle>, angle 0..180");
  Serial.println("  X 90 | Y 75 | SD 120");
  Serial.println("Only an armed servo command writes one channel.");
}

void printStatus() {
  Serial.printf("PCA9685: %s\n", pcaOk ? "OK" : "FAIL");
  Serial.printf("ARM: %s\n", armed ? "ARMED" : "DISARMED");
  Serial.println("SELECTED: NONE (direct servo commands)");
  Serial.println("BOOT OUTPUT WRITES: NONE");
}

void printMap() {
  Serial.println("CHANNEL MAP:");
  for (uint8_t servo = 0; servo < 6; ++servo) {
    Serial.printf("  %s = CH%d\n", SERVO_NAMES[servo], SERVO_CHANNELS[servo]);
  }
  Serial.println("ANGLE INTERFACE: 0..180 degrees");
  Serial.printf("COMMAND SCALE: %d..%d us (canonical, matches production)\n",
                PULSE_0_US, PULSE_180_US);
}

bool parseInteger(const String &text, int &value) {
  if (text.length() == 0) {
    return false;
  }
  uint8_t start = (text[0] == '+' || text[0] == '-') ? 1 : 0;
  if (start == text.length()) {
    return false;
  }
  for (uint8_t i = start; i < text.length(); ++i) {
    if (!isDigit(text[i])) {
      return false;
    }
  }
  value = text.toInt();
  return true;
}

int findServo(const String &name) {
  for (uint8_t servo = 0; servo < 6; ++servo) {
    if (name == SERVO_NAMES[servo]) {
      return servo;
    }
  }
  return -1;
}

bool canMove() {
  if (!pcaOk) {
    Serial.println("ERR PCA9685_NOT_READY");
    return false;
  }
  if (!armed) {
    Serial.println("ERR DISARMED; use arm");
    return false;
  }
  return true;
}

int angleToPulse(int angle) {
  return PULSE_0_US + ((PULSE_180_US - PULSE_0_US) * angle) / 180;
}

uint16_t pulseToTicks(int pulseUs) {
  constexpr uint32_t PERIOD_US = 1000000UL / SERVO_FREQUENCY_HZ;
  return static_cast<uint16_t>((static_cast<uint32_t>(pulseUs) * 4096UL +
                                PERIOD_US / 2UL) /
                               PERIOD_US);
}

void sendAngle(uint8_t servo, int angle) {
  int pulseUs = angleToPulse(angle);
  uint16_t ticks = pulseToTicks(pulseUs);

  // This is the only function that writes a servo channel.
  pwm.setPWM(SERVO_CHANNELS[servo], 0, ticks);
  uint16_t readbackOn = pwm.getPWM(SERVO_CHANNELS[servo], false);
  uint16_t readbackOff = pwm.getPWM(SERVO_CHANNELS[servo], true);
  Serial.printf("SERVO: %s\n", SERVO_NAMES[servo]);
  Serial.printf("CHANNEL: %d\n", SERVO_CHANNELS[servo]);
  Serial.printf("ANGLE: %d\n", angle);
  Serial.printf("PULSE_US: %d\n", pulseUs);
  Serial.printf("PCA_READBACK: on=%u off=%u expected_off=%u %s\n",
                readbackOn, readbackOff, ticks,
                (readbackOn == 0 && readbackOff == ticks) ? "OK" : "MISMATCH");
}

void setEyelids(int sd, int id, int si, int ii) {
  sendAngle(2, sd);
  sendAngle(3, id);
  sendAngle(4, si);
  sendAngle(5, ii);
}

void runBlink() {
  Serial.println("TEST BLINK: CLOSE");
  setEyelids(SD_CLOSED, ID_CLOSED, SI_CLOSED, II_CLOSED);
  delay(170);
  Serial.println("TEST BLINK: OPEN");
  setEyelids(SD_OPEN, ID_OPEN, SI_OPEN, II_OPEN);
  delay(500);
  Serial.println("TEST BLINK: PASS IF ALL FOUR EYELIDS CLOSED AND OPENED ONCE");
}

void runGaze() {
  const int pauseMs = 700;
  Serial.println("TEST GAZE X: CENTER RIGHT CENTER LEFT CENTER");
  sendAngle(0, X_CENTER); delay(pauseMs);
  sendAngle(0, X_RIGHT); delay(pauseMs);
  sendAngle(0, X_CENTER); delay(pauseMs);
  sendAngle(0, X_LEFT); delay(pauseMs);
  sendAngle(0, X_CENTER); delay(pauseMs);

  Serial.println("TEST GAZE Y: CENTER UP CENTER DOWN CENTER");
  sendAngle(1, Y_CENTER); delay(pauseMs);
  sendAngle(1, Y_UP); delay(pauseMs);
  sendAngle(1, Y_CENTER); delay(pauseMs);
  sendAngle(1, Y_DOWN); delay(pauseMs);
  sendAngle(1, Y_CENTER); delay(pauseMs);
  Serial.println("TEST GAZE: PASS IF X/Y MOVED AND RETURNED TO CENTER");
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) {
    return;
  }

  int separator = line.indexOf(' ');
  String first = separator < 0 ? line : line.substring(0, separator);
  String argument = separator < 0 ? "" : line.substring(separator + 1);
  argument.trim();
  first.toUpperCase();

  if (first == "HELP") {
    printHelp();
    return;
  }
  if (first == "STATUS") {
    printStatus();
    return;
  }
  if (first == "SHOW") {
    printMap();
    printStatus();
    return;
  }
  if (first == "ARM") {
    if (!pcaOk) {
      Serial.println("ERR PCA9685_NOT_READY");
      return;
    }
    armed = true;
    Serial.println("ARMED; NO OUTPUT WRITTEN");
    return;
  }
  if (first == "OFF") {
    armed = false;
    Serial.println("OFF; DISARMED; NO OUTPUT WRITTEN");
    return;
  }
  if (first == "BLINK" || first == "GAZE" || first == "TEST") {
    if (!canMove()) {
      return;
    }
    if (first == "BLINK" || first == "TEST") {
      runBlink();
    }
    if (first == "GAZE" || first == "TEST") {
      runGaze();
    }
    Serial.println("TEST COMPLETE");
    return;
  }

  int servo = findServo(first);
  if (servo < 0) {
    Serial.println("ERR UNKNOWN_SERVO; use show");
    return;
  }

  int angle = -1;
  if (!parseInteger(argument, angle) || angle < 0 || angle > 180) {
    Serial.println("ERR ANGLE_OUT_OF_RANGE 0..180");
    return;
  }
  if (canMove()) {
    sendAngle(static_cast<uint8_t>(servo), angle);
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Wire.begin(SDA_PIN, SCL_PIN);
  pcaOk = pwm.begin();
  if (pcaOk) {
    pwm.setOscillatorFrequency(27000000);
    pwm.setPWMFreq(SERVO_FREQUENCY_HZ);
  } else {
    armed = false;
  }

  // Deliberately no channel writes here: boot is disarmed and motionless.
  armed = false;
  Serial.println("SIRAH PCA CALIBRATOR");
  Serial.printf("PCA9685: %s at 0x%02X\n", pcaOk ? "OK" : "FAIL",
                PCA9685_ADDRESS);
  Serial.println("STATE: DISARMED");
  printHelp();
  printStatus();
}

void loop() {
  if (Serial.available()) {
    handleCommand(Serial.readStringUntil('\n'));
  }
}
