# AGENTS.md — SIRAH v2

> Parte de cero: no conoces este proyecto ni a su dueño. Todo lo que necesitas saber está en este archivo.
> Léelo completo al iniciar cada sesión. Si algo contradice una suposición tuya, gana este archivo.

## 1. Qué es SIRAH

**S.I.R.A.H. (Sistema Inteligente Robótico de Asistencia Humana)** es un robot conversacional con ojos animatrónicos:

- Conversación con un LLM, por texto y por voz.
- Visión local: detecta una cara y los ojos la siguen.
- Ojos animados con 6 servos: mirada, parpadeo y expresiones.

Se construye por capas: primero funciona solo por texto en terminal y luego se añaden ojos, visión y voz sin romper lo anterior.

## 2. Contexto del dueño y del entorno

- El dueño (Luis) habla español. **Documentación, comentarios para humanos y mensajes al usuario: en español. Código e identificadores: en inglés.**
- Desarrollo: laptop con **Linux** (audio ALSA, cámara V4L2). Destino de ejecución previsto: la misma laptop o una **Raspberry Pi** (modelo por confirmar). El software debe correr en Linux **x86_64 y aarch64**; verifica que cada dependencia tenga paquete precompilado para ambas.
- **Sin contenedores.** SIRAH se instala y corre de forma nativa.
- No puedes tocar el hardware del robot: solo el dueño prueba servos, cámara, micrófono y altavoz (sección 14). Puede haber un ESP32 de banco para tus pruebas (sección 7).

## 3. Prioridad nº 1: estable y fácil de usar

Las versiones anteriores se rompían: el ESP32 no se comunicaba bien con los ojos, no iniciaba, era difícil de configurar y cargar una personalidad obligaba a reescribir casi todo. **El éxito se mide en confiabilidad y simplicidad, no en cantidad de funciones.** Si hay que elegir entre una función nueva y la estabilidad, gana la estabilidad.

- **Instalar en un comando** (`uv sync`) y **arrancar en un comando** (`uv run sirah`). Sin compilar nada ni pasos ocultos.
- **Única configuración obligatoria: `LLM_API_KEY`.** Todo lo demás con valores por defecto sensatos y validación con mensajes claros.
- **`sirah setup`:** asistente que crea la configuración, detecta serial, cámara, micrófono y altavoz, descarga el modelo de voz y pide solo lo que falte.
- **`sirah doctor`:** diagnostica cada capa y, para cada falla, da la solución exacta (diagnósticos del ESP32 en la sección 5).
- **Detección automática del hardware.** Si algo no está, esa capa se desactiva con un aviso de una línea, sin trazas.
- **Errores en español y accionables.** Los stack traces van al log.
- **Se recupera solo:** reconexión del ESP32, reintentos con espera creciente y timeout en LLM y STT; si un servicio falla, SIRAH sigue (por texto o avisando que no pudo).
- **Apagado limpio:** al salir centra los ojos y cierra serial, cámara y audio.
- **Logs a archivo** con rotación y tamaño acotado (en una Raspberry Pi la tarjeta SD se desgasta); `-debug` para más detalle.
- **Dependencias con versión fija** (`uv.lock`), pocas y precompiladas.

## 4. Estado inicial y estructura

Proyecto **nuevo y limpio**. Solo existe el hardware:

| Ruta | Qué es | ¿Se puede modificar? |
|---|---|---|
| `firmware/` | Sketch Arduino del ESP32 y calibradores | **No** |
| `config/eyes-calibration.toml` | Calibración física de los servos (única fuente válida) | **No** |
| `models/` | Modelo de detección facial YuNet (.onnx + sha256) | **No** |
| `.env.example` | Variables de configuración de referencia | Se puede ampliar |

No existe software previo. **No busques ni leas nada fuera de este directorio.** El diseño del software es tuyo.

**La estructura (carpetas, módulos, nombres) la eliges tú**, con estas condiciones:

