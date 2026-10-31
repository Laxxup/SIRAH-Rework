# Sugerencias de stack y alternativas

Investigación hecha el **24/10/2026**. Criterios, en orden: estabilidad,
facilidad de instalación, costo cero, funcionamiento sin internet cuando se
pueda, licencia, calidad en español y rendimiento sin GPU (incluida una
Raspberry Pi).

Los datos de planes gratuitos y versiones cambian sin aviso. Cada dato lleva
su fuente y la fecha de consulta. Lo que no se pudo verificar se marca como
**sin verificar**.

## Resumen de recomendaciones

| Pieza | Opción actual / heredada | Recomendación | Cambio |
|---|---|---|---|
| LLM | Endpoint OpenAI-compatible; `.env` apunta a OpenCode Zen/Kimi | **Groq Free** con `openai/gpt-oss-20b`; configurable | Sí |
| STT | Groq `whisper-large-v3-turbo` | **Groq `whisper-large-v3-turbo`** | No |
| TTS | Piper; voz `es_MX-claude-high` | **Piper + `es_MX-claude-high`**, invocado como proceso | No (se fija la voz) |
| Visión | OpenCV + YuNet | **YuNet 2023mar con OpenCV 4.x** | No (se fija versión) |
| VAD | VAD por energía/RMS (heredado) | **WebRTC VAD + umbral RMS** | Sí |
| Palabra de activación | Ninguna | **Omitir en v1** | No |
| Memoria | Historial local; Zep opcional | **Historial local primero; Zep solo opt-in** | No |
| Serial | `pyserial` | **`pyserial`** | No |
| HTTP | Sin definir | **`httpx`** para SSE, multipart y timeouts | Sí |
| Panel web | Sin definir | **Starlette + uvicorn** como extra opcional, sin build de frontend | Se decide en hito 7 |
| Hardware | Fuente externa para servos | **5 V/5 A, masa común, 1000 µF, cables cortos** | Sí (sugerencia) |

Nada de esto se adopta hasta que el dueño apruebe el plan. Hasta entonces rige
la sección 9 de `AGENTS.md`.

---

## 1. LLM

### Opción actual

Endpoint compatible con OpenAI (`/chat/completions`, Bearer, SSE). El
`.env.example` heredado apunta a `https://opencode.ai/zen/go/v1` con
`kimi-k2.6`, pero no hay una decisión vigente ni un plan gratuito verificado
para ese endpoint. Se puede usar cualquier proveedor compatible cambiando
`LLM_BASE_URL` y `LLM_MODEL`.

### Alternativas evaluadas

| Opción | Por qué conviene | Límites gratuitos | Licencia / costo | Esfuerzo | Riesgos |
|---|---|---|---|---|---|
| **Groq Free** (recomendada) | Muy rápido, OpenAI-compatible, mismo proveedor que STT, sin GPU local | `openai/gpt-oss-120b` y `gpt-oss-20b`: 30 RPM, 1.000 req/día, 8K tokens/min, 200K tokens/día; `qwen/qwen3.8-27b` con límites similares | Servicio gratuito con límites; sin licencia de código | Bajo | Límite diario de tokens; puede cambiar; datos en la nube; 429 |
| Google Gemini API Free | Buena calidad en español, modelos Flash gratuitos | La página oficial no publica RPM/RPD por modelo; se consultan en AI Studio. El plan Free existe para Gemini 3.8/3.6 Flash, 3.5/3.1 Flash-Lite y Gemma 4 | Gratis con límites; el contenido del plan Free se usa para mejorar productos | Medio | Límites no publicados y variables; datos usados para entrenamiento; otra clave |
| OpenRouter Free | Un solo API compatible con muchos modelos `:free` | 20 RPM; 50 req/día con menos de 10 USD comprados; 1.000 req/día tras comprar 10 USD | Gratis con límites; modelos con licencias variadas | Bajo | 50/día es insuficiente para una conversación de 30 min; capacidad variable |
| Ollama local | Sin internet, sin clave, sin cuota; privacidad total | Sin límite de API; limitado por RAM/CPU | Gratis, código abierto | Medio | En Raspberry Pi 5 los modelos pequeños van lentos; descarga y RAM; calidad inferior a un modelo grande |

### Recomendación

**Groq Free como proveedor por defecto**, con `LLM_MODEL=openai/gpt-oss-20b`
para respuestas rápidas y la posibilidad de cambiar a `openai/gpt-oss-120b`
sin tocar código. Mantener el cliente genérico OpenAI-compatible para que el
dueño pueda usar Gemini, OpenRouter u Ollama cambiando tres variables.

