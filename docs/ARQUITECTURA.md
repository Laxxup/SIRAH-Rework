# Arquitectura de SIRAH

Estado: **aprobada por el dueño el 24/10/2026**. Hitos 0 y 1 implementados en
código y tests; falta la prueba manual del dueño. El hito 2 (ojos) está
pendiente. Este documento es la guía de construcción; cualquier cambio de
estructura se anota en `docs/DECISIONES.md`.

## 1. Resumen

SIRAH es **un solo proceso** de Python 3.12 con `asyncio`. El núcleo no importa
hardware ni red: recibe texto, produce texto y acciones semánticas. Los
adaptadores hablan con el LLM, el micrófono, el altavoz, la cámara y el ESP32.
Un supervisor arranca cada capa, la vigila y la degrada sin tumbar el resto.

Con solo `LLM_API_KEY` funciona el chat por texto. Ojos, visión y voz son
opt-in. Sin ESP32, cámara o micrófono, SIRAH sigue conversando y avisa en una
línea de lo que falta.

Decisiones que sostienen el diseño:

- **Un dueño por recurso:** una tarea para el serial, una para la cámara, una
  para el micrófono. Nadie más los toca.
- **El núcleo no sabe de hardware:** las acciones son semánticas (`look`,
  `blink`, `tired`); el adaptador decide cómo se envían.
- **La calibración no se duplica:** los ángulos viven en
  `config/eyes-calibration.toml` y en el firmware. La aplicación solo envía
  coordenadas normalizadas y nunca calcula pulsos.
- **Degradar, no caer:** una capa que falla se apaga con un mensaje accionable;
  el chat sigue.

## 2. Estructura de archivos

```
SIRAH-Rework/
├── pyproject.toml              # proyecto uv, dependencias y extras
├── uv.lock                     # versiones fijas
├── Makefile                    # check, test, lint, run
├── README.md                   # qué es, requisitos, inicio rápido
├── .env.example                # configuración comentada (sin secretos)
├── sirah/
│   ├── __main__.py             # python -m sirah
│   ├── cli.py                  # argumentos y subcomandos
│   ├── config.py               # .env + validación + calibración TOML
│   ├── logs.py                 # logging a archivo con rotación
│   ├── session.py              # compone persona + LLM + memoria + agente
│   ├── terminal.py             # chat de texto por consola
│   ├── voice.py                # bucle de voz (micrófono → VAD → STT → TTS)
│   ├── doctor.py               # diagnóstico de todas las capas
│   ├── setup_wizard.py         # `sirah setup`
│   ├── core/                   # sin hardware ni red
│   │   ├── agent.py            # turno: prompt → LLM → texto + acciones
│   │   ├── actions.py          # etiquetas semánticas permitidas
│   │   ├── memory.py           # historial acotado en memoria
│   │   ├── persona.py          # carga tarjetas Character Card v2/v3
│   │   ├── text.py             # limpieza de Markdown sobre el stream
│   │   ├── health.py           # Health para doctor
│   │   └── voice.py            # VAD, frases, estados y supervisor
│   └── adapters/               # todo lo que toca el exterior
│       ├── llm.py              # OpenAI-compatible con SSE
│       ├── stt.py              # Groq Whisper (multipart)
│       ├── tts.py              # Piper en proceso + aplay
│       ├── mic.py              # arecord
│       └── history_file.py     # persistencia JSONL del historial
├── config/
│   ├── eyes-calibration.toml   # intocable, fuente única de calibración
│   ├── sirah.toml.example      # plantilla de persona (local: sirah.toml)
│   └── persona/                # tarjetas de personaje; solo sirah.json se versiona
├── tests/                      # pytest, sin hardware ni red
├── firmware/                   # intocable
├── models/                     # YuNet intocable; voices/ se crea en setup
└── docs/
```

Los archivos de los hitos que aún no existen (`app.py`, `core/states.py`,
`core/supervisor.py`, `adapters/camera.py`, `adapters/eyes.py`,
`adapters/serial_eyes.py`, `adapters/simulated.py`, `web/` y `bench/`) se
crean cuando toque, no antes.

