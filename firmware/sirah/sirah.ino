#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <math.h>
#include <stdio.h>

#include "calibration.h"

// Firmware final SIRAH: ESP32 + PCA9685 + 6x SG90.
// Fuente canonica de numeros: config/eyes-calibration.toml (genera calibration.h).
// Cableado final documentado: CH0 X, CH1 Y, CH2 SD, CH3 ID, CH4 SI, CH5 II.
// Debe coincidir con el hardware real.
//
// Contratos:
// - Go/LLM solo piden acciones semanticas; este archivo es dueno de la fisica.
// - TARGET controla SOLO X/Y. BLINK controla SOLO parpados. CENTER solo mirada.
// - Serial preservado: "<ID> CENTER|BLINK|TIRED|NOD|MODE ...|TARGET x y|HEARTBEAT|STATUS"
//   Respuestas: READY, ACK <ID>, DONE <ID>, STATE <modo>, ERR <codigo>.
// - BLINK: ACK al aceptar, DONE cuando fisicamente termina (no bloqueante).
// - Integracion PCA todavia pendiente de prueba HIL final. Calibraciones validadas,
//   integracion PCA no declarada como validada en hardware.

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
bool pcaReady = false;
const unsigned long COMMAND_TIMEOUT_MS = 3000;
// Tiempo fisico con parpados cerrados (mismo orden que el sketch de prueba: 170 ms).
const unsigned long BLINK_CLOSED_MS = 170;
const unsigned long TIRED_HOLD_MS = 350;
const unsigned long EYELID_STEP_MS = 15;
const int EYELID_STEP_DEGREES = 3;
unsigned long lastCommand = 0;

// Punto medio candidato: derivado de extremos validados, pendiente de HIL visual.
const int SD_TIRED = (SD_OPEN + SD_CLOSED + 1) / 2;
const int ID_TIRED = (ID_OPEN + ID_CLOSED + 1) / 2;
const int SI_TIRED = (SI_OPEN + SI_CLOSED + 1) / 2;
const int II_TIRED = (II_OPEN + II_CLOSED + 1) / 2;

enum EyelidState : uint8_t {
  EYELIDS_IDLE = 0,
  EYELIDS_BLINK_CLOSED = 1,
  EYELIDS_TIRED_CLOSING = 2,
  EYELIDS_TIRED_HOLD = 3,
  EYELIDS_TIRED_OPENING = 4,
};
enum EyelidAction : uint8_t { EYELID_NONE = 0, EYELID_BLINK = 1, EYELID_TIRED = 2 };

struct PendingEyelidAction {
  EyelidAction action;
  String id;
  bool hasId;
};

const uint8_t EYELID_QUEUE_CAPACITY = 4;
PendingEyelidAction eyelidQueue[EYELID_QUEUE_CAPACITY];
uint8_t eyelidQueueHead = 0;
uint8_t eyelidQueueCount = 0;
EyelidState eyelidState = EYELIDS_IDLE;
unsigned long eyelidDeadline = 0;
String activeEyelidId = "0";
bool activeEyelidHasId = false;
int currentSD = SD_OPEN;
int currentID = ID_OPEN;
int currentSI = SI_OPEN;
int currentII = II_OPEN;

int angleToPulseUs(int angle) {
  if (angle < 0) angle = 0;
  if (angle > 180) angle = 180;
  return EYES_PULSE_0_US + (angle * (EYES_PULSE_180_US - EYES_PULSE_0_US)) / 180;
}

uint16_t pulseUsToTicks(int pulseUs) {
  const uint32_t periodUs = 1000000UL / EYES_PWM_HZ;  // 20000 a 50 Hz
  return (uint16_t)(((uint32_t)pulseUs * 4096UL + periodUs / 2UL) / periodUs);
}

void writeServo(uint8_t channel, int angle) {
  pwm.setPWM(channel, 0, pulseUsToTicks(angleToPulseUs(angle)));
}

// Mapeo por segmentos alrededor del centro fisico calibrado.
// No usar un map lineal unico min/max: destruiria el centro.
int targetToAngleX(float t) {
  if (!isfinite(t)) return X_CENTER;
  if (t < -1.0f) t = -1.0f;
  if (t > 1.0f) t = 1.0f;
  if (t < 0.0f) {
    return (int)roundf(X_CENTER + t * (X_CENTER - X_LEFT));  // t=-1 -> X_LEFT
  }
  return (int)roundf(X_CENTER + t * (X_RIGHT - X_CENTER));  // t=+1 -> X_RIGHT
}

