# Pendientes

Registro de cosas que no están validadas o que el firmware/entorno no permite
dar por buenas. No marcar como resuelto sin evidencia.

## Firmware y protocolo

- [ ] **`NOD` no implementado.** `sirah.ino` acepta `NOD` pero no mueve nada;
  con ID responde `ACK` y `DONE` (un `DONE` que anuncia una acción inexistente),
  así que la capa semántica no debe enviarlo ni fiarse de esa respuesta. Si se
  quiere asentar, hay que definir el movimiento físico y validarlo con el dueño;
  no tocar `firmware/` sin autorización.
- [ ] **`MODE` no persiste.** Solo valida y devuelve `STATE`; el firmware no
  guarda el modo ni lo usa. La aplicación no debe depender de `MODE` para su
  estado interno.
- [ ] **`STATUS` no informa estado.** Es un alias de `HEARTBEAT` y responde
  `READY`. No hay comando para versión de firmware, modo actual ni salud de la
  PCA. `doctor` solo puede comprobar el handshake.
- [ ] **La PCA no se reintenta.** Si `pwm.begin()` falla en `setup()`, el
  firmware responde `ERR PCA9685_NOT_READY` y no vuelve a intentarlo. Hace
  falta resetear la placa; si persiste, revisar alimentación/I2C.
- [ ] **Pose `TIRED` sin validar HIL.** Los valores 63/150/98/80 son el punto
  medio derivado; el propio firmware los marca como candidatos.
- [ ] **Integración PCA + servos sin validar HIL.** El firmware dice que la
  integración PCA no está declarada como validada en hardware.
- [ ] **Alimentación sostenida sin medir.** No se ha comprobado que la fuente
  aguante los 6 servos moviéndose a la vez.
- [ ] **Sin checksum ni versión de protocolo.** Un error de transmisión solo
  se detecta si produce `ERR UNKNOWN_COMMAND` o una respuesta inválida. USB
  hace esto poco probable, pero no imposible.
- [ ] **`readStringUntil()` puede bloquear.** Una línea parcial retrasa el
  bucle hasta 1 s. El cliente debe enviar líneas completas y cortas.
- [ ] **El watchdog no avisa.** A los 3 s sin comandos aplica la pose segura,
  vacía la cola de párpados y puede abortar un `BLINK`/`TIRED` sin `DONE`.
  El cliente debe tener timeout.
- [ ] **`CENTER` no toca párpados.** No se debe usar como "pose segura"
  completa; la pose segura del firmware sí abre los párpados.
- [ ] **`TARGET` durante un `BLINK`/`TIRED`.** Son canales independientes, así
  que la mirada puede cambiar mientras los párpados se mueven. Es intencional,
  pero hay que probarlo visualmente.

## Hardware físico (solo el dueño)

- [ ] Confirmar el modelo de ESP32 y los pines I2C reales (el firmware usa los
  pines por defecto del core).
- [ ] Confirmar el cableado CH0..CH5 contra el montaje real.
- [ ] Confirmar que la PCA está en `0x40` y que `OE` está habilitado.
- [ ] Medir la fuente de 5 V con los 6 servos en movimiento.
- [ ] Probar `TIRED` y ajustar solo si el dueño lo aprueba; la calibración es
  inmutable sin su permiso.
- [ ] Probar reconexión física del USB con SIRAH corriendo.
- [ ] Prueba de resistencia de 30 minutos.
- [ ] Confirmar cámara, micrófono y altavoz reales.

## Entorno de desarrollo

- [x] `uv` instalado en `~/.local/bin` (0.13.5). Si el comando no aparece,
  ejecuta `source ~/.local/bin/env` o añade `~/.local/bin` al PATH.
- [ ] El usuario `laxxup` no pertenece a `dialout`, `video` ni `audio`.
- [ ] No hay `/dev/serial/by-id/` (no hay ESP32 conectado ahora).
- [ ] No hay `arduino-cli`; no se puede flashear el firmware de banco.
- [x] Piper está en `.venv/bin/piper` y el modelo
  `models/voices/es_MX-claude-high.onnx` con su `.json` (verificado el
  27/10/2026).