**Por qué esta estructura y no otra:**

- `core/` y `adapters/` son la única separación grande. Es la que exige el
  requisito de que una pieza que falla no tire a las demás, y permite probar
  el agente con un LLM falso y los ojos con un pty.
- `session.py` compone el chat (config, persona, LLM, memoria) y lo comparten
  `terminal.py` y `voice.py`. `app.py`, los estados y el supervisor de capas
  llegan con el hito 2, cuando hay algo que supervisar. No se crean archivos
  vacíos.
- No hay registro de plugins, inyección de dependencias ni interfaces
  genéricas: cada adaptador es una clase concreta que cumple un `Protocol`
  pequeño. Añadir un backend (I2C, TCP) es un archivo nuevo y una rama en la
  fábrica; no hay que tocar el núcleo.
- No hay un único lugar que conozca todas las piezas: `session.py` compone el
  chat y `voice.py` añade la voz. No hay singletons globales ni estado de
  módulo.
- Los archivos son planos dentro de cada carpeta. No hay subpaquetes "por si
  acaso" ni una capa de servicios.

## 3. Capas y responsabilidades

| Capa | Archivo | Responsabilidad | Si falla |
|---|---|---|---|
| LLM | `adapters/llm.py` | `/chat/completions` con SSE, timeouts, reintentos y 429 | El turno falla con mensaje claro; el chat sigue abierto y reintenta |
| Ojos (hito 2) | `adapters/serial_eyes.py` | Dueño único del puerto, handshake, heartbeat, cola y reconexión | Capa apagada con aviso; SIRAH sigue por texto |
| Visión (hito 3) | `adapters/camera.py` | Captura V4L2, YuNet, suavizado y `TARGET` | Se apaga con aviso; los ojos quedan a la última orden |
| STT | `adapters/stt.py` | Groq Whisper en español | El modo voz se apaga; el texto sigue |
| TTS | `adapters/tts.py` | Piper + `aplay`, por frases | Responde por texto y avisa una vez |
| Audio | `adapters/mic.py` + `adapters/tts.py` | `arecord` / `aplay` como subprocesos | Sin voz; el resto sigue |
| VAD | `core/voice.py` | WebRTC VAD + RMS mínimo, turno mínimo de 300 ms | Sin manos libres; el texto sigue |
| Persona | `core/persona.py` | Carga tarjetas v2/v3, limpia en memoria y avisa | Si la tarjeta falla, avisa y arranca con `sirah.json` |
| Memoria | `core/memory.py` + `adapters/history_file.py` | Historial acotado y JSONL | Aviso; la sesión sigue sin persistencia |
| Supervisor | `core/voice.py` (`Supervisor`) | Estados y aviso a los ojos (hoy `NullEyes`) | — |

Estados de capa: `off`, `starting`, `ready`, `degraded`, `failed`. El
supervisor no reinicia en bucle: la reconexión es responsabilidad del
adaptador (serial) o del siguiente intento (LLM, STT).

### 3.1 Contratos pequeños

```python
class Eyes(Protocol):
    def look(self, x: float, y: float) -> None: ...   # no bloquea, último gana
    def blink(self) -> bool: ...                      # False si la cola está llena
    def tired(self) -> bool: ...
    def center(self) -> None: ...
    def health(self) -> Health: ...
    def close(self) -> None: ...

class LLM(Protocol):
    async def stream(self, messages: list[Message]) -> AsyncIterator[str]: ...
    async def health(self) -> Health: ...
```

`STT`, `TTS`, `Microphone` y `Camera` siguen el mismo patrón: método de uso,
`health()` y `close()`. No hay herencia de una clase base grande.

## 4. Flujo de datos

