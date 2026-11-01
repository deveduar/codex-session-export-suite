"""Run organization, session naming, metadata, and index generation."""

from __future__ import annotations

import json
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from extract import read_session_metadata


PRODUCT_TITLES = {
    "transcript": "Transcript with Tool Activity",
    "conversation": "Conversation Only",
    "memory": "RAG Events",
    "instructions": "Developer Instructions",
    "faithful": "Source JSONL",
}

PRODUCT_EXTENSIONS = {
    "transcript": ".md",
    "conversation": ".md",
    "memory": ".jsonl",
    "instructions": ".md",
    "faithful": ".jsonl",
}

TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def _valid_usage_snapshot(value: Any) -> Optional[Dict[str, int]]:
    """Return a complete non-negative token usage snapshot, if valid."""
    if not isinstance(value, dict):
        return None

    snapshot = {}
    for field in TOKEN_USAGE_FIELDS:
        count = value.get(field)
        if type(count) is not int or count < 0:
            return None
        snapshot[field] = count
    return snapshot


def read_token_usage(file_path: Path) -> Dict[str, Any]:
    """Read the latest cumulative thread usage without loading transcript data."""
    record_count = 0
    valid_snapshot_count = 0
    latest_snapshot = None

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(record, dict) or record.get("type") != "token_usage_record":
                    continue

                record_count += 1
                payload = record.get("payload")
                payload = payload if isinstance(payload, dict) else {}
                snapshot = _valid_usage_snapshot(payload.get("thread_token_usage"))
                if snapshot is not None:
                    latest_snapshot = snapshot
                    valid_snapshot_count += 1
    except OSError:
        pass

    usage = {
        "source": "rollout.token_usage_record",
        "scope": "thread_cumulative",
        "record_count": record_count,
        "valid_snapshot_count": valid_snapshot_count,
    }
    if latest_snapshot is None:
        usage["status"] = "unavailable"
    else:
        usage["status"] = "available"
        usage.update(latest_snapshot)
    return usage


def summarize_token_usage(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize one latest usage snapshot per unique session/thread ID."""
    available_count = sum(
        1 for session in sessions
        if (session.get("usage") or {}).get("status") == "available"
    )
    summary: Dict[str, Any] = {
        "source": "rollout.token_usage_record",
        "aggregation": "latest_thread_snapshot_per_unique_session_id",
        "sessions_with_usage": available_count,
        "sessions_without_usage": len(sessions) - available_count,
    }

    latest_by_id: Dict[str, Dict[str, Any]] = {}
    missing_id_usage = False
    for session in sessions:
        session_id = session.get("id")
        if not session_id:
            if (session.get("usage") or {}).get("status") == "available":
                missing_id_usage = True
            continue
        session_id = str(session_id)
        current = latest_by_id.get(session_id)
        try:
            source_mtime = int(session.get("source_mtime_ns") or 0)
        except (TypeError, ValueError):
            source_mtime = 0
        try:
            current_mtime = int((current or {}).get("source_mtime_ns") or 0)
        except (TypeError, ValueError):
            current_mtime = 0
        if current is None or source_mtime >= current_mtime:
            latest_by_id[session_id] = session

    usage_threads = {
        session_id: session
        for session_id, session in latest_by_id.items()
        if (session.get("usage") or {}).get("status") == "available"
    }
    summary["unique_threads"] = len(latest_by_id)
    summary["unique_threads_with_usage"] = len(usage_threads)
    summary["unique_threads_without_usage"] = len(latest_by_id) - len(usage_threads)
    if missing_id_usage:
        summary["totals_status"] = "unavailable_missing_thread_id"
        return summary

    if not usage_threads:
        summary["totals_status"] = "unavailable_no_usage_records"
        return summary

    totals = {field: 0 for field in TOKEN_USAGE_FIELDS}
    agent_types: Dict[str, int] = {}
    for session in usage_threads.values():
        usage = session["usage"]
        for field in TOKEN_USAGE_FIELDS:
            totals[field] += usage[field]
        agent_type = "subagent" if session.get("parent_thread_id") else "root"
        agent_types[agent_type] = agent_types.get(agent_type, 0) + 1

    summary["totals_status"] = "partial" if available_count < len(sessions) else "available"
    summary["totals"] = totals
    summary["threads_with_usage_by_agent_type"] = agent_types
    return summary


def find_codex_root(path: Optional[Path]) -> Optional[Path]:
    """Find the Codex root that contains session_index.jsonl or sessions/."""
    if path is None:
        return None

    try:
        start = path.resolve()
    except OSError:
        start = path.absolute()

    if start.is_file():
        start = start.parent

    for candidate in (start, *start.parents):
        if (candidate / "session_index.jsonl").is_file():
            return candidate
        if candidate.name.lower() in ("sessions", "archived_sessions"):
            return candidate.parent
        if (candidate / "sessions").is_dir():
            return candidate

    return None


def load_session_index(codex_root: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Load session_index.jsonl into a mapping keyed by session id."""
    index: Dict[str, Dict[str, Any]] = {}
    if codex_root is None:
        return index

    index_path = codex_root / "session_index.jsonl"
    if not index_path.is_file():
        return index

    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return index

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue

        session_id = data.get("id")
        if not session_id:
            continue

        index[str(session_id)] = {
            "thread_name": data.get("thread_name"),
        }

    return index


def project_from_cwd(cwd: Optional[str]) -> Optional[str]:
    """Return the last path component from a Windows or POSIX cwd."""
    if not cwd:
        return None

    text = str(cwd).replace("\\", "/").rstrip("/")
    if not text:
        return None

    name = text.rsplit("/", 1)[-1]
    return name or None


def project_identity(metadata: Dict[str, Any]) -> Dict[str, str]:
    """Build a stable project folder name from cwd or a workspace root."""
    roots = metadata.get("workspace_roots") or []
    path = metadata.get("cwd") or (roots[0] if roots else None)
    if not path:
        return {"project": "unknown", "project_key": "unknown", "project_slug": "unknown"}

    normalized = re.sub(r"/+", "/", str(path).replace("\\", "/")).rstrip("/")
    if not normalized:
        normalized = str(path)
    windows_drive = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    wsl_drive = re.match(r"^/mnt/([A-Za-z])/(.*)$", normalized, flags=re.IGNORECASE)
    if windows_drive:
        key = f"{windows_drive.group(1)}:/{windows_drive.group(2)}".casefold()
    elif wsl_drive:
        key = f"{wsl_drive.group(1)}:/{wsl_drive.group(2)}".casefold()
    else:
        key = normalized.casefold() if os.name == "nt" else normalized
    name = project_from_cwd(normalized) or "project"
    suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return {
        "project": name,
        "project_key": key,
        "project_slug": f"{slugify(name, 48)}-{suffix}",
    }


def source_fingerprint(file_path: Path) -> Dict[str, Any]:
    """Return a content hash and filesystem details for update comparisons."""
    stat = file_path.stat()
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "source_sha256": digest.hexdigest(),
    }