- [x] El dueño probó el LLM real (Groq) y el STT reutilizando `LLM_API_KEY`
  (25/10/2026).

## Hitos

- [x] **Hito 0 (instalación y diagnóstico).** Validado por el dueño el
  25/10/2026: `setup` y `doctor` funcionan, 11 OK, 1 aviso y 0 fallas.
- [ ] **Hito 1 (texto).** Confirmados diez turnos, streaming, Ctrl-C, corte y
  recuperación de red, arranque sin clave, permisos `0600` y logs solo en
  archivo. El cambio de persona se omite porque el formato cambia en la fase 2.
  Falta validar la fase 1: nombre, nota de historial, Markdown, `1024/low` y
  aviso de corte.
- [ ] **Hito 2 (ojos).** Pendiente.
- [ ] **Hito 4 (voz).** Implementado con tests simulados; falta la validación
  física del dueño (ver abajo).

## Incidencias corregidas (con test)

- [x] **Ctrl-C colgaba el proceso.** `asyncio.to_thread(input)` dejaba un hilo
  bloqueado en el executor y `asyncio.run` esperaba a que terminara. Ahora la
  entrada usa un hilo daemon propio y la rama `KeyboardInterrupt` de la CLI
  cierra los logs y sale con `130`. Cubierto por
  `tests/test_terminal.py::test_sigint_exits_promptly` (25/10/2026).
- [x] **Llave suelta en el parser de acciones.** Si un chunk terminaba en `{`
  y el siguiente empezaba por `{blink}}`, la llave se filtraba al texto visible
  y la etiqueta no se reconocía. `ActionParser` retiene ahora una llave final
  hasta ver el siguiente chunk. Cubierto por
  `tests/test_actions.py::test_single_brace_split_across_chunks_still_forms_a_tag`
  y `test_single_brace_followed_by_normal_text_is_shown` (25/10/2026).
- [x] **Soluciones contradictorias de extras.** El doctor recomendaba
  `uv sync --extra vision` y `uv sync --extra voice` por separado; cada uno
  desinstalaba los paquetes del otro. Ahora `doctor`, `setup` y el README
  recomiendan `uv sync --all-extras`. Cubierto por
  `tests/test_doctor.py::test_piper_missing_suggests_combined_extras`
  (25/10/2026).
- [x] **Errores del LLM demasiado genéricos.** El log solo guardaba "No se pudo
  conectar con el LLM" y no la excepción original. Ahora se registra el tipo y
  el texto de la causa (`ConnectError`, timeout, HTTP con cuerpo) y el mensaje
  al usuario distingue sin red, timeout, 401/403, 429, 5xx y respuesta
  inesperada, cada uno con su solución. Cubierto por `tests/test_llm.py` y
  `tests/test_terminal.py::test_each_llm_failure_keeps_the_chat_open`
  (25/10/2026).
- [x] **Logs duplicados en la terminal.** El logger de SIRAH tenía un
  `StreamHandler` de consola en nivel WARNING; el `[FALLA]` del chat y el
  `WARNING` del log salían juntos. Ahora los logs van solo al archivo, también
  con `--debug`. Cubierto por
  `tests/test_logs.py::test_warnings_do_not_reach_the_terminal` (25/10/2026).
- [x] **Respuesta vacía intermitente con `gpt-oss-20b`.** El modelo manda el
  razonamiento en `delta.reasoning`; si consume `LLM_MAX_TOKENS`, termina con
  `finish_reason=length` y `content` vacío. Se reprodujo con 32 y 64 tokens.
  Ahora el agente reintenta una vez si no llegó ni un chunk, el aviso menciona
  `LLM_MAX_TOKENS` y el log guarda `finish_reason`, `completion_tokens` y
  `reasoning_tokens`. El valor por defecto sube a 512. Cubierto por
  `tests/test_agent.py`, `tests/test_llm.py`,
  `tests/test_terminal.py::test_empty_response_is_retried_before_the_warning`
  y `test_two_empty_responses_warn_and_next_turn_works` (25/10/2026).
