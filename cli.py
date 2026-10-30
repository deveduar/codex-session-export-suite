"""CLI entry point for Codex Extension Exporter.

Provides multiple export modes (presets) for Codex session JSONL files.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from config import ConfigError, expand_path, load_config
from extract import extract_messages_from_jsonl
from output import (
    format_digest_summary,
    format_faithful_json,
    format_jsonl_memory,
    format_markdown_conversation,
    format_markdown_transcript,
)
from products import (
    PRESETS,
    ProductConfig,
    digest,
    faithful,
    get_preset,
    list_presets,
    memory,
    transcript,
)


VERSION = "2.1.0"

PRODUCTS: Dict[str, ProductConfig] = {
    "transcript": transcript,
    "memory": memory,
    "digest": digest,
    "faithful": faithful,
}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _configure_stdout() -> None:
    """Use UTF-8 on Windows consoles when possible."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="codex_export",
        description="Extract and export Codex conversation sessions from VS Code.",
        epilog="Supported presets: archive, quick, study, review, notes, conversation, prompts, rag, digest_only",
    )

    parser.add_argument(
        "codex_dir",
        type=str,
        nargs="?",
        default=None,
        help="Codex directory, sessions directory, subdirectory or a single .jsonl file (default: config or ~/.codex)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output directory (default: config or ./codex_exports)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to an INI config file (default: ./codex_export.ini or user config)",
    )

    parser.add_argument(
        "-p",
        "--preset",
        type=str,
        default=None,
        help=f"Export preset: {', '.join(PRESETS.keys())} or transcript/memory/digest/faithful",
    )

    parser.add_argument(
        "--products",
        type=str,
        nargs="+",
        default=None,
        help="Custom products: transcript, memory, digest, faithful or any preset name",
    )

    parser.add_argument(
        "--role",
        type=str,
        default=None,
        help="Force role filter: user, assistant, or both",
    )

    parser.add_argument(
        "--truncate",
        type=int,
        default=None,
        help="Truncate tool output to N characters (0 disables truncation)",
    )

    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        default=None,
        help="Hide timestamps in output",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be extracted without writing files",
    )

    parser.add_argument(
        "--list-presets",
        action="store_true",
        default=False,
        help="List available export presets",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"codex_export {VERSION}",
    )

    return parser


def sanitize_filename(name: str) -> str:
    """Make a filename safe on both Linux and Windows."""
    safe = _INVALID_FILENAME_CHARS.sub("_", str(name)).strip().rstrip(". ")
    if not safe:
        safe = "session"

    base = safe.split(".")[0].upper()
    if base in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"

    return safe[:180].rstrip(". ") or "session"


def discover_sessions(codex_dir: str) -> List[Path]:
    """Discover .jsonl session files.

    Accepts:
        - the Codex root directory (contains ``sessions/``)
        - the ``sessions`` directory itself
        - a year/month subdirectory
        - a single ``.jsonl`` file
    """
    codex_path = expand_path(codex_dir)
    if codex_path is None or not codex_path.exists():
        return []

    if codex_path.is_file():
        if codex_path.suffix.lower() == ".jsonl":
            return [codex_path]
        return []

    if not codex_path.is_dir():
        return []

    sessions_dir = codex_path / "sessions"
    search_root = sessions_dir if sessions_dir.is_dir() else codex_path

    try:
        jsonl_files = sorted(search_root.glob("**/*.jsonl"))
    except OSError:
        return []

    unique_files = []
    seen = set()
    for file_path in jsonl_files:
        try:
            key = file_path.resolve()
        except OSError:
            key = file_path.absolute()

        if key in seen:
            continue

        seen.add(key)
        unique_files.append(file_path)

    return unique_files


def get_display_name(file_path: Path) -> str:
    """Get a safe display name from a session file path.

    Handles nested paths like sessions/2026/10/27/filename.jsonl.
    Returns: '2026-10-27-filename' or just 'filename'.
    """
    parts = file_path.parts
    lowered_parts = [part.lower() for part in parts]

    try:
        sessions_idx = lowered_parts.index("sessions")
    except ValueError:
        return sanitize_filename(file_path.stem)

    relative_parts = parts[sessions_idx + 1:]
    name_parts = []
    for part in relative_parts:
        if part.lower().endswith(".jsonl"):
            name_parts.append(part[:-6])
        else:
            name_parts.append(part)

    return sanitize_filename("-".join(name_parts) if name_parts else file_path.stem)


def resolve_product_config(name: str) -> ProductConfig:
    """Resolve a product/preset name to a ProductConfig."""
    normalized = str(name).strip().lower()

    if normalized in PRODUCTS:
        return PRODUCTS[normalized]

    if normalized in PRESETS:
        return get_preset(normalized)

    available = ", ".join(list(PRODUCTS) + list(PRESETS))
    raise KeyError(f"'{name}' no es un producto/preset reconocido. Disponibles: {available}")


def apply_overrides(
    product_config: ProductConfig,
    role: Optional[str] = None,
    truncate: Optional[int] = None,
) -> ProductConfig:
    """Apply CLI/config overrides without mutating global presets."""
    overrides: Dict[str, object] = {}

    if role:
        normalized_role = str(role).strip().lower()
        if normalized_role == "both":
            overrides["role_filter"] = []
            overrides["role"] = None
        elif normalized_role in ("user", "assistant"):
            overrides["role_filter"] = [normalized_role]
            overrides["role"] = None
        else:
            raise ValueError(f"Rol no válido: '{role}'. Usa user, assistant o both.")

    if truncate is not None:
        overrides["truncate_tool_output"] = truncate if truncate > 0 else None

    return product_config.clone(**overrides) if overrides else product_config


