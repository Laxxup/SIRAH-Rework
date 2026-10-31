# AGENTS.md — SIRAH

> Contexto para sesiones de OpenCode. El dueño (Luis) habla español: documentación,
> comentarios para humanos y mensajes al usuario en español; código e identificadores
> en inglés. Si algo contradice una suposición, gana este archivo.

## 1. Qué es y estado actual

S.I.R.A.H. es un robot conversacional con ojos animatrónicos: chat por texto y voz,
visión local y 6 servos. Es un solo proceso Python 3.12 con `asyncio`, nativo en Linux
(x86_64 y Raspberry Pi aarch64), sin contenedores, GPU ni servicios externos salvo el
LLM y Groq para STT.

- **Implementados:** hitos 0 (instalación/doctor), 1 (texto) y 4 (voz), con tests
  simulados. El hito 2 (ojos) es el siguiente; 3 (visión) y 5–8 no existen.
- **Los ojos y la visión no existen todavía.** `terminal.py` reconoce `{{look}}`,
  `{{blink}}`, `{{tired}}` y `{{center}}`, pero las descarta; no hay adaptador serial
  ni cámara. No inventes capas, comandos ni archivos que no estén en el código.
- `docs/ARQUITECTURA.md` (aprobada el 24/10/2026) manda en estructura y flujos;
  `docs/PROTOCOL.md` y `docs/HARDWARE.md` derivan del `.ino`; `docs/PENDIENTES.md` es
  la verdad de lo que falta validar. Actualiza `docs/DECISIONES.md` si cambias algo
  estructural.

## 2. Comandos

```bash
uv sync                      # instalación base
uv sync --all-extras         # añade voz (Piper + VAD); no uses --extra por separado
uv run sirah                 # chat por texto
uv run sirah voice           # voz manos libres (opt-in)
uv run sirah voice --check   # graba 3 s y muestra RMS/VAD
uv run sirah doctor --offline
uv run sirah setup
make check                   # ruff check + ruff format --check + pytest
make test                    # solo pytest
make format                  # ruff format
make guard                   # falla si se tocó una ruta intocable (necesita git)
uv run pytest tests/test_agent.py -q
uv run pytest tests/test_agent.py::test_name -q
```

- No hay `.venv` versionado: ejecuta `uv sync` antes de tests o CLI. Si `uv` no está en
  PATH, instálalo con el comando del README (`~/.local/bin`).
- `opencode-setup/` es andamiaje de agentes (regenera `.opencode/`), **no** la
  instalación de SIRAH. La instalación real es `uv sync` + `uv run sirah setup`.
- `make check` debe pasar sin red, sin hardware y sin `BENCH_PORT`.

## 3. Arquitectura y puntos delicados

- `sirah/core/` no importa hardware ni red: agente, persona, memoria, acciones, texto,
  salud y VAD. Se prueba con dobles.
- `sirah/adapters/` toca el exterior: LLM (SSE OpenAI-compatible), Groq STT, Piper TTS,
  `arecord`, `aplay`/`paplay`/`pw-play`, historial JSONL. Cada adaptador tiene su
  versión real y los tests usan dobles.
- `sirah/session.py` compone persona + LLM + memoria + agente; `terminal.py` y
  `voice.py` son los dos bucles de entrada. `cli.py` solo parsea y compone.
- La entrada de terminal usa un hilo daemon; Ctrl-C hace `logging.shutdown()` y
  `os._exit(130)` a propósito para no colgarse esperando a `input()`. No lo cambies por
  un retorno normal sin comprobar el test de PTY.
- La voz es half-duplex: un `arecord` nuevo por turno, el micrófono se para mientras
  habla y no hay interrupción por voz. El audio se envía a Groq y **nunca** toca disco;
  al historial solo va el texto.
- Piper se usa como **librería** (`piper.PiperVoice`), no como CLI; necesita el `.onnx`
  y su `.onnx.json`. `aplay` puede colgarse con PipeWire: `doctor`/`voice` prueban 200 ms
  y caen a `paplay` o `pw-play`; `AUDIO_PLAYER_COMMAND` lo fuerza.
