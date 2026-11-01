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

# Escapa &, la barra invertida y el delimitador usado por sed para que los IDs
# no rompan la sustitucion ni inserten texto especial (por ejemplo "&").
escape_replacement() {
    printf '%s' "$1" | sed 's/[&\\|]/\\&/g'
}
ORCH_ESCAPED="$(escape_replacement "$ORCH")"
SUB_ESCAPED="$(escape_replacement "$SUB")"

grep -rl --include='*.md' -e '__ORCH_MODEL__' -e '__SUB_MODEL__' .opencode | while read -r f; do
    sed -i "s|__ORCH_MODEL__|$ORCH_ESCAPED|g; s|__SUB_MODEL__|$SUB_ESCAPED|g" "$f"
    echo "actualizado: $f"
done
