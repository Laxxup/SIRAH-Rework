# SIRAH

**S.I.R.A.H.** (Sistema Inteligente Robótico de Asistencia Humana) es un robot
conversacional por texto y voz. El chat por texto funciona solo con una clave de
LLM; la voz requiere hardware de audio y Piper. Los ojos, la visión y el
movimiento de servos llegan en el hito 2 y siguientes; por ahora las etiquetas
`{{look}}`, `{{blink}}`, `{{tired}}` y `{{center}}` se analizan y se descartan.

Está pensado para Linux (x86_64 y Raspberry Pi aarch64), sin contenedores y sin
GPU. Sin configurar `EYES_ADDRESS`, SIRAH sigue funcionando por texto y puede
usar voz si el audio está disponible.

> **Estado:** hitos 0, 1 y 4 implementados. El texto y la voz manos libres
> funcionan; el dueño confirmó la conversación por voz en esta máquina con su
> micrófono y altavoz. El hito 2 es el siguiente. Los ojos y la visión aún no
> existen físicamente. Este README se actualiza al cerrar cada hito.

## Requisitos

- Linux con Python 3.12 (lo instala `uv` si hace falta).
- [`uv`](https://docs.astral.sh/uv/).
- Para ojos: ESP32 con el firmware de `firmware/`, cable USB y permisos en el
  grupo `dialout`. Usa siempre una ruta `/dev/serial/by-id/...` en
  `EYES_ADDRESS`.
- Para visión: cámara V4L2 y permisos en el grupo `video`.
- Para voz: `alsa-utils` (`arecord`, `aplay`), Piper y un modelo de voz.
- Para voz: una sola clave LLM. Si ya usas Groq, SIRAH reutiliza `LLM_API_KEY`;
  si no, añade `GROQ_API_KEY` para el STT.

## Inicio rápido

```bash
# 1. Instalar uv (solo la primera vez)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 2. Dependencias
uv sync

# 3. Configuración guiada
uv run sirah setup

# 4. Diagnóstico
uv run sirah doctor

# 5. Conversar
uv run sirah
```

`sirah setup` crea `.env` con permisos restringidos, copia
`config/sirah.toml.example` a `config/sirah.toml`, detecta el ESP32, la cámara y
el audio, y ofrece descargar la voz de Piper. La única configuración obligatoria
para conversar es `LLM_API_KEY`.

## Extras opcionales

```bash
uv sync --all-extras   # voz (Piper + VAD)
```

Instala todos los extras de una vez. `uv sync` con un solo `--extra` desinstala
los paquetes de los demás, así que evita ejecutarlos por separado.

## Uso

```bash
uv run sirah             # chat por texto; escribe /salir para terminar
uv run sirah --persona config/persona/otra.json   # una tarjeta concreta
uv run sirah voice       # conversación manos libres (opt-in)
uv run sirah voice --check   # graba al menos 3 s y muestra nivel RMS y VAD
uv run sirah doctor      # diagnóstico con soluciones
uv run sirah setup       # configuración guiada
```

El chat responde en streaming, guarda un historial local acotado por tarjeta y
carga la personalidad desde tarjetas Character Card v2/v3
([detalles](config/persona/README.md)). La tarjeta activa, el idioma y el modo
de identidad se eligen en `config/sirah.toml`: `card` por defecto (manda la
tarjeta; `personaje` es alias) y `robot` como modo estricto opcional. Una
tarjeta rota no impide arrancar: se avisa y se usa `sirah.json`. Las tarjetas
locales no se versionan. `doctor` muestra la identidad efectiva y avisa si el
modo estricto está activo. SIRAH conserva por defecto los últimos 12 mensajes
por tarjeta (`MEMORY_MESSAGES`) y los persiste si `MEMORY_PERSIST=true`; el
saludo de arranque no se guarda en el historial. `USER_NAME` entra como dato de
conversación.

Los logs van solo a `$XDG_DATA_HOME/sirah/logs/sirah.log`; la terminal no
muestra advertencias del logger. Usa `--debug` para más detalle. El log se
rota en 3 archivos de 1 MB por defecto. Las etiquetas de acción del LLM
(`{{look}}`, `{{blink}}`, `{{tired}}`, `{{center}}`) se analizan y se quitan
del texto; mover los ojos llega en el hito 2.

Los comandos de ojos y panel se añaden en sus hitos. `sirah doctor` no
abre el puerto serial: abrirlo reinicia el ESP32 y mueve los servos. Esa prueba
es explícita, con aviso y confirmación.

### Voz (hito 4)

La voz nunca se activa sola: solo con `uv run sirah voice`. Solo necesita una
clave: si tu LLM ya es Groq, SIRAH reutiliza `LLM_API_KEY`; si no, añade
`GROQ_API_KEY`. También necesita `arecord` de `alsa-utils`, un reproductor
(`aplay`, `paplay` o `pw-play`) y Piper con su modelo. Si falta algo, SIRAH lo
explica con `Solución:` y sigue por texto.

- **Privacidad:** el audio del micrófono se envía a Groq para transcribirlo y
  **no se guarda en disco**; solo queda en memoria durante el turno. Al
  historial va el texto transcrito.
- **Half-duplex:** el micrófono se detiene mientras SIRAH habla y se reinicia
  vacío al terminar, para no oírse a sí misma. En esta versión no se interrumpe
  por voz.
- **Turnos largos:** un turno sin pausas termina tras
  `VAD_MAX_TURN_MS` (10 s por defecto) y se envía igualmente; habla en frases
  breves si quieres evitar el recorte.
- **Ajuste:** `uv run sirah voice --check` graba al menos 3 segundos y muestra
  el nivel RMS y si el VAD detecta voz. Ajusta `VAD_MIN_START_RMS` y
  `VAD_MIN_END_RMS` en `.env`, dejando siempre el de fin por debajo del de
  inicio.
- **Cierre:** Ctrl-C detiene `arecord`, `piper` y el reproductor de audio antes
  de salir.
- **Reproductor:** `aplay` puede colgarse con PipeWire; SIRAH prueba 200 ms y,
  si falla, prueba `paplay` o `pw-play`. Puedes forzarlo con
  `AUDIO_PLAYER_COMMAND`.

Puedes consultar [`docs/PENDIENTES.md`](docs/PENDIENTES.md) para ver qué queda por
validar con hardware real.

## Documentación

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — estructura, flujos y
  decisiones de diseño.
- [`docs/HARDWARE.md`](docs/HARDWARE.md) — cableado, canales y calibración.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — protocolo serial del ESP32.
- [`docs/SUGERENCIAS.md`](docs/SUGERENCIAS.md) — alternativas y fuentes.
- [`docs/DECISIONES.md`](docs/DECISIONES.md) — decisiones y su estado.
- [`docs/PENDIENTES.md`](docs/PENDIENTES.md) — lo que falta validar.

## Limitaciones conocidas

- Los ojos y la visión aún no están implementados; el chat por texto y la voz
  funcionan sin ellos. Las etiquetas de acción se descartan sin mover hardware.
- La voz está implementada y el dueño confirmó una conversación completa por
  texto/voz en esta máquina: micrófono, Groq STT, LLM y Piper con `paplay`.
  Siguen pendientes el VAD con ruido constante, el corte de internet y el cierre
  limpio con Ctrl-C. La voz acepta turnos de hasta 10 s por defecto.
- El firmware no implementa `NOD` ni persiste `MODE`; SIRAH no los usa.
- La pose `TIRED` y la alimentación sostenida de los servos aún no están
  validadas en el robot real.
- Sin `BENCH_PORT`, las pruebas de hardware se saltan; nunca se abre otro
  puerto serial.
- El rendimiento en Raspberry Pi no se ha medido todavía.

## Licencias y créditos

- Mecanismo de ojos: **ε-Series Animatronic Eye Mechanism** de Will Cogley /
  NM Robotics, licencia **CC BY-NC-SA 4.0**. Atribución obligatoria; no se
  permite uso comercial del mecanismo.
- **Piper TTS**: GPL-3.0-or-later. SIRAH lo invoca como proceso separado.
- Modelo **YuNet**: MIT.
- Código nuevo de SIRAH: **MIT** (ver [`LICENSE`](LICENSE)).
