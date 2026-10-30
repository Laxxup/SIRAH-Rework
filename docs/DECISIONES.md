# Decisiones de SIRAH

Registro de las decisiones de diseño y de su estado. Fecha de la propuesta:
**24/10/2026**.

Estados:

- **Aprobada:** el dueño la confirmó.
- **Propuesta:** forma parte de un plan futuro y espera confirmación.
- **Tomada:** decisión técnica dentro del margen del agente; no necesita
  aprobación, pero se puede revertir si el dueño lo pide.
- **Descartada:** se evaluó y no se adopta, con su motivo.

> El dueño aprobó el plan completo y el stack propuesto el **24/10/2026**. Las
> decisiones A1–A11 quedan aprobadas. A partir de aquí se construye el hito 0.

## 1. Aprobaciones

| # | Decisión | Propuesta | Motivo | Estado |
|---|---|---|---|---|
| A1 | Plan y estructura completos | `docs/ARQUITECTURA.md` | Una sola confirmación antes de escribir código | **Aprobada** (24/10/2026) |
| A2 | LLM por defecto | Groq Free con `openai/gpt-oss-20b`, endpoint OpenAI-compatible configurable | Rápido, gratis y sin GPU; permite cambiar a Gemini, OpenRouter u Ollama con tres variables | **Aprobada** (24/10/2026) |
| A3 | STT | Groq `whisper-large-v3-turbo`, español | Buen español, sin instalar modelos; 8 h de audio/día en el plan gratuito | **Aprobada** (24/10/2026) |
| A4 | TTS | Piper + voz `es_MX-claude-high`, invocado como proceso | Local, rápido en Pi, sin cuota; el motor GPL queda aislado | **Aprobada** (24/10/2026) |
| A5 | Visión | YuNet 2023mar con `opencv-python-headless<5` | Ya está en el repo; OpenCV 5 rompe la entrada fija del modelo | **Aprobada** (24/10/2026) |
| A6 | VAD | WebRTC VAD + umbral RMS | Wheel aarch64, sin modelo ni cuota; suficiente para micrófono cercano | **Aprobada** (24/10/2026) |
| A7 | Palabra de activación | Omitir en v1 | Los modelos de openWakeWord son solo en inglés y no comerciales | **Aprobada** (24/10/2026) |
| A8 | Memoria | Historial local JSONL primero; Zep opt-in y **no** en v1 | Zep añade nube, clave y límites; el historial local cubre la continuidad | **Aprobada** (24/10/2026) |
| A9 | Panel web | Starlette + uvicorn como extra en el hito 7, sin build de frontend | Capa fina sobre el mismo núcleo; se puede omitir sin afectar a SIRAH | **Aprobada** (24/10/2026) |
| A10 | Dependencias base | `httpx`, `pyserial`; extras `vision`, `voice`, `web`; versiones fijas en `uv.lock` | Pocas, con wheel x86_64 y aarch64 | **Aprobada** (24/10/2026) |
| A11 | Autotest y `NOD` | Autotest solo por comando explícito; no enviar `NOD` | El firmware no implementa `NOD`; mover servos sin avisar está prohibido | **Aprobada** (24/10/2026) |
| A12 | La tarjeta manda, con piso fijo | La personalidad, el cuerpo, el afecto, el saludo y la longitud dependen de la tarjeta; el código solo impone formato, consentimiento, honestidad mínima y contexto | Ninguna regla de personalidad es global; cambiar de personaje es cambiar un archivo | **Aprobada** (27/10/2026) |

## 2. Decisiones técnicas tomadas

Estas decisiones no cambian el stack ni el alcance; son la forma de construirlo.