```
teclado ───────────────┐
                       ├─> terminal.py ─┐
micrófono ─> VAD ─> STT┘                 │
                                         v
cámara ─> YuNet ─> suavizado ───────> core/agent.py ──> adapters/llm.py
                                         │                 (SSE)
                                         │
                    ┌────────────────────┼────────────────────┐
                    v                    v                    v
              texto a pantalla      frases a TTS        acciones
              o a TTS               (Piper+aplay)      (look/blink/tired)
                    │                                       │
                    v                                       v
              core/memory.py                        serial_eyes.py
                                                    (TARGET/BLINK/TIRED)
```

### 4.1 Un turno por texto

1. `terminal.py` lee una línea y la pasa a `Agent.respond()`.
2. El estado pasa a `THINKING`; los ojos parpadean una vez si están listos.
3. Se arma el prompt en este orden: contrato (formato, acciones, identidad del
   modo y consentimiento) > datos (idioma, nombre del usuario, modo de
   identidad) > estilo por defecto > ficha de la tarjeta > reglas fijas. La
   ficha manda sobre identidad, cuerpo y carácter; las reglas fijas quedan
   después para que ninguna tarjeta las anule. Incluyen honestidad mínima,
   hechos reales y `HISTORY`/`MEMORY` como contexto pasado. Después se añaden
   los últimos 12 mensajes y el turno actual.
4. El LLM responde en streaming. El parser separa texto de etiquetas de acción
   y **nunca** muestra ni pronuncia las etiquetas. Un limpiador quita el
   Markdown residual y los espacios antes del salto de línea sin guardar toda
   la respuesta.
5. El texto limpio se imprime al ritmo del stream; las acciones se envían a los
   ojos. Ese mismo texto va al historial y, en el hito 4, a TTS.
6. Al terminar, se guarda el turno y el estado vuelve a `IDLE`.

### 4.2 Un turno por voz

1. `sirah voice` comprueba claves, `arecord`/`aplay` y Piper. Si falta algo,
   imprime el problema con `Solución:` y cae al chat por texto.
2. `arecord` entrega frames PCM crudos de 20 ms (16 kHz, mono, S16_LE). Cada
   turno arranca un proceso nuevo: al pararlo se vacía el buffer de la pausa.
3. El VAD combina el umbral `VAD_MIN_RMS` con `webrtcvad` si está instalado.
   El turno incluye el pre-roll, empieza tras `VAD_START_FRAMES` frames de voz
   y termina por `VAD_SILENCE_MS` de silencio o `VAD_MAX_TURN_MS`.
4. El PCM se envuelve en WAV en memoria y se envía a Groq; el texto vuelve al
   mismo `Agent.respond()`. El audio no toca el disco.
5. El texto limpio se imprime y se corta en frases. Piper sintetiza una frase
   mientras suena la anterior, y `aplay` la reproduce; las etiquetas de acción
   nunca se pronuncian.
6. Mientras SIRAH habla el micrófono está parado (half-duplex). No hay
   interrupción por voz en v1. Un texto vacío o ruidoso se ignora y se vuelve a
   escuchar.
7. El saludo de arranque también se dice en voz alta. Ctrl-C para el
   micrófono, Piper y `aplay` antes de salir.

### 4.3 Visión

Un hilo captura a 640×480, detecta la cara más grande cada 2–3 frames y
convierte su centro en `x, y ∈ [-1, 1]` con zona muerta y suavizado EMA. El
resultado se publica en los ojos como `TARGET`, como máximo a 15 Hz y siempre
con el último valor. Si no hay cara durante 1,5 s, envía `CENTER` una vez.

La visión **solo** mueve la mirada; no toca párpados ni envía `BLINK`. La
correspondencia izquierda/derecha se confirma en la prueba física del hito 3;
si sale invertida, es un cambio de signo de una línea.

## 5. Ojos: el dueño único del serial

`serial_eyes.py` es la pieza más delicada. Su diseño:

- **Un hilo dedicado** abre, escribe y lee el puerto. El resto del programa solo
  llama métodos que encolan y vuelven de inmediato. Así el bucle de asyncio
  nunca se bloquea con `pyserial`.