def output_path_for(
    product_name: str,
    display_name: str,
    output_dir: Path,
    include_product: bool = False,
) -> Path:
    """Return the output file path for a product.

    When several products are requested at once, non-default products get
    their name in the filename so they do not overwrite each other.
    """
    if product_name == "memory":
        return output_dir / f"memory_{display_name}.jsonl"
    if product_name == "faithful":
        return output_dir / f"faithful_{display_name}.json"
    if product_name == "digest":
        return output_dir / f"digest_{display_name}.md"

    if include_product and product_name != "transcript":
        prefix = f"{product_name}_"
    else:
        prefix = "session_"

    return output_dir / f"{prefix}{display_name}.md"


def process_session(
    file_path: Path,
    product_config: ProductConfig,
    output_dir: Path,
    no_timestamps: bool = False,
    dry_run: bool = False,
    include_product: bool = False,
) -> None:
    """Process a single session file and generate output."""
    display_name = get_display_name(file_path)
    messages = extract_messages_from_jsonl(file_path)

    if not messages:
        print(f"[*] No se encontraron mensajes en {file_path.name}")
        return

    product_name = getattr(product_config, "name", "transcript")
    output_file = output_path_for(
        product_name,
        display_name,
        output_dir,
        include_product=include_product,
    )

    if dry_run:
        print(f"[*] {product_name}: {file_path.name} -> {output_file}")
        return

    filtered = product_config.apply(messages)

    if product_name == "conversation":
        content = format_markdown_conversation(filtered, display_name)
        label = "Markdown conversación"
    elif product_name in ("transcript", "notes", "review"):
        content = format_markdown_transcript(
            filtered,
            filename=display_name,
            include_timestamps=not no_timestamps,
        )
        label = "Markdown"
    elif product_name == "memory":
        content = format_jsonl_memory(filtered, display_name)
        label = "JSONL memoria"
    elif product_name == "faithful":
        content = format_faithful_json(filtered, display_name)
        label = "JSON fiel"
    elif product_name == "digest":
        max_chars = getattr(product_config, "truncate_tool_output", 500) or 500
        content = format_digest_summary(filtered, display_name, max_chars=max_chars)
        label = "Resumen digest"
    else:
        content = format_markdown_transcript(
            filtered,
            filename=display_name,
            include_timestamps=not no_timestamps,
        )
        label = "Markdown (predeterminado)"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write(content)

    print(f"[+] {label} exportado: {output_file.name}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point for the CLI."""
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        print("Productos disponibles:")
        for product_name, product in PRODUCTS.items():
            print(f"  - {product_name}: {product.description}")
        print()
        print("Presets disponibles:")
        for preset_name in list_presets():
            preset = get_preset(preset_name)
            print(f"  - {preset_name}: {preset.description}")
        return 0

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"[!] {exc}")
        return 1

    codex_dir = args.codex_dir if args.codex_dir is not None else config["codex_dir"]
    output_value = args.output if args.output is not None else config["output_dir"]
    role = args.role if args.role is not None else config["role"]
    truncate = args.truncate if args.truncate is not None else config["truncate"]

    if args.no_timestamps is None:
        no_timestamps = not config["timestamps"]
    else:
        no_timestamps = args.no_timestamps

    if truncate is not None and truncate < 0:
        print("[!] --truncate no puede ser negativo.")
        return 1

    try:
        if args.products:
            product_configs = [resolve_product_config(name) for name in args.products]
        else:
            preset_name = args.preset if args.preset is not None else config["preset"]
            product_configs = [
                resolve_product_config(preset_name) if preset_name else transcript
            ]
    except KeyError as exc:
        print(f"[!] Error: {exc}")
        print("Use --list-presets para ver las opciones disponibles.")
        return 1

    try:
        product_configs = [
            apply_overrides(product_config, role=role, truncate=truncate)
            for product_config in product_configs
        ]
    except ValueError as exc:
        print(f"[!] Error: {exc}")
        return 1

    jsonl_files = discover_sessions(codex_dir)
    if not jsonl_files:
        print(f"[!] No se encontraron archivos .jsonl en: {expand_path(codex_dir)}")
        print("  Asegúrate de pasar la carpeta de Codex, sessions, un subdirectorio o un .jsonl.")
        return 1

    output_dir = expand_path(output_value) or Path("./codex_exports")
    config_path = config.get("_config_path")
    if config_path:
        print(f"[*] Configuración: {config_path}")

    print(f"[*] Se encontraron {len(jsonl_files)} archivos de sesión. Procesando...")
    if len(product_configs) > 1:
        names = ", ".join(product.name for product in product_configs)
        print(f"[*] Productos: {names}")
    print()

    include_product = len(product_configs) > 1
    for index, file_path in enumerate(jsonl_files, 1):
        print(f"[{index}/{len(jsonl_files)}] Procesando: {file_path.name}")
        for product_config in product_configs:
            process_session(
                file_path,
                product_config,
                output_dir,
                no_timestamps=no_timestamps,
                dry_run=args.dry_run,
                include_product=include_product,
            )

    print()
    if args.dry_run:
        print(f"Simulación completa. Se escribiría en: {output_dir.absolute()}")
    else:
        print(f"¡Extracción completa! Revisa tu contenido en: {output_dir.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