| # | Decisión | Alternativa descartada | Motivo |
|---|---|---|---|
| T1 | Python 3.12 + `uv`, paquete plano `sirah/` con `core/` y `adapters/` | `src/` layout o un solo módulo | La separación núcleo/adaptadores es requisito; el resto sería ceremonia |
| T2 | Un proceso con `asyncio`; hilos solo para serial y cámara; subprocesos para audio | Microservicios o un hilo por capa | Menos superficie de fallo y un solo ciclo de vida |
| T3 | `.env` parseado con la biblioteca estándar | `python-dotenv` | Son ~20 líneas; no se añade una dependencia por eso |
| T4 | Duraciones en nombres (`*_MS`, `*_S`) como enteros | Cadenas tipo `90s` | Se valida y se lee sin un parser propio |
| T5 | La calibración TOML solo se valida; no se usa para calcular ángulos | Duplicar la calibración en Python o en el prompt | El firmware es el dueño de la física; una sola fuente |
| T6 | Datos en `$XDG_DATA_HOME/sirah` con `0700`; historial y logs `0600` | Guardar junto al código | Permisos correctos y no ensuciar el repo |
| T7 | Logs con `RotatingFileHandler` 1 MB × 3 | Log sin límite | La SD de la Raspberry Pi se desgasta |
| T8 | Interfaz `Eyes` no bloqueante; un hilo dueño del serial | `asyncio` + `pyserial` en el bucle | `pyserial` es bloqueante; el hilo aísla el I/O y simplifica la reconexión |
| T9 | Dirección `serial://...`; si está vacía, ojos apagados | Adivinar el único puerto serial disponible | Podría mover un dispositivo que no es el robot; `setup`/`doctor` ayudan a fijarlo |
| T10 | Heartbeat a 1 Hz; `TARGET` último-gana a 15 Hz; sin cola de mirada | Encolar cada `TARGET` | Evita acumular retraso y saturar el puerto |
| T11 | No enviar `MODE` ni `NOD`; `STATUS` solo para handshake | Usar `MODE` como estado de la aplicación | El firmware no persiste el modo y `NOD` no hace nada |
| T12 | Etiquetas `{{look x y}}`, `{{blink}}`, `{{tired}}`, `{{center}}` | JSON aparte o una línea de acciones al final | Se pueden quitar del stream sin romper la reproducción por frases |
| T13 | Máximo 2 acciones por respuesta y una de párpados; el resto se descarta | Dejar que el LLM decida el ritmo | Evita ráfagas de servos y respuestas raras |
| T14 | Cuatro estados: `IDLE`, `LISTENING`, `THINKING`, `SPEAKING` | Estados por capa o por emoción | Es lo que los ojos necesitan y lo que el resto entiende |
| T15 | Half-duplex en voz, con 200 ms de cooldown | Interrupción por voz (barge-in) | Menos complejidad y menos eco en v1 |
| T16 | `doctor` no abre el serial; el handshake va en `eyes test` | Abrir el puerto en cada diagnóstico | Abrirlo reinicia la placa y mueve los servos |
| T17 | Bench en `bench/sirah_bench/`, nunca se flashea solo | Usar el firmware real sin PCA | El real no anuncia `READY` sin PCA; el de banco imita el protocolo |
| T18 | Tests con pty, servidor LLM falso y detector falso | Depender de hardware o de red | `make check` debe correr en cualquier máquina |
| T19 | Actualización solo desde etiquetas git, con reversión | Descargar un ZIP o auto-modificarse | Reversible y auditable |
| T20 | Servicio systemd **de usuario** | Servicio del sistema | No requiere root y encaja con una Pi de escritorio |
| T21 | Panel solo en `127.0.0.1` por defecto; token si sale a la red | Abrirlo a la red con contraseña opcional | Evita exponer claves y servos por descuido |
| T22 | El criterio "llega a chatear" del hito 0 se cierra en el hito 1 | Bloquear el hito 0 hasta tener chat | El hito 0 entrega instalación y diagnóstico; el chat es el hito 1 |
| T23 | Documentación y mensajes en español; código e identificadores en inglés | Todo en inglés | Lo pide `AGENTS.md` y el dueño |
| T24 | `--debug` para trazas; errores de usuario siempre en español y accionables | Mostrar stack traces en consola | Se puede diagnosticar sin asustar al usuario |
| T25 | `uv` se instaló en `~/.local/bin` durante el hito 0 (0.13.5) | Instalación del sistema con root | No hacía falta root; si falta en el PATH, `source ~/.local/bin/env` |
| T26 | `app.py`, `states.py` y `core/supervisor.py` se posponen al hito 2; el chat de texto se compone en `terminal.py` | Crear archivos vacíos o un supervisor sin capas | En el hito 1 no hay capas que supervisar; el hito 2 los añade con los ojos |
| T27 | El saludo se genera al arrancar (máximo 8 s) y cae a un saludo fijo si falla; no se guarda en el historial. Desde 2A se inspira en `first_mes` (ver T44) | Saludo fijo o esperar el timeout completo del LLM | Conserva la persona como dato y no bloquea el arranque si no hay red |
| T28 | Un archivo de historial por persona (`default.jsonl`, `otra.jsonl`) | Un único `default.jsonl` compartido | Cambiar de persona no mezcla conversaciones; el nombre se sanea |
| T29 | La entrada de terminal usa un hilo daemon; Ctrl-C cierra logs y sale con `os._exit(130)` | `asyncio.to_thread(input)` y salida normal | El hilo de `input` no se puede cancelar y `asyncio.run` esperaba a que terminara; el cierre limpio se comprueba con un test de PTY |
| T30 | `ActionParser` retiene una `{` final entre chunks | Emitirla y no reconocer `{{blink}}` partido | Evita filtrar la llave y pierde como máximo una llave literal al final del stream |
| T31 | Las ayudas de instalación recomiendan `uv sync --all-extras` | Mantener un comando por extra | `uv sync --extra X` desinstala los paquetes de los otros extras y crea un ciclo de avisos |
| T32 | Los errores del LLM se clasifican y el log guarda la causa original | Un único mensaje de conexión | Sin la causa no se puede distinguir DNS, TLS, proxy, timeout o HTTP; el usuario necesita una solución concreta |
| T33 | Los logs van solo al archivo, también con `--debug` | Consola en nivel WARNING o DEBUG | Duplicaba el `[FALLA]` del chat y ensuciaba el prompt; el archivo ya conserva todo |
| T34 | Una respuesta vacía se reintenta una vez; si falla, el aviso menciona `LLM_MAX_TOKENS` y el log guarda `finish_reason` y uso | Avisar al primer vacío o subir el límite sin diagnóstico | `gpt-oss-20b` descuenta el razonamiento del límite; el reintento y el diagnóstico cubren el fallo sin alargar las respuestas normales |
| T35 | En modo `robot` estricto, la identidad de robot y el límite de experiencias humanas van en el prompt del núcleo | Confiar en el JSON de persona solo en ese modo | El modo estricto debe poder usarse en una demostración pública; en `card` manda la tarjeta (A12) |
| T36 | `LLM_MAX_TOKENS=1024`, `LLM_REASONING_EFFORT=low` configurable (vacío = no enviar), log de `finish_reason`/uso en cada turno y aviso `[AVISO]` si el corte es por `length` | Mantener 512 y reintentar los cortes con contenido | El razonamiento de `gpt-oss-20b` consumía el límite; reintentar un corte duplicaría el texto. Con `low` el razonamiento baja a ~10 tokens y las respuestas caben |
| T37 | `USER_NAME` es un dato: el prompt añade solo `Nombre del usuario: {nombre}.`; el historial lleva siempre la nota de que `HISTORY` es contexto pasado | Convertir el nombre en una regla ("no preguntes el nombre") o no marcar el historial | La conducta la decide la personalidad; el nombre y el origen del historial son contexto, no instrucciones |
| T38 | Un limpiador de texto plano actúa sobre el stream y su resultado se guarda en historial y se usará para TTS | Limpiar solo al final o confiar en el prompt | El modelo ignora el formato; el mismo texto limpio evita que TTS lea asteriscos o viñetas |
| T39 | Las personas son Character Card v2/v3; también se aceptan tarjetas antiguas con campos en la raíz | Mantener un formato propio o exigir solo v3 | Es el formato que ya usan las tarjetas del dueño; el cargador tolera variantes |
| T40 | La tarjeta se limpia solo en memoria: macros, asteriscos de acción y líneas que anulan el contrato | Reescribir el archivo o confiar en el prompt | El archivo original queda intacto y ninguna tarjeta puede saltarse el contrato |
| T41 | La tarjeta activa, el idioma y la identidad viven en `config/sirah.toml`; `SIRAH_PERSONA` sigue como override temporal | Poner la identidad en la tarjeta o todo en `.env` | Cambiar de personaje no toca código ni secretos; la identidad es una decisión del dueño |
| T42 | Si una tarjeta falla, se avisa con `Solución:` y se arranca con `sirah.json` | Salir con error | Una tarjeta rota no debe impedir conversar |
| T43 | En modo `card` (por defecto) la tarjeta decide cuerpo, afecto y ficción; el piso fijo impide afirmar capacidades reales o hechos no ocurridos | Prohibir toda ficción o dejar que la tarjeta anule la honestidad | La tarjeta manda sin permitir mentir sobre el hardware (A12) |
| T44 | El saludo se inspira en `first_mes` y, si no hay, usa el texto fijo; el historial de la tarjeta por defecto se migra de `default.jsonl` a `sirah.jsonl` con respaldo | Copiar el saludo literal o dejar dos historiales | Evita repetir el mismo saludo y no pierde conversaciones al cambiar de formato |
| T45 | Half-duplex con un `arecord` nuevo por turno: al pararlo se descarta el audio de la pausa; no hay interrupción por voz en v1 | Mantener el proceso y vaciar el buffer del kernel, o dejar el micrófono abierto mientras habla | Es simple y garantiza que no se oiga a sí misma |
| T46 | El audio del turno se envuelve en WAV en memoria y se envía a Groq; nunca toca el disco ni el historial | Guardar WAV temporales o el audio en el historial | Privacidad y menos limpieza; al historial solo va el texto |
| T47 | Piper y `aplay` se comunican por tuberías, sin archivos temporales; la frase siguiente se sintetiza mientras suena la actual | Sintetizar todo antes de hablar o escribir WAV en `/tmp` | Menor latencia y nada que borrar |
| T48 | Si falta clave de Groq, micrófono, `arecord`/`aplay` o Piper, `sirah voice` lo explica con `Solución:` y cae al chat por texto | Salir con error o arrancar sin voz en silencio | La conversación por texto sigue disponible |