- `firmware/`, `config/eyes-calibration.toml` y `models/` quedan en su ruta, sin modificar. Todo lo nuevo va en carpetas nuevas.
- Respeta el **orden de diseño** de la sección 12 y los principios de la sección 6.
- **Simple y pequeña:** sin capas ni carpetas "por si acaso".
- Antes de escribir código, documenta la estructura y el porqué en `docs/ARQUITECTURA.md` y preséntala dentro del plan (misma confirmación única).

## 5. Hardware (inmutable)

- **ESP32** por USB serial a 115200 baudios.
- **PCA9685** (I2C) controlando **6 servos SG90**.
- Canales: CH0 = X, CH1 = Y, CH2 = SD, CH3 = ID, CH4 = SI, CH5 = II. Glosario (confírmalo en el `.ino`): X/Y = mirada horizontal/vertical; SD, ID, SI, II = los cuatro párpados.
- **Cámara USB**, **micrófono** y **altavoz**.
- Alimentación externa de servos con masa común con el ESP32.

Reglas:

- No cambies el firmware ni la calibración. Si ves un posible bug, anótalo en `docs/PENDIENTES.md`. No dupliques la calibración en el código; léela de su TOML.
- Lo único que debes leer para entender el protocolo es `firmware/sirah/sirah.ino`. Con eso escribe `docs/PROTOCOL.md` (comandos, respuestas, timeouts, errores) y `docs/HARDWARE.md` (pinout, canales, cableado, calibración).
- Comandos esperados: `CENTER`, `BLINK`, `TIRED`, `NOD`, `TARGET`, `MODE`, `HEARTBEAT`, `STATUS`. Confírmalos contra el `.ino`; si algo no coincide, manda el `.ino`.
- El firmware tiene timeout de comandos: envía `HEARTBEAT` mientras el robot esté activo. Si la PCA9685 no responde, el firmware contesta `ERR PCA9685_NOT_READY` y no anuncia `READY`.
- Sin validar físicamente aún: la pose `TIRED` y la estabilidad de la alimentación sostenida. No las des por buenas.
- **Transporte por ahora: solo USB serial con ESP32**, que es lo que funciona. Deja el adaptador de ojos detrás de una interfaz y la dirección de conexión en la configuración (`serial://...`), de modo que más adelante se pueda añadir otro backend (I2C directo desde una Raspberry Pi, o TCP/WiFi). **No los implementes ahora.**

**Diagnósticos del ESP32 que `doctor` debe cubrir** (causas conocidas de fallas en Linux):

- ModemManager o brltty capturando el puerto.
- Usuario fuera del grupo `dialout`.
- Puerto cambiante: usar siempre `/dev/serial/by-id/...`.
- Reinicio del ESP32 al abrir el puerto (líneas DTR/RTS): tras abrir, esperar `READY` con timeout y reintentar.
- Cable solo de carga, o servos sin fuente externa que reinician la placa.
- Baudios incorrectos o firmware distinto al esperado (`STATUS`).

## 6. Principios de diseño

Guía, no estructura obligada. El objetivo es que una pieza que falla no tire a las demás.

1. **Núcleo sin I/O** (agente, persona, memoria, máquina de estados, acciones semánticas). Nunca importa hardware ni red; se prueba con simulaciones.
2. **Adaptadores intercambiables** (LLM, STT, TTS, micrófono, altavoz, cámara, ojos). Cada uno con versión real, versión simulada y un método `check()` con su estado y la solución sugerida. `doctor` y el panel solo juntan esos `check()`.
3. **Un solo dueño del puerto serial.** Una única tarea abre el puerto, espera `READY`, envía `HEARTBEAT`, usa cola con acuse y timeout, y reconecta sola. Nadie más escribe al serial. En `TARGET` gana siempre el último valor para no acumular retraso.
4. **Supervisor** que arranca y vigila cada capa con estados (apagada, iniciando, lista, degradada, fallida). Si una capa falla, se degrada y el resto sigue.
5. **Máquina de estados explícita** (reposo, escucha, piensa, habla). Los ojos reaccionan a estados, no a `if`s dispersos.
6. **Persona y expresión como datos.** El LLM devuelve texto y, opcionalmente, etiquetas de una lista permitida de acciones (mirar, parpadear, cansancio, asentir); una capa las traduce a comandos y descarta lo desconocido. La prioridad de capas está en la sección 11.
7. **Configuración validada:** esquema con valores por defecto, secretos aparte, calibración solo en su TOML. Un valor inválido da un mensaje claro, no un crash.
8. Un solo proceso con `asyncio` (e hilos para cámara y audio si hace falta). Sin microservicios, plugins genéricos ni ORMs.