int targetToAngleY(float t) {
  if (!isfinite(t)) return Y_CENTER;
  if (t < -1.0f) t = -1.0f;
  if (t > 1.0f) t = 1.0f;
  if (t < 0.0f) {
    return (int)roundf(Y_CENTER + t * (Y_CENTER - Y_DOWN));  // t=-1 -> Y_DOWN
  }
  return (int)roundf(Y_CENTER + t * (Y_UP - Y_CENTER));  // t=+1 -> Y_UP
}

void applyGaze(int angleX, int angleY) {
  writeServo(CH_X, angleX);
  writeServo(CH_Y, angleY);
}

void applyEyelids(int sd, int id, int si, int ii) {
  currentSD = sd;
  currentID = id;
  currentSI = si;
  currentII = ii;
  writeServo(CH_SD, sd);
  writeServo(CH_ID, id);
  writeServo(CH_SI, si);
  writeServo(CH_II, ii);
}

void openEyelids() { applyEyelids(SD_OPEN, ID_OPEN, SI_OPEN, II_OPEN); }

void closeEyelids() { applyEyelids(SD_CLOSED, ID_CLOSED, SI_CLOSED, II_CLOSED); }

void safePose() {
  applyGaze(X_CENTER, Y_CENTER);
  openEyelids();
}

void reply(const String &event, const String &value = "") {
  Serial.print(event);
  if (value.length() > 0) { Serial.print(" "); Serial.print(value); }
  Serial.println();
}

int stepToward(int current, int target) {
  if (current < target) return min(current + EYELID_STEP_DEGREES, target);
  if (current > target) return max(current - EYELID_STEP_DEGREES, target);
  return current;
}

bool stepEyelidsToward(int sd, int id, int si, int ii) {
  applyEyelids(stepToward(currentSD, sd), stepToward(currentID, id),
                stepToward(currentSI, si), stepToward(currentII, ii));
  return currentSD == sd && currentID == id && currentSI == si && currentII == ii;
}

void startEyelidAction(EyelidAction action, const String &id, bool hasId) {
  activeEyelidId = id;
  activeEyelidHasId = hasId;
  lastCommand = millis();
  if (action == EYELID_BLINK) {
    closeEyelids();
    eyelidState = EYELIDS_BLINK_CLOSED;
    eyelidDeadline = millis() + BLINK_CLOSED_MS;
    return;
  }
  eyelidState = EYELIDS_TIRED_CLOSING;
  eyelidDeadline = millis();
}

void startNextEyelidAction() {
  if (eyelidQueueCount == 0) return;
  PendingEyelidAction next = eyelidQueue[eyelidQueueHead];
  eyelidQueueHead = (eyelidQueueHead + 1) % EYELID_QUEUE_CAPACITY;
  eyelidQueueCount--;
  startEyelidAction(next.action, next.id, next.hasId);
}

void finishEyelidAction() {
  String doneId = activeEyelidId;
  bool hasId = activeEyelidHasId;
  eyelidState = EYELIDS_IDLE;
  activeEyelidHasId = false;
  if (hasId) reply("DONE", doneId);
  startNextEyelidAction();
}

bool enqueueEyelidAction(EyelidAction action, const String &id, bool hasId) {
  if (eyelidState == EYELIDS_IDLE && eyelidQueueCount == 0) {
    if (hasId) reply("ACK", id);
    startEyelidAction(action, id, hasId);
    return true;
  }
  if (eyelidQueueCount >= EYELID_QUEUE_CAPACITY) {
    reply("ERR", "EYELIDS_BUSY");
    return false;
  }
  uint8_t tail = (eyelidQueueHead + eyelidQueueCount) % EYELID_QUEUE_CAPACITY;
  eyelidQueue[tail] = {action, id, hasId};
  eyelidQueueCount++;
  if (hasId) reply("ACK", id);
  lastCommand = millis();
  return true;
}

