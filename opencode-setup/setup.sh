#!/usr/bin/env bash
# Genera la configuración local de OpenCode sin necesidad de instalar skills.
# Uso: ./setup.sh <modelo-orquestador> <modelo-subagentes>
# Los modelos exactos salen de: opencode models
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Uso: ./setup.sh <modelo-orquestador> <modelo-subagentes>"
    echo "Ejemplo: ./setup.sh opencode/deepseek-v4.1-flash-free ollama/beam:cloud"
    echo "Ver IDs disponibles: opencode models"
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$PWD"
ORCH="$1"
SUB="$2"

exec python3 "$SCRIPT_DIR/install.py" \
    --scope project \
    --project-dir "$PROJECT_DIR" \
    --orch "$ORCH" \
    --build "$SUB" \
    --explore "$SUB" \
    --skip-external