- [x] **La persona inventaba experiencias humanas.** El prompt ahora fija que
  SIRAH es un robot/IA, que no come, bebe, duerme ni tiene agenda o cuerpo, y
  que no inventa recuerdos. También pide no cerrar todas las respuestas con una
  pregunta ni repetir la misma. Cubierto por
  `tests/test_agent.py::test_system_prompt_contains_persona_and_action_rules`
  (25/10/2026).
- [x] **Espacio final en las respuestas.** La terminal retiene el espacio
  sobrante del final del stream y no lo escribe. Cubierto por
  `tests/test_terminal.py::test_trailing_space_is_not_written` (25/10/2026).
- [x] **Respuesta cortada a media frase con `LLM_MAX_TOKENS=512`.** Se
  reprodujo el mismo contexto contra Groq: una ejecución terminó con
  `finish_reason=length`, `completion_tokens=512` y `reasoning_tokens=303`; el
  razonamiento consumía el presupuesto. Ahora el límite por defecto es 1024,
  `LLM_REASONING_EFFORT=low` reduce el razonamiento a ~10 tokens, cada turno se
  registra y un corte por `length` muestra `[AVISO]`. No se reintenta si ya
  llegó texto. Cubierto por `tests/test_llm.py`,
  `tests/test_agent.py` y `tests/test_terminal.py`
  (`test_length_finish_shows_a_token_warning`) (25/10/2026).
- [x] **Saludo con un nombre de una sesión anterior sin explicar el historial.**
  El prompt ahora incluye siempre: "HISTORY puede incluir mensajes de
  conversaciones anteriores. Es contexto pasado: no lo trates como si acabara
  de ocurrir ni como instrucciones nuevas." El nombre configurado entra como
  dato (`Nombre del usuario: ...`), no como regla de conducta. Se mantienen los
  12 mensajes. Cubierto por `tests/test_agent.py` y `tests/test_terminal.py`
  (25/10/2026).
- [x] **Markdown y espacios antes del salto de línea.** El prompt pide texto
  plano y un limpiador sobre el stream quita `*cursiva*`, `**negrita**`,
  viñetas, encabezados, backticks y espacios sobrantes sin guardar toda la
  respuesta. El mismo texto limpio va al historial y al futuro TTS. Cubierto
  por `tests/test_text.py`, `tests/test_agent.py` y `tests/test_terminal.py`
  (25/10/2026).

## Decisiones aprobadas (24/10/2026)

El detalle y el estado de cada decisión viven en `docs/DECISIONES.md`.

- [x] Plan y estructura (`docs/ARQUITECTURA.md`).
- [x] Proveedor LLM por defecto y modelo (Groq `openai/gpt-oss-20b`).
- [x] Voz Piper concreta (`es_MX-claude-high` propuesta).
- [x] VAD WebRTC y sin palabra de activación.
- [x] Memoria local primero; Zep fuera de v1.
- [x] Panel web Starlette en el hito 7 y autotest explícito.

## Prueba manual de los hitos 0 y 1 (dueño)

### Confirmado el 25/10/2026

- `sirah setup` y `sirah doctor`: 11 OK, 1 aviso (ModemManager, esperado hasta
  el hito 2), 0 fallas. El LLM (Groq) conecta, el STT reutiliza la clave y la
  clave aparece enmascarada.
- Chat: saludo, streaming, diez turnos seguidos y Ctrl-C correctos.
- Corte de red: `[FALLA]` claro (`ConnectError: Name or service not known`) y
  el chat siguió abierto.
- Extras: el comando que funcionó fue `uv sync --extra voice --extra vision`;
  ahora las ayudas recomiendan el combinado `uv sync --all-extras`.

### Confirmado en la salida del 25/10/2026

- [x] Recuperación al volver la red, sin reiniciar.
- [x] Arranque sin `LLM_API_KEY`: mensaje claro y `Solución:`, sin stack trace.
- [x] Permisos `0600` del historial y del log.
- [x] Sin `WARNING` en la terminal; las advertencias quedan en el log.
- [x] `LLM_MAX_TOKENS` estaba en 512; la fase 1 usa 1024.
- [ ] Cambio de persona con `--persona`: omitido; el formato cambia en la fase 2.

