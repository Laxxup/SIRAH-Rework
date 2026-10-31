# Tarjetas de personaje

SIRAH carga tarjetas **Character Card v2 o v3** (campo `spec` + objeto `data`). También
acepta tarjetas antiguas con los campos en la raíz. `sirah.json` es la tarjeta por
defecto y la única versionada en git.

## Campos que se usan

| Campo | Uso |
|---|---|
| `name` | Nombre del personaje. Obligatorio. |
| `nickname` | Alias opcional. |
| `description` | Contexto del personaje. |
| `personality` | Rasgos y estilo de habla. |
| `scenario` | Situación de la conversación. |
| `mes_example` | Ejemplos de diálogo. |
| `first_mes` | Inspira el saludo de arranque; no se copia literalmente. |

Se ignoran `system_prompt`, `post_history_instructions`, `alternate_greetings`,
`extensions`, `assets` y saludos solo para grupos. Si hay `character_book` se avisa y
no se usa. Los PNG de personaje no están soportados.

## Limpieza en memoria

La tarjeta **nunca se modifica en disco**. Al cargarla se resuelven `{{char}}`,
`{{user}}`, `<BOT>` y `<USER>`; se quitan los asteriscos de acciones (`*sonríe*`) sin
tocar la multiplicación (`3*4`); y se descartan las líneas que intentan anular el
contrato de SIRAH (sin restricciones, consentimiento asumido, contenido explícito
obligatorio, ignorar instrucciones, límites de tokens, describir el cuerpo). El resto
se conserva.

## Elegir tarjeta y modo

La tarjeta activa y el modo de identidad se configuran en `config/sirah.toml`
(créalo con `sirah setup` o copiando `config/sirah.toml.example`):

```toml
[persona]
active = "config/persona/sirah.json"
language = "es"
identity = "card"  # por defecto; "personaje" es alias

[persona.cards."ashley.json"]
identity = "robot"  # modo estricto solo para esa tarjeta
```

También puedes arrancar con otra tarjeta sin tocar el TOML:

```bash
uv run sirah --persona ruta/a/tarjeta.json
```

`SIRAH_PERSONA` en `.env` sigue funcionando y tiene prioridad sobre `active`, pero es
temporal. Ninguna tarjeta puede cambiar el modo de identidad por sí misma: eso solo se
decide en `sirah.toml`.

Si una tarjeta no se puede leer, SIRAH avisa con una solución y arranca con
`sirah.json`; nunca se cae por una tarjeta rota.

## Historial

Cada tarjeta tiene su historial en `~/.local/share/sirah/history/<archivo>.jsonl`
(o bajo `SIRAH_DATA_DIR`). El historial de `default.jsonl` se migra a `sirah.jsonl`
con un respaldo la primera vez que se usa la tarjeta por defecto.

## Seguridad

- El piso fijo (texto plano, acciones permitidas, consentimiento, privacidad,
  honestidad mínima e historial como contexto) vive en el código y ninguna
  tarjeta lo anula. La tarjeta manda sobre identidad, cuerpo, afecto, saludo,
  nombre, humor, longitud y registro.
- Una tarjeta puede aportar ficción, pero SIRAH no afirma como hechos reales
  acciones o sentidos que no ocurrieron.
- Si alguien comparte una tarjeta, revísala: puede traer instrucciones ocultas. SIRAH
  descarta las más comunes, no todas.
- Las tarjetas locales no se versionan (`config/persona/*.json` está ignorado salvo
  `sirah.json`).