## 7. Pruebas con hardware

Tres niveles, de menos a más real:

1. **Simulado:** serial simulado (p. ej. pseudo-terminal) y mocks. Corre en cualquier máquina; es la base de `make check`.
2. **ESP32 de banco:** una placa conectada a la laptop **sin PCA9685 ni servos**. Como el firmware real no anuncia `READY` sin la PCA9685, crea en una carpeta aparte (`bench/`) un firmware de prueba que imite el protocolo (incluido `READY`) para probar con USB real: apertura de puerto, handshake, latencia, `HEARTBEAT` y reconexión. `firmware/` no se toca.
3. **Robot real:** solo lo prueba el dueño (sección 14).

Reglas del ESP32 de banco:

- Se identifica por su serial en `/dev/serial/by-id/...` y se guarda como `BENCH_PORT`. Pide al dueño **una vez** que confirme cuál es.
- **Nunca** abras, flashees ni envíes comandos a otro puerto que no sea `BENCH_PORT`. El robot real puede estar conectado.
- Si no hay `BENCH_PORT` conectado, salta esos tests y dilo; no falles ni improvises.
- Flashear el `bench/` solo con `BENCH_PORT` confirmado y con el CLI de Arduino disponible; si falta algo, indícaselo al dueño.

## 8. Entorno y requisitos

Verifica e informa qué falta antes de asumir que está instalado:

- **uv** y Python 3.12.
- **alsa-utils** (`arecord`, `aplay`).
- Grupos del usuario: `dialout` (serial), `video` (cámara), `audio`.
- **Piper TTS** y un modelo de voz en español (`.onnx` + `.onnx.json`) en `models/voices/` (no se versiona). Verifica la instalación vigente.
- Claves en la configuración: LLM (obligatoria), Groq (solo voz), Zep (opcional).

## 9. Stack

> Valores por defecto. Antes de fijarlos aplica la sección 10; nada cambia sin aprobación del dueño.

- **Python 3.12 + uv**; stdlib antes que una librería nueva.
- LLM: endpoint compatible con OpenAI (`/chat/completions`, Bearer, streaming SSE) con `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`.
- STT: Groq `whisper-large-v3-turbo`, español. TTS: Piper.
- Visión: OpenCV + YuNet (headless, sin compilar nada).
- Serial: `pyserial`. Memoria persistente opcional: Zep.
- Tests: `pytest`. Lint: `ruff`.

## 10. Sugerencias y alternativas (sin presupuesto)

El dueño **no tiene presupuesto**: todo debe ser gratis, de código abierto o con plan gratuito real. **Busca y recomienda mejores opciones** cuando existan.