def slugify(value: Any, max_length: int = 80) -> str:
    """Create a readable filename component that is safe on Windows."""
    text = str(value or "").strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w.-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-_.")

    if not text:
        text = "session"

    return text[:max_length].rstrip("-_.") or "session"


def session_date(metadata: Dict[str, Any], file_path: Path) -> str:
    """Return YYYY-MM-DD from session metadata or the source filename."""
    timestamp = metadata.get("timestamp")
    if timestamp:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", str(timestamp))
        if match:
            return match.group(1)

    match = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
    return match.group(1) if match else "unknown-date"


def short_session_id(metadata: Dict[str, Any], file_path: Path) -> str:
    """Return a short, filename-safe session id."""
    session_id = metadata.get("id")
    if session_id:
        compact = re.sub(r"[^A-Za-z0-9]", "", str(session_id))
        if compact:
            return compact[:8]

    compact = re.sub(r"[^A-Za-z0-9]", "", file_path.stem)
    return compact[-8:] or "session"


def session_identity(
    metadata: Dict[str, Any],
    index_entry: Optional[Dict[str, Any]],
    file_path: Path,
) -> Dict[str, Optional[str]]:
    """Build the human-readable session identity used in filenames."""
    thread_name = (index_entry or {}).get("thread_name")
    project = project_identity(metadata)
    date = session_date(metadata, file_path)
    short_id = short_session_id(metadata, file_path)
    label = thread_name or project["project"] or "session"
    slug = f"{date}_{slugify(label, 55)}_{short_id}"

    return {
        "thread_name": thread_name or None,
        **project,
        "date": date,
        "short_id": short_id,
        "slug": slug,
    }


def source_file_relative(file_path: Path, codex_root: Optional[Path]) -> str:
    """Return the source file path relative to the Codex root when possible."""
    try:
        resolved = file_path.resolve()
    except OSError:
        resolved = file_path.absolute()

    if codex_root is not None:
        try:
            return resolved.relative_to(codex_root.resolve()).as_posix()
        except (OSError, ValueError):
            pass

    return resolved.as_posix()


