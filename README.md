# SIRAH

**S.I.R.A.H.** (Sistema Inteligente Robótico de Asistencia Humana) es un robot
conversacional por texto y voz. El chat por texto solo necesita una clave LLM;
la voz requiere audio real y Piper. Los ojos, la visión y los servos llegan en
los hitos 2 y 3; por ahora las etiquetas `{{look}}`, `{{blink}}`, `{{tired}}` y
`{{center}}` se analizan y se descartan.

Está pensado para Linux (x86_64 o Raspberry Pi aarch64), sin contenedores ni
GPU. Sin configurar `EYES_ADDRESS`, SIRAH funciona por texto y puede usar voz si
el audio está disponible.

> **Estado:** hitos 0, 1 y 4 implementados. El texto y la voz funcionan; se
> validó una conversación completa por voz en esta máquina. El hito 2 es el
> siguiente. Los ojos y la visión aún no existen físicamente. Este README se
> actualiza al cerrar cada hito.

## Requisitos

- Linux con Python 3.12 (`uv` lo instala si hace falta).
- [`uv`](https://docs.astral.sh/uv/).
- Para voz real: `alsa-utils` (`arecord`, `aplay`), Piper y su modelo.
- Para voz: una sola clave LLM. Si el proveedor ya es Groq, se reutiliza
  `LLM_API_KEY`; si no, añade `GROQ_API_KEY`.
- Para ojos: ESP32 con el firmware de `firmware/`, cable USB, grupo `dialout`
  y una ruta `/dev/serial/by-id/...` en `EYES_ADDRESS`.
- Para visión: cámara V4L2 y grupo `video` (pendiente de implementación).

## Inicio rápido

```bash
uv sync --all-extras
uv run sirah setup
uv run sirah doctor
uv run sirah
```

Uso básico:

```bash
uv run sirah             # chat por texto; /salir para terminar
uv run sirah voice       # voz manos libres, opt-in
uv run sirah voice --check   # graba al menos 3 s y muestra RMS y VAD
uv run sirah doctor --offline
uv run sirah --persona config/persona/otra.json
```

`sirah setup` crea `.env` con permisos restringidos, copia
`config/sirah.toml.example` a `config/sirah.toml`, detecta ESP32, cámara y
audio, y ofrece descargar la voz de Piper. La única configuración obligatoria
para conversar es `LLM_API_KEY`.

`sirah doctor` no abre el puerto serial: abrirlo reinicia el ESP32 y mueve
servos. El handshake real es explícito y con confirmación.

## Configuración y datos

La tarjeta activa, idioma y modo de identidad se eligen en
`config/sirah.toml` (`card` por defecto, `personaje` como alias, `robot` como
modo estricto). `--persona` tiene prioridad. Una tarjeta rota no impide
arrancar: se avisa y se usa `sirah.json`.

SIRAH conserva por defecto los últimos 12 mensajes por tarjeta
(`MEMORY_MESSAGES`, `MEMORY_PERSIST=true`) y no guarda el saludo de arranque en
el historial. `USER_NAME` entra como dato de conversación, no como regla.

Los logs van solo a `$XDG_DATA_HOME/sirah/logs/sirah.log` (rotación de 3
archivos de 1 MB); con `--debug` se registran trazas. Las etiquetas de
acción (`{{look}}`, `{{blink}}`, `{{tired}}`, `{{center}}`) se quitan del texto
siempre, también del TTS.

## Voz

- **Privacidad:** el audio se envía a Groq para transcribirlo y no se guarda en
  disco; al historial va el texto transcrito.
- **Half-duplex:** micrófono parado mientras habla; no hay interrupción por
  voz.
- **Turnos:** sin pausa, se recorta a `VAD_MAX_TURN_MS` (10 s por defecto).
- **Ajuste:** `voice --check` graba al menos 3 s y muestra RMS/VAD. Ajusta
  `VAD_MIN_START_RMS` y `VAD_MIN_END_RMS` en `.env`; deja el umbral de fin por
  debajo del de inicio.
- **Cierre:** Ctrl-C detiene `arecord`, Piper y el reproductor antes de salir.
- **Reproductor:** `aplay` puede colgarse con PipeWire; SIRAH prueba 200 ms y,
  si falla, usa `paplay` o `pw-play`. Se puede forzar con
  `AUDIO_PLAYER_COMMAND`.

## Limitaciones conocidas

- Los ojos, la visión y el movimiento de servos no están implementados todavía.
- La voz está implementada y se validó una conversación completa en esta
  máquina. Siguen pendientes el VAD con ruido constante, el corte de internet
  y el cierre limpio (ver `docs/PENDIENTES.md`).
- `aplay` puede colgar bajo PipeWire, aunque se autoselecciona `paplay` o
  `pw-play`.
- El firmware no implementa `NOD` ni persiste `MODE`.
- La pose `TIRED`, la alimentación sostenida y el rendimiento en Raspberry Pi
  no están validados.
- Sin `BENCH_PORT`, las pruebas de hardware se saltan y no se abre otro puerto.
- Las tarjetas locales no se versionan; `doctor` muestra la identidad efectiva.

## Documentación

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md): estructura, flujos y
  decisiones.
- [`docs/HARDWARE.md`](docs/HARDWARE.md): cableado, canales, calibración.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md): protocolo serial del ESP32.
- [`docs/PENDIENTES.md`](docs/PENDIENTES.md): lo que falta validar.
- [`docs/DECISIONES.md`](docs/DECISIONES.md): decisiones y su estado.
- [`docs/SUGERENCIAS.md`](docs/SUGERENCIAS.md): alternativas y fuentes.
- [`config/persona/README.md`](config/persona/README.md): Character Card v2/v3.

## Licencias y créditos

- Ojos animatrónicos: ε-Series, CC BY-NC-SA 4.0. Atribución obligatoria; no
  uso comercial sin permiso.
- Piper TTS: GPL-3.0-or-later, invocado como proceso separado.
- Modelo YuNet: MIT.
- Código nuevo de SIRAH: MIT (`LICENSE`).