- No usar el endpoint de OpenCode Zen/Kimi del `.env` heredado como default:
  no se verificó que sea gratuito.
- Limitar el historial a 12 mensajes. Para texto, `LLM_MAX_TOKENS=1024` con
  `LLM_REASONING_EFFORT=low`; si la cuota de 200K tokens/día aprieta, bajar a
  512. El razonamiento consume el mismo presupuesto que la respuesta.
- Manejar 429 y 5xx con espera creciente y un mensaje claro; no bloquear la
  conversación.
- Ollama queda como **respaldo opcional sin internet**, no como default. En
  una Pi 5 conviene un modelo de 1–4B y aceptar respuestas más lentas.

**Fuentes:** Groq, *Rate Limits* (consultado 24/10/2026)
<https://console.groq.com/docs/rate-limits>; Google, *Gemini Developer API
pricing* (actualizado 21/10/2026) <https://ai.google.dev/gemini-api/docs/pricing>
y *Rate limits* (actualizado 15/10/2026)
<https://ai.google.dev/gemini-api/docs/rate-limits>; OpenRouter, *API Credit &
Rate Limits* (consultado 24/10/2026)
<https://openrouter.ai/docs/api_reference/limits>; Ollama
<https://ollama.com/>.

---

## 2. STT (voz a texto)

### Opción actual

Groq `whisper-large-v3-turbo`, español, endpoint OpenAI-compatible de audio.

### Alternativas evaluadas

| Opción | Por qué conviene | Límites / costo | Licencia | Esfuerzo | Riesgos |
|---|---|---|---|---|---|
| **Groq `whisper-large-v3-turbo`** (recomendada) | Muy rápido, buen español, sin instalar modelos, misma clave que el LLM | 20 RPM, 2.000 req/día, 7.200 segundos de audio/hora, 28.800 seg/día, 25 MB por archivo; mínimo facturable 10 s | Servicio gratuito con límites | Bajo | Internet; 429; privacidad; mínimo de 10 s por petición |
| faster-whisper | Local, MIT, CTranslate2; wheel `cp312` para `aarch64` verificada; int8 ahorra RAM | Gratis; descarga de modelo; CPU | MIT | Medio | En Pi 5 no hay benchmark propio; el benchmark oficial en un i7 tarda 1m42s en 13 min de audio con `small` int8 (8 hilos), así que en Pi será más lento |
| whisper.cpp | Local, MIT, C/C++; `tiny`/`base` corren en tiempo real en Pi 5 según reportes de la comunidad | Gratis; compilar o usar binario | MIT | Medio-alto | Compilar va contra “instalar en un comando”; binarios por arquitectura; precisión menor con modelos pequeños |
| Vosk `small-es` | Local, Apache 2.0, 39 MB, pensado para Raspberry Pi; streaming | Gratis | Apache 2.0 | Bajo | WER ~16% en CommonVoice; calidad inferior a Whisper; sin puntuación |

### Recomendación

**Mantener Groq `whisper-large-v3-turbo` como opción principal.** El plan
gratuito da 8 horas de audio al día, muy por encima de una conversación de 30
minutos, y evita instalar modelos pesados en la Pi.

- No implementar STT local en el hito 4. Dejar la interfaz `STT` preparada
  para un adaptador local futuro.
- Si el dueño quiere funcionar sin internet, la primera alternativa a probar
  es **faster-whisper `small` int8** por su wheel aarch64 y su integración
  Python; Vosk `small-es` es el respaldo de bajo consumo si la Pi va justa.
- Enviar audio mono 16 kHz; recortar silencios con el VAD antes de gastar una
  petición (el mínimo de 10 s se cobra igual, pero se evita enviar ruido).

**Fuentes:** Groq, *Speech to Text* y *Rate Limits* (consultados 24/10/2026)
<https://console.groq.com/docs/speech-to-text>,
<https://console.groq.com/docs/rate-limits>; SYSTRAN, *faster-whisper*
(consultado 24/10/2026) <https://github.com/SYSTRAN/faster-whisper>; ggml-org,
*whisper.cpp* <https://github.com/ggml-org/whisper.cpp>; Alpha Cephei, *VOSK
Models* (consultado 24/10/2026) <https://alphacephei.com/vosk/models>; PyPI,
wheels `ctranslate2-4.8.3-cp312-...-aarch64` (consultado 24/10/2026)
<https://pypi.org/project/ctranslate2/>.