## 3. Descartadas

| Opción | Por qué no |
|---|---|
| Endpoint OpenCode Zen/Kimi del `.env` heredado como default | No se verificó que sea gratuito ni su vigencia |
| Ollama como opción por defecto | Sin medición en la Pi; se queda como respaldo configurable |
| `openWakeWord` en v1 | Modelos preentrenados solo en inglés y con licencia no comercial |
| Silero VAD como dependencia base | Añade `onnxruntime`/PyTorch; WebRTC basta para empezar |
| faster-whisper o whisper.cpp en v1 | Groq cubre la voz sin descargar modelos; quedan como adaptadores futuros |
| Kokoro o XTTS v2 | Más peso o licencia no comercial; Piper ya funciona |
| MediaPipe | Otra dependencia y otro modelo sin ventaja para una sola cara |
| Zep en v1 | Nube, clave y créditos; el historial local es suficiente |
| Character cards v1–v3 | El JSON nativo cubre el caso; el formato hay que verificarlo |
| `NOD` en v1 | El firmware lo acepta pero no mueve nada |
| I2C directo o WiFi | Idea futura; solo se deja la interfaz y la dirección |
| Contenedores, ORM, base de datos, framework de plugins | Complejidad sin beneficio para un proceso único |
| Adivinar el puerto serial | Riesgo de mover el dispositivo equivocado |
| Prueba automática de servos al arrancar | Mover hardware sin avisar está prohibido |

