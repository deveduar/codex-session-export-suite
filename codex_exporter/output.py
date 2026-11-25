"""Output formatting for Codex export products.

Formats Markdown and derived JSONL products. The faithful product copies its
source JSONL directly in the CLI.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def format_markdown_transcript(
    messages: List[dict],
    filename: str = "session",
    include_timestamps: bool = True,
    show_role: bool = True,
    title: Optional[str] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Format messages as a Markdown transcript.
    
    Args:
        messages: List of message dicts with 'role', 'timestamp', 'text' keys
        filename: Session filename for the header
        include_timestamps: Whether to include timestamps
        show_role: Whether to show role labels (USER/CODEX)
    
    Returns:
        Markdown-formatted string
    """
    lines = _markdown_frontmatter(filename, title, session_metadata)
    
    # Keep the original chronological order: user/assistant turns interleaved.
    for msg in messages:
        role = msg.get("role")
        if not show_role:
            header = ">"
        else:
            labels = {
                "user": "User",
                "assistant": "Codex",
                "developer": "Developer instruction",
            }
            label = labels.get(role, str(role or "Message"))
            header = f"> **{label}**"

        if include_timestamps and msg.get("timestamp"):
            header += f" · {msg['timestamp']}"

        lines.append(header)
        text = str(msg.get("text", ""))
        quoted_lines = [f"> {line}" if line else ">" for line in text.splitlines()]
        lines.extend(quoted_lines or [">"])
        lines.append("")
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines).rstrip() + "\n"


