# Hardware de SIRAH

Estado: derivado de `firmware/sirah/sirah.ino`, de
`config/eyes-calibration.toml` y de `firmware/README.md` (24/10/2026). La
calibración de los extremos está validada físicamente según el firmware; la
pose `TIRED`, la integración completa con la PCA y la alimentación sostenida
siguen pendientes de prueba HIL. No dar nada de eso por validado.

## 1. Componentes

| Pieza | Función | Notas |
|---|---|---|
| ESP32 | Controlador USB serial | Firmware `firmware/sirah/sirah.ino`; 115200 baudios. |
| PCA9685 | Driver PWM I2C de 16 canales | Dirección `0x40`; solo se usan 6 canales. |
| 6 × SG90 | Servos de los ojos | X, Y y cuatro párpados. |
| Fuente externa 5 V | Alimenta los servos | **No** alimentar los servos desde el ESP32/USB. |
| Cámara USB | Visión V4L2 | Opt-in; no mueve la cámara, solo los ojos. |
| Micrófono USB/ALSA | Captura de voz | Opt-in. |
| Altavoz | Salida de Piper | Opt-in. |

## 2. Diagrama

```
                 USB (datos + alimentación lógica)
  Laptop/Pi  ─────────────────────────────────────┐
                                                  │
                                            ┌─────┴─────┐
                                            │   ESP32   │
                                            └──┬─────┬──┘
                                     I2C SDA/SCL│     │USB
                                            ┌───┴─────┴───┐
                                            │  PCA9685    │
                                            │  addr 0x40  │
                                            └──┬───────┬──┘
                          CH0..CH5 (PWM)        │       │ V+ / GND
                                    ┌───────────┘       │
                              ┌─────┴─────┐      ┌──────┴──────┐
                              │ 6 × SG90  │      │ Fuente 5 V  │
                              └───────────┘      │  externa    │
                                                 └──────┬──────┘
                                                        │ GND común
                                                 ───────┴──────
```

La masa de la fuente de servos, la de la PCA y la del ESP32 deben estar
unidas. Sin masa común, los pulsos PWM no tienen referencia y los servos se
comportan de forma errática.

## 3. Conexión ESP32 ↔ PCA9685

| PCA9685 | ESP32 | Nota |
|---|---|---|
| `VCC` | `3V3` | Alimentación lógica de 3,3 V. |
| `GND` | `GND` | Masa común. |
| `SDA` | SDA del I2C | En una placa DevKit ESP32-WROOM suele ser GPIO21; confirmar la variante. |
| `SCL` | SCL del I2C | En una placa DevKit ESP32-WROOM suele ser GPIO22; confirmar la variante. |
| `OE` | `GND` o GPIO | Activo en bajo. Si se deja al aire puede quedar deshabilitado. |
| `V+` | Fuente 5 V externa | **No** al 5 V del ESP32. |
| `GND` (bornera) | GND de la fuente | Masa común con el ESP32. |

El firmware usa `Wire` sin declarar pines, así que toma los pines I2C por
defecto del core de ESP32 para la placa. En una placa DevKit estándar son
GPIO21 (SDA) y GPIO22 (SCL); en otras variantes pueden cambiar. **Confirmar
siempre contra la placa real.**

La dirección I2C es `0x40` porque el firmware construye
`Adafruit_PWMServoDriver(0x40)`. Los jumpers `A0`–`A5` deben quedar en bajo
(dirección base). Si se cambian, el firmware no encuentra la PCA y responde
`ERR PCA9685_NOT_READY`.

## 4. Conexión PCA9685 ↔ servos

| Canal | Nombre | Función | Abierto / centro / cerrado |
|---|---|---|---|
| CH0 | X | Mirada horizontal | 60° derecha, 120° centro, 180° izquierda |
| CH1 | Y | Mirada vertical | 15° abajo, 30° centro, 60° arriba |
| CH2 | SD | Párpado | 110° abierto, 15° cerrado |
| CH3 | ID | Párpado | 120° abierto, 180° cerrado |
| CH4 | SI | Párpado | 50° abierto, 145° cerrado |
| CH5 | II | Párpado | 110° abierto, 50° cerrado |

Cableado típico de un SG90:

| Cable | Conexión |
|---|---|
| Naranja/amarillo (señal) | Salida PWM del canal correspondiente de la PCA. |
| Rojo (V+) | Borne `V+` de la PCA, alimentado por la fuente externa. |
| Marrón/negro (GND) | Borne `GND` de la PCA, con masa común. |