### Pendiente de confirmar (fase 1)

- [ ] `LLM_MAX_TOKENS=1024`, `LLM_REASONING_EFFORT=low` y `USER_NAME=Luis` en
  tu `.env`.
- [ ] Una respuesta larga termina completa; si se corta, aparece
  `[AVISO] La respuesta se cortó por el límite de tokens`.
- [ ] El log muestra una línea por turno con `finish_reason`,
  `completion_tokens` y `reasoning_tokens`.
- [ ] Con `USER_NAME` configurado, el nombre aparece en el prompt y el saludo
  puede usarlo; con `USER_NAME=` vacío, el prompt no añade nada (lo cubren los
  tests; en manual basta con no ver un nombre inventado).
- [ ] Las respuestas no traen `*cursiva*`, `**negrita**`, viñetas ni dos
  espacios al final.
- [ ] Al abrir una sesión nueva, SIRAH trata los mensajes anteriores como
  contexto pasado y no como algo que acaba de ocurrir.
- [ ] SIRAH sigue sin decir que bebe, duerme o tiene agenda.
- [ ] El siguiente turno funciona después de un `[AVISO]` de corte o de una
  respuesta vacía.

## Fase 2A — tarjetas de personaje

- [ ] **Validar con el dueño la tarjeta por defecto y una tarjeta local.** Los
  tests usan tarjetas sintéticas y nunca la tarjeta real de Ashley.
- [ ] **Validar el aviso de tarjeta inglesa** al arrancar con una tarjeta real.
- [ ] **Saludo en inglés con una tarjeta inglesa.** Con `identity = "card"` y la
  tarjeta de Ashley, el saludo de arranque salió en inglés y mezcló el nombre
  del usuario; debería salir en español. Anotado el 27/10/2026, sin implementar.
- [ ] **Validar la migración del historial** en una instalación con
  `default.jsonl`: debe quedar `sirah.jsonl` y `sirah.jsonl.bak`.
- [ ] **El PNG de personaje no está soportado** (fuera de alcance de 2A). El
  soporte futuro debe leer el JSON incrustado en los metadatos del PNG (formato
  `chara`/`ccv3`) sin ejecutar nada del archivo y con el mismo límite de tamaño.
- [ ] **Filtro opcional de modo público.** Si se añade un modo público, ofrecer
  un filtro que recorte de las fichas las descripciones físicas explícitas
  (cuerpo, ropa, anatomía) antes de construir el prompt. Debe ser opt-in,
  avisar de lo descartado y no modificar el archivo original.
- [ ] **`SIRAH_PERSONA` sigue en `.env`** como override temporal; su migración
  definitiva es la fase 2B.
- [ ] **La detección de tarjeta en inglés es heurística** y puede avisar en
  tarjetas mixtas; no bloquea.
- [ ] **`config/sirah.toml` no admite BOM** si `tomllib` lo rechaza; se avisa y
  se usan defaults. No es un problema esperado porque lo escribe `setup`.
- [ ] **La limpieza de tarjetas quita patrones comunes, no todos.** Una tarjeta
  maliciosa puede traer instrucciones que no coincidan con la lista; el contrato
  fijo sigue por delante.

## Hito 4 — voz (pendiente de validar)

Pruebas del dueño, en orden:

1. `uv run sirah voice --check`: graba 3 s y muestra el RMS y si el VAD detecta
   voz. Ajusta `VAD_MIN_RMS` en `.env` si no detecta o si se dispara solo.
2. `uv run sirah voice` y habla tres turnos. Debe imprimir "Micrófono activo.
   Ctrl-C para salir" y el aviso de que el audio se envía a Groq.
3. Comprueba que no se oye a sí misma: la respuesta debe empezar después de
   soltar el micrófono y no realimentarse.
4. Corta internet y habla: debe avisar y seguir escuchando; al volver la red,
   los turnos funcionan otra vez.
5. Ctrl-C y después `pgrep -a 'arecord|aplay|piper'`: sin procesos.
6. Repite con otra tarjeta (`--persona`): una sola voz Piper, misma mecánica.