---

## 3. TTS (texto a voz)

### Opción actual

Piper, con el modelo `models/voices/es_MX-claude-high.onnx` (todavía no
descargado). El `.env` heredado también menciona un `scripts/piper_server.py`
y un `.venv-piper`; no existen en este proyecto y no se van a recrear.

### Alternativas evaluadas

| Opción | Por qué conviene | Costo / límites | Licencia | Esfuerzo | Riesgos |
|---|---|---|---|---|---|
| **Piper** (recomendada) | Local, rápido en Pi 4/5, 22,05 kHz, muchas voces; wheel `cp312` aarch64 disponible | Gratis, sin límites | Motor **GPL-3.0-or-later**; cada voz tiene su `MODEL_CARD` | Bajo | Licencia GPL del motor; algunas voces tienen licencias restrictivas; voz sintética |
| Kokoro-82M | 82M parámetros, calidad alta para su tamaño, Apache 2.0, 8 idiomas y 54 voces (español: 1F/2M) | Gratis, local | Apache 2.0 | Medio | Requiere PyTorch/misaki o un runtime ONNX; más pesado y lento en Pi que Piper; integración menos madura |
| Coqui XTTS v2 | Multilingüe, clonación de voz, buen español | Gratis para uso personal | **CPML, solo no comercial**; Coqui cerró y no hay vía comercial clara | Alto | Pesado (~2 GB), pensado para GPU; licencia no comercial; proyecto sin mantenimiento |
| eSpeak NG | Diminuto, rápido, offline, GPL | Gratis | GPL-3.0 | Bajo | Voz robótica; solo como respaldo de emergencia |

### Recomendación

**Piper con `es_MX-claude-high`** (español de México, 22,05 kHz, alta
calidad). El `MODEL_CARD` de esa voz declara dataset con licencia Apache-2.0.
Alternativas de voz si al dueño no le gusta: `es_ES-davefx-medium` (dataset
CC0) o `es_MX-ald-medium` (dataset Unlicense).

- Invocar `piper` como **proceso separado** (`subprocess`) y no importar su
  librería: así SIRAH (MIT) no se convierte en obra derivada GPL y el
  aislamiento es más simple.
- Sintetizar por frases y reproducir con `aplay`; la primera frase suena
  mientras se genera la siguiente.
- Descargar el `.onnx` y su `.onnx.json` en `models/voices/` desde
  `sirah setup`, con verificación SHA256 y consentimiento (no versionar).
- Revisar el `MODEL_CARD` de la voz elegida antes de distribuir el robot;
  para uso personal no comercial no hay problema, pero la licencia de la voz
  manda.

**Fuentes:** OHF-Voice, *piper1-gpl* (GPL-3.0, consultado 24/10/2026)
<https://github.com/OHF-Voice/piper1-gpl>; PyPI, `piper-tts 1.8.0` con wheel
`cp39-abi3-manylinux_2_17_aarch64` (consultado 24/10/2026)
<https://pypi.org/project/piper-tts/>; `rhasspy/piper-voices`, `MODEL_CARD` de
`es_MX/claude/high`, `es_ES/davefx/medium` y `es_MX/ald/medium` (consultados
24/10/2026) <https://huggingface.co/rhasspy/piper-voices>; Hexgrad,
*Kokoro-82M* (Apache 2.0; v1.0 del 27/01/2025, consultado 24/10/2026)
<https://huggingface.co/hexgrad/Kokoro-82M>; Coqui, *XTTS-v2 LICENSE* (CPML
no comercial) <https://huggingface.co/coqui/XTTS-v2/blob/main/LICENSE.txt>.

---

## 4. Detección facial

### Opción actual

OpenCV + YuNet 2023mar, modelo local
`models/face_detection_yunet_2023mar.onnx` (MIT, 232.589 bytes, SHA256
`8f2383e4...552fa4`).

### Alternativas evaluadas