- **Apertura:** `serial.Serial(port, 115200, timeout=0.05, write_timeout=0.5,
  exclusive=True)`. Después espera `READY` hasta 8 s (el DTR puede reiniciar la
  placa) y confirma con `STATUS`.
- **Heartbeat** cada 1 s mientras el enlace está vivo, en el mismo hilo. No
  depende de que haya conversación.
- **Órdenes de párpados:** una sola orden en vuelo y hasta 2 en cola. Cada
  orden lleva un ID incremental (1–255, con vuelta). Si no llega `DONE` en 2 s,
  se registra y se libera; nunca se queda esperando para siempre.
  `ERR EYELIDS_BUSY` descarta la orden y se registra en debug.
- **Mirada:** un único slot "último valor". No hay cola. Se envía `TARGET` como
  máximo a 15 Hz y solo si cambió más de 0,02, para no saturar el puerto.
- **`MODE` no se envía.** El firmware solo hace eco y no lo guarda.
  **`NOD` no se envía.** No mueve nada y no responde.
- **Reconexión:** ante error de lectura/escritura o desaparición del
  dispositivo se cierran las órdenes pendientes, se cierra el puerto y se
  reintenta con espera 1, 2, 4, 8, 16 y 30 s (tope). Al reconectar se espera
  `READY`, se envía `STATUS` y se asume la pose segura del firmware; no se
  reenvía la última mirada.
- **Si el dispositivo no existe al arrancar**, el hilo sigue reintentando si
  hay dirección configurada. Así se puede enchufar el ESP32 con SIRAH ya
  abierto.
- **Cierre:** se vacían las órdenes, se envía `CENTER`, se espera 300 ms y se
  cierra el puerto. Los párpados los abre el firmware al terminar la acción o
  por su watchdog.

La dirección se configura como `serial:///dev/serial/by-id/...`. Si está
vacía, la capa de ojos queda apagada (no se adivina el puerto). `setup` y
`doctor` detectan los candidatos y explican cómo fijarlo. Otros esquemas
(`i2c://`, `tcp://`) se rechazan con "no implementado todavía"; la interfaz
`Eyes` ya permite añadirlos sin tocar el núcleo.

## 6. Acciones semánticas

El LLM puede terminar su respuesta con etiquetas entre `{{ }}`. La lista es
cerrada:

| Etiqueta | Efecto | Validación |
|---|---|---|
| `{{look 0.3 -0.2}}` | Mueve la mirada | Dos floats en `[-1, 1]`; fuera de rango se descarta |
| `{{blink}}` | Parpadeo | Máximo uno por respuesta |
| `{{tired}}` | Parpadeo lento | Máximo uno por respuesta; nunca automático |
| `{{center}}` | Mirada al centro | Sin argumentos |

Reglas del parser:

- Las etiquetas se eliminan siempre del texto, se conozcan o no. Nunca se
  imprimen ni se envían a TTS.
- Máximo 2 acciones por respuesta; una sola de párpados.
- Una etiqueta desconocida o mal formada se descarta y se registra en debug.
- `{{nod}}` no se ofrece en el prompt y se ignora si aparece: el firmware no
  lo implementa.
- El prompt pide texto plano y las etiquetas al final. La brevedad (una a tres
  frases) es un estilo por defecto que la ficha puede cambiar. El limpiador
  sigue quitando asteriscos, viñetas, encabezados, backticks y espacios
  sobrantes por si el modelo no obedece, y no pega frases al quitar énfasis.

El parpadeo natural es independiente del LLM: cada 3–7 s en `IDLE`,
`LISTENING` y `SPEAKING`, con una pausa de 1 s después de cualquier acción de
párpados.

## 7. Máquina de estados

```
IDLE ──voz──> LISTENING ──fin de turno──> THINKING ──primera frase──> SPEAKING
 ^                  │                         │                         │
 └──────────────────┴─────────────────────────┴─────────────────────────┘
                         fin / error recuperable
```