- El LLM por defecto es Groq `openai/gpt-oss-20b`. Su razonamiento consume
  `LLM_MAX_TOKENS`; por eso el defecto es 1024 con `LLM_REASONING_EFFORT=low`, una
  respuesta vacía se reintenta una vez y un corte por `length` muestra `[AVISO]`.
- Datos en `$XDG_DATA_HOME/sirah` (`SIRAH_DATA_DIR`): historial JSONL por tarjeta y logs
  con rotación. Los logs van **solo al archivo**, también con `--debug`; la consola solo
  muestra chat, `[AVISO]` y `[FALLA]`.
- Las etiquetas de acción se quitan siempre del texto (también de TTS), máximo 2 por
  respuesta y una sola de párpados; las desconocidas se descartan.

## 4. Configuración y persona

- Precedencia: entorno del proceso > `.env` > valores por defecto. `.env` se busca en la
  raíz; `SIRAH_ENV_FILE` permite otra ruta. `sirah setup` lo crea con `0600`.
- `LLM_API_KEY` es la única obligatoria para conversar. `GROQ_API_KEY` solo para voz; si
  el LLM ya es Groq, se reutiliza `LLM_API_KEY`. `Zep` no está en v1.
- `config/sirah.toml` (local, ignorado por git) guarda **solo** persona: `active`,
  `language`, `identity` y overrides por tarjeta. `SIRAH_SETTINGS_FILE` permite otra ruta.
- La identidad (`card` por defecto, alias `personaje`, o `robot` estricto) se decide solo
  en `sirah.toml`; ninguna tarjeta puede cambiarla. `SIRAH_PERSONA`/`--persona` solo
  eligen la tarjeta.
- Tarjetas Character Card v2/v3 (también formato antiguo con campos en la raíz) en
  `config/persona/*.json`. `sirah.json` es la única versionada; las demás son locales y
  están ignoradas por git. La tarjeta se usa sin modificar el archivo: la limpieza
  (macros, asteriscos, líneas que anulan el contrato) ocurre en memoria.
- Si una tarjeta falla, se avisa con `Solución:` y se arranca con `sirah.json`. Una
  tarjeta rota nunca impide conversar.
- Prioridad: piso fijo del código (formato, consentimiento, honestidad mínima,
  historial como contexto) > tarjeta (identidad, cuerpo, carácter, afecto, saludo,
  nombre, humor, longitud) > defaults de SIRAH. No añadas reglas de personalidad
  globales.

## 5. Hardware, protocolo y rutas intocables

- **No modifiques** `firmware/`, `config/eyes-calibration.toml` ni `models/`. Si ves un
  posible bug, anótalo en `docs/PENDIENTES.md`.
- La calibración es la única fuente de los ángulos; la app solo envía coordenadas
  normalizadas y nunca calcula pulsos. `doctor` la valida, no la duplica.
- Serial: USB del ESP32 a **115200 8N1**, líneas completas y cortas. Comandos reales:
  `CENTER`, `BLINK`, `TIRED`, `TARGET`, `HEARTBEAT`, `STATUS`; `MODE` solo hace eco y
  `NOD` no mueve nada. No envíes `MODE` ni `NOD`; no confíes en `STATUS` como estado.
- Tras abrir el puerto hay que esperar `READY` (DTR puede reiniciar la placa) y enviar
  `HEARTBEAT` cada ~1 s. Si la PCA no responde: `ERR PCA9685_NOT_READY`, sin `READY`;
  hay que resetear/revisar alimentación e I2C, no reintentar `pwm.begin()` desde la app.
- Un solo dueño del puerto serial. La mirada es latest-wins (un slot, no cola) y los
  párpados tienen una orden en vuelo con timeout; nunca bloquees el bucle de asyncio.
- **Nunca abras, flashees ni envíes comandos a un puerto serial que no sea
  `BENCH_PORT`** (ruta `/dev/serial/by-id/...` confirmada por el dueño). Si no hay
  `BENCH_PORT`, salta los tests de hardware y dilo; no improvises.