## 4. Preguntas abiertas

No bloquean el inicio del hito 0, salvo la primera si se quieren probar los
ojos con placa de banco:

- [ ] **`BENCH_PORT`:** ruta `/dev/serial/by-id/...` del ESP32 de banco. Sin
  ella, los tests de hardware se saltan y se informa; nunca se abre otro
  puerto.
- [ ] Confirmar el sentido izquierda/derecha de la cámara en el hito 3; si está
  invertido, es un cambio de signo.
- [ ] Confirmar la voz Piper en el hito 4 (`es_MX-claude-high` propuesta;
  alternativas `es_ES-davefx-medium` y `es_MX-ald-medium`).
- [ ] Decidir si el panel debe salir de `localhost` en el hito 7; si sí, hará
  falta `PANEL_TOKEN`.

## 5. Historial

- **24/10/2026:** se documentan protocolo, hardware y alternativas; el dueño
  aprueba el plan completo y el stack. Empieza el hito 0.
- **24/10/2026:** hito 0 implementado: configuración, `setup`, `doctor`, logs,
  tests y `uv.lock`. `make check` pasa (52 tests). Repositorio git inicializado
  con el commit del hito 0. La prueba manual del dueño sigue pendiente.
- **24/10/2026:** hito 1 implementado: chat por texto con streaming, persona,
  historial JSONL por persona, saludo, parser de acciones, `--persona` y
  manejo de errores. `make check` pasa (105 tests) y se probó el arranque
  completo con un LLM falso local. La prueba manual del dueño sigue pendiente.