| Estado | Qué hace SIRAH | Ojos |
|---|---|---|
| `IDLE` | Espera entrada | Centro y parpadeo natural |
| `LISTENING` | Captura y VAD | Centro; parpadeo natural |
| `THINKING` | Espera al LLM | Un parpadeo al entrar; mirada al centro |
| `SPEAKING` | Imprime o reproduce | Parpadeo natural; mirada sigue la cara si hay visión |

En modo texto solo se usan `IDLE`, `THINKING` y `SPEAKING` (imprimir cuenta
como hablar). Un error de LLM o STT vuelve a `IDLE`; no se inventa un estado
de "fingir que funcionó". La visión puede cambiar la mirada en cualquier
estado; las acciones de párpados del LLM tienen prioridad sobre el parpadeo
natural.

## 8. Configuración

Precedencia: variables de entorno del proceso > `.env` > valores por defecto.
`.env` se busca en la raíz del proyecto; `SIRAH_ENV_FILE` permite otra ruta
(útil en tests). El archivo se crea con permisos `0600` y nunca se versiona.
Las claves se muestran siempre enmascaradas.

| Variable | Defecto | Validación |
|---|---|---|
| `LLM_API_KEY` | — | Obligatoria para conversar; no se valida el formato |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | URL `http(s)` |
| `LLM_MODEL` | `openai/gpt-oss-20b` | Texto no vacío |
| `LLM_TIMEOUT_S` | `60` | 5–300 |
| `LLM_MAX_TOKENS` | `1024` | 32–4096 |
| `LLM_TEMPERATURE` | `0.6` | 0–2 |
| `LLM_REASONING_EFFORT` | `low` | `low`, `medium`, `high` o vacío (no se envía) |
| `USER_NAME` | vacío | Texto libre; vacío = no se añade al prompt |
| `SIRAH_PERSONA` | vacío | Temporal: ruta a una tarjeta; tiene prioridad sobre `[persona] active` |
| `SIRAH_DATA_DIR` | `$XDG_DATA_HOME/sirah` | Ruta escribible; se crea con `0700` |
| `MEMORY_MESSAGES` | `12` | 2–50 |
| `MEMORY_PERSIST` | `true` | Booleano |
| `EYES_ADDRESS` | vacío | `serial://...` o vacío (ojos apagados) |
| `EYES_BAUD` | `115200` | 9600–921600; **no lo cambies**: el firmware fija 115200 |
| `EYES_HEARTBEAT_MS` | `1000` | 500–2500 |
| `EYES_TARGET_HZ` | `15` | 5–30 |
| `VISION_ENABLED` | `false` | Booleano |
| `VISION_CAMERA` | `/dev/video0` | Dispositivo existente al activar |
| `VISION_MODEL` | `models/face_detection_yunet_2023mar.onnx` | Archivo existente y SHA256 correcto |
| `GROQ_API_KEY` | — | Obligatoria solo para voz |
| `STT_MODEL` | `whisper-large-v3-turbo` | Texto no vacío |
| `STT_LANGUAGE` | `es` | Código ISO corto |
| `STT_TIMEOUT_S` | `30` | 5–120 |
| `TTS_MODEL` | `models/voices/es_MX-claude-high.onnx` | `.onnx` y `.onnx.json` existentes |
| `AUDIO_INPUT_DEVICE` | vacío | Nombre ALSA o vacío (defecto del sistema) |
| `AUDIO_OUTPUT_DEVICE` | vacío | Nombre ALSA o vacío |
| `VAD_AGGRESSIVENESS` | `2` | 0–3 |
| `VAD_MIN_RMS` | `350` | 0–5000 |
| `VAD_PREBUFFER_MS` | `300` | 100–1000 |
| `VAD_START_FRAMES` | `3` | 1–10 (frames de 20 ms) |
| `VAD_SILENCE_MS` | `400` | 200–1500 |
| `VAD_MAX_TURN_MS` | `10000` | 2000–30000 |
| `PANEL_HOST` | `127.0.0.1` | Si no es loopback, exige `PANEL_TOKEN` |
| `PANEL_PORT` | `8765` | 1024–65535 |
| `PANEL_TOKEN` | vacío | Mínimo 16 caracteres si el panel sale de localhost |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Un valor inválido produce un mensaje en español que nombra la variable y el
rango esperado; no un stack trace. Las variables desconocidas se ignoran para
no romper configuraciones antiguas.