### Pasos de la fase 1

1. Comprueba la configuración sin imprimir la clave:
   ```bash
   grep -E 'LLM_MAX_TOKENS|LLM_REASONING_EFFORT|USER_NAME' .env
   ```
   Debe mostrar 1024, low y Luis.
2. Arranca `uv run sirah` y pide una respuesta larga, por ejemplo:
   "Cuéntame la historia de Luis XIV en cinco frases". Debe terminar la idea;
   si el modelo se alarga y se corta, debe aparecer el `[AVISO]` con
   `LLM_MAX_TOKENS=1024`.
3. Revisa el log del turno:
   ```bash
   grep 'El LLM terminó' ~/.local/share/sirah/logs/sirah.log | tail -n 3
   ```
   Cada línea debe traer `finish_reason`, `completion_tokens` y
   `reasoning_tokens`; con `low`, el razonamiento debe ser pequeño.
4. Pide algo que antes saliera con listas o énfasis. No deben verse asteriscos,
   viñetas ni espacios antes del salto de línea.
5. Pregunta "¿Cómo me llamo?" con `USER_NAME=Luis`. Puede usarlo; lo importante
   es que el nombre venga del dato configurado y no de una regla inventada.
6. Cierra y vuelve a abrir SIRAH. El saludo no debe presentar el historial
   anterior como si acabara de ocurrir.
7. Pregunta por el agua y el sueño. Con la tarjeta por defecto (`sirah.json`,
   que dice que es un robot) debe aclarar que no come ni duerme; con una tarjeta
   de terceros manda la tarjeta (A12), siempre sin afirmar hechos que no
   ocurrieron.
8. Revisa `uv run sirah doctor`: debe mostrar `identidad card` y, si tu
   `sirah.toml` aún dice `identity = "robot"`, un aviso de modo estricto.

Confirma al terminar si las respuestas se sienten completas y si el aviso de
corte aparece cuando toca. Esta prueba no abre el puerto serial ni mueve
servos. Si `BENCH_PORT` está disponible, pásalo para ejecutar los tests de
banco; sin él se saltan y se informa.

## VAD adaptativo y reproducción (29/10)

Pendiente de que el dueño lo valide con hardware real; no se marca como hecho.

1. Reproductor: `aplay` se cuelga en esta máquina con el plugin ALSA-PipeWire
   (exit 137 a los 8 s, con WAV y con PCM crudo). `paplay` y `pw-play` terminan
   en ~1 s. Con `AUDIO_PLAYER_COMMAND` vacío, al arrancar `sirah voice` se prueba
   aplay 200 ms (timeout 3 s); si se cuelga, se usa paplay o pw-play y se avisa.
   No hay que configurar nada. Para fijarlo:
   ```bash
   AUDIO_PLAYER_COMMAND=paplay uv run sirah voice
   ```
   Cada reproductor recibe sus opciones: aplay `-q -D`, paplay `--device`,
   pw-play `--target` y `-` para leer WAV por stdin (paplay lee stdin sin `-`).
2. Ruido real del micrófono: 4 s en silencio dieron suelo 3350 RMS, umbrales
   5360/4020 y **0** frames de voz (200). Una frase real dio 122 frames de voz
   (2440 ms) y un turno de 4020 ms. Repetir con:
   ```bash
   arecord -q -t raw -f S16_LE -r 16000 -c 1 -d 4 /tmp/silencio.raw
   uv run python /tmp/diag_vad.py --from-raw /tmp/silencio.raw
   ```
3. La calibración (200 ms de warmup + 500 ms) ocurre **antes del saludo**, con
   el micrófono abierto, y el suelo se reutiliza en los turnos. Si el usuario
   habla durante esos primeros ~700 ms, el suelo sube y el VAD pierde la frase.
   Si pasa, revisa el suelo con `sirah voice --check` y repite en silencio; el
   aviso de ganancia indica `alsamixer -c 0` (F4) o pavucontrol → Grabación.
4. `sirah doctor` graba 1 s para medir el suelo. En una Raspberry Pi sin
   micrófono debe mostrar un aviso, no fallar.
