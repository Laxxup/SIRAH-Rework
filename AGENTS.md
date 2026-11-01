# AGENTS.md — SIRAH

> Contexto para sesiones de OpenCode. Dueño (Luis): español docs/comentarios/mensajes; código e IDs inglés. Si algo contradice una suposición, gana este archivo.

Un solo proceso Python 3.12 con `asyncio`. Chat por texto y voz; ojos y visión no
existen físicamente, aunque `terminal.py` parsea `{{look}}`, `{{blink}}`,
`{{tired}}` y `{{center}}` y los descarta. Hitos: 0, 1 y 4. No inventes código
de ojos o visión. Docs canónicos: `docs/ARQUITECTURA.md` manda en estructura;
`docs/PROTOCOL.md` y `docs/HARDWARE.md` derivan del firmware;
`docs/PENDIENTES.md` es verdad de lo no validado; actualiza
`docs/DECISIONES.md` si cambias algo estructural.

Español para documentación, comentarios y mensajes al usuario; inglés para código
e identificadores.

## Comandos

```bash
uv sync                      # instalación base
uv sync --all-extras         # instala TODOS los extras (voz). No uses --extra solo
uv run sirah                 # chat por texto
uv run sirah voice           # voz manos libres (opt-in)
uv run sirah voice --check   # graba 3 s; muestra RMS/VAD
uv run sirah doctor --offline
uv run sirah setup
make check                   # ruff check + ruff format --check + pytest
make test                    # solo pytest
make format                  # ruff format
make guard                   # falla si tocaste rutas intocables (requiere git)
uv run pytest tests/test_agent.py -q
uv run pytest tests/test_agent.py::test_name -q
```

Ejecuta `uv sync` antes de tests/CLI. Instala `uv` en `~/.local/bin` si falta (no hay `.venv` versionado).
`opencode-setup/` es andamiaje de agentes; la instalación real es `uv sync` + `uv run sirah setup`.
`make check` debe pasar sin red, sin hardware y sin `BENCH_PORT`.

## Arquitectura rápida

- `sirah/core/` no importa hardware ni red: agente, persona, memoria, acciones,
  texto, salud, VAD. Se prueba con dobles.
- `sirah/adapters/` toca exterior: LLM SSE, Groq STT, Piper TTS, `arecord`,
  `aplay`/`paplay`/`pw-play`, historial JSONL.
- `sirah/session.py` compone chat. `terminal.py` y `voice.py` son los bucles
  de entrada. `cli.py` solo parsea/compone.
- Entrada de texto usa un hilo daemon; Ctrl-C termina con `logging.shutdown()`
  y `os._exit(130)` intencional. No cambies el comportamiento sin revisar el
  test PTY.
- Voz half-duplex: un `arecord` por turno, mic parado mientras habla, sin
  interrupción por voz. Audio nunca toca disco; el historial solo texto.
- Piper como librería (`piper.PiperVoice`), no CLI; necesita `.onnx` y `.onnx.json`.
  `aplay` puede colgar bajo PipeWire: doctor/voice prueban 200 ms y caen a
  `paplay`/`pw-play`; `AUDIO_PLAYER_COMMAND` fuerza.
- LLM por defecto Groq `openai/gpt-oss-20b`. Su razonamiento consume
  `LLM_MAX_TOKENS`; defecto 1024 con `LLM_REASONING_EFFORT=low`; respuesta
  vacía se reintenta una vez; corte por `length` muestra `[AVISO]`.
- Datos en `$XDG_DATA_HOME/sirah` (`SIRAH_DATA_DIR`): historial JSONL por
  tarjeta y logs rotativos. Logs solo archivo, también con `--debug`.
- Etiquetas de acción se quitan siempre (también TTS), máximo 2 y solo una
  de párpados; desconocidas se descartan.

## Configuración y persona

- Precedencia: entorno de proceso > `.env` > defaults. `.env` en raíz;
  `SIRAH_ENV_FILE` permite otra ruta. `sirah setup` lo crea con `0600`.
- `LLM_API_KEY` única obligatoria. `GROQ_API_KEY` solo voz; si LLM ya es Groq,
  se reutiliza `LLM_API_KEY`.
- `config/sirah.toml` (local, gitignored) guarda solo persona: `active`,
  `language`, `identity` y overrides por tarjeta. `SIRAH_SETTINGS_FILE` otra
  ruta.
