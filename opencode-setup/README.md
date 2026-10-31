# opencode-setup

Regenera la configuración local de opencode para este proyecto:
`.opencode/agents/` (orchestrator, explorer, builder, reviewer) y `opencode.json`
con los plugins superpowers y ponytail. Ambos destinos están en `.gitignore`
porque llevan tus modelos.

```bash
opencode models        # IDs disponibles
python3 opencode-setup/install.py --scope project --project-dir . \
  --orch opencode/deepseek-v4.1-flash-free \
  --build ollama/beam:cloud \
  --explore ollama/gemma4:31b-cloud \
  --skip-external
```

- Detecta opencode V1 o V2 (cambian `plugin`/`plugins` y el formato de permisos).
- Hace copia de seguridad (`*.bak-FECHA`) y mezcla con tu `opencode.json`.
- `--dry-run` muestra qué haría. Sin `--skip-external` también ejecuta
  `npx skills add` para find-skills e impeccable (te pregunta para qué agente).
- Las plantillas de agentes están en `opencode-setup/agents/`; edítalas ahí
  y vuelve a ejecutar el script.
