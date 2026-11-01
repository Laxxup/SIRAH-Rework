# Contribuciones

SIRAH es un proyecto local y de un solo mantenedor por ahora. Si quieres
enviar cambios, prueba toda modificación con `make check` y `make guard` antes
de enviarla. No abras puertos seriales sin `BENCH_PORT`, no muevas servos ni
toques las rutas protegidas (`firmware/`, `config/eyes-calibration.toml`,
`models/`).

Instalación para desarrollo:

```bash
uv sync --all-extras
uv run sirah --help
make check
```

Mantén cambios en español en docs, comentarios y mensajes, y en inglés en código
e identificadores.
