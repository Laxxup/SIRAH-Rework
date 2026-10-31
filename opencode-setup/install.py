#!/usr/bin/env python3
"""Configura opencode con agentes orquestador/subagentes y plugins.

Uso típico (global, en ~/.config/opencode):
    python3 opencode-setup/install.py --scope project --project-dir . \
        --orch <proveedor>/<modelo> --build <proveedor>/<modelo>

Los IDs exactos de modelo salen de:  opencode models
Es idempotente: se puede ejecutar de nuevo. Hace copia de seguridad de todo lo que toca.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

SUPERPOWERS = "superpowers@git+https://github.com/obra/superpowers.git"
PONYTAIL = "@dietrichgebert/ponytail"

# Bloques de permisos por versión de opencode. V1 usa `permission:` como mapa;
# V2 usa `permissions:` como lista de reglas.
PERMS_V1 = {
    "explorer": "permission:\n  edit: deny\n  bash: deny",
    "reviewer": "permission:\n  edit: deny",
}
PERMS_V2 = {
    "explorer": (
        "permissions:\n"
        '  - action: edit\n    resource: "*"\n    effect: deny\n'
        '  - action: bash\n    resource: "*"\n    effect: deny'
    ),
    "reviewer": 'permissions:\n  - action: edit\n    resource: "*"\n    effect: deny',
}


def say(message: str) -> None:
    print(message, flush=True)


def opencode_major() -> int | None:
    exe = shutil.which("opencode")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.\d+", out)
    return int(match.group(1)) if match else None


def backup(path: Path) -> None:
    if path.exists():
        target = path.with_name(f"{path.name}.bak-{STAMP}")
        shutil.copy2(path, target)
        say(f"  copia de seguridad: {target}")


def ask(prompt: str, hint: str) -> str:
    say(hint)
    value = input(f"{prompt}: ").strip()
    if not value or "/" not in value:
        sys.exit("ID inválido: debe tener la forma proveedor/modelo (mira `opencode models`).")
    return value


def merge_config(path: Path, plugin_key: str, ollama_model: str | None, dry_run: bool) -> None:
    """Añade plugins (y el proveedor Ollama) sin pisar lo que ya haya."""
    jsonc = path.with_suffix(".jsonc")
    if not path.exists() and jsonc.exists():
        say(f"  AVISO: existe {jsonc.name} (con comentarios); no lo edito automáticamente.")
        say(f'  Añade a mano en "{plugin_key}": ["{SUPERPOWERS}", "{PONYTAIL}"]')
        return

    config: dict = {"$schema": "https://opencode.ai/config.json"}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            say(f"  AVISO: {path} no es JSON puro; no lo edito automáticamente.")
            say(f'  Añade a mano en "{plugin_key}": ["{SUPERPOWERS}", "{PONYTAIL}"]')
            return
        if not isinstance(config, dict):
            sys.exit(f"{path} no contiene un objeto JSON.")

    plugins = config.get(plugin_key, [])
    if not isinstance(plugins, list):
        sys.exit(f'"{plugin_key}" en {path} no es una lista.')
    for spec in (SUPERPOWERS, PONYTAIL):
        base = spec.split("@git+")[0] if "@git+" in spec else spec
        already = any(
            (item if isinstance(item, str) else (item[0] if item else "")).startswith(base)
            for item in plugins
        )
        if not already:
            plugins.append(spec)
    config[plugin_key] = plugins

    if ollama_model:
        providers = config.setdefault("provider", {})
        entry = providers.setdefault(
            "ollama",
            {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Ollama (local)",
                "options": {"baseURL": "http://localhost:11434/v1"},
                "models": {},
            },
        )
        entry.setdefault("models", {}).setdefault(ollama_model, {"name": ollama_model})

    if dry_run:
        say(f"  [dry-run] escribiría {path}:\n{json.dumps(config, indent=2)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"  config actualizada: {path}")


def render_agents(dest: Path, models: dict[str, str], perms: dict[str, str], dry_run: bool) -> None:
    for source in sorted((HERE / "agents").glob("*.md")):
        text = source.read_text(encoding="utf-8")
        text = text.replace("__ORCH_MODEL__", models["orch"])
        text = text.replace("__BUILD_MODEL__", models["build"])
        text = text.replace("__EXPLORE_MODEL__", models["explore"])
        text = text.replace("__PERMS_EXPLORER__", perms["explorer"])
        text = text.replace("__PERMS_REVIEWER__", perms["reviewer"])
        target = dest / source.name
        if dry_run:
            say(f"  [dry-run] escribiría {target}")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        backup(target)
        target.write_text(text, encoding="utf-8")
        say(f"  agente: {target}")


def run_external(cmd: list[str], dry_run: bool) -> None:
    say(f"  $ {' '.join(cmd)}")
    if dry_run:
        return
    if shutil.which(cmd[0]) is None:
        say(f"    AVISO: falta `{cmd[0]}`; instálalo y ejecuta ese comando a mano.")
        return
    result = subprocess.run(cmd)
    if result.returncode != 0:
        say(f"    AVISO: terminó con código {result.returncode}; repítelo a mano si hace falta.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--orch", help="modelo del orquestador (proveedor/modelo)")
    parser.add_argument("--build", help="modelo de builder y reviewer (proveedor/modelo)")
    parser.add_argument(
        "--explore", help="modelo del explorer (por defecto, ollama/<--ollama-model> si se da)"
    )
    parser.add_argument(
        "--ollama-model", help="registra Ollama local con este modelo, p. ej. qwen2.5-coder:7b"
    )
    parser.add_argument("--scope", choices=["global", "project"], default="global")
    parser.add_argument("--project-dir", default=".", help="raíz del proyecto si --scope project")
    parser.add_argument(
        "--with-claude-mem", action="store_true", help="instala claude-mem (necesita Bun)"
    )
    parser.add_argument(
        "--skip-external", action="store_true", help="no ejecuta npx (find-skills, impeccable)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="muestra qué haría sin escribir nada"
    )
    args = parser.parse_args()

    major = opencode_major()
    if major is None:
        say("AVISO: no encuentro `opencode` o no pude leer su versión; asumo V1.")
        major = 1
    v2 = major >= 2
    say(f"opencode detectado: V{major}")

    orch = args.orch or ask(
        "Modelo del orquestador (p. ej. tu DeepSeek)",
        "Ejecuta `opencode models` en otra terminal para ver los IDs.",
    )
    build = args.build or ask(
        "Modelo de builder/reviewer", "Un modelo más barato o rápido que el orquestador."
    )
    explore = args.explore or (f"ollama/{args.ollama_model}" if args.ollama_model else build)

    models = {"orch": orch, "build": build, "explore": explore}
    perms = PERMS_V2 if v2 else PERMS_V1

    if args.scope == "global":
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"
        config_path = base / "opencode.json"
        agents_dir = base / "agents"
        rules_path = base / "AGENTS.md"
    else:
        root = Path(args.project_dir).resolve()
        config_path = root / "opencode.json"
        agents_dir = root / ".opencode" / "agents"
        rules_path = root / "AGENTS.md"

    say("\n1) Agentes")
    render_agents(agents_dir, models, perms, args.dry_run)

    say("\n2) Configuración y plugins")
    merge_config(config_path, "plugins" if v2 else "plugin", args.ollama_model, args.dry_run)

    say("\n3) Reglas globales (AGENTS.md)")
    if rules_path.exists():
        say(f"  ya existe {rules_path}; no lo toco.")
    elif not (HERE / "templates" / "AGENTS.global.md").exists():
        say("  no hay plantilla en este kit; no se crea AGENTS.md.")
    elif args.dry_run:
        say(f"  [dry-run] copiaría la plantilla a {rules_path}")
    else:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "templates" / "AGENTS.global.md", rules_path)
        say(f"  plantilla copiada: {rules_path}")

    say("\n4) Skills externas (el instalador pregunta para qué agente; elige opencode)")
    if args.skip_external:
        say("  omitido (--skip-external).")
    else:
        flag_scope = ["-g"] if args.scope == "global" else []
        run_external(
            [
                "npx",
                "--yes",
                "skills",
                "add",
                "vercel-labs/skills",
                "--skill",
                "find-skills",
                *flag_scope,
            ],
            args.dry_run,
        )
        run_external(
            ["npx", "--yes", "skills", "add", "pbakaus/impeccable", *flag_scope], args.dry_run
        )

    if args.with_claude_mem:
        say("\n5) claude-mem")
        if args.skip_external:
            say("  omitido (--skip-external).")
        else:
            run_external(
                ["npx", "--yes", "claude-mem", "install", "--ide", "opencode"], args.dry_run
            )

    say("\nListo. Reinicia opencode y comprueba:")
    say('  - pregúntale: "Tell me about your superpowers"')
    say("  - Tab para cambiar al agente `orchestrator`")
    say("  - /ponytail para ver el nivel de ponytail")
    if v2:
        say(
            "  - V2: los permisos siguen la doc de V2 y no se probaron en un opencode real; "
            "revisa .opencode/agents/."
        )


if __name__ == "__main__":
    main()
