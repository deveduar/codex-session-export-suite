"""CLI entry point for Codex Extension Exporter.

Provides multiple export modes (presets) for Codex session JSONL files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extract import extract_messages_from_jsonl
from output import (
    format_digest_summary,
    format_faithful_json,
    format_jsonl_memory,
    format_markdown_conversation,
    format_markdown_transcript,
)
from products import (
    get_preset,
    list_presets,
    PRESETS,
    transcript,
    memory,
    digest,
    faithful,
)


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
        default="~/.codex",
        help="Path to Codex directory (default: ~/.codex)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="./codex_exports",
        help="Output directory (default: ./codex_exports)",
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
        help="Custom products: transcript, memory, digest, faithful",
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
        help="Truncate tool output to N characters",
    )

    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        default=False,
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
        version="codex_export 2.0.0",
    )

    return parser


def discover_sessions(codex_dir: str) -> list[Path]:
    """Discover .jsonl session files in the Codex directory.

    Args:
        codex_dir: Path to Codex directory (expanded ~)

    Returns:
        List of .jsonl file paths
    """
    from pathlib import Path

    codex_path = Path(codex_dir).expanduser()
    sessions_dir = codex_path / "sessions"

    if not sessions_dir.exists():
        print(f"[!] No se encontró la carpeta de sesiones: {sessions_dir}")
        return []

    jsonl_files = list(sessions_dir.glob("**/*.jsonl"))
    return sorted(jsonl_files)


def get_display_name(file_path: Path) -> str:
    """Get a display name from a session file path.

    Handles nested paths like sessions/2026/10/27/filename.jsonl
    Returns: '2026-10-27-filename' or just 'filename'
    """
    parts = file_path.parts
    try:
        sessions_idx = parts.index("sessions")
        relative_parts = parts[sessions_idx + 1:]  # subdirs + filename
        # Remove .jsonl extension
        name_parts = []
        for p in relative_parts:
            if p.endswith(".jsonl"):
                name_parts.append(p[:-6])  # remove .jsonl
            else:
                name_parts.append(p)
        return "-".join(name_parts)
    except ValueError:
        # Fallback: just use stem without extension
        return file_path.stem


def process_session(
    file_path: Path,
    product_config: object,
    output_dir: Path,
    no_timestamps: bool = False,
    dry_run: bool = False,
) -> None:
    """Process a single session file and generate output.

    Args:
        file_path: Path to the .jsonl file
        product_config: ProductConfig instance or preset name string
        output_dir: Output directory
        no_timestamps: Whether to hide timestamps
        dry_run: If True, just print what would be done
    """
    # Extract session display name
    display_name = get_display_name(file_path)

    # Extract messages from JSONL
    messages = extract_messages_from_jsonl(file_path)

    if not messages:
        print(f"[*] No messages found in {file_path.name}")
        return

    # Determine product name
    product_name = getattr(product_config, "name", "transcript")

    if dry_run:
        print(f"[*] {product_name} mode would process: {file_path.name}")
        print(f"[*] Would output to: {output_dir / f'session_{display_name}.md'}")
        return

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Apply product-specific filtering/formatting
    if hasattr(product_config, "apply"):
        filtered = product_config.apply(messages)
    elif isinstance(product_config, str):
        preset = get_preset(product_config)
        filtered = preset.apply(messages)
    else:
        filtered = messages

    # Generate output based on product type
    product_name = getattr(product_config, "name", "transcript")

    if product_name in ("transcript", "conversation", "notes", "review"):
        # Markdown transcript format
        if product_name == "conversation":
            markdown = format_markdown_conversation(filtered, display_name)
        elif product_name == "notes":
            markdown = format_markdown_transcript(
                filtered,
                filename=display_name,
                include_timestamps=not no_timestamps,
            )
        elif product_name == "review":
            markdown = format_markdown_transcript(
                filtered,
                filename=display_name,
                include_timestamps=not no_timestamps,
            )
        else:
            # transcript default
            markdown = format_markdown_transcript(
                filtered,
                filename=display_name,
                include_timestamps=not no_timestamps,
            )

        # Write Markdown output
        output_filename = f"session_{display_name}.md"
        output_file = output_dir / output_filename
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"[+] Archivo Markdown exportado: {output_file.name}")

    elif product_name == "memory":
        # JSONL memory format
        jsonl_content = format_jsonl_memory(filtered, display_name)
        memory_file = output_dir / f"memory_{display_name}.jsonl"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        with open(memory_file, "w", encoding="utf-8") as f:
            f.write(jsonl_content)
        print(f"[+] Archivo JSONL memoria exportado: {memory_file.name}")

    elif product_name == "faithful":
        # Faithful JSON archive
        faithful_content = format_faithful_json(filtered, display_name)
        faithful_file = output_dir / f"faithful_{display_name}.json"
        faithful_file.parent.mkdir(parents=True, exist_ok=True)
        with open(faithful_file, "w", encoding="utf-8") as f:
            f.write(faithful_content)
        print(f"[+] Archivo JSON fiel exportado: {faithful_file.name}")

    elif product_name == "digest":
        # Digest summary
        max_chars = getattr(product_config, "truncate_tool_output", 500)
        digest_content = format_digest_summary(filtered, display_name, max_chars=max_chars)
        digest_file = output_dir / f"digest_{display_name}.md"
        digest_file.parent.mkdir(parents=True, exist_ok=True)
        with open(digest_file, "w", encoding="utf-8") as f:
            f.write(digest_content)
        print(f"[+] Resumen digest exportado: {digest_file.name}")

    else:
        # Fallback: transcript format
        markdown = format_markdown_transcript(
            filtered, display_name, include_timestamps=not no_timestamps
        )
        output_file = output_dir / f"session_{display_name}.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"[+] Archivo Markdown exportado (predeterminado): {output_file.name}")


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle --list-presets (early return)
    if args.list_presets:
        presets = list_presets()
        print("Presets disponibles:")
        for preset_name in presets:
            preset = get_preset(preset_name)
            print(f"  - {preset_name}: {preset.description}")
        return 0

    # Build product configs (from --preset or --products or default)
    product_configs = []

    # Handle --preset argument
    if args.preset:
        if args.preset in PRESETS:
            product_configs.append(get_preset(args.preset))
        elif args.preset in ("transcript", "memory", "digest", "faithful"):
            product_map = {
                "transcript": transcript,
                "memory": memory,
                "digest": digest,
                "faithful": faithful,
            }
            product_configs.append(product_map[args.preset])
        else:
            print(f"[!] Error: '{args.preset}' no es un preset reconocido.")
            print(f"Use --list-presets para ver las opciones disponibles.")
            return 1

    # Handle --products (alternative to --preset)
    if args.products and not args.preset:
        for product in args.products:
            product_configs.append(product)

    # Default: transcript mode if no preset specified
    if not product_configs:
        product_configs.append(transcript)

    # Apply --role flag override AFTER product_configs is built
    if args.role:
        role_override = args.role
        forced_role = "user" if role_override == "user" else "assistant"
        new_configs = []
        for pc in product_configs:
            current_name = getattr(pc, "name", "transcript")
            # Modify the product config's role_filter attribute
            if hasattr(pc, "role_filter"):
                pc.role_filter = [role_override]
            else:
                # Create a fresh ProductConfig with role filter
                from products import ProductConfig
                forced_config = ProductConfig(
                    name=current_name,
                    description=pc.description,
                    role_filter=[role_override],
                    include_tool_output=pc.include_tool_output,
                    truncate_tool_output=pc.truncate_tool_output,
                    no_reasoning=pc.no_reasoning,
                )
                new_configs.append(forced_config)
        product_configs = new_configs

    # Discover sessions
    codex_dir = args.codex_dir
    jsonl_files = discover_sessions(codex_dir)

    if not jsonl_files:
        print(f"[!] No se encontraron archivos .jsonl en: {codex_dir}")
        print(
            "  Asegúrate de que la extensión Codex esté instalada y tenga sesiones."
        )
        return 1

    print(f"[*] Se encontraron {len(jsonl_files)} archivos de sesión. Procesando...")
    print()

    # Process each session
    output_dir = Path(args.output)

    for i, file_path in enumerate(jsonl_files, 1):
        print(f"[/{len(jsonl_files)}] Procesando: {file_path.name}")

        # Use the first product config
        product_config = product_configs[0]

        process_session(
            file_path,
            product_config,
            output_dir,
            no_timestamps=args.no_timestamps,
            dry_run=args.dry_run,
        )

    print()
    print(f"¡Extracción completa! Revisa tu contenido en: {output_dir.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())