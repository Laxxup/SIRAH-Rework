# SIRAH

SIRAH es un robot conversacional por texto y voz. El chat por texto solo
necesita una clave LLM; la voz requiere audio real y Piper. Los ojos, la
visión y los servos llegan en los hitos 2 y 3; por ahora las etiquetas
`{{look}}`, `{{blink}}`, `{{tired}}` y `{{center}}` se analizan y se
descartan.

Está pensado para Linux (x86_64 o Raspberry Pi aarch64), sin contenedores ni
GPU. Sin configurar `EYES_ADDRESS`, SIRAH sigue funcionando por texto y puede
usar voz si el audio está disponible.

> **Estado:** hitos 0, 1 y 4 implementados. Texto y voz funcionan; se validó una
> conversación por voz en esta máquina. Hito 2 es el siguiente. Ojos y visión
> aún no existen físicamente. Este README se actualiza en cada hito.
## Requisitos

- Python 3.12 (`uv` lo instala si hace falta) y [`uv`](https://docs.astral.sh/uv/).
- Una sola clave LLM. Si ya usas Groq, se reutiliza `LLM_API_KEY`; si no,
  añade `GROQ_API_KEY` para la voz.
- Para voz: `alsa-utils` (`arecord`, `aplay`), Piper y su modelo.
- Para ojos: ESP32, firmware en `firmware/`, grupo `dialout` y ruta
  `/dev/serial/by-id/...`.
- Para visión: cámara V4L2 y grupo `video` (pendiente de implementación).

## Inicio rápido

```bash
uv sync --all-extras
uv run sirah setup
uv run sirah doctor
uv run sirah
```

```bash
uv run sirah voice       # conversación manos libres, opt-in
uv run sirah voice --check   # graba al menos 3 s y muestra RMS y VAD
uv run sirah --persona config/persona/otra.json
uv run sirah doctor --offline
```

`sirah setup` crea `.env` con permisos restringidos, copia
`config/sirah.toml.example` a `config/sirah.toml`, detecta ESP32, cámara y
audio, y ofrece descargar la voz. La única configuración obligatoria para
conversar es `LLM_API_KEY`.

`sirah doctor` no abre el serial: abrirlo reinicia el ESP32 y mueve servos.
La prueba real requiere confirmación.

## Configuración y datos

Tarjeta activa, idioma e identidad se eligen en `config/sirah.toml`
(`card` por defecto, `personaje` de alias, `robot` como modo estricto).
`--persona` tiene prioridad. Una tarjeta rota no impide arrancar.

SIRAH conserva por defecto los últimos 12 mensajes por tarjeta
(`MEMORY_MESSAGES`, `MEMORY_PERSIST=true`); el saludo de arranque se guarda como primer turno `assistant`.
`USER_NAME` entra como dato y es global para todas las tarjetas. El idioma y la
identidad de `config/sirah.toml` también son globales y sobreviven al cambiar de
tarjeta. Los logs usan `$XDG_DATA_HOME/sirah/logs/sirah.log`,
con `--debug` y rotación de 3 archivos de 1 MB. Las etiquetas `{{look}}`,
`{{blink}}`, `{{tired}}` y `{{center}}` se quitan del texto siempre.

## Voz

- Privacidad: el audio se envía a Groq y no se guarda; el historial queda en
  texto.
- Half-duplex: micrófono parado mientras habla; no hay interrupción por voz.
- Turnos sin pausa: se recorta tras `VAD_MAX_TURN_MS` (10 s por defecto).
- Configura `VAD_MIN_START_RMS` y `VAD_MIN_END_RMS` con `voice --check`; deja
  el de fin por debajo del de inicio.
- Ctrl-C detiene `arecord`, Piper y el reproductor. `aplay` puede colgarse
  con PipeWire: se autoselecciona `paplay` o `pw-play`, o fórzalo con
  `AUDIO_PLAYER_COMMAND`.

## Limitaciones conocidas

- Ojos, visión y servos aún no están implementados; las etiquetas se descartan.
- La voz está implementada y se validó una conversación completa en esta
  máquina. Siguen pendientes el VAD con ruido, el corte de internet y el
  cierre limpio.
- El firmware no implementa `NOD` ni persiste `MODE`.
- La pose `TIRED`, la alimentación sostenida y el rendimiento en Raspberry Pi no
  están validados.
- Sin `BENCH_PORT`, las pruebas de hardware se saltan y no se abre otro puerto.
- Las tarjetas locales no se versionan; `doctor` muestra la identidad.

## Documentación

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md): estructura y decisiones.
- [`docs/HARDWARE.md`](docs/HARDWARE.md): cableado, canales, calibración.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md): protocolo serial del ESP32.
- [`docs/PENDIENTES.md`](docs/PENDIENTES.md): lo que falta validar.
- [`docs/DECISIONES.md`](docs/DECISIONES.md): decisiones y estado.
- [`config/persona/README.md`](config/persona/README.md): Character Card v2/v3.

## Licencias

- **Ojos ε-Series:** CC BY-NC-SA 4.0. Atribución obligatoria; no comercial sin
  permiso.
- **Piper TTS:** GPL-3.0-or-later, como proceso separado.
- **YuNet:** MIT. **Código nuevo:** MIT (`LICENSE`).