`config/sirah.toml` (local, ignorado por git) guarda solo la persona:

```toml
[persona]
active = "config/persona/sirah.json"
language = "es"
identity = "card"           # por defecto; "personaje" es alias

[persona.cards."ashley.json"]
identity = "robot"          # modo estricto solo para esa tarjeta
```

`sirah setup` lo copia de `config/sirah.toml.example` sin sobrescribir. Si falta,
se usan los valores por defecto y `doctor` lo avisa. Un TOML inválido tampoco
tumba el arranque: se usan los valores por defecto y se muestra el motivo. La
identidad (`card`, alias `personaje`, o `robot` estricto) solo puede venir de
aquí; ninguna tarjeta la cambia. `doctor` muestra la identidad efectiva y avisa
si el modo estricto está activo.

La calibración se lee con `tomllib` **solo para validarla** en `doctor` (seis
canales únicos, valores 0–180, pose de arranque coherente). La aplicación no
calcula ángulos ni pulsos y no duplica esos números.

## 9. Persistencia y logs

Directorio de datos (`~/.local/share/sirah` por defecto, `0700`):

```
sirah/
├── history/
│   └── sirah.jsonl       # 0600, uno por tarjeta; solo rol y texto
└── logs/
    └── sirah.log         # 1 MB × 3, rotación
```

- El historial guarda `{"ts", "role", "text"}`. No guarda etiquetas de acción,
  audio, imágenes ni claves. Cada tarjeta usa `<nombre>.jsonl`; el antiguo
  `default.jsonl` se migra una vez a `sirah.jsonl` con respaldo `.bak`.
- Se envían al LLM los últimos `MEMORY_MESSAGES`; el archivo conserva 200
  líneas y se recorta al superar 256 KB.
- El historial no es instrucción: el prompt incluye la nota de que `HISTORY`
  puede venir de conversaciones anteriores y es contexto pasado.
- Los logs van solo al archivo, también con `--debug`; la consola solo muestra
  el chat y los mensajes `[FALLA]`/`[AVISO]`. Los stack traces van al log.
- `sirah setup` escribe `.env` con `0600`; nunca imprime la clave.

## 10. Arranque, degradación y apagado

Orden de arranque:

1. Configuración, `sirah.toml` y logging.
2. Tarjeta activa; si falla, aviso con `Solución:` y arranque con `sirah.json`.
3. Avisos de la tarjeta y, solo en modo estricto, `Modo robot estricto`.
4. Supervisor con las capas disponibles según configuración y flags.
5. Aviso de una línea por cada capa apagada o degradada.
6. Saludo breve (inspirado en `first_mes`, con texto fijo de respaldo).
7. Bucle de texto o de voz.

Reglas:

- Sin `LLM_API_KEY` no se arranca el chat: mensaje con el comando exacto para
  configurarla.
- Sin ojos, visión o voz, el chat funciona igual.
- Un fallo de LLM en un turno no cierra el programa; se muestra el error y se
  puede reintentar.
- Un `ERR PCA9685_NOT_READY` se trata como fallo de hardware: se avisa de
  revisar alimentación/I2C y se reintenta con espera; no se reintenta el
  `pwm.begin()` desde la aplicación.
- `SIGINT`/`SIGTERM`/fin de entrada: se cancela el stream, se para la voz, se
  centra la mirada, se cierran serial, cámara y audio, y se vuelca el log.
  Tiempo máximo de apagado: 3 s.

## 11. Comandos