def _code_block(text: str, language: str = "text") -> List[str]:
    """Return a fenced code block whose fence cannot be closed by its content."""
    longest = max((len(match) for match in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}{language}", text, fence]


def _markdown_frontmatter(
    filename: str,
    title: Optional[str],
    session_metadata: Optional[Dict[str, Any]],
) -> List[str]:
    metadata = session_metadata or {}
    resolved_title = str(title or metadata.get("thread_name") or filename or "session")
    heading = " ".join(resolved_title.splitlines()).strip() or "session"
    fields = [
        ("title", resolved_title),
        ("session_id", metadata.get("id")),
        ("date", metadata.get("started_at")),
        ("project", metadata.get("project")),
        ("source_file", metadata.get("source_file")),
    ]
    lines = ["---"]
    lines.extend(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in fields
        if value not in (None, "")
    )
    lines.extend(["---", "", f"# {heading}", ""])
    return lines


def format_markdown_activity_transcript(
    events: List[dict],
    filename: str = "session",
    include_timestamps: bool = True,
    title: Optional[str] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Format messages and tool activity as one chronological Markdown transcript."""
    lines = _markdown_frontmatter(filename, title, session_metadata)

    for event in events:
        kind = event.get("kind")
        timestamp = event.get("timestamp")
        if kind == "message":
            role = event.get("role")
            labels = {
                "user": "User",
                "assistant": "Codex",
                "developer": "Developer instruction",
            }
            label = labels.get(role, str(role or "Message"))
            heading = f"## {label}"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            text = str(event.get("text", ""))
            lines.extend([f"> {line}" if line else ">" for line in text.splitlines()] or [">"])
        elif kind == "tool_call":
            tool = str(event.get("tool") or "tool")
            heading = f"## Tool call: `{tool}`"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            if event.get("call_id"):
                lines.append(f"Call ID: `{event['call_id']}`")
            if event.get("status"):
                lines.append(f"Status: `{event['status']}`")
            if event.get("arguments"):
                lines.extend(["", "Arguments:"])
                lines.extend(_code_block(str(event["arguments"])))
        elif kind == "tool_output":
            tool = str(event.get("tool") or "tool")
            heading = f"## Tool output: `{tool}`"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            if event.get("call_id"):
                lines.append(f"Call ID: `{event['call_id']}`")
            details = event.get("details") or {}
            if details:
                lines.extend(["", "Details:"])
                lines.extend(_code_block(json.dumps(details, ensure_ascii=False, indent=2), "json"))
            if event.get("output"):
                lines.extend(["", "Output:"])
                lines.extend(_code_block(str(event["output"])))
        elif kind == "activity":
            activity = str(event.get("activity") or "activity").replace("_", " ").title()
            heading = f"## {activity}"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            if event.get("event_id"):
                lines.append(f"Event ID: `{event['event_id']}`")
            if event.get("output"):
                lines.extend(["", "Details:"])
                lines.extend(_code_block(str(event["output"]), "json"))
        else:
            continue

        lines.extend(["", "---", ""])

    return "\n".join(lines).rstrip() + "\n"


def _truncated_copy(payload: Dict[str, Any], limit: Optional[int]) -> Dict[str, Any]:
    result = dict(payload)
    if not limit:
        return result
    text = result.get("text")
    if isinstance(text, str) and len(text) > limit:
        result["text"] = text[:limit] + "..."
    return result


def build_memory_record(
    session: Dict[str, Any],
    events: List[dict],
    messages: List[dict],
    parts: List[dict],
    usage: Dict[str, Any],
    children: Optional[List[Dict[str, Any]]] = None,
    truncate_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Build one session memory record with nested child sessions."""
    record: Dict[str, Any] = {
        "schema_version": 2,
        "record_type": "session_memory",
        "session": session.get("slug"),
        "session_id": session.get("id"),
        "session_title": session.get("thread_name") or session.get("slug"),
        "project": session.get("project"),
        "project_key": session.get("project_key"),
        "project_id": session.get("project_id"),
        "project_date": session.get("project_date"),
        "project_folder": session.get("project_folder"),
        "date": session.get("date"),
        "cwd": session.get("cwd"),
        "workspace_roots": session.get("workspace_roots") or [],
        "parent_thread_id": session.get("parent_thread_id"),
        "agent_role": session.get("agent_role"),
        "agent_nickname": session.get("agent_nickname"),
        "thread_source": session.get("thread_source"),
        "source_file": session.get("source_file"),
        "events": events,
        "messages": [_truncated_copy(item, truncate_chars) for item in messages],
        "parts": [_truncated_copy(item, truncate_chars) for item in parts],
        "usage": usage,
        "children": children or [],
    }
    if session.get("parent_unresolved"):
        record["parent_unresolved"] = True
    return record


def build_corpus_document(
    session: Dict[str, Any],
    documents: List[Dict[str, Any]],
    truncate_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Build one flattened corpus document from a root and its child sessions."""
    labeled = []
    contents = []
    source_files = []
    child_session_ids = []
    message_count = 0

    for position, document in enumerate(documents):
        member = document.get("session") or {}
        source_file = member.get("source_file")
        if source_file and source_file not in source_files:
            source_files.append(source_file)
        if position:
            session_id = member.get("id")
            if session_id and str(session_id) not in child_session_ids:
                child_session_ids.append(str(session_id))
        for message in document.get("messages") or []:
            text = str(message.get("text") or "")
            if not text:
                continue
            if truncate_chars and len(text) > truncate_chars:
                text = text[:truncate_chars] + "..."
            role = str(message.get("role") or "message")
            labeled.append(f"[{role}] {text}")
            contents.append(text)
            message_count += 1

    record: Dict[str, Any] = {
        "schema_version": 2,
        "record_type": "corpus_document",
        "session": session.get("slug"),
        "session_id": session.get("id"),
        "session_title": session.get("thread_name") or session.get("slug"),
        "project": session.get("project"),
        "project_key": session.get("project_key"),
        "project_id": session.get("project_id"),
        "project_date": session.get("project_date"),
        "project_folder": session.get("project_folder"),
        "date": session.get("date"),
        "cwd": session.get("cwd"),
        "source_files": source_files,
        "child_session_ids": child_session_ids,
        "message_count": message_count,
        "text": "\n".join(labeled),
        "content": "\n".join(contents),
    }
    if session.get("parent_unresolved"):
        record["parent_unresolved"] = True
    return record


def format_jsonl_memory(record: Dict[str, Any]) -> str:
    """Serialize one session-structured memory record as JSONL."""
    return json.dumps(record, ensure_ascii=False)


def format_jsonl_corpus(document: Dict[str, Any]) -> str:
    """Serialize one flattened corpus document as JSONL."""
    return json.dumps(document, ensure_ascii=False)