Los canales no usados de la PCA quedan libres. No hay que cambiar el orden:
CH0 = X, CH1 = Y, CH2 = SD, CH3 = ID, CH4 = SI, CH5 = II. Ese orden es el que
usa el firmware y el que está en `config/eyes-calibration.toml`.

## 5. Calibración

La **única fuente válida** es `config/eyes-calibration.toml`. No copiar estos
números a la aplicación ni a otro archivo. El firmware los recibe compilados
en `firmware/sirah/calibration.h`, generado desde el TOML.

### 5.1 PWM

| Parámetro | Valor |
|---|---|
| Frecuencia | 50 Hz (periodo 20 ms) |
| Pulso para 0° | 1000 µs |
| Pulso para 180° | 2000 µs |
| Resolución de la PCA | 12 bits (4096 cuentas por periodo) |
| Oscilador configurado | 27 MHz |

Conversión del firmware:

```
pulso_us = 1000 + (ángulo × (2000 - 1000)) / 180
cuentas  = round(pulso_us × 4096 / 20000)
```

### 5.2 Tabla de ángulos y pulsos

Los pulsos son calculados con la fórmula anterior; los ángulos son los
valores canónicos del TOML.

| Servo | Punto | Ángulo | Pulso aproximado |
|---|---|---|---|
| X | derecha | 60° | 1333 µs |
| X | centro | 120° | 1667 µs |
| X | izquierda | 180° | 2000 µs |
| Y | abajo | 15° | 1083 µs |
| Y | centro | 30° | 1167 µs |
| Y | arriba | 60° | 1333 µs |
| SD | abierto | 110° | 1611 µs |
| SD | cerrado | 15° | 1083 µs |
| ID | abierto | 120° | 1667 µs |
| ID | cerrado | 180° | 2000 µs |
| SI | abierto | 50° | 1278 µs |
| SI | cerrado | 145° | 1806 µs |
| II | abierto | 110° | 1611 µs |
| II | cerrado | 50° | 1278 µs |

Pose `TIRED` (candidata, **pendiente de validación HIL**): se calcula como el
punto medio de abierto y cerrado, redondeando hacia arriba:

| Servo | Ángulo TIRED | Pulso aproximado |
|---|---|---|
| SD | 63° | 1350 µs |
| ID | 150° | 1833 µs |
| SI | 98° | 1544 µs |
| II | 80° | 1444 µs |

### 5.3 Pose de arranque y pose segura

| Servo | Ángulo |
|---|---|
| X | 120° |
| Y | 30° |
| SD | 110° |
| ID | 120° |
| SI | 50° |
| II | 110° |

Es la misma pose que `safePose()`: mirada centrada y párpados abiertos. No hay
barrido ni coreografía automática al arrancar.

### 5.4 Mapeo de la mirada

`TARGET x y` usa coordenadas normalizadas. El firmware interpola por tramos
alrededor del centro para no destruir el centro calibrado:

- X: `-1` → 180° (izquierda), `0` → 120°, `+1` → 60° (derecha).
- Y: `-1` → 15° (abajo), `0` → 30°, `+1` → 60° (arriba).

La aplicación no debe replicar este mapeo; solo envía `x` e `y`.

## 6. Alimentación

Los SG90 son servos baratos y ruidosos en corriente. Los valores típicos de
un SG90 son 4,8–6 V y una corriente de stall de cientos de miliamperios por
servo; con seis servos, una fuente de 5 V y 3 A puede quedarse corta al mover
varios a la vez. **Recomendación:** fuente externa de 5 V con al menos 5 A
(margen), cables cortos y gruesos, y un condensador electrolítico de
1000 µF entre `V+` y `GND` cerca de la PCA. Los valores exactos de consumo
del montaje real están sin medir.

Reglas:

- **Nunca** alimentar los servos desde el pin `5V` o `VIN` del ESP32 ni desde
  el USB de la laptop. El ESP32 se reinicia o se daña.
- **Siempre** masa común entre fuente, PCA y ESP32.
- Encender la fuente de servos antes o a la vez que el ESP32; evitar que un
  servo en movimiento hunda la tensión del ESP32.
- No conectar ni desconectar servos con la alimentación puesta.
- Si el ESP32 se reinicia al mover los servos, la causa más probable es la
  alimentación, no el firmware.