def build_session_record(
    file_path: Path,
    codex_root: Optional[Path],
    session_index: Dict[str, Dict[str, Any]],
    include_fingerprint: bool = True,
    include_usage: bool = True,
) -> Dict[str, Any]:
    """Build the safe metadata record for one session."""
    metadata = read_session_metadata(file_path)
    session_id = str(metadata.get("id") or "")
    index_entry = session_index.get(session_id)
    identity = session_identity(metadata, index_entry, file_path)

    record = {
        "id": metadata.get("id"),
        "parent_thread_id": metadata.get("parent_thread_id"),
        "thread_source": metadata.get("thread_source"),
        "agent_role": metadata.get("agent_role"),
        "agent_nickname": metadata.get("agent_nickname"),
        "thread_name": identity["thread_name"],
        "project": identity["project"],
        "project_key": identity["project_key"],
        "project_slug": identity["project_slug"],
        "cwd": metadata.get("cwd"),
        "workspace_roots": metadata.get("workspace_roots") or [],
        "started_at": metadata.get("timestamp"),
        "date": identity["date"],
        "source": metadata.get("source"),
        "originator": metadata.get("originator"),
        "cli_version": metadata.get("cli_version"),
        "model_provider": metadata.get("model_provider"),
        "git": metadata.get("git") or {},
        "source_file": source_file_relative(file_path, codex_root),
        "slug": identity["slug"],
    }
    if include_fingerprint:
        record.update(source_fingerprint(file_path))
    if include_usage:
        record["usage"] = read_token_usage(file_path)
    return record


def run_label(preset: Optional[str], products: List[str]) -> str:
    """Return the label appended to the timestamped run folder."""
    if preset:
        return slugify(preset, 40)
    return "products"


def next_run_dir(output_dir: Path, label: str, now: datetime) -> Path:
    """Return an unused timestamped run directory path."""
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    base_name = f"{stamp}_{slugify(label, 40)}"
    candidate = output_dir / base_name

    if not candidate.exists():
        return candidate

    for index in range(1, 1000):
        candidate = output_dir / f"{base_name}_{index:02d}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not allocate a run directory in: {output_dir}")


def create_run_dir(output_dir: Path, label: str, now: datetime) -> Path:
    """Create and return a unique timestamped run directory."""
    while True:
        run_dir = next_run_dir(output_dir, label, now)
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_dir
        except FileExistsError:
            continue


def product_filename(product_name: str, slug: str) -> str:
    """Return the filename for a product and session slug."""
    extension = PRODUCT_EXTENSIONS.get(product_name, ".md")
    return f"{slug}{extension}"


def write_metadata(run_dir: Path, metadata: Dict[str, Any]) -> Path:
    """Write metadata.json for an export run."""
    path = run_dir / "metadata.json"
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def find_latest_run(output_dir: Path) -> Optional[tuple[Path, Dict[str, Any]]]:
    """Load the most recently written run metadata under an output directory."""
    if not output_dir.is_dir():
        return None

    candidates = []
    for child in output_dir.iterdir():
        metadata_path = child / "metadata.json"
        if not child.is_dir() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            modified = metadata_path.stat().st_mtime_ns
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(metadata, dict):
            candidates.append((modified, child, metadata))

    if not candidates:
        return None

    _, run_dir, metadata = max(candidates, key=lambda item: item[0])
    return run_dir, metadata