| Opción | Por qué conviene | Costo | Licencia | Esfuerzo | Riesgos |
|---|---|---|---|---|---|
| **YuNet 2023mar** (recomendada) | Ya está en el repo; 232 KB; AP 0,834 easy / 0,824 medium en WIDER Face; OpenCV DNN en CPU; sin GPU | Gratis | MIT | Bajo | Modelo de 2023 con entrada fija; OpenCV 5 puede requerir el modelo dinámico 2026may, que no está en el repo |
| MediaPipe Face Detector | Muy rápido, Apache 2.0, buen soporte en Pi | Gratis | Apache 2.0 | Medio | Otra dependencia y otro modelo; APIs y wheels cambian; no aporta nada frente a YuNet para una sola cara |
| Haar cascade de OpenCV | Viene con OpenCV; ligerísimo | Gratis | BSD (OpenCV) | Bajo | Menos preciso y menos robusto a luz/pose; falsos positivos |

### Recomendación

**Mantener YuNet 2023mar y fijar OpenCV 4.x** (`opencv-python-headless` con
`<5`). El README oficial de opencv_zoo advierte que el modelo 2023mar tiene
forma de entrada fija y que el motor ONNX Runtime de OpenCV 5.x necesita
dimensiones dinámicas; usar OpenCV 4.x evita ese problema y no requiere
cambiar `models/`.

- Usar `cv2.FaceDetectorYN`, rostro más grande, umbral ~0,9, 640×480, detectar
  cada 2–3 frames y suavizar la posición (EMA).
- La cámara solo genera `TARGET`; no se guardan imágenes ni se envía video a
  la nube.
- Si no hay cámara o el modelo no carga, la capa se apaga con un aviso y el
  resto sigue.

**Fuentes:** OpenCV Zoo, *YuNet* (consultado 24/10/2026)
<https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet>;
`models/face_detection_yunet_2023mar.onnx.sha256`; PyPI,
`opencv-python-headless` 4.14.0.94 con wheel `cp37-abi3` aarch64 (consultado
24/10/2026) <https://pypi.org/project/opencv-python-headless/>; Google AI Edge,
*Face landmark detection* (Apache 2.0, actualizado 09/10/2026)
<https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker>.

---

## 5. VAD y palabra de activación

### Opción actual

El `.env` heredado define umbrales de energía/RMS (`VOICE_*_RMS`,
`VOICE_START_FRAMES`, etc.). No hay implementación en este proyecto.

### Alternativas evaluadas

| Opción | Por qué conviene | Costo | Licencia | Esfuerzo | Riesgos |
|---|---|---|---|---|---|
| **WebRTC VAD** (recomendada) | Diminuto, sin modelo, wheel `cp312` aarch64 verificada; 10/20/30 ms; ideal para micrófono cercano | Gratis | MIT | Bajo | Menos preciso que un VAD neuronal; puede cortar sílabas; necesita 16 kHz |
| Silero VAD | MIT, ~2 MB, <1 ms por chunk de 30 ms, 8/16 kHz, muy buena precisión | Gratis | MIT | Medio | Añade `onnxruntime` (~50 MB) o PyTorch; más instalación |
| VAD por energía/RMS | Cero dependencias, ya configurado en el `.env` heredado | Gratis | — | Bajo | Falsos positivos con ruido; muy sensible al micrófono |
| openWakeWord | Palabra de activación local, código Apache 2.0 | Gratis | Código Apache 2.0; **modelos preentrenados CC BY-NC-SA 4.0** | Alto | Solo modelos en inglés; entrenar en español requiere datos y tiempo; falsos positivos |

### Recomendación

**WebRTC VAD + umbral mínimo de RMS**, sin palabra de activación en v1.

- Frame de 20 ms a 16 kHz mono; pre-roll de 300 ms; inicio tras 3 frames de
  voz; fin tras 400 ms de silencio; máximo 10 s por turno.
- El RMS mínimo evita que un ruido constante dispare el VAD.
- No usar openWakeWord en v1: sus modelos preentrenados son solo en inglés y
  con licencia no comercial; entrenar “SIRAH” en español es un proyecto
  aparte. Se puede añadir después si el dueño lo pide.
- Si WebRTC corta demasiadas sílabas en las pruebas reales, subir a Silero
  VAD como extra opcional, no como dependencia base.

**Fuentes:** PyPI, `webrtcvad-wheels 2.0.14.post1` (MIT; wheel cp312 aarch64,
consultado 24/10/2026) <https://pypi.org/project/webrtcvad-wheels/>; Silero,
*Silero VAD* (MIT, consultado 24/10/2026)
<https://github.com/snakers4/silero-vad>; openWakeWord (solo inglés;
modelos CC BY-NC-SA 4.0, consultado 24/10/2026)
<https://github.com/dscripka/openWakeWord>.

---

## 6. Memoria persistente

### Opción actual

Historial local limitado; Zep opcional.