## 7. Cámara, micrófono y altavoz

- **Cámara:** USB, se espera en `/dev/video0` o similar. El firmware no la
  controla; la visión corre en la laptop/Pi con OpenCV + V4L2. La cámara no
  se mueve; el seguimiento mueve solo X/Y de los ojos.
- **Micrófono:** ALSA. Se captura con `arecord` (16 kHz, mono, S16_LE).
- **Altavoz:** ALSA. Piper genera audio y se reproduce con `aplay`.
- La cámara y el audio no pasan por el ESP32.

## 8. Cable USB y puerto serial

- Usa un cable **de datos**, no uno solo de carga.
- El ESP32 aparece como `/dev/ttyUSB*` o `/dev/ttyACM*`; para uso normal,
  usar siempre el enlace estable `/dev/serial/by-id/...`.
- El usuario debe pertenecer al grupo `dialout` para abrir el puerto.
- ModemManager o brltty pueden capturar el puerto; `sirah doctor` debe
  detectarlo y explicar cómo liberarlo.
- Abrir el puerto puede reiniciar el ESP32 por DTR/RTS. Es normal; hay que
  esperar `READY`.

## 9. Diagnóstico de hardware (`sirah doctor`)

| Síntoma | Causa probable | Comprobación / solución |
|---|---|---|
| No aparece `/dev/serial/by-id/...` | Cable de carga, placa sin alimentación o driver | Probar otro cable USB de datos; revisar `dmesg`. |
| `Permission denied` al abrir el puerto | Usuario fuera de `dialout` | `sudo usermod -aG dialout $USER`; cerrar sesión y volver a entrar. |
| El puerto desaparece o cambia | ModemManager/brltty o renumeración | Usar `by-id`; `systemctl status ModemManager`; regla udev si aplica. |
| `ERR PCA9685_NOT_READY` | PCA sin alimentación, I2C mal cableado, dirección distinta de `0x40`, OE mal | Revisar 3V3, GND, SDA/SCL, jumpers de dirección y OE. |
| No llega `READY` | La placa se reinició al abrir el puerto, baudios incorrectos o firmware distinto | Esperar 8 s; confirmar 115200; volver a abrir; revisar `STATUS`. |
| Los servos tiemblan o el ESP32 se reinicia | Fuente insuficiente o masa común ausente | Fuente externa de 5 V/5 A, masa común, condensador. |
| Los párpados se mueven al revés | Canal o calibración incorrectos | No cambiar el firmware; revisar el canal y el TOML con el dueño. |
| `TIRED` no se ve bien | Pose intermedia sin validar | Tratarlo como pendiente HIL; no declararlo validado. |
| `NOD` no hace nada | El firmware no lo implementa | No usarlo; está en `docs/PENDIENTES.md`. |

## 10. Estado de validación

| Elemento | Estado |
|---|---|
| Extremos de calibración X/Y/SD/ID/SI/II | Validados físicamente según `firmware/README.md`. |
| Pose de arranque segura | Definida; validar en el montaje final. |
| Integración PCA9685 + 6 servos | Pendiente HIL. |
| Pose `TIRED` (63/150/98/80) | Pendiente HIL. |
| Alimentación sostenida con los 6 servos | Pendiente de medir. |
| `NOD` | No implementado. |
| Seguimiento visual con cámara real | Pendiente del dueño. |
| Audio con micrófono/altavoz reales | Pendiente del dueño. |

## 11. Seguridad

- Antes de cablear o cambiar un servo, apagar la fuente externa y desconectar
  el USB.
- No mover los servos a mano contra su tope; pueden romper el mecanismo.
- Al probar, mantener dedos y cables fuera del mecanismo.
- No ejecutar un autotest de ojos sin avisar al dueño: los servos se mueven.
- No alimentar la PCA por USB ni por el regulador del ESP32.
- Si algo huele a quemado o el ESP32 se reinicia repetidamente, cortar la
  alimentación y revisar el cableado.

## 12. Ideas futuras (no implementadas)

Solo para `docs/SUGERENCIAS.md`; no forman parte del firmware ni de esta
versión:

- Corte de servos por el pin `OE` de la PCA9685 al apagar.
- Botón físico de apagado limpio.
- I2C directo desde la Raspberry Pi, sin ESP32.
- Transporte TCP/WiFi para los ojos.
- Medición de consumo y protección de la fuente.