def compare_session_records(
    previous: List[Dict[str, Any]],
    current: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Compare sessions by source SHA-256 relative to the current scan."""
    old_by_key = {
        str(record.get("id") or record.get("source_file")): record
        for record in previous
    }
    new_by_key = {
        str(record.get("id") or record.get("source_file")): record
        for record in current
    }
    result: Dict[str, List[Dict[str, Any]]] = {
        "new": [],
        "modified": [],
        "unchanged": [],
        "not_found_in_scan": [],
    }

    missing_hashes = [
        str(record.get("id") or record.get("source_file") or "unknown")
        for record in previous
        if not record.get("source_sha256")
    ]
    if missing_hashes:
        raise ValueError(
            f"baseline is missing source SHA-256 fingerprints for {len(missing_hashes)} session(s)"
        )

    for key, record in new_by_key.items():
        old = old_by_key.get(key)
        if old is None:
            result["new"].append(record)
        elif old.get("source_sha256") == record.get("source_sha256"):
            result["unchanged"].append(record)
        else:
            result["modified"].append(record)

    for key, record in old_by_key.items():
        if key not in new_by_key:
            result["not_found_in_scan"].append(record)

    return result


def _markdown_text(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def _markdown_link(path: str, text: str) -> str:
    return f"[{_markdown_text(text)}]({path})"


def _display_name(session: Dict[str, Any]) -> str:
    return (
        session.get("thread_name")
        or session.get("project")
        or session.get("id")
        or "session"
    )


def _session_usage_text(session: Dict[str, Any]) -> str:
    """Format per-session token counters compactly for the run index."""
    usage = session.get("usage") or {}
    if usage.get("status") != "available":
        return "unavailable"

    values = (
        usage.get("input_tokens"),
        usage.get("cached_input_tokens"),
        usage.get("cache_write_input_tokens"),
        usage.get("output_tokens"),
        usage.get("reasoning_output_tokens"),
        usage.get("total_tokens"),
    )
    if any(type(value) is not int for value in values):
        return "unavailable"
    return " / ".join(f"{value:,}" for value in values)


def _product_item_count(session: Dict[str, Any], product_name: str) -> int:
    """Return the count that best represents a product's content."""
    recorded = session.get("product_items", {}).get(product_name)
    if isinstance(recorded, int):
        return recorded
    if product_name == "instructions":
        return session.get("developer_messages", 0)
    if product_name == "memory":
        return session.get("event_count", 0)
    return session.get("message_count", 0)


def write_product_index(
    run_dir: Path,
    product_name: str,
    sessions: List[Dict[str, Any]],
    run_id: str,
) -> Optional[Path]:
    """Write index.md for one product."""
    product_sessions = [
        session for session in sessions if product_name in session.get("outputs", {})
    ]
    if not product_sessions:
        return None

    omitted = sum(
        1
        for session in sessions
        if product_name in session.get("skipped_products", [])
    )
    title = PRODUCT_TITLES.get(product_name, product_name.title())
    lines = [
        f"# {title} Export",
        "",
        f"- Run: `{run_id}`",
        f"- Sessions: {len(product_sessions)} of {len(sessions)}",
    ]
    if omitted:
        lines.append(f"- Omitted: {omitted} sessions with no usable content")
    lines.extend(
        [
            "",
            "| Date | Session | Project | Items | File |",
            "|---|---|---|---|---|",
        ]
    )

    for session in product_sessions:
        output = session["outputs"][product_name]
        date = str(session.get("started_at") or session.get("date") or "")[:10]
        name = _display_name(session)
        project = session.get("project") or ""
        items = _product_item_count(session, product_name)
        output_parts = PurePosixPath(output).parts
        relative_output = PurePosixPath(*output_parts[1:]).as_posix()
        lines.append(
            f"| {date} | {_markdown_text(name)} | {_markdown_text(project)} | "
            f"{items} | {_markdown_link(relative_output, Path(output).name)} |"
        )

    path = run_dir / product_name / "index.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_root_index(
    run_dir: Path,
    metadata: Dict[str, Any],
) -> Path:
    """Write the run-level index.md."""
    sessions = metadata.get("sessions", [])
    product_names = metadata.get("products", [])
    counts = metadata.get("counts", {})
    usage_summary = metadata.get("usage_summary") or {}
    run_id = metadata.get("run_id", run_dir.name)

    lines = [
        f"# Codex Export Run: `{run_id}`",
        "",
        f"- Generated: {metadata.get('generated_at', '')}",
        f"- Codex directory: `{metadata.get('codex_dir') or ''}`",
        f"- Layout: {metadata.get('layout', '')}",
        f"- Archived sessions included: {'yes' if metadata.get('include_archived') else 'no'}",
        f"- Preset: {metadata.get('preset') or '(none)'}",
        f"- Products: {', '.join(product_names)}",
        (
            "- Filters: "
            f"role={metadata.get('options', {}).get('role') or 'all'}; "
            f"developer={'on' if metadata.get('options', {}).get('include_developer') else 'off'}; "
            f"recent_turns={metadata.get('options', {}).get('recent_turns') if metadata.get('options', {}).get('recent_turns') is not None else 'all'}; "
            f"boilerplate={'on' if metadata.get('options', {}).get('strip_boilerplate') else 'off'}"
        ),
        (
            "- Sessions: "
            f"{counts.get('sessions_exported', 0)} exported, {counts.get('sessions_skipped', 0)} skipped | "
            f"derived={counts.get('sessions_with_derived_output', 0)} | source-only={counts.get('sessions_source_only', 0)}"
        ),
        (
            "- Messages: "
            f"{counts.get('sessions_with_messages', 0)} sessions with messages | "
            f"developer={counts.get('sessions_with_developer', 0)}"
        ),
    ]

    if usage_summary:
        found = usage_summary.get("sessions_with_usage", 0)
        total = len(sessions)
        totals_status = usage_summary.get("totals_status", "unavailable")
        lines.append(
            f"- Token usage: {found}/{total} sessions recorded; totals {totals_status}."
        )
        totals = usage_summary.get("totals")
        if isinstance(totals, dict):
            lines.append(
                "- Totals: "
                f"input {totals.get('input_tokens', 0):,}; "
                f"cached input {totals.get('cached_input_tokens', 0):,}; "
                f"output {totals.get('output_tokens', 0):,}; "
                f"reasoning output {totals.get('reasoning_output_tokens', 0):,}; "
                f"total {totals.get('total_tokens', 0):,}."
            )

    lines.extend(["", "## Product indexes", ""])

    omitted_counts = counts.get("product_omitted_counts", {})
    for product_name in product_names:
        count = sum(
            1 for session in sessions if product_name in session.get("outputs", {})
        )
        if count:
            omitted = omitted_counts.get(product_name, 0)
            title = PRODUCT_TITLES.get(product_name, product_name.title())
            details = f"{count} of {len(sessions)}"
            if omitted:
                details += f"; {omitted} omitted"
            lines.append(
                f"- {_markdown_link(f'{product_name}/index.md', title)} ({details})"
            )

    project_groups: Dict[str, List[Dict[str, Any]]] = {}
    for session in sessions:
        if session.get("outputs"):
            project_groups.setdefault(session.get("project_slug") or "unknown", []).append(session)
    if project_groups:
        lines.extend(["", "## Sessions by project"])
        for project_slug, project_sessions in sorted(project_groups.items()):
            project_name = project_sessions[0].get("project") or "Unknown project"
            lines.extend(
                [
                    "",
                    f"### {_markdown_text(project_name)}",
                    "",
                    "| Date | Session | Agent | Parent | Messages | Developer | Token usage | Files |",
                    "|---|---|---|---|---:|---:|---|---|",
                ]
            )
            sessions_by_id = {
                str(session.get("id")): session
                for session in project_sessions
                if session.get("id")
            }
            for session in project_sessions:
                date = str(session.get("started_at") or session.get("date") or "")[:10]
                name = _display_name(session)
                agent = (
                    session.get("agent_nickname")
                    or session.get("agent_role")
                    or session.get("thread_source")
                    or ""
                )
                parent_id = str(session.get("parent_thread_id") or "")
                parent_session = sessions_by_id.get(parent_id)
                if parent_session:
                    parent_output = next(iter(parent_session.get("outputs", {}).values()))
                    parent = _markdown_link(parent_output, _display_name(parent_session))
                else:
                    parent = _markdown_text(parent_id[:12])
                links = [
                    _markdown_link(
                        output,
                        PRODUCT_TITLES.get(product_name, product_name.title()),
                    )
                    for product_name, output in session.get("outputs", {}).items()
                ]
                lines.append(
                    f"| {date} | {_markdown_text(name)} | {_markdown_text(agent)} | "
                    f"{parent} | {session.get('message_count', 0)} | "
                    f"{session.get('developer_messages', 0)} | "
                    f"{_session_usage_text(session)} | {' · '.join(links)} |"
                )

    skipped = [session for session in sessions if session.get("skipped")]
    if skipped:
        lines.extend(
            [
                "",
                "## Skipped sessions",
                "",
                "| Date | Session | Project | Reason | Token usage |",
                "|---|---|---|---|---|",
            ]
        )
        for session in skipped:
            date = str(session.get("started_at") or session.get("date") or "")[:10]
            lines.append(
                f"| {date} | {_markdown_text(_display_name(session))} | "
                f"{_markdown_text(session.get('project') or '')} | "
                f"{_markdown_text(session.get('reason') or 'skipped')} | "
                f"{_session_usage_text(session)} |"
            )

    path = run_dir / "index.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_indexes(run_dir: Path, metadata: Dict[str, Any]) -> List[Path]:
    """Write product indexes and the project-grouped run index."""
    paths = []
    sessions = metadata.get("sessions", [])
    run_id = metadata.get("run_id", run_dir.name)

    for product_name in metadata.get("products", []):
        path = write_product_index(run_dir, product_name, sessions, run_id)
        if path is not None:
            paths.append(path)

    paths.append(write_root_index(run_dir, metadata))
    return paths
