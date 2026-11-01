"""CLI entry point for Codex Session Exporter.

Provides portable exports for Codex session JSONL files using products and
presets.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from config import ConfigError, detect_codex_dir, expand_path, load_config
from extract import extract_session_events_from_jsonl, retain_recent_turns
from organize import (
    build_session_record,
    create_run_dir,
    compare_session_records,
    find_latest_run,
    find_codex_root,
    load_session_index,
    next_run_dir,
    product_filename,
    run_label,
    summarize_token_usage,
    write_indexes,
    write_metadata,
)
from output import (
    format_jsonl_memory,
    format_markdown_transcript,
    format_markdown_activity_transcript,
)
from products import (
    ProductConfig,
    get_preset,
    get_product,
    list_presets,
    list_products,
    resolve_preset,
)


VERSION = "2.10.0"

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
        description="Export local Codex session JSONL as transcripts and data products.",
        epilog="Presets: " + ", ".join(list_presets()),
    )

    parser.add_argument(
        "codex_dir",
        type=str,
        nargs="?",
        default=None,
        help="Codex directory, sessions directory, subdirectory or a single .jsonl file (default: auto-detect)",
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
        help=f"Export preset: {', '.join(list_presets())}",
    )

    parser.add_argument(
        "--products",
        type=str,
        nargs="+",
        default=None,
        help=f"Products to export: {', '.join(list_products())}",
    )

    parser.add_argument(
        "--role",
        type=str,
        default=None,
        help="Filter chat messages and tool events by role: user, assistant, or both",
    )

    parser.add_argument(
        "--include-developer",
        action="store_true",
        default=None,
        help="Include developer instructions in products that exclude them by default",
    )

    parser.add_argument(
        "--truncate",
        type=int,
        default=None,
        help="Keep the first N characters of each message or tool body (0 disables truncation)",
    )

    parser.add_argument(
        "--recent-turns",
        type=int,
        default=None,
        help="Keep the latest N whole user turns with their messages and tool events",
    )

    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        default=None,
        help="Hide timestamps in output",
    )

    parser.add_argument(
        "--flat",
        action="store_true",
        default=False,
        help="Write files directly into the output directory instead of a timestamped run folder",
    )

    parser.add_argument(
        "--include-archived",
        action="store_true",
        default=None,
        help="Include sessions from Codex's archived_sessions directory",
    )

    parser.add_argument(
        "--check-updates",
        action="store_true",
        default=False,
        help="Compare current Codex sessions with the latest export run",
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
        help="List available products and presets",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"Codex Session Exporter {VERSION}",
    )

    parser.add_argument(
        "--strip-boilerplate",
        action="store_true",
        default=None,
        help="Remove recognized generated boilerplate from derived user prompts and conversation text",
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


def discover_sessions(
    codex_path: Optional[Path],
    include_archived: bool = False,
) -> List[Path]:
    """Discover .jsonl session files.

    Accepts:
        - the Codex root directory (contains ``sessions/``)
        - the ``sessions`` directory itself
        - a year/month subdirectory
        - a single ``.jsonl`` file
    """
    if codex_path is None or not codex_path.exists():
        return []

    if codex_path.is_file():
        if codex_path.suffix.lower() == ".jsonl":
            return [codex_path]
        return []

    if not codex_path.is_dir():
        return []

    path_name = codex_path.name.lower()
    if path_name == "archived_sessions":
        search_roots = [codex_path]
    elif path_name == "sessions":
        search_roots = [codex_path]
        archived_dir = codex_path.parent / "archived_sessions"
        if include_archived and archived_dir.is_dir():
            search_roots.append(archived_dir)
    elif (codex_path / "sessions").is_dir():
        search_roots = [codex_path / "sessions"]
        archived_dir = codex_path / "archived_sessions"
        if include_archived and archived_dir.is_dir():
            search_roots.append(archived_dir)
    elif (codex_path / "archived_sessions").is_dir():
        search_roots = (
            [codex_path / "archived_sessions"] if include_archived else []
        )
    else:
        search_roots = [codex_path]
        if include_archived:
            codex_root = find_codex_root(codex_path)
            archived_dir = codex_root / "archived_sessions" if codex_root else None
            if archived_dir is not None and archived_dir.is_dir():
                search_roots.append(archived_dir)

    jsonl_files = []
    for search_root in search_roots:
        try:
            jsonl_files.extend(search_root.glob("**/*.jsonl"))
        except OSError:
            continue
    jsonl_files = sorted(jsonl_files)

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


def preset_product_names(name: str) -> List[str]:
    """Return the product names used by a preset."""
    preset = get_preset(name)

    if "products" in preset:
        return list(preset["products"])

    if "product" in preset:
        return [preset["product"]]

    return []


def apply_overrides(
    product_config: ProductConfig,
    role: Optional[str] = None,
    truncate: Optional[int] = None,
    include_developer: bool = False,
    strip_boilerplate: Optional[bool] = None,
) -> ProductConfig:
    """Apply CLI/config overrides without mutating global products."""
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
            raise ValueError(f"Invalid role: '{role}'. Use user, assistant or both.")

    if include_developer and product_config.developer == "exclude":
        overrides["developer"] = "include"

    if strip_boilerplate is not None:
        overrides["strip_boilerplate"] = bool(strip_boilerplate)

    if truncate is not None:
        overrides["truncate_chars"] = truncate if truncate > 0 else None

    return product_config.clone(**overrides) if overrides else product_config


def output_path_for(product_name: str, display_name: str, output_dir: Path) -> Path:
    """Return the output file path for a product."""
    if product_name == "memory":
        return output_dir / f"memory_{display_name}.jsonl"
    if product_name == "faithful":
        return output_dir / f"faithful_{display_name}.jsonl"
    if product_name == "conversation":
        return output_dir / f"conversation_{display_name}.md"
    if product_name == "instructions":
        return output_dir / f"instructions_{display_name}.md"
    return output_dir / f"session_{display_name}.md"


def product_skip_reason(product_name: str) -> str:
    """Return a human-readable reason for a product with no data."""
    if product_name == "instructions":
        return "no developer instructions"
    if product_name in ("conversation", "transcript"):
        return "no messages"
    return "no extractable events"


def process_session(
    file_path: Path,
    events: List[dict],
    product_config: ProductConfig,
    output_file: Path,
    display_name: str,
    no_timestamps: bool = False,
    dry_run: bool = False,
) -> None:
    """Format messages for one product and write the output file."""
    product_name = getattr(product_config, "name", "transcript")

    if dry_run:
        print(f"[*] {product_name}: {file_path.name} -> {output_file}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if product_name == "faithful":
        shutil.copyfile(file_path, output_file)
        print(f"[+] Source JSONL copied: {output_file.name}")
        return

    filtered_events = [dict(event) for event in events]
    limit = product_config.truncate_chars
    if limit:
        for event in filtered_events:
            for key in ("text", "arguments", "output"):
                value = event.get(key)
                if isinstance(value, str) and len(value) > limit:
                    event[key] = value[:limit] + "..."

    if product_name == "transcript":
        content = format_markdown_activity_transcript(
            filtered_events,
            filename=display_name,
            include_timestamps=not no_timestamps,
        )
        label = "Markdown transcript"
    elif product_name == "memory":
        content = format_jsonl_memory(filtered_events, display_name)
        label = "Structured RAG JSONL"
    else:
        content = format_markdown_transcript(
            filtered_events,
            filename=display_name,
            include_timestamps=not no_timestamps,
        )
        label = (
            "Developer instructions"
            if product_name == "instructions"
            else "Markdown conversation"
        )

    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write(content)

    print(f"[+] {label} exported: {output_file.name}")


def _resolve_codex_dir(explicit: Optional[str], config: Dict[str, object]) -> Optional[Path]:
    """Resolve the Codex directory from CLI, config, environment or auto-detect."""
    if explicit:
        return expand_path(explicit)

    configured_dir = config.get("codex_dir")
    if configured_dir:
        return expand_path(str(configured_dir))

    return detect_codex_dir()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point for the CLI."""
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        print("Products:")
        for product_name in list_products():
            product = get_product(product_name)
            print(f"  - {product_name}: {product.description}")

        print()
        print("Presets:")
        for preset_name in list_presets():
            preset = get_preset(preset_name)
            products = ", ".join(preset_product_names(preset_name))
            print(f"  - {preset_name}: {preset['description']}")
            print(f"    products: {products}")

        return 0

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"[!] {exc}")
        return 1

    codex_path = _resolve_codex_dir(args.codex_dir, config)
    output_value = args.output if args.output is not None else config["output_dir"]
    include_archived = (
        args.include_archived
        if args.include_archived is not None
        else config.get("include_archived", False)
    )
    role = args.role if args.role is not None else config["role"]
    include_developer = (
        args.include_developer
        if args.include_developer is not None
        else config.get("include_developer", False)
    )
    strip_boilerplate = (
        args.strip_boilerplate
        if args.strip_boilerplate is not None
        else config.get("strip_boilerplate", False)
    )
    truncate = args.truncate if args.truncate is not None else config["truncate"]
    recent_turns = (
        args.recent_turns
        if args.recent_turns is not None
        else config.get("recent_turns")
    )
    layout = "flat" if args.flat else str(config.get("layout") or "run")

    if args.no_timestamps is None:
        no_timestamps = not config["timestamps"]
    else:
        no_timestamps = args.no_timestamps

    if truncate is not None and truncate < 0:
        print("[!] --truncate cannot be negative.")
        return 1
    if recent_turns is not None and recent_turns <= 0:
        print("[!] --recent-turns must be greater than zero.")
        return 1

    selected_preset: Optional[str] = None
    try:
        if args.products:
            product_configs = [get_product(name) for name in args.products]
        elif args.preset:
            selected_preset = args.preset
            product_configs = resolve_preset(args.preset)
        elif config.get("products"):
            product_configs = [get_product(name) for name in config["products"]]
        elif config.get("preset"):
            selected_preset = str(config["preset"])
            product_configs = resolve_preset(selected_preset)
        else:
            product_configs = [get_product("transcript")]
    except (KeyError, ValueError) as exc:
        print(f"[!] Error: {exc}")
        print("Use --list-presets to see available options.")
        return 1

    try:
        product_configs = [
            apply_overrides(
                product_config,
                role=role,
                truncate=truncate,
                include_developer=include_developer,
                strip_boilerplate=strip_boilerplate,
            )
            for product_config in product_configs
        ]
    except ValueError as exc:
        print(f"[!] Error: {exc}")
        return 1

    if codex_path is None:
        print("[!] Could not auto-detect the Codex directory.")
        print("  Pass it as the first argument or set it in codex_export.ini.")
        return 1

    output_base = expand_path(output_value) or Path("./codex_exports")

    if args.check_updates:
        latest = find_latest_run(output_base)
        if latest is None:
            print(f"[!] No run metadata found under: {output_base}")
            print("  Create a run-layout export before checking for updates.")
            return 1

        latest_run_dir, latest_metadata = latest
        if args.include_archived is None:
            include_archived = latest_metadata.get(
                "include_archived",
                include_archived,
            )
        if not codex_path.exists():
            print(f"[!] Codex input path does not exist: {codex_path}")
            return 1

        codex_root = find_codex_root(codex_path)
        session_index = load_session_index(codex_root)
        current_files = discover_sessions(codex_path, include_archived=include_archived)
        current_records = []
        for file_path in current_files:
            current_records.append(
                build_session_record(
                    file_path,
                    codex_root,
                    session_index,
                    include_usage=False,
                )
            )
        previous_records = latest_metadata.get("sessions", [])
        try:
            comparison = compare_session_records(previous_records, current_records)
        except ValueError as exc:
            print(f"[!] Cannot compare this run: {exc}")
            print("  Create a new export with source fingerprints first.")
            return 1

        print(f"[*] Comparing with: {latest_run_dir}")
        print(f"[*] Current sessions found: {len(current_records)}")
        for status in (
            "new",
            "modified",
            "unchanged",
            "not_found_in_scan",
        ):
            records = comparison[status]
            label = status.replace("_", " ").title()
            print(f"[*] {label}: {len(records)}")
            for record in records:
                if status in (
                    "new",
                    "modified",
                    "not_found_in_scan",
                ):
                    print(f"    - {record.get('thread_name') or record.get('project') or record.get('source_file')}")

        if comparison["not_found_in_scan"]:
            print("[*] Not found means absent from this scan path; it does not prove deletion.")

        return 0

    jsonl_files = discover_sessions(codex_path, include_archived=include_archived)
    if not jsonl_files:
        print(f"[!] No .jsonl files found in: {codex_path}")
        print("  Pass the Codex directory, sessions directory, a subdirectory, or a .jsonl file.")
        return 1

    now = datetime.now().astimezone()
    product_names = [product.name for product in product_configs]

    run_dir: Optional[Path] = None
    if layout == "run":
        label = run_label(selected_preset, product_names)
        run_dir = next_run_dir(output_base, label, now)
        if not args.dry_run:
            run_dir = create_run_dir(output_base, label, now)

    config_path = config.get("_config_path")
    if config_path:
        print(f"[*] Configuration: {config_path}")

    print(f"[*] Codex directory: {codex_path}")
    if include_archived:
        print("[*] Archived sessions: included")
    if run_dir is not None:
        print(f"[*] Run directory: {run_dir}")
    print(f"[*] Found {len(jsonl_files)} session files. Processing...")
    if len(product_configs) > 1:
        print(f"[*] Products: {', '.join(product_names)}")
    print()

    codex_root = find_codex_root(codex_path)
    session_index = load_session_index(codex_root)
    session_records = []
    files_written = 0

    for index, file_path in enumerate(jsonl_files, 1):
        print(f"[{index}/{len(jsonl_files)}] Processing: {file_path.name}")
        record = build_session_record(
            file_path,
            codex_root,
            session_index,
            include_fingerprint=run_dir is not None and not args.dry_run,
        )
        all_events = extract_session_events_from_jsonl(file_path)
        all_messages = [event for event in all_events if event.get("kind") == "message"]
        events = retain_recent_turns(all_events, recent_turns)
        messages = [event for event in events if event.get("kind") == "message"]
        record["message_count"] = len(messages)
        record["user_messages"] = sum(
            1 for message in messages if message.get("role") == "user"
        )
        record["assistant_messages"] = sum(
            1 for message in messages if message.get("role") == "assistant"
        )
        record["developer_messages"] = sum(
            1 for message in messages if message.get("role") == "developer"
        )
        record["event_count"] = len(events)
        if recent_turns is not None:
            record["source_message_count"] = len(all_messages)
        record["outputs"] = {}
        record["product_items"] = {}
        record["skipped_products"] = []
        record["skipped_product_reasons"] = {}
        record["skipped"] = False

        if not messages and not events:
            print(f"[*] No extractable conversation text in {file_path.name}")

        display_name = (
            str(record["slug"])
            if run_dir is not None
            else get_display_name(file_path)
        )
        for product_config in product_configs:
            product_name = product_config.name
            product_events = product_config.select_events(events)
            has_product_data = bool(product_events) or product_name == "faithful"
            if not has_product_data:
                record["skipped_products"].append(product_name)
                record["skipped_product_reasons"][product_name] = product_skip_reason(
                    product_name
                )
                continue

            record["product_items"][product_name] = (
                1 if product_name == "faithful" else len(product_events)
            )

            if run_dir is not None:
                output_file = (
                    run_dir
                    / product_name
                    / str(record.get("project_slug") or "unknown")
                    / product_filename(product_name, display_name)
                )
            else:
                output_file = output_path_for(
                    product_name,
                    display_name,
                    output_base,
                )

            process_session(
                file_path,
                product_events,
                product_config,
                output_file,
                display_name,
                no_timestamps=no_timestamps,
                dry_run=args.dry_run,
            )

            if run_dir is not None:
                record["outputs"][product_name] = output_file.relative_to(
                    run_dir
                ).as_posix()
            else:
                record["outputs"][product_name] = output_file.as_posix()

            if not args.dry_run:
                files_written += 1

        if not record["outputs"]:
            record["skipped"] = True
            record["reason"] = "no extractable conversation text or source product selected"
        session_records.append(record)

    if run_dir is not None:
        product_counts = {
            product_name: sum(
                1
                for record in session_records
                if product_name in record.get("outputs", {})
            )
            for product_name in product_names
        }
        product_omitted_counts = {
            product_name: sum(
                1
                for record in session_records
                if product_name in record.get("skipped_products", [])
            )
            for product_name in product_names
        }
        metadata = {
            "schema_version": 6,
            "tool": "codex_session_exporter",
            "version": VERSION,
            "run_id": run_dir.name,
            "generated_at": now.isoformat(),
            "codex_dir": str(codex_path.absolute()),
            "output_dir": str(output_base.absolute()),
            "include_archived": bool(include_archived),
            "preset": selected_preset,
            "products": product_names,
            "options": {
                "role": role,
                "include_developer": bool(include_developer),
                "strip_boilerplate": bool(strip_boilerplate),
                "truncate": truncate,
                "recent_turns": recent_turns,
                "timestamps": not no_timestamps,
            },
            "counts": {
                "sessions_found": len(jsonl_files),
                "sessions_exported": sum(
                    1 for record in session_records if not record.get("skipped")
                ),
                "sessions_skipped": sum(
                    1 for record in session_records if record.get("skipped")
                ),
                "sessions_with_derived_output": sum(
                    1
                    for record in session_records
                    if any(
                        product_name != "faithful"
                        for product_name in record.get("outputs", {})
                    )
                ),
                "sessions_source_only": sum(
                    1
                    for record in session_records
                    if record.get("outputs")
                    and not any(
                        product_name != "faithful"
                        for product_name in record.get("outputs", {})
                    )
                ),
                "sessions_with_messages": sum(
                    1
                    for record in session_records
                    if record.get("message_count", 0) > 0
                ),
                "sessions_with_developer": sum(
                    1
                    for record in session_records
                    if record.get("developer_messages", 0) > 0
                ),
                "product_counts": product_counts,
                "product_omitted_counts": product_omitted_counts,
                "files_written": files_written,
            },
            "usage_summary": summarize_token_usage(session_records),
            "sessions": session_records,
        }

        if args.dry_run:
            print(f"[*] Would write: {run_dir / 'metadata.json'}")
            print(f"[*] Would write: {run_dir / 'index.md'}")
            for product_name in product_names:
                if any(
                    product_name in record.get("outputs", {})
                    for record in session_records
                ):
                    print(f"[*] Would write: {run_dir / product_name / 'index.md'}")
        else:
            metadata_path = write_metadata(run_dir, metadata)
            index_paths = write_indexes(run_dir, metadata)
            print(f"[+] Metadata exported: {metadata_path.name}")
            for path in index_paths:
                print(f"[+] Index exported: {path.relative_to(run_dir).as_posix()}")

    print()
    target = run_dir if run_dir is not None else output_base
    if args.dry_run:
        print(f"Dry run complete. Output would be written to: {target.absolute()}")
    else:
        print(f"Export complete. Check your files in: {target.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
