# Calibrator direct

Standalone sketch for the classic ESP32 and Arduino-ESP32 3.x. No PCA9685,
ESP32Servo library, SIRAH runtime, saved positions, automatic center, or sweep.
Six logical labels (X, Y, SD, ID, SI, II) share exactly one output: GPIO18.

ESP32Servo is not installed (`arduino-cli lib list`). Its published 3.2.1
metadata and README declare Arduino-ESP32 3.0.0+ compatibility, which includes
3.3.11 in scope; that library was not locally compiled or installed. This sketch
keeps direct LEDC from the already installed core, with no extra dependency or
implicit Servo default position.

## Wiring

Disconnect servo power before wiring or changing servos. Power the ESP32 by USB.

| Connection | Destination |
| --- | --- |
| ESP32 GPIO18 | The single servo SIGNAL |
| Regulated external supply +5 V | SG90 V+ |
| External supply negative | Servo GND |
| ESP32 GND | Same external supply negative/GND |

On a breakout, use the SIGNAL contact electrically connected to ESP32 GPIO18,
usually labelled 18, IO18, or D18. This is not physical header position 18.
If there are S/V/G rows, use S for that GPIO only after checking the markings
or continuity with all power disconnected. Do not assume row order or rail voltage.
The breakout model was not identified in software. Power the servo directly
from the external supply rather than an unverified breakout V rail.

GPIO18 is output-capable, not a classic ESP32 strapping pin, not flash/PSRAM,
and not UART0. Its optional SPI function is unused in this sketch.

Use the user's external regulated 5 V supply for the SG90; a supply capable of
2 A is recommended for one servo's current peaks, not a claim of continuous
2 A consumption. TowerPro lists 0.5-2 A in its SG90 product Q&A; clones vary.
The usual SG90 wires are orange SIGNAL, red V+, brown GND; verify your unit.
Use the expander only for GPIO18 and GND, not its V rail. Use separate leads if
necessary instead of inserting the complete three-wire servo plug into it.
Never power a servo from 3V3. Confirm 3.3 V SIGNAL compatibility. Do not
join external positive to ESP32 5V/VIN/USB or breakout power rails.
Route servo power current directly to its supply, not through the ESP32.
A 10 kohm pulldown from SIGNAL to common GND is recommended to avoid a floating
input during reset; it does not guarantee a servo cannot twitch on power-up.

## Pulse configuration

The user identified the servo as SG90. The shipped nominal control settings are:

| Setting | Value |
| --- | --- |
| `CALIBRATOR_FREQUENCY_HZ` | 50 Hz (20 ms frame) |
| `CALIBRATOR_PULSE_0_US` | 1000 us |
| `CALIBRATOR_PULSE_180_US` | 2000 us |

The explicit conversion is `1000 + round(angle * 1000 / 180)` microseconds:
0 maps to 1000 us, 90 to 1500 us, and 180 to 2000 us. These are nominal SG90
control values documented by Components101, NOT inherited calibration or safe
mechanical limits. They do not guarantee a physical 180-degree stroke; TowerPro
explicitly notes that normal models may have only 150 degrees of travel, and
clones differ. Do not extend the pulse range automatically to seek more travel.

LEDC adds 14-bit duty quantization; PULSE_US reports the requested pulse, not a
measurement. Invalid/zero configuration overrides still reject movement with
`ERR PULSE_CONFIG_REQUIRED`.
Do not change this mapping while recording angles in your calibration text file.
Record the mapping and frequency alongside the angles.

No angle, including 90, is assumed to be a safe center. No mechanical stops,
directions, eyelid positions, or old calibration values are included.

References:

- [SG90 control timing and usual wire colors](https://components101.com/motors/servo-motor-basics-pinout-datasheet)
- [TowerPro SG90 specifications and power/travel Q&A](https://www.towerpro.com.tw/product/sg90-7/)
- [ESP32Servo compatibility declaration](https://github.com/madhephaestus/ESP32Servo)

## Build

From the repository root, using the installed ESP32 core (verified: 3.3.11):

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/calibrator-direct
```

The generic ESP32 Dev Module target is a build choice for the detected
ESP32-D0WD-V3, not proof of the breakout model or flash settings.

## Upload and monitor

Upload is a separate, explicit operation and replaces the current firmware.
Keep servo power disconnected during upload/reset and initial signal checks.
These commands are instructions, not evidence that upload has been performed:

```bash
arduino-cli upload --fqbn esp32:esp32:esp32 --port /dev/ttyUSB0 firmware/calibrator-direct
arduino-cli monitor --port /dev/ttyUSB0 --config baudrate=115200
```

Do not run SIRAH or another serial monitor on that port at the same time.

## Manual commands

Send a complete line with LF, CR, or CRLF. Names are case-insensitive.

```text
help
status
X 90
Y 90
SD 90
ID 90
SI 90
II 90
off
```

These are syntax examples, not a sequence to run or safe positions. Only one
servo is connected. Integers 0..180 are accepted; extra arguments, unknown
names, damaged/overlong lines, fractions and out-of-range values are rejected
without changing an existing output. Incomplete lines never trigger motion.
Responses to successful movement contain SERVO, ANGLE, and PULSE_US.

Boot configures GPIO18 low without attaching LEDC. Help/status never attach
PWM. A valid movement command with configured pulse parameters starts PWM,
which holds the requested position until another command or off. There is no
timeout movement. Off writes zero duty, detaches LEDC, and drives GPIO18 low;
it does not cut power or guarantee a digital servo releases torque. Status
reports the last command, not a measured physical position.

Before connecting a servo, verify GPIO18 with a scope/logic analyzer through
power-on, reset, serial opening, invalid commands, valid commands and off.
Software tests cannot prove electrical startup behavior or mechanical safety.
Then power off, connect one servo, and make small deliberate manual changes,
without forcing stops. Record X/Y center/min/max and each eyelid open/closed,
plus observed directions. Run off AND cut servo power before changing servos.

## Host regression tests

Tests simulate Arduino/LEDC and never access hardware. The default test uses
the actual shipped SG90 settings; the second explicitly disables configuration
to check the no-PWM error path. Neither verifies mechanical safety.

```bash
g++ -std=c++17 -Wall -Wextra -Werror -Ifirmware/tests/one-servo firmware/tests/one-servo/test.cpp -o /tmp/opencode/one-servo-test
/tmp/opencode/one-servo-test
g++ -std=c++17 -Wall -Wextra -Werror -DTEST_UNCONFIGURED -Ifirmware/tests/one-servo firmware/tests/one-servo/test.cpp -o /tmp/opencode/one-servo-unconfigured-test
/tmp/opencode/one-servo-unconfigured-test
```
