# Protocolo serial SIRAH

Estado: derivado únicamente de `firmware/sirah/sirah.ino` y de
`config/eyes-calibration.toml` (24/10/2026). El firmware no declara versión;
no hay validación HIL completa todavía. Si el `.ino` cambia, este documento
debe revisarse.

Este protocolo es la interfaz entre SIRAH y el ESP32. El firmware es el dueño
de la física: la aplicación solo pide acciones semánticas y envía coordenadas
normalizadas. La aplicación **no** debe calcular ángulos ni pulsos.

## 1. Enlace físico

| Propiedad | Valor |
|---|---|
| Transporte | USB serial (CDC) del ESP32 |
| Baudios | 115200 |
| Formato | 8N1, sin control de flujo |
| Codificación | ASCII; comandos en mayúsculas |
| Fin de línea | `\n` al enviar; el firmware responde con `\r\n` |
| Longitud recomendada | menos de 64 bytes por línea |
| Dueño del puerto | una sola tarea/proceso |

El firmware lee con `Serial.readStringUntil('\n')`. Una línea incompleta puede
bloquear el bucle hasta 1 segundo (timeout interno de Arduino), retrasando
parpadeos y la máquina de párpados. **Envía siempre la línea completa de una
vez.**

Abrir el puerto puede reiniciar el ESP32 por las líneas DTR/RTS. Tras abrir,
hay que esperar `READY`.

## 2. Formato de los mensajes

Comando:

```
[<id> ]<COMANDO>[ <argumentos>]\n
```

- `<id>` es un entero decimal mayor que cero y es opcional.
- Solo se interpreta como ID si el primer token está formado exclusivamente
  por dígitos y hay un espacio después.
- El ID `0` equivale a no enviar ID.
- Sin ID no se reciben `ACK` ni `DONE` (salvo las respuestas propias del
  comando, como `STATE` o `READY`).
- Los comandos distinguen mayúsculas de minúsculas. `CENTER` funciona;
  `center` devuelve `ERR UNKNOWN_COMMAND`.
- Usa un solo espacio entre argumentos y punto decimal (`0.5`, no `0,5`).

Respuesta:

```
READY
ACK <id>
DONE <id>
STATE <modo>
ERR <código>
```

## 3. Arranque y handshake

Secuencia real del firmware en `setup()`:

1. Abre el serial a 115200.
2. Inicializa la PCA9685 en la dirección I2C `0x40`.
3. Si la PCA no responde: envía `ERR PCA9685_NOT_READY`, **no** mueve los
   servos y **no** anuncia `READY`.
4. Si responde: configura 50 Hz, aplica la pose segura (mirada centrada y
   párpados abiertos) y envía `READY`.

Secuencia recomendada para la aplicación:

1. Abrir el puerto.
2. Esperar `READY` con timeout de 8 s (el reinicio por DTR puede tardar).
3. Enviar `STATUS`; si responde `READY`, el enlace está vivo.
4. Si llega `ERR PCA9685_NOT_READY`: cerrar, resetear la placa (o pedir al
   dueño que revise alimentación/I2C) y reintentar con espera creciente.
5. Si no llega nada: cerrar, esperar y reintentar. No enviar comandos a ciegas.

`READY` es solo una señal de vida. El firmware no informa versión, estado de
la PCA ni modo actual. `STATUS` es un alias de `HEARTBEAT`.

## 4. Comandos

| Comando | Argumentos | Efecto físico | Respuesta con ID | Respuesta sin ID |
|---|---|---|---|---|
| `CENTER` | ninguno | Mirada a X=120, Y=30. No toca párpados. | `ACK`, `DONE` inmediatos | ninguna |
| `BLINK` | ninguno | Cierra los cuatro párpados, espera 170 ms y los abre. No toca X/Y. | `ACK` al aceptar, `DONE` al reabrir | ninguna |
| `TIRED` | ninguno | Cierra los párpados hacia la pose intermedia, espera 350 ms y los abre. No toca X/Y. | `ACK` al aceptar, `DONE` al reabrir | ninguna |
| `NOD` | ninguno | **Sin efecto físico.** Con ID responde `ACK` y `DONE`, pero no mueve nada: el `DONE` anuncia una acción que no ocurre. | `ACK` y `DONE` inmediatos si lleva ID | ninguna |
| `MODE` | `IDLE`, `FACE` o `PERSON` | No mueve nada. Valida y devuelve el modo. **No guarda estado.** | `ACK`, luego `STATE <modo>` | solo `STATE <modo>` |
| `TARGET` | `x y` | Mueve solo X/Y. `x` e `y` son floats en `[-1, 1]`. | `ACK`, `DONE` inmediatos | ninguna |
| `HEARTBEAT` | ninguno | Reinicia el watchdog de 3 s. Responde `READY`. | `READY` (no hay `ACK`) | `READY` |
| `STATUS` | ninguno | Igual que `HEARTBEAT`; no devuelve estado real. | `READY` (no hay `ACK`) | `READY` |