### Alternativas evaluadas

| Opción | Por qué conviene | Límites / costo | Licencia | Esfuerzo | Riesgos |
|---|---|---|---|---|---|
| **Historial local (JSONL)** (recomendada) | Sin dependencias, privado, fácil de borrar, suficiente para continuidad entre sesiones | Gratis | — | Bajo | Solo recupera por recencia, no por significado; hay que acotar tamaño |
| Zep Cloud | Memoria semántica gestionada, grafo temporal | Free: 10.000 créditos/mes, 2 proyectos, límites variables, sin rollover; 1 crédito por episodio de hasta 350 bytes | Servicio; SDK/API | Medio | Nube y clave; Community Edition descontinuada; límites variables; no es necesario para v1 |
| Sin memoria persistente | Menos superficie de fallo | Gratis | — | Ninguno | Pierde contexto entre sesiones |

### Recomendación

**Historial local primero.** Guardar JSONL acotado (últimos N mensajes y
rotación por tamaño) en el directorio de datos del usuario. No implementar
Zep en v1; dejar la interfaz `Memory` y activarlo solo si el dueño lo pide en
el hito 5.

- No guardar secretos ni audio.
- El historial no es instrucción: el prompt lo marca como referencia.
- Zep no reemplaza al historial local; lo complementa.

**Fuentes:** Zep, *Pricing* (Free: 10.000 créditos/mes; consultado 24/10/2026)
<https://www.getzep.com/pricing/>; Zep, *A New Direction for Zep's Open Source
Strategy* (Community Edition descontinuada, 02/04/2025)
<https://www.getzep.com/blog/announcing-a-new-direction-for-zeps-open-source-strategy/>.

---

## 7. Otras piezas que afectan la estabilidad

| Pieza | Recomendación | Motivo |
|---|---|---|
| Serial | `pyserial` con `exclusive=True`, timeout corto y un solo dueño | Estándar, puro Python, funciona en x86_64 y aarch64 |
| HTTP | `httpx` con timeouts explícitos, reintentos acotados y streaming SSE | SSE, multipart para STT y timeouts sin pelear con `urllib`; pocas dependencias |
| OpenCV | `opencv-python-headless >=4.10,<5` | YuNet 2023mar; sin GUI; wheel aarch64 |
| Audio | `arecord`/`aplay` de ALSA vía `subprocess` | Ya instalado en Linux; sin PortAudio ni compilación |
| Cámara | `cv2.VideoCapture` con `CAP_V4L2` en un hilo | Suficiente para 640×480; sin GStreamer |
| Web | Starlette + uvicorn como extra `web`; HTML/CSS/JS sin build | Capa fina, async, probada; se decide en el hito 7 |
| Logs | `logging` + `RotatingFileHandler` (1 MB × 3) | Evita desgastar la SD de la Pi |
| Tests | `pytest` + `ruff`; serial simulado con pty; LLM falso local | Sin hardware en `make check` |

No se añaden ORMs, bases de datos, frameworks de plugins ni microservicios.

---

## 8. Hardware de bajo costo (solo sugerencias)

No se asume ninguna compra ni se toca el firmware.

| Mejora | Por qué | Coste aproximado | Riesgo / nota |
|---|---|---|---|
| Fuente externa 5 V/5 A para los 6 SG90 | Evita reinicios del ESP32 y brownouts al mover varios servos | 10–20 USD | **Sin verificar precios**; comprobar conector y protección |
| Condensador electrolítico 1000 µF en `V+`/`GND` | Absorbe picos de corriente | 1–2 USD | Polaridad; cerca de la PCA |
| Cables cortos y gruesos para servos | Menos caída de tensión | 3–5 USD | No sustituye la fuente |
| Borne de alimentación para la PCA | Evita pasar corriente por la placa | 2–5 USD | Sujeción mecánica |
| Corte de servos por `OE` de la PCA | Deja los servos sin par al apagar | 0–2 USD (GPIO) | Requiere cambiar el firmware; **no hacerlo ahora** |
| Botón físico de apagado limpio | Apagado ordenado de la Pi | 2–5 USD | Requiere GPIO y servicio; hito 8+ |
| I2C directo desde la Raspberry Pi | Elimina el ESP32 y el USB | 0 USD si se reutiliza la PCA | Idea futura; no implementar ahora |

Para el montaje actual: **no** alimentar los servos desde el ESP32, usar masa
común y probar la fuente con los seis servos moviéndose. Los valores exactos
de consumo del robot real siguen sin medir (`docs/PENDIENTES.md`).

