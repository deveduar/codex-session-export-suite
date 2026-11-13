"""CLI entry point for Codex Session Exporter.

Provides portable exports for Codex session JSONL files using products and
presets.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import (
    ConfigError,
    detect_codex_dir_with_origin,
    expand_path,
    load_config,
)
from .extract import (
    extract_session_events_from_jsonl,
    read_session_metadata,
    retain_recent_turns,
)
from .organize import (
    build_session_record,
    create_run_dir,
    compare_session_records,
    find_latest_run,
    find_codex_root,
    load_session_index,
    next_run_dir,
    product_filename,
    run_label,
    session_folder_name,
    summarize_token_usage,
    write_indexes,
    write_metadata,
)
from .output import (
    format_jsonl_memory,
    format_jsonl_corpus,
    format_markdown_transcript,
    format_markdown_activity_transcript,
)
from .products import (
    ResolvedProduct,
    get_preset,
    get_product,
    list_presets,
    list_products,
    resolve_preset,
    RUN_LEVEL_PRODUCTS,
)


VERSION = "3.0.0"

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_NO_DATA = 2


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
        prog="codexexport.py",
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
        help="Output directory (default: config or ./exports)",
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
        help=f"Base products to export: {', '.join(list_products())}",
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
        "--sessions",
        type=str,
        nargs="+",
        default=None,
        help="Only export these sessions (matches session id, short id, or source filename)",
    )

    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Only export the N most recent sessions by session timestamp",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress per-file and informational output; keep errors and a final summary",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON on stdout (implies --quiet)",
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
        "--list-sessions",
        action="store_true",
        default=False,
        help="List discovered sessions and exit without exporting",
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


def session_selection_keys(file_path: Path) -> List[str]:
    """Return the lowercase tokens that identify a session file.

    Supports matching on the full session id, its short form, the source
    filename stem and the filename itself, so ``--sessions`` is forgiving about
    which identifier the caller has at hand.
    """
    metadata = read_session_metadata(file_path)
    keys = {file_path.stem.lower(), file_path.name.lower()}
    session_id = metadata.get("id")
    if session_id:
        session_id = str(session_id)
        keys.add(session_id.lower())
        compact = "".join(ch for ch in session_id if ch.isalnum())
        if compact:
            keys.add(compact[:8].lower())
    return [key for key in keys if key]


def select_sessions(
    files: List[Path],
    sessions: Optional[Sequence[str]] = None,
    last: Optional[int] = None,
) -> List[Path]:
    """Narrow discovered session files by explicit ids and/or recency.

    This is session-level selection: it chooses whole sessions. It is distinct
    from ``--recent-turns``, which trims turns *within* every selected session.
    """
    selected = list(files)

    if sessions:
        wanted = {token.strip().lower() for token in sessions if token and token.strip()}
        matched = []
        for file_path in selected:
            keys = set(session_selection_keys(file_path))
            if keys & wanted:
                matched.append(file_path)
        selected = matched

    if last is not None and last > 0:
        def sort_key(file_path: Path):
            metadata = read_session_metadata(file_path)
            return str(metadata.get("timestamp") or file_path.name)

        selected = sorted(selected, key=sort_key)[-last:]

    return selected


def preset_product_names(name: str) -> List[str]:
    """Return the product names used by a preset."""
    preset = get_preset(name)

    if "products" in preset:
        return list(preset["products"])

    if "product" in preset:
        return [preset["product"]]

    return []


def apply_overrides(
    product_config: ResolvedProduct,
    role: Optional[str] = None,
    truncate: Optional[int] = None,
    include_developer: bool = False,
    strip_boilerplate: Optional[bool] = None,
) -> ResolvedProduct:
    """Apply CLI/config overrides without mutating global products."""
    config = product_config.clone()

    if role:
        normalized_role = str(role).strip().lower()
        if normalized_role == "both":
            config.role_filter = []
            config.role = None
        elif normalized_role in ("user", "assistant"):
            config.role_filter = [normalized_role]
            config.role = None
        else:
            raise ValueError(f"Invalid role: '{role}'. Use user, assistant or both.")

    if include_developer and config.developer == "exclude":
        config.developer = "include"

    if strip_boilerplate is not None:
        config.strip_boilerplate = bool(strip_boilerplate)

    if truncate is not None:
        config.truncate_chars = truncate if truncate > 0 else None

    return config


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
    product_config: ResolvedProduct,
    output_file: Path,
    display_name: str,
    no_timestamps: bool = False,
    dry_run: bool = False,
    quiet: bool = False,
    append_output: bool = False,
    session_metadata: Optional[Dict[str, object]] = None,
) -> None:
    """Format messages for one product and write the output file."""
    product_name = getattr(product_config, "name", "transcript")

    if dry_run:
        if not quiet:
            print(f"[*] {product_name}: {file_path.name} -> {output_file}")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if product_name == "faithful":
        shutil.copyfile(file_path, output_file)
        if not quiet:
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
            title=str((session_metadata or {}).get("thread_name") or display_name),
            session_metadata=session_metadata,
        )
        label = "Markdown transcript"
    elif product_name == "memory":
        metadata = session_metadata or {}
        content = format_jsonl_memory(
            filtered_events,
            display_name,
            session_id=str(metadata.get("id") or "") or None,
            session_title=str(metadata.get("thread_name") or display_name),
        )
        label = "Structured retrieval JSONL"
    elif product_name == "corpus":
        metadata = session_metadata or {}
        content = format_jsonl_corpus(
            [event for event in filtered_events if event.get("kind") == "message"],
            display_name,
            session_id=str(metadata.get("id") or "") or None,
            session_title=str(metadata.get("thread_name") or display_name),
        )
        label = "Normalized message corpus JSONL"
    else:
        content = format_markdown_transcript(
            filtered_events,
            filename=display_name,
            include_timestamps=not no_timestamps,
            title=str((session_metadata or {}).get("thread_name") or display_name),
            session_metadata=session_metadata,
        )
        label = (
            "Developer instructions"
            if product_name == "instructions"
            else "Markdown conversation"
        )

    mode = "a" if append_output else "w"
    with open(output_file, mode, encoding="utf-8") as handle:
        handle.write(content)
        if append_output and content:
            handle.write("\n")

    if not quiet:
        print(f"[+] {label} exported: {output_file.name}")


def _resolve_codex_dir(
    explicit: Optional[str],
    config: Dict[str, object],
) -> Tuple[Optional[Path], str]:
    """Resolve the Codex directory and report which source won.

    Precedence: positional source > INI ``codex_dir`` > ``CODEX_HOME`` >
    ``~/.codex`` > XDG auto-detection.
    """
    if explicit:
        return expand_path(explicit), "argument"

    configured_dir = config.get("codex_dir")
    if configured_dir:
        return expand_path(str(configured_dir)), "config"

    return detect_codex_dir_with_origin()


def _emit_json(payload: Dict[str, object]) -> None:
    """Print a single machine-readable JSON object."""
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _error(message: str) -> None:
    """Write a human-readable error to stderr."""
    print(message, file=sys.stderr)


def _list_sessions(
    codex_path: Path,
    source_origin: str,
    include_archived: bool,
    sessions_selection: Optional[Sequence[str]],
    last: Optional[int],
    json_output: bool,
) -> int:
    """List selected session metadata without creating an export run."""
    files = select_sessions(
        discover_sessions(codex_path, include_archived=include_archived),
        sessions=sessions_selection,
        last=last,
    )
    codex_root = find_codex_root(codex_path)
    session_index = load_session_index(codex_root)
    records = [
        build_session_record(
            file_path,
            codex_root,
            session_index,
            include_fingerprint=False,
            include_usage=False,
        )
        for file_path in files
    ]
    sessions = [
        {
            "id": record.get("id"),
            "started_at": record.get("started_at"),
            "thread_name": record.get("thread_name"),
            "project": record.get("project"),
            "source_file": record.get("source_file"),
        }
        for record in records
    ]
    if json_output:
        _emit_json(
            {
                "tool": "codex_session_exporter",
                "version": VERSION,
                "ok": True,
                "source": {
                    "resolved": str(codex_path),
                    "exists": codex_path.exists(),
                    "origin": source_origin,
                },
                "sessions_found": len(sessions),
                "sessions": sessions,
            }
        )
        return EXIT_OK

    print(f"Sessions found: {len(sessions)}")
    for session in sessions:
        title = session["thread_name"] or session["project"] or "(untitled)"
        print(
            f"{session['started_at'] or '-'}  "
            f"{session['id'] or '-'}  {title}  [{session['source_file']}]"
        )
    return EXIT_OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point for the CLI."""
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    quiet = bool(args.quiet or args.json)

    if args.list_presets:
        if args.json:
            _emit_json(
                {
                    "tool": "codex_session_exporter",
                    "version": VERSION,
                    "products": [
                        {
                            "name": product_name,
                            "description": get_product(product_name).description,
                        }
                        for product_name in list_products()
                    ],
                    "presets": [
                        {
                            "name": preset_name,
                            "description": get_preset(preset_name)["description"],
                            "recipe": preset_product_names(preset_name),
                        }
                        for preset_name in list_presets()
                    ],
                }
            )
            return EXIT_OK

        print("Base products:")
        for product_name in list_products():
            product = get_product(product_name)
            print(f"  - {product_name}: {product.description}")

        print()
        print("Presets:")
        for preset_name in list_presets():
            preset = get_preset(preset_name)
            products = ", ".join(preset_product_names(preset_name))
            print(f"  - {preset_name}: {preset['description']}")
            print(f"    recipe: {products}")

        return EXIT_OK

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _error(f"[!] {exc}")
        return EXIT_CONFIG

    codex_path, source_origin = _resolve_codex_dir(args.codex_dir, config)
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
    sessions_selection = (
        args.sessions if args.sessions is not None else config.get("sessions")
    )
    last = args.last if args.last is not None else config.get("last")

    if args.list_sessions:
        if codex_path is None:
            _error("[!] Could not auto-detect the Codex directory.")
            _error("  Pass it as the first argument or set it in codex_export.ini.")
            return EXIT_CONFIG
        if not codex_path.exists():
            _error(f"[!] Codex input path does not exist: {codex_path}")
            return EXIT_CONFIG
        if last is not None and last <= 0:
            _error("[!] --last must be greater than zero.")
            return EXIT_CONFIG
        return _list_sessions(
            codex_path,
            source_origin,
            bool(include_archived),
            sessions_selection,
            last,
            args.json,
        )

    if args.no_timestamps is None:
        no_timestamps = not config["timestamps"]
    else:
        no_timestamps = args.no_timestamps

    if truncate is not None and truncate < 0:
        _error("[!] --truncate cannot be negative.")
        return EXIT_CONFIG
    if recent_turns is not None and recent_turns <= 0:
        _error("[!] --recent-turns must be greater than zero.")
        return EXIT_CONFIG
    if last is not None and last <= 0:
        _error("[!] --last must be greater than zero.")
        return EXIT_CONFIG

    selected_preset: Optional[str] = None
    try:
        if args.products:
            product_configs = [
                ResolvedProduct(get_product(name))
                for name in args.products
            ]
        elif args.preset:
            selected_preset = args.preset
            product_configs = resolve_preset(args.preset)
        elif config.get("products"):
            product_configs = [
                ResolvedProduct(get_product(name))
                for name in config["products"]
            ]
        elif config.get("preset"):
            selected_preset = str(config["preset"])
            product_configs = resolve_preset(selected_preset)
        else:
            product_configs = [ResolvedProduct(get_product("transcript"))]
    except (KeyError, ValueError) as exc:
        _error(f"[!] Error: {exc}")
        _error("Use --list-presets to see available options.")
        return EXIT_CONFIG

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
        _error(f"[!] Error: {exc}")
        return EXIT_CONFIG

    if codex_path is None:
        _error("[!] Could not auto-detect the Codex directory.")
        _error("  Pass it as the first argument or set it in codex_export.ini.")
        return EXIT_CONFIG

    if not codex_path.exists():
        _error(f"[!] Codex input path does not exist: {codex_path}")
        return EXIT_CONFIG

    output_base = expand_path(output_value) or Path("./exports")

    if args.check_updates:
        latest = find_latest_run(output_base)
        if latest is None:
            if args.json:
                _emit_json(
                    {
                        "tool": "codex_session_exporter",
                        "version": VERSION,
                        "ok": False,
                        "reason": "no_baseline",
                        "run_dir": None,
                        "baseline": None,
                        "current_sessions": 0,
                        "comparison": None,
                    }
                )
            else:
                _error(f"[!] No run metadata found under: {output_base}")
                _error("  Create an export before checking for updates.")
            return EXIT_CONFIG

        latest_run_dir, latest_metadata = latest
        if args.include_archived is None:
            include_archived = latest_metadata.get(
                "include_archived",
                include_archived,
            )

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
            if args.json:
                _emit_json(
                    {
                        "tool": "codex_session_exporter",
                        "version": VERSION,
                        "ok": False,
                        "reason": "baseline_missing_fingerprints",
                        "run_dir": str(latest_run_dir),
                        "baseline": latest_run_dir.name,
                        "current_sessions": len(current_records),
                        "comparison": None,
                    }
                )
            else:
                _error(f"[!] Cannot compare this run: {exc}")
                _error("  Create a new export with source fingerprints first.")
            return EXIT_CONFIG

        if args.json:
            _emit_json(
                {
                    "tool": "codex_session_exporter",
                    "version": VERSION,
                    "ok": True,
                    "run_dir": str(latest_run_dir),
                    "baseline": latest_run_dir.name,
                    "current_sessions": len(current_records),
                    "comparison": {
                        "new": [record.get("source_file") for record in comparison["new"]],
                        "modified": [
                            record.get("source_file")
                            for record in comparison["modified"]
                        ],
                        "unchanged_count": len(comparison["unchanged"]),
                        "not_found_in_scan": [
                            record.get("source_file")
                            for record in comparison["not_found_in_scan"]
                        ],
                    },
                }
            )
            return EXIT_OK

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

        return EXIT_OK

    jsonl_files = discover_sessions(codex_path, include_archived=include_archived)
    jsonl_files = select_sessions(
        jsonl_files,
        sessions=sessions_selection,
        last=last,
    )
    if not jsonl_files:
        reason = (
            "no_sessions_matched_selection"
            if sessions_selection or last
            else "no_jsonl_files_found"
        )
        if args.json:
            _emit_json(
                {
                    "tool": "codex_session_exporter",
                    "version": VERSION,
                    "ok": False,
                    "source": {
                        "resolved": str(codex_path),
                        "exists": codex_path.exists(),
                        "origin": source_origin,
                    },
                    "sessions_found": 0,
                    "no_data_reason": reason,
                    "run_dir": None,
                    "dry_run": bool(args.dry_run),
                }
            )
        else:
            _error(f"[!] No .jsonl files found in: {codex_path}")
            _error("  Pass the Codex directory, sessions directory, a subdirectory, or a .jsonl file.")
        return EXIT_NO_DATA

    now = datetime.now().astimezone()
    product_names = [product.name for product in product_configs]

    label = run_label(selected_preset, product_names)
    run_dir: Path = next_run_dir(output_base, label, now)
    if not args.dry_run:
        run_dir = create_run_dir(output_base, label, now)

    config_path = config.get("_config_path")
    if not quiet:
        if config_path:
            print(f"[*] Configuration: {config_path}")

        print(f"[*] Codex directory: {codex_path}")
        if include_archived:
            print("[*] Archived sessions: included")
        print(f"[*] Run directory: {run_dir}")
        print(f"[*] Found {len(jsonl_files)} session files. Processing...")
        if len(product_configs) > 1:
            print(f"[*] Products: {', '.join(product_names)}")
        print()

    codex_root = find_codex_root(codex_path)
    session_index = load_session_index(codex_root)
    session_records = []
    written_output_paths = set()

    for index, file_path in enumerate(jsonl_files, 1):
        if not quiet:
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

        if not messages and not events and not quiet:
            print(f"[*] No extractable conversation text in {file_path.name}")

        display_name = str(record["slug"])
        session_dir = run_dir / session_folder_name(display_name)
        session_title = str(record.get("thread_name") or record.get("project") or display_name)
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

            if product_name in RUN_LEVEL_PRODUCTS:
                output_file = run_dir / f"{product_name}.jsonl"
            else:
                output_file = session_dir / product_filename(display_name, product_name)

            process_session(
                file_path,
                product_events,
                product_config,
                output_file,
                display_name,
                no_timestamps=no_timestamps,
                dry_run=args.dry_run,
                quiet=quiet or product_name in RUN_LEVEL_PRODUCTS,
                append_output=product_name in RUN_LEVEL_PRODUCTS,
                session_metadata=record,
            )

            record["outputs"][product_name] = output_file.relative_to(
                run_dir
            ).as_posix()

            if not args.dry_run:
                written_output_paths.add(output_file.relative_to(run_dir).as_posix())

        if not record["outputs"]:
            record["skipped"] = True
            record["reason"] = "no extractable conversation text or source product selected"
        session_records.append(record)

    files_written = len(written_output_paths)
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
        "schema_version": 8,
        "tool": "codex_session_exporter",
        "version": VERSION,
        "run_id": run_dir.name,
        "generated_at": now.isoformat(),
        "codex_dir": str(codex_path.absolute()),
        "source_origin": source_origin,
        "output_dir": str(output_base.absolute()),
        "include_archived": bool(include_archived),
        "recent_turns": recent_turns,
        "sessions_selected": list(sessions_selection) if sessions_selection else None,
        "last": last,
        "timestamps": not no_timestamps,
        "preset": selected_preset,
        "products": product_names,
        "product_artifacts": {
            product_name: f"{product_name}.jsonl"
            for product_name in product_names
            if product_name in RUN_LEVEL_PRODUCTS
            and f"{product_name}.jsonl" in written_output_paths
        },
        "resolved_products": [
            {
                "name": product.name,
                "role": product.role,
                "role_filter": list(product.role_filter),
                "developer": product.developer,
                "message_only": bool(product.message_only),
                "clean_user_prompts": bool(product.clean_user_prompts),
                "strip_boilerplate": bool(product.strip_boilerplate),
                "truncate_chars": product.truncate_chars,
            }
            for product in product_configs
        ],
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
        if not quiet:
            print(f"[*] Would write: {run_dir / 'metadata.json'}")
            print(f"[*] Would write: {run_dir / 'index.md'}")
            for product_name in RUN_LEVEL_PRODUCTS:
                if product_name in product_names and any(
                    product_name in record.get("outputs", {})
                    for record in session_records
                ):
                    print(f"[*] Would write: {run_dir / f'{product_name}.jsonl'}")
            for product_name in product_names:
                if any(
                    product_name in record.get("outputs", {})
                    for record in session_records
                ):
                    print(f"[*] Would write: {run_dir / f'index.{product_name}.md'}")
    else:
        metadata_path = write_metadata(run_dir, metadata)
        index_paths = write_indexes(run_dir, metadata)
        if not quiet:
            print(f"[+] Metadata exported: {metadata_path.name}")
            for path in index_paths:
                print(f"[+] Index exported: {path.relative_to(run_dir).as_posix()}")

    target = run_dir

    if args.json:
        _emit_json(
            {
                "tool": "codex_session_exporter",
                "version": VERSION,
                "ok": True,
                "run_dir": str(target),
                "dry_run": bool(args.dry_run),
                "source": {
                    "resolved": str(codex_path),
                    "exists": codex_path.exists(),
                    "origin": source_origin,
                },
                "sessions_found": len(jsonl_files),
                "files_written": files_written,
            }
        )
        return EXIT_OK

    if not quiet:
        print()
    if args.dry_run:
        print(f"Dry run complete. Output would be written to: {target.absolute()}")
    else:
        print(f"Export complete. Check your files in: {target.absolute()}")

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())