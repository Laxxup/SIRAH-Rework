"""Punto de entrada y subcomandos de SIRAH."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import replace
from pathlib import Path

from sirah import __version__
from sirah.config import (
    DEFAULT_PERSONA,
    ConfigError,
    active_card_path,
    identity_for,
    load_config,
)
from sirah.core.persona import PersonaError, load_persona
from sirah.doctor import print_report, run_checks
from sirah.logs import setup_logging
from sirah.setup_wizard import SetupError, run_setup
from sirah.terminal import run_terminal
from sirah.voice import run_check, run_voice

logger = logging.getLogger("sirah.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sirah",
        description="S.I.R.A.H. — robot conversacional con ojos animatrónicos.",
    )
    parser.add_argument("--version", action="version", version=f"SIRAH {__version__}")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="escribe trazas y logs de depuración en el archivo",
    )
    parser.add_argument(
        "--persona",
        metavar="RUTA",
        help="tarjeta de personaje v2/v3 (por defecto, la de config/sirah.toml)",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "setup",
        help="crea la configuración y detecta serial, cámara y audio",
    )
    doctor = subparsers.add_parser(
        "doctor",
        help="diagnostica cada capa y propone una solución",
    )
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="no comprueba la conexión con el LLM",
    )
    voice = subparsers.add_parser(
        "voice",
        help="conversación manos libres: micrófono, Groq y Piper",
    )
    voice.add_argument(
        "--check",
        action="store_true",
        help="graba 3 segundos y muestra el nivel RMS y si el VAD detecta voz",
    )
    return parser


def _config_failure(exc: ConfigError) -> int:
    print(f"[FALLA] Configuración: {exc}")
    print("        Solución: corrige .env o ejecuta `sirah setup`.")
    return 1


def _persona_failure(exc: PersonaError) -> int:
    print(f"[FALLA] Persona: {exc}")
    print("        Solución: corrige el archivo o elige otra con `--persona`.")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "setup":
        try:
            return run_setup()
        except SetupError as exc:
            print(f"Configuración cancelada: {exc}")
            return 1
        except KeyboardInterrupt:
            print("\nConfiguración cancelada.")
            return 130

    try:
        config = load_config()
    except ConfigError as exc:
        return _config_failure(exc)

    if args.persona:
        config = replace(
            config,
            persona_path=Path(args.persona).expanduser().resolve(),
            persona_path_set=True,
        )

    if args.command == "doctor":
        return print_report(run_checks(config, offline=args.offline), config.env_file)

    try:
        setup_logging(config.data_dir, config.log_level, args.debug)
    except OSError as exc:
        print(f"[FALLA] No se pudo preparar el log en {config.data_dir}: {exc}")
        return 1

    if args.command == "voice" and args.check:
        # El ajuste del micrófono no necesita LLM ni tarjeta.
        try:
            return asyncio.run(run_check(config))
        except KeyboardInterrupt:
            print("\nGrabación cancelada.")
            return 130

    try:
        config.require_llm_key()
    except ConfigError as exc:
        return _config_failure(exc)

    settings = config.persona_settings
    for warning in settings.warnings:
        print(f"[AVISO] {warning}")

    active = active_card_path(config, settings)
    try:
        persona = load_persona(active, user_name=config.user_name)
    except PersonaError as exc:
        if active.resolve() == DEFAULT_PERSONA.resolve():
            return _persona_failure(exc)
        print(f"[AVISO] {exc}")
        print("        Solución: corrige la tarjeta o elige otra con `--persona`.")
        print(f"        Se usará {DEFAULT_PERSONA}.")
        try:
            persona = load_persona(DEFAULT_PERSONA, user_name=config.user_name)
        except PersonaError as fallback_exc:
            return _persona_failure(fallback_exc)

    identity = identity_for(settings, persona.path)
    try:
        if args.command == "voice":
            return asyncio.run(
                run_voice(
                    config,
                    persona,
                    identity=identity,
                    language=settings.language,
                )
            )
        return asyncio.run(
            run_terminal(
                config,
                persona,
                identity=identity,
                language=settings.language,
            )
        )
    except KeyboardInterrupt:
        print("\nHasta luego.", flush=True)
        # El hilo daemon que lee stdin sigue bloqueado; salir normal se cuelga
        # al finalizar el intérprete. Cerramos logs y salimos directo.
        logging.shutdown()
        os._exit(130)
    except Exception:
        logger.exception("Fallo inesperado en el chat")
        print("[FALLA] SIRAH se detuvo por un error inesperado. Revisa el log.")
        return 1
