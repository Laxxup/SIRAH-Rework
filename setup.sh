#!/usr/bin/env bash
# Delega a la copia canónica del asistente de OpenCode.
exec "$(dirname "$0")/opencode-setup/setup.sh" "$@"