- Identidad (`card`, alias `personaje`, o `robot`) se decide solo en
  `sirah.toml`; ninguna tarjeta la cambia. `SIRAH_PERSONA`/`--persona` solo
  eligen tarjeta.
- Tarjetas v2/v3 (y formato antiguo con campos en la raíz) en
  `config/persona/*.json`. Solo `sirah.json` versionada. La tarjeta se usa
  sin modificar el archivo; la limpieza ocurre en memoria.
- Si una tarjeta falla: aviso con `Solución:` y arranque con `sirah.json`.

## Hardware, protocolo y rutas intocables

- No modificar `firmware/`, `config/eyes-calibration.toml` ni `models/`.
  Anota dudas en `docs/PENDIENTES.md`.
- Calibración es la única fuente de ángulos; la app solo envía coordenadas
  normalizadas y nunca calcula pulsos. `doctor` valida, no duplica.
- Serial: USB ESP32 a 115200 8N1, líneas completas y cortas. Comandos
  reales: `CENTER`, `BLINK`, `TIRED`, `TARGET`, `HEARTBEAT`, `STATUS`. `MODE`
  solo eco y `NOD` no mueve nada: no los envíes. No confíes en `STATUS`.
- Espera `READY` al abrir puerto; heartbeat cada ~1 s. Si la PCA no responde:
  `ERR PCA9685_NOT_READY`; resetear/revisar alimentación/I2C, no reintentar
  desde la app.
- Un solo dueño del puerto serial. Mirada es latest-wins (un slot, no cola);
  párpados con una orden en vuelo y timeout. No bloquear `asyncio`.
- Nunca abrir, flashear ni enviar comandos a un serial que no sea
  `BENCH_PORT`. Sin `BENCH_PORT`, saltar pruebas de hardware y decírselo.
- `doctor` no abre el serial por defecto.
- No implementar I2C directo, TCP/WiFi, contenedores ni backend futuros;
  solo la interfaz `Eyes` y `EYES_ADDRESS=serial://...`.
- `TIRED`, alimentación sostenida e integración PCA+servos no validados.

## Tests y entorno

- `pytest` sin red ni hardware. `tests/fake_llm.py` levanta SSE local; hay
  PTY para Ctrl-C, dobles de mic/Piper/aplay y HTTP simulado para STT.
- Los tests aíslan config con `SIRAH_ENV_FILE`, `SIRAH_SETTINGS_FILE`,
  `SIRAH_DATA_DIR`, `XDG_DATA_HOME`, `SIRAH_PERSONA`. No leer `.env` real en
  pruebas.
- Ejecutar pytest desde la raíz: imports como `from tests.fake_llm import`.
- Marker `hardware` para pruebas de banco; sin `BENCH_PORT` se saltan y se
  informa. No debilitar tests: test de hardware inejecutable se salta, no se borra.
- `models/voices/` no versionado; `sirah setup` descarga la voz.

## Trabajo

- Máximo 3 preguntas en total, solo si bloquean. El resto se decide y anota
  en `docs/DECISIONES.md`.
- No explicar lo que se va a hacer; trabajar y mostrar resultados.
- Commits pequeños con mensaje claro. Nada de secretos (`.env` y claves fuera).
- Solo el orquestador habla con el dueño. Subagentes ejecutan/revisan y anotan
  dudas. Todos respetan rutas intocables y `BENCH_PORT`.
- No añadir dependencias/frameworks/ORMs/capas "por si acaso".
- Al terminar algo que requiera hardware real: entregar lista corta de pasos
  manuales y registrar en `docs/PENDIENTES.md`; no marcar como validado.
- Antes de cerrar: `make check` y `make guard`.

## No hacer

- No tocar `firmware/`, `config/eyes-calibration.toml` ni `models/`.
- No leer ni copiar código de fuera de este directorio.
- No abrir seriales que no sean `BENCH_PORT` ni mover servos sin avisar.
- No contenedores, ORMs, microservicios, frameworks de plugins ni build frontend.
- No I2C/WiFi ni panel web antes de su hito.
- No reglas de personalidad globales ni duplicar calibración.
- No panel a red sin autenticación.
- No dar por validado nada dependiente de hardware real.