void pollEyelids() {
  if (eyelidState == EYELIDS_IDLE || (long)(millis() - eyelidDeadline) < 0) return;
  if (eyelidState == EYELIDS_BLINK_CLOSED) {
    openEyelids();
    finishEyelidAction();
    return;
  }
  if (eyelidState == EYELIDS_TIRED_CLOSING) {
    if (stepEyelidsToward(SD_TIRED, ID_TIRED, SI_TIRED, II_TIRED)) {
      eyelidState = EYELIDS_TIRED_HOLD;
      eyelidDeadline = millis() + TIRED_HOLD_MS;
    } else {
      eyelidDeadline = millis() + EYELID_STEP_MS;
    }
    return;
  }
  if (eyelidState == EYELIDS_TIRED_HOLD) {
    eyelidState = EYELIDS_TIRED_OPENING;
    eyelidDeadline = millis();
    return;
  }
  if (stepEyelidsToward(SD_OPEN, ID_OPEN, SI_OPEN, II_OPEN)) {
    finishEyelidAction();
  } else {
    eyelidDeadline = millis() + EYELID_STEP_MS;
  }
}

void handleCommand(String line) {
  line.trim();
  if (!pcaReady) {
    reply("ERR", "PCA9685_NOT_READY");
    return;
  }
  int separator = line.indexOf(' ');
  String id = "0";
  bool hasId = false;
  String command = line;
  if (separator > 0) {
    String first = line.substring(0, separator);
    bool numeric = first.length() > 0;
    for (uint8_t i = 0; i < first.length(); ++i) { if (!isDigit(first[i])) numeric = false; }
    if (numeric) { id = first; hasId = (id != "0"); command = line.substring(separator + 1); command.trim(); }
  }
  if (command == "CENTER") {
    // Solo direccion de mirada; no toca parpados en comportamiento normal.
    applyGaze(X_CENTER, Y_CENTER);
  } else if (command == "BLINK") {
    // Solo parpados; nunca X/Y. DONE se emite al reabrir (no bloqueante).
    enqueueEyelidAction(EYELID_BLINK, id, hasId);
    return;
  } else if (command == "TIRED") {
    // Expresion temporal suave y derivada; nunca modifica X/Y.
    enqueueEyelidAction(EYELID_TIRED, id, hasId);
    return;
  } else if (command == "NOD") {
    // Expresion fisica pendiente de calibracion: se acepta sin fingir fisica.
  } else if (command.startsWith("MODE ")) {
    String mode = command.substring(5);
    mode.trim();
    if (mode != "IDLE" && mode != "FACE" && mode != "PERSON") {
      reply("ERR", "INVALID_MODE");
      return;
    }
    if (hasId) reply("ACK", id);
    reply("STATE", mode);
    lastCommand = millis();
    return;
  } else if (command.startsWith("TARGET ")) {
    String payload = command.substring(7);
    char extra = '\0';
    float x = 0.0f;
    float y = 0.0f;
    int parsed = sscanf(payload.c_str(), "%f %f %c", &x, &y, &extra);
    if (parsed != 2 || !isfinite(x) || !isfinite(y) || x < -1.0f || x > 1.0f || y < -1.0f || y > 1.0f) {
      reply("ERR", "INVALID_TARGET");
      return;
    }
    // TARGET latest-wins: aplica inmediato solo a X/Y, no toca parpados.
    applyGaze(targetToAngleX(x), targetToAngleY(y));
  } else if (command == "HEARTBEAT" || command == "STATUS") {
    reply("READY");
    lastCommand = millis();
    return;
  } else {
    reply("ERR", "UNKNOWN_COMMAND");
    return;
  }
  lastCommand = millis();
  if (hasId) { reply("ACK", id); reply("DONE", id); }
}

void setup() {
  Serial.begin(115200);
  pcaReady = pwm.begin();
  if (!pcaReady) {
    reply("ERR", "PCA9685_NOT_READY");
    return;
  }
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(EYES_PWM_HZ);
  safePose();
  lastCommand = millis();
  reply("READY");
}

void loop() {
  if (Serial.available()) { handleCommand(Serial.readStringUntil('\n')); }
  if (!pcaReady) { return; }
  pollEyelids();
  if (millis() - lastCommand > COMMAND_TIMEOUT_MS) {
    // Watchdog a pose segura calibrada (no neutral generico, no sweep).
    safePose();
    eyelidState = EYELIDS_IDLE;
    activeEyelidHasId = false;
    eyelidQueueHead = 0;
    eyelidQueueCount = 0;
    lastCommand = millis();
  }
}