- **25/10/2026:** se corrige el cuelgue de Ctrl-C (hilo daemon y salida `130`)
  y el caso de una `{` partida entre chunks en el parser de acciones. Se añaden
  tests de PTY y de streaming; `make check` pasa (108 tests).
- **25/10/2026:** el dueño valida el hito 0 y confirma el chat por texto. Se
  unifican las ayudas de extras en `uv sync --all-extras` y se clasifican los
  errores del LLM (red, timeout, clave, cuota, 5xx, respuesta inesperada), con
  la causa original en el log y tests de recuperación del chat. `make check`
  pasa con 117 tests.
- **25/10/2026:** segunda prueba manual: diez turnos, Ctrl-C y corte de red
  confirmados. Se elimina el log de consola, se reintenta una respuesta vacía
  (causa: razonamiento de `gpt-oss-20b` consumiendo `max_tokens`), se sube el
  valor por defecto a 512, se refuerza la identidad de robot y se recorta el
  espacio final del stream. `make check` pasa con 124 tests.
- **25/10/2026:** fase 1 de las correcciones aprobadas. Se sube el límite a
  1024 con `reasoning_effort=low`, se registra el uso en cada turno y se avisa
  de los cortes por `length`. El nombre del usuario entra como dato y el
  historial se marca como contexto pasado. Se añade un limpiador de Markdown
  sobre el stream; el mismo texto limpio va al historial y al futuro TTS.
  `make check` pasa con 145 tests.
- **27/10/2026:** el dueño fija la prioridad de capas: la tarjeta manda sobre
  identidad, cuerpo, afecto, saludo, nombre y longitud; el código solo conserva
  un piso fijo (formato, consentimiento, honestidad mínima e historial como
  contexto). `identity = "card"` pasa a ser el modo por defecto y `"robot"` queda
  como modo estricto opcional. Registrado como A12.
- **27/10/2026:** hito 4 (voz) adelantado antes del hito 2. Micrófono por
  `arecord`, VAD con RMS y `webrtcvad`, STT de Groq, Piper y `aplay`, todo
  opt-in con `sirah voice`, half-duplex y audio solo en memoria. `make check`
  pasa con 218 tests; falta la validación física del dueño.
