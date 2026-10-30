#!/usr/bin/env bash
# Reemplaza los marcadores de modelo en los archivos de agentes.
# Uso: ./setup.sh <modelo-orquestador> <modelo-subagentes>
# Los IDs exactos salen de: opencode models
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Uso: ./setup.sh <modelo-orquestador> <modelo-subagentes>"
  echo "Ejemplo: ./setup.sh opencode/<id-deepseek> <proveedor>/<id-beam>"
  echo "Ver IDs disponibles: opencode models"
  exit 1
fi

ORCH="$1"
SUB="$2"

grep -rl --include='*.md' -e '__ORCH_MODEL__' -e '__SUB_MODEL__' .opencode | while read -r f; do
  sed -i "s|__ORCH_MODEL__|$ORCH|g; s|__SUB_MODEL__|$SUB|g" "$f"
  echo "actualizado: $f"
done