1. **Antes del plan**, investiga alternativas para cada pieza clave (LLM, STT, TTS, detección facial, VAD o palabra de activación y lo que pese en estabilidad). Usa búsqueda web si la tienes; si no, marca cada dato como "sin verificar".
2. **Criterios, en orden:** estabilidad, facilidad de instalar y configurar, costo cero, funcionar sin internet cuando se pueda, licencia, calidad en español, rendimiento sin GPU (incluida una Raspberry Pi).
3. Entrega `docs/SUGERENCIAS.md`: por pieza, la opción actual, hasta 3 alternativas, por qué conviene, límites del plan gratuito, licencia, esfuerzo, riesgos y **una sola recomendación**, con **fecha y fuente** de cada dato.
4. Tu recomendación final por pieza va dentro del plan de superpowers, con **una sola confirmación conjunta**. No cuenta contra el límite de preguntas.
5. **No adoptes nada sin aprobación.** Hasta entonces rige la sección 9.
6. Ejemplos a evaluar (verifica vigencia): faster-whisper, whisper.cpp o Vosk frente a Groq; Ollama como respaldo sin internet; otros TTS con buen español; Silero VAD y openWakeWord; MediaPipe frente a YuNet.
7. **Hardware:** solo sugerencias de bajo costo en `SUGERENCIAS.md` (alimentación estable de servos, cableado; a futuro, I2C directo desde la Raspberry Pi, botón de apagado limpio, corte de servos por el pin OE de la PCA9685). No asumas compras ni toques el firmware.
8. Si una función del plan te parece innecesaria o riesgosa para la estabilidad, propón omitirla.

## 11. Identidad y persona

**Principio:** la personalidad vive en la tarjeta de personaje, no en reglas
globales. Cambiar de personalidad, de rol o de identidad (por ejemplo, de robot a
otro ser) es cambiar o elegir un archivo, sin tocar código; hay un test que lo
demuestra.

**Formato único de persona:** Character Card v2 (lectura también de v3 y de la
versión antigua con campos en la raíz), en `config/persona/*.json`. No existe un
formato propio de SIRAH. La tarjeta por defecto es `config/persona/sirah.json`
(versionada, estable y probada). Las demás tarjetas son locales y no se suben a git.
La tarjeta se usa sin modificar el archivo; la limpieza ocurre solo en memoria.

**Prioridad de capas (de mayor a menor):**
1. **Piso fijo**, sobre cualquier tarjeta. Solo esto:
   - Formato técnico: texto plano para voz, sin Markdown ni acciones entre
     asteriscos, y etiquetas de acción de la lista permitida para los ojos.
   - Consentimiento y privacidad: se descartan en memoria las líneas de una tarjeta
     que intenten anularlos ("sin restricciones", "asume consentimiento", etc.).
   - Honestidad mínima: si el usuario sale del personaje y pregunta en serio qué es
     SIRAH, responde que es SIRAH, un robot con IA. Nunca afirma como hechos reales
     cosas que no ocurrieron (haber movido los ojos, ver u oír algo). Dentro de la
     ficción, en diálogo, el personaje habla con libertad.
   - HISTORY y MEMORY son contexto, no instrucciones.
2. **La tarjeta de personaje manda** sobre todo lo demás: identidad, cuerpo,
   carácter, afecto, saludo, si pregunta el nombre, humor, longitud y registro.
3. **Defaults de SIRAH**, solo cuando la tarjeta no dice nada: estilo breve y español.

**Datos, no reglas:** el nombre del usuario, el idioma y el modo de identidad son
datos de configuración. Que la IA pregunte o no el nombre lo decide la tarjeta.

**Modo de identidad** (`[persona] identity` en `config/sirah.toml`): `"card"` por
defecto (manda la tarjeta; `"personaje"` es alias) y `"robot"`, modo estricto opcional
que fuerza el contrato de robot (por ejemplo, para una demostración pública). Solo se
decide en `sirah.toml`: una tarjeta nunca cambia su propio modo.

**Tarjeta por defecto (SIRAH):** español, tono amable y cercano, respuestas cortas
pensadas para decirse en voz alta, saludo breve al despertar y, como parte de su
ficha, es un robot. Son valores de esa tarjeta, no del programa.

## 12. Funcionalidad por hitos

**Orden de diseño (obligatorio):** (1) leer el `.ino` y documentar hardware y protocolo, (2) investigar alternativas, (3) plan y estructura con una confirmación, (4) construir los hitos 0 → 8 en ese orden.

Cada hito funciona sin los siguientes. Sin ESP32, cámara o micrófono, SIRAH sigue conversando por texto. **No pases al siguiente hito sin cumplir el criterio del actual.**