- `doctor` **no abre el serial** por defecto: abrirlo reinicia la placa y mueve servos.
  El handshake real solo va en una prueba explícita con aviso y confirmación.
- No implementes I2C directo, TCP/WiFi, contenedores ni backends futuros; solo deja la
  interfaz `Eyes` y `EYES_ADDRESS=serial://...`.
- `TIRED`, la alimentación sostenida y la integración PCA+servos **no están validadas
  físicamente**. Solo el dueño prueba servos, cámara, micrófono y altavoz; ningún agente
  marca eso como validado.

## 6. Tests y entorno

- `pytest` no usa red ni hardware. `tests/fake_llm.py` levanta un servidor SSE local; hay
  PTY para Ctrl-C, dobles para micrófono/Piper/`aplay` y HTTP simulado para STT.
- Los tests aíslan la configuración con `SIRAH_ENV_FILE`, `SIRAH_SETTINGS_FILE`,
  `SIRAH_DATA_DIR`, `XDG_DATA_HOME` y `SIRAH_PERSONA`. No leas el `.env` real en tests.
- Ejecuta pytest desde la raíz: hay imports `from tests.fake_llm import ...`.
- El marcador `hardware` existe para pruebas de banco; sin `BENCH_PORT` se saltan y se
  informa. Nunca contra otro puerto.
- `models/voices/` no se versiona; `sirah setup` descarga la voz. Los tests de voz no
  necesitan el modelo real.
- No debilites tests para hacer pasar un cambio. Si un test de hardware no puede correr,
  se salta, no se borra.

## 7. Forma de trabajar

- Máximo **3 preguntas** en total, y solo si algo bloquea; la confirmación del plan y la
  de `BENCH_PORT` no cuentan. Lo demás decídelo y anótalo en `docs/DECISIONES.md`.
- No expliques lo que vas a hacer; trabaja y muestra resultados.
- Commits pequeños con mensaje claro. Nada de secretos en el repo (`.env` y claves fuera).
- Solo el orquestador habla con el dueño, pregunta y decide; los subagentes ejecutan o
  revisan y anotan dudas en su reporte. Todos respetan las rutas intocables y `BENCH_PORT`.
- Antes de añadir una dependencia, un framework, un ORM o una capa "por si acaso",
  justifícalo; el proyecto prioriza estabilidad y simplicidad sobre funciones.
- Al terminar algo que requiera hardware real, entrega al dueño una lista corta de pasos
  manuales (comando, qué debe verse u oírse) y espera su confirmación. Regístralo en
  `docs/PENDIENTES.md`; no lo marques como validado.

## 8. No hacer

- No tocar `firmware/`, `config/eyes-calibration.toml` ni `models/`.
- No leer ni copiar código de fuera de este directorio.
- No abrir seriales que no sean `BENCH_PORT` ni mover servos sin avisar.
- No usar contenedores, ORMs, microservicios, frameworks de plugins ni build de frontend.
- No implementar I2C/WiFi ni el panel web antes de su hito.
- No añadir reglas de personalidad globales ni duplicar la calibración.
- No exponer el panel a la red sin autenticación (cuando exista).
- No dar por validado nada que dependa de hardware real.

## 9. Agentes de OpenCode

- `orchestrator` (principal): planifica, delega, verifica y habla con el dueño. Cambia
  con `Tab`.
- Subagentes: `explorer` (solo lectura), `builder` (implementa un paso) y `reviewer`
  (revisa el diff, sin editar). Definidos en `.opencode/agents/`; los modelos se fijan
  ahí (local, no versionado). Para regenerarlos: `opencode-setup/README.md`.
- Los plugins `superpowers` y `ponytail` **no anulan este archivo**: sus flujos de
  brainstorming o preguntas siguen sujetos al límite de 3 preguntas de la sección 7 y a
  las rutas intocables de la sección 5. Si chocan, gana este archivo.
- Antes de cerrar una tarea: `make check` y `make guard`.
