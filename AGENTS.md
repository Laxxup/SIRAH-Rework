# AGENTS.md — SIRAH

Un solo proceso Python 3.12 con `asyncio`; sin contenedores y sin GPU. Chat por
texto y voz. Los ojos y la visión aún no existen físicamente: `terminal.py`
parsea `{{look}}`, `{{blink}}`, `{{tired}}` y `{{center}}` y los descarta. No
crear código ni experimentar con ojos o visión. Docs canónicos:
`docs/ARQUITECTURA.md` manda en estructura y flujos;
`docs/PROTOCOL.md` y `docs/HARDWARE.md` derivan del firmware;
`docs/PENDIENTES.md` es la verdad de lo no validado; actualiza
`docs/DECISIONES.md` para cambios estructurales.

Comunicación: español en docs, comentarios y mensajes; inglés en código e
identificadores.

## Comandos

```bash
uv sync                      # instalación base
uv sync --all-extras         # añade voz (Piper + VAD); no --extra suelto
uv run sirah                 # chat por texto
uv run sirah voice           # voz manos libres, opt-in
uv run sirah voice --check   # graba ≥3 s y muestra RMS/VAD
uv run sirah doctor --offline
uv run sirah setup
make check                   # ruff check + ruff format --check + pytest
make test                    # solo pytest
make format                  # ruff format
make guard                   # falla si se tocan rutas intocables
uv run pytest tests/test_agent.py -q
uv run pytest tests/test_agent.py::test_name -q
```

No hay `.venv` versionado: ejecuta `uv sync` antes de tests o CLI. Si `uv` no
está en PATH, instálalo en `~/.local/bin`. `make check` debe pasar sin red, sin
hardware y sin `BENCH_PORT`. 

## Arquitectura rápida

- `sirah/core/` no importa hardware ni red: agente, persona, memoria, acciones,
  texto, salud y VAD.
- `sirah/adapters/` accede al exterior: LLM SSE, Groq STT, Piper TTS,
  `arecord`, `aplay`/`paplay`/`pw-play`, historial JSONL.
- `session.py` compone chat; `terminal.py` y `voice.py` son los bucles de
  entrada; `cli.py` solo parsea y compone.
- La entrada de terminal usa un hilo daemon. Ctrl-C hace `logging.shutdown()` y
  `os._exit(130)` a propósito para no esperar a `input()`. Revisa el test PTY
  antes de cambiarlo.
- Voz half-duplex: `arecord` nuevo por turno, micrófono apagado mientras habla,
  sin interrupción por voz. El audio no toca disco; historial solo texto.
- Piper se usa como librería (`piper.PiperVoice`) con `.onnx` y `.onnx.json`.
  `aplay` puede colgar en PipeWire: doctor/voice prueban 200 ms y caen a
  `paplay`/`pw-play`; `AUDIO_PLAYER_COMMAND` fija el reproductor.
- LLM por defecto: Groq `openai/gpt-oss-20b`. Su razonamiento consume
  `LLM_MAX_TOKENS`; por defecto 1024 con `LLM_REASONING_EFFORT=low`. Una
  respuesta vacía se reintenta una vez y un corte por `length` muestra
  `[AVISO]`.
- Datos en `$XDG_DATA_HOME/sirah` (`SIRAH_DATA_DIR`): historial JSONL por
  tarjeta y logs rotativos (1 MB × 3). Los logs van solo al archivo; también
  con `--debug`.
- Etiquetas de acción: se quitan del texto y del TTS, máximo 2 por respuesta y
  solo una de párpados; las desconocidas se descartan.

## Configuración y persona

- Precedencia: entorno del proceso > `.env` > defaults. `.env` está en la raíz;
  `SIRAH_ENV_FILE` permite otra ruta. `sirah setup` lo crea con `0600`.
- `LLM_API_KEY` es la única obligatoria. `GROQ_API_KEY` solo sirve para voz y se
  reutiliza si el LLM ya es Groq.
- `config/sirah.toml` es local e ignora git y guarda solo persona: `active`,
  `language`, `identity` y overrides por tarjeta. `SIRAH_SETTINGS_FILE` permite
  otra ruta.