| Comando | Hito | Qué hace |
|---|---|---|
| `sirah` | 1 | Chat por texto (flags `--vision`, `--debug`, `--persona`) |
| `sirah voice` | 4 | Manos libres con micrófono, Groq y Piper |
| `sirah voice --check` | 4 | Graba 3 s y muestra RMS y VAD |
| `sirah setup` | 0 | Crea `.env`, detecta serial/cámara/audio, ofrece descargar la voz |
| `sirah doctor` | 0 | Diagnóstico de cada capa con solución exacta (`--offline` evita red) |
| `sirah eyes test` | 2 | Prueba explícita de ojos; avisa y pide confirmación |
| `sirah test-hardware` | 6 | Autotest de ojos, cámara, micrófono y altavoz; nunca automático |
| `sirah --panel` | 7 | Chat + panel web en el mismo proceso |
| `sirah update` | 8 | Actualiza desde una etiqueta git, sincroniza y revierte si falla |
| `sirah install-service` | 8 | Servicio systemd de usuario |
| `sirah --version` | 0 | Versión instalada |

`doctor` no abre el puerto serial por defecto (abrirlo reinicia la placa y
mueve los servos a la pose segura). Comprueba dispositivo, permisos, grupos,
ModemManager/brltty y calibración. El handshake real se hace en
`eyes test`/`test-hardware`, con aviso previo.

## 12. Pruebas

`make check` ejecuta `ruff check`, `ruff format --check` y `pytest`, sin red ni
hardware.

- **Protocolo serial:** un firmware simulado sobre un pty (no el de banco)
  implementa el mismo protocolo: `READY`, `ACK`/`DONE`, cola de párpados,
  watchdog, `ERR`. Se prueban handshake, timeout de `DONE`, `EYELIDS_BUSY`,
  reconexión (cerrar el pty) y latest-wins de `TARGET`.
- **LLM:** servidor HTTP falso local que emite SSE; se prueban streaming,
  etiquetas, 429, timeout y respuesta truncada.
- **Persona y acciones:** JSON inválido, versión desconocida, etiquetas
  desconocidas, coordenadas fuera de rango y límite de acciones.
- **Visión:** detector falso para probar zona muerta, suavizado, pérdida de
  cara y límite de frecuencia; carga real del modelo sobre una imagen en
  blanco solo como smoke test.
- **VAD:** frames sintéticos de silencio y tono para inicio, fin, pre-roll y
  turno máximo.
- **Voz:** micrófono, Piper y `aplay` falsos como procesos reales; STT con
  transporte HTTP simulado; bucle completo con micrófono/VAD/STT/TTS falsos,
  half-duplex, transcripción vacía, caída del STT y cierre sin huérfanos.
- **Supervisor:** una capa que falla no impide las demás.
- **Hardware de banco:** marcados `hardware`; solo corren si existe
  `BENCH_PORT`, y solo contra ese puerto. Si no está, se saltan y se dice.
- **Voz real, cámara real, servos reales:** solo el dueño. Cada hito con
  hardware entrega una lista corta de pasos manuales y se registra en
  `docs/PENDIENTES.md`.

## 13. Hitos

| Hito | Alcance | Listo cuando |
|---|---|---|
| 0 | Scaffold, config, logs, CLI, `setup`, `doctor`, `Makefile`, README inicial, tests | `uv sync`, `setup` y `doctor` funcionan en limpio. El criterio "llega a chatear" se cierra con el hito 1 |
| 1 | Texto: persona, LLM con streaming, historial local, parser de acciones, saludo, tests | `uv run sirah` conversa solo con `LLM_API_KEY`; pasar persona es cambiar un archivo |
| 2 | Ojos: adaptador serial, firmware de banco, parpadeo natural, heartbeat, reconexión, `eyes test` | Pasan tests simulados y de banco (si hay `BENCH_PORT`); el dueño confirma los servos |
| 3 | Visión: YuNet, hilo de cámara, suavizado, `TARGET`, opt-in | Tests con detector falso y modelo real; el dueño confirma el seguimiento |
| 4 | Voz: `arecord`, VAD, Groq STT, Piper, `aplay`, half-duplex | Pruebas por etapa con audio; el dueño confirma una conversación |
| 5 | Memoria: historial local ya cubierto; **Zep se omite** salvo que el dueño lo pida | Persistencia entre sesiones comprobada |
| 6 | Autotest explícito de hardware con confirmación | `sirah test-hardware` recorre ojos, cámara, micro y altavoz |
| 7 | Panel web local, sin build de frontend | El dueño configura y arranca desde el navegador; SIRAH funciona sin panel |
| 8 | Versiones, `update` con reversión, servicio systemd, `DESPLIEGUE.md` | Actualizar, revertir y sobrevivir a un reinicio |