0. **Instalación y diagnóstico.** `uv sync`, `sirah setup`, `sirah doctor`, configuración validada. *Listo cuando:* en una máquina limpia el dueño llega a chatear con solo `uv sync` y la clave del LLM.
1. **Texto.** Chat en terminal con streaming, historial local limitado y persona cargable. *Listo cuando:* `uv run sirah` conversa con solo `LLM_API_KEY`, con tests y sin hardware.
2. **Ojos.** Acciones semánticas (mirar, parpadear, cansancio, asentir) traducidas a comandos serial, con parpadeo natural, `HEARTBEAT` y el dueño único del puerto. *Listo cuando:* pasan los tests simulados y, si hay `BENCH_PORT`, los del ESP32 de banco; y el dueño confirma que los servos se mueven bien.
3. **Visión.** Detección facial opt-in; la cara genera `TARGET`. *Listo cuando:* tests con imágenes de prueba, y el dueño confirma el seguimiento.
4. **Voz.** Manos libres: captura, VAD, STT, LLM y TTS en streaming. *Listo cuando:* pruebas por etapa con audio grabado, y el dueño confirma una conversación real.
5. **Memoria persistente (Zep), opcional.**
6. **Autotest de hardware.** Comando explícito, nunca automático, que avisa antes de mover los servos.
7. **Panel web.** Administración sin editar archivos: estado y `doctor` en vivo, chat, configuración (claves, dispositivos, persona), activar o apagar capas, logs, reinicio y test manual de ojos con aviso previo. Capa fina sobre el mismo núcleo: **SIRAH funciona también sin él**. Usa la skill impeccable. Sin paso de compilación de frontend salvo que lo justifiques. Seguridad: escucha en `127.0.0.1` por defecto; si se abre a la red, **contraseña o token obligatorios**; nunca muestra claves completas; secretos con permisos restringidos; protección CSRF. *Listo cuando:* el dueño configura y arranca todo desde el navegador sin tocar archivos.
8. **Actualización y servicio.** Versiones etiquetadas en git (solo se etiqueta si `make check` pasa). `sirah update` baja la versión nueva, sincroniza dependencias, corre `doctor` y **vuelve a la versión anterior si algo falla**. `sirah install-service` crea un servicio systemd de usuario para arrancar solo. Documenta en `docs/DESPLIEGUE.md` instalación, actualización, servicio, uso en Raspberry Pi y seguridad del panel. *Listo cuando:* en una máquina limpia el dueño instala, actualiza y revierte una versión, y el servicio sobrevive a un reinicio.

## 13. Skills disponibles y cuándo usarlas

- **superpowers:** `brainstorming` y `writing-plans` antes de escribir código. UNA confirmación del plan.
- **ponytail:** siempre activo. Lo mínimo que funcione, sin abstracciones ni dependencias innecesarias.
- **find-skills:** solo si falta una skill concreta para el stack. Máximo 2 instalaciones.
- **claude-mem:** guarda decisiones clave (estructura, protocolo, por qué se eligió algo).
- **impeccable:** solo para el diseño del panel web (hito 7).

## 14. Forma de trabajar

- Máximo **3 preguntas** en total, y solo si algo bloquea (la confirmación del plan y la de `BENCH_PORT` no cuentan). Lo demás decídelo y anótalo en `docs/DECISIONES.md`.
- No expliques lo que vas a hacer; trabaja y muestra resultados.
- Commits pequeños con mensaje claro. Nada de secretos en el repo.
- Todo lo físico (serial, cámara, audio) debe poder simularse para correr tests sin hardware.
- **Pruebas físicas:** tú no puedes hacerlas. Al terminar un hito con hardware real, entrega al dueño una lista corta de pasos manuales (qué comando correr, qué debería verse u oírse) y espera su confirmación antes de marcarlo como validado. Registra el resultado en `docs/PENDIENTES.md`.

## 15. Cuándo está terminado