- Identidad (`card`/`personaje` o `robot`) sale solo del TOML; ninguna tarjeta
  la cambia. `SIRAH_PERSONA`/`--persona` solo eligen tarjeta.
- Tarjetas Character Card v2/v3 y formato antiguo con campos en la raíz, en
  `config/persona/*.json`. Solo `sirah.json` se versiona. La limpieza ocurre
  en memoria; el archivo original no se toca.
- Si una tarjeta falla, SIRAH avisa con `Solución:` y arranca con
  `sirah.json`.

## Hardware, protocolo y rutas intocables

- No modificar `firmware/`, `config/eyes-calibration.toml` ni `models/`. Anota
  dudas en `docs/PENDIENTES.md`.
- La calibración es la única fuente de ángulos; la app envía coordenadas
  normalizadas y no calcula pulsos. `doctor` las valida, no las duplica.
- Serial del ESP32: 115200 8N1, líneas completas y cortas. Comandos reales:
  `CENTER`, `BLINK`, `TIRED`, `TARGET`, `HEARTBEAT`, `STATUS`. `MODE` solo
  hace eco y `NOD` no mueve nada; no enviarlos. `STATUS` no es estado real.
- Esperar `READY`; heartbeat cada ~1 s. Si la PCA no responde:
  `ERR PCA9685_NOT_READY`; resetear/revisar alimentación o I2C, no reintentar
  desde la app.
- Un solo dueño del puerto serial. Mirada latest-wins (un slot, no cola); los
  párpados tienen una orden en vuelo con timeout. No bloquee `asyncio`.
- Nunca abrir, flashear ni enviar comandos a un serial que no sea `BENCH_PORT`.
  Sin `BENCH_PORT`, salta las pruebas de hardware y lo dice.
- `doctor` no abre el serial por defecto.
- No implementar I2C directo, TCP/WiFi, contenedores ni backend futuro; solo la
  interfaz `Eyes` en `EYES_ADDRESS=serial://...`.
- `TIRED`, alimentación sostenida e integración PCA+servos no están validados.

## Tests y entorno

- `pytest` no usa red ni hardware. `tests/fake_llm.py` levanta SSE local; hay
  PTY para Ctrl-C, dobles para mic/Piper/`aplay` y HTTP simulado para STT.
- Los tests aíslan config con `SIRAH_ENV_FILE`, `SIRAH_SETTINGS_FILE`,
  `SIRAH_DATA_DIR`, `XDG_DATA_HOME` y `SIRAH_PERSONA`. No leer `.env` real en
  pruebas.
- Ejecuta pytest desde la raíz (`from tests.fake_llm import ...`).
- Marker `hardware`: sin `BENCH_PORT` se saltan y se informa. No debilitar
  tests: uno que no puede correr se omite, no se borra.
- `models/voices/` no se versiona; `sirah setup` descarga la voz.

## Forma de trabajar

- Máximo 3 preguntas en total, solo si algo bloquea. Lo demás se decide y se
  anota en `docs/DECISIONES.md`.
- No expliques lo que vas a hacer; trabaja y muestra resultados.
- Commits pequeños con mensaje claro. Nada de secretos en el repo
  (`.env` y claves fuera).
- Solo el orquestador habla con la persona del proyecto. Subagentes ejecutan o
  revisan y anotan dudas. Todos respetan rutas intocables y `BENCH_PORT`.
- No añadir dependencias, frameworks, ORM ni capas "por si acaso".
- Al terminar algo que requiere hardware real: entrega pasos manuales breves,
  registra en `docs/PENDIENTES.md` y no lo marques como validado.
- Antes de cerrar: `make check` y `make guard`.

## No hacer

- No tocar `firmware/`, `config/eyes-calibration.toml` ni `models/`.
- No leer ni copiar código de fuera de este directorio.
- No abrir seriales que no sean `BENCH_PORT` ni mover servos sin avisar.
- No contenedores, ORMs, microservicios, frameworks de plugins ni build
  frontend.
- No I2C/WiFi ni panel web antes de su hito. No panel a red sin
  autenticación.
- No reglas de personalidad globales ni duplicar la calibración.
- Nada es válido por hardware real hasta una prueba real confirmada.