Los hitos 0, 1 y 4 están implementados y cubiertos por tests simulados. **No se
dan por validados** hasta que el dueño complete las pruebas manuales de
`docs/PENDIENTES.md`.

Pruebas manuales por hito (el dueño las ejecuta y las confirma):

- **0:** `uv sync`, `sirah setup`, `sirah doctor`; mensajes claros.
- **1:** conversación de 10 turnos; respuesta en streaming; cambiar de persona.
- **2:** `sirah eyes test` con aviso; centro, parpadeo, cansancio y mirada;
  desenchufar y reenchufar el USB con SIRAH corriendo.
- **3:** cara a la izquierda/derecha/arriba/abajo; sin cara vuelve al centro.
- **4:** `sirah voice --check`; tres turnos hablados; SIRAH no se oye a sí
  misma; cortar internet y comprobar el aviso; Ctrl-C y `pgrep -a
  'arecord|aplay|piper'` sin procesos; probarlo con otra tarjeta.
- **5:** cerrar y abrir; el historial sigue.
- **6:** `sirah test-hardware` completo.
- **7:** abrir el panel, cambiar persona y capas, ver logs y `doctor`.
- **8:** actualizar, revertir y reiniciar el servicio.

## 14. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El firmware no tiene `NOD`, `MODE` persistente ni versión | No se usan; `doctor` solo comprueba el handshake; se documenta en `PENDIENTES.md` |
| Reinicio del ESP32 al abrir el puerto | Esperar `READY` hasta 8 s y reintentar; no enviar a ciegas |
| `ModemManager`/`brltty` capturan el puerto | `doctor` lo detecta y da la regla/orden exacta |
| Los servos reinician la placa por falta de corriente | Aviso de fuente externa y masa común; nunca alimentar desde USB |
| OpenCV 5 rompe YuNet 2023mar | Fijar `opencv-python-headless<5`; test de carga del modelo |
| Piper cambia su CLI | Aislado en `tts.py`; smoke test y mensaje claro si falta |
| Límites gratuitos de Groq (429) | Reintento con espera, mensaje claro y proveedor configurable |
| Sin aarch64 para medir | Rendimiento en Pi marcado "sin verificar"; dependencias con wheel aarch64 |
| El micrófono captura al altavoz | Half-duplex y cooldown de 200 ms tras hablar |
| El panel expone secretos o la red | Loopback por defecto, token obligatorio fuera de él, CSRF, claves enmascaradas |

## 15. Lo que no se construye

- **Zep** en v1. Historial local primero; la interfaz queda para añadirlo.
- **Palabra de activación.** WebRTC VAD es suficiente; openWakeWord solo
  tiene modelos en inglés y licencia no comercial.
- **`NOD`.** El firmware no lo implementa.
- **I2C directo o WiFi.** Solo la interfaz y la dirección quedan preparadas.
- **Character cards v1–v3.** El JSON nativo es suficiente.
- **Contenedores, ORM, base de datos, framework de plugins, build de
  frontend.** No hacen falta.
- **Autotest automático al arrancar.** Mover servos siempre requiere un
  comando explícito y confirmación.

## 16. Documentos relacionados

- `docs/PROTOCOL.md` — comandos, respuestas, tiempos y errores del ESP32.
- `docs/HARDWARE.md` — cableado, canales, calibración y alimentación.
- `docs/SUGERENCIAS.md` — alternativas y fuentes.
- `docs/DECISIONES.md` — decisiones y estado de aprobación.
- `docs/PENDIENTES.md` — lo que falta validar.
- `docs/DESPLIEGUE.md` — se escribe en el hito 8.
