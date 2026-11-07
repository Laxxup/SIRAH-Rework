# SIRAH

Robot conversacional por texto y voz para Linux. Combina un LLM, tarjetas de
personaje, memoria local y voz. Proyecto de la Comunidad Robótica, taller de
alumnos del TEC de Madero; dirigido a compañeros, evaluadores y futuros
integrantes. El repositorio incluye el firmware de los ojos animatrónicos, pero
la aplicación todavía no envía órdenes al hardware.

## Estado

| Área | Estado | Evidencia |
|---|---|---|
| Texto | Funciona | Chat, tarjetas, memoria e historial JSONL; pruebas offline |
| Voz | Parcial | STT, TTS y VAD implementados; conversación validada en una máquina |
| Ojos | Parcial | Firmware y protocolo escritos; extremos calibrados; HIL pendiente |
| Visión | Parcial | `VISION_ENABLED` opt-in; captura y seguimiento con receptor nulo; webcam real y Pi 4B sin validar |

Lo que no aparece como validado aquí no está validado. Los detalles y criterios
de cierre están en `docs/PENDIENTES.md`.

## Requisitos y hardware

- Python 3.12, `uv` y Linux.
- Una clave de LLM compatible con OpenAI. Por defecto, Ollama Cloud con
  `gemma4:31b`; `sirah setup` también ofrece Groq con `gpt-oss-20b`.
- Voz opcional: `uv sync --all-extras`, Piper y `arecord` (ALSA) para captura.
- Reproducción: `aplay` (ALSA) o `paplay`/`pw-play` (PulseAudio/PipeWire).
- Ojos opcionales: usuario en el grupo `dialout`.

| Componente | Cantidad | Estado |
|---|---:|---|
| ESP32 | 1 | Modelo por confirmar; firmware y protocolo escritos, HIL pendiente |
| PCA9685 (dirección `0x40`) | 1 | Canales definidos; integración con servos pendiente |
| Servo SG90 | 6 | Extremos validados; `TIRED` y alimentación pendientes |
| Fuente externa de 5 V | 1 | Amperaje real sin medir |
| Cámara USB | 1, opt-in | Modelo YuNet incluido; captura y seguimiento sin implementar |
| Micrófono y altavoz | 1 + 1, opt-in | Voz validada en una máquina; faltan pruebas de ruido, red y cierre |

La lista de componentes, el cableado y la alimentación están en
`docs/HARDWARE.md`. El firmware y su compilación están en
[`firmware/README.md`](firmware/README.md); el flasheo físico aún no está
documentado.

## Instalación y uso

```bash
uv sync --all-extras
uv run sirah setup
uv run sirah doctor
uv run sirah
```

Para solo texto, `uv sync` es suficiente. `setup` configura `.env` y
`config/sirah.toml`, y puede descargar la voz. `doctor` no abre el puerto
serial.

```bash
uv run sirah voice
uv run sirah voice --check
```

`voice --check` graba al menos 3 segundos y muestra RMS y VAD. `--persona RUTA`
permite arrancar con otra tarjeta de personaje.

## Configuración

- `.env`: `LLM_API_KEY` es obligatoria. El proveedor y el modelo por defecto son
  Ollama Cloud y `gemma4:31b`; `sirah setup` permite elegir Groq. `GROQ_API_KEY`
  es obligatoria para la voz salvo que el LLM ya sea Groq. `EYES_ADDRESS` y
  `SIRAH_DATA_DIR` son opcionales.
- `config/sirah.toml`: tarjeta activa, idioma e identidad (`card` o `robot`).
  La tarjeta no puede cambiar la identidad. `SIRAH_PERSONA` y `--persona` solo
  eligen tarjeta.
- Historial y logs: `$XDG_DATA_HOME/sirah`. Hay un historial por tarjeta.
- `doctor` consulta el saldo de Ollama Cloud cuando el proveedor es Ollama; no
  hay plan gratuito verificado para `gemma4:31b`.

## Validación

```bash
make check
make guard
uv run sirah doctor --offline
uv run sirah voice --check
```

`make check` ejecuta Ruff y pytest sin red ni hardware. `make guard` falla si se
modifican `firmware/`, `config/eyes-calibration.toml` o `models/`. La validación
de hardware es manual. CI ejecuta `make check` en cada push y pull request
(`.github/workflows/check.yml`).

## Limitaciones

- La aplicación no controla los ojos por serial todavía.
- `TIRED`, la alimentación sostenida, la reconexión y la integración PCA+servos
  siguen pendientes de prueba HIL.
- En voz faltan VAD con ruido real, corte de red, cierre limpio y arranque sin
  micrófono.
- La visión es opt-in (`VISION_ENABLED=false` por defecto): captura y sigue la
  cara, pero el receptor es nulo y no mueve los ojos. Webcam real y Pi 4B sin
  validar.
- El texto del chat se envía al proveedor del LLM (Ollama Cloud por defecto) y
  el audio a Groq para transcribir; no hay modo local por defecto.
- El modelo exacto del ESP32 y el consumo real de la fuente de 5 V no están
  confirmados.

## Contribuir

Lee `CONTRIBUTING.md`. Antes de enviar cambios, ejecuta `make check` y
`make guard`. Los cambios en `firmware/`, `config/eyes-calibration.toml` y
`models/` requieren aprobación del supervisor. Las reglas de `BENCH_PORT` y de
hardware están en `CONTRIBUTING.md` y `AGENTS.md`.

## Créditos y contacto

Comunidad Robótica, taller de alumnos del TEC de Madero. Supervisor: @Laxxup.
Integrantes: alumnos del taller de Comunidad Robótica. Contacto: GitHub Issues.

Mecánica: EyeMech ε3.2 de Will Cogley. No se incluyen sus archivos STL.

## Licencias

- Código del repositorio, incluido el sketch: MIT. Ver [`LICENSE`](LICENSE).
- Mecánica EyeMech ε3.2:
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), de
  [Will Cogley](https://github.com/will-cogley/EyeMech_Epsilon). No se
  redistribuyen los STL. Para uso comercial hay que contactar al autor.
- Modelo YuNet: MIT. Ver [`models/LICENSE.yunet`](models/LICENSE.yunet).
- Firmware: las librerías Adafruit PWM Servo Driver (BSD) y Adafruit BusIO
  (MIT) tienen sus propias licencias. Ver `firmware/README.md`.
- Piper, voces y modelos descargados: revisar sus licencias respectivas.