Notas:

- `CENTER` no abre los párpados. Si estaban cerrados por una acción en curso,
  esa acción sigue su curso.
- `TARGET` no toca los párpados; `BLINK`/`TIRED` no tocan X/Y.
- `TARGET` es *latest-wins*: cada línea se aplica al instante y reemplaza la
  anterior. No hay cola para `TARGET`.
- `MODE` solo devuelve el valor recibido; el firmware no lo almacena ni lo usa
  para nada. La aplicación no debe depender de él.
- `NOD` está reservado. No enviarlo hasta que el firmware tenga una
  implementación física validada: no mueve nada y, con ID, responde `ACK` y
  `DONE` como si hubiera terminado una acción que no existe.

### 4.1 Mapeo de `TARGET`

El firmware mapea por tramos alrededor del centro físico calibrado (no un
`map` lineal único):

| `x` | Ángulo X | | `y` | Ángulo Y |
|---|---|---|---|---|
| `-1.0` | 180 (izquierda) | | `-1.0` | 15 (abajo) |
| `0.0` | 120 (centro) | | `0.0` | 30 (centro) |
| `+1.0` | 60 (derecha) | | `+1.0` | 60 (arriba) |

Los valores fuera de rango, `NaN`, `inf`, o con texto extra se rechazan con
`ERR INVALID_TARGET`. No hay respuesta de error por `x` o `y` individuales.

## 5. Respuestas y errores

| Respuesta | Significado | Acción del cliente |
|---|---|---|
| `READY` | Arranque correcto o respuesta a `HEARTBEAT`/`STATUS`. | Marcar enlace vivo. |
| `ACK <id>` | Comando aceptado; no significa terminado. | Esperar `DONE` si se necesita completitud. |
| `DONE <id>` | Acción física terminada (o aplicación inmediata en `CENTER`/`TARGET`). | Liberar la orden. |
| `STATE <modo>` | Eco de `MODE`. | Informativo; no persistente. |
| `ERR PCA9685_NOT_READY` | La PCA no respondió en el arranque. No habrá `READY` ni movimiento. | Resetear/revisar alimentación e I2C; reintentar. |
| `ERR EYELIDS_BUSY` | La cola de párpados está llena (4 en espera, más la activa). | Descartar o coalescer la acción; no reintentar en bucle. |
| `ERR INVALID_MODE` | Modo distinto de `IDLE`, `FACE`, `PERSON`. | Corregir; no reintentar igual. |
| `ERR INVALID_TARGET` | Coordenadas inválidas o fuera de `[-1, 1]`. | Corregir; no reintentar igual. |
| `ERR UNKNOWN_COMMAND` | Comando vacío, desconocido o con formato incorrecto. | Corregir. |

Cuando la PCA no está lista, `handleCommand()` responde
`ERR PCA9685_NOT_READY` a **cualquier** línea, incluso antes de interpretarla.
No hay reintento automático de `pwm.begin()`: hace falta resetear la placa.

## 6. Tiempos, watchdog y cola de párpados

| Parámetro | Valor | Consecuencia |
|---|---|---|
| Timeout de comandos | 3000 ms | Sin comandos válidos, el firmware aplica la pose segura. |
| `HEARTBEAT` recomendado | cada 1000 ms | Mantiene el watchdog despierto con margen. |
| `BLINK` cerrado | 170 ms | Más el tiempo de escritura I2C y reapertura. |
| `TIRED` | pasos de 3° cada 15 ms + 350 ms de espera | Duración aproximada 0,8–1,0 s; depende del recorrido. |
| Cola de párpados | 4 en espera | Más la acción activa: 5 en vuelo. Al llenarse responde `ERR EYELIDS_BUSY`. |

Reglas del watchdog:

- Cualquier comando válido reinicia el contador, incluidos `CENTER`, `TARGET`,
  `MODE`, `BLINK`, `TIRED` y `NOD`.
- Un comando inválido **no** reinicia el contador.
- Al vencer los 3 s, el firmware aplica `safePose()` (mirada centrada y
  párpados abiertos), vacía la cola de párpados y **no avisa por serial**.
- Si había un `BLINK` o `TIRED` en curso, se aborta y nunca llega su `DONE`.
  El cliente debe tener timeout y no quedarse esperando.
- Si el robot está activo pero nadie envía comandos, el watchdog vuelve a
  aplicar la pose segura cada 3 s. Es inofensivo, pero genera escrituras I2C
  periódicas.

