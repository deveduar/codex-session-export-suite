"""CLI entry point for Codex Session Exporter.

Provides portable exports for Codex session JSONL files using products and
presets.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .config import (
    ConfigError,
    detect_codex_dir_with_origin,
    expand_path,
    load_config,
)
from .extract import (
    extract_session_events_from_jsonl,
    extract_session_messages_and_parts,
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
    summarize_token_usage,
    write_indexes,
    write_metadata,
)
from .output import (
    build_corpus_document,
    build_memory_record,
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
        "--run-label",
        type=str,
        default=None,
        help="Label appended to the timestamped run folder (default: preset or products)",
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


def _apply_truncation(events: List[dict], limit: Optional[int]) -> List[dict]:
    filtered = [dict(event) for event in events]
    if limit:
        for event in filtered:
            for key in ("text", "arguments", "output"):
                value = event.get(key)
                if isinstance(value, str) and len(value) > limit:
                    event[key] = value[:limit] + "..."
    return filtered


def _truncate_text_payloads(items: List[dict], limit: Optional[int]) -> List[dict]:
    result = [dict(item) for item in items]
    if limit:
        for item in result:
            text = item.get("text")
            if isinstance(text, str) and len(text) > limit:
                item["text"] = text[:limit] + "..."
    return result


def _session_tree(
    records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    by_id = {
        str(record.get("id")): record
        for record in records
        if record.get("id")
    }
    children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        parent_id = str(record.get("parent_thread_id") or "")
        session_id = str(record.get("id") or "")
        if parent_id and parent_id in by_id and parent_id != session_id:
            children_by_parent.setdefault(parent_id, []).append(record)

    child_ids = {
        id(child)
        for children in children_by_parent.values()
        for child in children
    }
    document_sessions: List[Dict[str, Any]] = []
    for record in records:
        if id(record) in child_ids:
            continue
        parent_id = str(record.get("parent_thread_id") or "")
        session_id = str(record.get("id") or "")
        if parent_id and parent_id != session_id and parent_id not in by_id:
            record["parent_unresolved"] = True
        document_sessions.append(record)
    return document_sessions, children_by_parent


def _session_descendants(
    record: Dict[str, Any],
    children_by_parent: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = {str(record.get("id") or "")}
    queue = list(children_by_parent.get(str(record.get("id") or ""), []))
    while queue:
        child = queue.pop(0)
        child_id = str(child.get("id") or "")
        if child_id in seen:
            continue
        seen.add(child_id)
        result.append(child)
        queue.extend(children_by_parent.get(child_id, []))
    return result


def _build_memory_tree(
    record: Dict[str, Any],
    children_by_parent: Dict[str, List[Dict[str, Any]]],
    structured_by_session: Dict[int, Dict[str, Any]],
    product_name: str,
    truncate_chars: Optional[int],
    seen: Set[str],
) -> Dict[str, Any]:
    session_id = str(record.get("id") or "")
    seen.add(session_id)
    data = structured_by_session[id(record)]["products"].get(product_name) or {
        "events": [],
        "messages": [],
        "parts": [],
    }
    children = []
    for child in children_by_parent.get(session_id, []):
        child_id = str(child.get("id") or "")
        if child_id in seen:
            continue
        children.append(
            _build_memory_tree(
                child,
                children_by_parent,
                structured_by_session,
                product_name,
                truncate_chars,
                seen,
            )
        )
    return build_memory_record(
        record,
        data["events"],
        data["messages"],
        data["parts"],
        record.get("usage") or {},
        children=children,
        truncate_chars=truncate_chars,
    )


def _register_output(
    record: Dict[str, Any],
    product_name: str,
    output_file: Path,
    run_dir: Path,
    artifact_paths: Dict[str, List[str]],
    written_output_paths: Set[str],
    dry_run: bool,
) -> None:
    relative = output_file.relative_to(run_dir).as_posix()
    record["outputs"][product_name] = relative
    paths = artifact_paths.setdefault(product_name, [])
    if relative not in paths:
        paths.append(relative)
    if not dry_run:
        written_output_paths.add(relative)


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

    filtered_events = _apply_truncation(events, product_config.truncate_chars)

    if product_name == "transcript":
        content = format_markdown_activity_transcript(
            filtered_events,
            filename=display_name,
            include_timestamps=not no_timestamps,
            title=str((session_metadata or {}).get("thread_name") or display_name),
            session_metadata=session_metadata,
        )
        label = "Markdown transcript"
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


def _source_revision(record: Dict[str, Any], codex_root: Optional[Path]) -> Optional[int]:
    """Return a cheap source-file revision for change-aware launchers."""
    source_file = record.get("source_file")
    if not source_file or codex_root is None:
        return None
    path = Path(source_file)
    if not path.is_absolute():
        path = codex_root / path
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


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
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "revision": _source_revision(record, codex_root),
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

    now = datetime.now(timezone.utc)
    product_names = [product.name for product in product_configs]

    label = (args.run_label or "").strip() or run_label(selected_preset, product_names)
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
    prepared_sessions = []
    for file_path in jsonl_files:
        record = build_session_record(
            file_path,
            codex_root,
            session_index,
            include_fingerprint=run_dir is not None and not args.dry_run,
        )
        prepared_sessions.append((file_path, record))

    project_dates: Dict[str, str] = {}
    for _file_path, record in prepared_sessions:
        key = str(record.get("project_key") or "no-project")
        date = str(record.get("updated_at") or record.get("date") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue
        if key not in project_dates or date > project_dates[key]:
            project_dates[key] = date
    for _file_path, record in prepared_sessions:
        key = str(record.get("project_key") or "no-project")
        date = project_dates.get(key, "unknown-date")
        record["project_date"] = date
        record["project_folder"] = f"{date}_{record['project_slug']}"

    session_records = []
    written_output_paths: Set[str] = set()
    artifact_paths: Dict[str, List[str]] = {name: [] for name in product_names}
    structured_by_session: Dict[int, Dict[str, Any]] = {}
    product_config_by_name = {config.name: config for config in product_configs}
    wants_structured = "memory" in product_names or "corpus" in product_names

    for index, (file_path, record) in enumerate(prepared_sessions, 1):
        if not quiet:
            print(f"[{index}/{len(prepared_sessions)}] Processing: {file_path.name}")
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
        project_dir = run_dir / str(record["project_folder"])
        structure = (
            extract_session_messages_and_parts(file_path) if wants_structured else None
        )
        if structure is not None and recent_turns is not None:
            retained_ordinals = {event.get("ordinal") for event in events}
            structure = {
                "messages": [
                    message
                    for message in structure["messages"]
                    if message.get("ordinal") in retained_ordinals
                ],
                "parts": [
                    part
                    for part in structure["parts"]
                    if part.get("message_ordinal") in retained_ordinals
                ],
            }
        structured_entry: Dict[str, Any] = {
            "file_path": file_path,
            "record": record,
            "events": events,
            "structure": structure,
            "products": {},
        }
        structured_by_session[id(record)] = structured_entry

        for product_config in product_configs:
            product_name = product_config.name
            product_events = product_config.select_events(events)

            if product_name in ("memory", "corpus"):
                selected_messages = product_config.select_messages(
                    (structure or {}).get("messages", [])
                )
                selected_ordinals = {
                    message.get("ordinal") for message in selected_messages
                }
                selected_parts = [
                    part
                    for part in (structure or {}).get("parts", [])
                    if part.get("message_ordinal") in selected_ordinals
                ]
                if not (product_events or selected_messages or selected_parts):
                    record["skipped_products"].append(product_name)
                    record["skipped_product_reasons"][product_name] = product_skip_reason(
                        product_name
                    )
                    continue

                structured_entry["products"][product_name] = {
                    "config": product_config,
                    "events": _apply_truncation(
                        product_events, product_config.truncate_chars
                    ),
                    "messages": _truncate_text_payloads(
                        selected_messages, product_config.truncate_chars
                    ),
                    "parts": _truncate_text_payloads(
                        selected_parts, product_config.truncate_chars
                    ),
                }
                continue

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
            output_file = project_dir / product_filename(display_name, product_name)

            process_session(
                file_path,
                product_events,
                product_config,
                output_file,
                display_name,
                no_timestamps=no_timestamps,
                dry_run=args.dry_run,
                quiet=quiet,
                session_metadata=record,
            )
            _register_output(
                record,
                product_name,
                output_file,
                run_dir,
                artifact_paths,
                written_output_paths,
                args.dry_run,
            )

        session_records.append(record)

    if wants_structured:
        document_sessions, children_by_parent = _session_tree(session_records)
        corpus_documents: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        memory_documents: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        for document_session in document_sessions:
            members = [document_session] + _session_descendants(
                document_session, children_by_parent
            )
            for product_name in ("memory", "corpus"):
                if product_name not in product_names:
                    continue

                contributing = []
                for member in members:
                    data = structured_by_session[id(member)]["products"].get(product_name)
                    if data and (
                        data.get("events") or data.get("messages") or data.get("parts")
                    ):
                        contributing.append((member, data))
                if not contributing:
                    continue

                config = product_config_by_name[product_name]
                session_data = next(
                    (
                        data
                        for member, data in contributing
                        if id(member) == id(document_session)
                    ),
                    None,
                ) or {"events": [], "messages": [], "parts": []}
                child_data = [
                    (member, data)
                    for member, data in contributing
                    if id(member) != id(document_session)
                ]

                if product_name == "memory":
                    document: Dict[str, Any] = _build_memory_tree(
                        document_session,
                        children_by_parent,
                        structured_by_session,
                        product_name,
                        config.truncate_chars,
                        set(),
                    )
                else:
                    corpus_members = [
                        {
                            "session": document_session,
                            "messages": session_data["messages"],
                        }
                    ]
                    corpus_members.extend(
                        {"session": member, "messages": data["messages"]}
                        for member, data in child_data
                    )
                    document = build_corpus_document(
                        document_session,
                        corpus_members,
                        truncate_chars=config.truncate_chars,
                    )
                if product_name == "corpus" and not (
                    document.get("text") or document.get("content")
                ):
                    continue

                if product_name in ("corpus", "memory"):
                    output_file = run_dir / f"{product_name}.jsonl"
                    if product_name == "corpus":
                        corpus_documents.append((document_session, document))
                    else:
                        memory_documents.append((document_session, document))
                _register_output(
                    document_session,
                    product_name,
                    output_file,
                    run_dir,
                    artifact_paths,
                    written_output_paths,
                    args.dry_run,
                )
                document_session["product_items"][product_name] = 1
                for record in [document_session] + [member for member, _ in child_data]:
                    if product_name in record.get("skipped_products", []):
                        record["skipped_products"].remove(product_name)
                        record["skipped_product_reasons"].pop(product_name, None)
                    if record is not document_session:
                        record["nested_in"] = document_session.get("id")

        if corpus_documents:
            corpus_file = run_dir / "corpus.jsonl"
            if args.dry_run:
                if not quiet:
                    print(f"[*] corpus: -> {corpus_file}")
            else:
                corpus_file.parent.mkdir(parents=True, exist_ok=True)
                with corpus_file.open("w", encoding="utf-8") as handle:
                    for _session, document in corpus_documents:
                        handle.write(format_jsonl_corpus(document))
                        handle.write("\n")
                if not quiet:
                    print(f"[+] Flattened corpus exported: {corpus_file.name}")

        if memory_documents:
            memory_file = run_dir / "memory.jsonl"
            if args.dry_run:
                if not quiet:
                    print(f"[*] memory: -> {memory_file}")
            else:
                memory_file.parent.mkdir(parents=True, exist_ok=True)
                with memory_file.open("w", encoding="utf-8") as handle:
                    for _session, document in memory_documents:
                        handle.write(format_jsonl_memory(document))
                        handle.write("\n")
                if not quiet:
                    print(f"[+] Session memory exported: {memory_file.name}")

    for record in session_records:
        if not record.get("outputs") and not record.get("nested_in"):
            record["skipped"] = True
            record["reason"] = "no extractable conversation text or source product selected"

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
        "run_label": label,
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
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
        "product_artifacts": {},
        "artifacts": {
            product_name: sorted(paths)
            for product_name, paths in artifact_paths.items()
            if paths
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
            for product_name in product_names:
                paths = sorted(artifact_paths.get(product_name, []))
                for relative in paths:
                    print(f"[*] Would write: {run_dir / relative}")
                if paths:
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
                "products": product_names,
                "product_counts": metadata["counts"]["product_counts"],
                "artifacts": metadata["artifacts"],
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