---

## 9. Lo que propongo omitir en v1

Omitir no es abandonar: es no cargar complejidad antes de que haga falta.

- **Palabra de activación.** WebRTC VAD es suficiente para empezar; una
  palabra mal entrenada genera falsos positivos y frustración.
- **`NOD`.** El firmware lo acepta pero no mueve nada. No se enviará ni se
  ofrecerá al LLM hasta que exista una implementación física validada.
- **Zep.** La memoria local cubre el caso de uso; Zep añade clave, nube y
  límites.
- **STT/TTS locales.** Groq + Piper cubren voz sin instalar modelos grandes;
  el respaldo offline se evalúa si el dueño lo pide.
- **Panel web en el primer corte.** Primero texto, ojos, visión y voz; el
  panel llega en el hito 7.
- **Character cards.** La fase 2A ya carga v2/v3 y tarjetas antiguas simples;
  las v1 con `spec` propio y los PNG de personaje quedan fuera.

---

## 10. Fuentes y fechas

Todas consultadas el **24/10/2026**, salvo la fecha propia de la página.

| Dato | Fuente | Fecha / nota |
|---|---|---|
| Límites Groq LLM y STT | <https://console.groq.com/docs/rate-limits> | Consultado 24/10/2026 |
| Modelos STT Groq | <https://console.groq.com/docs/speech-to-text> | Consultado 24/10/2026 |
| Gemini free tier | <https://ai.google.dev/gemini-api/docs/pricing> | Actualizado 21/10/2026 |
| Gemini rate limits | <https://ai.google.dev/gemini-api/docs/rate-limits> | Actualizado 15/10/2026 |
| OpenRouter free limits | <https://openrouter.ai/docs/api_reference/limits> | Consultado 24/10/2026 |
| Piper motor GPL | <https://github.com/OHF-Voice/piper1-gpl> | Consultado 24/10/2026 |
| Piper wheel aarch64 | <https://pypi.org/project/piper-tts/> | Versión 1.8.0 |
| Voces Piper español | <https://huggingface.co/rhasspy/piper-voices> | `MODEL_CARD` de cada voz |
| Kokoro-82M | <https://huggingface.co/hexgrad/Kokoro-82M> | v1.0 del 27/01/2025 |
| XTTS v2 CPML | <https://huggingface.co/coqui/XTTS-v2/blob/main/LICENSE.txt> | Licencia no comercial |
| faster-whisper | <https://github.com/SYSTRAN/faster-whisper> | MIT; benchmark CPU en la página |
| whisper.cpp | <https://github.com/ggml-org/whisper.cpp> | MIT |
| Vosk modelos español | <https://alphacephei.com/vosk/models> | `small-es` 39 MB, Apache 2.0 |
| Silero VAD | <https://github.com/snakers4/silero-vad> | MIT |
| WebRTC VAD wheels | <https://pypi.org/project/webrtcvad-wheels/> | cp312 aarch64 |
| openWakeWord | <https://github.com/dscripka/openWakeWord> | Solo inglés; modelos CC BY-NC-SA 4.0 |
| YuNet | <https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet> | MIT; 2023mar fixed shape |
| OpenCV wheels aarch64 | <https://pypi.org/project/opencv-python-headless/> | 4.14.0.94 con `cp37-abi3` |
| Zep free | <https://www.getzep.com/pricing/> | 10.000 créditos/mes |
| Zep CE descontinuada | <https://www.getzep.com/blog/announcing-a-new-direction-for-zeps-open-source-strategy/> | 02/04/2025 |
| Ollama | <https://ollama.com/> | Consultado 24/10/2026 |
| MediaPipe | <https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker> | Apache 2.0; actualizado 09/10/2026 |

## 11. Incertidumbres

- Los límites gratuitos pueden cambiar sin aviso; el código debe degradar con
  un mensaje claro, no asumir cuota.
- No se ha medido el rendimiento real de ningún modelo en la Raspberry Pi del
  dueño. Todas las estimaciones de rendimiento en Pi son cualitativas.
- No se ha probado la calidad de `es_MX-claude-high` con la voz del dueño;
  puede requerir cambiar a `davefx` o `ald`.
- La licencia de cada voz de Piper debe revisarse en su `MODEL_CARD` antes de
  distribuir el robot.
- El consumo real de los seis SG90 y la estabilidad de la fuente no se han
  medido.