La cola de párpados es FIFO y no bloqueante:

- Si está libre, la acción empieza ya y se envía `ACK`.
- Si hay una acción activa, se encola y se envía `ACK` al encolar.
- `DONE` se envía cuando termina la acción concreta, no al encolar.
- `TARGET` y `CENTER` no pasan por esta cola.

## 7. Reglas para el cliente SIRAH

1. **Un solo dueño del puerto.** Una única tarea abre, escribe y lee. Ningún
   otro módulo toca el serial.
2. **Usar `/dev/serial/by-id/...`**, no `/dev/ttyUSB0`, para sobrevivir a
   renumeraciones.
3. **Heartbeat a 1 Hz** mientras SIRAH esté activo, en una tarea independiente
   del chat.
4. **No bloquear la conversación esperando `DONE`.** Las acciones de ojos son
   best-effort; si no llega `DONE`, se registra y se sigue.
5. **Coalescer `TARGET`.** Guardar solo el último valor y enviarlo a 10–20 Hz
   como máximo. Nunca encolar posiciones antiguas.
6. **Limitar `BLINK`/`TIRED`.** No encadenar más de 1–2 acciones; si llega
   `ERR EYELIDS_BUSY`, descartar.
7. **No enviar `NOD`** hasta que exista implementación física.
8. **No confiar en `MODE`** para el estado de la aplicación.
9. **Tras reconectar**, esperar `READY` y asumir que la pose es la segura.
   No reenviar la última posición de los ojos sin querer.
10. **Al salir**, enviar `CENTER` y dejar que el watchdog o un cierre ordenado
    abran los párpados; después cerrar el puerto.

### 7.1 Reconexión

Secuencia recomendada:

1. Detectar error de escritura/lectura o desaparición del dispositivo.
2. Fallar las órdenes pendientes (no dejarlas colgadas).
3. Cerrar el puerto.
4. Reabrir con espera creciente: 1, 2, 4, 8, hasta 30 s.
5. Esperar `READY` hasta 8 s.
6. Enviar `STATUS` y confirmar `READY`.
7. Reanudar heartbeat y el envío de `TARGET`.

Si `READY` no llega y se recibe `ERR PCA9685_NOT_READY`, no es un problema de
baudios: es la PCA o su alimentación. Un reset por DTR puede resolver un fallo
transitorio; si persiste, el dueño debe revisar el hardware.

## 8. Ejemplos

Sesión normal:

```
S: STATUS
F: READY
S: 1 BLINK
F: ACK 1
F: DONE 1
S: 2 TIRED
F: ACK 2
F: DONE 2
S: TARGET -0.5 0.2
S: TARGET 0.0 0.0
S: 3 CENTER
F: ACK 3
F: DONE 3
S: 4 MODE FACE
F: ACK 4
F: STATE FACE
S: HEARTBEAT
F: READY
```

Errores:

```
S: TARGET 1.2 0
F: ERR INVALID_TARGET
S: TARGET 0.1
F: ERR INVALID_TARGET
S: MODE SLEEP
F: ERR INVALID_MODE
S: 7 NOD
R: ACK 7
R: DONE 7
(no mueve nada: el DONE no corresponde a ninguna acción real)
S: FOO
F: ERR UNKNOWN_COMMAND
```

PCA ausente:

```
F: ERR PCA9685_NOT_READY
(no llega READY)
S: HEARTBEAT
F: ERR PCA9685_NOT_READY
```

## 9. Limitaciones conocidas del firmware

Estas limitaciones se documentan para que la aplicación no las tape ni las
finja. Están anotadas en `docs/PENDIENTES.md`.

- `NOD` no tiene efecto físico; con ID responde `ACK` y `DONE` aunque no mueva
  nada. La aplicación no debe enviarlo.
- `MODE` no persiste el modo; solo hace eco.
- `STATUS` no informa versión, modo ni estado de la PCA.
- La PCA no se reintenta si falla el arranque; hace falta reset.
- `TIRED` usa una pose intermedia derivada, pendiente de validación HIL.
- No hay checksum ni número de versión de firmware.
- `readStringUntil()` puede bloquear el bucle si se envía una línea parcial.
- El watchdog aplica la pose segura sin avisar y puede abortar un `BLINK` o
  `TIRED` sin `DONE`.
- La integración PCA + servos y la estabilidad de alimentación sostenida
  siguen pendientes de prueba física.

## 10. Referencias

- `firmware/sirah/sirah.ino` — implementación real.
- `firmware/sirah/calibration.h` — calibración generada.
- `config/eyes-calibration.toml` — fuente canónica de la calibración.
- `docs/HARDWARE.md` — cableado, canales y alimentación.
