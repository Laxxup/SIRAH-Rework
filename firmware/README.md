# Firmware

`firmware/sirah/sirah.ino` es el firmware final de ojos: ESP32 + PCA9685 + 6x SG90.
Incluye `calibration.h` (mismo directorio), generado desde
`config/eyes-calibration.toml` con `python3 scripts/generate_eyes_calibration.py`
(verificar con `--check`; `python3 scripts/check_eyes_mapping.py` valida el mapeo).

## Compilación

Versiones verificadas: Arduino CLI 1.5.1, core `esp32:esp32` 3.3.11,
`Adafruit PWM Servo Driver Library` 3.0.3 y `Adafruit BusIO` 1.17.4.
La libreria PWM es BSD y BusIO es MIT. FQBN: `esp32:esp32:esp32`.

```sh
arduino-cli lib install "Adafruit PWM Servo Driver Library@3.0.3"
arduino-cli lib install "Adafruit BusIO@1.17.4"
make check-firmware
```

Compilar NO valida el hardware: solo verifica BUILD. El comportamiento físico
requiere prueba HIL manual (ver Estado). Las pruebas HIL adicionales permanecen
pendientes, pero no son requisito para publicar el codigo o compilar el sketch.

## Tests host

`tests/one-servo` verifica el calibrador de un servo sin hardware (HOST/SIMULATED):

```sh
make test-firmware-host
```

El target compila ambos casos con C++17 y `-Wall -Wextra -Werror`, usa
ejecutables temporales y no accede al ESP32 ni a los servos.

Cableado final documentado: CH0 X, CH1 Y, CH2 SD, CH3 ID, CH4 SI, CH5 II.
Debe coincidir con el hardware real.

Reglas: TARGET solo X/Y con mapeo segmentado alrededor del centro,
BLINK y TIRED solo párpados con máquina de estados (no bloqueante),
CENTER solo mirada (X=120, Y=30). Boot seguro: mirada centrada +
párpados abiertos, sin sweep ni coreografia autonoma. La API `bool begin()` de Adafruit 3.0.3 comprueba
la presencia I2C; si falla, el firmware responde `ERR PCA9685_NOT_READY`, no
escribe la pose y no anuncia `READY`.

Calibracion final: X=60/120/180, Y=15/30/60, SD=110/15, ID=120/180,
SI=50/145 e II=110/50. Esos extremos fueron validados fisicamente. TIRED usa
por ahora la pose intermedia candidata SD=63, ID=150, SI=98, II=80; esta dentro
de los extremos pero sigue HIL PENDING. La integracion runtime y la estabilidad
de alimentacion sostenida tambien deben verificarse antes de declarar la demo
completa como validada; esa verificacion manual no bloquea esta publicacion del
codigo.

`calibrator-direct/` drives ONE servo straight from ESP32 GPIO18 for
maintenance (no PCA, no production protocol). `calibrator-pca/` moves
X/Y/SD/ID/SI/II manually through the PCA9685 on the assembled robot to read
back new calibrations; it uses the canonical channel map and command scale so
findings transfer 1:1 to `config/eyes-calibration.toml`. Neither calibrator is
production firmware and neither speaks the Go serial protocol.