- [ ] Instalar y arrancar toma dos comandos; `sirah setup` y `sirah doctor` explican cada falla.
- [ ] `uv run sirah` conversa por texto con solo `LLM_API_KEY`.
- [ ] Con el ESP32 configurado, los ojos responden a la conversación; con visión activa, siguen una cara; en modo voz, SIRAH escucha y responde hablando.
- [ ] Sin hardware conectado, todo degrada con gracia y no se cae.
- [ ] Cambiar la persona es cambiar un archivo, sin tocar código.
- [ ] `make check` (tests, `ruff`) pasa sin hardware.
- [ ] **Reconexión:** el dueño desconecta y reconecta el cable del ESP32 con SIRAH corriendo y vuelve a funcionar en pocos segundos, sin reiniciar nada. También probado con simulación y, si hay `BENCH_PORT`, con la placa de banco.
- [ ] Cortar la red unos segundos no tumba el programa.
- [ ] Prueba de resistencia del dueño: 30 minutos sin intervención ni reinicios.
- [ ] El panel configura y arranca SIRAH sin editar archivos, y SIRAH funciona sin él.
- [ ] `sirah update` actualiza y revierte; el servicio arranca solo tras un reinicio.
- [ ] `docs/SUGERENCIAS.md` entregado y las decisiones aprobadas registradas en `docs/DECISIONES.md`.
- [ ] Los pendientes físicos están listados, no marcados como validados.

## 16. Documentación a entregar

- `README.md`: qué es, requisitos, quick start (texto primero), cómo activar ojos, visión y voz, limitaciones.
- `docs/HARDWARE.md`, `docs/PROTOCOL.md`: hardware, calibración y protocolo serial completos.
- `docs/ARQUITECTURA.md`: estructura elegida, módulos, flujo de datos y un diagrama simple.
- `docs/DESPLIEGUE.md`: instalación, actualización, servicio, Raspberry Pi y seguridad del panel.
- `docs/SUGERENCIAS.md`, `docs/DECISIONES.md`, `docs/PENDIENTES.md`.
- `.env.example` actualizado y comentado.

## 17. Licencias y créditos (incluir en el README)

- Mecanismo de ojos: **ε-Series Animatronic Eye Mechanism** de Will Cogley / NM Robotics, CC BY-NC-SA 4.0 (atribución, sin uso comercial).
- Piper TTS: GPL-3.0-or-later. Modelo YuNet: MIT. Código nuevo de SIRAH: MIT.

## 18. Qué NO hacer

- No modificar `firmware/`, `config/eyes-calibration.toml` ni `models/`.
- No leer ni copiar código de fuera de este directorio.
- No usar contenedores, ni implementar I2C directo ni WiFi (son ideas futuras, solo como sugerencia).
- No tocar ningún puerto serial que no sea `BENCH_PORT` en pruebas automáticas.
- No añadir frameworks pesados, ORMs ni capas "por si acaso".
- No dar por validado nada que requiera hardware real, ni mover servos sin avisar al dueño.
- No añadir reglas de personalidad globales (cómo saluda, si pregunta el nombre, afecto, longitud). Si una conducta depende del carácter, va en la tarjeta.
- No exponer el panel a la red sin autenticación.

## 19. Delegación entre agentes

- Solo el **orquestador** habla con el dueño, hace preguntas (cuentan contra el límite de la sección 14) y toma decisiones de diseño.
- Los **subagentes** (`worker`, `scout`, `reviewer`) no hacen preguntas ni planes: ejecutan o revisan lo que se les encarga y anotan sus dudas en el reporte final.
- Los subagentes respetan la sección 18 al pie de la letra (no tocar `firmware/`, `config/eyes-calibration.toml` ni `models/`, ni puertos que no sean `BENCH_PORT`).
- Todo lo que requiera hardware real lo valida solo el dueño; ningún agente lo marca como validado.
- El orquestador sigue el orden de la sección 12 y el flujo de superpowers (brainstorming y plan con una confirmación) antes de delegar código.
