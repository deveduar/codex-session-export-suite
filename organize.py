"""Run organization, session naming, metadata, and index generation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from extract import read_session_metadata


PRODUCT_TITLES = {
    "transcript": "Transcript",
    "memory": "Memory",
    "faithful": "Faithful",
    "digest": "Digest",
}

PRODUCT_EXTENSIONS = {
    "transcript": ".md",
    "memory": ".jsonl",
    "faithful": ".json",
    "digest": ".md",
}


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
            "updated_at": data.get("updated_at"),
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
    project = project_from_cwd(metadata.get("cwd"))
    date = session_date(metadata, file_path)
    short_id = short_session_id(metadata, file_path)
    label = thread_name or project or "session"
    slug = f"{date}_{slugify(label, 55)}_{short_id}"

    return {
        "thread_name": thread_name or None,
        "project": project,
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
) -> Dict[str, Any]:
    """Build the safe metadata record for one session."""
    metadata = read_session_metadata(file_path)
    session_id = str(metadata.get("id") or "")
    index_entry = session_index.get(session_id)
    identity = session_identity(metadata, index_entry, file_path)

    return {
        "id": metadata.get("id"),
        "thread_name": identity["thread_name"],
        "project": identity["project"],
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


def _session_rows(sessions: List[Dict[str, Any]], product_names: List[str]) -> List[str]:
    rows = []
    for session in sessions:
        outputs = session.get("outputs", {})
        if not outputs:
            continue

        date = str(session.get("started_at") or session.get("date") or "")[:10]
        name = _display_name(session)
        project = session.get("project") or ""
        links = [
            _markdown_link(outputs[name], name) if name in outputs else ""
            for name in product_names
        ]
        rows.append(
            f"| {date} | {_markdown_text(name)} | {_markdown_text(project)} | "
            + " | ".join(links)
            + " |"
        )
    return rows


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

    title = PRODUCT_TITLES.get(product_name, product_name.title())
    lines = [
        f"# {title} Export",
        "",
        f"- Run: `{run_id}`",
        f"- Sessions: {len(product_sessions)}",
        "",
        "| Date | Session | Project | Messages | File |",
        "|---|---|---|---|---|",
    ]

    for session in product_sessions:
        output = session["outputs"][product_name]
        date = str(session.get("started_at") or session.get("date") or "")[:10]
        name = _display_name(session)
        project = session.get("project") or ""
        messages = session.get("message_count", 0)
        lines.append(
            f"| {date} | {_markdown_text(name)} | {_markdown_text(project)} | "
            f"{messages} | {_markdown_link(Path(output).name, Path(output).name)} |"
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
    run_id = metadata.get("run_id", run_dir.name)

    lines = [
        f"# Codex Export Run: `{run_id}`",
        "",
        f"- Generated: {metadata.get('generated_at', '')}",
        f"- Codex directory: `{metadata.get('codex_dir') or ''}`",
        f"- Layout: {metadata.get('layout', '')}",
        f"- Preset: {metadata.get('preset') or '(none)'}",
        f"- Products: {', '.join(product_names)}",
        (
            f"- Sessions: {counts.get('sessions_exported', 0)} exported, "
            f"{counts.get('sessions_skipped', 0)} skipped"
        ),
        "",
        "## Product indexes",
        "",
    ]

    for product_name in product_names:
        count = sum(
            1 for session in sessions if product_name in session.get("outputs", {})
        )
        if count:
            title = PRODUCT_TITLES.get(product_name, product_name.title())
            lines.append(
                f"- {_markdown_link(f'{product_name}/index.md', title)} ({count})"
            )

    lines.extend(
        [
            "",
            "## Sessions",
            "",
            "| Date | Session | Project | "
            + " | ".join(product_names)
            + " |",
            "|---|---|---|" + "---|" * len(product_names),
        ]
    )
    lines.extend(_session_rows(sessions, product_names))

    skipped = [session for session in sessions if session.get("skipped")]
    if skipped:
        lines.extend(
            [
                "",
                "## Skipped sessions",
                "",
                "| Date | Session | Project | Reason |",
                "|---|---|---|---|",
            ]
        )
        for session in skipped:
            date = str(session.get("started_at") or session.get("date") or "")[:10]
            lines.append(
                f"| {date} | {_markdown_text(_display_name(session))} | "
                f"{_markdown_text(session.get('project') or '')} | "
                f"{_markdown_text(session.get('reason') or 'skipped')} |"
            )

    path = run_dir / "index.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_indexes(run_dir: Path, metadata: Dict[str, Any]) -> List[Path]:
    """Write product indexes and the run index."""
    paths = []
    sessions = metadata.get("sessions", [])
    run_id = metadata.get("run_id", run_dir.name)

    for product_name in metadata.get("products", []):
        path = write_product_index(run_dir, product_name, sessions, run_id)
        if path is not None:
            paths.append(path)

    paths.append(write_root_index(run_dir, metadata))
    return paths
